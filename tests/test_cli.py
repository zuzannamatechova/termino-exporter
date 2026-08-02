import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

from termino_exporter import cli
from termino_exporter.browser import BrowserError, ProfilePathError
from termino_exporter.cli import DEFAULT_URL, create_parser, main
from termino_exporter.close_diagnosis import CloseDiagnosisError
from termino_exporter.diagnosis import DiagnosisError
from termino_exporter.inspection import InspectionError


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


def test_diagnose_calendar_help_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "termino_exporter", "diagnose-calendar", "--help"],
        check=False,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )

    assert result.returncode == 0
    assert "--profile-dir" in result.stdout
    assert "--timeout-seconds" in result.stdout
    assert "bez klikání" in result.stdout
    assert "aktuálně zobrazeného kalendáře" in result.stdout


def test_inspect_single_event_help_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "termino_exporter", "inspect-single-event", "--help"],
        check=False,
        capture_output=True,
        encoding="utf-8",
        text=True,
    )
    assert result.returncode == 0
    assert "pohledu Den" in result.stdout
    assert "--profile-dir" in result.stdout
    assert "--timeout-seconds" in result.stdout


def test_inspect_single_event_arguments_are_parsed() -> None:
    args = create_parser().parse_args(
        [
            "inspect-single-event",
            "--url",
            "https://example.invalid/calendar",
            "--profile-dir",
            "invented-profile",
            "--timeout-seconds",
            "12.5",
        ]
    )
    assert args.command == "inspect-single-event"
    assert args.url == "https://example.invalid/calendar"
    assert args.profile_dir == Path("invented-profile")
    assert args.timeout_seconds == 12.5


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "-inf"])
def test_inspect_single_event_rejects_nonpositive_timeout(value: str) -> None:
    with pytest.raises(SystemExit) as caught:
        create_parser().parse_args(["inspect-single-event", "--timeout-seconds", value])

    assert caught.value.code == 2


def test_inspect_single_event_cli_uses_safe_profile_and_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requested = tmp_path / "profile"
    safe = tmp_path / "safe-profile"
    runner = MagicMock()
    monkeypatch.setattr(cli, "safe_profile_dir", MagicMock(return_value=safe))
    monkeypatch.setattr(cli, "inspect_single_event", runner)
    assert main(["inspect-single-event", "--profile-dir", str(requested)]) == 0
    cli.safe_profile_dir.assert_called_once_with(requested)
    runner.assert_called_once_with(
        url=DEFAULT_URL,
        profile_dir=safe,
        timeout_seconds=30.0,
    )


def test_inspect_single_event_cli_sanitizes_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from termino_exporter.single_event import SingleEventError

    error = SingleEventError("SINGLE_EVENT_NOT_FOUND")
    error.__cause__ = Error("TEST OSOBA test@example.invalid")
    monkeypatch.setattr(cli, "safe_profile_dir", lambda _path: tmp_path / "safe-profile")
    monkeypatch.setattr(cli, "inspect_single_event", MagicMock(side_effect=error))
    assert main(["inspect-single-event", "--profile-dir", str(tmp_path / "profile")]) == 1
    stderr = capsys.readouterr().err
    assert "SINGLE_EVENT_NOT_FOUND" in stderr
    assert "TEST OSOBA" not in stderr
    assert "test@example.invalid" not in stderr


@pytest.mark.parametrize(
    ("error", "expected_code"),
    [
        (BrowserError("citlivá interní chyba"), "BROWSER_ERROR"),
        (ProfilePathError("citlivá absolutní cesta"), "UNSAFE_PROFILE_DIR"),
        (InspectionError("citlivý detail"), "EVENT_DETAIL_PROCESSING_FAILED"),
    ],
)
def test_inspect_single_event_cli_maps_non_phase4b_errors_to_fixed_codes(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    error: Exception,
    expected_code: str,
) -> None:
    monkeypatch.setattr(cli, "safe_profile_dir", lambda _path: tmp_path / "safe-profile")
    monkeypatch.setattr(cli, "inspect_single_event", MagicMock(side_effect=error))

    assert main(["inspect-single-event", "--profile-dir", str(tmp_path / "profile")]) == 1

    stderr = capsys.readouterr().err
    assert stderr == f"Chyba: {expected_code}\n"
    assert "citliv" not in stderr


def test_diagnose_calendar_arguments_are_parsed() -> None:
    args = create_parser().parse_args(
        [
            "diagnose-calendar",
            "--url",
            "https://example.invalid/calendar",
            "--profile-dir",
            "invented-profile",
            "--timeout-seconds",
            "12.5",
        ]
    )

    assert args.command == "diagnose-calendar"
    assert args.url == "https://example.invalid/calendar"
    assert args.profile_dir == Path("invented-profile")
    assert args.timeout_seconds == 12.5


def test_obsolete_diagnose_day_command_is_rejected() -> None:
    with pytest.raises(SystemExit) as caught:
        create_parser().parse_args(["diagnose-day"])

    assert caught.value.code == 2


def test_diagnose_calendar_cli_uses_safe_profile_and_runner(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    requested = tmp_path / "profile"
    safe = tmp_path / "safe-profile"
    runner = MagicMock()
    monkeypatch.setattr(cli, "safe_profile_dir", MagicMock(return_value=safe))
    monkeypatch.setattr(cli, "diagnose_calendar", runner)

    assert main(["diagnose-calendar", "--profile-dir", str(requested)]) == 0

    cli.safe_profile_dir.assert_called_once_with(requested)
    runner.assert_called_once_with(
        url=DEFAULT_URL,
        profile_dir=safe,
        timeout_seconds=30.0,
    )


def test_diagnose_calendar_cli_prints_only_safe_error_code(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    from termino_exporter.calendar_diagnosis import CalendarDiagnosisError

    error = CalendarDiagnosisError("CALENDAR_DIAG_FAILED")
    error.__cause__ = Error("TEST OSOBA v DOM")
    monkeypatch.setattr(cli, "safe_profile_dir", lambda _path: tmp_path / "safe-profile")
    monkeypatch.setattr(cli, "diagnose_calendar", MagicMock(side_effect=error))

    assert main(["diagnose-calendar", "--profile-dir", str(tmp_path / "profile")]) == 1

    stderr = capsys.readouterr().err
    assert "CALENDAR_DIAG_FAILED" in stderr
    assert "TEST OSOBA" not in stderr
    assert "DOM" not in stderr


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
