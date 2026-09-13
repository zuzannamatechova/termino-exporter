"""Narrow Win32 primitives used only by the isolated Phase 4C-ID0 supervisor."""

from __future__ import annotations

import ctypes
import hashlib
import os
import secrets
import struct
import sys
import threading
import time
from collections.abc import Sequence
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from termino_exporter.identity_candidate import IdentityCandidateError

CREATE_SUSPENDED: Final = 0x00000004
EXTENDED_STARTUPINFO_PRESENT: Final = 0x00080000
CREATE_NO_WINDOW: Final = 0x08000000
STARTF_USESTDHANDLES: Final = 0x00000100
PROC_THREAD_ATTRIBUTE_HANDLE_LIST: Final = 0x00020002
PROC_THREAD_ATTRIBUTE_JOB_LIST: Final = 0x0002000D
HANDLE_FLAG_INHERIT: Final = 0x00000001
ENABLE_PROCESSED_INPUT: Final = 0x0001
FILE_TYPE_CHAR: Final = 0x0002
STD_INPUT_HANDLE: Final = -10
WAIT_OBJECT_0: Final = 0
WAIT_ABANDONED: Final = 0x00000080
WAIT_TIMEOUT: Final = 0x00000102
INFINITE: Final = 0xFFFFFFFF
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: Final = 0x00002000
JobObjectExtendedLimitInformation: Final = 9
JobObjectBasicAccountingInformation: Final = 1
ERROR_IO_PENDING: Final = 997
ERROR_PIPE_CONNECTED: Final = 535
PIPE_ACCESS_INBOUND: Final = 0x00000001
PIPE_ACCESS_OUTBOUND: Final = 0x00000002
FILE_FLAG_OVERLAPPED: Final = 0x40000000
PIPE_TYPE_BYTE: Final = 0
PIPE_READMODE_BYTE: Final = 0
PIPE_WAIT: Final = 0
PIPE_REJECT_REMOTE_CLIENTS: Final = 0x00000008
OPEN_EXISTING: Final = 3
GENERIC_READ: Final = 0x80000000
GENERIC_WRITE: Final = 0x40000000
FILE_SHARE_READ: Final = 1
FILE_SHARE_WRITE: Final = 2
KEY_EVENT: Final = 0x0001
CTRL_C_EVENT: Final = 0
CTRL_BREAK_EVENT: Final = 1

_launch_lock = threading.Lock()
_kernel32_instance: ctypes.WinDLL | None = None


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


class SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", ctypes.c_void_p),
        ("bInheritHandle", wintypes.BOOL),
    ]


class OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


class CHAR_UNION(ctypes.Union):
    _fields_ = [("UnicodeChar", wintypes.WCHAR), ("AsciiChar", wintypes.CHAR)]


class KEY_EVENT_RECORD(ctypes.Structure):
    _fields_ = [
        ("bKeyDown", wintypes.BOOL),
        ("wRepeatCount", wintypes.WORD),
        ("wVirtualKeyCode", wintypes.WORD),
        ("wVirtualScanCode", wintypes.WORD),
        ("uChar", CHAR_UNION),
        ("dwControlKeyState", wintypes.DWORD),
    ]


class EVENT_UNION(ctypes.Union):
    _fields_ = [("KeyEvent", KEY_EVENT_RECORD), ("Padding", ctypes.c_byte * 16)]


class INPUT_RECORD(ctypes.Structure):
    _fields_ = [("EventType", wintypes.WORD), ("Event", EVENT_UNION)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        (name, ctypes.c_ulonglong)
        for name in (
            "ReadOperationCount",
            "WriteOperationCount",
            "OtherOperationCount",
            "ReadTransferCount",
            "WriteTransferCount",
            "OtherTransferCount",
        )
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", wintypes.DWORD),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", wintypes.DWORD),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", wintypes.DWORD),
        ("SchedulingClass", wintypes.DWORD),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_ACCOUNTING_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("TotalUserTime", ctypes.c_longlong),
        ("TotalKernelTime", ctypes.c_longlong),
        ("ThisPeriodTotalUserTime", ctypes.c_longlong),
        ("ThisPeriodTotalKernelTime", ctypes.c_longlong),
        ("TotalPageFaultCount", wintypes.DWORD),
        ("TotalProcesses", wintypes.DWORD),
        ("ActiveProcesses", wintypes.DWORD),
        ("TotalTerminatedProcesses", wintypes.DWORD),
    ]


@dataclass(frozen=True, slots=True)
class SpawnedWorker:
    process_handle: int
    process_id: int


@dataclass(slots=True)
class IpcHandles:
    control_write: int
    result_read: int
    control_read_child: int
    result_write_child: int
    null_read_child: int
    null_write_child: int

    def close_parent(self) -> None:
        close_handle(self.control_write)
        close_handle(self.result_read)
        self.control_write = 0
        self.result_read = 0

    def close_children(self) -> None:
        for name in (
            "control_read_child",
            "result_write_child",
            "null_read_child",
            "null_write_child",
        ):
            close_handle(getattr(self, name))
            setattr(self, name, 0)


def quote_windows_argument(argument: str) -> str:
    """Encode one argv item according to the MS CRT CommandLineToArgv contract."""
    if not isinstance(argument, str) or "\0" in argument:
        raise IdentityCandidateError("ID0_INVALID_ARGUMENTS")
    if argument and not any(character in argument for character in ' \t"'):
        return argument
    result = ['"']
    backslashes = 0
    for character in argument:
        if character == "\\":
            backslashes += 1
        elif character == '"':
            result.append("\\" * (backslashes * 2 + 1))
            result.append('"')
            backslashes = 0
        else:
            result.append("\\" * backslashes)
            result.append(character)
            backslashes = 0
    result.append("\\" * (backslashes * 2))
    result.append('"')
    return "".join(result)


def encode_windows_command_line(argv: Sequence[str]) -> str:
    """Encode a non-empty complete argv without relying on a private stdlib API."""
    if not argv:
        raise IdentityCandidateError("ID0_INVALID_ARGUMENTS")
    return " ".join(quote_windows_argument(argument) for argument in argv)


def worker_argv(control_handle: int, result_handle: int) -> tuple[str, ...]:
    executable = str(Path(sys.executable).resolve())
    return (
        executable,
        "-m",
        "termino_exporter.identity_candidate_worker",
        "--control-handle",
        str(control_handle),
        "--result-handle",
        str(result_handle),
    )


def _kernel32() -> ctypes.WinDLL:
    global _kernel32_instance
    if os.name != "nt":
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    if _kernel32_instance is None:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        for name in (
            "CreateJobObjectW",
            "CreateMutexW",
            "CreateEventW",
            "CreateNamedPipeW",
            "CreateFileW",
            "GetStdHandle",
        ):
            getattr(kernel32, name).restype = wintypes.HANDLE
        kernel32.CreateProcessW.restype = wintypes.BOOL
        _kernel32_instance = kernel32
    return _kernel32_instance


def close_handle(handle: int | None) -> None:
    if handle:
        _kernel32().CloseHandle(wintypes.HANDLE(handle))


def set_inheritable(handle: int, inheritable: bool) -> None:
    kernel32 = _kernel32()
    flags = HANDLE_FLAG_INHERIT if inheritable else 0
    if not kernel32.SetHandleInformation(wintypes.HANDLE(handle), HANDLE_FLAG_INHERIT, flags):
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")


def create_kill_on_close_job() -> int:
    kernel32 = _kernel32()
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    set_inheritable(int(handle), False)
    limits = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    limits.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not kernel32.SetInformationJobObject(
        wintypes.HANDLE(handle),
        JobObjectExtendedLimitInformation,
        ctypes.byref(limits),
        ctypes.sizeof(limits),
    ):
        close_handle(int(handle))
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    return int(handle)


def active_processes(job_handle: int) -> int | None:
    info = JOBOBJECT_BASIC_ACCOUNTING_INFORMATION()
    returned = wintypes.DWORD()
    ok = _kernel32().QueryInformationJobObject(
        wintypes.HANDLE(job_handle),
        JobObjectBasicAccountingInformation,
        ctypes.byref(info),
        ctypes.sizeof(info),
        ctypes.byref(returned),
    )
    return int(info.ActiveProcesses) if ok else None


def terminate_job(job_handle: int) -> bool:
    return bool(_kernel32().TerminateJobObject(wintypes.HANDLE(job_handle), 1))


def atomic_spawn_worker(
    *,
    child_handles: tuple[int, int, int, int],
    job_handle: int,
) -> SpawnedWorker:
    """Create the Python worker suspended and atomically assigned to the Job Object."""
    if len(set(child_handles)) != 4 or job_handle in child_handles:
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    kernel32 = _kernel32()
    size = ctypes.c_size_t()
    kernel32.InitializeProcThreadAttributeList(None, 2, 0, ctypes.byref(size))
    attribute_buffer = ctypes.create_string_buffer(size.value)
    attribute_list = ctypes.cast(attribute_buffer, ctypes.c_void_p)
    if not kernel32.InitializeProcThreadAttributeList(attribute_list, 2, 0, ctypes.byref(size)):
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    handle_array = (wintypes.HANDLE * 4)(*(wintypes.HANDLE(value) for value in child_handles))
    job_array = (wintypes.HANDLE * 1)(wintypes.HANDLE(job_handle))
    process = PROCESS_INFORMATION()
    startup = STARTUPINFOEXW()
    startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
    startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
    startup.StartupInfo.hStdInput = wintypes.HANDLE(child_handles[2])
    startup.StartupInfo.hStdOutput = wintypes.HANDLE(child_handles[3])
    startup.StartupInfo.hStdError = wintypes.HANDLE(child_handles[3])
    created = False
    inheritance_restore_failed = False
    try:
        if not kernel32.UpdateProcThreadAttribute(
            attribute_list,
            0,
            PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
            ctypes.byref(handle_array),
            ctypes.sizeof(handle_array),
            None,
            None,
        ) or not kernel32.UpdateProcThreadAttribute(
            attribute_list,
            0,
            PROC_THREAD_ATTRIBUTE_JOB_LIST,
            ctypes.byref(job_array),
            ctypes.sizeof(job_array),
            None,
            None,
        ):
            raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
        startup.lpAttributeList = attribute_list
        argv = worker_argv(child_handles[0], child_handles[1])
        command_buffer = ctypes.create_unicode_buffer(encode_windows_command_line(argv))
        with _launch_lock:
            try:
                for handle in child_handles:
                    set_inheritable(handle, True)
                created = bool(
                    kernel32.CreateProcessW(
                        ctypes.c_wchar_p(argv[0]),
                        command_buffer,
                        None,
                        None,
                        True,
                        EXTENDED_STARTUPINFO_PRESENT | CREATE_NO_WINDOW | CREATE_SUSPENDED,
                        None,
                        None,
                        ctypes.byref(startup),
                        ctypes.byref(process),
                    )
                )
            finally:
                for handle in child_handles:
                    try:
                        set_inheritable(handle, False)
                    except IdentityCandidateError:
                        inheritance_restore_failed = True
        if not created or inheritance_restore_failed:
            raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
        in_job = wintypes.BOOL()
        if (
            not kernel32.IsProcessInJob(
                process.hProcess, wintypes.HANDLE(job_handle), ctypes.byref(in_job)
            )
            or not in_job.value
        ):
            raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
        resumed = kernel32.ResumeThread(process.hThread)
        if resumed != 1:
            raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
        close_handle(int(process.hThread))
        process.hThread = None
        return SpawnedWorker(int(process.hProcess), int(process.dwProcessId))
    except IdentityCandidateError:
        if created:
            terminate_job(job_handle)
            deadline = time.monotonic_ns() + 2_000_000_000
            while active_processes(job_handle) != 0 and time.monotonic_ns() < deadline:
                time.sleep(0.05)
        close_handle(int(process.hThread) if process.hThread else None)
        close_handle(int(process.hProcess) if process.hProcess else None)
        raise
    finally:
        kernel32.DeleteProcThreadAttributeList(attribute_list)


def profile_mutex_name(profile_dir: Path) -> str:
    canonical = os.path.normcase(str(profile_dir.resolve())).encode("utf-8")
    return "Local\\TerminoExporter-ID0-" + hashlib.sha256(canonical).hexdigest()


@dataclass(slots=True)
class ProfileLease:
    handle: int

    @classmethod
    def acquire(cls, profile_dir: Path) -> ProfileLease:
        kernel32 = _kernel32()
        handle = kernel32.CreateMutexW(None, False, profile_mutex_name(profile_dir))
        if not handle:
            raise IdentityCandidateError("ID0_PROFILE_IN_USE_OR_UNAVAILABLE")
        result = kernel32.WaitForSingleObject(wintypes.HANDLE(handle), 0)
        if result == WAIT_TIMEOUT:
            close_handle(int(handle))
            raise IdentityCandidateError("ID0_PROFILE_IN_USE")
        if result not in {WAIT_OBJECT_0, WAIT_ABANDONED}:
            close_handle(int(handle))
            raise IdentityCandidateError("ID0_PROFILE_IN_USE_OR_UNAVAILABLE")
        return cls(int(handle))

    def close(self) -> None:
        if self.handle:
            kernel32 = _kernel32()
            kernel32.ReleaseMutex(wintypes.HANDLE(self.handle))
            close_handle(self.handle)
            self.handle = 0


def console_preflight() -> int:
    """Return the verified console-input handle before any worker can exist."""
    kernel32 = _kernel32()
    handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
    if not handle or int(handle) == -1 or kernel32.GetFileType(handle) != FILE_TYPE_CHAR:
        raise IdentityCandidateError("ID0_INTERACTIVE_STDIN_REQUIRED")
    mode = wintypes.DWORD()
    if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        raise IdentityCandidateError("ID0_CONSOLE_MODE_QUERY_FAILED")
    return int(handle)


def _security_attributes() -> tuple[SECURITY_ATTRIBUTES, int]:
    """Create an owner-only DACL; caller releases the descriptor with LocalFree."""
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    descriptor = ctypes.c_void_p()
    if not advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        "D:P(A;;GA;;;OW)", 1, ctypes.byref(descriptor), None
    ):
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    attributes = SECURITY_ATTRIBUTES(ctypes.sizeof(SECURITY_ATTRIBUTES), descriptor, False)
    if descriptor.value is None:
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    return attributes, int(descriptor.value)


def _named_pipe_pair(*, parent_writes: bool) -> tuple[int, int]:
    kernel32 = _kernel32()
    attributes, descriptor = _security_attributes()
    name = rf"\\.\pipe\TerminoExporter-ID0-{secrets.token_hex(24)}"
    access = PIPE_ACCESS_OUTBOUND if parent_writes else PIPE_ACCESS_INBOUND
    server = kernel32.CreateNamedPipeW(
        name,
        access | FILE_FLAG_OVERLAPPED,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT | PIPE_REJECT_REMOTE_CLIENTS,
        1,
        32_772,
        32_772,
        0,
        ctypes.byref(attributes),
    )
    ctypes.windll.kernel32.LocalFree(ctypes.c_void_p(descriptor))
    if not server or int(server) == -1:
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    desired = GENERIC_READ if parent_writes else GENERIC_WRITE
    child = kernel32.CreateFileW(name, desired, 0, None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
    if not child or int(child) == -1:
        close_handle(int(server))
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    connected = kernel32.ConnectNamedPipe(wintypes.HANDLE(server), None)
    if not connected and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
        close_handle(int(child))
        close_handle(int(server))
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    set_inheritable(int(server), False)
    set_inheritable(int(child), False)
    return int(server), int(child)


def create_ipc_handles() -> IpcHandles:
    """Create two local byte-mode named pipes plus isolated NUL standard handles."""
    kernel32 = _kernel32()
    control_write = result_read = control_child = result_child = 0
    null_read = null_write = 0
    try:
        control_write, control_child = _named_pipe_pair(parent_writes=True)
        result_read, result_child = _named_pipe_pair(parent_writes=False)
        null_read = int(
            kernel32.CreateFileW(
                "NUL",
                GENERIC_READ,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
        )
        null_write = int(
            kernel32.CreateFileW(
                "NUL",
                GENERIC_WRITE,
                FILE_SHARE_READ | FILE_SHARE_WRITE,
                None,
                OPEN_EXISTING,
                0,
                None,
            )
        )
        if not null_read or null_read == -1 or not null_write or null_write == -1:
            raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
        for handle in (null_read, null_write):
            set_inheritable(handle, False)
        return IpcHandles(
            control_write, result_read, control_child, result_child, null_read, null_write
        )
    except IdentityCandidateError:
        for handle in (
            control_write,
            result_read,
            control_child,
            result_child,
            null_read,
            null_write,
        ):
            close_handle(handle)
        raise


def create_event(*, manual_reset: bool = True) -> int:
    handle = _kernel32().CreateEventW(None, manual_reset, False, None)
    if not handle:
        raise IdentityCandidateError("ID0_SUPERVISOR_SETUP_FAILED")
    set_inheritable(int(handle), False)
    return int(handle)


def _wait_handles(handles: Sequence[int], timeout_ms: int) -> int:
    array = (wintypes.HANDLE * len(handles))(*(wintypes.HANDLE(value) for value in handles))
    result = _kernel32().WaitForMultipleObjects(len(handles), array, False, timeout_ms)
    return int(result)


def _overlapped_chunk(
    handle: int,
    buffer: ctypes.Array[ctypes.c_char],
    size: int,
    *,
    write: bool,
    process_handle: int,
    interrupt_event: int,
    deadline_ns: int,
) -> int:
    kernel32 = _kernel32()
    event = create_event(manual_reset=True)
    overlapped = OVERLAPPED()
    overlapped.hEvent = wintypes.HANDLE(event)
    transferred = wintypes.DWORD()
    try:
        operation = kernel32.WriteFile if write else kernel32.ReadFile
        ok = operation(
            wintypes.HANDLE(handle),
            buffer,
            size,
            ctypes.byref(transferred),
            ctypes.byref(overlapped),
        )
        if ok:
            return int(transferred.value)
        if ctypes.get_last_error() != ERROR_IO_PENDING:
            raise IdentityCandidateError("ID0_IPC_CHANNEL_BROKEN")
        while True:
            remaining = max(0, deadline_ns - time.monotonic_ns())
            timeout_ms = min(50, (remaining + 999_999) // 1_000_000)
            result = _wait_handles((event, interrupt_event, process_handle), int(timeout_ms))
            if result == WAIT_OBJECT_0 + 1:
                raise IdentityCandidateError("ID0_INTERRUPTED")
            if time.monotonic_ns() >= deadline_ns:
                kernel32.CancelIoEx(wintypes.HANDLE(handle), ctypes.byref(overlapped))
                raise IdentityCandidateError(
                    "ID0_IPC_WRITE_TIMEOUT" if write else "ID0_STAGE_TIMEOUT"
                )
            if result == WAIT_OBJECT_0:
                if not kernel32.GetOverlappedResult(
                    wintypes.HANDLE(handle),
                    ctypes.byref(overlapped),
                    ctypes.byref(transferred),
                    False,
                ):
                    raise IdentityCandidateError("ID0_IPC_CHANNEL_BROKEN")
                return int(transferred.value)
            if result == WAIT_OBJECT_0 + 2:
                raise IdentityCandidateError("ID0_WORKER_EXITED_WITHOUT_RESPONSE")
            if result != WAIT_TIMEOUT:
                raise IdentityCandidateError("ID0_IPC_CHANNEL_BROKEN")
    finally:
        close_handle(event)


def write_frame(
    handle: int, frame: bytes, *, process_handle: int, interrupt_event: int, deadline_ns: int
) -> None:
    offset = 0
    while offset < len(frame):
        chunk = frame[offset : offset + 4096]
        buffer = ctypes.create_string_buffer(chunk)
        count = _overlapped_chunk(
            handle,
            buffer,
            len(chunk),
            write=True,
            process_handle=process_handle,
            interrupt_event=interrupt_event,
            deadline_ns=deadline_ns,
        )
        if count <= 0:
            raise IdentityCandidateError("ID0_IPC_CHANNEL_BROKEN")
        offset += count


def read_frame(
    handle: int, *, process_handle: int, interrupt_event: int, deadline_ns: int
) -> bytes:
    received_any = False

    def read_exact(size: int) -> bytes:
        nonlocal received_any
        result = bytearray()
        while len(result) < size:
            buffer = ctypes.create_string_buffer(min(4096, size - len(result)))
            try:
                count = _overlapped_chunk(
                    handle,
                    buffer,
                    len(buffer),
                    write=False,
                    process_handle=process_handle,
                    interrupt_event=interrupt_event,
                    deadline_ns=deadline_ns,
                )
            except IdentityCandidateError as error:
                if received_any and error.code == "ID0_WORKER_EXITED_WITHOUT_RESPONSE":
                    raise IdentityCandidateError("ID0_IPC_CHANNEL_BROKEN") from error
                if error.code == "ID0_WORKER_EXITED_WITHOUT_RESPONSE":
                    exit_status = wintypes.DWORD()
                    if _kernel32().GetExitCodeProcess(
                        wintypes.HANDLE(process_handle), ctypes.byref(exit_status)
                    ):
                        if exit_status.value == 71:
                            raise IdentityCandidateError("ID0_IPC_WRITE_TIMEOUT") from error
                        if exit_status.value == 70:
                            raise IdentityCandidateError("ID0_WORKER_BOOTSTRAP_FAILED") from error
                raise
            if count <= 0:
                raise IdentityCandidateError("ID0_IPC_CHANNEL_BROKEN")
            result.extend(buffer.raw[:count])
            received_any = True
        return bytes(result)

    prefix = read_exact(4)
    length = struct.unpack(">I", prefix)[0]
    if not 1 <= length <= 32_768:
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    return prefix + read_exact(length)


def wait_for_console_enter(
    console_handle: int,
    process_handle: int,
    interrupt_event: int,
    *,
    deadline_ns: int | None,
) -> None:
    """Wait for a key-down carriage return while preserving console state exactly."""
    kernel32 = _kernel32()
    mode = wintypes.DWORD()
    handler_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

    def on_control(control_type: int) -> bool:
        if control_type in {CTRL_C_EVENT, CTRL_BREAK_EVENT}:
            kernel32.SetEvent(wintypes.HANDLE(interrupt_event))
            return True
        return False

    handler = handler_type(on_control)
    if not kernel32.GetConsoleMode(wintypes.HANDLE(console_handle), ctypes.byref(mode)):
        raise IdentityCandidateError("ID0_CONSOLE_MODE_QUERY_FAILED")
    original = int(mode.value)
    if not original & ENABLE_PROCESSED_INPUT and not kernel32.SetConsoleMode(
        wintypes.HANDLE(console_handle), original | ENABLE_PROCESSED_INPUT
    ):
        raise IdentityCandidateError("ID0_CONSOLE_MODE_SET_FAILED")
    registered = False
    primary: IdentityCandidateError | None = None
    try:
        if not kernel32.SetConsoleCtrlHandler(handler, True):
            raise IdentityCandidateError("ID0_CONSOLE_HANDLER_REGISTRATION_FAILED")
        registered = True
        while True:
            if deadline_ns is None:
                timeout_ms = 50
            else:
                remaining = max(0, deadline_ns - time.monotonic_ns())
                timeout_ms = min(50, (remaining + 999_999) // 1_000_000)
            result = _wait_handles(
                (interrupt_event, process_handle, console_handle), int(timeout_ms)
            )
            if result == WAIT_OBJECT_0:
                raise IdentityCandidateError("ID0_INTERRUPTED")
            if deadline_ns is not None and time.monotonic_ns() >= deadline_ns:
                raise IdentityCandidateError("ID0_STAGE_TIMEOUT")
            if result == WAIT_OBJECT_0 + 1:
                raise IdentityCandidateError("ID0_WORKER_EXITED_WITHOUT_RESPONSE")
            if result == WAIT_OBJECT_0 + 2:
                records = (INPUT_RECORD * 16)()
                read = wintypes.DWORD()
                if not kernel32.ReadConsoleInputW(
                    wintypes.HANDLE(console_handle), records, 16, ctypes.byref(read)
                ):
                    raise IdentityCandidateError("ID0_MANUAL_INPUT_FAILED")
                for record in records[: read.value]:
                    if (
                        record.EventType == KEY_EVENT
                        and record.Event.KeyEvent.bKeyDown
                        and record.Event.KeyEvent.uChar.UnicodeChar == "\r"
                    ):
                        return
            elif result != WAIT_TIMEOUT:
                raise IdentityCandidateError("ID0_MANUAL_INPUT_FAILED")
    except IdentityCandidateError as error:
        primary = error
        raise
    finally:
        restore_failed = not bool(
            kernel32.SetConsoleMode(wintypes.HANDLE(console_handle), original)
        )
        cleanup_failed = registered and not bool(kernel32.SetConsoleCtrlHandler(handler, False))
        if primary is None:
            if restore_failed:
                raise IdentityCandidateError("ID0_CONSOLE_MODE_RESTORE_FAILED")
            if cleanup_failed:
                raise IdentityCandidateError("ID0_CONSOLE_HANDLER_CLEANUP_FAILED")
