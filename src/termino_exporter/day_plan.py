"""Build an immutable anonymous no-click plan for one calendar day."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from termino_exporter.calendar_diagnosis import (
    CalendarDiagnosisError,
    CalendarDomSnapshot,
    CalendarLayerSnapshot,
    resolve_calendar_snapshot,
)

DAY_EVENT_LIMIT = 10
DAY_PLAN_CONTRACT_VERSION = "PHASE4C1"


class DayPlanError(RuntimeError):
    """Expected safe failure while creating a no-click day plan."""


@dataclass(frozen=True, slots=True)
class LayerStructureFingerprint:
    """Anonymous aggregate numeric and boolean structure of one calendar layer."""

    branch_count: int
    gridcell_counts: tuple[int, ...]
    direct_child_counts: tuple[int, ...]
    descendant_counts: tuple[int, ...]
    event_block_counts: tuple[int, ...]
    navigation_like: bool
    header_like: bool
    shadowed_by_nested_equivalent_grid_anchor: bool


@dataclass(frozen=True, slots=True)
class DayStructureFingerprint:
    """Anonymous aggregate structure of one baseline day census."""

    column_count: Literal[1]
    event_count: int
    grid_layer: LayerStructureFingerprint
    event_layer: LayerStructureFingerprint


@dataclass(frozen=True, slots=True)
class EventSelectionTarget:
    """Baseline-only position; never a stable event identity across censuses."""

    baseline_ordinal: int
    day_fingerprint: DayStructureFingerprint = field(repr=False)


@dataclass(frozen=True, slots=True)
class DaySelectionPlan:
    """Finite no-click Phase 4C1 plan derived from one validated baseline census."""

    fingerprint: DayStructureFingerprint
    targets: tuple[EventSelectionTarget, ...] = field(repr=False)
    event_limit: int = DAY_EVENT_LIMIT
    contract_version: str = DAY_PLAN_CONTRACT_VERSION

    @property
    def event_count(self) -> int:
        return len(self.targets)


def layer_structure_fingerprint(layer: CalendarLayerSnapshot) -> LayerStructureFingerprint:
    """Copy only bounded anonymous structural values from a census layer."""
    return LayerStructureFingerprint(
        branch_count=layer.branch_count,
        gridcell_counts=layer.gridcell_counts,
        direct_child_counts=layer.direct_child_counts,
        descendant_counts=layer.descendant_counts,
        event_block_counts=layer.event_block_counts,
        navigation_like=layer.navigation_like,
        header_like=layer.header_like,
        shadowed_by_nested_equivalent_grid_anchor=(layer.shadowed_by_nested_equivalent_grid_anchor),
    )


def _is_event_layer(layer: CalendarLayerSnapshot, column_count: int) -> bool:
    return (
        layer.branch_count == column_count
        and not any(layer.gridcell_counts)
        and not layer.navigation_like
        and not layer.header_like
        and sum(layer.event_block_counts) > 0
    )


def create_day_selection_plan(snapshot: CalendarDomSnapshot) -> DaySelectionPlan:
    """Create a Phase 4C1 plan without obtaining handles or interacting with a page."""
    if len(snapshot.contexts) != 1:
        raise DayPlanError("DAY_CALENDAR_STRUCTURE_CHANGED")
    try:
        diagnosis = resolve_calendar_snapshot(snapshot)
    except CalendarDiagnosisError as error:
        code = (
            "DAY_EMPTY_EVENT_LAYER_UNPROVEN"
            if str(error) == "EVENT_LAYER_EMPTY_OR_NOT_FOUND"
            else "DAY_CALENDAR_STRUCTURE_CHANGED"
        )
        raise DayPlanError(code) from error

    if diagnosis.column_count != 1:
        raise DayPlanError("DAY_REQUIRES_DAY_VIEW")
    event_count = diagnosis.columns[0].event_block_count
    if event_count == 0:
        raise DayPlanError("DAY_EMPTY_EVENT_LAYER_UNPROVEN")
    if event_count > DAY_EVENT_LIMIT:
        raise DayPlanError("DAY_EVENT_LIMIT_EXCEEDED")

    context = snapshot.contexts[0]
    grid_layers = [
        (index, layer)
        for index, layer in enumerate(context.layers)
        if not layer.shadowed_by_nested_equivalent_grid_anchor
        and all(value == 1 for value in layer.gridcell_counts)
    ]
    if len(grid_layers) != 1:
        raise DayPlanError("DAY_CALENDAR_STRUCTURE_CHANGED")
    grid_index, grid_layer = grid_layers[0]
    event_layers = [
        layer
        for index, layer in enumerate(context.layers)
        if index > grid_index and layer is not grid_layer and _is_event_layer(layer, 1)
    ]
    if len(event_layers) != 1:
        raise DayPlanError("DAY_CALENDAR_STRUCTURE_CHANGED")

    fingerprint = DayStructureFingerprint(
        column_count=1,
        event_count=event_count,
        grid_layer=layer_structure_fingerprint(grid_layer),
        event_layer=layer_structure_fingerprint(event_layers[0]),
    )
    targets = tuple(
        EventSelectionTarget(baseline_ordinal=ordinal, day_fingerprint=fingerprint)
        for ordinal in range(1, event_count + 1)
    )
    return DaySelectionPlan(fingerprint=fingerprint, targets=targets)
