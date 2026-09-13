from unittest.mock import MagicMock

import pytest

from termino_exporter import cli


def test_missing_dummy_ack_fails_before_supervisor(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    supervisor = MagicMock()
    monkeypatch.setattr(cli, "run_identity_supervisor", supervisor)
    assert cli.main([cli.ID0_COMMAND]) == 1
    assert capsys.readouterr().err == "Chyba: ID0_DUMMY_ONLY_ACK_REQUIRED\n"
    supervisor.assert_not_called()


def test_invalid_id0_arguments_have_only_fixed_sanitized_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert cli.main([cli.ID0_COMMAND, "--timeout-seconds", "301", "private-value"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "Chyba: ID0_INVALID_ARGUMENTS\n"
    assert "private-value" not in captured.err


def test_id0_help_is_fixed_bounded_and_does_not_start_worker(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    supervisor = MagicMock()
    monkeypatch.setattr(cli, "run_identity_supervisor", supervisor)
    assert cli.main([cli.ID0_COMMAND, "--help"]) == 0
    output = capsys.readouterr().out
    assert "--dummy-only" in output
    assert len(output.encode("utf-8")) <= 32_768
    supervisor.assert_not_called()
