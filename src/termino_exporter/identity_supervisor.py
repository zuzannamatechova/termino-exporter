"""Parent-owned Windows supervisor for the Phase 4C-ID0 diagnostic."""

from __future__ import annotations

import ctypes
import time
from collections.abc import Mapping
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from termino_exporter.browser import ProfilePathError, safe_profile_dir
from termino_exporter.identity_candidate import (
    IdentityCandidateDiagnosticResult,
    IdentityCandidateError,
    deserialize_final_result,
    sanitize_browser_projection,
)
from termino_exporter.identity_output import TextWriter
from termino_exporter.identity_protocol import clipped_timeout_ns, decode_frame, encode_frame
from termino_exporter.identity_windows import (
    ProfileLease,
    active_processes,
    atomic_spawn_worker,
    close_handle,
    console_preflight,
    create_event,
    create_ipc_handles,
    create_kill_on_close_job,
    read_frame,
    terminate_job,
    wait_for_console_enter,
    write_frame,
)

OPERATIONAL_SECONDS: Final = 220.0
SUPERVISOR_SECONDS: Final = 222.0
COMMAND_SECONDS: Final = 5.0
MANUAL_OPEN_SECONDS: Final = 120.0
MANUAL_CLOSE_SECONDS: Final = 60.0
SHUTDOWN_SECONDS: Final = 2.0

WORKFLOW_INSTRUCTIONS: Final = (
    "1. Ručně se přihlaste, zvolte pohled Den a dummy-only datum se 2 až 10 zjevně "
    "testovacími rezervacemi; známý detail nechte zavřený. Nepoužívejte Upravit, "
    "Odstranit ani Zkopírovat rezervaci. Potom stiskněte Enter.\n"
    "2. Ručně otevřete právě jednu známou dummy rezervaci a stiskněte Enter.\n"
    "3. Ručně zavřete tentýž detail běžným ovládacím prvkem a stiskněte Enter.\n"
)


@dataclass(slots=True)
class _Session:
    process_handle: int
    control_write: int
    result_read: int
    interrupt_event: int
    sequence: int = 1
    operational_deadline_ns: int | None = None
    supervisor_deadline_ns: int | None = None

    def transact(
        self,
        command: str,
        payload: Mapping[str, object],
        *,
        local_seconds: float,
        timeout_code: str,
    ) -> dict[str, object]:
        now = time.monotonic_ns()
        allowed = clipped_timeout_ns(local_seconds, now, self.operational_deadline_ns)
        if allowed <= 0:
            raise IdentityCandidateError("ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED")
        deadline = now + allowed
        sequence = self.sequence
        self.sequence += 1
        frame = encode_frame(command, sequence, payload)
        write_frame(
            self.control_write,
            frame,
            process_handle=self.process_handle,
            interrupt_event=self.interrupt_event,
            deadline_ns=deadline,
        )
        try:
            raw = read_frame(
                self.result_read,
                process_handle=self.process_handle,
                interrupt_event=self.interrupt_event,
                deadline_ns=deadline,
            )
        except IdentityCandidateError as error:
            if error.code == "ID0_STAGE_TIMEOUT":
                raise IdentityCandidateError(timeout_code) from error
            raise
        return decode_frame(
            raw,
            expected_type={
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
            }[command],
            expected_sequence_id=sequence,
        )


def _fixed_code(payload: Mapping[str, object], keys: set[str]) -> str:
    if set(payload) != keys or not isinstance(payload.get("code"), str):
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    code = payload["code"]
    if not isinstance(code, str):
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    if not code.isascii() or not code.startswith("ID0_") or len(code) > 64:
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    return code


def _expect_boolean_result(
    payload: Mapping[str, object], *, success_code: str, boolean_key: str, failure_code: str
) -> None:
    code = _fixed_code(payload, {"code", boolean_key})
    value = payload[boolean_key]
    if not isinstance(value, bool):
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    if code != success_code or value is not True:
        raise IdentityCandidateError(failure_code)


def _expect_detail(payload: Mapping[str, object], stage: str) -> None:
    code = _fixed_code(payload, {"code", "detail_state"})
    state = payload["detail_state"]
    if code != "ID0_DETAIL_CHECK_OK" or state not in {
        "KNOWN_DETAIL_PRESENT",
        "KNOWN_DETAIL_ABSENT",
        "UNKNOWN_OR_AMBIGUOUS",
    }:
        raise IdentityCandidateError(
            {
                "baseline": "ID0_BASELINE_DETAIL_CHECK_FAILED",
                "open": "ID0_MANUAL_OPEN_DETAIL_CHECK_FAILED",
                "close": "ID0_MANUAL_CLOSE_DETAIL_CHECK_FAILED",
            }[stage]
        )
    expected = {
        "baseline": "KNOWN_DETAIL_ABSENT",
        "open": "KNOWN_DETAIL_PRESENT",
        "close": "KNOWN_DETAIL_ABSENT",
    }[stage]
    if state == expected:
        return
    codes = {
        ("baseline", "KNOWN_DETAIL_PRESENT"): "ID0_BASELINE_DETAIL_ALREADY_OPEN",
        ("baseline", "UNKNOWN_OR_AMBIGUOUS"): "ID0_BASELINE_DETAIL_STATE_AMBIGUOUS",
        ("open", "KNOWN_DETAIL_ABSENT"): "ID0_MANUAL_OPEN_DETAIL_NOT_CONFIRMED",
        ("open", "UNKNOWN_OR_AMBIGUOUS"): "ID0_MANUAL_OPEN_DETAIL_UNKNOWN_OR_AMBIGUOUS",
        ("close", "KNOWN_DETAIL_PRESENT"): "ID0_MANUAL_CLOSE_DETAIL_STILL_OPEN",
        ("close", "UNKNOWN_OR_AMBIGUOUS"): "ID0_MANUAL_CLOSE_DETAIL_UNKNOWN_OR_AMBIGUOUS",
    }
    raise IdentityCandidateError(codes[(stage, state)])


def _validated_projection(payload: object, stage: str, success_code: str) -> dict[str, object]:
    projection = sanitize_browser_projection(payload, stage)
    code = projection["code"]
    if code != success_code:
        if not isinstance(code, str):
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        raise IdentityCandidateError(code)
    return projection


def _write_instructions(stdout: TextWriter) -> None:
    try:
        write = stdout.write
        flush = stdout.flush
        if write(WORKFLOW_INSTRUCTIONS) != len(WORKFLOW_INSTRUCTIONS):
            raise OSError
        flush()
    except Exception as error:
        raise IdentityCandidateError("ID0_OUTPUT_FAILED") from error


def run_identity_supervisor(
    *,
    url: str,
    profile_dir: Path,
    timeout_seconds: float,
    stdout: TextWriter,
) -> IdentityCandidateDiagnosticResult:
    """Run ID0 and return a result only after graceful zero-process shutdown."""
    console = console_preflight()
    try:
        profile_dir = safe_profile_dir(profile_dir)
    except ProfilePathError as error:
        raise IdentityCandidateError("ID0_UNSAFE_PROFILE_DIR") from error
    lease = ProfileLease.acquire(profile_dir)
    job = interrupt = 0
    ipc = None
    worker = None
    session = None
    primary: IdentityCandidateError | None = None
    result_model: IdentityCandidateDiagnosticResult | None = None
    hard_required = False
    context_created = False
    private_state_possible = False
    clear_confirmed = False
    context_closed = False
    shutdown_acknowledged = False
    try:
        _write_instructions(stdout)
        job = create_kill_on_close_job()
        interrupt = create_event(manual_reset=True)
        ipc = create_ipc_handles()
        worker = atomic_spawn_worker(
            child_handles=(
                ipc.control_read_child,
                ipc.result_write_child,
                ipc.null_read_child,
                ipc.null_write_child,
            ),
            job_handle=job,
        )
        ipc.close_children()
        session = _Session(worker.process_handle, ipc.control_write, ipc.result_read, interrupt)
        timeout_ms = int(timeout_seconds * 1000)
        start = session.transact(
            "START_BROWSER",
            {"profile_dir": str(profile_dir), "timeout_ms": timeout_ms},
            local_seconds=timeout_seconds,
            timeout_code="ID0_BROWSER_START_TIMEOUT",
        )
        _expect_boolean_result(
            start,
            success_code="ID0_BROWSER_READY",
            boolean_key="context_created",
            failure_code="ID0_PROFILE_IN_USE_OR_UNAVAILABLE",
        )
        context_created = True
        navigation = session.transact(
            "NAVIGATE",
            {"url": url, "timeout_ms": timeout_ms},
            local_seconds=timeout_seconds,
            timeout_code="ID0_CALENDAR_OPEN_TIMEOUT",
        )
        _expect_boolean_result(
            navigation,
            success_code="ID0_NAVIGATED",
            boolean_key="navigated",
            failure_code="ID0_CALENDAR_OPEN_FAILED",
        )
        wait_for_console_enter(console, worker.process_handle, interrupt, deadline_ns=None)
        _expect_detail(
            session.transact(
                "BASELINE_DETAIL_CHECK",
                {},
                local_seconds=COMMAND_SECONDS,
                timeout_code="ID0_BASELINE_DETAIL_CHECK_TIMEOUT",
            ),
            "baseline",
        )
        private_state_possible = True
        baseline_response = session.transact(
            "BASELINE_REGISTER",
            {},
            local_seconds=COMMAND_SECONDS,
            timeout_code="ID0_CENSUS_TIMEOUT",
        )
        if (
            _fixed_code(baseline_response, {"code", "post_baseline_t0_ns", "projection"})
            != "ID0_BASELINE_REGISTER_RESULT"
        ):
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        timestamp = baseline_response["post_baseline_t0_ns"]
        if not isinstance(timestamp, int) or isinstance(timestamp, bool):
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        now = time.monotonic_ns()
        if timestamp > now or now - timestamp > 5_000_000_000:
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        session.operational_deadline_ns = timestamp + int(OPERATIONAL_SECONDS * 1e9)
        session.supervisor_deadline_ns = timestamp + int(SUPERVISOR_SECONDS * 1e9)
        baseline_projection = _validated_projection(
            baseline_response["projection"], "baseline", "ID0_BASELINE_REGISTERED"
        )
        manual_open_deadline = min(
            timestamp + int(MANUAL_OPEN_SECONDS * 1e9), session.operational_deadline_ns
        )
        try:
            wait_for_console_enter(
                console, worker.process_handle, interrupt, deadline_ns=manual_open_deadline
            )
        except IdentityCandidateError as error:
            if error.code == "ID0_STAGE_TIMEOUT":
                if time.monotonic_ns() >= session.operational_deadline_ns:
                    raise IdentityCandidateError(
                        "ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED"
                    ) from error
                raise IdentityCandidateError("ID0_MANUAL_OPEN_TIMEOUT") from error
            raise
        _expect_detail(
            session.transact(
                "OPEN_DETAIL_CHECK",
                {},
                local_seconds=COMMAND_SECONDS,
                timeout_code="ID0_MANUAL_OPEN_DETAIL_CHECK_TIMEOUT",
            ),
            "open",
        )
        open_response = session.transact(
            "OPEN_CENSUS", {}, local_seconds=COMMAND_SECONDS, timeout_code="ID0_CENSUS_TIMEOUT"
        )
        if _fixed_code(open_response, {"code", "projection"}) != "ID0_OPEN_CENSUS_RESULT":
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        open_projection = _validated_projection(
            open_response["projection"], "open", "ID0_OPEN_CENSUS_OK"
        )
        close_start = time.monotonic_ns()
        manual_close_deadline = min(
            close_start + int(MANUAL_CLOSE_SECONDS * 1e9), session.operational_deadline_ns
        )
        try:
            wait_for_console_enter(
                console, worker.process_handle, interrupt, deadline_ns=manual_close_deadline
            )
        except IdentityCandidateError as error:
            if error.code == "ID0_STAGE_TIMEOUT":
                if time.monotonic_ns() >= session.operational_deadline_ns:
                    raise IdentityCandidateError(
                        "ID0_POST_BASELINE_OPERATIONAL_DEADLINE_EXCEEDED"
                    ) from error
                raise IdentityCandidateError("ID0_MANUAL_CLOSE_TIMEOUT") from error
            raise
        _expect_detail(
            session.transact(
                "CLOSE_DETAIL_CHECK",
                {},
                local_seconds=COMMAND_SECONDS,
                timeout_code="ID0_MANUAL_CLOSE_DETAIL_CHECK_TIMEOUT",
            ),
            "close",
        )
        close_response = session.transact(
            "CLOSE_CENSUS", {}, local_seconds=COMMAND_SECONDS, timeout_code="ID0_CENSUS_TIMEOUT"
        )
        if _fixed_code(close_response, {"code", "projection"}) != "ID0_CLOSE_CENSUS_RESULT":
            raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
        close_projection = _validated_projection(
            close_response["projection"], "close", "ID0_CLOSE_CENSUS_OK"
        )
        result_model = deserialize_final_result(
            baseline_projection, open_projection, close_projection
        )
        clear = session.transact(
            "CLEAR",
            {},
            local_seconds=COMMAND_SECONDS,
            timeout_code="ID0_PRIVATE_STATE_CLEANUP_TIMEOUT",
        )
        _expect_boolean_result(
            clear,
            success_code="ID0_PRIVATE_STATE_CLEARED",
            boolean_key="cleared",
            failure_code="ID0_PRIVATE_STATE_CLEANUP_FAILED",
        )
        clear_confirmed = True
        closed = session.transact(
            "CLOSE_CONTEXT",
            {},
            local_seconds=COMMAND_SECONDS,
            timeout_code="ID0_BROWSER_CLOSE_TIMEOUT",
        )
        _expect_boolean_result(
            closed,
            success_code="ID0_BROWSER_CONTEXT_CLOSED",
            boolean_key="closed",
            failure_code="ID0_BROWSER_CLOSE_FAILED",
        )
        context_closed = True
        shutdown = session.transact(
            "SHUTDOWN",
            {},
            local_seconds=SHUTDOWN_SECONDS,
            timeout_code="ID0_WORKER_SHUTDOWN_TIMEOUT",
        )
        _expect_boolean_result(
            shutdown,
            success_code="ID0_WORKER_SHUTDOWN_ACKNOWLEDGED",
            boolean_key="exiting",
            failure_code="ID0_WORKER_SHUTDOWN_FAILED",
        )
        shutdown_acknowledged = True
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        remaining_ns = clipped_timeout_ns(
            SHUTDOWN_SECONDS, time.monotonic_ns(), session.operational_deadline_ns
        )
        shutdown_deadline = time.monotonic_ns() + remaining_ns
        wait_result = kernel32.WaitForSingleObject(
            wintypes.HANDLE(worker.process_handle), max(0, remaining_ns // 1_000_000)
        )
        exit_code = wintypes.DWORD()
        while active_processes(job) != 0 and time.monotonic_ns() < shutdown_deadline:
            time.sleep(0.05)
        if (
            wait_result != 0
            or not kernel32.GetExitCodeProcess(
                wintypes.HANDLE(worker.process_handle), ctypes.byref(exit_code)
            )
            or exit_code.value != 0
            or active_processes(job) != 0
        ):
            hard_required = True
            raise IdentityCandidateError("ID0_WORKER_SHUTDOWN_TIMEOUT")
        if result_model is None:
            raise IdentityCandidateError("ID0_INTERNAL_ERROR")
        return result_model
    except IdentityCandidateError as error:
        primary = error
        hard_required = worker is not None
        if session is not None and worker is not None:
            if private_state_possible and not clear_confirmed:
                try:
                    cleanup = session.transact(
                        "CLEAR",
                        {},
                        local_seconds=COMMAND_SECONDS,
                        timeout_code="ID0_PRIVATE_STATE_CLEANUP_TIMEOUT",
                    )
                    _expect_boolean_result(
                        cleanup,
                        success_code="ID0_PRIVATE_STATE_CLEARED",
                        boolean_key="cleared",
                        failure_code="ID0_PRIVATE_STATE_CLEANUP_FAILED",
                    )
                    clear_confirmed = True
                except IdentityCandidateError:
                    pass
            if context_created and not context_closed:
                try:
                    cleanup = session.transact(
                        "CLOSE_CONTEXT",
                        {},
                        local_seconds=COMMAND_SECONDS,
                        timeout_code="ID0_BROWSER_CLOSE_TIMEOUT",
                    )
                    _expect_boolean_result(
                        cleanup,
                        success_code="ID0_BROWSER_CONTEXT_CLOSED",
                        boolean_key="closed",
                        failure_code="ID0_BROWSER_CLOSE_FAILED",
                    )
                    context_closed = True
                except IdentityCandidateError:
                    pass
            if not shutdown_acknowledged:
                try:
                    cleanup = session.transact(
                        "SHUTDOWN",
                        {},
                        local_seconds=SHUTDOWN_SECONDS,
                        timeout_code="ID0_WORKER_SHUTDOWN_TIMEOUT",
                    )
                    _expect_boolean_result(
                        cleanup,
                        success_code="ID0_WORKER_SHUTDOWN_ACKNOWLEDGED",
                        boolean_key="exiting",
                        failure_code="ID0_WORKER_SHUTDOWN_FAILED",
                    )
                    shutdown_acknowledged = True
                except IdentityCandidateError:
                    pass
            if shutdown_acknowledged:
                deadline = time.monotonic_ns() + int(SHUTDOWN_SECONDS * 1e9)
                while active_processes(job) != 0 and time.monotonic_ns() < deadline:
                    time.sleep(0.05)
                hard_required = active_processes(job) != 0
        raise
    except KeyboardInterrupt as error:
        primary = IdentityCandidateError("ID0_INTERRUPTED")
        hard_required = worker is not None
        raise primary from error
    except Exception as error:
        primary = IdentityCandidateError("ID0_INTERNAL_ERROR")
        hard_required = worker is not None
        raise primary from error
    finally:
        if hard_required and job:
            terminate_job(job)
            deadline = (
                session.supervisor_deadline_ns
                if session is not None and session.supervisor_deadline_ns is not None
                else time.monotonic_ns() + int(SHUTDOWN_SECONDS * 1e9)
            )
            while time.monotonic_ns() < deadline and active_processes(job) != 0:
                time.sleep(0.05)
            if active_processes(job) != 0 and primary is None:
                primary = IdentityCandidateError("ID0_PROCESS_TREE_TERMINATION_UNCONFIRMED")
        if ipc is not None:
            ipc.close_parent()
            ipc.close_children()
        close_handle(interrupt)
        close_handle(job)
        if worker is not None:
            close_handle(worker.process_handle)
        lease.close()
