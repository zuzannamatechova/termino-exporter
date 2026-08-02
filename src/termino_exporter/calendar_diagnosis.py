"""Read-only structural diagnosis of parallel Termino calendar layers."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, TypedDict

from playwright.sync_api import BrowserContext, Error, Page

from termino_exporter.browser import persistent_browser_context

ContextFactory = Callable[[Path, float], AbstractContextManager[BrowserContext]]
OutputWriter = Callable[[str], None]
WaitForEnter = Callable[[str], str]

MAX_DOM_DEPTH = 12
MAX_DOM_ELEMENTS = 5_000
MAX_CONTEXTS = 20
MAX_LAYERS = 20
MAX_COLUMNS = 14
MAX_EVENT_DESCENDANTS = 30

CALENDAR_DIAGNOSIS_SCRIPT = r"""
() => {
  const MAX_DEPTH = 12;
  const MAX_ELEMENTS = 5000;
  const MAX_CONTEXTS = 20;
  const MAX_LAYERS = 20;
  const MAX_COLUMNS = 14;
  const MAX_COMMON_ANCESTORS = 4;
  const MAX_EVENT_DESCENDANTS = 30;
  const EXCLUDED_BLOCK_TAGS = new Set([
    "input", "option", "path", "select", "svg", "textarea"
  ]);
  const WEEKDAYS = new Map([
    ["po", 0], ["út", 1], ["st", 2], ["čt", 3], ["pá", 4], ["so", 5], ["ne", 6]
  ]);

  const visible = (element) => {
    let current = element;
    for (let depth = 0; current && depth <= MAX_DEPTH; depth += 1) {
      const presentation = window.getComputedStyle(current);
      if (presentation.display === "none" || presentation.visibility === "hidden") return false;
      if (current === document.body) return true;
      current = current.parentElement;
    }
    return false;
  };
  const exactRole = (element, role) => element.getAttribute("role") === role;
  const underNavigation = (element) => {
    let current = element;
    for (let depth = 0; current && depth < 6; depth += 1) {
      if (current.tagName.toLowerCase() === "nav" ||
          current.getAttribute("role") === "navigation") return true;
      current = current.parentElement;
    }
    return false;
  };
  const parseHeader = (element) => {
    const privateText = typeof element.innerText === "string" ?
      element.innerText.trim().toLocaleLowerCase("cs-CZ") : "";
    const match = privateText.match(/^(po|út|st|čt|pá|so|ne)\s+([1-9]|[12][0-9]|3[01])\.?$/u);
    if (!match) return null;
    return {weekday_index: WEEKDAYS.get(match[1]), day_number: Number(match[2])};
  };
  const directVisibleChildren = (element) => Array.from(element.children).filter(visible);

  const records = [];
  const queue = [{element: document.body, depth: 0}];
  while (queue.length) {
    const current = queue.shift();
    if (!current || records.length >= MAX_ELEMENTS) break;
    records.push(current);
    if (current.depth >= MAX_DEPTH) continue;
    for (const child of current.element.children) {
      queue.push({element: child, depth: current.depth + 1});
    }
  }
  if (records.length >= MAX_ELEMENTS) return {error: "CALENDAR_DIAG_LIMIT_EXCEEDED"};
  const all = records.map((record) => record.element);
  const descendantsOf = (element) => all.filter((candidate) =>
    candidate !== element && element.contains(candidate)
  );
  const hasNonemptyDirectText = (element) => Array.from(element.childNodes).some((node) =>
    node.nodeType === Node.TEXT_NODE && (node.nodeValue || "").trim().length > 0
  );
  const isEventBlock = (element) => {
    const tag = element.tagName.toLowerCase();
    if (!visible(element) || EXCLUDED_BLOCK_TAGS.has(tag) || exactRole(element, "gridcell") ||
        underNavigation(element) || element.children.length > 10) return false;
    const descendants = descendantsOf(element);
    if (descendants.length > MAX_EVENT_DESCENDANTS) return false;
    return hasNonemptyDirectText(element) ||
      (typeof element.innerText === "string" && element.innerText.trim().length > 0);
  };
  const blocksForBranch = (branch) => {
    const direct = directVisibleChildren(branch).filter(isEventBlock);
    if (direct.length !== 1) return direct;
    const possibleWrapper = direct[0];
    const nested = directVisibleChildren(possibleWrapper).filter(isEventBlock);
    if (!hasNonemptyDirectText(possibleWrapper) && nested.length &&
        nested.every((block) => block.children.length > 0)) return nested;
    return direct;
  };

  const layerElements = all.filter((element) => {
    const count = directVisibleChildren(element).length;
    return count >= 1 && count <= MAX_COLUMNS;
  });
  const gridAnchors = layerElements.filter((element) => {
    const branches = directVisibleChildren(element);
    return !underNavigation(element) && branches.every((branch) =>
      descendantsOf(branch).filter((candidate) =>
        visible(candidate) && exactRole(candidate, "gridcell")
      ).length === 1
    );
  });
  if (!gridAnchors.length) return {contexts: [], header_groups: []};

  const contextRoots = [];
  for (const anchor of gridAnchors) {
    const root = anchor.parentElement;
    if (!root) continue;
    if (!contextRoots.includes(root)) contextRoots.push(root);
  }
  if (contextRoots.length > MAX_CONTEXTS) return {error: "CALENDAR_DIAG_LIMIT_EXCEEDED"};

  const contexts = [];
  for (const root of contextRoots) {
    const candidates = directVisibleChildren(root).filter((element) => {
      const count = directVisibleChildren(element).length;
      return count >= 1 && count <= MAX_COLUMNS;
    });
    if (candidates.length > MAX_LAYERS) return {error: "CALENDAR_DIAG_LIMIT_EXCEEDED"};
    const layers = [];
    for (const element of candidates) {
      const branches = directVisibleChildren(element);
      const gridcellCounts = branches.map((branch) =>
        descendantsOf(branch).filter((candidate) =>
          visible(candidate) && exactRole(candidate, "gridcell")
        ).length
      );
      const headerLike = branches.every((branch) =>
        [branch, ...descendantsOf(branch)].filter((candidate) => parseHeader(candidate) !== null)
          .length === 1
      );
      const eventBlockCounts = branches.map((branch) => blocksForBranch(branch).length);
      layers.push({
        branch_count: branches.length,
        gridcell_counts: gridcellCounts.map((count) => Number(count)),
        direct_child_counts: branches.map((branch) => Number(branch.children.length)),
        descendant_counts: branches.map((branch) => Number(descendantsOf(branch).length)),
        event_block_counts: eventBlockCounts.map((count) => Number(count)),
        navigation_like: Boolean(underNavigation(element)),
        header_like: Boolean(headerLike),
      });
    }
    contexts.push({layers});
  }
  const headerGroups = [];
  for (const element of layerElements) {
    const branches = directVisibleChildren(element);
    const matches = branches.map((branch) =>
      [branch, ...descendantsOf(branch)].map(parseHeader).filter((value) => value !== null)
    );
    if (!matches.every((values) => values.length === 1)) continue;
    const headers = matches.map((values) => ({
      weekday_index: Number(values[0].weekday_index),
      day_number: Number(values[0].day_number),
      header_parseable: true,
    }));
    const keys = headers.map((header) => `${header.weekday_index}:${header.day_number}`);
    headerGroups.push({
      headers,
      headers_distinct: new Set(keys).size === keys.length,
    });
  }
  if (headerGroups.length > MAX_LAYERS) return {error: "CALENDAR_DIAG_LIMIT_EXCEEDED"};
  return {
    contexts: contexts.map((context) => ({layers: context.layers})),
    header_groups: headerGroups.map((group) => ({
      headers: group.headers.map((header) => ({
        weekday_index: header.weekday_index,
        day_number: header.day_number,
        header_parseable: header.header_parseable,
      })),
      headers_distinct: group.headers_distinct,
    })),
  };
}
"""


class CalendarDiagnosisError(RuntimeError):
    """Safe expected failure of calendar layer diagnosis."""


class RawCalendarLayerSnapshot(TypedDict):
    branch_count: int
    gridcell_counts: list[int]
    direct_child_counts: list[int]
    descendant_counts: list[int]
    event_block_counts: list[int]
    navigation_like: bool
    header_like: bool


class RawCalendarContextSnapshot(TypedDict):
    layers: list[RawCalendarLayerSnapshot]


class RawCalendarHeaderSnapshot(TypedDict):
    weekday_index: int | None
    day_number: int | None
    header_parseable: bool


class RawCalendarHeaderGroupSnapshot(TypedDict):
    headers: list[RawCalendarHeaderSnapshot]
    headers_distinct: bool


class RawCalendarDomSnapshot(TypedDict):
    contexts: list[RawCalendarContextSnapshot]
    header_groups: list[RawCalendarHeaderGroupSnapshot]


@dataclass(frozen=True, slots=True)
class CalendarLayerSnapshot:
    branch_count: int
    gridcell_counts: tuple[int, ...]
    direct_child_counts: tuple[int, ...]
    descendant_counts: tuple[int, ...]
    event_block_counts: tuple[int, ...]
    navigation_like: bool
    header_like: bool


@dataclass(frozen=True, slots=True)
class CalendarContextSnapshot:
    layers: tuple[CalendarLayerSnapshot, ...]


@dataclass(frozen=True, slots=True)
class CalendarHeaderSnapshot:
    weekday_index: int | None
    day_number: int | None
    header_parseable: bool


@dataclass(frozen=True, slots=True)
class CalendarHeaderGroupSnapshot:
    headers: tuple[CalendarHeaderSnapshot, ...]
    headers_distinct: bool


@dataclass(frozen=True, slots=True)
class CalendarDomSnapshot:
    contexts: tuple[CalendarContextSnapshot, ...]
    header_groups: tuple[CalendarHeaderGroupSnapshot, ...]


@dataclass(frozen=True, slots=True)
class CalendarDayColumnDiagnosis:
    ordinal: int
    weekday_index: int | None
    day_number: int | None
    gridcell_present: bool
    event_block_count: int


@dataclass(frozen=True, slots=True)
class CalendarLayerDiagnosis:
    mode: Literal["CALENDAR_LAYERS_FOUND", "CALENDAR_LAYERS_FOUND_HEADERS_UNRESOLVED"]
    column_count: int
    headers_resolved: bool
    headers_distinct: bool
    gridcell_layer_found: bool
    event_layer_found: bool
    columns: tuple[CalendarDayColumnDiagnosis, ...]
    click_count: Literal[0]


def _bounded_int(value: object, maximum: int, *, minimum: int = 0) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise ValueError
    return value


def _int_tuple(value: object, length: int, maximum: int = MAX_DOM_ELEMENTS) -> tuple[int, ...]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError
    return tuple(_bounded_int(item, maximum) for item in value)


def _layer(payload: object) -> CalendarLayerSnapshot:
    if not isinstance(payload, Mapping):
        raise ValueError
    branch_count = _bounded_int(payload.get("branch_count"), MAX_COLUMNS, minimum=1)
    if not isinstance(payload.get("navigation_like"), bool) or not isinstance(
        payload.get("header_like"), bool
    ):
        raise ValueError
    return CalendarLayerSnapshot(
        branch_count=branch_count,
        gridcell_counts=_int_tuple(payload.get("gridcell_counts"), branch_count),
        direct_child_counts=_int_tuple(payload.get("direct_child_counts"), branch_count),
        descendant_counts=_int_tuple(payload.get("descendant_counts"), branch_count),
        event_block_counts=_int_tuple(payload.get("event_block_counts"), branch_count),
        navigation_like=payload["navigation_like"],
        header_like=payload["header_like"],
    )


def _header(payload: object) -> CalendarHeaderSnapshot:
    if not isinstance(payload, Mapping) or not isinstance(payload.get("header_parseable"), bool):
        raise ValueError
    parseable = payload["header_parseable"]
    weekday = payload.get("weekday_index")
    day_number = payload.get("day_number")
    if parseable:
        weekday = _bounded_int(weekday, 6)
        day_number = _bounded_int(day_number, 31, minimum=1)
    elif weekday is not None or day_number is not None:
        raise ValueError
    return CalendarHeaderSnapshot(weekday, day_number, parseable)


def deserialize_calendar_snapshot(payload: object) -> CalendarDomSnapshot:
    """Validate a census payload without including its representation in failures."""
    try:
        if not isinstance(payload, Mapping):
            raise ValueError
        if payload.get("error") is not None:
            if payload.get("error") == "CALENDAR_DIAG_LIMIT_EXCEEDED":
                raise CalendarDiagnosisError("CALENDAR_DIAG_LIMIT_EXCEEDED")
            raise ValueError
        raw_contexts = payload.get("contexts")
        raw_groups = payload.get("header_groups")
        if not isinstance(raw_contexts, list) or not isinstance(raw_groups, list):
            raise ValueError
        if len(raw_contexts) > MAX_CONTEXTS or len(raw_groups) > MAX_LAYERS:
            raise CalendarDiagnosisError("CALENDAR_DIAG_LIMIT_EXCEEDED")
        contexts = []
        for raw_context in raw_contexts:
            if not isinstance(raw_context, Mapping) or not isinstance(
                raw_context.get("layers"), list
            ):
                raise ValueError
            if len(raw_context["layers"]) > MAX_LAYERS:
                raise CalendarDiagnosisError("CALENDAR_DIAG_LIMIT_EXCEEDED")
            contexts.append(
                CalendarContextSnapshot(tuple(_layer(layer) for layer in raw_context["layers"]))
            )
        groups = []
        for raw_group in raw_groups:
            if (
                not isinstance(raw_group, Mapping)
                or not isinstance(raw_group.get("headers"), list)
                or not isinstance(raw_group.get("headers_distinct"), bool)
            ):
                raise ValueError
            if len(raw_group["headers"]) > MAX_COLUMNS:
                raise CalendarDiagnosisError("CALENDAR_DIAG_LIMIT_EXCEEDED")
            groups.append(
                CalendarHeaderGroupSnapshot(
                    tuple(_header(header) for header in raw_group["headers"]),
                    raw_group["headers_distinct"],
                )
            )
        return CalendarDomSnapshot(tuple(contexts), tuple(groups))
    except CalendarDiagnosisError:
        raise
    except (TypeError, ValueError) as error:
        raise CalendarDiagnosisError("CALENDAR_DIAG_INVALID_SNAPSHOT") from error


def _is_grid_layer(layer: CalendarLayerSnapshot) -> bool:
    return all(count == 1 for count in layer.gridcell_counts)


def _validate_snapshot_model(snapshot: CalendarDomSnapshot) -> None:
    try:
        if len(snapshot.contexts) > MAX_CONTEXTS or len(snapshot.header_groups) > MAX_LAYERS:
            raise CalendarDiagnosisError("CALENDAR_DIAG_LIMIT_EXCEEDED")
        for context in snapshot.contexts:
            if len(context.layers) > MAX_LAYERS:
                raise CalendarDiagnosisError("CALENDAR_DIAG_LIMIT_EXCEEDED")
            for layer in context.layers:
                count = _bounded_int(layer.branch_count, MAX_COLUMNS, minimum=1)
                for values in (
                    layer.gridcell_counts,
                    layer.direct_child_counts,
                    layer.descendant_counts,
                    layer.event_block_counts,
                ):
                    if len(values) != count:
                        raise ValueError
                    for value in values:
                        _bounded_int(value, MAX_DOM_ELEMENTS)
                if not isinstance(layer.navigation_like, bool) or not isinstance(
                    layer.header_like, bool
                ):
                    raise ValueError
        for group in snapshot.header_groups:
            if len(group.headers) > MAX_COLUMNS or not isinstance(group.headers_distinct, bool):
                raise ValueError
            for header in group.headers:
                if not isinstance(header.header_parseable, bool):
                    raise ValueError
                if header.header_parseable:
                    _bounded_int(header.weekday_index, 6)
                    _bounded_int(header.day_number, 31, minimum=1)
                elif header.weekday_index is not None or header.day_number is not None:
                    raise ValueError
    except CalendarDiagnosisError:
        raise
    except (TypeError, ValueError) as error:
        raise CalendarDiagnosisError("CALENDAR_DIAG_INVALID_SNAPSHOT") from error


def resolve_calendar_snapshot(snapshot: CalendarDomSnapshot) -> CalendarLayerDiagnosis:
    """Resolve one calendar context from a safe immutable census snapshot."""
    _validate_snapshot_model(snapshot)
    grid_candidates = [
        (context, layer)
        for context in snapshot.contexts
        for layer in context.layers
        if _is_grid_layer(layer)
    ]
    if not grid_candidates:
        raise CalendarDiagnosisError("GRIDCELL_LAYER_NOT_FOUND")
    if len(grid_candidates) != 1:
        raise CalendarDiagnosisError("GRIDCELL_LAYER_AMBIGUOUS")
    context, grid_layer = grid_candidates[0]
    column_count = grid_layer.branch_count
    event_candidates = [
        layer
        for layer in context.layers
        if layer is not grid_layer
        and layer.branch_count == column_count
        and not any(layer.gridcell_counts)
        and not layer.navigation_like
        and not layer.header_like
        and sum(layer.event_block_counts) > 0
    ]
    if not event_candidates:
        raise CalendarDiagnosisError("EVENT_LAYER_EMPTY_OR_NOT_FOUND")
    if len(event_candidates) != 1:
        raise CalendarDiagnosisError("EVENT_LAYER_AMBIGUOUS")
    event_layer = event_candidates[0]

    valid_headers = [
        group
        for group in snapshot.header_groups
        if len(group.headers) == column_count
        and group.headers_distinct
        and all(
            header.header_parseable
            and header.weekday_index is not None
            and header.day_number is not None
            for header in group.headers
        )
    ]
    headers_resolved = len(valid_headers) == 1
    headers = valid_headers[0].headers if headers_resolved else ()
    columns = tuple(
        CalendarDayColumnDiagnosis(
            ordinal=index + 1,
            weekday_index=headers[index].weekday_index if headers_resolved else None,
            day_number=headers[index].day_number if headers_resolved else None,
            gridcell_present=True,
            event_block_count=count,
        )
        for index, count in enumerate(event_layer.event_block_counts)
    )
    return CalendarLayerDiagnosis(
        mode=(
            "CALENDAR_LAYERS_FOUND"
            if headers_resolved
            else "CALENDAR_LAYERS_FOUND_HEADERS_UNRESOLVED"
        ),
        column_count=column_count,
        headers_resolved=headers_resolved,
        headers_distinct=headers_resolved,
        gridcell_layer_found=True,
        event_layer_found=True,
        columns=columns,
        click_count=0,
    )


def diagnose_calendar_structure(page: Page) -> CalendarLayerDiagnosis:
    """Read, validate and resolve the structural census for the current view."""
    try:
        payload: Any = page.evaluate(CALENDAR_DIAGNOSIS_SCRIPT)
        return resolve_calendar_snapshot(deserialize_calendar_snapshot(payload))
    except CalendarDiagnosisError:
        raise
    except Error as error:
        raise CalendarDiagnosisError("CALENDAR_DIAG_CENSUS_FAILED") from error


def _yes_no(value: bool) -> str:
    return "ano" if value else "ne"


def _view_name(column_count: int) -> str:
    return {1: "Den", 3: "3 dny", 7: "Týden"}.get(column_count, "Neurčen")


def format_calendar_diagnosis(diagnosis: CalendarLayerDiagnosis) -> str:
    """Format only validated structural calendar-layer aggregates."""
    lines = [
        "----- Diagnostika kalendáře -----",
        f"Režim: {diagnosis.mode}",
        f"Typ pohledu: {_view_name(diagnosis.column_count)}",
        f"Sloupců: {diagnosis.column_count}",
        "Gridcell vrstva nalezena: " + _yes_no(diagnosis.gridcell_layer_found),
        "Vrstva událostí nalezena: " + _yes_no(diagnosis.event_layer_found),
        "Záhlaví propojena: " + _yes_no(diagnosis.headers_resolved),
    ]
    for column in diagnosis.columns:
        weekday = column.weekday_index if column.weekday_index is not None else "Neuvedeno"
        day_number = column.day_number if column.day_number is not None else "Neuvedeno"
        lines.extend(
            [
                f"Sloupec {column.ordinal}",
                f"Den v týdnu: {weekday}",
                f"Číslo dne: {day_number}",
                "Gridcell přítomen: " + _yes_no(column.gridcell_present),
                f"Bloků událostí: {column.event_block_count}",
            ]
        )
    lines.extend(
        [
            "Události klasifikovány: ne",
            "Texty událostí vypsány: ne",
            "Hodnoty atributů vypsány: ne",
            "Kliknutí provedena: 0",
            "----- Konec diagnostiky kalendáře -----",
        ]
    )
    return "\n".join(lines)


def diagnose_calendar(
    *,
    url: str,
    profile_dir: Path,
    timeout_seconds: float,
    wait_for_enter: WaitForEnter = input,
    write: OutputWriter = print,
    context_factory: ContextFactory = persistent_browser_context,
) -> CalendarLayerDiagnosis:
    """Open a manually selected calendar view and diagnose it without interactions."""
    with context_factory(profile_dir, timeout_seconds) as context:
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url)
        except Error as error:
            raise CalendarDiagnosisError("CALENDAR_DIAG_FAILED") from error
        write(
            "V prohlížeči se ručně přihlaste a ručně přejděte na požadovaný kalendářní "
            "pohled Den, 3 dny nebo Týden. Neotvírejte detail žádné události."
        )
        wait_for_enter("Potom se vraťte do terminálu a stiskněte Enter...")
        diagnosis = diagnose_calendar_structure(page)
        write(format_calendar_diagnosis(diagnosis))
        return diagnosis
