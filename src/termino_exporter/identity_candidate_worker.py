"""Isolated browser-owning worker for Phase 4C-ID0 (never invoked directly by users)."""

from __future__ import annotations

import ctypes
import json
import os
import struct
import sys
import time
from collections.abc import Mapping
from ctypes import wintypes
from pathlib import Path
from typing import Any

from termino_exporter.identity_protocol import (
    COMMAND_RESPONSES,
    MAX_PAYLOAD_BYTES,
    PROTOCOL_VERSION,
    encode_frame,
)

BOOTSTRAP_EXIT = 70
WRITE_TIMEOUT_EXIT = 71
ERROR_IO_PENDING = 997
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


def _parse_handles(argv: list[str]) -> tuple[int, int] | None:
    if len(argv) != 4 or argv[0] != "--control-handle" or argv[2] != "--result-handle":
        return None
    try:
        values = (int(argv[1], 10), int(argv[3], 10))
    except ValueError:
        return None
    if any(value <= 0 for value in values) or values[0] == values[1]:
        return None
    return values


def _set_noninheritable(handle: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    return bool(kernel32.SetHandleInformation(wintypes.HANDLE(handle), 1, 0))


def _io_chunk(
    handle: int,
    buffer: ctypes.Array[ctypes.c_char],
    size: int,
    *,
    write: bool,
    deadline_ns: int | None,
) -> int | None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    event = kernel32.CreateEventW(None, True, False, None)
    if not event:
        return None
    overlapped = OVERLAPPED()
    overlapped.hEvent = event
    transferred = wintypes.DWORD()
    try:
        operation = kernel32.WriteFile if write else kernel32.ReadFile
        if operation(
            wintypes.HANDLE(handle),
            buffer,
            size,
            ctypes.byref(transferred),
            ctypes.byref(overlapped),
        ):
            return int(transferred.value)
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            return None
        timeout_ms = 0xFFFFFFFF
        if deadline_ns is not None:
            timeout_ms = max(0, (deadline_ns - time.monotonic_ns() + 999_999) // 1_000_000)
        wait = kernel32.WaitForSingleObject(event, timeout_ms)
        if wait == WAIT_TIMEOUT:
            kernel32.CancelIoEx(wintypes.HANDLE(handle), ctypes.byref(overlapped))
            return -1
        if wait != WAIT_OBJECT_0 or not kernel32.GetOverlappedResult(
            wintypes.HANDLE(handle),
            ctypes.byref(overlapped),
            ctypes.byref(transferred),
            False,
        ):
            return None
        return int(transferred.value)
    finally:
        kernel32.CloseHandle(event)


def _read_exact(handle: int, size: int, deadline_ns: int | None) -> bytes | None:
    result = bytearray()
    while len(result) < size:
        chunk_size = min(4096, size - len(result))
        buffer = ctypes.create_string_buffer(chunk_size)
        received = _io_chunk(handle, buffer, chunk_size, write=False, deadline_ns=deadline_ns)
        if received is None or received <= 0:
            return None
        result.extend(buffer.raw[:received])
    return bytes(result)


def _read_message(
    handle: int, expected_types: set[str], deadline_ns: int | None
) -> tuple[str, int, dict[str, object]] | None:
    prefix = _read_exact(handle, 4, deadline_ns)
    if prefix is None:
        return None
    length = struct.unpack(">I", prefix)[0]
    if not 1 <= length <= MAX_PAYLOAD_BYTES:
        return None
    body = _read_exact(handle, length, deadline_ns)
    if body is None:
        return None
    try:

        def exact_object(items: list[tuple[str, object]]) -> dict[str, object]:
            result: dict[str, object] = {}
            for key, value in items:
                if key in result:
                    raise ValueError
                result[key] = value
            return result

        envelope = json.loads(body.decode("utf-8"), object_pairs_hook=exact_object)
        if not isinstance(envelope, dict):
            return None
        if set(envelope) != {"protocol_version", "message_type", "sequence_id", "payload"}:
            return None
        sequence = envelope["sequence_id"]
        payload = envelope["payload"]
        if (
            envelope["protocol_version"] != PROTOCOL_VERSION
            or envelope["message_type"] not in expected_types
            or not isinstance(sequence, int)
            or isinstance(sequence, bool)
            or not 1 <= sequence <= 0xFFFF_FFFF
            or not isinstance(payload, dict)
        ):
            return None
        return str(envelope["message_type"]), sequence, payload
    except (UnicodeError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_all(handle: int, data: bytes) -> bool:
    deadline_ns = time.monotonic_ns() + 5_000_000_000
    offset = 0
    while offset < len(data):
        chunk = data[offset : offset + 4096]
        buffer = ctypes.create_string_buffer(chunk)
        written = _io_chunk(handle, buffer, len(chunk), write=True, deadline_ns=deadline_ns)
        if written is None or written <= 0:
            return False
        offset += written
    return True


def _send(handle: int, command: str, sequence: int, payload: Mapping[str, object]) -> bool:
    try:
        frame = encode_frame(COMMAND_RESPONSES[command], sequence, payload)
    except Exception:
        return False
    return _write_all(handle, frame)


def _empty(payload: Mapping[str, object]) -> bool:
    return not payload


def _detail_payload(page: Any, command: str) -> dict[str, object]:
    from termino_exporter.identity_candidate import IdentityCandidateError, known_detail_state

    try:
        state = known_detail_state(page)
        return {"code": "ID0_DETAIL_CHECK_OK", "detail_state": state}
    except IdentityCandidateError:
        code = {
            "BASELINE_DETAIL_CHECK": "ID0_BASELINE_DETAIL_CHECK_FAILED",
            "OPEN_DETAIL_CHECK": "ID0_MANUAL_OPEN_DETAIL_CHECK_FAILED",
            "CLOSE_DETAIL_CHECK": "ID0_MANUAL_CLOSE_DETAIL_CHECK_FAILED",
        }[command]
        return {"code": code, "detail_state": "UNKNOWN_OR_AMBIGUOUS"}


def worker_main(argv: list[str] | None = None) -> int:
    """Run the exact single-context worker state machine with silent standard streams."""
    if os.name != "nt":
        return BOOTSTRAP_EXIT
    handles = _parse_handles(sys.argv[1:] if argv is None else argv)
    if handles is None:
        return BOOTSTRAP_EXIT
    control, result = handles
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetStdHandle.restype = wintypes.HANDLE
    standard_handles = {
        int(kernel32.GetStdHandle(-10)),
        int(kernel32.GetStdHandle(-11)),
        int(kernel32.GetStdHandle(-12)),
    }
    if (
        any(handle <= 0 or handle == -1 for handle in standard_handles)
        or not _set_noninheritable(control)
        or not _set_noninheritable(result)
        or not all(_set_noninheritable(handle) for handle in standard_handles)
    ):
        return BOOTSTRAP_EXIT
    playwright = None
    context = None
    page = None
    token: str | None = None
    clear_confirmed = False
    expected = "START_BROWSER"
    try:
        while True:
            read_deadline = (
                time.monotonic_ns() + 5_000_000_000 if expected == "START_BROWSER" else None
            )
            allowed = {expected}
            if token is not None and not clear_confirmed:
                allowed.add("CLEAR")
            if context is not None:
                allowed.add("CLOSE_CONTEXT")
            if expected != "START_BROWSER":
                allowed.add("SHUTDOWN")
            message = _read_message(control, allowed, read_deadline)
            if message is None:
                return BOOTSTRAP_EXIT if expected == "START_BROWSER" else 1
            command, sequence, payload = message
            response: dict[str, object]
            if command == "START_BROWSER":
                if set(payload) != {"profile_dir", "timeout_ms"}:
                    return 1
                profile = payload["profile_dir"]
                timeout_ms = payload["timeout_ms"]
                if (
                    not isinstance(profile, str)
                    or not 1 <= len(profile.encode("utf-8")) <= 8192
                    or not isinstance(timeout_ms, int)
                    or isinstance(timeout_ms, bool)
                    or not 1 <= timeout_ms <= 300_000
                ):
                    return 1
                try:
                    from playwright.sync_api import sync_playwright

                    playwright = sync_playwright().start()
                except Exception:
                    response = {"code": "ID0_BROWSER_FAILED", "context_created": False}
                else:
                    try:
                        Path(profile).mkdir(parents=True, exist_ok=True)
                        context = playwright.chromium.launch_persistent_context(
                            user_data_dir=profile, headless=False
                        )
                        context.set_default_timeout(timeout_ms)
                        page = context.pages[0] if context.pages else context.new_page()
                        response = {"code": "ID0_BROWSER_READY", "context_created": True}
                    except Exception:
                        response = {
                            "code": "ID0_PROFILE_IN_USE_OR_UNAVAILABLE",
                            "context_created": False,
                        }
                expected = "NAVIGATE" if context is not None else "SHUTDOWN"
            elif command == "NAVIGATE":
                if set(payload) != {"url", "timeout_ms"} or page is None:
                    return 1
                url, timeout_ms = payload["url"], payload["timeout_ms"]
                if not isinstance(url, str) or not isinstance(timeout_ms, int):
                    return 1
                try:
                    page.goto(url, timeout=timeout_ms)
                    response = {"code": "ID0_NAVIGATED", "navigated": True}
                    expected = "BASELINE_DETAIL_CHECK"
                except Exception:
                    response = {"code": "ID0_CALENDAR_OPEN_FAILED", "navigated": False}
                    expected = "CLOSE_CONTEXT"
            elif command in {
                "BASELINE_DETAIL_CHECK",
                "OPEN_DETAIL_CHECK",
                "CLOSE_DETAIL_CHECK",
            }:
                if not _empty(payload) or page is None:
                    return 1
                response = _detail_payload(page, command)
                state = response["detail_state"]
                if command == "BASELINE_DETAIL_CHECK" and state == "KNOWN_DETAIL_ABSENT":
                    expected = "BASELINE_REGISTER"
                elif command == "OPEN_DETAIL_CHECK" and state == "KNOWN_DETAIL_PRESENT":
                    expected = "OPEN_CENSUS"
                elif command == "CLOSE_DETAIL_CHECK" and state == "KNOWN_DETAIL_ABSENT":
                    expected = "CLOSE_CENSUS"
                else:
                    expected = "CLEAR" if token is not None else "CLOSE_CONTEXT"
            elif command == "BASELINE_REGISTER":
                if not _empty(payload) or page is None:
                    return 1
                from termino_exporter.identity_candidate import (
                    new_channel_token,
                    register_private_state,
                    sanitize_browser_projection,
                )

                token = new_channel_token()
                raw_projection = register_private_state(page, token)
                try:
                    projection = sanitize_browser_projection(raw_projection, "baseline")
                except Exception:
                    projection = {"code": "ID0_INVALID_SANITIZED_PAYLOAD", "stage": "FAILED"}
                response = {
                    "code": "ID0_BASELINE_REGISTER_RESULT",
                    "post_baseline_t0_ns": time.monotonic_ns(),
                    "projection": projection,
                }
                expected = (
                    "OPEN_DETAIL_CHECK"
                    if isinstance(projection, Mapping)
                    and projection.get("code") == "ID0_BASELINE_REGISTERED"
                    else "CLEAR"
                )
            elif command in {"OPEN_CENSUS", "CLOSE_CENSUS"}:
                if not _empty(payload) or page is None or token is None:
                    return 1
                from termino_exporter.identity_candidate import (
                    private_state_command,
                    sanitize_browser_projection,
                )

                raw_projection = private_state_command(page, token, command)
                try:
                    projection = sanitize_browser_projection(
                        raw_projection, "open" if command == "OPEN_CENSUS" else "close"
                    )
                except Exception:
                    projection = {"code": "ID0_INVALID_SANITIZED_PAYLOAD", "stage": "FAILED"}
                response = {"code": f"ID0_{command}_RESULT", "projection": projection}
                expected = (
                    "CLOSE_DETAIL_CHECK"
                    if command == "OPEN_CENSUS"
                    and isinstance(projection, Mapping)
                    and projection.get("code") == "ID0_OPEN_CENSUS_OK"
                    else "CLEAR"
                )
            elif command == "CLEAR":
                if not _empty(payload):
                    return 1
                if clear_confirmed:
                    response = {"code": "ID0_PRIVATE_STATE_CLEARED", "cleared": True}
                elif page is not None and token is not None:
                    from termino_exporter.identity_candidate import private_state_command

                    raw = private_state_command(page, token, "CLEAR")
                    if (
                        isinstance(raw, Mapping)
                        and raw.get("code") == "ID0_PRIVATE_STATE_CLEARED"
                        and raw.get("cleared") is True
                    ):
                        clear_confirmed = True
                        response = {"code": "ID0_PRIVATE_STATE_CLEARED", "cleared": True}
                    else:
                        response = {"code": "ID0_PRIVATE_STATE_CLEANUP_FAILED", "cleared": False}
                else:
                    response = {"code": "ID0_PRIVATE_STATE_CLEANUP_FAILED", "cleared": False}
                expected = "CLOSE_CONTEXT"
            elif command == "CLOSE_CONTEXT":
                if not _empty(payload):
                    return 1
                try:
                    if context is not None:
                        context.close()
                    context = None
                    response = {"code": "ID0_BROWSER_CONTEXT_CLOSED", "closed": True}
                except Exception:
                    response = {"code": "ID0_BROWSER_CLOSE_FAILED", "closed": False}
                expected = "SHUTDOWN"
            elif command == "SHUTDOWN":
                if not _empty(payload):
                    return 1
                response = {"code": "ID0_WORKER_SHUTDOWN_ACKNOWLEDGED", "exiting": True}
            else:
                return 1
            if not _send(result, command, sequence, response):
                return WRITE_TIMEOUT_EXIT
            if response.get("exiting") is True:
                return 0
    except KeyboardInterrupt:
        return 1
    except Exception:
        return 1
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CloseHandle(wintypes.HANDLE(control))
        kernel32.CloseHandle(wintypes.HANDLE(result))


if __name__ == "__main__":
    raise SystemExit(worker_main())
