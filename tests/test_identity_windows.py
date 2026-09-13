import inspect
from types import SimpleNamespace

import pytest

from termino_exporter import identity_windows
from termino_exporter.identity_candidate import IdentityCandidateError
from termino_exporter.identity_windows import encode_windows_command_line, quote_windows_argument


def test_windows_argv_encoder_covers_spaces_quotes_and_trailing_backslashes() -> None:
    assert quote_windows_argument("") == '""'
    assert quote_windows_argument("plain") == "plain"
    assert quote_windows_argument("two words") == '"two words"'
    assert quote_windows_argument('a"b') == '"a\\"b"'
    assert quote_windows_argument("C:\\Test Folder\\") == '"C:\\Test Folder\\\\"'


def test_complete_command_line_keeps_executable_as_argv_zero() -> None:
    encoded = encode_windows_command_line(
        ("C:\\Program Files\\Python\\python.exe", "-m", "termino_exporter.worker")
    )
    assert encoded.startswith('"C:\\Program Files\\Python\\python.exe" -m ')


def test_bootstrap_uses_public_explicit_encoder_and_atomic_job_attribute() -> None:
    source = inspect.getsource(identity_windows)
    assert "subprocess.list2cmdline" not in source
    assert "CreateProcessW" in source
    assert "CREATE_SUSPENDED" in source
    assert "PROC_THREAD_ATTRIBUTE_JOB_LIST" in source
    assert "ResumeThread" in source
    assert "create_unicode_buffer" in source


@pytest.mark.parametrize("original_mode", [0x20, 0x21])
def test_console_wait_restores_exact_mode_and_unregisters_handler(
    monkeypatch: pytest.MonkeyPatch, original_mode: int
) -> None:
    modes: list[int] = []
    handlers: list[bool] = []

    def get_mode(_handle: object, pointer: object) -> bool:
        pointer._obj.value = original_mode
        return True

    fake = SimpleNamespace(
        GetConsoleMode=get_mode,
        SetConsoleMode=lambda _handle, mode: modes.append(mode) or True,
        SetConsoleCtrlHandler=lambda _handler, enabled: handlers.append(bool(enabled)) or True,
    )
    monkeypatch.setattr(identity_windows, "_kernel32", lambda: fake)
    monkeypatch.setattr(
        identity_windows,
        "_wait_handles",
        lambda _handles, _timeout: identity_windows.WAIT_OBJECT_0,
    )
    with pytest.raises(IdentityCandidateError, match="^ID0_INTERRUPTED$"):
        identity_windows.wait_for_console_enter(10, 11, 12, deadline_ns=None)
    assert modes[-1] == original_mode
    assert handlers == [True, False]
    if not original_mode & identity_windows.ENABLE_PROCESSED_INPUT:
        assert modes[0] == original_mode | identity_windows.ENABLE_PROCESSED_INPUT
