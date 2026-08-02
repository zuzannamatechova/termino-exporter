import json
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

from termino_exporter.close_diagnosis import (
    BUTTON_STRUCTURE_SCRIPT,
    MAX_COMMON_ANCESTOR_DEPTH,
    MAX_ROOT_DEPTH,
    MAX_VISIBLE_BUTTONS,
    OUTPUT_FIELDS,
    CloseDiagnosisError,
    diagnose_close_buttons,
)


def _empty_locator() -> MagicMock:
    locator = MagicMock()
    locator.count.return_value = 0
    return locator


def _content_with_root(buttons: list[MagicMock]) -> tuple[MagicMock, MagicMock]:
    content = MagicMock()
    current = content
    for _ in range(MAX_ROOT_DEPTH):
        parent = MagicMock()
        parent_handle = MagicMock()
        parent_handle.as_element.return_value = parent
        current.evaluate_handle.return_value = parent_handle
        current = parent
    current.query_selector_all.return_value = buttons
    return content, current


def _safe_raw(**overrides: object) -> dict[str, object]:
    raw: dict[str, object] = {
        "limitExceeded": False,
        "buttonDepth": 2,
        "directChildCount": 1,
        "hasSvg": True,
        "hasImg": False,
        "hasSpan": False,
        "hasNonemptyTextNode": False,
        "hasSafeAccessibleName": False,
        "isForbiddenAction": False,
        "precedesScrollContainer": True,
        "followsScrollContainer": False,
        "sameParentAsScrollContainer": False,
        "commonAncestorDistance": 3,
        "visible": True,
    }
    raw.update(overrides)
    return raw


def test_diagnosis_outputs_only_exact_allowlisted_schema_and_booleans() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    button = MagicMock()
    button.is_visible.return_value = True
    button.evaluate.return_value = _safe_raw(
        hasSvg=True,
        hasNonemptyTextNode=True,
        hasSafeAccessibleName=True,
        isForbiddenAction=True,
        clientName="TEST OSOBA",
        ariaLabel="Zavřít",
        text="soukromý text rezervace",
    )
    content, _root = _content_with_root([button])
    output: list[str] = []

    diagnose_close_buttons(page, content, output.append)

    assert len(output) == 1
    record = json.loads(output[0])
    assert tuple(record) == tuple(sorted(OUTPUT_FIELDS))
    assert set(record) == set(OUTPUT_FIELDS)
    assert record["has_svg"] is True
    assert record["has_nonempty_text_node"] is True
    assert record["has_safe_accessible_name"] is True
    assert record["is_forbidden_action"] is True
    assert "TEST OSOBA" not in output[0]
    assert "soukromý text rezervace" not in output[0]
    assert "Upravit" not in output[0]
    assert "Zavřít" not in output[0]


def test_diagnosis_uses_exact_names_only_as_non_output_identity_sets() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    button = MagicMock()
    button.is_visible.return_value = True
    button.evaluate.return_value = _safe_raw()
    content, _root = _content_with_root([button])

    diagnose_close_buttons(page, content, MagicMock())

    assert page.get_by_role.call_count == 2
    safe_pattern = page.get_by_role.call_args_list[0].kwargs["name"]
    forbidden_pattern = page.get_by_role.call_args_list[1].kwargs["name"]
    assert safe_pattern.fullmatch("Zavřít")
    assert safe_pattern.fullmatch("Close")
    assert safe_pattern.fullmatch("Upravit") is None
    assert forbidden_pattern.fullmatch("Upravit")
    assert forbidden_pattern.fullmatch("Odstranit")
    assert forbidden_pattern.fullmatch("Zkopírovat rezervaci")
    assert forbidden_pattern.fullmatch("Zavřít") is None


def test_diagnosis_never_reads_or_returns_dom_text_and_never_interacts() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    button = MagicMock()
    button.is_visible.return_value = True
    button.evaluate.return_value = _safe_raw(hasNonemptyTextNode=True)
    content, _root = _content_with_root([button])
    output: list[str] = []

    diagnose_close_buttons(page, content, output.append)

    for forbidden_method in (
        "inner_text",
        "text_content",
        "inner_html",
        "click",
        "press",
        "fill",
        "type",
        "hover",
        "dispatch_event",
    ):
        getattr(button, forbidden_method).assert_not_called()
    assert "innerText" not in BUTTON_STRUCTURE_SCRIPT
    assert "textContent" not in BUTTON_STRUCTURE_SCRIPT
    assert "innerHTML" not in BUTTON_STRUCTURE_SCRIPT
    assert "outerHTML" not in BUTTON_STRUCTURE_SCRIPT
    assert ".id" not in BUTTON_STRUCTURE_SCRIPT
    assert "className" not in BUTTON_STRUCTURE_SCRIPT
    assert "dataset" not in BUTTON_STRUCTURE_SCRIPT
    assert MAX_COMMON_ANCESTOR_DEPTH == 10
    assert all(not isinstance(value, str) for value in json.loads(output[0]).values())


def test_more_than_twenty_visible_buttons_fails_without_partial_output() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    buttons = [MagicMock() for _ in range(MAX_VISIBLE_BUTTONS + 1)]
    for button in buttons:
        button.is_visible.return_value = True
    content, _root = _content_with_root(buttons)
    write = MagicMock()

    with pytest.raises(CloseDiagnosisError) as caught:
        diagnose_close_buttons(page, content, write)

    assert caught.value.code == "CLOSE_DIAG_TOO_MANY_BUTTONS"
    assert str(caught.value) == "CLOSE_DIAG_TOO_MANY_BUTTONS"
    write.assert_not_called()
    for button in buttons:
        button.evaluate.assert_not_called()
        button.click.assert_not_called()


def test_limit_error_in_later_candidate_has_no_partial_output() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    first = MagicMock()
    first.is_visible.return_value = True
    first.evaluate.return_value = _safe_raw()
    second = MagicMock()
    second.is_visible.return_value = True
    second.evaluate.return_value = {"limitExceeded": True}
    content, _root = _content_with_root([first, second])
    write = MagicMock()

    with pytest.raises(CloseDiagnosisError) as caught:
        diagnose_close_buttons(page, content, write)

    assert caught.value.code == "CLOSE_DIAG_RECORD_LIMIT"
    write.assert_not_called()
    first.click.assert_not_called()
    second.click.assert_not_called()


def test_root_search_stops_after_four_parents() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    button = MagicMock()
    button.is_visible.return_value = True
    button.evaluate.return_value = _safe_raw()
    content, root = _content_with_root([button])

    diagnose_close_buttons(page, content, MagicMock())

    assert MAX_ROOT_DEPTH == 4
    assert root.evaluate_handle.call_count == 0
    assert root.query_selector_all.call_args.args == ("button",)


def test_missing_safe_root_has_specific_code_and_no_output() -> None:
    page = MagicMock()
    content = MagicMock()
    parent_handle = MagicMock()
    parent_handle.as_element.return_value = None
    content.evaluate_handle.return_value = parent_handle
    write = MagicMock()

    with pytest.raises(CloseDiagnosisError) as caught:
        diagnose_close_buttons(page, content, write)

    assert caught.value.code == "CLOSE_DIAG_ROOT_NOT_FOUND"
    write.assert_not_called()


def test_no_visible_buttons_has_specific_code_and_no_output() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    content, _root = _content_with_root([])
    write = MagicMock()

    with pytest.raises(CloseDiagnosisError) as caught:
        diagnose_close_buttons(page, content, write)

    assert caught.value.code == "CLOSE_DIAG_NO_BUTTONS"
    write.assert_not_called()


def test_invalid_record_has_structure_error_code_and_no_dom_data() -> None:
    page = MagicMock()
    page.get_by_role.return_value = _empty_locator()
    button = MagicMock()
    button.is_visible.return_value = True
    button.evaluate.return_value = {"clientName": "TEST OSOBA"}
    content, _root = _content_with_root([button])
    write = MagicMock()

    with pytest.raises(CloseDiagnosisError) as caught:
        diagnose_close_buttons(page, content, write)

    assert caught.value.code == "CLOSE_DIAG_STRUCTURE_ERROR"
    assert "TEST OSOBA" not in str(caught.value)
    write.assert_not_called()


def test_playwright_error_has_specific_code_and_sanitized_message() -> None:
    page = MagicMock()
    content = MagicMock()
    content.evaluate_handle.side_effect = Error("DOM obsahuje TEST OSOBA")
    write = MagicMock()

    with pytest.raises(CloseDiagnosisError) as caught:
        diagnose_close_buttons(page, content, write)

    assert caught.value.code == "CLOSE_DIAG_PLAYWRIGHT_ERROR"
    assert str(caught.value) == "CLOSE_DIAG_PLAYWRIGHT_ERROR"
    assert "TEST OSOBA" not in str(caught.value)
    assert isinstance(caught.value.__cause__, Error)
    write.assert_not_called()


def test_close_diagnosis_disposes_all_temporary_handle_wrappers() -> None:
    page = MagicMock()
    safe_name_handle = MagicMock()
    forbidden_handle = MagicMock()

    def locator_for(handle: MagicMock) -> MagicMock:
        candidate = MagicMock()
        candidate.is_visible.return_value = True
        candidate.element_handle.return_value = handle
        locator = MagicMock()
        locator.count.return_value = 1
        locator.nth.return_value = candidate
        return locator

    page.get_by_role.side_effect = [
        locator_for(safe_name_handle),
        locator_for(forbidden_handle),
    ]
    content = MagicMock()
    roots = [MagicMock(name=f"root-{index}") for index in range(MAX_ROOT_DEPTH)]
    conversion_handles = []
    current = content
    for root in roots:
        conversion = MagicMock()
        conversion.as_element.return_value = root
        current.evaluate_handle.return_value = conversion
        conversion_handles.append(conversion)
        current = root
    button = MagicMock()
    button.is_visible.return_value = True
    button.evaluate.return_value = _safe_raw()
    hidden_button = MagicMock()
    hidden_button.is_visible.return_value = False
    roots[-1].query_selector_all.return_value = [button, hidden_button]

    diagnose_close_buttons(page, content, MagicMock())

    for conversion in conversion_handles:
        conversion.dispose.assert_called_once_with()
    for root in roots:
        root.dispose.assert_called_once_with()
    safe_name_handle.dispose.assert_called_once_with()
    forbidden_handle.dispose.assert_called_once_with()
    button.dispose.assert_called_once_with()
    hidden_button.dispose.assert_called_once_with()
    content.dispose.assert_not_called()
