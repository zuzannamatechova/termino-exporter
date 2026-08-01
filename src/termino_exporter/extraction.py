"""Safe structural extraction from one already opened Termino detail."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from playwright.sync_api import ElementHandle, Error, Locator, Page

from termino_exporter.close_diagnosis import (
    FORBIDDEN_ACTION_NAMES,
    named_visible_button_handles,
)

MAX_CONTENT_ANCESTOR_DEPTH = 10
MAX_STRUCTURE_ANCESTOR_DEPTH = 4
MAX_FIELD_ANCESTOR_DEPTH = 6
KNOWN_FIELD_LABELS = (
    "Datum",
    "Čas",
    "Služba nebo balíček",
    "Počet osob na rezervaci",
    "Cena",
    "Pracoviště",
    "Zaměstnanec",
    "Poznámka",
    "E-mail",
    "Telefon",
    "Zdroj",
    "Typ",
    "Stav rezervace",
    "Vytvořena",
)
FIND_SCROLL_CONTAINER_SCRIPT = """
(dateLabel, options) => {
    const timeLabel = options.timeLabel;
    let current = dateLabel;
    let depth = 0;
    while (current && depth <= options.maxDepth) {
        const style = window.getComputedStyle(current);
        const overflowY = style.overflowY;
        const visible = style.display !== "none" && style.visibility !== "hidden";
        if (
            visible &&
            current.contains(timeLabel) &&
            (overflowY === "auto" || overflowY === "scroll") &&
            current.scrollHeight > current.clientHeight
        ) {
            return current;
        }
        current = current.parentElement;
        depth += 1;
    }
    return null;
}
"""
PARENT_ELEMENT_SCRIPT = "(element) => element.parentElement"
ROOT_STRUCTURE_SCRIPT = """
(root, options) => {
    const branches = Array.from(root.children);
    const contentBranches = branches.filter(
        (branch) => branch === options.content || branch.contains(options.content)
    );
    const actionBranches = branches.filter(
        (branch) => options.forbiddenActions.every((action) => branch.contains(action))
    );
    if (contentBranches.length !== 1 || actionBranches.length !== 1) {
        return false;
    }
    const contentIndex = branches.indexOf(contentBranches[0]);
    const actionIndex = branches.indexOf(actionBranches[0]);
    const headerBranches = branches.filter(
        (branch, index) => index < contentIndex && branch !== actionBranches[0]
    );
    return headerBranches.length === 1 && contentIndex < actionIndex;
}
"""
BRANCH_CONTAINING_SCRIPT = """
(root, target) => {
    const matches = Array.from(root.children).filter(
        (branch) => branch === target || branch.contains(target)
    );
    return matches.length === 1 ? matches[0] : null;
}
"""
CLOSE_CONTROL_SIGNATURE_SCRIPT = """
(button, options) => {
    const branches = Array.from(options.root.children);
    const buttonBranches = branches.filter(
        (branch) => branch === button || branch.contains(button)
    );
    const contentBranches = branches.filter(
        (branch) => branch === options.content || branch.contains(options.content)
    );
    const actionBranches = branches.filter(
        (branch) => options.forbiddenActions.every((action) => branch.contains(action))
    );
    return {
        isInHeader:
            buttonBranches.length === 1 &&
            contentBranches.length === 1 &&
            actionBranches.length === 1 &&
            buttonBranches[0] !== contentBranches[0] &&
            buttonBranches[0] !== actionBranches[0] &&
            branches.indexOf(buttonBranches[0]) < branches.indexOf(contentBranches[0]),
        hasSvg: button.querySelector("svg") !== null,
        hasNonemptyTextContent: (button.textContent || "").trim().length > 0,
        isForbiddenAction: options.forbiddenActions.includes(button),
    };
}
"""
EXTRACT_CLIENT_NAME_SCRIPT = r"""
(header, closeControl) => {
    const path = [];
    let current = closeControl;
    while (current !== header) {
        const parent = current.parentElement;
        if (!parent) {
            return {status: "not-found"};
        }
        const index = Array.prototype.indexOf.call(parent.children, current);
        if (index < 0) {
            return {status: "not-found"};
        }
        path.unshift(index);
        current = parent;
    }
    const clone = header.cloneNode(true);
    let cloneControl = clone;
    for (const index of path) {
        cloneControl = cloneControl.children[index];
        if (!cloneControl) {
            return {status: "not-found"};
        }
    }
    if (cloneControl.tagName.toLowerCase() !== "button") {
        return {status: "not-found"};
    }
    cloneControl.remove();
    const text = (clone.innerText || "").replace(/\r\n?/g, "\n").trim();
    const lines = text.split("\n").map((line) => line.trim()).filter(Boolean);
    const status = lines.length === 0 ? "not-found" : (lines.length === 1 ? "ok" : "ambiguous");
    return status === "ok" ? {status, value: lines[0]} : {status};
}
"""
EXTRACT_CLEAN_TEXT_SCRIPT = r"""
(element) => {
    const clone = element.cloneNode(true);
    for (const button of clone.querySelectorAll("button")) {
        if ((button.textContent || "").trim() === "Méně") {
            button.remove();
        }
    }
    return (clone.innerText || "").replace(/\r\n?/g, "\n").trim();
}
"""
EXTRACT_FIELDS_SCRIPT = r"""
(content, options) => {
    const labels = options.labels;
    const labelSet = new Set(labels);
    const cleanCloneText = (elements) => elements.map((element) => {
        const clone = element.cloneNode(true);
        for (const button of clone.querySelectorAll("button")) {
            if ((button.textContent || "").trim() === "Méně") {
                button.remove();
            }
        }
        return clone.innerText || "";
    }).join("\n").replace(/\r\n?/g, "\n").trim();

    const candidates = [];
    for (const element of content.querySelectorAll("*")) {
        const label = (element.textContent || "").trim();
        if (!labelSet.has(label)) {
            continue;
        }
        let current = element.parentElement;
        let depth = 0;
        while (current && content.contains(current) && depth <= options.maxDepth) {
            const branches = Array.from(current.children);
            const labelBranches = branches.filter(
                (branch) => branch === element || branch.contains(element)
            );
            if (labelBranches.length === 1) {
                const labelBranch = labelBranches[0];
                const labelIndex = branches.indexOf(labelBranch);
                const following = branches.slice(labelIndex + 1);
                if (
                    (labelBranch.textContent || "").trim() === label &&
                    following.length > 0
                ) {
                    const alreadyRecorded = candidates.some(
                        (candidate) => candidate.label === label && candidate.container === current
                    );
                    if (!alreadyRecorded) {
                        candidates.push({label, element, container: current, following, depth});
                    }
                    break;
                }
            }
            current = current.parentElement;
            depth += 1;
        }
    }

    const isInsideValueOf = (inner, outer) => outer.following.some(
        (valueBranch) =>
            valueBranch === inner.container || valueBranch.contains(inner.container)
    );
    const valid = candidates.filter((candidate) => !candidates.some((other) => {
        if (other === candidate || other.container === candidate.container) {
            return false;
        }
        return isInsideValueOf(candidate, other) || isInsideValueOf(other, candidate);
    }));

    const fields = {};
    for (const label of labels) {
        const matches = valid.filter((candidate) => candidate.label === label);
        if (matches.length > 1) {
            return {status: "duplicate"};
        }
        if (matches.length === 1) {
            fields[label] = cleanCloneText(matches[0].following);
        }
    }
    return {status: "ok", fields};
}
"""


@dataclass(frozen=True, slots=True)
class DetailStructure:
    root: ElementHandle
    header_branch: ElementHandle
    content_branch: ElementHandle
    scroll_container: ElementHandle
    action_branch: ElementHandle
    close_control: ElementHandle


@dataclass(frozen=True, slots=True)
class ExtractedReservationData:
    fields: Mapping[str, str]
    client_name: str | None
    raw_detail: str


class ReservationExtractionError(RuntimeError):
    """A safe DOM extraction failure identified only by a fixed code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _visible_matches(locator: Locator) -> list[Locator]:
    matches: list[Locator] = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            matches.append(candidate)
    return matches


def _one_visible_label(page: Page, label: str) -> Locator:
    matches = _visible_matches(page.get_by_text(label, exact=True))
    if len(matches) != 1:
        raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
    return matches[0]


def find_detail_content(page: Page) -> ElementHandle:
    """Find the bounded genuinely scrollable content containing Datum and Čas."""
    try:
        date_element = _one_visible_label(page, "Datum").element_handle()
        time_element = _one_visible_label(page, "Čas").element_handle()
        if date_element is None or time_element is None:
            raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
        result_handle = date_element.evaluate_handle(
            FIND_SCROLL_CONTAINER_SCRIPT,
            {"timeLabel": time_element, "maxDepth": MAX_CONTENT_ANCESTOR_DEPTH},
        )
        content = result_handle.as_element()
        if content is None:
            result_handle.dispose()
            raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
        return content
    except Error as error:
        raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE") from error


def _branch_containing(root: ElementHandle, target: ElementHandle) -> ElementHandle:
    handle = root.evaluate_handle(BRANCH_CONTAINING_SCRIPT, target)
    branch = handle.as_element()
    if branch is None:
        handle.dispose()
        raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
    return branch


def _matches_close_control(raw: object) -> bool:
    return isinstance(raw, Mapping) and (
        raw.get("isInHeader") is True
        and raw.get("hasSvg") is True
        and raw.get("hasNonemptyTextContent") is False
        and raw.get("isForbiddenAction") is False
    )


def find_detail_structure(
    page: Page,
    content: ElementHandle | None = None,
) -> DetailStructure:
    """Find exactly one bounded HEADER-CONTENT-ACTION detail structure."""
    try:
        resolved_content = content if content is not None else find_detail_content(page)
        forbidden_actions: list[ElementHandle] = []
        for name in FORBIDDEN_ACTION_NAMES:
            matches = named_visible_button_handles(page, (name,))
            if len(matches) != 1:
                raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
            forbidden_actions.append(matches[0])

        current: ElementHandle | None = resolved_content
        structures: list[DetailStructure] = []
        saw_valid_root = False
        for depth in range(MAX_STRUCTURE_ANCESTOR_DEPTH + 1):
            if current is None:
                break
            if current.evaluate(
                ROOT_STRUCTURE_SCRIPT,
                {"content": resolved_content, "forbiddenActions": forbidden_actions},
            ):
                saw_valid_root = True
                content_branch = _branch_containing(current, resolved_content)
                action_branch = _branch_containing(current, forbidden_actions[0])
                header_candidates: list[ElementHandle] = []
                for button in current.query_selector_all("button"):
                    if not button.is_visible():
                        continue
                    signature = button.evaluate(
                        CLOSE_CONTROL_SIGNATURE_SCRIPT,
                        {
                            "root": current,
                            "content": resolved_content,
                            "forbiddenActions": forbidden_actions,
                        },
                    )
                    if not _matches_close_control(signature):
                        continue
                    header_candidates.append(button)
                if len(header_candidates) == 1:
                    close_control = header_candidates[0]
                    structures.append(
                        DetailStructure(
                            root=current,
                            header_branch=_branch_containing(current, close_control),
                            content_branch=content_branch,
                            scroll_container=resolved_content,
                            action_branch=action_branch,
                            close_control=close_control,
                        )
                    )
                elif len(header_candidates) > 1:
                    raise ReservationExtractionError("CLOSE_CONTROL_NOT_UNIQUE")
            if depth < MAX_STRUCTURE_ANCESTOR_DEPTH:
                parent_handle = current.evaluate_handle(PARENT_ELEMENT_SCRIPT)
                current = parent_handle.as_element()

        if len(structures) != 1:
            code = (
                "CLOSE_CONTROL_NOT_UNIQUE"
                if saw_valid_root and not structures
                else "DETAIL_STRUCTURE_NOT_UNIQUE"
            )
            raise ReservationExtractionError(code)
        return structures[0]
    except ReservationExtractionError:
        raise
    except Error as error:
        raise ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE") from error


def _extract_client_name(structure: DetailStructure) -> str | None:
    try:
        raw = structure.header_branch.evaluate(
            EXTRACT_CLIENT_NAME_SCRIPT,
            structure.close_control,
        )
    except Error as error:
        raise ReservationExtractionError("CLIENT_NAME_NOT_FOUND") from error
    if not isinstance(raw, Mapping):
        raise ReservationExtractionError("CLIENT_NAME_NOT_FOUND")
    status = raw.get("status")
    if status == "not-found":
        raise ReservationExtractionError("CLIENT_NAME_NOT_FOUND")
    if status != "ok":
        raise ReservationExtractionError("CLIENT_NAME_AMBIGUOUS")
    value = raw.get("value")
    if not isinstance(value, str) or not value:
        raise ReservationExtractionError("CLIENT_NAME_NOT_FOUND")
    return value


def _extract_fields(content: ElementHandle) -> Mapping[str, str]:
    try:
        raw = content.evaluate(
            EXTRACT_FIELDS_SCRIPT,
            {"labels": KNOWN_FIELD_LABELS, "maxDepth": MAX_FIELD_ANCESTOR_DEPTH},
        )
    except Error as error:
        raise ReservationExtractionError("FIELD_STRUCTURE_AMBIGUOUS") from error
    if not isinstance(raw, Mapping):
        raise ReservationExtractionError("FIELD_STRUCTURE_AMBIGUOUS")
    if raw.get("status") == "duplicate":
        raise ReservationExtractionError("DUPLICATE_KNOWN_FIELD")
    fields = raw.get("fields")
    if raw.get("status") != "ok" or not isinstance(fields, Mapping):
        raise ReservationExtractionError("FIELD_STRUCTURE_AMBIGUOUS")
    safe_fields: dict[str, str] = {}
    for label, value in fields.items():
        if label not in KNOWN_FIELD_LABELS or not isinstance(value, str):
            raise ReservationExtractionError("FIELD_STRUCTURE_AMBIGUOUS")
        safe_fields[label] = value
    return MappingProxyType(safe_fields)


def _extract_raw_detail(content: ElementHandle) -> str:
    try:
        value = content.evaluate(EXTRACT_CLEAN_TEXT_SCRIPT)
    except Error as error:
        raise ReservationExtractionError("DETAIL_TEXT_EXTRACTION_FAILED") from error
    if not isinstance(value, str):
        raise ReservationExtractionError("DETAIL_TEXT_EXTRACTION_FAILED")
    return value


def extract_reservation_data(
    page: Page,
    structure: DetailStructure,
) -> ExtractedReservationData:
    """Extract structured fields and cleaned text without changing the live DOM."""
    del page
    return ExtractedReservationData(
        fields=_extract_fields(structure.scroll_container),
        client_name=_extract_client_name(structure),
        raw_detail=_extract_raw_detail(structure.scroll_container),
    )
