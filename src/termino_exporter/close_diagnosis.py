"""Privacy-safe structural diagnosis of close-button candidates."""

import json
import re
from collections.abc import Callable, Mapping

from playwright.sync_api import ElementHandle, Error, Page

OutputWriter = Callable[[str], None]

MAX_VISIBLE_BUTTONS = 20
MAX_ROOT_DEPTH = 4
MAX_COMMON_ANCESTOR_DEPTH = 10
MAX_DIRECT_CHILDREN = 99
MAX_COMMON_ANCESTOR_DISTANCE = 20
SAFE_CLOSE_NAMES = ("Zavřít", "Close")
FORBIDDEN_ACTION_NAMES = ("Upravit", "Odstranit", "Zkopírovat rezervaci")

PARENT_ELEMENT_SCRIPT = "(element) => element.parentElement"
BUTTON_STRUCTURE_SCRIPT = """
(button, options) => {
    const root = options.root;
    const scrollContainer = options.scrollContainer;
    const maxDepth = options.maxDepth;

    let buttonDepth = 0;
    let current = button;
    while (current && current !== root && buttonDepth <= maxDepth) {
        current = current.parentElement;
        buttonDepth += 1;
    }
    if (current !== root || buttonDepth > maxDepth) {
        return {limitExceeded: true};
    }

    const buttonAncestors = [];
    current = button;
    for (let depth = 0; current && depth <= maxDepth; depth += 1) {
        buttonAncestors.push(current);
        current = current.parentElement;
    }
    const scrollAncestors = [];
    current = scrollContainer;
    for (let depth = 0; current && depth <= maxDepth; depth += 1) {
        scrollAncestors.push(current);
        current = current.parentElement;
    }

    let commonAncestorDistance = null;
    for (let buttonIndex = 0; buttonIndex < buttonAncestors.length; buttonIndex += 1) {
        const scrollIndex = scrollAncestors.indexOf(buttonAncestors[buttonIndex]);
        if (scrollIndex !== -1) {
            commonAncestorDistance = buttonIndex + scrollIndex;
            break;
        }
    }
    if (commonAncestorDistance === null) {
        return {limitExceeded: true};
    }

    const hasNonemptyTextNode = Array.from(button.childNodes).some(
        (node) => node.nodeType === Node.TEXT_NODE && /\\S/.test(node.nodeValue || "")
    );
    const relation = button.compareDocumentPosition(scrollContainer);
    return {
        limitExceeded: false,
        buttonDepth,
        directChildCount: Math.min(
            Math.max(button.childElementCount, 0),
            options.maxDirectChildren
        ),
        hasSvg: button.querySelector("svg") !== null,
        hasImg: button.querySelector("img") !== null,
        hasSpan: button.querySelector("span") !== null,
        hasNonemptyTextNode,
        hasSafeAccessibleName: options.safeNames.includes(button),
        isForbiddenAction: options.forbiddenActions.includes(button),
        precedesScrollContainer: Boolean(relation & Node.DOCUMENT_POSITION_FOLLOWING),
        followsScrollContainer: Boolean(relation & Node.DOCUMENT_POSITION_PRECEDING),
        sameParentAsScrollContainer: button.parentElement === scrollContainer.parentElement,
        commonAncestorDistance,
        visible: true,
    };
}
"""

OUTPUT_FIELDS = (
    "candidate",
    "root_depth",
    "button_depth",
    "direct_child_count",
    "has_svg",
    "has_img",
    "has_span",
    "has_nonempty_text_node",
    "has_safe_accessible_name",
    "is_forbidden_action",
    "precedes_scroll_container",
    "follows_scroll_container",
    "same_parent_as_scroll_container",
    "common_ancestor_distance",
    "visible",
)
ALLOWED_ERROR_CODES = frozenset(
    {
        "CLOSE_DIAG_ROOT_NOT_FOUND",
        "CLOSE_DIAG_NO_BUTTONS",
        "CLOSE_DIAG_TOO_MANY_BUTTONS",
        "CLOSE_DIAG_RECORD_LIMIT",
        "CLOSE_DIAG_STRUCTURE_ERROR",
        "CLOSE_DIAG_PLAYWRIGHT_ERROR",
    }
)


class CloseDiagnosisError(RuntimeError):
    """The close-button diagnosis could not be completed safely."""

    def __init__(self, code: str) -> None:
        safe_code = code if code in ALLOWED_ERROR_CODES else "CLOSE_DIAG_STRUCTURE_ERROR"
        self.code = safe_code
        super().__init__(safe_code)


def _safe_boolean(value: object) -> bool:
    return value if isinstance(value, bool) else False


def _safe_integer(value: object, minimum: int, maximum: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CloseDiagnosisError("CLOSE_DIAG_STRUCTURE_ERROR")
    return min(max(value, minimum), maximum)


def _safe_optional_integer(
    value: object,
    minimum: int,
    maximum: int,
) -> int | None:
    if value is None:
        return None
    return _safe_integer(value, minimum, maximum)


def _sanitize_record(
    candidate: int,
    root_depth: int,
    raw: object,
) -> dict[str, object]:
    if not isinstance(raw, Mapping):
        raise CloseDiagnosisError("CLOSE_DIAG_STRUCTURE_ERROR")
    if raw.get("limitExceeded") is True:
        raise CloseDiagnosisError("CLOSE_DIAG_RECORD_LIMIT")
    if raw.get("limitExceeded") is not False:
        raise CloseDiagnosisError("CLOSE_DIAG_STRUCTURE_ERROR")
    record: dict[str, object] = {
        "candidate": _safe_integer(candidate, 1, MAX_VISIBLE_BUTTONS),
        "root_depth": _safe_integer(root_depth, 0, MAX_ROOT_DEPTH),
        "button_depth": _safe_integer(
            raw.get("buttonDepth"),
            0,
            MAX_COMMON_ANCESTOR_DEPTH,
        ),
        "direct_child_count": _safe_integer(
            raw.get("directChildCount"),
            0,
            MAX_DIRECT_CHILDREN,
        ),
        "has_svg": _safe_boolean(raw.get("hasSvg")),
        "has_img": _safe_boolean(raw.get("hasImg")),
        "has_span": _safe_boolean(raw.get("hasSpan")),
        "has_nonempty_text_node": _safe_boolean(raw.get("hasNonemptyTextNode")),
        "has_safe_accessible_name": _safe_boolean(raw.get("hasSafeAccessibleName")),
        "is_forbidden_action": _safe_boolean(raw.get("isForbiddenAction")),
        "precedes_scroll_container": _safe_boolean(raw.get("precedesScrollContainer")),
        "follows_scroll_container": _safe_boolean(raw.get("followsScrollContainer")),
        "same_parent_as_scroll_container": _safe_boolean(raw.get("sameParentAsScrollContainer")),
        "common_ancestor_distance": _safe_optional_integer(
            raw.get("commonAncestorDistance"),
            0,
            MAX_COMMON_ANCESTOR_DISTANCE,
        ),
        "visible": _safe_boolean(raw.get("visible")),
    }
    if tuple(record) != OUTPUT_FIELDS:
        raise CloseDiagnosisError("CLOSE_DIAG_STRUCTURE_ERROR")
    return record


def named_visible_button_handles(
    page: Page,
    names: tuple[str, ...],
) -> list[ElementHandle]:
    pattern = re.compile(rf"^({'|'.join(re.escape(name) for name in names)})$")
    locator = page.get_by_role("button", name=pattern)
    handles: list[ElementHandle] = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            handle = candidate.element_handle()
            if handle is not None:
                handles.append(handle)
    return handles


def _bounded_root(content: ElementHandle) -> tuple[ElementHandle, int]:
    root = content
    root_depth = 0
    for depth in range(1, MAX_ROOT_DEPTH + 1):
        parent_handle = root.evaluate_handle(PARENT_ELEMENT_SCRIPT)
        parent = parent_handle.as_element()
        if parent is None:
            parent_handle.dispose()
            if root_depth == 0:
                raise CloseDiagnosisError("CLOSE_DIAG_ROOT_NOT_FOUND")
            break
        root = parent
        root_depth = depth
    return root, root_depth


def diagnose_close_buttons(
    page: Page,
    content: ElementHandle,
    write: OutputWriter = print,
) -> None:
    """Print only bounded boolean and numeric structure for candidate buttons."""
    try:
        root, root_depth = _bounded_root(content)
        safe_names = named_visible_button_handles(page, SAFE_CLOSE_NAMES)
        forbidden_actions = named_visible_button_handles(page, FORBIDDEN_ACTION_NAMES)
        visible_buttons: list[ElementHandle] = []
        for button in root.query_selector_all("button"):
            if button.is_visible():
                visible_buttons.append(button)
                if len(visible_buttons) > MAX_VISIBLE_BUTTONS:
                    raise CloseDiagnosisError("CLOSE_DIAG_TOO_MANY_BUTTONS")

        if not visible_buttons:
            raise CloseDiagnosisError("CLOSE_DIAG_NO_BUTTONS")

        records = [
            _sanitize_record(
                candidate=index,
                root_depth=root_depth,
                raw=button.evaluate(
                    BUTTON_STRUCTURE_SCRIPT,
                    {
                        "root": root,
                        "scrollContainer": content,
                        "maxDepth": MAX_COMMON_ANCESTOR_DEPTH,
                        "maxDirectChildren": MAX_DIRECT_CHILDREN,
                        "safeNames": safe_names,
                        "forbiddenActions": forbidden_actions,
                    },
                ),
            )
            for index, button in enumerate(visible_buttons, start=1)
        ]
    except Error as error:
        raise CloseDiagnosisError("CLOSE_DIAG_PLAYWRIGHT_ERROR") from error

    for record in records:
        write(json.dumps(record, ensure_ascii=False, sort_keys=True))
