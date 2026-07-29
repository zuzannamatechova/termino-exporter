import os
import subprocess
import sys

import pytest

from termino_exporter.cli import main


def test_main_without_arguments_displays_czech_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "Automatizace prohlížeče zatím není implementována" in output
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
    assert "Automatizace prohlížeče zatím není implementována" in result.stdout


def test_module_version_exits_successfully() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "termino_exporter", "--version"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "0.1.0" in result.stdout
