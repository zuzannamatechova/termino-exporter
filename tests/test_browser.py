from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from playwright.sync_api import Error

from termino_exporter.browser import (
    BrowserError,
    ProfilePathError,
    default_profile_dir,
    persistent_browser_context,
    safe_profile_dir,
)


def test_default_profile_dir_uses_local_app_data() -> None:
    profile = default_profile_dir(
        {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"},
        home=Path(r"C:\Users\Ignored"),
    )

    assert profile == Path(r"C:\Users\Test\AppData\Local") / "TerminoExporter" / ("browser-profile")


def test_default_profile_dir_falls_back_to_home() -> None:
    profile = default_profile_dir({}, home=Path("/invented/home"))

    assert profile == Path("/invented/home/.termino-exporter/browser-profile")


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    return project


def test_profile_at_project_root_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    with pytest.raises(ProfilePathError, match="nesmí být uvnitř projektu"):
        safe_profile_dir(project, working_directory=project)


def test_profile_below_project_root_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)

    with pytest.raises(ProfilePathError, match="nesmí být uvnitř projektu"):
        safe_profile_dir(project / "private-profile", working_directory=project)


def test_profile_outside_project_is_allowed(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    external_profile = tmp_path / "private-profile"

    result = safe_profile_dir(external_profile, working_directory=project)

    assert result == external_profile.resolve()


def test_relative_profile_is_resolved_before_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = make_project(tmp_path)
    monkeypatch.chdir(project)

    result = safe_profile_dir(Path("../private-profile"), working_directory=project)

    assert result == (tmp_path / "private-profile").resolve()


def test_working_directory_is_protected_when_repository_root_is_unknown(
    tmp_path: Path,
) -> None:
    working_directory = tmp_path / "standalone"
    working_directory.mkdir()

    with (
        patch("termino_exporter.browser._find_repository_root", return_value=None),
        pytest.raises(ProfilePathError, match="nesmí být uvnitř projektu"),
    ):
        safe_profile_dir(
            working_directory / "private-profile",
            working_directory=working_directory,
        )


def playwright_mocks() -> tuple[MagicMock, MagicMock, MagicMock]:
    context = MagicMock()
    playwright = MagicMock()
    playwright.chromium.launch_persistent_context.return_value = context
    manager = MagicMock()
    manager.__enter__.return_value = playwright
    return context, playwright, manager


def test_persistent_context_closes_after_normal_completion(tmp_path: Path) -> None:
    context, _, manager = playwright_mocks()

    with (
        patch("termino_exporter.browser.sync_playwright", return_value=manager),
        persistent_browser_context(tmp_path / "profile", 15) as opened_context,
    ):
        assert opened_context is context

    context.close.assert_called_once_with()
    manager.__exit__.assert_called_once()


def test_persistent_context_closes_when_body_fails(tmp_path: Path) -> None:
    context, _, manager = playwright_mocks()

    with (
        patch("termino_exporter.browser.sync_playwright", return_value=manager),
        pytest.raises(RuntimeError, match="záměrná testovací chyba"),
        persistent_browser_context(tmp_path / "profile", 15),
    ):
        raise RuntimeError("záměrná testovací chyba")

    context.close.assert_called_once_with()
    manager.__exit__.assert_called_once()


def test_persistent_context_closes_and_preserves_keyboard_interrupt(tmp_path: Path) -> None:
    context, _, manager = playwright_mocks()

    with (
        patch("termino_exporter.browser.sync_playwright", return_value=manager),
        pytest.raises(KeyboardInterrupt),
        persistent_browser_context(tmp_path / "profile", 15),
    ):
        raise KeyboardInterrupt

    context.close.assert_called_once_with()
    manager.__exit__.assert_called_once()


def test_close_failure_does_not_hide_keyboard_interrupt(tmp_path: Path) -> None:
    context, _, manager = playwright_mocks()
    context.close.side_effect = Error("chyba při zavírání")

    with (
        patch("termino_exporter.browser.sync_playwright", return_value=manager),
        pytest.raises(KeyboardInterrupt),
        persistent_browser_context(tmp_path / "profile", 15),
    ):
        raise KeyboardInterrupt

    context.close.assert_called_once_with()
    manager.__exit__.assert_called_once()


def test_persistent_context_closes_when_timeout_setup_fails(tmp_path: Path) -> None:
    context, _, manager = playwright_mocks()
    context.set_default_timeout.side_effect = Error("citlivý interní detail")

    with (
        patch("termino_exporter.browser.sync_playwright", return_value=manager),
        pytest.raises(BrowserError) as captured_error,
        persistent_browser_context(tmp_path / "profile", 15),
    ):
        pytest.fail("context manager neměl předat řízení")

    assert "citlivý interní detail" not in str(captured_error.value)
    context.close.assert_called_once_with()
    manager.__exit__.assert_called_once()


def test_playwright_stops_without_closing_missing_context_when_launch_fails(
    tmp_path: Path,
) -> None:
    context, playwright, manager = playwright_mocks()
    playwright.chromium.launch_persistent_context.side_effect = Error("interní detail")

    with (
        patch("termino_exporter.browser.sync_playwright", return_value=manager),
        pytest.raises(BrowserError) as captured_error,
        persistent_browser_context(tmp_path / "profile", 15),
    ):
        pytest.fail("context manager neměl předat řízení")

    assert "interní detail" not in str(captured_error.value)
    context.close.assert_not_called()
    manager.__exit__.assert_called_once()
