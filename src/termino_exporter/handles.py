"""Small ownership helpers for Playwright handles."""

import sys
from collections.abc import Iterable

from playwright.sync_api import Error, JSHandle


def safe_dispose_handle(handle: JSHandle | None) -> None:
    """Dispose one owned handle without replacing an active application error."""
    if handle is None:
        return
    active_error = sys.exception()
    try:
        handle.dispose()
    except Error:
        pass
    except Exception as cleanup_error:
        if active_error is not None:
            raise active_error from cleanup_error
        raise


def dispose_handles(
    handles: Iterable[JSHandle | None],
    *,
    exclude: Iterable[JSHandle] = (),
    disposed_wrappers: list[JSHandle] | None = None,
) -> None:
    """Dispose each distinct owned wrapper once, optionally retaining selected wrappers."""
    excluded = tuple(exclude)
    tracked = [] if disposed_wrappers is None else disposed_wrappers
    active_error = sys.exception()
    first_cleanup_error: Exception | None = None
    for handle in handles:
        if (
            handle is None
            or any(item is handle for item in excluded)
            or any(item is handle for item in tracked)
        ):
            continue
        try:
            handle.dispose()
        except Error:
            pass
        except Exception as cleanup_error:
            if first_cleanup_error is None:
                first_cleanup_error = cleanup_error
        finally:
            tracked.append(handle)

    if first_cleanup_error is not None:
        if active_error is not None:
            raise active_error from first_cleanup_error
        raise first_cleanup_error
