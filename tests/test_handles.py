from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

from termino_exporter.extraction import DetailStructure
from termino_exporter.handles import dispose_handles, safe_dispose_handle


def _structure() -> tuple[DetailStructure, list[MagicMock]]:
    handles = [MagicMock(name=f"handle-{index}") for index in range(6)]
    structure = DetailStructure(
        root=handles[0],
        header_branch=handles[1],
        content_branch=handles[2],
        scroll_container=handles[3],
        action_branch=handles[4],
        close_control=handles[5],
        _owned_handles=tuple(handles),
    )
    return structure, handles


def test_detail_structure_dispose_releases_every_owned_wrapper_once() -> None:
    structure, handles = _structure()

    structure.dispose()
    structure.dispose()

    for handle in handles:
        handle.dispose.assert_called_once_with()


def test_detail_structure_can_transfer_one_handle_to_caller() -> None:
    structure, handles = _structure()
    transferred = structure.close_control

    structure.release_handle(transferred)
    structure.dispose()

    transferred.dispose.assert_not_called()
    for handle in handles[:-1]:
        handle.dispose.assert_called_once_with()


def test_detail_structure_disposes_aliased_wrapper_only_once() -> None:
    shared = MagicMock()
    structure = DetailStructure(
        root=shared,
        header_branch=shared,
        content_branch=shared,
        scroll_container=shared,
        action_branch=shared,
        close_control=shared,
        _owned_handles=(shared, shared),
    )

    structure.dispose()

    shared.dispose.assert_called_once_with()


def test_playwright_dispose_error_is_suppressed_but_programmer_error_is_not() -> None:
    playwright_failure = MagicMock()
    playwright_failure.dispose.side_effect = Error("TEST DOM")
    programmer_failure = MagicMock()
    programmer_failure.dispose.side_effect = RuntimeError("programming error")

    safe_dispose_handle(playwright_failure)
    with pytest.raises(RuntimeError, match="programming error"):
        safe_dispose_handle(programmer_failure)


def test_playwright_dispose_error_does_not_prevent_remaining_cleanup() -> None:
    playwright_failure = MagicMock()
    playwright_failure.dispose.side_effect = Error("TEST DOM")
    remaining = MagicMock()

    dispose_handles((playwright_failure, remaining))

    playwright_failure.dispose.assert_called_once_with()
    remaining.dispose.assert_called_once_with()


def test_detail_structure_playwright_dispose_error_still_releases_all_wrappers() -> None:
    structure, handles = _structure()
    handles[0].dispose.side_effect = Error("TEST DOM")

    structure.dispose()

    for handle in handles:
        handle.dispose.assert_called_once_with()


def test_detail_structure_programmer_dispose_error_is_visible_after_full_cleanup() -> None:
    structure, handles = _structure()
    handles[0].dispose.side_effect = RuntimeError("programming error")

    with pytest.raises(RuntimeError, match="programming error"):
        structure.dispose()

    for handle in handles:
        handle.dispose.assert_called_once_with()
    structure.dispose()
    for handle in handles:
        handle.dispose.assert_called_once_with()


def test_dispose_handles_deduplicates_same_wrapper() -> None:
    handle = MagicMock()

    dispose_handles((handle, handle, handle))

    handle.dispose.assert_called_once_with()


def test_dispose_helpers_accept_none_and_consume_generator_once() -> None:
    handles = [MagicMock(), MagicMock()]
    iterations = 0

    def generated_handles():
        nonlocal iterations
        iterations += 1
        yield None
        yield from handles

    safe_dispose_handle(None)
    dispose_handles(generated_handles())

    assert iterations == 1
    for handle in handles:
        handle.dispose.assert_called_once_with()


def test_distinct_wrappers_are_each_disposed_even_for_same_conceptual_node() -> None:
    first_wrapper = MagicMock(node="same-node")
    second_wrapper = MagicMock(node="same-node")

    dispose_handles((first_wrapper, second_wrapper))

    first_wrapper.dispose.assert_called_once_with()
    second_wrapper.dispose.assert_called_once_with()


def test_dispose_handles_attempts_all_wrappers_before_raising_programmer_error() -> None:
    failing = MagicMock()
    failing.dispose.side_effect = RuntimeError("programming error")
    remaining = MagicMock()

    with pytest.raises(RuntimeError, match="programming error"):
        dispose_handles((failing, remaining))

    failing.dispose.assert_called_once_with()
    remaining.dispose.assert_called_once_with()


def test_cleanup_programmer_error_does_not_replace_active_application_error() -> None:
    failing = MagicMock()
    cleanup_error = RuntimeError("cleanup programming error")
    failing.dispose.side_effect = cleanup_error
    remaining = MagicMock()

    with pytest.raises(ValueError, match="application error") as caught:
        try:
            raise ValueError("application error")
        finally:
            dispose_handles((failing, remaining))

    assert caught.value.__cause__ is cleanup_error
    remaining.dispose.assert_called_once_with()


def test_single_handle_cleanup_preserves_active_application_error() -> None:
    failing = MagicMock()
    cleanup_error = RuntimeError("cleanup programming error")
    failing.dispose.side_effect = cleanup_error

    with pytest.raises(ValueError, match="application error") as caught:
        try:
            raise ValueError("application error")
        finally:
            safe_dispose_handle(failing)

    assert caught.value.__cause__ is cleanup_error


def test_claimed_handle_is_owned_once_and_cannot_be_claimed_after_dispose() -> None:
    structure, _handles = _structure()
    claimed = MagicMock()

    structure.claim_handle(claimed)
    structure.claim_handle(claimed)
    structure.dispose()

    claimed.dispose.assert_called_once_with()
    with pytest.raises(RuntimeError, match="uvolněné struktury"):
        structure.claim_handle(MagicMock())


def test_releasing_from_disposed_structure_is_programmer_error() -> None:
    structure, _handles = _structure()
    structure.dispose()

    with pytest.raises(RuntimeError, match="uvolněné struktury"):
        structure.release_handle(structure.close_control)
