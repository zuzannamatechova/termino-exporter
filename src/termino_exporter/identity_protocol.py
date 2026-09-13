"""Bounded, sanitized IPC framing for the Phase 4C-ID0 worker."""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

PROTOCOL_VERSION: Final = 1
MAX_PAYLOAD_BYTES: Final = 32_768
MAX_FRAME_BYTES: Final = MAX_PAYLOAD_BYTES + 4
MAX_SEQUENCE_ID: Final = 0xFFFF_FFFF

COMMAND_RESPONSES: Final = {
    "START_BROWSER": "START_BROWSER_RESULT",
    "NAVIGATE": "NAVIGATE_RESULT",
    "BASELINE_DETAIL_CHECK": "BASELINE_DETAIL_RESULT",
    "BASELINE_REGISTER": "BASELINE_REGISTER_RESULT",
    "OPEN_DETAIL_CHECK": "OPEN_DETAIL_RESULT",
    "OPEN_CENSUS": "OPEN_CENSUS_RESULT",
    "CLOSE_DETAIL_CHECK": "CLOSE_DETAIL_RESULT",
    "CLOSE_CENSUS": "CLOSE_CENSUS_RESULT",
    "CLEAR": "CLEAR_RESULT",
    "CLOSE_CONTEXT": "CLOSE_CONTEXT_RESULT",
    "SHUTDOWN": "SHUTDOWN_RESULT",
}
MESSAGE_TYPES: Final = frozenset((*COMMAND_RESPONSES, *COMMAND_RESPONSES.values()))


class IdentityProtocolError(RuntimeError):
    """A protocol failure whose public representation is always a fixed code."""

    def __init__(self, code: str = "ID0_INVALID_SANITIZED_PAYLOAD") -> None:
        self.code = code
        super().__init__(code)


def _reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def encode_frame(message_type: str, sequence_id: int, payload: Mapping[str, object]) -> bytes:
    """Encode one deterministic UTF-8 JSON frame after validating its envelope."""
    if (
        message_type not in MESSAGE_TYPES
        or not isinstance(sequence_id, int)
        or isinstance(sequence_id, bool)
        or not 1 <= sequence_id <= MAX_SEQUENCE_ID
        or not isinstance(payload, Mapping)
    ):
        raise IdentityProtocolError()
    envelope = {
        "protocol_version": PROTOCOL_VERSION,
        "message_type": message_type,
        "sequence_id": sequence_id,
        "payload": dict(payload),
    }
    try:
        body = json.dumps(
            envelope, ensure_ascii=True, separators=(",", ":"), sort_keys=True
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as error:
        raise IdentityProtocolError() from error
    if not 1 <= len(body) <= MAX_PAYLOAD_BYTES:
        raise IdentityProtocolError()
    return struct.pack(">I", len(body)) + body


def decode_frame(
    frame: bytes, *, expected_type: str, expected_sequence_id: int
) -> dict[str, object]:
    """Decode one complete frame without reflecting invalid content in an error."""
    try:
        if not isinstance(frame, bytes) or len(frame) < 4:
            raise ValueError
        size = struct.unpack(">I", frame[:4])[0]
        if not 1 <= size <= MAX_PAYLOAD_BYTES or len(frame) != size + 4:
            raise ValueError
        decoded = json.loads(frame[4:].decode("utf-8"), object_pairs_hook=_reject_duplicates)
        if not isinstance(decoded, dict) or set(decoded) != {
            "protocol_version",
            "message_type",
            "sequence_id",
            "payload",
        }:
            raise ValueError
        if (
            decoded["protocol_version"] != PROTOCOL_VERSION
            or isinstance(decoded["protocol_version"], bool)
            or decoded["message_type"] != expected_type
            or decoded["sequence_id"] != expected_sequence_id
            or isinstance(decoded["sequence_id"], bool)
            or not isinstance(decoded["payload"], dict)
        ):
            raise ValueError
        return decoded["payload"]
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as error:
        raise IdentityProtocolError() from error


@dataclass(slots=True)
class IncrementalFrameReader:
    """Bounded state machine for deterministic partial prefix/body reads."""

    _prefix: bytearray
    _body: bytearray
    _expected_body: int | None
    _complete: bool

    def __init__(self) -> None:
        self._prefix = bytearray()
        self._body = bytearray()
        self._expected_body = None
        self._complete = False

    @property
    def bytes_received(self) -> int:
        return len(self._prefix) + len(self._body)

    @property
    def complete(self) -> bool:
        return self._complete

    @property
    def partial(self) -> bool:
        return self.bytes_received > 0 and not self.complete

    def feed(self, data: bytes) -> None:
        if self._complete or not isinstance(data, bytes):
            raise IdentityProtocolError()
        view = memoryview(data)
        prefix_needed = 4 - len(self._prefix)
        if prefix_needed:
            take = min(prefix_needed, len(view))
            self._prefix.extend(view[:take])
            view = view[take:]
            if len(self._prefix) == 4:
                self._expected_body = struct.unpack(">I", self._prefix)[0]
                if not 1 <= self._expected_body <= MAX_PAYLOAD_BYTES:
                    raise IdentityProtocolError()
        if view:
            if self._expected_body is None:
                raise IdentityProtocolError()
            remaining = self._expected_body - len(self._body)
            if len(view) > remaining:
                raise IdentityProtocolError()
            self._body.extend(view)
        self._complete = self._expected_body is not None and len(self._body) == self._expected_body

    def frame(self) -> bytes:
        if not self._complete:
            raise IdentityProtocolError("ID0_IPC_CHANNEL_BROKEN")
        return bytes(self._prefix + self._body)


def worker_exit_code(*, started: bool, bytes_received: int, status: int) -> str:
    """Apply the normative no-complete-frame worker-exit mapping."""
    if bytes_received:
        return "ID0_IPC_CHANNEL_BROKEN"
    if not started and status == 70:
        return "ID0_WORKER_BOOTSTRAP_FAILED"
    if started and status == 71:
        return "ID0_IPC_WRITE_TIMEOUT"
    return "ID0_WORKER_EXITED_WITHOUT_RESPONSE" if started else "ID0_WORKER_BOOTSTRAP_FAILED"


def clipped_timeout_ns(local_seconds: float, now_ns: int, global_deadline_ns: int | None) -> int:
    """Return a non-negative timeout clipped to one immutable global deadline."""
    local_ns = max(0, int(local_seconds * 1_000_000_000))
    if global_deadline_ns is None:
        return local_ns
    return max(0, min(local_ns, global_deadline_ns - now_ns))
