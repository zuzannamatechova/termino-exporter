from unittest.mock import MagicMock

import pytest

from termino_exporter.inspection import (
    EXPAND_CLICK_TIMEOUT_MS,
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


def test_one_more_changes_to_less_and_is_clicked_once() -> None:
    candidate = MagicMock()
    less_button = MagicMock()
    finder = _finder_with_results([candidate], [candidate], [less_button], [])
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    candidate.evaluate.assert_not_called()


def test_longer_inner_text_confirms_expansion() -> None:
    candidate = MagicMock()
    finder = _finder_with_results([candidate], [candidate], [])
    content = MagicMock()
    content.inner_text.side_effect = ["krátký", "delší rozbalený text"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    candidate.evaluate.assert_not_called()


def test_lower_more_count_confirms_expansion() -> None:
    candidate = MagicMock()
    second = MagicMock()
    finder = _finder_with_results([second, candidate], [second], [])
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    second.click.assert_not_called()


def test_two_buttons_are_processed_with_fresh_handles() -> None:
    first = MagicMock()
    stale_second = MagicMock()
    fresh_second = MagicMock()
    finder = _finder_with_results(
        [stale_second, first],
        [fresh_second],
        [fresh_second],
        [],
        [],
    )
    content = MagicMock()
    content.inner_text.side_effect = ["a", "a", "b", "b"]

    expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    first.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    fresh_second.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    stale_second.click.assert_not_called()
    assert finder.call_count == 5


def test_unconfirmed_expansion_stops_without_second_click() -> None:
    candidate = MagicMock()
    candidate.evaluate.return_value = False
    finder = _finder_with_results([candidate], [candidate], [])
    content = MagicMock()
    content.inner_text.side_effect = ["stejné", "stejné"]

    with pytest.raises(ExpansionError, match="nepodařilo potvrdit"):
        expand_all_more_buttons(MagicMock(), content, find_buttons=finder)

    candidate.click.assert_called_once_with(timeout=EXPAND_CLICK_TIMEOUT_MS)
    candidate.evaluate.assert_not_called()


def test_more_than_ten_expansions_stops_before_eleventh_click() -> None:
    candidates = [MagicMock() for _ in range(MAX_SUCCESSFUL_EXPANSIONS + 1)]
    results: list[list[MagicMock]] = []
    for candidate in candidates[:MAX_SUCCESSFUL_EXPANSIONS]:
        results.extend(([candidate], []))
    results.append([candidates[-1]])
    finder = _finder_with_results(*results)
    content = MagicMock()
    content.inner_text.side_effect = ["stejné"] * (MAX_SUCCESSFUL_EXPANSIONS * 2)

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


def test_final_text_is_read_only_after_expansion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    content = MagicMock()
    events: list[str] = []
    content.inner_text.side_effect = lambda: (
        events.append("read-final-text") or "Finální rozbalený obsah"
    )
    expand_detail = MagicMock(side_effect=lambda _page, _content: events.append("expand"))
    write = MagicMock()
    flush = MagicMock()
    close_candidate = MagicMock()
    monkeypatch.setattr(
        "termino_exporter.inspection.find_detail_content",
        MagicMock(return_value=content),
    )
    monkeypatch.setattr(
        "termino_exporter.inspection.find_safe_close_control",
        MagicMock(return_value=close_candidate),
    )
    monkeypatch.setattr(
        "termino_exporter.inspection.confirm_detail_closed",
        MagicMock(),
    )

    inspect_open_detail(
        page,
        write=write,
        flush_output=flush,
        expand_detail=expand_detail,
    )

    expand_detail.assert_called_once_with(page, content)
    content.inner_text.assert_called_once_with()
    assert events == ["expand", "read-final-text"]
    write.assert_any_call("Finální rozbalený obsah")
    flush.assert_called_once_with()
