from __future__ import annotations

from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from termino_exporter.inspection import (
    CLOSE_CONFIRM_TIMEOUT_MS,
    FIND_SCROLL_CONTAINER_SCRIPT,
    MAX_CONTENT_ANCESTOR_DEPTH,
    CloseControlError,
    DetailStructureError,
    ExpansionError,
    InspectionError,
    ReservationProcessingError,
    confirm_detail_closed,
    find_detail_content,
    find_safe_close_control,
    inspect_one_reservation,
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


def test_safe_close_control_uses_shared_detail_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    content = MagicMock()
    candidate = MagicMock()
    structure = MagicMock(close_control=candidate)
    resolver = MagicMock(return_value=structure)
    monkeypatch.setattr("termino_exporter.inspection.find_detail_structure", resolver)

    assert find_safe_close_control(page, content) is candidate
    resolver.assert_called_once_with(page, content)
    candidate.click.assert_not_called()


def test_safe_close_control_translates_safe_structure_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from termino_exporter.extraction import ReservationExtractionError

    resolver = MagicMock(side_effect=ReservationExtractionError("CLOSE_CONTROL_NOT_UNIQUE"))
    monkeypatch.setattr("termino_exporter.inspection.find_detail_structure", resolver)

    with pytest.raises(CloseControlError) as caught:
        find_safe_close_control(MagicMock(), MagicMock())

    assert str(caught.value) == "Detail nemá jednoznačně rozpoznaný zavírací prvek."


def test_closure_is_confirmed_when_one_detail_label_disappears() -> None:
    page, _date_matches, _time_matches = _page_with_labels((True,), (False,))
    content = MagicMock()
    content.wait_for_element_state.side_effect = PlaywrightTimeoutError("timeout")

    confirm_detail_closed(page, content)

    content.wait_for_element_state.assert_called_once_with(
        "hidden", timeout=CLOSE_CONFIRM_TIMEOUT_MS
    )


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


def test_browser_context_closes_after_processing_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    monkeypatch.setattr(
        "termino_exporter.inspection.inspect_open_detail",
        MagicMock(
            side_effect=ReservationProcessingError(
                "Zpracování rezervace se nezdařilo (INVALID_DATE)."
            )
        ),
    )
    manager = RecordingContextManager(page)

    with pytest.raises(ReservationProcessingError):
        inspect_one_reservation(
            url="https://local.termino.eu/",
            profile_dir=Path("profile"),
            timeout_seconds=30.0,
            context_factory=lambda _profile, _timeout: manager,
            wait_for_enter=lambda _: "",
        )

    assert manager.exited is True
    assert manager.exit_type is ReservationProcessingError


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
