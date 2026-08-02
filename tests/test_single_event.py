from __future__ import annotations

import inspect
from contextlib import AbstractContextManager
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from playwright.sync_api import Error

import termino_exporter.inspection as inspection_module
import termino_exporter.single_event as single_event_module
from termino_exporter.calendar_diagnosis import (
    CalendarContextSnapshot,
    CalendarDiagnosisError,
    CalendarDomSnapshot,
    CalendarLayerSnapshot,
)
from termino_exporter.extraction import ReservationExtractionError
from termino_exporter.models import Reservation
from termino_exporter.single_event import (
    SingleEventError,
    create_single_event_plan,
    find_single_event_handle,
    inspect_single_event,
    inspect_single_event_page,
)


def _layer(
    count: int,
    *,
    grid: bool = False,
    events: tuple[int, ...] | None = None,
    shadowed: bool = False,
) -> CalendarLayerSnapshot:
    zeros = (0,) * count
    return CalendarLayerSnapshot(
        branch_count=count,
        gridcell_counts=(1,) * count if grid else zeros,
        direct_child_counts=zeros,
        descendant_counts=zeros,
        event_block_counts=zeros if events is None else events,
        navigation_like=False,
        header_like=False,
        shadowed_by_nested_equivalent_grid_anchor=shadowed,
    )


def _snapshot(
    count: int = 1,
    *,
    events: tuple[int, ...] | None = None,
    extra_layers: tuple[CalendarLayerSnapshot, ...] = (),
) -> CalendarDomSnapshot:
    event_counts = (1,) + (0,) * (count - 1) if events is None else events
    return CalendarDomSnapshot(
        (
            CalendarContextSnapshot(
                (_layer(count, grid=True), *extra_layers, _layer(count, events=event_counts))
            ),
        ),
        (),
    )


def _flattened_day_snapshot(
    *,
    trailing_layers: tuple[CalendarLayerSnapshot, ...] = (),
    include_event: bool = True,
) -> CalendarDomSnapshot:
    layers = (
        _layer(1, events=(23,)),
        _layer(1),
        _layer(1),
        _layer(1, grid=True),
    )
    if include_event:
        layers = (*layers, _layer(1, events=(1,)))
    return CalendarDomSnapshot(
        (CalendarContextSnapshot((*layers, *trailing_layers)),),
        (),
    )


def _changed_grid_structure_snapshot() -> CalendarDomSnapshot:
    snapshot = _snapshot()
    context = snapshot.contexts[0]
    changed_grid = replace(context.layers[0], direct_child_counts=(1,))
    return CalendarDomSnapshot(
        (CalendarContextSnapshot((changed_grid, *context.layers[1:])),),
        (),
    )


def test_one_day_column_and_one_event_create_plan() -> None:
    plan = create_single_event_plan(_snapshot())
    assert plan.context_ordinal == 1
    assert plan.column_count == 1
    assert plan.column_ordinal == 1
    assert plan.event_ordinal == 1
    assert plan.event_block_counts == (1,)
    assert plan.fingerprint.column_count == 1
    assert plan.fingerprint.event_block_counts == (1,)


def test_selection_plan_and_semantic_fingerprint_are_immutable() -> None:
    plan = create_single_event_plan(_snapshot())

    with pytest.raises(FrozenInstanceError):
        plan.context_ordinal = 2  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.fingerprint.column_count = 2  # type: ignore[misc]


def test_flattened_day_plan_ignores_time_layer_before_grid() -> None:
    plan = create_single_event_plan(_flattened_day_snapshot())

    assert plan.context_ordinal == 1
    assert plan.event_layer_ordinal == 5
    assert plan.column_count == 1
    assert plan.event_block_counts == (1,)


@pytest.mark.parametrize("columns", [3, 7])
def test_non_day_view_is_rejected(columns: int) -> None:
    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_REQUIRES_DAY_VIEW$"):
        create_single_event_plan(_snapshot(columns))


def test_zero_events_are_rejected() -> None:
    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_NOT_FOUND$"):
        create_single_event_plan(_snapshot(events=(0,)))


def test_two_events_are_rejected() -> None:
    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_NOT_UNIQUE$"):
        create_single_event_plan(_snapshot(events=(2,)))


def test_two_event_layers_are_rejected() -> None:
    with pytest.raises(SingleEventError, match="^CALENDAR_STRUCTURE_CHANGED$"):
        create_single_event_plan(_snapshot(extra_layers=(_layer(1, events=(1,)),)))


def test_two_event_layers_after_grid_do_not_select_first_handle() -> None:
    page = MagicMock()
    snapshot = _flattened_day_snapshot(trailing_layers=(_layer(1, events=(1,)),))

    with pytest.raises(SingleEventError, match="^CALENDAR_STRUCTURE_CHANGED$"):
        create_single_event_plan(snapshot)

    page.evaluate_handle.assert_not_called()
    page.click.assert_not_called()


def test_missing_event_layer_does_not_request_handle() -> None:
    page = MagicMock()

    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_NOT_FOUND$"):
        create_single_event_plan(_flattened_day_snapshot(include_event=False))

    page.evaluate_handle.assert_not_called()
    page.click.assert_not_called()


def test_two_grid_layers_are_rejected() -> None:
    with pytest.raises(SingleEventError, match="^CALENDAR_STRUCTURE_CHANGED$"):
        create_single_event_plan(_snapshot(extra_layers=(_layer(1, grid=True),)))


def test_shadowed_equivalent_grid_layer_is_ignored_by_single_event_plan() -> None:
    plan = create_single_event_plan(_snapshot(extra_layers=(_layer(1, grid=True, shadowed=True),)))

    assert plan.column_count == 1
    assert plan.event_block_counts == (1,)


def test_two_calendar_contexts_are_rejected() -> None:
    one = _snapshot().contexts[0]
    with pytest.raises(SingleEventError, match="^CALENDAR_STRUCTURE_CHANGED$"):
        create_single_event_plan(CalendarDomSnapshot((one, one), ()))


def _handle_result(status: str, element: MagicMock | None = None) -> MagicMock:
    result = MagicMock()
    status_property = MagicMock()
    status_property.json_value.return_value = status
    element_property = MagicMock()
    element_property.as_element.return_value = element
    result.get_property.side_effect = lambda name: (
        status_property if name == "status" else element_property
    )
    result.status_property = status_property
    result.element_property = element_property
    return result


def test_fresh_handle_is_returned_exactly_once() -> None:
    page = MagicMock()
    element = MagicMock()
    page.evaluate_handle.return_value = _handle_result("ok", element)
    handle = find_single_event_handle(page, create_single_event_plan(_snapshot()))
    assert handle is element
    page.evaluate_handle.assert_called_once()
    page.evaluate_handle.return_value.dispose.assert_called_once_with()
    element.dispose.assert_not_called()


def test_flattened_day_returns_only_mocked_event_handle() -> None:
    page = MagicMock()
    element = MagicMock()
    page.evaluate_handle.return_value = _handle_result("ok", element)
    plan = create_single_event_plan(_flattened_day_snapshot())

    handle = find_single_event_handle(page, plan)

    assert handle is element
    page.evaluate_handle.assert_called_once_with(
        single_event_module.CALENDAR_DIAGNOSIS_SCRIPT,
        {
            "column_ordinal": 1,
            "event_ordinal": 1,
            "column_count": 1,
            "event_block_counts": [1],
            "grid_layer": {
                "branch_count": 1,
                "gridcell_counts": [1],
                "direct_child_counts": [0],
                "descendant_counts": [0],
                "event_block_counts": [0],
                "navigation_like": False,
                "header_like": False,
                "shadowed_by_nested_equivalent_grid_anchor": False,
            },
            "event_layer": {
                "branch_count": 1,
                "gridcell_counts": [0],
                "direct_child_counts": [0],
                "descendant_counts": [0],
                "event_block_counts": [1],
                "navigation_like": False,
                "header_like": False,
                "shadowed_by_nested_equivalent_grid_anchor": False,
            },
        },
    )
    element.click.assert_not_called()


def test_atomic_handle_payload_contains_no_snapshot_local_ordinals() -> None:
    page = MagicMock()
    page.evaluate_handle.return_value = _handle_result("ok", MagicMock())

    find_single_event_handle(page, create_single_event_plan(_flattened_day_snapshot()))

    payload = page.evaluate_handle.call_args.args[1]
    assert "context_ordinal" not in payload
    assert "event_layer_ordinal" not in payload


def test_playwright_failure_during_atomic_handle_lookup_is_sanitized() -> None:
    page = MagicMock()
    page.evaluate_handle.side_effect = Error("TEST OSOBA test@example.invalid")

    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_HANDLE_NOT_FOUND$") as caught:
        find_single_event_handle(page, create_single_event_plan(_snapshot()))

    assert "TEST OSOBA" not in str(caught.value)
    assert "test@example.invalid" not in str(caught.value)


def test_failed_element_conversion_disposes_both_temporary_handles() -> None:
    page = MagicMock()
    result = _handle_result("ok")
    result.element_property.as_element.side_effect = Error("TEST DOM")
    page.evaluate_handle.return_value = result

    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_HANDLE_NOT_FOUND$"):
        find_single_event_handle(page, create_single_event_plan(_snapshot()))

    result.element_property.dispose.assert_called_once_with()
    result.dispose.assert_called_once_with()


@pytest.mark.parametrize(
    "status",
    ["SINGLE_EVENT_HANDLE_NOT_FOUND", "SINGLE_EVENT_HANDLE_AMBIGUOUS"],
)
def test_missing_or_ambiguous_handle_is_safe(status: str) -> None:
    page = MagicMock()
    page.evaluate_handle.return_value = _handle_result(status)
    with pytest.raises(SingleEventError, match=f"^{status}$"):
        find_single_event_handle(page, create_single_event_plan(_snapshot()))


def test_ok_status_without_element_is_not_accepted() -> None:
    page = MagicMock()
    page.evaluate_handle.return_value = _handle_result("ok", None)
    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_HANDLE_NOT_FOUND$"):
        find_single_event_handle(page, create_single_event_plan(_snapshot()))


def test_already_open_detail_prevents_event_click(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = MagicMock()
    monkeypatch.setattr(
        single_event_module, "find_single_event_handle", MagicMock(return_value=handle)
    )
    with pytest.raises(SingleEventError, match="^DETAIL_ALREADY_OPEN$"):
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=MagicMock(return_value=MagicMock()),
            read_snapshot=MagicMock(return_value=_snapshot()),
        )
    handle.click.assert_not_called()


def test_ambiguous_detail_precheck_prevents_event_click(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = MagicMock()
    monkeypatch.setattr(
        single_event_module, "find_single_event_handle", MagicMock(return_value=handle)
    )
    with pytest.raises(SingleEventError, match="^DETAIL_PRECHECK_AMBIGUOUS$"):
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=MagicMock(
                side_effect=ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
            ),
            read_snapshot=MagicMock(return_value=_snapshot()),
        )
    handle.click.assert_not_called()


def test_snapshot_local_layer_reordering_keeps_same_semantic_plan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle = MagicMock()
    handle_finder = MagicMock(return_value=handle)
    inspector = MagicMock(return_value=Reservation(client_name="TEST OSOBA"))
    monkeypatch.setattr(single_event_module, "find_single_event_handle", handle_finder)
    changed_ordinals = _snapshot(extra_layers=(_layer(1),))

    inspect_single_event_page(
        MagicMock(),
        timeout_seconds=3,
        find_detail=MagicMock(
            side_effect=[
                ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND"),
                MagicMock(),
            ]
        ),
        read_snapshot=MagicMock(side_effect=[_snapshot(), changed_ordinals]),
        inspect_detail=inspector,
    )

    selected_plan = handle_finder.call_args.args[1]
    assert selected_plan.event_layer_ordinal == 3
    handle.click.assert_called_once_with(timeout=3000)
    handle.dispose.assert_called_once_with()


@pytest.mark.parametrize(
    "changed",
    [
        _snapshot(3),
        _snapshot(events=(0,)),
        _snapshot(events=(2,)),
        _changed_grid_structure_snapshot(),
    ],
)
def test_meaningful_second_census_change_prevents_event_click(
    monkeypatch: pytest.MonkeyPatch,
    changed: CalendarDomSnapshot,
) -> None:
    handle_finder = MagicMock()
    monkeypatch.setattr(single_event_module, "find_single_event_handle", handle_finder)

    with pytest.raises(SingleEventError, match="^CALENDAR_STRUCTURE_CHANGED$"):
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=MagicMock(
                side_effect=ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND")
            ),
            read_snapshot=MagicMock(side_effect=[_snapshot(), changed]),
        )

    handle_finder.assert_not_called()


@pytest.mark.parametrize(
    "failure",
    [
        CalendarDiagnosisError("TEST OSOBA test@example.invalid"),
        Error("TEST OSOBA test@example.invalid"),
    ],
)
def test_initial_census_failure_is_sanitized_before_event_click(
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
) -> None:
    handle_finder = MagicMock()
    monkeypatch.setattr(single_event_module, "find_single_event_handle", handle_finder)

    with pytest.raises(SingleEventError, match="^CALENDAR_INITIAL_STRUCTURE_INVALID$"):
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=MagicMock(
                side_effect=ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND")
            ),
            read_snapshot=MagicMock(side_effect=failure),
        )

    handle_finder.assert_not_called()


def test_invalid_initial_grid_structure_has_distinct_fixed_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle_finder = MagicMock()
    monkeypatch.setattr(single_event_module, "find_single_event_handle", handle_finder)

    with pytest.raises(SingleEventError, match="^CALENDAR_INITIAL_STRUCTURE_INVALID$"):
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=MagicMock(
                side_effect=ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND")
            ),
            read_snapshot=MagicMock(return_value=_snapshot(extra_layers=(_layer(1, grid=True),))),
        )

    handle_finder.assert_not_called()


def test_event_gets_one_click_and_existing_inspector_runs_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    handle = MagicMock()
    reservation = Reservation(client_name="TEST OSOBA")
    inspector = MagicMock(return_value=reservation)
    finder = MagicMock(
        side_effect=[ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND"), MagicMock()]
    )
    monkeypatch.setattr(
        single_event_module, "find_single_event_handle", MagicMock(return_value=handle)
    )
    result = inspect_single_event_page(
        page,
        timeout_seconds=3,
        find_detail=finder,
        read_snapshot=MagicMock(return_value=_snapshot()),
        inspect_detail=inspector,
    )
    assert result is reservation
    handle.click.assert_called_once_with(timeout=3000)
    handle.dispose.assert_called_once_with()
    inspector.assert_called_once_with(page)


def test_workflow_orders_censuses_precheck_handle_click_and_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    events: list[str] = []
    detail_calls = 0

    def read_snapshot(_page: MagicMock) -> CalendarDomSnapshot:
        events.append("census")
        return _snapshot()

    def find_detail(_page: MagicMock) -> MagicMock:
        nonlocal detail_calls
        detail_calls += 1
        events.append("precheck" if detail_calls == 1 else "detail-confirmed")
        if detail_calls == 1:
            raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND")
        return MagicMock()

    handle = MagicMock()
    handle.click.side_effect = lambda **_kwargs: events.append("event-click")

    def find_handle(_page: MagicMock, _plan: object) -> MagicMock:
        events.append("atomic-handle")
        return handle

    def inspect_detail(_page: MagicMock) -> Reservation:
        events.append("inspect-detail")
        return Reservation(client_name="TEST OSOBA")

    monkeypatch.setattr(single_event_module, "find_single_event_handle", find_handle)

    inspect_single_event_page(
        page,
        timeout_seconds=3,
        read_snapshot=read_snapshot,
        find_detail=find_detail,
        inspect_detail=inspect_detail,
    )

    assert events == [
        "census",
        "precheck",
        "census",
        "atomic-handle",
        "event-click",
        "detail-confirmed",
        "inspect-detail",
    ]


def test_failed_click_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    handle = MagicMock()
    handle.click.side_effect = Error("TEST UDÁLOST")
    monkeypatch.setattr(
        single_event_module, "find_single_event_handle", MagicMock(return_value=handle)
    )
    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_CLICK_FAILED$") as caught:
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=MagicMock(
                side_effect=ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND")
            ),
            read_snapshot=MagicMock(return_value=_snapshot()),
        )
    handle.click.assert_called_once_with(timeout=3000)
    handle.dispose.assert_called_once_with()
    assert "TEST UDÁLOST" not in str(caught.value)


def test_unknown_detail_never_runs_inspector_or_unverified_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handle = MagicMock()
    inspector = MagicMock()
    finder = MagicMock(
        side_effect=[
            ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND"),
            ReservationExtractionError("unknown"),
        ]
    )
    monkeypatch.setattr(
        single_event_module, "find_single_event_handle", MagicMock(return_value=handle)
    )
    with pytest.raises(
        SingleEventError,
        match="^EVENT_DETAIL_NOT_RESERVATION_OR_UNSUPPORTED$",
    ):
        inspect_single_event_page(
            MagicMock(),
            timeout_seconds=3,
            find_detail=finder,
            read_snapshot=MagicMock(return_value=_snapshot()),
            inspect_detail=inspector,
            monotonic=MagicMock(side_effect=[0.0, 4.0]),
            sleep=MagicMock(),
        )
    handle.click.assert_called_once()
    handle.dispose.assert_called_once_with()
    inspector.assert_not_called()
    handle.query_selector.assert_not_called()


def test_detail_processing_failure_is_mapped_to_fixed_phase4b_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    handle = MagicMock()
    monkeypatch.setattr(
        single_event_module, "find_single_event_handle", MagicMock(return_value=handle)
    )

    with pytest.raises(SingleEventError, match="^EVENT_DETAIL_PROCESSING_FAILED$") as caught:
        inspect_single_event_page(
            page,
            timeout_seconds=3,
            find_detail=MagicMock(
                side_effect=[
                    ReservationExtractionError("DETAIL_STRUCTURE_NOT_FOUND"),
                    MagicMock(),
                ]
            ),
            read_snapshot=MagicMock(return_value=_snapshot()),
            inspect_detail=MagicMock(
                side_effect=inspection_module.InspectionError("TEST OSOBA test@example.invalid")
            ),
        )

    assert "TEST OSOBA" not in str(caught.value)
    assert "test@example.invalid" not in str(caught.value)
    handle.click.assert_called_once_with(timeout=3000)
    handle.dispose.assert_called_once_with()


def test_single_event_module_has_no_unsafe_interactions() -> None:
    source = inspect.getsource(single_event_module)
    assert source.count(".click(") == 1
    for forbidden in (
        "force=",
        "scrollIntoView",
        "scrollTo",
        "screenshot",
        "outerHTML",
        "innerHTML",
        "bounding_box",
        'get_attribute("class")',
        'get_attribute("id")',
        'get_attribute("style")',
        "query_selector",
        "locator(",
    ):
        assert forbidden not in source
    assert "blokace" not in source.lower()


def test_handle_mode_atomically_rechecks_context_grid_and_event_uniqueness() -> None:
    source = single_event_module.CALENDAR_DIAGNOSIS_SCRIPT
    assert "contexts.length !== 1" in source
    assert "gridIndexes.length !== 1" in source
    assert "eventIndexes.length !== 1" in source
    assert "item.index > gridIndexes[0].index" in source
    assert 'fail("SINGLE_EVENT_HANDLE_AMBIGUOUS")' in source
    assert "selection.context_ordinal" not in source
    assert "selection.event_layer_ordinal" not in source
    assert "const layerIndex = eventIndexes[0].index" in source
    assert "matchesLayerFingerprint(gridIndexes[0].layer, selection.grid_layer)" in source
    assert "matchesLayerFingerprint(layer, selection.event_layer)" in source


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


def test_context_closes_when_single_event_workflow_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    manager = _Manager(page)
    monkeypatch.setattr(
        single_event_module,
        "inspect_single_event_page",
        MagicMock(side_effect=SingleEventError("SINGLE_EVENT_NOT_FOUND")),
    )
    with pytest.raises(SingleEventError, match="^SINGLE_EVENT_NOT_FOUND$"):
        inspect_single_event(
            url="https://example.invalid/calendar",
            profile_dir=Path("test-profile"),
            timeout_seconds=3,
            wait_for_enter=lambda _prompt: "",
            write=MagicMock(),
            context_factory=lambda _profile, _timeout: manager,
        )
    assert manager.exited is True


def test_instruction_requires_manual_day_view_and_closed_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    manager = _Manager(page)
    write = MagicMock()
    monkeypatch.setattr(
        single_event_module,
        "inspect_single_event_page",
        MagicMock(return_value=Reservation()),
    )
    inspect_single_event(
        url="https://example.invalid/calendar",
        profile_dir=Path("test-profile"),
        timeout_seconds=3,
        wait_for_enter=lambda _prompt: "",
        write=write,
        context_factory=lambda _profile, _timeout: manager,
    )
    instruction = write.call_args.args[0]
    assert "pohled Den" in instruction
    assert "právě jednu" in instruction
    assert "neotvírejte" in instruction.lower()


def test_total_production_click_sites_are_exactly_three() -> None:
    assert inspect.getsource(inspection_module).count(".click(") == 2
    assert inspect.getsource(single_event_module).count(".click(") == 1
