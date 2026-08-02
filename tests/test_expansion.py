from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

import termino_exporter.inspection as inspection_module
from termino_exporter.extraction import DetailStructure
from termino_exporter.inspection import (
    EXPAND_CLICK_TIMEOUT_MS,
    EXPAND_POLL_INTERVAL_SECONDS,
    MATCHES_NAMED_BUTTON_SCRIPT,
    MAX_SUCCESSFUL_EXPANSIONS,
    ExpansionError,
    _visible_named_buttons_inside,
    expand_all_more_buttons,
    inspect_open_detail,
)


def _finder_with_results(*results: list[MagicMock]) -> MagicMock:
    finder = MagicMock()
    finder.side_effect = results
    return finder


def test_no_more_button_means_no_click() -> None:
    finder = _finder_with_results([])
    content = MagicMock()

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    content.inner_text.assert_not_called()
    content.click.assert_not_called()


def test_first_less_button_increase_confirms_click() -> None:
    candidate = MagicMock()
    less_button = MagicMock()
    finder = _finder_with_results([candidate], [], [candidate], [less_button], [])
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    candidate.evaluate.assert_called_once_with(
        MATCHES_NAMED_BUTTON_SCRIPT,
        [less_button],
    )
    less_button.click.assert_not_called()
    candidate.dispose.assert_called_once_with()
    less_button.dispose.assert_called_once_with()


def test_second_less_button_increase_confirms_click() -> None:
    candidate = MagicMock()
    old_less = MagicMock()
    new_less = MagicMock()
    finder = _finder_with_results(
        [candidate],
        [old_less],
        [candidate],
        [old_less, new_less],
        [],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    old_less.click.assert_not_called()
    new_less.click.assert_not_called()


def test_existing_less_without_new_change_does_not_confirm_click() -> None:
    candidate = MagicMock()
    old_less = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results(
        [candidate],
        [old_less],
        [candidate],
        [old_less],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    with pytest.raises(ExpansionError, match="nepodařilo potvrdit"):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder, progress_timeout_ms=0)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    old_less.click.assert_not_called()


def test_clicked_handle_changing_exact_name_confirms_click() -> None:
    candidate = MagicMock()
    changed_candidate = MagicMock()
    candidate.evaluate.return_value = True
    finder = _finder_with_results(
        [candidate],
        [MagicMock()],
        [candidate],
        [changed_candidate],
        [],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.evaluate.assert_called_once_with(
        MATCHES_NAMED_BUTTON_SCRIPT,
        [changed_candidate],
    )
    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    changed_candidate.click.assert_not_called()


def test_longer_inner_text_confirms_expansion() -> None:
    candidate = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results([candidate], [], [candidate], [], [])
    content = MagicMock()
    content.inner_text.side_effect = ["krátký", "delší rozbalený text"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)


def test_lower_more_count_confirms_expansion() -> None:
    candidate = MagicMock()
    second = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results([second, candidate], [], [second], [], [])
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    second.click.assert_not_called()


def test_two_more_first_succeeds_second_does_not_react() -> None:
    first = MagicMock()
    stale_second = MagicMock()
    fresh_second = MagicMock()
    old_less = MagicMock()
    first.evaluate.return_value = False
    fresh_second.evaluate.return_value = False
    finder = _finder_with_results(
        [stale_second, first],
        [],
        [fresh_second],
        [old_less],
        [fresh_second],
        [old_less],
        [fresh_second],
        [old_less],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["a", "a", "b", "b"]

    with pytest.raises(ExpansionError, match="nepodařilo potvrdit"):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder, progress_timeout_ms=0)

    first.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    fresh_second.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    stale_second.click.assert_not_called()
    old_less.click.assert_not_called()
    assert finder.call_count == 8


def test_unconfirmed_expansion_stops_without_second_click() -> None:
    candidate = MagicMock()
    old_less = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results([candidate], [old_less], [candidate], [old_less])
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    with pytest.raises(ExpansionError, match="nepodařilo potvrdit"):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder, progress_timeout_ms=0)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    old_less.click.assert_not_called()
    candidate.dispose.assert_called_once_with()
    old_less.dispose.assert_called_once_with()


def test_timeout_keeps_candidate_alive_through_last_check_then_disposes() -> None:
    events: list[str] = []
    candidate = MagicMock()
    old_less = MagicMock()
    candidate.click.side_effect = lambda **_kwargs: events.append("click")
    candidate.evaluate.side_effect = lambda *_args: events.append("verify") or False
    candidate.dispose.side_effect = lambda: events.append("dispose")
    finder = _finder_with_results([candidate], [old_less], [candidate], [old_less])
    content = MagicMock()
    content.inner_text.side_effect = ["x", "x"]

    with pytest.raises(ExpansionError):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder, progress_timeout_ms=0)

    assert events == ["click", "verify", "dispose"]


def test_reused_mock_wrapper_is_never_disposed_twice() -> None:
    candidate = MagicMock()
    old_less = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results([candidate], [old_less], [candidate], [old_less])
    content = MagicMock()
    content.inner_text.side_effect = ["x", "x"]

    with pytest.raises(ExpansionError):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder, progress_timeout_ms=0)

    candidate.dispose.assert_called_once_with()
    old_less.dispose.assert_called_once_with()


def test_more_count_can_drop_on_second_poll_without_another_click() -> None:
    candidate = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results(
        [candidate],
        [],
        [candidate],
        [],
        [],
        [],
        [],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné", "stejné"]
    sleep = MagicMock()

    expand_all_more_buttons(
        MagicMock(), content, find_buttons=finder, monotonic=lambda: 0.0, sleep=sleep
    )

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    sleep.assert_called_once_with(EXPAND_POLL_INTERVAL_SECONDS)


def test_less_count_can_increase_on_third_poll() -> None:
    candidate = MagicMock()
    old_less = MagicMock()
    new_less = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results(
        [candidate],
        [old_less],
        [candidate],
        [old_less],
        [candidate],
        [old_less],
        [candidate],
        [old_less, new_less],
        [],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["x", "x", "x", "x"]
    sleep = MagicMock()

    expand_all_more_buttons(
        MagicMock(), content, find_buttons=finder, monotonic=lambda: 0.0, sleep=sleep
    )

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    assert sleep.call_count == 2
    old_less.click.assert_not_called()
    new_less.click.assert_not_called()


def test_text_can_grow_after_multiple_polls() -> None:
    candidate = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results(
        [candidate], [], [candidate], [], [candidate], [], [candidate], [], []
    )
    content = MagicMock()
    content.inner_text.side_effect = ["x", "x", "x", "delší"]
    sleep = MagicMock()

    expand_all_more_buttons(
        MagicMock(), content, find_buttons=finder, monotonic=lambda: 0.0, sleep=sleep
    )

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    assert sleep.call_count == 2


def test_candidate_can_change_to_less_after_delayed_poll() -> None:
    candidate = MagicMock()
    changed = MagicMock()
    candidate.evaluate.side_effect = [False, True]
    finder = _finder_with_results([candidate], [], [candidate], [], [candidate], [changed], [])
    content = MagicMock()
    content.inner_text.side_effect = ["x", "x", "x"]
    sleep = MagicMock()

    expand_all_more_buttons(
        MagicMock(), content, find_buttons=finder, monotonic=lambda: 0.0, sleep=sleep
    )

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    sleep.assert_called_once_with(EXPAND_POLL_INTERVAL_SECONDS)


def test_stale_candidate_during_poll_is_not_exposed_as_playwright_error() -> None:
    candidate = MagicMock()
    candidate.evaluate.side_effect = Error("TEST CITLIVÝ DETAIL")
    finder = _finder_with_results([candidate], [], [candidate], [])
    content = MagicMock()
    content.inner_text.side_effect = ["x", "x"]

    with pytest.raises(ExpansionError) as captured_error:
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder, progress_timeout_ms=0)

    assert "TEST CITLIVÝ DETAIL" not in str(captured_error.value)
    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)


def test_more_than_ten_expansions_stops_before_eleventh_click() -> None:
    candidates = [MagicMock() for _ in range(MAX_SUCCESSFUL_EXPANSIONS + 1)]
    results: list[list[MagicMock]] = []
    text_values: list[str] = []
    for index, candidate in enumerate(candidates[:MAX_SUCCESSFUL_EXPANSIONS]):
        candidate.evaluate.return_value = False
        results.extend(([candidate], [], [candidate], []))
        text_values.extend(("x" * (index + 1), "x" * (index + 2)))
    results.append([candidates[-1]])
    finder = _finder_with_results(*results)
    content = MagicMock()
    content.inner_text.side_effect = text_values

    with pytest.raises(ExpansionError, match="příliš mnoho"):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    for candidate in candidates[:MAX_SUCCESSFUL_EXPANSIONS]:
        candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    candidates[-1].click.assert_not_called()


def test_named_button_must_be_visible_descendant_button() -> None:
    page = MagicMock()
    content = MagicMock()
    inside = MagicMock()
    inside.is_visible.return_value = True
    inside.evaluate.return_value = True
    outside = MagicMock()
    named_locator = MagicMock()
    named_locator.count.return_value = 2
    named_locator.nth.side_effect = [inside, outside]
    inside.element_handle.return_value = inside
    outside.is_visible.return_value = True
    outside.element_handle.return_value = outside
    page.get_by_role.return_value = named_locator
    content.query_selector_all.return_value = [inside]

    assert _visible_named_buttons_inside(page, content, "Více") == [inside]
    inside.evaluate.assert_called_once_with(
        MATCHES_NAMED_BUTTON_SCRIPT,
        [inside, outside],
    )
    outside.click.assert_not_called()


@pytest.mark.parametrize("non_matching_content", ["Více informací", "Méně"])
def test_inexact_or_less_button_is_not_returned(non_matching_content: str) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.count.return_value = 0
    page.get_by_role.return_value = locator
    content = MagicMock()
    content.query_selector_all.return_value = []

    assert _visible_named_buttons_inside(page, content, "Více") == []
    pattern = page.get_by_role.call_args.kwargs["name"]
    assert pattern.fullmatch(non_matching_content) is None


def test_span_named_more_without_button_is_not_clicked() -> None:
    page = MagicMock()
    page.get_by_role.return_value.count.return_value = 0
    content = MagicMock()
    content.query_selector_all.return_value = []

    assert _visible_named_buttons_inside(page, content, "Více") == []
    content.query_selector_all.assert_called_once_with("button")


@pytest.mark.parametrize(
    "forbidden_name",
    ["Upravit", "Odstranit", "Zkopírovat rezervaci"],
)
def test_forbidden_action_is_not_returned_or_clicked(forbidden_name: str) -> None:
    page = MagicMock()
    locator = MagicMock()
    locator.count.return_value = 0
    page.get_by_role.return_value = locator
    content = MagicMock()
    forbidden_button = MagicMock()
    forbidden_button.is_visible.return_value = True
    forbidden_button.evaluate.return_value = False
    content.query_selector_all.return_value = [forbidden_button]

    assert _visible_named_buttons_inside(page, content, "Více") == []
    assert page.get_by_role.call_args.kwargs["name"].fullmatch(forbidden_name) is None
    forbidden_button.click.assert_not_called()


def test_expansion_error_prints_no_detail_or_client_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    scroll_container = MagicMock()
    structure = MagicMock(scroll_container=scroll_container)
    write = MagicMock()
    monkeypatch.setattr(
        "termino_exporter.inspection.find_detail_structure",
        MagicMock(return_value=structure),
    )

    with pytest.raises(ExpansionError):
        inspect_open_detail(
            page,
            write=write,
            expand_detail=MagicMock(
                side_effect=ExpansionError("Rozbalení se nepodařilo potvrdit.")
            ),
        )

    write.assert_not_called()
    structure.close_control.click.assert_not_called()
    structure.dispose.assert_called_once_with()


def test_detail_structure_dispose_error_does_not_mask_expansion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles = [MagicMock() for _ in range(6)]
    handles[0].dispose.side_effect = Error("TEST DOM")
    structure = DetailStructure(
        root=handles[0],
        header_branch=handles[1],
        content_branch=handles[2],
        scroll_container=handles[3],
        action_branch=handles[4],
        close_control=handles[5],
        _owned_handles=tuple(handles),
    )
    monkeypatch.setattr(
        inspection_module,
        "find_detail_structure",
        MagicMock(return_value=structure),
    )

    with pytest.raises(ExpansionError, match="původní chyba"):
        inspect_open_detail(
            MagicMock(),
            expand_detail=MagicMock(side_effect=ExpansionError("původní chyba")),
        )
