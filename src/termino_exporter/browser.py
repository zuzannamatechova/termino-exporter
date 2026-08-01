"""Safe browser context setup for local Termino inspection."""

import os
import subprocess
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

from playwright.sync_api import BrowserContext, Error, sync_playwright


class BrowserError(RuntimeError):
    """Expected failure while starting or using the browser."""


class ProfilePathError(RuntimeError):
    """The persistent profile path is not safe for private browser state."""


def default_profile_dir(
    environment: Mapping[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    """Return the local persistent browser profile directory."""
    current_environment = os.environ if environment is None else environment
    local_app_data = current_environment.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "TerminoExporter" / "browser-profile"
    return (Path.home() if home is None else home) / ".termino-exporter" / "browser-profile"


def _find_repository_root(start: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            check=False,
            capture_output=True,
            encoding="utf-8",
            text=True,
        )
    except OSError:
        result = None
    if result is not None and result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()

    for directory in (start, *start.parents):
        if (directory / ".git").exists():
            return directory.resolve()
    return None


def safe_profile_dir(profile_dir: Path, working_directory: Path | None = None) -> Path:
    """Resolve a profile path and reject locations inside the current project."""
    current_directory = (
        Path.cwd().resolve() if working_directory is None else working_directory.resolve()
    )
    resolved_profile = profile_dir.expanduser().resolve()
    repository_root = _find_repository_root(current_directory)
    protected_root = repository_root if repository_root is not None else current_directory
    if resolved_profile == protected_root or protected_root in resolved_profile.parents:
        raise ProfilePathError("Adresář profilu nesmí být uvnitř projektu.")
    return resolved_profile


@contextmanager
def persistent_browser_context(
    profile_dir: Path,
    timeout_seconds: float,
) -> Iterator[BrowserContext]:
    """Launch a visible persistent Chromium context and always close it."""
    try:
        profile_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
            )
            try:
                context.set_default_timeout(timeout_seconds * 1000)
                yield context
            except BaseException:
                try:
                    context.close()
                except Error:
                    pass
                raise
            else:
                context.close()
    except (Error, OSError) as error:
        raise BrowserError("Prohlížeč se nepodařilo spustit nebo bezpečně ukončit.") from error
