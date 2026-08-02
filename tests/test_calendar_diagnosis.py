from __future__ import annotations

import inspect
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

import termino_exporter.calendar_diagnosis as calendar_module
from termino_exporter.calendar_diagnosis import (
    CALENDAR_DIAGNOSIS_SCRIPT,
    CalendarContextSnapshot,
    CalendarDiagnosisError,
    CalendarDomSnapshot,
    CalendarHeaderGroupSnapshot,
    CalendarHeaderSnapshot,
    CalendarLayerSnapshot,
    deserialize_calendar_snapshot,
    diagnose_calendar,
    diagnose_calendar_structure,
    format_calendar_diagnosis,
    resolve_calendar_snapshot,
)


def _layer(
    count: int,
    *,
    gridcells: tuple[int, ...] | None = None,
    children: tuple[int, ...] | None = None,
    descendants: tuple[int, ...] | None = None,
    events: tuple[int, ...] | None = None,
    navigation: bool = False,
    header: bool = False,
) -> CalendarLayerSnapshot:
    zeros = (0,) * count
    return CalendarLayerSnapshot(
        branch_count=count,
        gridcell_counts=zeros if gridcells is None else gridcells,
        direct_child_counts=zeros if children is None else children,
        descendant_counts=zeros if descendants is None else descendants,
        event_block_counts=zeros if events is None else events,
        navigation_like=navigation,
        header_like=header,
    )


def _headers(count: int, *, start_day: int = 1) -> CalendarHeaderGroupSnapshot:
    return CalendarHeaderGroupSnapshot(
        tuple(CalendarHeaderSnapshot(index % 7, start_day + index, True) for index in range(count)),
        True,
    )


def _snapshot(
    count: int = 7,
    *,
    extra_layers: tuple[CalendarLayerSnapshot, ...] = (),
    events: tuple[int, ...] | None = None,
    headers: tuple[CalendarHeaderGroupSnapshot, ...] | None = None,
) -> CalendarDomSnapshot:
    event_counts = (1,) + (0,) * (count - 1) if events is None else events
    grid = _layer(count, gridcells=(1,) * count)
    event = _layer(count, events=event_counts)
    return CalendarDomSnapshot(
        (CalendarContextSnapshot((grid, *extra_layers, event)),),
        (_headers(count),) if headers is None else headers,
    )


def _layer_payload(count: int, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "branch_count": count,
        "gridcell_counts": [0] * count,
        "direct_child_counts": [0] * count,
        "descendant_counts": [0] * count,
        "event_block_counts": [0] * count,
        "navigation_like": False,
        "header_like": False,
    }
    payload.update(overrides)
    return payload


def _payload(count: int = 7) -> dict[str, object]:
    return {
        "contexts": [
            {
                "layers": [
                    _layer_payload(count, gridcell_counts=[1] * count),
                    _layer_payload(count, event_block_counts=[1] + [0] * (count - 1)),
                ]
            }
        ],
        "header_groups": [
            {
                "headers": [
                    {
                        "weekday_index": index % 7,
                        "day_number": index + 1,
                        "header_parseable": True,
                    }
                    for index in range(count)
                ],
                "headers_distinct": True,
            }
        ],
    }


def _five_layer_payload() -> dict[str, object]:
    count = 7
    return {
        "contexts": [
            {
                "layers": [
                    _layer_payload(1, event_block_counts=[4]),
                    _layer_payload(count, direct_child_counts=[1, 1, 0, 0, 0, 0, 0]),
                    _layer_payload(
                        count,
                        direct_child_counts=[17] * count,
                        descendant_counts=[17] * count,
                    ),
                    _layer_payload(count, gridcell_counts=[1] * count),
                    _layer_payload(
                        count,
                        direct_child_counts=[1, 1, 0, 0, 0, 1, 0],
                        event_block_counts=[1, 1, 0, 0, 0, 0, 0],
                    ),
                ]
            }
        ],
        "header_groups": [
            {
                "headers": [
                    {
                        "weekday_index": weekday,
                        "day_number": day,
                        "header_parseable": True,
                    }
                    for weekday, day in enumerate((27, 28, 29, 30, 31, 1, 2))
                ],
                "headers_distinct": True,
            }
        ],
    }


def test_resolver_selects_event_layer_from_five_parallel_layers() -> None:
    count = 7
    different_width = _layer(1, events=(4,))
    empty_helper = _layer(count, children=(1, 1, 0, 0, 0, 0, 0))
    time_grid = _layer(count, children=(24,) * count, descendants=(24,) * count)
    grid = _layer(count, gridcells=(1,) * count)
    event = _layer(count, children=(1, 1, 0, 0, 0, 1, 0), events=(1, 1, 0, 0, 0, 0, 0))
    snapshot = CalendarDomSnapshot(
        (CalendarContextSnapshot((different_width, empty_helper, time_grid, grid, event)),),
        (_headers(count, start_day=20),),
    )

    result = resolve_calendar_snapshot(snapshot)

    assert result.mode == "CALENDAR_LAYERS_FOUND"
    assert result.column_count == 7
    assert tuple(column.ordinal for column in result.columns) == tuple(range(1, 8))
    assert tuple(column.event_block_count for column in result.columns) == (1, 1, 0, 0, 0, 0, 0)
    assert all(column.gridcell_present for column in result.columns)
    assert not hasattr(result, "event_type")


@pytest.mark.parametrize("count", [1, 3, 7, 5, 14])
def test_resolver_supports_bounded_column_counts(count: int) -> None:
    result = resolve_calendar_snapshot(_snapshot(count))
    assert result.column_count == count
    assert len(result.columns) == count


def test_resolver_rejects_direct_snapshot_outside_column_limit() -> None:
    invalid = CalendarDomSnapshot(
        (CalendarContextSnapshot((_layer(15, gridcells=(1,) * 15),)),),
        (),
    )
    with pytest.raises(CalendarDiagnosisError, match="^CALENDAR_DIAG_INVALID_SNAPSHOT$"):
        resolve_calendar_snapshot(invalid)


def test_resolver_reports_two_grid_layers_as_ambiguous() -> None:
    grid = _layer(7, gridcells=(1,) * 7)
    snapshot = CalendarDomSnapshot(
        (CalendarContextSnapshot((grid, grid, _layer(7, events=(1, 0, 0, 0, 0, 0, 0)))),),
        (),
    )
    with pytest.raises(CalendarDiagnosisError, match="^GRIDCELL_LAYER_AMBIGUOUS$"):
        resolve_calendar_snapshot(snapshot)


def test_resolver_reports_missing_grid_layer() -> None:
    snapshot = CalendarDomSnapshot((CalendarContextSnapshot((_layer(7, events=(1,) * 7),)),), ())
    with pytest.raises(CalendarDiagnosisError, match="^GRIDCELL_LAYER_NOT_FOUND$"):
        resolve_calendar_snapshot(snapshot)


def test_empty_helper_and_different_sized_time_grid_are_not_events() -> None:
    empty_helper = _layer(7, children=(1, 1, 0, 0, 0, 0, 0))
    time_grid = _layer(7, children=(17,) * 7, descendants=(17,) * 7)
    result = resolve_calendar_snapshot(_snapshot(extra_layers=(empty_helper, time_grid)))
    assert tuple(column.event_block_count for column in result.columns) == (1, 0, 0, 0, 0, 0, 0)


def test_two_event_layers_are_ambiguous_and_first_is_not_selected() -> None:
    second_event = _layer(7, events=(0, 1, 0, 0, 0, 0, 0))
    with pytest.raises(CalendarDiagnosisError, match="^EVENT_LAYER_AMBIGUOUS$"):
        resolve_calendar_snapshot(_snapshot(extra_layers=(second_event,)))


def test_empty_period_has_no_event_layer() -> None:
    grid = _layer(7, gridcells=(1,) * 7)
    helper = _layer(7)
    snapshot = CalendarDomSnapshot((CalendarContextSnapshot((grid, helper)),), ())
    with pytest.raises(CalendarDiagnosisError, match="^EVENT_LAYER_EMPTY_OR_NOT_FOUND$"):
        resolve_calendar_snapshot(snapshot)


def test_event_layer_does_not_need_to_be_first_parallel_layer() -> None:
    result = resolve_calendar_snapshot(
        _snapshot(extra_layers=(_layer(7), _layer(3, events=(2, 2, 2))))
    )
    assert tuple(column.event_block_count for column in result.columns) == (1, 0, 0, 0, 0, 0, 0)


def test_event_counts_remain_separate_for_every_column() -> None:
    counts = (1, 2, 0, 3, 0, 0, 4)
    result = resolve_calendar_snapshot(_snapshot(events=counts))
    assert tuple(column.event_block_count for column in result.columns) == counts


def test_navigation_header_and_grid_layers_are_not_event_layers() -> None:
    excluded = (
        _layer(7, events=(1,) * 7, navigation=True),
        _layer(7, events=(1,) * 7, header=True),
    )
    result = resolve_calendar_snapshot(_snapshot(extra_layers=excluded))
    assert tuple(column.event_block_count for column in result.columns) == (1, 0, 0, 0, 0, 0, 0)


def test_one_valid_header_group_is_used() -> None:
    result = resolve_calendar_snapshot(_snapshot(3, headers=(_headers(3, start_day=10),)))
    assert result.headers_resolved is True
    assert tuple(column.weekday_index for column in result.columns) == (0, 1, 2)
    assert tuple(column.day_number for column in result.columns) == (10, 11, 12)


@pytest.mark.parametrize("groups", [(), (_headers(7), _headers(7, start_day=8))])
def test_missing_or_ambiguous_headers_do_not_block_layers(
    groups: tuple[CalendarHeaderGroupSnapshot, ...],
) -> None:
    result = resolve_calendar_snapshot(_snapshot(headers=groups))
    assert result.mode == "CALENDAR_LAYERS_FOUND_HEADERS_UNRESOLVED"
    assert result.headers_resolved is False
    assert all(
        column.weekday_index is None and column.day_number is None for column in result.columns
    )


@pytest.mark.parametrize(
    "header",
    [
        {"weekday_index": 7, "day_number": 1, "header_parseable": True},
        {"weekday_index": 0, "day_number": 32, "header_parseable": True},
    ],
)
def test_deserializer_rejects_invalid_header_values(header: dict[str, object]) -> None:
    payload = _payload(1)
    payload["header_groups"] = [{"headers": [header], "headers_distinct": True}]
    with pytest.raises(CalendarDiagnosisError, match="^CALENDAR_DIAG_INVALID_SNAPSHOT$"):
        deserialize_calendar_snapshot(payload)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.update(contexts="invalid"),
        lambda payload: payload["contexts"][0]["layers"][0].update(branch_count=15),
        lambda payload: payload["contexts"][0]["layers"][0].update(gridcell_counts=[1, -1, 1]),
        lambda payload: payload["contexts"][0]["layers"][0].update(event_block_counts=[1]),
    ],
)
def test_deserializer_rejects_invalid_snapshot_without_repr(
    mutation: Any,
) -> None:
    payload = _payload(3)
    payload["private"] = "TEST UDÁLOST"
    mutation(payload)
    with pytest.raises(CalendarDiagnosisError) as caught:
        deserialize_calendar_snapshot(payload)
    assert str(caught.value) == "CALENDAR_DIAG_INVALID_SNAPSHOT"
    assert "TEST UDÁLOST" not in str(caught.value)


def test_deserializer_enforces_context_and_layer_limits() -> None:
    with pytest.raises(CalendarDiagnosisError, match="^CALENDAR_DIAG_LIMIT_EXCEEDED$"):
        deserialize_calendar_snapshot({"contexts": [{}] * 21, "header_groups": []})
    with pytest.raises(CalendarDiagnosisError, match="^CALENDAR_DIAG_LIMIT_EXCEEDED$"):
        deserialize_calendar_snapshot(
            {"contexts": [{"layers": [_layer_payload(1)] * 21}], "header_groups": []}
        )


def test_raw_javascript_contract_keys_are_accepted_exactly() -> None:
    snapshot = deserialize_calendar_snapshot(_five_layer_payload())
    layer = snapshot.contexts[0].layers[0]
    assert set(_five_layer_payload()) == {"contexts", "header_groups"}
    assert set(_five_layer_payload()["contexts"][0]) == {"layers"}
    assert layer.branch_count == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"header_groups": []},
        {"contexts": "invalid", "header_groups": []},
        {"contexts": [{}], "header_groups": []},
        {
            "contexts": [{"layers": [_layer_payload(1, branch_count="1")]}],
            "header_groups": [],
        },
        {
            "contexts": [{"layers": [_layer_payload(1, branch_count=True)]}],
            "header_groups": [],
        },
        {
            "contexts": [{"layers": [_layer_payload(2, gridcell_counts=[1])]}],
            "header_groups": [],
        },
        {
            "contexts": [
                {
                    "layers": [
                        {
                            key: value
                            for key, value in _layer_payload(1).items()
                            if key != "event_block_counts"
                        }
                    ]
                }
            ],
            "header_groups": [],
        },
        {"contexts": [], "nested": {"header_groups": []}},
    ],
)
def test_missing_malformed_or_undefined_census_is_invalid(payload: object) -> None:
    with pytest.raises(CalendarDiagnosisError, match="^CALENDAR_DIAG_INVALID_SNAPSHOT$"):
        deserialize_calendar_snapshot(payload)


def test_diagnose_structure_deserializes_and_resolves_snapshot() -> None:
    page = MagicMock()
    page.evaluate.return_value = _payload(7)
    result = diagnose_calendar_structure(page)
    assert result.mode == "CALENDAR_LAYERS_FOUND"
    assert result.column_count == 7


def test_missing_page_evaluate_return_is_invalid_snapshot() -> None:
    page = MagicMock()
    page.evaluate.return_value = None
    with pytest.raises(CalendarDiagnosisError, match="^CALENDAR_DIAG_INVALID_SNAPSHOT$"):
        diagnose_calendar_structure(page)


def test_public_orchestration_processes_realistic_five_layer_census() -> None:
    page = MagicMock()
    page.evaluate.return_value = _five_layer_payload()
    manager = _Manager(page)
    result = diagnose_calendar(
        url="https://example.invalid/calendar",
        profile_dir=Path("test-profile"),
        timeout_seconds=10,
        wait_for_enter=lambda _prompt: "",
        write=MagicMock(),
        context_factory=lambda _profile, _timeout: manager,
    )
    assert result.mode == "CALENDAR_LAYERS_FOUND"
    assert result.column_count == 7
    assert result.headers_resolved is True
    assert tuple(column.weekday_index for column in result.columns) == tuple(range(7))
    assert tuple(column.day_number for column in result.columns) == (27, 28, 29, 30, 31, 1, 2)
    assert tuple(column.event_block_count for column in result.columns) == (1, 1, 0, 0, 0, 0, 0)
    assert result.click_count == 0
    page.evaluate.assert_called_once_with(CALENDAR_DIAGNOSIS_SCRIPT)
    assert manager.exited is True


def test_playwright_error_is_sanitized() -> None:
    page = MagicMock()
    page.evaluate.side_effect = Error("TEST UDÁLOST v DOM")
    with pytest.raises(CalendarDiagnosisError) as caught:
        diagnose_calendar_structure(page)
    assert str(caught.value) == "CALENDAR_DIAG_CENSUS_FAILED"
    assert "TEST UDÁLOST" not in str(caught.value)


def test_static_census_source_has_only_safe_bounded_techniques() -> None:
    source = inspect.getsource(calendar_module)
    for forbidden in (
        ".click(",
        "scrollIntoView",
        "scrollTo",
        "screenshot",
        "outerHTML",
        "innerHTML",
        "bounding_box",
        'get_attribute("class")',
        'get_attribute("id")',
        'get_attribute("style")',
        "className",
        "getElementById",
    ):
        assert forbidden not in source
    assert "MAX_DEPTH = 12" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "MAX_ELEMENTS = 5000" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "MAX_CONTEXTS = 20" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "MAX_LAYERS = 20" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "MAX_COLUMNS = 14" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "MAX_COMMON_ANCESTORS = 4" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "MAX_EVENT_DESCENDANTS = 30" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "element.children.length > 10" in CALENDAR_DIAGNOSIS_SCRIPT


def test_static_census_keeps_private_text_inside_javascript() -> None:
    assert "privateText" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "element.innerText.trim().length > 0" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "inner_text" not in inspect.getsource(calendar_module)
    assert "text_content" not in inspect.getsource(calendar_module)


def test_static_visibility_checks_bounded_ancestor_chain() -> None:
    assert "current = current.parentElement" in CALENDAR_DIAGNOSIS_SCRIPT
    assert "depth <= MAX_DEPTH" in CALENDAR_DIAGNOSIS_SCRIPT
    assert 'presentation.display === "none"' in CALENDAR_DIAGNOSIS_SCRIPT
    assert 'presentation.visibility === "hidden"' in CALENDAR_DIAGNOSIS_SCRIPT
    assert "current === document.body" in CALENDAR_DIAGNOSIS_SCRIPT


class _Manager(AbstractContextManager[MagicMock]):
    def __init__(self, page: MagicMock) -> None:
        self.context = MagicMock(pages=[page])
        self.exited = False

    def __enter__(self) -> MagicMock:
        return self.context

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: Any,
    ) -> None:
        self.exited = True


def test_diagnose_calendar_reads_once_without_interactions() -> None:
    page = MagicMock()
    page.evaluate.return_value = _payload(7)
    manager = _Manager(page)
    write = MagicMock()
    result = diagnose_calendar(
        url="https://example.invalid/calendar",
        profile_dir=Path("test-profile"),
        timeout_seconds=10,
        wait_for_enter=lambda _prompt: "",
        write=write,
        context_factory=lambda _profile, _timeout: manager,
    )
    assert result.column_count == 7
    page.goto.assert_called_once_with("https://example.invalid/calendar")
    page.evaluate.assert_called_once_with(CALENDAR_DIAGNOSIS_SCRIPT)
    page.click.assert_not_called()
    page.keyboard.press.assert_not_called()
    assert manager.exited is True


def test_context_closes_after_safe_error() -> None:
    page = MagicMock()
    page.evaluate.return_value = {"contexts": [], "header_groups": []}
    manager = _Manager(page)
    with pytest.raises(CalendarDiagnosisError, match="^GRIDCELL_LAYER_NOT_FOUND$"):
        diagnose_calendar(
            url="https://example.invalid/calendar",
            profile_dir=Path("test-profile"),
            timeout_seconds=10,
            wait_for_enter=lambda _prompt: "",
            context_factory=lambda _profile, _timeout: manager,
        )
    assert manager.exited is True


def test_format_keeps_classification_and_private_text_out() -> None:
    output = format_calendar_diagnosis(resolve_calendar_snapshot(_snapshot()))
    assert "Události klasifikovány: ne" in output
    assert "Texty událostí vypsány: ne" in output
    assert "Hodnoty atributů vypsány: ne" in output
    assert "TEST UDÁLOST" not in output
