"""Safely open and process exactly one event in a manually selected day view."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from playwright.sync_api import BrowserContext, ElementHandle, Error, JSHandle, Page

from termino_exporter.browser import persistent_browser_context
from termino_exporter.calendar_diagnosis import (
    CALENDAR_DIAGNOSIS_SCRIPT,
    CalendarDiagnosisError,
    CalendarDomSnapshot,
    CalendarLayerSnapshot,
    read_calendar_snapshot,
    resolve_calendar_snapshot,
)
from termino_exporter.extraction import (
    DetailStructure,
    ReservationExtractionError,
    find_detail_structure,
)
from termino_exporter.inspection import InspectionError, inspect_open_detail
from termino_exporter.models import Reservation

ContextFactory = Callable[[Path, float], AbstractContextManager[BrowserContext]]
OutputWriter = Callable[[str], None]
WaitForEnter = Callable[[str], str]
SnapshotReader = Callable[[Page], CalendarDomSnapshot]
DetailFinder = Callable[[Page], DetailStructure]
DetailInspector = Callable[[Page], Reservation]
MonotonicClock = Callable[[], float]
Sleep = Callable[[float], None]

DETAIL_OPEN_TIMEOUT_SECONDS = 3.0
DETAIL_POLL_INTERVAL_SECONDS = 0.05
EVENT_CLICK_TIMEOUT_MS = 3_000


class SingleEventError(RuntimeError):
    """Expected safe failure while selecting one calendar event."""


@dataclass(frozen=True, slots=True)
class SingleEventLayerFingerprint:
    """Anonymous numeric and boolean structure of one selected calendar layer."""

    branch_count: int
    gridcell_counts: tuple[int, ...]
    direct_child_counts: tuple[int, ...]
    descendant_counts: tuple[int, ...]
    event_block_counts: tuple[int, ...]
    navigation_like: bool
    header_like: bool
    shadowed_by_nested_equivalent_grid_anchor: bool


@dataclass(frozen=True, slots=True)
class SingleEventStructureFingerprint:
    """Meaning-level structure shared safely between independent censuses."""

    column_count: Literal[1]
    event_block_counts: tuple[int, ...]
    grid_layer: SingleEventLayerFingerprint
    event_layer: SingleEventLayerFingerprint


@dataclass(frozen=True, slots=True)
class SingleEventSelectionPlan:
    context_ordinal: int
    event_layer_ordinal: int
    column_ordinal: Literal[1]
    event_ordinal: Literal[1]
    column_count: Literal[1]
    event_block_counts: tuple[int, ...]
    fingerprint: SingleEventStructureFingerprint


def _is_event_layer(layer: CalendarLayerSnapshot, column_count: int) -> bool:
    return (
        layer.branch_count == column_count
        and not any(layer.gridcell_counts)
        and not layer.navigation_like
        and not layer.header_like
        and sum(layer.event_block_counts) > 0
    )


def _layer_fingerprint(layer: CalendarLayerSnapshot) -> SingleEventLayerFingerprint:
    return SingleEventLayerFingerprint(
        branch_count=layer.branch_count,
        gridcell_counts=layer.gridcell_counts,
        direct_child_counts=layer.direct_child_counts,
        descendant_counts=layer.descendant_counts,
        event_block_counts=layer.event_block_counts,
        navigation_like=layer.navigation_like,
        header_like=layer.header_like,
        shadowed_by_nested_equivalent_grid_anchor=(layer.shadowed_by_nested_equivalent_grid_anchor),
    )


def create_single_event_plan(snapshot: CalendarDomSnapshot) -> SingleEventSelectionPlan:
    """Create an immutable one-event plan from a validated anonymous snapshot."""
    if len(snapshot.contexts) != 1:
        raise SingleEventError("CALENDAR_STRUCTURE_CHANGED")
    try:
        diagnosis = resolve_calendar_snapshot(snapshot)
    except CalendarDiagnosisError as error:
        code = (
            "SINGLE_EVENT_NOT_FOUND"
            if str(error) == "EVENT_LAYER_EMPTY_OR_NOT_FOUND"
            else "CALENDAR_STRUCTURE_CHANGED"
        )
        raise SingleEventError(code) from error
    if diagnosis.column_count != 1:
        raise SingleEventError("SINGLE_EVENT_REQUIRES_DAY_VIEW")
    event_count = diagnosis.columns[0].event_block_count
    if event_count == 0:
        raise SingleEventError("SINGLE_EVENT_NOT_FOUND")
    if event_count != 1:
        raise SingleEventError("SINGLE_EVENT_NOT_UNIQUE")

    context = snapshot.contexts[0]
    grid_layers = [
        (index, layer)
        for index, layer in enumerate(context.layers, start=1)
        if not layer.shadowed_by_nested_equivalent_grid_anchor
        and all(value == 1 for value in layer.gridcell_counts)
    ]
    if len(grid_layers) != 1:
        raise SingleEventError("CALENDAR_STRUCTURE_CHANGED")
    grid_ordinal, grid_layer = grid_layers[0]
    event_layers = [
        (index, layer)
        for index, layer in enumerate(context.layers, start=1)
        if index > grid_ordinal and layer is not grid_layer and _is_event_layer(layer, 1)
    ]
    if len(event_layers) != 1:
        raise SingleEventError("CALENDAR_STRUCTURE_CHANGED")
    event_ordinal, event_layer = event_layers[0]
    fingerprint = SingleEventStructureFingerprint(
        column_count=1,
        event_block_counts=(1,),
        grid_layer=_layer_fingerprint(grid_layer),
        event_layer=_layer_fingerprint(event_layer),
    )
    return SingleEventSelectionPlan(
        context_ordinal=1,
        event_layer_ordinal=event_ordinal,
        column_ordinal=1,
        event_ordinal=1,
        column_count=1,
        event_block_counts=(1,),
        fingerprint=fingerprint,
    )


def _plan_payload(plan: SingleEventSelectionPlan) -> dict[str, object]:
    def layer_payload(layer: SingleEventLayerFingerprint) -> dict[str, object]:
        return {
            "branch_count": layer.branch_count,
            "gridcell_counts": list(layer.gridcell_counts),
            "direct_child_counts": list(layer.direct_child_counts),
            "descendant_counts": list(layer.descendant_counts),
            "event_block_counts": list(layer.event_block_counts),
            "navigation_like": layer.navigation_like,
            "header_like": layer.header_like,
            "shadowed_by_nested_equivalent_grid_anchor": (
                layer.shadowed_by_nested_equivalent_grid_anchor
            ),
        }

    return {
        "column_ordinal": plan.column_ordinal,
        "event_ordinal": plan.event_ordinal,
        "column_count": plan.column_count,
        "event_block_counts": list(plan.event_block_counts),
        "grid_layer": layer_payload(plan.fingerprint.grid_layer),
        "event_layer": layer_payload(plan.fingerprint.event_layer),
    }


def _property_value(handle: JSHandle, name: str) -> object:
    property_handle = handle.get_property(name)
    try:
        return property_handle.json_value()
    finally:
        property_handle.dispose()


def _dispose_handle(handle: JSHandle | None) -> None:
    if handle is None:
        return
    try:
        handle.dispose()
    except Error:
        pass


def find_single_event_handle(page: Page, plan: SingleEventSelectionPlan) -> ElementHandle:
    """Re-run bounded DOM rules and return exactly one fresh event element."""
    result: JSHandle | None = None
    element_property: JSHandle | None = None
    try:
        result = page.evaluate_handle(CALENDAR_DIAGNOSIS_SCRIPT, _plan_payload(plan))
        status = _property_value(result, "status")
        if status in {
            "CALENDAR_STRUCTURE_CHANGED",
            "SINGLE_EVENT_HANDLE_NOT_FOUND",
            "SINGLE_EVENT_HANDLE_AMBIGUOUS",
        }:
            raise SingleEventError(str(status))
        if status != "ok":
            raise SingleEventError("SINGLE_EVENT_HANDLE_NOT_FOUND")
        element_property = result.get_property("element")
        element = element_property.as_element()
        if element is None:
            raise SingleEventError("SINGLE_EVENT_HANDLE_NOT_FOUND")
        element_property = None  # Ownership is transferred to the caller as ElementHandle.
        return element
    except Error as error:
        raise SingleEventError("SINGLE_EVENT_HANDLE_NOT_FOUND") from error
    finally:
        _dispose_handle(element_property)
        _dispose_handle(result)


def _ensure_detail_closed(page: Page, find_detail: DetailFinder) -> None:
    try:
        find_detail(page)
    except ReservationExtractionError as error:
        if error.code == "DETAIL_STRUCTURE_NOT_FOUND":
            return
        raise SingleEventError("DETAIL_PRECHECK_AMBIGUOUS") from error
    except Error as error:
        raise SingleEventError("DETAIL_PRECHECK_FAILED") from error
    raise SingleEventError("DETAIL_ALREADY_OPEN")


def _wait_for_known_detail(
    page: Page,
    find_detail: DetailFinder,
    *,
    timeout_seconds: float,
    monotonic: MonotonicClock,
    sleep: Sleep,
) -> None:
    deadline = monotonic() + min(timeout_seconds, DETAIL_OPEN_TIMEOUT_SECONDS)
    while True:
        try:
            find_detail(page)
            return
        except ReservationExtractionError:
            pass
        except Error as error:
            raise SingleEventError("EVENT_DETAIL_NOT_RESERVATION_OR_UNSUPPORTED") from error
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise SingleEventError("EVENT_DETAIL_NOT_RESERVATION_OR_UNSUPPORTED")
        sleep(min(DETAIL_POLL_INTERVAL_SECONDS, remaining))


def inspect_single_event_page(
    page: Page,
    *,
    timeout_seconds: float,
    read_snapshot: SnapshotReader = read_calendar_snapshot,
    find_detail: DetailFinder = find_detail_structure,
    inspect_detail: DetailInspector = inspect_open_detail,
    monotonic: MonotonicClock = time.monotonic,
    sleep: Sleep = time.sleep,
) -> Reservation:
    """Open one structurally verified event and reuse the existing detail processor."""
    try:
        plan = create_single_event_plan(read_snapshot(page))
    except (CalendarDiagnosisError, Error) as error:
        raise SingleEventError("CALENDAR_INITIAL_STRUCTURE_INVALID") from error
    except SingleEventError as error:
        if str(error) == "CALENDAR_STRUCTURE_CHANGED":
            raise SingleEventError("CALENDAR_INITIAL_STRUCTURE_INVALID") from error
        raise
    _ensure_detail_closed(page, find_detail)
    try:
        fresh_plan = create_single_event_plan(read_snapshot(page))
    except (CalendarDiagnosisError, Error, SingleEventError) as error:
        raise SingleEventError("CALENDAR_STRUCTURE_CHANGED") from error
    if fresh_plan.fingerprint != plan.fingerprint:
        raise SingleEventError("CALENDAR_STRUCTURE_CHANGED")
    event_handle = find_single_event_handle(page, fresh_plan)
    try:
        event_handle.click(timeout=min(timeout_seconds * 1_000, EVENT_CLICK_TIMEOUT_MS))
    except Error as error:
        raise SingleEventError("SINGLE_EVENT_CLICK_FAILED") from error
    finally:
        _dispose_handle(event_handle)
    _wait_for_known_detail(
        page,
        find_detail,
        timeout_seconds=timeout_seconds,
        monotonic=monotonic,
        sleep=sleep,
    )
    try:
        return inspect_detail(page)
    except InspectionError as error:
        raise SingleEventError("EVENT_DETAIL_PROCESSING_FAILED") from error


def inspect_single_event(
    *,
    url: str,
    profile_dir: Path,
    timeout_seconds: float,
    wait_for_enter: WaitForEnter = input,
    write: OutputWriter = print,
    context_factory: ContextFactory = persistent_browser_context,
) -> Reservation:
    """Run the one-event read-only workflow in an always-closed browser context."""
    with context_factory(profile_dir, timeout_seconds) as context:
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url)
        except Error as error:
            raise SingleEventError("CALENDAR_OPEN_FAILED") from error
        write(
            "V prohlížeči se ručně přihlaste, ručně zvolte pohled Den a ručně přejděte "
            "na datum obsahující právě jednu zjevně testovací klientskou rezervaci. "
            "Detail rezervace neotvírejte."
        )
        wait_for_enter("Potom se vraťte do terminálu a stiskněte Enter...")
        return inspect_single_event_page(page, timeout_seconds=timeout_seconds)
