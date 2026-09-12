from __future__ import annotations

import dataclasses
import inspect
from dataclasses import FrozenInstanceError

import pytest
from playwright.sync_api import ElementHandle, JSHandle

import termino_exporter.day_plan as day_plan_module
from termino_exporter.calendar_diagnosis import (
    CalendarContextSnapshot,
    CalendarDiagnosisError,
    CalendarDomSnapshot,
    CalendarLayerSnapshot,
)
from termino_exporter.day_plan import (
    DayPlanError,
    DaySelectionPlan,
    DayStructureFingerprint,
    EventSelectionTarget,
    create_day_selection_plan,
)


def _layer(
    columns: int,
    *,
    grid: bool = False,
    events: tuple[int, ...] | None = None,
    shadowed: bool = False,
) -> CalendarLayerSnapshot:
    zeros = (0,) * columns
    event_counts = zeros if events is None else events
    return CalendarLayerSnapshot(
        branch_count=columns,
        gridcell_counts=(1,) * columns if grid else zeros,
        direct_child_counts=event_counts,
        descendant_counts=event_counts,
        event_block_counts=event_counts,
        navigation_like=False,
        header_like=False,
        shadowed_by_nested_equivalent_grid_anchor=shadowed,
    )


def _snapshot(
    event_count: int,
    *,
    columns: int = 1,
    extra_layers: tuple[CalendarLayerSnapshot, ...] = (),
) -> CalendarDomSnapshot:
    event_counts = (event_count,) + (0,) * (columns - 1)
    return CalendarDomSnapshot(
        (
            CalendarContextSnapshot(
                (_layer(columns, grid=True), *extra_layers, _layer(columns, events=event_counts))
            ),
        ),
        (),
    )


@pytest.mark.parametrize("event_count", [1, 2, 3, 10])
def test_supported_event_counts_create_finite_baseline_plan(event_count: int) -> None:
    plan = create_day_selection_plan(_snapshot(event_count))

    assert plan.event_count == event_count
    assert plan.event_limit == 10
    assert plan.contract_version == "PHASE4C1"
    assert tuple(target.baseline_ordinal for target in plan.targets) == tuple(
        range(1, event_count + 1)
    )
    assert all(target.day_fingerprint is plan.fingerprint for target in plan.targets)


def test_empty_or_unproven_event_layer_is_rejected() -> None:
    with pytest.raises(DayPlanError, match="^DAY_EMPTY_EVENT_LAYER_UNPROVEN$"):
        create_day_selection_plan(_snapshot(0))


def test_eleven_events_exceed_day_limit() -> None:
    with pytest.raises(DayPlanError, match="^DAY_EVENT_LIMIT_EXCEEDED$"):
        create_day_selection_plan(_snapshot(11))


@pytest.mark.parametrize("columns", [3, 7])
def test_non_day_view_is_rejected(columns: int) -> None:
    with pytest.raises(DayPlanError, match="^DAY_REQUIRES_DAY_VIEW$"):
        create_day_selection_plan(_snapshot(1, columns=columns))


@pytest.mark.parametrize(
    "snapshot",
    [
        CalendarDomSnapshot((_snapshot(1).contexts[0], _snapshot(1).contexts[0]), ()),
        _snapshot(1, extra_layers=(_layer(1, grid=True),)),
        _snapshot(1, extra_layers=(_layer(1, events=(1,)),)),
    ],
)
def test_ambiguous_structure_is_rejected(snapshot: CalendarDomSnapshot) -> None:
    with pytest.raises(DayPlanError, match="^DAY_CALENDAR_STRUCTURE_CHANGED$"):
        create_day_selection_plan(snapshot)


def test_plan_target_and_fingerprint_are_deeply_immutable() -> None:
    plan = create_day_selection_plan(_snapshot(2))

    with pytest.raises(FrozenInstanceError):
        plan.contract_version = "CHANGED"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.targets[0].baseline_ordinal = 9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.fingerprint.event_count = 9  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.fingerprint.grid_layer.branch_count = 9  # type: ignore[misc]


def test_plan_and_targets_never_contain_playwright_handles() -> None:
    plan = create_day_selection_plan(_snapshot(3))
    values = (
        *dataclasses.astuple(plan.fingerprint),
        *(dataclasses.astuple(target) for target in plan.targets),
    )

    assert not any(isinstance(value, (ElementHandle, JSHandle)) for value in values)
    assert all("handle" not in field.name for field in dataclasses.fields(DaySelectionPlan))
    assert all("handle" not in field.name for field in dataclasses.fields(EventSelectionTarget))


def test_fingerprint_contains_only_anonymous_aggregate_structure() -> None:
    fingerprint = create_day_selection_plan(_snapshot(2)).fingerprint

    assert isinstance(fingerprint, DayStructureFingerprint)
    assert fingerprint.column_count == 1
    assert fingerprint.event_count == 2
    assert fingerprint.event_layer.event_block_counts == (2,)
    assert all(
        "text" not in field.name
        and "attribute" not in field.name
        and "key" not in field.name
        and "handle" not in field.name
        for model in (DayStructureFingerprint, type(fingerprint.event_layer))
        for field in dataclasses.fields(model)
    )


def test_errors_are_fixed_sanitized_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    private_error = CalendarDiagnosisError("TEST UDÁLOST PRIVATE")
    monkeypatch.setattr(
        day_plan_module,
        "resolve_calendar_snapshot",
        lambda _snapshot: (_ for _ in ()).throw(private_error),
    )

    with pytest.raises(DayPlanError) as caught:
        create_day_selection_plan(_snapshot(1))

    assert str(caught.value) == "DAY_CALENDAR_STRUCTURE_CHANGED"
    assert "TEST" not in str(caught.value)
    assert caught.value.__cause__ is private_error


def test_target_ordinal_is_explicitly_baseline_only_not_persistent_identity() -> None:
    field_names = {field.name for field in dataclasses.fields(EventSelectionTarget)}
    documentation = inspect.getdoc(EventSelectionTarget) or ""

    assert field_names == {"baseline_ordinal", "day_fingerprint"}
    assert "Baseline-only" in documentation
    assert "never a stable event identity across censuses" in documentation
    assert "stable_event_key" not in inspect.getsource(day_plan_module)


def test_day_plan_module_has_no_browser_interactions_or_live_resolver() -> None:
    source = inspect.getsource(day_plan_module)

    assert ".click(" not in source
    assert "evaluate_handle" not in source
    assert "ElementHandle" not in source
    assert "JSHandle" not in source
