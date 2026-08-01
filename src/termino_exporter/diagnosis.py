"""Temporary privacy-safe DOM structure diagnosis for a manually opened detail."""

import json
from collections.abc import Callable, Mapping

from playwright.sync_api import Error, Locator, Page

OutputWriter = Callable[[str], None]

MAX_MATCHES_PER_PROBE = 10
MAX_ANCESTOR_DEPTH = 6
MAX_TOTAL_RECORDS = 100

PROBES = (
    ("probe_1", "Datum"),
    ("probe_2", "Čas"),
    ("probe_3", "Upravit"),
    ("probe_4", "Odstranit"),
    ("probe_5", "Zkopírovat rezervaci"),
)
SAFE_PROBES = {probe for probe, _interface_text in PROBES}
SAFE_TAGS = {
    "div",
    "section",
    "aside",
    "main",
    "article",
    "form",
    "nav",
    "header",
    "footer",
    "dialog",
    "button",
    "span",
    "label",
}
SAFE_ROLES = {
    "dialog",
    "alertdialog",
    "region",
    "main",
    "form",
    "group",
    "document",
    "complementary",
    "navigation",
    "button",
    "none",
    "presentation",
}
SAFE_POSITIONS = {"static", "relative", "absolute", "fixed", "sticky"}
SAFE_OVERFLOWS = {"visible", "hidden", "clip", "scroll", "auto"}
DOM_STRUCTURE_SCRIPT = """
(element, maxDepth) => {
    const safeTags = new Set([
        "div", "section", "aside", "main", "article", "form", "nav",
        "header", "footer", "dialog", "button", "span", "label"
    ]);
    const safeRoles = new Set([
        "dialog", "alertdialog", "region", "main", "form", "group",
        "document", "complementary", "navigation", "button", "none", "presentation"
    ]);
    const safePositions = new Set(["static", "relative", "absolute", "fixed", "sticky"]);
    const safeOverflows = new Set(["visible", "hidden", "clip", "scroll", "auto"]);
    const result = [];
    let current = element;
    let depth = 0;
    while (current && depth <= maxDepth) {
        const computedStyle = window.getComputedStyle(current);
        const tag = current.tagName.toLowerCase();
        const role = current.getAttribute("role");
        const modal = current.getAttribute("aria-modal");
        const position = computedStyle.position;
        const overflowY = computedStyle.overflowY;
        result.push({
            depth,
            tag: safeTags.has(tag) ? tag : "other",
            role: safeRoles.has(role) ? role : null,
            ariaModal: modal === "true" ? true : (modal === "false" ? false : null),
            position: safePositions.has(position) ? position : null,
            overflowY: safeOverflows.has(overflowY) ? overflowY : null,
            visible: true,
            childCount: Math.min(Math.max(current.childElementCount, 0), 999),
            isScrollable: current.scrollHeight > current.clientHeight,
            isFixedOrAbsolute: position === "fixed" || position === "absolute",
        });
        current = current.parentElement;
        depth += 1;
    }
    return result;
}
"""


class DiagnosisError(RuntimeError):
    """The privacy-safe DOM diagnosis could not be completed."""


def _safe_enum(value: object, allowed: set[str]) -> str | None:
    return value if isinstance(value, str) and value in allowed else None


def _safe_boolean(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _safe_optional_boolean(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _safe_integer(value: object, minimum: int, maximum: int) -> int:
    if not isinstance(value, int):
        return minimum
    return min(max(value, minimum), maximum)


def _sanitize_structure(probe: str, raw: object) -> list[dict[str, object]]:
    if probe not in SAFE_PROBES or not isinstance(raw, list):
        raise DiagnosisError("Diagnostiku se nepodařilo bezpečně dokončit.")

    records: list[dict[str, object]] = []
    for item in raw[: MAX_ANCESTOR_DEPTH + 1]:
        if not isinstance(item, Mapping):
            raise DiagnosisError("Diagnostiku se nepodařilo bezpečně dokončit.")
        records.append(
            {
                "probe": probe,
                "depth": _safe_integer(item.get("depth"), 0, MAX_ANCESTOR_DEPTH),
                "tag": _safe_enum(item.get("tag"), SAFE_TAGS) or "other",
                "role": _safe_enum(item.get("role"), SAFE_ROLES),
                "aria_modal": _safe_optional_boolean(item.get("ariaModal")),
                "position": _safe_enum(item.get("position"), SAFE_POSITIONS),
                "overflow_y": _safe_enum(item.get("overflowY"), SAFE_OVERFLOWS),
                "visible": _safe_boolean(item.get("visible")),
                "child_count": _safe_integer(item.get("childCount"), 0, 999),
                "is_scrollable": _safe_boolean(item.get("isScrollable")),
                "is_fixed_or_absolute": _safe_boolean(item.get("isFixedOrAbsolute")),
            }
        )
    return records


def _visible_matches(locator: Locator) -> list[Locator]:
    matches: list[Locator] = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            matches.append(candidate)
            if len(matches) > MAX_MATCHES_PER_PROBE:
                raise DiagnosisError("Diagnostika nalezla příliš mnoho odpovídajících prvků.")
    return matches


def diagnose_dialog_structure(page: Page, write: OutputWriter = print) -> None:
    """Print only bounded allowlisted structure near safe static interface probes."""
    records: list[dict[str, object]] = []
    try:
        for probe, interface_text in PROBES:
            for match in _visible_matches(page.get_by_text(interface_text, exact=True)):
                records.extend(
                    _sanitize_structure(
                        probe,
                        match.evaluate(DOM_STRUCTURE_SCRIPT, MAX_ANCESTOR_DEPTH),
                    )
                )
                if len(records) > MAX_TOTAL_RECORDS:
                    raise DiagnosisError("Diagnostický výstup by překročil bezpečný limit.")
    except Error as error:
        raise DiagnosisError("Diagnostiku se nepodařilo bezpečně dokončit.") from error

    for record in records:
        write(json.dumps(record, ensure_ascii=False, sort_keys=True))
