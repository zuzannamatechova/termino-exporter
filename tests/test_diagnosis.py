import json
from pathlib import Path
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from playwright.sync_api import Error

from termino_exporter.diagnosis import (
    MAX_ANCESTOR_DEPTH,
    MAX_MATCHES_PER_PROBE,
    MAX_TOTAL_RECORDS,
    PROBES,
    DiagnosisError,
    diagnose_dialog_structure,
)

OUTPUT_FIELDS = {
    "probe",
    "depth",
    "tag",
    "role",
    "aria_modal",
    "position",
    "overflow_y",
    "visible",
    "child_count",
    "is_scrollable",
    "is_fixed_or_absolute",
}
PRIVATE_VALUES = (
    "anna-testova",
    "Jan-Novak",
    "client-420-700-000-001",
    "reservation-123-456-789",
    "test@example.com",
    "https://example.com/client/123",
)


def safe_raw_record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "depth": 0,
        "tag": "div",
        "role": "dialog",
        "ariaModal": True,
        "position": "fixed",
        "overflowY": "auto",
        "visible": True,
        "childCount": 3,
        "isScrollable": True,
        "isFixedOrAbsolute": True,
    }
    record.update(overrides)
    return record


def locator_with_matches(
    count: int,
    raw_structure: object,
    *,
    visible: bool = True,
) -> tuple[MagicMock, list[MagicMock]]:
    locator = MagicMock()
    matches = [MagicMock() for _ in range(count)]
    for match in matches:
        match.is_visible.return_value = visible
        match.evaluate.return_value = raw_structure
    locator.count.return_value = count
    locator.nth.side_effect = lambda index: matches[index]
    return locator, matches


def test_diagnosis_uses_only_safe_probe_texts_without_outputting_them() -> None:
    page = MagicMock()
    locator, matches = locator_with_matches(1, [safe_raw_record()])
    page.get_by_text.return_value = locator
    output: list[str] = []

    diagnose_dialog_structure(page, write=output.append)

    assert page.get_by_text.call_args_list == [
        call(interface_text, exact=True) for _probe, interface_text in PROBES
    ]
    combined_output = "\n".join(output)
    for _probe, interface_text in PROBES:
        assert interface_text not in combined_output
    assert {json.loads(line)["probe"] for line in output} == {
        probe for probe, _interface_text in PROBES
    }
    for match in matches:
        match.evaluate.assert_called_with(ANY, MAX_ANCESTOR_DEPTH)


def test_output_has_exact_schema_and_no_private_dom_fields() -> None:
    page = MagicMock()
    raw_record = safe_raw_record(
        id="reservation-123-456-789",
        className="anna-testova",
        classList=["client-420-700-000-001"],
        ariaLabel="Jan-Novak",
        title="test@example.com",
        dataset={"url": "https://example.com/client/123"},
        textContent="soukromý text",
    )
    locator, _ = locator_with_matches(1, [raw_record])
    page.get_by_text.return_value = locator
    output: list[str] = []

    diagnose_dialog_structure(page, write=output.append)

    combined_output = "\n".join(output)
    for private_value in PRIVATE_VALUES:
        assert private_value not in combined_output
    assert "soukromý text" not in combined_output
    assert set(json.loads(output[0])) == OUTPUT_FIELDS
    for forbidden_key in (
        "id",
        "class",
        "className",
        "classList",
        "ariaLabel",
        "title",
        "dataset",
        "textContent",
    ):
        assert forbidden_key not in combined_output


def test_more_than_ten_visible_matches_fails_without_output() -> None:
    page = MagicMock()
    locator, _ = locator_with_matches(MAX_MATCHES_PER_PROBE + 1, [safe_raw_record()])
    page.get_by_text.return_value = locator
    output: list[str] = []

    with pytest.raises(DiagnosisError, match="příliš mnoho odpovídajících prvků"):
        diagnose_dialog_structure(page, write=output.append)

    assert output == []


def test_exactly_ten_visible_matches_are_allowed() -> None:
    page = MagicMock()
    empty_locator, _ = locator_with_matches(0, [])
    ten_locator, _ = locator_with_matches(MAX_MATCHES_PER_PROBE, [safe_raw_record()])
    page.get_by_text.side_effect = [
        ten_locator,
        empty_locator,
        empty_locator,
        empty_locator,
        empty_locator,
    ]
    output: list[str] = []

    diagnose_dialog_structure(page, write=output.append)

    assert len(output) == MAX_MATCHES_PER_PROBE


def test_total_record_limit_fails_without_partial_output() -> None:
    page = MagicMock()
    records_per_match = [safe_raw_record(depth=depth) for depth in range(3)]
    locator, _ = locator_with_matches(MAX_MATCHES_PER_PROBE, records_per_match)
    page.get_by_text.return_value = locator
    output: list[str] = []

    with pytest.raises(DiagnosisError, match="překročil bezpečný limit"):
        diagnose_dialog_structure(page, write=output.append)

    assert MAX_MATCHES_PER_PROBE * 3 * len(PROBES) > MAX_TOTAL_RECORDS
    assert output == []


def test_ancestors_are_limited_to_depth_zero_through_six() -> None:
    page = MagicMock()
    raw_structure = [safe_raw_record(depth=depth) for depth in range(10)]
    locator, _ = locator_with_matches(1, raw_structure)
    page.get_by_text.return_value = locator
    output: list[str] = []

    diagnose_dialog_structure(page, write=output.append)

    depths = [json.loads(line)["depth"] for line in output[: MAX_ANCESTOR_DEPTH + 1]]
    assert depths == list(range(MAX_ANCESTOR_DEPTH + 1))


def test_unknown_enums_are_replaced_and_child_count_is_capped() -> None:
    page = MagicMock()
    locator, _ = locator_with_matches(
        1,
        [
            safe_raw_record(
                tag="custom-client-element",
                role="client-name",
                position="private-position",
                overflowY="private-overflow",
                childCount=50_000,
            )
        ],
    )
    page.get_by_text.return_value = locator
    output: list[str] = []

    diagnose_dialog_structure(page, write=output.append)

    record = json.loads(output[0])
    assert record["tag"] == "other"
    assert record["role"] is None
    assert record["position"] is None
    assert record["overflow_y"] is None
    assert record["child_count"] == 999


def test_diagnosis_never_reads_content_or_interacts() -> None:
    page = MagicMock()
    locator, matches = locator_with_matches(1, [safe_raw_record()])
    page.get_by_text.return_value = locator

    diagnose_dialog_structure(page, write=MagicMock())

    for target in (page, *matches):
        target.inner_text.assert_not_called()
        target.text_content.assert_not_called()
        target.click.assert_not_called()
        target.press.assert_not_called()
        target.fill.assert_not_called()
        target.type.assert_not_called()


def test_diagnosis_does_not_write_files() -> None:
    page = MagicMock()
    locator, _ = locator_with_matches(0, [])
    page.get_by_text.return_value = locator

    with (
        patch("builtins.open") as open_file,
        patch.object(Path, "write_text") as write_text,
        patch.object(Path, "write_bytes") as write_bytes,
    ):
        diagnose_dialog_structure(page, write=MagicMock())

    open_file.assert_not_called()
    write_text.assert_not_called()
    write_bytes.assert_not_called()


def test_playwright_error_is_sanitized() -> None:
    page = MagicMock()
    page.get_by_text.side_effect = Error("locator s klientským údajem Jana Nováková")

    with pytest.raises(DiagnosisError) as captured_error:
        diagnose_dialog_structure(page)

    assert str(captured_error.value) == "Diagnostiku se nepodařilo bezpečně dokončit."
