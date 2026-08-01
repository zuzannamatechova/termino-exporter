import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

from termino_exporter import cli
from termino_exporter.cli import DEFAULT_URL, create_parser, main
from termino_exporter.close_diagnosis import CloseDiagnosisError
from termino_exporter.diagnosis import DiagnosisError


def test_main_without_arguments_displays_czech_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "bezpečné čtení rezervací" in output
    assert "inspect-one" in output
    assert "volby:" in output


@pytest.mark.parametrize("arguments", [[], ["--help"]])
def test_module_help_exits_successfully(arguments: list[str]) -> None:
    environment = os.environ.copy()
    environment["PYTHONIOENCODING"] = "cp1252"
    result = subprocess.run(
        [sys.executable, "-m", "termino_exporter", *arguments],
        check=False,
        capture_output=True,
        env=environment,
        encoding="utf-8",
        text=True,
    )

    assert result.returncode == 0
    assert "bezpečné čtení rezervací" in result.stdout


def test_module_version_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "termino_exporter", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_inspect_one_help_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "termino_exporter", "inspect-one", "--help"],
        check=False,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )

    assert result.returncode == 0
    assert "--reservation-text" not in result.stdout
    assert "--profile-dir" in result.stdout
    assert "--diagnose-dialog" in result.stdout
    assert "--diagnose-close" in result.stdout
    assert "pouze pro čtení" in result.stdout


def test_inspect_one_arguments_are_parsed() -> None:
    args = create_parser().parse_args(
        [
            "inspect-one",
            "--url",
            "https://example.invalid/calendar",
            "--profile-dir",
            "invented-profile",
            "--timeout-seconds",
            "12.5",
            "--diagnose-dialog",
        ]
    )

    assert args.command == "inspect-one"
    assert args.url == "https://example.invalid/calendar"
    assert args.profile_dir == Path("invented-profile")
    assert args.timeout_seconds == 12.5
    assert args.diagnose_dialog is True
    assert args.diagnose_close is False


def test_inspect_one_defaults_are_parsed() -> None:
    args = create_parser().parse_args(["inspect-one"])

    assert args.url == DEFAULT_URL
    assert args.profile_dir is None
    assert args.timeout_seconds == 30.0
    assert args.diagnose_dialog is False
    assert args.diagnose_close is False


def test_close_diagnostic_argument_is_parsed() -> None:
    args = create_parser().parse_args(["inspect-one", "--diagnose-close"])

    assert args.diagnose_close is True
    assert args.diagnose_dialog is False


def test_diagnostic_modes_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit) as caught:
        create_parser().parse_args(["inspect-one", "--diagnose-dialog", "--diagnose-close"])

    assert caught.value.code == 2


def test_diagnostic_playwright_error_is_sanitized_in_cli(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    error = DiagnosisError("Diagnostiku se nepodařilo bezpečně dokončit.")
    error.__cause__ = Error("locator obsahující Jana Nováková")
    monkeypatch.setattr(cli, "default_profile_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(cli, "safe_profile_dir", lambda path: path)
    inspect = MagicMock(side_effect=error)
    monkeypatch.setattr(cli, "inspect_one_reservation", inspect)

    assert main(["inspect-one", "--diagnose-dialog"]) == 1

    stderr = capsys.readouterr().err
    assert "Diagnostiku se nepodařilo bezpečně dokončit." in stderr
    assert "Jana Nováková" not in stderr
    assert "locator" not in stderr


def test_close_diagnostic_prints_only_safe_error_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    error = CloseDiagnosisError("CLOSE_DIAG_PLAYWRIGHT_ERROR")
    error.__cause__ = Error("DOM obsahuje Jana Nováková")
    monkeypatch.setattr(cli, "default_profile_dir", lambda: tmp_path / "profile")
    monkeypatch.setattr(cli, "safe_profile_dir", lambda path: path)
    monkeypatch.setattr(cli, "inspect_one_reservation", MagicMock(side_effect=error))

    assert main(["inspect-one", "--diagnose-close"]) == 1

    stderr = capsys.readouterr().err
    assert "Chyba: CLOSE_DIAG_PLAYWRIGHT_ERROR" in stderr
    assert "Jana Nováková" not in stderr
    assert "DOM" not in stderr
