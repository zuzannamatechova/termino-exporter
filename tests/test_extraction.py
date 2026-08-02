from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

import termino_exporter.extraction as extraction
from termino_exporter.extraction import (
    CLOSE_CONTROL_SIGNATURE_SCRIPT,
    EXTRACT_CLEAN_TEXT_SCRIPT,
    EXTRACT_CLIENT_NAME_SCRIPT,
    EXTRACT_FIELDS_SCRIPT,
    KNOWN_FIELD_LABELS,
    MAX_STRUCTURE_ANCESTOR_DEPTH,
    ROOT_STRUCTURE_SCRIPT,
    DetailStructure,
    ReservationExtractionError,
    extract_reservation_data,
    find_detail_content,
    find_detail_structure,
)


def _visible_locator(handle: MagicMock) -> MagicMock:
    candidate = MagicMock()
    candidate.is_visible.return_value = True
    candidate.element_handle.return_value = handle
    locator = MagicMock()
    locator.count.return_value = 1
    locator.nth.return_value = candidate
    return locator


def test_detail_content_distinguishes_absence_from_ambiguity() -> None:
    page = MagicMock()
    no_matches = MagicMock()
    no_matches.count.return_value = 0
    page.get_by_text.return_value = no_matches

    with pytest.raises(ReservationExtractionError, match="^DETAIL_STRUCTURE_NOT_FOUND$"):
        find_detail_content(page)

    one_match = MagicMock()
    one_match.is_visible.return_value = True
    one_label = MagicMock()
    one_label.count.return_value = 1
    one_label.nth.return_value = one_match
    page.get_by_text.side_effect = [one_label, no_matches]
    with pytest.raises(ReservationExtractionError, match="^DETAIL_STRUCTURE_NOT_UNIQUE$"):
        find_detail_content(page)


def _structure_page() -> tuple[MagicMock, list[MagicMock]]:
    page = MagicMock()
    actions = [MagicMock() for _ in range(3)]
    page.get_by_role.side_effect = [_visible_locator(action) for action in actions]
    return page, actions


def _parent(child: MagicMock, parent: MagicMock | None) -> None:
    handle = MagicMock()
    handle.as_element.return_value = parent
    child.evaluate_handle.return_value = handle


def _safe_close_signature() -> dict[str, bool]:
    return {
        "isInHeader": True,
        "hasSvg": True,
        "hasNonemptyTextContent": False,
        "isForbiddenAction": False,
    }


def _unique_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[MagicMock, DetailStructure, list[MagicMock]]:
    page, actions = _structure_page()
    content = MagicMock()
    root = MagicMock()
    header = MagicMock()
    content_branch = MagicMock()
    action_branch = MagicMock()
    close = MagicMock()
    close.is_visible.return_value = True
    close.evaluate.return_value = _safe_close_signature()
    content.evaluate.return_value = False
    root.evaluate.return_value = True
    root.query_selector_all.return_value = [close]
    _parent(content, root)
    _parent(root, None)

    def branch_for(_root: MagicMock, target: MagicMock) -> MagicMock:
        assert _root is root
        if target is content:
            return content_branch
        if target is actions[0]:
            return action_branch
        if target is close:
            return header
        raise AssertionError("Neočekávaný testovací cíl větve")

    monkeypatch.setattr(extraction, "_branch_containing", branch_for)
    structure = find_detail_structure(page, content)
    return page, structure, actions


def test_unique_header_content_action_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, structure, actions = _unique_structure(monkeypatch)

    assert structure.root is not structure.content_branch
    assert structure.header_branch is not structure.content_branch
    assert structure.action_branch is not structure.content_branch
    assert structure.scroll_container is not structure.content_branch
    assert structure.close_control is not None
    assert page.get_by_role.call_count == 3
    for call, expected in zip(
        page.get_by_role.call_args_list,
        ("Upravit", "Odstranit", "Zkopírovat rezervaci"),
        strict=True,
    ):
        assert call.kwargs["name"].fullmatch(expected)
    for action in actions:
        action.click.assert_not_called()


def test_returned_structure_owns_new_handles_but_not_caller_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _page, structure, actions = _unique_structure(monkeypatch)

    for handle in (
        structure.root,
        structure.header_branch,
        structure.content_branch,
        structure.action_branch,
        structure.close_control,
    ):
        handle.dispose.assert_not_called()
    structure.scroll_container.dispose.assert_not_called()
    for action in actions:
        action.dispose.assert_called_once_with()

    structure.dispose()

    for handle in (
        structure.root,
        structure.header_branch,
        structure.content_branch,
        structure.action_branch,
        structure.close_control,
    ):
        handle.dispose.assert_called_once_with()
    structure.scroll_container.dispose.assert_not_called()


def test_successful_detail_content_disposes_temporaries_but_returns_live_content() -> None:
    page = MagicMock()
    date_handle = MagicMock()
    time_handle = MagicMock()
    content = MagicMock()
    result_handle = MagicMock()
    result_handle.as_element.return_value = content
    page.get_by_text.side_effect = [_visible_locator(date_handle), _visible_locator(time_handle)]
    date_handle.evaluate_handle.return_value = result_handle

    assert find_detail_content(page) is content

    date_handle.dispose.assert_called_once_with()
    time_handle.dispose.assert_called_once_with()
    result_handle.dispose.assert_called_once_with()
    content.dispose.assert_not_called()


def test_failed_as_element_disposes_result_and_label_handles() -> None:
    page = MagicMock()
    date_handle = MagicMock()
    time_handle = MagicMock()
    result_handle = MagicMock()
    result_handle.as_element.return_value = None
    page.get_by_text.side_effect = [_visible_locator(date_handle), _visible_locator(time_handle)]
    date_handle.evaluate_handle.return_value = result_handle

    with pytest.raises(ReservationExtractionError, match="^DETAIL_STRUCTURE_NOT_UNIQUE$"):
        find_detail_content(page)

    date_handle.dispose.assert_called_once_with()
    time_handle.dispose.assert_called_once_with()
    result_handle.dispose.assert_called_once_with()


def test_second_label_handle_error_releases_first_handle() -> None:
    page = MagicMock()
    date_handle = MagicMock()
    date_locator = _visible_locator(date_handle)
    time_locator = _visible_locator(MagicMock())
    time_locator.nth.return_value.element_handle.side_effect = Error("TEST DOM")
    page.get_by_text.side_effect = [date_locator, time_locator]

    with pytest.raises(ReservationExtractionError, match="^DETAIL_STRUCTURE_NOT_UNIQUE$"):
        find_detail_content(page)

    date_handle.dispose.assert_called_once_with()


def test_evaluate_handle_error_releases_both_label_handles() -> None:
    page = MagicMock()
    date_handle = MagicMock()
    time_handle = MagicMock()
    page.get_by_text.side_effect = [_visible_locator(date_handle), _visible_locator(time_handle)]
    date_handle.evaluate_handle.side_effect = Error("TEST DOM")

    with pytest.raises(ReservationExtractionError, match="^DETAIL_STRUCTURE_NOT_UNIQUE$"):
        find_detail_content(page)

    date_handle.dispose.assert_called_once_with()
    time_handle.dispose.assert_called_once_with()


def test_internally_found_content_is_transferred_to_returned_structure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page, actions = _structure_page()
    content = MagicMock()
    root = MagicMock()
    header = MagicMock()
    content_branch = MagicMock()
    action_branch = MagicMock()
    close = MagicMock()
    close.is_visible.return_value = True
    close.evaluate.return_value = _safe_close_signature()
    content.evaluate.return_value = False
    root.evaluate.return_value = True
    root.query_selector_all.return_value = [close]
    _parent(content, root)
    _parent(root, None)
    monkeypatch.setattr(extraction, "find_detail_content", MagicMock(return_value=content))

    def branch_for(_root: MagicMock, target: MagicMock) -> MagicMock:
        assert _root is root
        if target is content:
            return content_branch
        if target is actions[0]:
            return action_branch
        if target is close:
            return header
        raise AssertionError("Neočekávaný testovací cíl větve")

    monkeypatch.setattr(extraction, "_branch_containing", branch_for)

    internal_structure = find_detail_structure(page)

    content.dispose.assert_not_called()
    internal_structure.dispose()
    content.dispose.assert_called_once_with()


@pytest.mark.parametrize("case", ["missing-header", "missing-action", "reversed-order"])
def test_invalid_branch_structure_is_rejected(case: str) -> None:
    page, _actions = _structure_page()
    content = MagicMock()
    root = MagicMock()
    content.evaluate.return_value = False
    root.evaluate.return_value = False
    _parent(content, root)
    _parent(root, None)

    with pytest.raises(ReservationExtractionError) as caught:
        find_detail_structure(page, content)

    assert str(caught.value) == "DETAIL_STRUCTURE_NOT_UNIQUE"
    root.dispose.assert_called_once_with()
    content.dispose.assert_not_called()


def test_multiple_possible_roots_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    page, actions = _structure_page()
    content = MagicMock()
    roots = [MagicMock(), MagicMock()]
    closes = [MagicMock(), MagicMock()]
    for root, close in zip(roots, closes, strict=True):
        root.evaluate.return_value = True
        root.query_selector_all.return_value = [close]
        close.is_visible.return_value = True
        close.evaluate.return_value = _safe_close_signature()
    content.evaluate.return_value = False
    _parent(content, roots[0])
    _parent(roots[0], roots[1])
    _parent(roots[1], None)

    def branch_for(root: MagicMock, target: MagicMock) -> MagicMock:
        del target
        return MagicMock(name=f"branch-{id(root)}")

    monkeypatch.setattr(extraction, "_branch_containing", branch_for)
    with pytest.raises(ReservationExtractionError) as caught:
        find_detail_structure(page, content)

    assert str(caught.value) == "DETAIL_STRUCTURE_NOT_UNIQUE"
    assert all(action.click.call_count == 0 for action in actions)


@pytest.mark.parametrize("close_count", [0, 2])
def test_close_control_must_be_unique(
    monkeypatch: pytest.MonkeyPatch,
    close_count: int,
) -> None:
    page, _actions = _structure_page()
    content = MagicMock()
    root = MagicMock()
    closes = [MagicMock() for _ in range(close_count)]
    for close in closes:
        close.is_visible.return_value = True
        close.evaluate.return_value = _safe_close_signature()
    content.evaluate.return_value = False
    root.evaluate.return_value = True
    root.query_selector_all.return_value = closes
    _parent(content, root)
    _parent(root, None)
    monkeypatch.setattr(extraction, "_branch_containing", MagicMock())

    with pytest.raises(ReservationExtractionError) as caught:
        find_detail_structure(page, content)

    assert str(caught.value) == "CLOSE_CONTROL_NOT_UNIQUE"
    for close in closes:
        close.click.assert_not_called()


def test_structure_search_is_bounded_to_four_ancestors() -> None:
    page, _actions = _structure_page()
    scopes = [MagicMock() for _ in range(MAX_STRUCTURE_ANCESTOR_DEPTH + 1)]
    for index, scope in enumerate(scopes):
        scope.evaluate.return_value = False
        if index < len(scopes) - 1:
            _parent(scope, scopes[index + 1])

    with pytest.raises(ReservationExtractionError):
        find_detail_structure(page, scopes[0])

    assert MAX_STRUCTURE_ANCESTOR_DEPTH == 4
    assert sum(scope.evaluate_handle.call_count for scope in scopes) == 4


def _extraction_structure() -> DetailStructure:
    return DetailStructure(
        root=MagicMock(),
        header_branch=MagicMock(),
        content_branch=MagicMock(),
        scroll_container=MagicMock(),
        action_branch=MagicMock(),
        close_control=MagicMock(),
    )


def _configure_extraction(
    structure: DetailStructure,
    *,
    client_result: object = None,
    fields_result: object = None,
    raw_result: object = "OČIŠTĚNÝ TESTOVACÍ DETAIL",
) -> None:
    if client_result is None:
        client_result = {"status": "ok", "value": "TEST OSOBA"}
    if fields_result is None:
        fields_result = {"status": "ok", "fields": {}}
    structure.header_branch.evaluate.return_value = client_result

    def evaluate(script: str, *args: object) -> object:
        del args
        if script == EXTRACT_FIELDS_SCRIPT:
            return fields_result
        if script == EXTRACT_CLEAN_TEXT_SCRIPT:
            return raw_result
        raise AssertionError("Neočekávaný extrakční skript")

    structure.scroll_container.evaluate.side_effect = evaluate


def test_client_name_is_one_unsplit_line_and_close_is_not_clicked() -> None:
    structure = _extraction_structure()
    _configure_extraction(structure)

    result = extract_reservation_data(MagicMock(), structure)

    assert result.client_name == "TEST OSOBA"
    structure.header_branch.evaluate.assert_called_once_with(
        EXTRACT_CLIENT_NAME_SCRIPT,
        structure.close_control,
    )
    structure.close_control.click.assert_not_called()
    assert "cloneNode(true)" in EXTRACT_CLIENT_NAME_SCRIPT
    assert "cloneControl.remove()" in EXTRACT_CLIENT_NAME_SCRIPT
    assert "querySelectorAll" not in EXTRACT_CLIENT_NAME_SCRIPT
    assert 'status === "ok" ? {status, value: lines[0]} : {status}' in (EXTRACT_CLIENT_NAME_SCRIPT)


@pytest.mark.parametrize(
    ("client_result", "code"),
    [
        ({"status": "not-found"}, "CLIENT_NAME_NOT_FOUND"),
        ({"status": "ambiguous"}, "CLIENT_NAME_AMBIGUOUS"),
    ],
)
def test_invalid_client_name_is_safe_error(client_result: object, code: str) -> None:
    structure = _extraction_structure()
    _configure_extraction(structure, client_result=client_result)

    with pytest.raises(ReservationExtractionError) as caught:
        extract_reservation_data(MagicMock(), structure)

    assert str(caught.value) == code
    structure.close_control.click.assert_not_called()


def test_raw_detail_clone_removes_only_exact_less_buttons() -> None:
    structure = _extraction_structure()
    raw = "Testovací poznámka\nMéně\nspan Méně\nJiný button"
    _configure_extraction(structure, raw_result=raw)

    result = extract_reservation_data(MagicMock(), structure)

    assert result.raw_detail == raw
    assert 'querySelectorAll("button")' in EXTRACT_CLEAN_TEXT_SCRIPT
    assert '=== "Méně"' in EXTRACT_CLEAN_TEXT_SCRIPT
    assert "cloneNode(true)" in EXTRACT_CLEAN_TEXT_SCRIPT
    assert '.replace("Méně"' not in EXTRACT_CLEAN_TEXT_SCRIPT
    structure.scroll_container.click.assert_not_called()


def test_all_known_fields_are_returned_without_flat_text_parsing() -> None:
    structure = _extraction_structure()
    fields = {label: f"TEST HODNOTA {index}" for index, label in enumerate(KNOWN_FIELD_LABELS)}
    fields["Poznámka"] = "Testovací poznámka\nMéně"
    _configure_extraction(structure, fields_result={"status": "ok", "fields": fields})

    result = extract_reservation_data(MagicMock(), structure)

    assert dict(result.fields) == fields
    assert len(result.fields) == 14
    assert result.fields["Poznámka"] == "Testovací poznámka\nMéně"
    assert "raw_detail" not in EXTRACT_FIELDS_SCRIPT
    assert 'maxDepth": MAX_FIELD_ANCESTOR_DEPTH' not in EXTRACT_FIELDS_SCRIPT
    assert "following" in EXTRACT_FIELDS_SCRIPT


def test_missing_empty_unknown_and_arbitrary_order_fields() -> None:
    structure = _extraction_structure()
    fields = {"Poznámka": "", "Datum": "27. 7. 2030"}
    _configure_extraction(structure, fields_result={"status": "ok", "fields": fields})

    result = extract_reservation_data(MagicMock(), structure)

    assert dict(result.fields) == fields
    assert "Neznámé pole" not in result.fields


def test_duplicate_structural_label_is_rejected() -> None:
    structure = _extraction_structure()
    _configure_extraction(structure, fields_result={"status": "duplicate"})

    with pytest.raises(ReservationExtractionError) as caught:
        extract_reservation_data(MagicMock(), structure)

    assert str(caught.value) == "DUPLICATE_KNOWN_FIELD"


def test_note_text_datum_is_excluded_when_nested_in_value_branch() -> None:
    assert "isInsideValueOf(candidate, other)" in EXTRACT_FIELDS_SCRIPT
    assert "isInsideValueOf(other, candidate)" in EXTRACT_FIELDS_SCRIPT
    assert "candidate.label === label" in EXTRACT_FIELDS_SCRIPT


def test_extraction_errors_do_not_expose_playwright_data() -> None:
    structure = _extraction_structure()
    structure.scroll_container.evaluate.side_effect = Error(
        "TEST OSOBA test@example.invalid Testovací poznámka"
    )

    with pytest.raises(ReservationExtractionError) as caught:
        extract_reservation_data(MagicMock(), structure)

    assert str(caught.value) == "FIELD_STRUCTURE_AMBIGUOUS"
    rendered = repr(caught.value)
    assert "TEST OSOBA" not in rendered
    assert "test@example.invalid" not in rendered
    assert "Testovací poznámka" not in rendered


def test_extraction_uses_no_unstable_selectors_or_interactions() -> None:
    source = "\n".join(
        (
            ROOT_STRUCTURE_SCRIPT,
            CLOSE_CONTROL_SIGNATURE_SCRIPT,
            EXTRACT_CLIENT_NAME_SCRIPT,
            EXTRACT_CLEAN_TEXT_SCRIPT,
            EXTRACT_FIELDS_SCRIPT,
        )
    )
    for forbidden in ("className", "getElementById", "xpath", "getBoundingClientRect"):
        assert forbidden not in source
    for interaction in (".click(", ".press(", ".fill(", ".type("):
        assert interaction not in source
    assert "options.maxDepth" in EXTRACT_FIELDS_SCRIPT


def test_text_normalization_scripts_keep_javascript_escapes() -> None:
    scripts = (
        EXTRACT_CLIENT_NAME_SCRIPT,
        EXTRACT_CLEAN_TEXT_SCRIPT,
        EXTRACT_FIELDS_SCRIPT,
    )
    for script in scripts:
        assert "\r" not in script
        assert r'replace(/\r\n?/g, "\n")' in script
