# ruff: noqa: E501 -- reviewed JavaScript stays source-controlled and readable inline.
"""Browser-only candidate state and sanitized models for Phase 4C-ID0."""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Final, Literal, cast

from playwright.sync_api import Error, Page

from termino_exporter.extraction import (
    DetailStructure,
    ReservationExtractionError,
    find_detail_structure,
)

CANDIDATE_ATTRIBUTE_ALLOWLIST: Final = ("data-event-id", "data-event-key")
MAX_EVENT_ROOT_ATTRIBUTES: Final = 32
MAX_CANDIDATES: Final = 32
MAX_CANDIDATE_NAME_BYTES: Final = 64
MIN_EVENTS: Final = 2
MAX_EVENTS: Final = 10
BLOCKER_CODE: Final = "EVENT_STABLE_IDENTITY_UNKNOWN"

REJECTION_ORDER: Final = (
    "ID0_CANDIDATE_MISSING",
    "ID0_CANDIDATE_EMPTY",
    "ID0_CANDIDATE_VALUE_SHAPE_REJECTED",
    "ID0_CANDIDATE_DUPLICATED",
    "ID0_CANDIDATE_VALUE_SET_CHANGED",
)
BROWSER_FAILURE_CODES: Final = frozenset(
    {
        "ID0_BASELINE_CENSUS_FAILED",
        "ID0_MANUAL_OPEN_CENSUS_FAILED",
        "ID0_MANUAL_CLOSE_CENSUS_FAILED",
        "ID0_CENSUS_LIMIT_EXCEEDED",
        "ID0_CENSUS_TIMEOUT",
        "ID0_BASELINE_STRUCTURE_INVALID",
        "ID0_CALENDAR_STRUCTURE_CHANGED",
        "ID0_REQUIRES_DAY_VIEW",
        "ID0_EMPTY_EVENT_LAYER_UNPROVEN",
        "ID0_EVENT_COUNT_TOO_SMALL",
        "ID0_EVENT_LIMIT_EXCEEDED",
        "ID0_EVENT_COUNT_CHANGED",
        "ID0_ATTRIBUTE_LIMIT_EXCEEDED",
        "ID0_BROWSER_STATE_REGISTRATION_FAILED",
        "ID0_BROWSER_STATE_LOST",
        "ID0_INVALID_SANITIZED_PAYLOAD",
    }
)


class IdentityCandidateError(RuntimeError):
    """A fixed-code ID0 failure that never includes runtime browser data."""

    def __init__(self, code: str) -> None:
        self.code = code
        self.terminal_write_attempted = False
        super().__init__(code)


class IdentityCandidateStatus(StrEnum):
    TECHNICALLY_STABLE_UNAPPROVED = "TECHNICALLY_STABLE_UNAPPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class IdentityCandidateObservation:
    attribute_name: str
    baseline_present_all: bool
    baseline_nonempty_all: bool
    baseline_shape_all: bool
    baseline_unique: bool
    open_present_all: bool
    open_nonempty_all: bool
    open_shape_all: bool
    open_unique: bool
    close_present_all: bool
    close_nonempty_all: bool
    close_shape_all: bool
    close_unique: bool
    value_set_stable_after_manual_open: bool
    value_set_stable_after_manual_close: bool
    order_stable_after_manual_open: bool
    order_stable_after_manual_close: bool
    technically_stable: bool
    rejection_codes: tuple[str, ...]

    @property
    def status(self) -> IdentityCandidateStatus:
        return (
            IdentityCandidateStatus.TECHNICALLY_STABLE_UNAPPROVED
            if self.technically_stable
            else IdentityCandidateStatus.REJECTED
        )


@dataclass(frozen=True, slots=True)
class IdentityDomContinuityObservation:
    same_dom_node_set_after_manual_open: bool
    same_dom_node_order_after_manual_open: bool
    same_dom_node_set_after_manual_close: bool
    same_dom_node_order_after_manual_close: bool


@dataclass(frozen=True, slots=True)
class IdentityCandidateDiagnosticResult:
    terminal_code: Literal[
        "ID0_TECHNICALLY_STABLE_CANDIDATES_FOUND_UNAPPROVED",
        "ID0_NO_TECHNICALLY_STABLE_CANDIDATE",
    ]
    event_count: int
    candidate_count: int
    technically_stable_candidate_count: int
    ignored_root_attribute_count: int
    observations: tuple[IdentityCandidateObservation, ...]
    dom_continuity: IdentityDomContinuityObservation
    manual_open_acknowledged: Literal[True] = True
    manual_close_acknowledged: Literal[True] = True
    baseline_known_detail_absent_confirmed: Literal[True] = True
    manual_open_known_detail_confirmed: Literal[True] = True
    manual_close_known_detail_absent_confirmed: Literal[True] = True
    identity_approved: Literal[False] = False
    blocker_code: Literal["EVENT_STABLE_IDENTITY_UNKNOWN"] = BLOCKER_CODE
    tool_click_count: Literal[0] = 0
    candidate_values_printed: Literal[False] = False


def validate_candidate_allowlist() -> None:
    """Fail closed if the source-controlled privacy contract was edited unsafely."""
    if len(CANDIDATE_ATTRIBUTE_ALLOWLIST) != 2 or len(set(CANDIDATE_ATTRIBUTE_ALLOWLIST)) != 2:
        raise IdentityCandidateError("ID0_ATTRIBUTE_LIMIT_EXCEEDED")
    for name in CANDIDATE_ATTRIBUTE_ALLOWLIST:
        try:
            encoded = name.encode("ascii")
        except UnicodeEncodeError as error:
            raise IdentityCandidateError("ID0_ATTRIBUTE_LIMIT_EXCEEDED") from error
        if not 1 <= len(encoded) <= MAX_CANDIDATE_NAME_BYTES:
            raise IdentityCandidateError("ID0_ATTRIBUTE_LIMIT_EXCEEDED")


def new_channel_token() -> str:
    """Create the non-public routing token for one lexical browser closure."""
    return secrets.token_hex(32)


ID0_BASELINE_SCRIPT = r"""
(options) => {
  "use strict";
  const ALLOWLIST = ["data-event-id", "data-event-key"];
  const MAX_DEPTH = 12, MAX_ELEMENTS = 5000, MAX_CONTEXTS = 20, MAX_LAYERS = 20;
  const MAX_COLUMNS = 14, MAX_EVENT_DESCENDANTS = 30, MAX_ATTRIBUTES = 32;
  const fail = (code) => ({code, stage: "FAILED"});
  if (!options || typeof options !== "object" ||
      typeof options.channel_token !== "string" || !/^[0-9a-f]{64}$/.test(options.channel_token) ||
      !Array.isArray(options.candidate_names) || options.candidate_names.length !== 2 ||
      options.candidate_names[0] !== ALLOWLIST[0] || options.candidate_names[1] !== ALLOWLIST[1]) {
    return fail("ID0_BROWSER_STATE_REGISTRATION_FAILED");
  }
  const eventType = "termino-exporter:id0:" + options.channel_token;
  const visible = (element) => {
    let current = element;
    for (let depth = 0; current && depth <= MAX_DEPTH; depth += 1) {
      const style = window.getComputedStyle(current);
      if (style.display === "none" || style.visibility === "hidden" ||
          style.visibility === "collapse") return false;
      if (current === document.body) return true;
      current = current.parentElement;
    }
    return false;
  };
  const directVisibleChildren = (element) => Array.from(element.children).filter(visible);
  const underNavigation = (element) => {
    let current = element;
    for (let depth = 0; current && depth < 6; depth += 1) {
      if (current.tagName.toLowerCase() === "nav" || current.getAttribute("role") === "navigation")
        return true;
      current = current.parentElement;
    }
    return false;
  };
  const WEEKDAYS = new Set(["po", "út", "st", "čt", "pá", "so", "ne"]);
  const parseHeader = (element) => {
    const privateText = typeof element.innerText === "string" ?
      element.innerText.trim().toLocaleLowerCase("cs-CZ") : "";
    const match = privateText.match(/^(po|út|st|čt|pá|so|ne)\s+([1-9]|[12][0-9]|3[01])\.?$/u);
    return match !== null && WEEKDAYS.has(match[1]);
  };
  const resolve = () => {
    const censusStarted = performance.now();
    const cpuExpired = () => performance.now() - censusStarted > 3000;
    const records = [], queue = [{element: document.body, depth: 0}];
    while (queue.length) {
      if (cpuExpired()) return {code: "ID0_CENSUS_TIMEOUT"};
      const current = queue.shift();
      if (!current || records.length >= MAX_ELEMENTS) break;
      records.push(current);
      if (current.depth < MAX_DEPTH) for (const child of current.element.children)
        queue.push({element: child, depth: current.depth + 1});
    }
    if (records.length >= MAX_ELEMENTS) return {code: "ID0_CENSUS_LIMIT_EXCEEDED"};
    const all = records.map((record) => record.element);
    const descendantsOf = (element) => all.filter((candidate) =>
      candidate !== element && element.contains(candidate));
    const hasNonemptyDirectText = (element) => Array.from(element.childNodes).some((node) =>
      node.nodeType === Node.TEXT_NODE && (node.nodeValue || "").trim().length > 0);
    const excluded = new Set(["input", "option", "path", "select", "svg", "textarea"]);
    const isEventBlock = (element) => {
      if (!visible(element) || excluded.has(element.tagName.toLowerCase()) ||
          element.getAttribute("role") === "gridcell" || underNavigation(element) ||
          element.children.length > 10) return false;
      const descendants = descendantsOf(element);
      if (descendants.length > MAX_EVENT_DESCENDANTS) return false;
      return hasNonemptyDirectText(element) ||
        (typeof element.innerText === "string" && element.innerText.trim().length > 0);
    };
    const blocksForBranch = (branch) => {
      const direct = directVisibleChildren(branch).filter(isEventBlock);
      if (direct.length !== 1) return direct;
      const wrapper = direct[0], nested = directVisibleChildren(wrapper).filter(isEventBlock);
      if (!hasNonemptyDirectText(wrapper) && nested.length &&
          nested.every((block) => block.children.length > 0)) return nested;
      return direct;
    };
    const layerElements = all.filter((element) => {
      const count = directVisibleChildren(element).length;
      return count >= 1 && count <= MAX_COLUMNS;
    });
    const anchors = layerElements.map((element) => {
      const branches = directVisibleChildren(element);
      const gridcells = branches.map((branch) => descendantsOf(branch).filter((candidate) =>
        visible(candidate) && candidate.getAttribute("role") === "gridcell"));
      return {element, branches, gridcells};
    }).filter((anchor) => !underNavigation(anchor.element) &&
      anchor.gridcells.every((matches) => matches.length === 1));
    if (anchors.length > MAX_CONTEXTS * MAX_LAYERS) return {code: "ID0_CENSUS_LIMIT_EXCEEDED"};
    const nestedEquivalent = (outer, inner) => outer !== inner &&
      outer.element.contains(inner.element) && outer.branches.length === inner.branches.length &&
      outer.gridcells.every((matches, index) => matches[0] === inner.gridcells[index][0]);
    const canonicals = anchors.filter((outer) => !anchors.some((inner) => nestedEquivalent(outer, inner)));
    const definitions = [];
    for (const canonical of canonicals) {
      let root = canonical.element.parentElement;
      if (!root) continue;
      let current = root;
      for (let depth = 0; current && depth <= 4; depth += 1) {
        const siblings = directVisibleChildren(current);
        const indexes = siblings.map((element, index) => ({element, index})).filter((item) =>
          item.element === canonical.element || item.element.contains(canonical.element));
        if (indexes.length === 1 && siblings.slice(indexes[0].index + 1).some((element) =>
          directVisibleChildren(element).length === canonical.branches.length)) { root = current; break; }
        current = current.parentElement;
      }
      const existing = definitions.find((item) => item.root === root);
      if (existing) existing.canonicals.push(canonical); else definitions.push({root, canonicals: [canonical]});
    }
    if (definitions.length !== 1) return {code: "ID0_BASELINE_STRUCTURE_INVALID"};
    const definition = definitions[0], root = definition.root;
    const rootCandidates = directVisibleChildren(root).filter((element) => {
      const count = directVisibleChildren(element).length; return count >= 1 && count <= MAX_COLUMNS;
    });
    const candidates = rootCandidates.flatMap((element) => {
      const contained = definition.canonicals.filter((canonical) =>
        element === canonical.element || element.contains(canonical.element));
      return contained.length === 1 ? [contained[0].element] : [element];
    });
    if (candidates.length > MAX_LAYERS) return {code: "ID0_CENSUS_LIMIT_EXCEEDED"};
    const layers = candidates.map((element) => {
      const branches = directVisibleChildren(element);
      const headerLike = branches.every((branch) =>
        [branch, ...descendantsOf(branch)].filter(parseHeader).length === 1);
      return {element, branches,
        branch_count: branches.length,
        gridcell_counts: branches.map((branch) => descendantsOf(branch).filter((candidate) =>
          visible(candidate) && candidate.getAttribute("role") === "gridcell").length),
        direct_child_counts: branches.map((branch) => branch.children.length),
        descendant_counts: branches.map((branch) => descendantsOf(branch).length),
        event_block_counts: branches.map((branch) => blocksForBranch(branch).length),
        navigation_like: underNavigation(element),
        header_like: headerLike,
        shadowed_by_nested_equivalent_grid_anchor: false,
      };
    });
    const grids = layers.map((layer, index) => ({layer, index})).filter((item) =>
      item.layer.gridcell_counts.every((count) => count === 1));
    if (grids.length !== 1) return {code: "ID0_BASELINE_STRUCTURE_INVALID"};
    const grid = grids[0];
    if (grid.layer.branch_count !== 1) return {code: "ID0_REQUIRES_DAY_VIEW"};
    const events = layers.map((layer, index) => ({layer, index})).filter((item) =>
      item.index > grid.index && item.layer.branch_count === 1 &&
      item.layer.gridcell_counts.every((count) => count === 0) &&
      !item.layer.navigation_like && item.layer.event_block_counts[0] > 0);
    if (!events.length) return {code: "ID0_EMPTY_EVENT_LAYER_UNPROVEN"};
    if (events.length !== 1) return {code: "ID0_BASELINE_STRUCTURE_INVALID"};
    const eventLayer = events[0].layer, eventRoots = blocksForBranch(eventLayer.branches[0]);
    const attributeLimitExceeded = eventRoots.some(
      (rootElement) => rootElement.attributes.length > MAX_ATTRIBUTES);
    const projectLayer = (layer) => ({branch_count: layer.branch_count,
      gridcell_counts: layer.gridcell_counts.map(Number),
      direct_child_counts: layer.direct_child_counts.map(Number),
      descendant_counts: layer.descendant_counts.map(Number),
      event_block_counts: layer.event_block_counts.map(Number),
      navigation_like: Boolean(layer.navigation_like), header_like: Boolean(layer.header_like),
      shadowed_by_nested_equivalent_grid_anchor:
        Boolean(layer.shadowed_by_nested_equivalent_grid_anchor)});
    return {code: "OK", eventRoots, event_count: eventRoots.length,
      attribute_limit_exceeded: attributeLimitExceeded,
      fingerprint: JSON.stringify({grid: projectLayer(grid.layer), event: projectLayer(eventLayer)}),
      ignored: eventRoots.reduce((sum, element) => sum + element.attributes.length -
        ALLOWLIST.filter((name) => element.hasAttribute(name)).length, 0)};
  };
  const inspect = (roots, name) => {
    const present = roots.map((root) => root.hasAttribute(name));
    const values = roots.map((root) => root.getAttribute(name));
    const presentAll = present.every(Boolean);
    const emptySeen = values.some((value) => typeof value === "string" && value.length === 0);
    const nonemptyAll = presentAll && !emptySeen;
    const validShape = (value) => typeof value === "string" && value.length >= 1 &&
      value.length <= 128 && value === value.trim() &&
      /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(value);
    const shapeRejectedSeen = values.some((value) => typeof value === "string" &&
      value.length > 0 && !validShape(value));
    const shapeAll = presentAll && values.every(validShape);
    const duplicatedSeen = presentAll && new Set(values).size !== values.length;
    const unique = presentAll && !duplicatedSeen;
    return {values, presentAll, nonemptyAll, shapeAll, unique, emptySeen,
      shapeRejectedSeen, duplicatedSeen};
  };
  try {
    const baseline = resolve();
    if (baseline.code !== "OK") return fail(baseline.code);
    if (baseline.event_count < 2) return fail("ID0_EVENT_COUNT_TOO_SMALL");
    if (baseline.event_count > 10) return fail("ID0_EVENT_LIMIT_EXCEEDED");
    if (baseline.attribute_limit_exceeded) return fail("ID0_ATTRIBUTE_LIMIT_EXCEEDED");
    let baselineValues = Object.create(null), observations = Object.create(null);
    for (const name of ALLOWLIST) {
      const item = inspect(baseline.eventRoots, name);
      baselineValues[name] = item.values;
      observations[name] = {baseline_present_all: item.presentAll,
        baseline_nonempty_all: item.nonemptyAll, baseline_shape_all: item.shapeAll,
        baseline_unique: item.unique, missing_seen: !item.presentAll,
        empty_seen: item.emptySeen, shape_rejected_seen: item.shapeRejectedSeen,
        duplicated_seen: item.duplicatedSeen, set_changed_seen: false};
    }
    let baselineNodes = new WeakMap();
    baseline.eventRoots.forEach((element, index) => baselineNodes.set(element, index));
    baseline.eventRoots = null;
    let stage = "BASELINE_REGISTERED";
    const publicBaseline = {code: "ID0_BASELINE_REGISTERED", stage,
      event_count: baseline.event_count, candidate_count: 2,
      ignored_root_attribute_count: baseline.ignored,
      candidates: ALLOWLIST.map((name) => ({attribute_name: name,
        present_all: observations[name].baseline_present_all,
        nonempty_all: observations[name].baseline_nonempty_all,
        shape_all: observations[name].baseline_shape_all,
        unique: observations[name].baseline_unique}))};
    const listener = (event) => {
      if (!event || event.__id0Handled === true || typeof event.__id0Command !== "string") return;
      event.__id0Handled = true;
      if (event.__id0Command === "CLEAR") {
        baselineValues = null; observations = null; baselineNodes = null; stage = "CLEARED";
        window.removeEventListener(eventType, listener);
        event.__id0Response = {code: "ID0_PRIVATE_STATE_CLEARED", cleared: true};
        return;
      }
      const wanted = event.__id0Command === "OPEN_CENSUS" ? "BASELINE_REGISTERED" :
        event.__id0Command === "CLOSE_CENSUS" ? "OPEN_CENSUS_DONE" : "INVALID";
      if (stage !== wanted || baselineValues === null || observations === null || baselineNodes === null) {
        event.__id0Response = {code: "ID0_BROWSER_STATE_LOST", stage: "FAILED"}; return;
      }
      try {
        const fresh = resolve();
        if (fresh.code !== "OK") {
          const structureCodes = new Set(["ID0_BASELINE_STRUCTURE_INVALID", "ID0_REQUIRES_DAY_VIEW",
            "ID0_EMPTY_EVENT_LAYER_UNPROVEN"]);
          event.__id0Response = {code: structureCodes.has(fresh.code) ?
            "ID0_CALENDAR_STRUCTURE_CHANGED" : fresh.code, stage: "FAILED"}; return;
        }
        if (fresh.event_count !== baseline.event_count) {
          event.__id0Response = {code: "ID0_EVENT_COUNT_CHANGED", stage: "FAILED"}; return;
        }
        if (fresh.fingerprint !== baseline.fingerprint) {
          event.__id0Response = {code: "ID0_CALENDAR_STRUCTURE_CHANGED", stage: "FAILED"}; return;
        }
        if (fresh.attribute_limit_exceeded) {
          event.__id0Response = {code: "ID0_ATTRIBUTE_LIMIT_EXCEEDED", stage: "FAILED"}; return;
        }
        const suffix = event.__id0Command === "OPEN_CENSUS" ? "open" : "close";
        const positions = fresh.eventRoots.map((element) => baselineNodes.get(element));
        const nodeSet = positions.every((value) => Number.isInteger(value)) &&
          new Set(positions).size === baseline.event_count;
        const nodeOrder = nodeSet && positions.every((value, index) => value === index);
        for (const name of ALLOWLIST) {
          const item = inspect(fresh.eventRoots, name), base = baselineValues[name];
          const setComparable = item.presentAll && observations[name].baseline_present_all;
          const currentSet = new Set(item.values), baselineSet = new Set(base);
          const setStable = setComparable && currentSet.size === baselineSet.size &&
            Array.from(currentSet).every((value) => baselineSet.has(value));
          const orderStable = setStable && item.values.length === base.length &&
            item.values.every((value, index) => value === base[index]);
          observations[name][suffix + "_present_all"] = item.presentAll;
          observations[name][suffix + "_nonempty_all"] = item.nonemptyAll;
          observations[name][suffix + "_shape_all"] = item.shapeAll;
          observations[name][suffix + "_unique"] = item.unique;
          observations[name][suffix + "_value_set_stable"] = setStable;
          observations[name][suffix + "_order_stable"] = orderStable;
          observations[name].missing_seen ||= !item.presentAll;
          observations[name].empty_seen ||= item.emptySeen;
          observations[name].shape_rejected_seen ||= item.shapeRejectedSeen;
          observations[name].duplicated_seen ||= item.duplicatedSeen;
          observations[name].set_changed_seen ||= setComparable && !setStable;
          item.values = null;
        }
        stage = suffix === "open" ? "OPEN_CENSUS_DONE" : "CLOSE_CENSUS_DONE";
        if (suffix === "open") {
          event.__id0Response = {code: "ID0_OPEN_CENSUS_OK", stage,
            event_count: fresh.event_count, same_dom_node_set: nodeSet,
            same_dom_node_order: nodeOrder};
        } else {
          const candidates = ALLOWLIST.map((name) => {
            const item = observations[name], rejection_codes = [];
            if (item.missing_seen)
              rejection_codes.push("ID0_CANDIDATE_MISSING");
            if (item.empty_seen)
              rejection_codes.push("ID0_CANDIDATE_EMPTY");
            if (item.shape_rejected_seen)
              rejection_codes.push("ID0_CANDIDATE_VALUE_SHAPE_REJECTED");
            if (item.duplicated_seen)
              rejection_codes.push("ID0_CANDIDATE_DUPLICATED");
            if (item.set_changed_seen)
              rejection_codes.push("ID0_CANDIDATE_VALUE_SET_CHANGED");
            return {attribute_name: name,
              baseline_present_all: item.baseline_present_all,
              baseline_nonempty_all: item.baseline_nonempty_all,
              baseline_shape_all: item.baseline_shape_all, baseline_unique: item.baseline_unique,
              open_present_all: item.open_present_all, open_nonempty_all: item.open_nonempty_all,
              open_shape_all: item.open_shape_all, open_unique: item.open_unique,
              close_present_all: item.close_present_all, close_nonempty_all: item.close_nonempty_all,
              close_shape_all: item.close_shape_all, close_unique: item.close_unique,
              value_set_stable_after_manual_open: item.open_value_set_stable,
              value_set_stable_after_manual_close: item.close_value_set_stable,
              order_stable_after_manual_open: item.open_order_stable,
              order_stable_after_manual_close: item.close_order_stable,
              technically_stable: rejection_codes.length === 0, rejection_codes};
          });
          event.__id0Response = {code: "ID0_CLOSE_CENSUS_OK", stage,
            event_count: fresh.event_count, candidate_count: 2,
            ignored_root_attribute_count: fresh.ignored, candidates,
            same_dom_node_set: nodeSet, same_dom_node_order: nodeOrder};
        }
      } catch (_) {
        event.__id0Response = {code: event.__id0Command === "OPEN_CENSUS" ?
          "ID0_MANUAL_OPEN_CENSUS_FAILED" : "ID0_MANUAL_CLOSE_CENSUS_FAILED", stage: "FAILED"};
      }
    };
    window.addEventListener(eventType, listener);
    return publicBaseline;
  } catch (_) { return fail("ID0_BASELINE_CENSUS_FAILED"); }
}
"""

ID0_COMMAND_SCRIPT = r"""
(options) => {
  "use strict";
  try {
    if (!options || typeof options.channel_token !== "string" ||
        !/^[0-9a-f]{64}$/.test(options.channel_token) ||
        !["OPEN_CENSUS", "CLOSE_CENSUS", "CLEAR"].includes(options.command))
      return {code: "ID0_BROWSER_STATE_LOST", stage: "FAILED"};
    const event = new Event("termino-exporter:id0:" + options.channel_token);
    Object.defineProperty(event, "__id0Command", {value: options.command});
    window.dispatchEvent(event);
    if (event.__id0Handled !== true || !event.__id0Response ||
        typeof event.__id0Response !== "object")
      return {code: "ID0_BROWSER_STATE_LOST", stage: "FAILED"};
    const response = event.__id0Response;
    event.__id0Response = null;
    return response;
  } catch (_) { return {code: "ID0_BROWSER_STATE_LOST", stage: "FAILED"}; }
}
"""


def register_private_state(page: Page, channel_token: str) -> object:
    """Create browser-only raw state and return only its sanitized projection."""
    validate_candidate_allowlist()
    try:
        return page.evaluate(
            ID0_BASELINE_SCRIPT,
            {
                "channel_token": channel_token,
                "candidate_names": list(CANDIDATE_ATTRIBUTE_ALLOWLIST),
            },
        )
    except Error as error:
        raise IdentityCandidateError("ID0_BASELINE_CENSUS_FAILED") from error


def private_state_command(page: Page, channel_token: str, command: str) -> object:
    """Dispatch one fixed command without creating a candidate-state JSHandle."""
    if command not in {"OPEN_CENSUS", "CLOSE_CENSUS", "CLEAR"}:
        raise IdentityCandidateError("ID0_BROWSER_STATE_LOST")
    try:
        return page.evaluate(
            ID0_COMMAND_SCRIPT, {"channel_token": channel_token, "command": command}
        )
    except Error as error:
        raise IdentityCandidateError("ID0_BROWSER_STATE_LOST") from error


def known_detail_state(page: Page) -> str:
    """Resolve and immediately dispose one supported detail without extracting it."""
    structure: DetailStructure | None = None
    try:
        structure = find_detail_structure(page)
        return "KNOWN_DETAIL_PRESENT"
    except ReservationExtractionError as error:
        if error.code == "DETAIL_STRUCTURE_NOT_FOUND":
            return "KNOWN_DETAIL_ABSENT"
        return "UNKNOWN_OR_AMBIGUOUS"
    except Error as error:
        raise IdentityCandidateError("ID0_DETAIL_CHECK_FAILED") from error
    finally:
        if structure is not None:
            structure.dispose()


def _exact_mapping(value: object, keys: set[str]) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError
    return value


def _boolean(value: object) -> bool:
    if not isinstance(value, bool):
        raise ValueError
    return value


def deserialize_final_observation(payload: object) -> IdentityCandidateObservation:
    """Validate one candidate projection, accepting no runtime-discovered name."""
    keys = {
        "attribute_name",
        "baseline_present_all",
        "baseline_nonempty_all",
        "baseline_shape_all",
        "baseline_unique",
        "open_present_all",
        "open_nonempty_all",
        "open_shape_all",
        "open_unique",
        "close_present_all",
        "close_nonempty_all",
        "close_shape_all",
        "close_unique",
        "value_set_stable_after_manual_open",
        "value_set_stable_after_manual_close",
        "order_stable_after_manual_open",
        "order_stable_after_manual_close",
        "technically_stable",
        "rejection_codes",
    }
    try:
        item = _exact_mapping(payload, keys)
        name = item["attribute_name"]
        if name not in CANDIDATE_ATTRIBUTE_ALLOWLIST:
            raise ValueError
        raw_rejections = item["rejection_codes"]
        if not isinstance(raw_rejections, list) or any(
            code not in REJECTION_ORDER for code in raw_rejections
        ):
            raise ValueError
        rejections = tuple(raw_rejections)
        if rejections != tuple(code for code in REJECTION_ORDER if code in rejections):
            raise ValueError
        boolean_keys = keys - {"attribute_name", "rejection_codes"}
        values = {key: _boolean(item[key]) for key in boolean_keys}
        if values["technically_stable"] != (not rejections):
            raise ValueError
        return IdentityCandidateObservation(
            attribute_name=name, rejection_codes=rejections, **values
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD") from error


def sanitize_browser_projection(payload: object, stage: str) -> dict[str, object]:
    """Validate and explicitly re-project browser data before it enters worker IPC."""
    try:
        if (
            isinstance(payload, Mapping)
            and set(payload) == {"code", "stage"}
            and payload.get("stage") == "FAILED"
            and payload.get("code") in BROWSER_FAILURE_CODES
        ):
            return {"code": cast(str, payload["code"]), "stage": "FAILED"}
        if stage == "baseline":
            item = _exact_mapping(
                payload,
                {
                    "code",
                    "stage",
                    "event_count",
                    "candidate_count",
                    "ignored_root_attribute_count",
                    "candidates",
                },
            )
            expected_code, expected_stage = "ID0_BASELINE_REGISTERED", "BASELINE_REGISTERED"
        elif stage == "open":
            item = _exact_mapping(
                payload,
                {"code", "stage", "event_count", "same_dom_node_set", "same_dom_node_order"},
            )
            expected_code, expected_stage = "ID0_OPEN_CENSUS_OK", "OPEN_CENSUS_DONE"
        elif stage == "close":
            item = _exact_mapping(
                payload,
                {
                    "code",
                    "stage",
                    "event_count",
                    "candidate_count",
                    "ignored_root_attribute_count",
                    "candidates",
                    "same_dom_node_set",
                    "same_dom_node_order",
                },
            )
            expected_code, expected_stage = "ID0_CLOSE_CENSUS_OK", "CLOSE_CENSUS_DONE"
        else:
            raise ValueError
        event_count = item["event_count"]
        if (
            item["code"] != expected_code
            or item["stage"] != expected_stage
            or not isinstance(event_count, int)
            or isinstance(event_count, bool)
            or not MIN_EVENTS <= event_count <= MAX_EVENTS
        ):
            raise ValueError
        if stage == "open":
            return {
                "code": expected_code,
                "stage": expected_stage,
                "event_count": event_count,
                "same_dom_node_set": _boolean(item["same_dom_node_set"]),
                "same_dom_node_order": _boolean(item["same_dom_node_order"]),
            }
        candidates = item["candidates"]
        ignored = item["ignored_root_attribute_count"]
        if (
            item["candidate_count"] != 2
            or not isinstance(candidates, list)
            or len(candidates) != 2
            or not isinstance(ignored, int)
            or isinstance(ignored, bool)
            or not 0 <= ignored <= 320
        ):
            raise ValueError
        if stage == "baseline":
            projected_candidates = []
            for expected_name, raw in zip(CANDIDATE_ATTRIBUTE_ALLOWLIST, candidates, strict=True):
                candidate = _exact_mapping(
                    raw,
                    {"attribute_name", "present_all", "nonempty_all", "shape_all", "unique"},
                )
                if candidate["attribute_name"] != expected_name:
                    raise ValueError
                projected_candidates.append(
                    {
                        "attribute_name": expected_name,
                        "present_all": _boolean(candidate["present_all"]),
                        "nonempty_all": _boolean(candidate["nonempty_all"]),
                        "shape_all": _boolean(candidate["shape_all"]),
                        "unique": _boolean(candidate["unique"]),
                    }
                )
        else:
            observations = tuple(deserialize_final_observation(raw) for raw in candidates)
            if (
                tuple(value.attribute_name for value in observations)
                != CANDIDATE_ATTRIBUTE_ALLOWLIST
            ):
                raise ValueError
            projected_candidates = [
                {
                    "attribute_name": value.attribute_name,
                    "baseline_present_all": value.baseline_present_all,
                    "baseline_nonempty_all": value.baseline_nonempty_all,
                    "baseline_shape_all": value.baseline_shape_all,
                    "baseline_unique": value.baseline_unique,
                    "open_present_all": value.open_present_all,
                    "open_nonempty_all": value.open_nonempty_all,
                    "open_shape_all": value.open_shape_all,
                    "open_unique": value.open_unique,
                    "close_present_all": value.close_present_all,
                    "close_nonempty_all": value.close_nonempty_all,
                    "close_shape_all": value.close_shape_all,
                    "close_unique": value.close_unique,
                    "value_set_stable_after_manual_open": value.value_set_stable_after_manual_open,
                    "value_set_stable_after_manual_close": value.value_set_stable_after_manual_close,
                    "order_stable_after_manual_open": value.order_stable_after_manual_open,
                    "order_stable_after_manual_close": value.order_stable_after_manual_close,
                    "technically_stable": value.technically_stable,
                    "rejection_codes": list(value.rejection_codes),
                }
                for value in observations
            ]
        result = {
            "code": expected_code,
            "stage": expected_stage,
            "event_count": event_count,
            "candidate_count": 2,
            "ignored_root_attribute_count": ignored,
            "candidates": projected_candidates,
        }
        if stage == "close":
            result["same_dom_node_set"] = _boolean(item["same_dom_node_set"])
            result["same_dom_node_order"] = _boolean(item["same_dom_node_order"])
        return result
    except IdentityCandidateError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD") from error


def deserialize_final_result(
    baseline_payload: object,
    open_payload: object,
    close_payload: object,
) -> IdentityCandidateDiagnosticResult:
    """Build the immutable result only from exact sanitized browser projections."""
    try:
        baseline_payload = sanitize_browser_projection(baseline_payload, "baseline")
        open_payload = sanitize_browser_projection(open_payload, "open")
        close_payload = sanitize_browser_projection(close_payload, "close")
        baseline = _exact_mapping(
            baseline_payload,
            {
                "code",
                "stage",
                "event_count",
                "candidate_count",
                "ignored_root_attribute_count",
                "candidates",
            },
        )
        opened = _exact_mapping(
            open_payload,
            {
                "code",
                "stage",
                "event_count",
                "same_dom_node_set",
                "same_dom_node_order",
            },
        )
        closed = _exact_mapping(
            close_payload,
            {
                "code",
                "stage",
                "event_count",
                "candidate_count",
                "ignored_root_attribute_count",
                "candidates",
                "same_dom_node_set",
                "same_dom_node_order",
            },
        )
        if (
            baseline["code"] != "ID0_BASELINE_REGISTERED"
            or baseline["stage"] != "BASELINE_REGISTERED"
        ):
            raise ValueError
        if opened["code"] != "ID0_OPEN_CENSUS_OK" or opened["stage"] != "OPEN_CENSUS_DONE":
            raise ValueError
        if closed["code"] != "ID0_CLOSE_CENSUS_OK" or closed["stage"] != "CLOSE_CENSUS_DONE":
            raise ValueError
        event_count = baseline["event_count"]
        if (
            not isinstance(event_count, int)
            or isinstance(event_count, bool)
            or not MIN_EVENTS <= event_count <= MAX_EVENTS
            or opened["event_count"] != event_count
            or closed["event_count"] != event_count
            or baseline["candidate_count"] != 2
            or closed["candidate_count"] != 2
        ):
            raise ValueError
        raw_candidates = closed["candidates"]
        if not isinstance(raw_candidates, list) or len(raw_candidates) != 2:
            raise ValueError
        observations = tuple(deserialize_final_observation(item) for item in raw_candidates)
        if tuple(item.attribute_name for item in observations) != CANDIDATE_ATTRIBUTE_ALLOWLIST:
            raise ValueError
        ignored = closed["ignored_root_attribute_count"]
        if not isinstance(ignored, int) or isinstance(ignored, bool) or not 0 <= ignored <= 320:
            raise ValueError
        continuity = IdentityDomContinuityObservation(
            same_dom_node_set_after_manual_open=_boolean(opened["same_dom_node_set"]),
            same_dom_node_order_after_manual_open=_boolean(opened["same_dom_node_order"]),
            same_dom_node_set_after_manual_close=_boolean(closed["same_dom_node_set"]),
            same_dom_node_order_after_manual_close=_boolean(closed["same_dom_node_order"]),
        )
        stable_count = sum(item.technically_stable for item in observations)
        terminal: Literal[
            "ID0_TECHNICALLY_STABLE_CANDIDATES_FOUND_UNAPPROVED",
            "ID0_NO_TECHNICALLY_STABLE_CANDIDATE",
        ] = (
            "ID0_TECHNICALLY_STABLE_CANDIDATES_FOUND_UNAPPROVED"
            if stable_count
            else "ID0_NO_TECHNICALLY_STABLE_CANDIDATE"
        )
        return IdentityCandidateDiagnosticResult(
            terminal_code=terminal,
            event_count=event_count,
            candidate_count=2,
            technically_stable_candidate_count=stable_count,
            ignored_root_attribute_count=ignored,
            observations=observations,
            dom_continuity=continuity,
        )
    except IdentityCandidateError:
        raise
    except (KeyError, TypeError, ValueError) as error:
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD") from error


def fixed_browser_code(payload: object) -> str:
    """Read only a fixed code from a browser payload without reflecting it."""
    if not isinstance(payload, Mapping) or not isinstance(payload.get("code"), str):
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    code = cast(str, payload["code"])
    if not code.startswith("ID0_") or len(code) > 64 or not code.isascii():
        raise IdentityCandidateError("ID0_INVALID_SANITIZED_PAYLOAD")
    return code
