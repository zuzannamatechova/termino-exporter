from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from xml.etree import ElementTree

import pytest
from playwright.sync_api import Error
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from termino_exporter.inspection import (
    CLOSE_CONFIRM_TIMEOUT_MS,
    CLOSE_SIGNATURE_SCRIPT,
    FIND_SCROLL_CONTAINER_SCRIPT,
    MAX_CLOSE_ANCESTOR_DEPTH,
    MAX_CONTENT_ANCESTOR_DEPTH,
    CloseControlError,
    DetailStructureError,
    ExpansionError,
    InspectionError,
    confirm_detail_closed,
    find_detail_content,
    find_safe_close_control,
    inspect_one_reservation,
    inspect_open_detail,
)


def _visible_locator(*visible: bool) -> tuple[MagicMock, list[MagicMock]]:
    locator = MagicMock()
    matches: list[MagicMock] = []
    for is_visible in visible:
        match = MagicMock()
        match.is_visible.return_value = is_visible
        matches.append(match)
    locator.count.return_value = len(matches)
    locator.nth.side_effect = matches.__getitem__
    return locator, matches


def _page_with_labels(
    date_visibility: tuple[bool, ...] = (True,),
    time_visibility: tuple[bool, ...] = (True,),
) -> tuple[MagicMock, list[MagicMock], list[MagicMock]]:
    page = MagicMock()
    date_locator, date_matches = _visible_locator(*date_visibility)
    time_locator, time_matches = _visible_locator(*time_visibility)

    def get_by_text(text: str, *, exact: bool) -> MagicMock:
        assert exact is True
        if text == "Datum":
            return date_locator
        if text == "Čas":
            return time_locator
        raise AssertionError(f"Nepovolený hledaný text: {text!r}")

    page.get_by_text.side_effect = get_by_text
    return page, date_matches, time_matches


def _detail_page() -> tuple[MagicMock, MagicMock]:
    page, date_matches, time_matches = _page_with_labels()
    date_element = MagicMock()
    time_element = MagicMock()
    content = MagicMock()
    result_handle = MagicMock()
    result_handle.as_element.return_value = content
    date_matches[0].element_handle.return_value = date_element
    time_matches[0].element_handle.return_value = time_element
    date_element.evaluate_handle.return_value = result_handle
    return page, content


@pytest.mark.parametrize(
    ("date_visibility", "time_visibility"),
    [
        ((), (True,)),
        ((False,), (True,)),
        ((True, True), (True,)),
        ((True,), ()),
        ((True,), (False,)),
        ((True,), (True, True)),
    ],
)
def test_detail_requires_exactly_one_visible_date_and_time_label(
    date_visibility: tuple[bool, ...],
    time_visibility: tuple[bool, ...],
) -> None:
    page, _, _ = _page_with_labels(date_visibility, time_visibility)

    with pytest.raises(DetailStructureError):
        find_detail_content(page)

    page.get_by_role.assert_not_called()


def test_detail_ignores_hidden_duplicate_labels() -> None:
    page, date_matches, time_matches = _page_with_labels((False, True), (True, False))
    date_element = MagicMock()
    time_element = MagicMock()
    content = MagicMock()
    result_handle = MagicMock()
    result_handle.as_element.return_value = content
    date_matches[1].element_handle.return_value = date_element
    time_matches[0].element_handle.return_value = time_element
    date_element.evaluate_handle.return_value = result_handle

    assert find_detail_content(page) is content


def test_detail_uses_bounded_shared_scroll_ancestor_search() -> None:
    page, content = _detail_page()
    date_match = page.get_by_text("Datum", exact=True).nth(0)
    date_element = date_match.element_handle.return_value
    time_element = page.get_by_text("Čas", exact=True).nth(0).element_handle.return_value

    assert find_detail_content(page) is content
    date_element.evaluate_handle.assert_called_once_with(
        FIND_SCROLL_CONTAINER_SCRIPT,
        {"timeLabel": time_element, "maxDepth": MAX_CONTENT_ANCESTOR_DEPTH},
    )
    assert MAX_CONTENT_ANCESTOR_DEPTH == 10
    assert 'overflowY === "auto"' in FIND_SCROLL_CONTAINER_SCRIPT
    assert 'overflowY === "scroll"' in FIND_SCROLL_CONTAINER_SCRIPT
    assert "scrollHeight > current.clientHeight" in FIND_SCROLL_CONTAINER_SCRIPT
    assert ".contains(timeLabel)" in FIND_SCROLL_CONTAINER_SCRIPT


@pytest.mark.parametrize("case", ["no-common-ancestor", "auto-but-not-scrollable"])
def test_detail_rejects_missing_qualifying_scroll_container(case: str) -> None:
    page, date_matches, time_matches = _page_with_labels()
    date_element = MagicMock()
    time_element = MagicMock()
    null_handle = MagicMock()
    null_handle.as_element.return_value = None
    date_matches[0].element_handle.return_value = date_element
    time_matches[0].element_handle.return_value = time_element
    date_element.evaluate_handle.return_value = null_handle

    with pytest.raises(DetailStructureError, match="rolovací obsah"):
        find_detail_content(page)

    null_handle.dispose.assert_called_once_with()


def test_detail_rejects_unavailable_element_handles() -> None:
    page, date_matches, _ = _page_with_labels()
    date_matches[0].element_handle.return_value = None

    with pytest.raises(DetailStructureError, match="rolovací obsah"):
        find_detail_content(page)


def _page_with_close_buttons(*visible: bool) -> tuple[MagicMock, list[MagicMock]]:
    page = MagicMock()
    matches = _configure_forbidden_actions(page, *visible)
    return page, matches


def _configure_forbidden_actions(page: MagicMock, *visible: bool) -> list[MagicMock]:
    if not visible:
        visible = (True,)
    matches: list[MagicMock] = []
    locators: list[MagicMock] = []
    for _action_name in range(3):
        locator, action_matches = _visible_locator(*visible)
        locators.append(locator)
        matches.extend(action_matches)
    page.get_by_role.side_effect = locators
    return matches


def _close_signature(**overrides: object) -> dict[str, object]:
    signature: dict[str, object] = {
        "hasUniqueBranches": True,
        "precedesScrollContainer": True,
        "followsScrollContainer": False,
        "hasSvg": True,
        "hasNonemptyTextContent": False,
        "isForbiddenAction": False,
    }
    signature.update(overrides)
    return signature


def _stop_parent_search(scope: MagicMock) -> None:
    parent_handle = MagicMock()
    parent_handle.as_element.return_value = None
    scope.evaluate_handle.return_value = parent_handle


def test_real_close_candidate_signature_is_accepted() -> None:
    page, _matches = _page_with_close_buttons()
    content = MagicMock()
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = [candidate]

    assert find_safe_close_control(page, content) is candidate
    assert page.get_by_role.call_count == 3
    for call, expected_name in zip(
        page.get_by_role.call_args_list,
        ("Upravit", "Odstranit", "Zkopírovat rezervaci"),
        strict=True,
    ):
        assert call.kwargs["name"].fullmatch(expected_name)
    candidate.evaluate.assert_called_once()
    assert candidate.evaluate.call_args.args[0] == CLOSE_SIGNATURE_SCRIPT
    assert "candidate" not in CLOSE_SIGNATURE_SCRIPT
    assert "buttonDepth" not in CLOSE_SIGNATURE_SCRIPT
    assert "options.root.children" in CLOSE_SIGNATURE_SCRIPT
    assert "headerIndex < contentIndex" in CLOSE_SIGNATURE_SCRIPT
    assert "contentIndex < actionIndex" in CLOSE_SIGNATURE_SCRIPT


def test_anonymized_nested_svg_button_matches_without_unstable_selectors() -> None:
    anonymized_button = ElementTree.fromstring(
        "<button><span><div><svg><path /></svg></div></span></button>"
    )
    page, _matches = _page_with_close_buttons()
    content = MagicMock()
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = [candidate]

    assert anonymized_button.tag == "button"
    assert anonymized_button.find(".//svg") is not None
    assert find_safe_close_control(page, content) is candidate
    assert 'querySelector("svg")' in CLOSE_SIGNATURE_SCRIPT
    assert "textContent" in CLOSE_SIGNATURE_SCRIPT
    for unstable_detail in ("class", "viewBox", "path", "buttonDepth"):
        assert unstable_detail not in CLOSE_SIGNATURE_SCRIPT


def test_close_control_can_be_in_parent_outside_scroll_content() -> None:
    page, _matches = _page_with_close_buttons()
    content = MagicMock()
    parent = MagicMock()
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = []
    parent.query_selector_all.return_value = [candidate]
    parent_handle = MagicMock()
    parent_handle.as_element.return_value = parent
    content.evaluate_handle.return_value = parent_handle

    assert find_safe_close_control(page, content) is candidate


@pytest.mark.parametrize(
    "signature",
    [
        _close_signature(hasUniqueBranches=False),
        _close_signature(precedesScrollContainer=False, followsScrollContainer=True),
        _close_signature(hasSvg=False),
        _close_signature(hasNonemptyTextContent=True),
        _close_signature(isForbiddenAction=True),
    ],
)
def test_close_control_rejects_unsafe_signature_without_click(
    signature: dict[str, object],
) -> None:
    page, _matches = _page_with_close_buttons()
    content = MagicMock()
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.evaluate.return_value = signature
    content.query_selector_all.return_value = [candidate]
    _stop_parent_search(content)

    with pytest.raises(CloseControlError):
        find_safe_close_control(page, content)

    candidate.click.assert_not_called()


def test_close_control_rejects_multiple_buttons_in_same_scope_without_click() -> None:
    page, _matches = _page_with_close_buttons()
    content = MagicMock()
    candidates = [MagicMock(), MagicMock()]
    for candidate in candidates:
        candidate.is_visible.return_value = True
        candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = candidates

    with pytest.raises(CloseControlError):
        find_safe_close_control(page, content)

    for candidate in candidates:
        candidate.click.assert_not_called()


def test_close_control_rejects_zero_candidates_without_click() -> None:
    page, _matches = _page_with_close_buttons()
    content = MagicMock()
    content.query_selector_all.return_value = []
    _stop_parent_search(content)

    with pytest.raises(CloseControlError):
        find_safe_close_control(page, content)

    content.click.assert_not_called()


def test_close_control_rejects_ambiguous_forbidden_action_branch() -> None:
    page, _matches = _page_with_close_buttons(True, True)
    content = MagicMock()
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = [candidate]

    with pytest.raises(CloseControlError, match="strukturální větve"):
        find_safe_close_control(page, content)

    candidate.evaluate.assert_not_called()
    candidate.click.assert_not_called()


def test_close_control_does_not_search_beyond_four_parent_levels() -> None:
    page, _matches = _page_with_close_buttons()
    scopes = [MagicMock() for _ in range(MAX_CLOSE_ANCESTOR_DEPTH + 1)]
    for index, scope in enumerate(scopes):
        scope.query_selector_all.return_value = []
        if index < len(scopes) - 1:
            handle = MagicMock()
            handle.as_element.return_value = scopes[index + 1]
            scope.evaluate_handle.return_value = handle

    with pytest.raises(CloseControlError):
        find_safe_close_control(page, scopes[0])

    assert MAX_CLOSE_ANCESTOR_DEPTH == 4
    assert sum(scope.evaluate_handle.call_count for scope in scopes) == 4


def test_inspection_reads_only_content_and_clicks_unique_close() -> None:
    page, content = _detail_page()
    content.inner_text.return_value = "Bezpečně načtený obsah"
    _configure_forbidden_actions(page)
    close_candidate = MagicMock()
    close_candidate.is_visible.return_value = True
    close_candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = [close_candidate]
    write = MagicMock()
    flush_output = MagicMock()

    inspect_open_detail(
        page,
        write=write,
        flush_output=flush_output,
        expand_detail=MagicMock(),
    )

    content.inner_text.assert_called_once_with()
    flush_output.assert_called_once_with()
    close_candidate.click.assert_called_once_with()
    content.wait_for_element_state.assert_called_once_with(
        "hidden", timeout=CLOSE_CONFIRM_TIMEOUT_MS
    )
    write.assert_any_call("Bezpečně načtený obsah")
    for call in page.get_by_text.call_args_list:
        call.return_value.inner_text.assert_not_called()


def test_inspection_prints_and_flushes_before_close_error() -> None:
    page, content = _detail_page()
    content.inner_text.return_value = "Jana Nováková"
    close_locator, _close_matches = _visible_locator()
    events: list[str] = []

    def get_by_role(*args: object, **kwargs: object) -> MagicMock:
        del args, kwargs
        events.append("find-close")
        return close_locator

    page.get_by_role.side_effect = get_by_role
    content.query_selector_all.return_value = []
    _stop_parent_search(content)

    with pytest.raises(CloseControlError):
        inspect_open_detail(
            page,
            write=lambda text: events.append(f"write:{text}"),
            flush_output=lambda: events.append("flush"),
            expand_detail=MagicMock(),
        )

    content.inner_text.assert_called_once_with()
    assert events == [
        "write:----- Finální text detailu rezervace -----",
        "write:Jana Nováková",
        "write:----- Konec finálního textu -----",
        "flush",
        "find-close",
    ]


def test_unconfirmed_close_is_not_clicked_twice() -> None:
    page, content = _detail_page()
    content.inner_text.return_value = "Jana Nováková"
    _configure_forbidden_actions(page)
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.evaluate.return_value = _close_signature()
    content.query_selector_all.return_value = [candidate]
    content.wait_for_element_state.side_effect = PlaywrightTimeoutError("timeout")

    with pytest.raises(CloseControlError, match="nepodařilo potvrdit"):
        inspect_open_detail(
            page,
            flush_output=MagicMock(),
            expand_detail=MagicMock(),
        )

    candidate.click.assert_called_once_with()


def test_closure_is_confirmed_when_one_detail_label_disappears() -> None:
    page, _date_matches, _time_matches = _page_with_labels((True,), (False,))
    content = MagicMock()
    content.wait_for_element_state.side_effect = PlaywrightTimeoutError("timeout")

    confirm_detail_closed(page, content)

    content.wait_for_element_state.assert_called_once_with(
        "hidden", timeout=CLOSE_CONFIRM_TIMEOUT_MS
    )


def test_playwright_error_does_not_expose_detail_data() -> None:
    page, content = _detail_page()
    content.inner_text.side_effect = Error("Jana Nováková")
    close_locator, close_matches = _visible_locator(True)
    page.get_by_role.return_value = close_locator
    close_matches[0].element_handle.return_value = MagicMock()
    content.evaluate.return_value = True

    with pytest.raises(InspectionError) as caught:
        inspect_open_detail(page, expand_detail=MagicMock())

    assert str(caught.value) == "Operace s otevřeným detailem se nezdařila."
    assert "Jana Nováková" not in str(caught.value)
    close_matches[0].click.assert_not_called()


class RecordingContextManager(AbstractContextManager[MagicMock]):
    def __init__(self, page: MagicMock) -> None:
        self.context = MagicMock()
        self.context.pages = [page]
        self.exited = False
        self.exit_type: type[BaseException] | None = None

    def __enter__(self) -> MagicMock:
        return self.context

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        self.exited = True
        self.exit_type = exc_type


def _run_with_context(
    monkeypatch: pytest.MonkeyPatch,
    page: MagicMock,
    *,
    diagnose_dialog: bool = False,
    diagnose_close: bool = False,
) -> RecordingContextManager:
    manager = RecordingContextManager(page)
    inspect_one_reservation(
        url="https://local.termino.eu/",
        profile_dir=Path("profile"),
        timeout_seconds=30.0,
        diagnose_dialog=diagnose_dialog,
        diagnose_close=diagnose_close,
        context_factory=lambda _profile, _timeout: manager,
        wait_for_enter=lambda _: "",
    )
    return manager


def test_browser_context_closes_after_success(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    monkeypatch.setattr("termino_exporter.inspection.inspect_open_detail", MagicMock())

    manager = _run_with_context(monkeypatch, page)

    assert manager.exited is True
    assert manager.exit_type is None


def test_browser_context_closes_after_expected_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    monkeypatch.setattr(
        "termino_exporter.inspection.inspect_open_detail",
        MagicMock(side_effect=DetailStructureError("bezpečná chyba")),
    )
    manager = RecordingContextManager(page)
    with pytest.raises(DetailStructureError):
        inspect_one_reservation(
            url="https://local.termino.eu/",
            profile_dir=Path("profile"),
            timeout_seconds=30.0,
            context_factory=lambda _profile, _timeout: manager,
            wait_for_enter=lambda _: "",
        )

    assert manager.exited is True
    assert manager.exit_type is DetailStructureError


def test_browser_context_closes_after_expansion_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    monkeypatch.setattr(
        "termino_exporter.inspection.inspect_open_detail",
        MagicMock(side_effect=ExpansionError("bezpečná chyba rozbalení")),
    )
    manager = RecordingContextManager(page)

    with pytest.raises(ExpansionError):
        inspect_one_reservation(
            url="https://local.termino.eu/",
            profile_dir=Path("profile"),
            timeout_seconds=30.0,
            context_factory=lambda _profile, _timeout: manager,
            wait_for_enter=lambda _: "",
        )

    assert manager.exited is True
    assert manager.exit_type is ExpansionError


def test_browser_context_closes_after_keyboard_interrupt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    monkeypatch.setattr(
        "termino_exporter.inspection.inspect_open_detail",
        MagicMock(side_effect=KeyboardInterrupt),
    )
    manager = RecordingContextManager(page)
    with pytest.raises(KeyboardInterrupt):
        inspect_one_reservation(
            url="https://local.termino.eu/",
            profile_dir=Path("profile"),
            timeout_seconds=30.0,
            context_factory=lambda _profile, _timeout: manager,
            wait_for_enter=lambda _: "",
        )

    assert manager.exited is True
    assert manager.exit_type is KeyboardInterrupt


def test_browser_context_closes_after_navigation_error() -> None:
    page = MagicMock()
    page.goto.side_effect = Error("citlivá URL")
    manager = RecordingContextManager(page)

    with pytest.raises(InspectionError) as caught:
        inspect_one_reservation(
            url="https://local.termino.eu/",
            profile_dir=Path("profile"),
            timeout_seconds=30.0,
            context_factory=lambda _profile, _timeout: manager,
            wait_for_enter=lambda _: "",
        )

    assert str(caught.value) == "Adresu Termino se nepodařilo otevřít."
    assert "citlivá URL" not in str(caught.value)
    assert manager.exited is True


def test_browser_context_closes_after_diagnostic_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    diagnose = MagicMock(side_effect=RuntimeError("diagnostická chyba"))
    monkeypatch.setattr("termino_exporter.inspection.diagnose_dialog_structure", diagnose)
    manager = RecordingContextManager(page)

    with pytest.raises(RuntimeError):
        inspect_one_reservation(
            url="https://local.termino.eu/",
            profile_dir=Path("profile"),
            timeout_seconds=30.0,
            diagnose_dialog=True,
            context_factory=lambda _profile, _timeout: manager,
            wait_for_enter=lambda _: "",
        )

    assert manager.exited is True


def test_diagnostic_mode_remains_separate(monkeypatch: pytest.MonkeyPatch) -> None:
    page = MagicMock()
    diagnose = MagicMock()
    inspect_detail = MagicMock()
    monkeypatch.setattr("termino_exporter.inspection.diagnose_dialog_structure", diagnose)
    monkeypatch.setattr("termino_exporter.inspection.inspect_open_detail", inspect_detail)

    manager = _run_with_context(monkeypatch, page, diagnose_dialog=True)

    diagnose.assert_called_once()
    inspect_detail.assert_not_called()
    assert manager.exited is True


def test_close_diagnostic_mode_uses_found_content_without_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    content = MagicMock()
    find_content = MagicMock(return_value=content)
    diagnose_close = MagicMock()
    inspect_detail = MagicMock()
    monkeypatch.setattr("termino_exporter.inspection.find_detail_content", find_content)
    monkeypatch.setattr(
        "termino_exporter.inspection.diagnose_close_buttons",
        diagnose_close,
    )
    monkeypatch.setattr("termino_exporter.inspection.inspect_open_detail", inspect_detail)

    manager = _run_with_context(monkeypatch, page, diagnose_close=True)

    find_content.assert_called_once_with(page)
    diagnose_close.assert_called_once()
    inspect_detail.assert_not_called()
    assert manager.exited is True
