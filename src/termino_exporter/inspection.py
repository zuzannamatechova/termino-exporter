"""Read-only inspection of one manually opened Termino reservation."""

import sys
from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path

from playwright.sync_api import (
    BrowserContext,
    ElementHandle,
    Error,
    Locator,
    Page,
)
from playwright.sync_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from termino_exporter.browser import persistent_browser_context
from termino_exporter.close_diagnosis import (
    FORBIDDEN_ACTION_NAMES,
    diagnose_close_buttons,
    named_visible_button_handles,
)
from termino_exporter.diagnosis import diagnose_dialog_structure

ContextFactory = Callable[[Path, float], AbstractContextManager[BrowserContext]]
OutputWriter = Callable[[str], None]
WaitForEnter = Callable[[str], str]
FlushOutput = Callable[[], None]

MAX_CONTENT_ANCESTOR_DEPTH = 10
MAX_CLOSE_ANCESTOR_DEPTH = 4
CLOSE_CONFIRM_TIMEOUT_MS = 3_000
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
CLOSE_SIGNATURE_SCRIPT = """
(button, options) => {
    const branches = Array.from(options.root.children);
    const contentBranches = branches.filter(
        (branch) => branch === options.scrollContainer || branch.contains(options.scrollContainer)
    );
    const actionBranches = branches.filter(
        (branch) => options.forbiddenActions.every((action) => branch.contains(action))
    );
    const headerBranches = branches.filter(
        (branch) => branch === button || branch.contains(button)
    );
    if (
        contentBranches.length !== 1 ||
        actionBranches.length !== 1 ||
        headerBranches.length !== 1
    ) {
        return {hasUniqueBranches: false};
    }

    const contentBranch = contentBranches[0];
    const actionBranch = actionBranches[0];
    const headerBranch = headerBranches[0];
    const headerIndex = branches.indexOf(headerBranch);
    const contentIndex = branches.indexOf(contentBranch);
    const actionIndex = branches.indexOf(actionBranch);
    const relation = button.compareDocumentPosition(options.scrollContainer);
    return {
        hasUniqueBranches:
            headerBranch !== contentBranch &&
            contentBranch !== actionBranch &&
            headerBranch !== actionBranch &&
            headerIndex < contentIndex &&
            contentIndex < actionIndex,
        precedesScrollContainer: Boolean(relation & Node.DOCUMENT_POSITION_FOLLOWING),
        followsScrollContainer: Boolean(relation & Node.DOCUMENT_POSITION_PRECEDING),
        hasSvg: button.querySelector("svg") !== null,
        hasNonemptyTextContent: (button.textContent || "").trim().length > 0,
        isForbiddenAction: options.forbiddenActions.includes(button),
    };
}
"""


class InspectionError(RuntimeError):
    """Expected error during read-only reservation inspection."""


class DetailStructureError(InspectionError):
    """The manually opened detail did not have the required safe DOM structure."""


class CloseControlError(InspectionError):
    """The detail did not have exactly one safe close control."""


def _flush_stdout() -> None:
    sys.stdout.flush()


def _visible_matches(locator: Locator) -> list[Locator]:
    matches: list[Locator] = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            matches.append(candidate)
    return matches


def _find_one_visible_label(page: Page, text: str, error_message: str) -> Locator:
    matches = _visible_matches(page.get_by_text(text, exact=True))
    if len(matches) != 1:
        raise DetailStructureError(error_message)
    return matches[0]


def find_detail_content(page: Page) -> ElementHandle:
    """Find the nearest common genuinely scrollable ancestor of Datum and Čas."""
    date_label = _find_one_visible_label(
        page,
        "Datum",
        "V otevřeném detailu nebyl jednoznačně nalezen popisek Datum.",
    )
    time_label = _find_one_visible_label(
        page,
        "Čas",
        "V otevřeném detailu nebyl jednoznačně nalezen popisek Čas.",
    )
    date_element = date_label.element_handle()
    time_element = time_label.element_handle()
    if date_element is None or time_element is None:
        raise DetailStructureError("Nebyl nalezen společný rolovací obsah detailu rezervace.")

    container_handle = date_element.evaluate_handle(
        FIND_SCROLL_CONTAINER_SCRIPT,
        {
            "timeLabel": time_element,
            "maxDepth": MAX_CONTENT_ANCESTOR_DEPTH,
        },
    )
    container = container_handle.as_element()
    if container is None:
        container_handle.dispose()
        raise DetailStructureError("Nebyl nalezen společný rolovací obsah detailu rezervace.")
    return container


def find_safe_close_control(
    page: Page,
    content: ElementHandle,
) -> ElementHandle:
    """Find one structurally safe close button in the nearest bounded root."""
    forbidden_actions: list[ElementHandle] = []
    for action_name in FORBIDDEN_ACTION_NAMES:
        action_matches = named_visible_button_handles(page, (action_name,))
        if len(action_matches) != 1:
            raise CloseControlError(
                "Detail nemá jednoznačně rozpoznané bezpečné strukturální větve."
            )
        forbidden_actions.append(action_matches[0])
    current: ElementHandle | None = content

    for depth in range(MAX_CLOSE_ANCESTOR_DEPTH + 1):
        if current is None:
            break
        safe_candidates: list[ElementHandle] = []
        for button in current.query_selector_all("button"):
            if button.is_visible() and _matches_close_signature(
                button.evaluate(
                    CLOSE_SIGNATURE_SCRIPT,
                    {
                        "root": current,
                        "scrollContainer": content,
                        "forbiddenActions": forbidden_actions,
                    },
                )
            ):
                safe_candidates.append(button)
        if len(safe_candidates) == 1:
            return safe_candidates[0]
        if len(safe_candidates) > 1:
            raise CloseControlError("Detail nemá jednoznačně rozpoznaný zavírací prvek.")
        if depth < MAX_CLOSE_ANCESTOR_DEPTH:
            parent_handle = current.evaluate_handle(PARENT_ELEMENT_SCRIPT)
            current = parent_handle.as_element()

    raise CloseControlError("Detail nemá jednoznačně rozpoznaný zavírací prvek.")


def _matches_close_signature(raw: object) -> bool:
    if not isinstance(raw, Mapping):
        return False
    return (
        raw.get("hasUniqueBranches") is True
        and raw.get("precedesScrollContainer") is True
        and raw.get("followsScrollContainer") is False
        and raw.get("hasSvg") is True
        and raw.get("hasNonemptyTextContent") is False
        and raw.get("isForbiddenAction") is False
    )


def confirm_detail_closed(
    page: Page,
    content: ElementHandle,
    timeout_ms: float = CLOSE_CONFIRM_TIMEOUT_MS,
) -> None:
    """Confirm closure once, without any retry click."""
    try:
        content.wait_for_element_state("hidden", timeout=timeout_ms)
        return
    except PlaywrightTimeoutError:
        pass

    date_visible = bool(_visible_matches(page.get_by_text("Datum", exact=True)))
    time_visible = bool(_visible_matches(page.get_by_text("Čas", exact=True)))
    if date_visible and time_visible:
        raise CloseControlError("Zavření detailu se nepodařilo potvrdit.")


def inspect_open_detail(
    page: Page,
    write: OutputWriter = print,
    flush_output: FlushOutput = _flush_stdout,
) -> None:
    """Print current content of one manually opened detail and close it safely."""
    try:
        content = find_detail_content(page)
        detail_text = content.inner_text()
        write("----- Aktuálně dostupný text detailu rezervace -----")
        write(detail_text)
        write("----- Konec aktuálně dostupného textu -----")
        flush_output()
        close_control = find_safe_close_control(page, content)
        close_control.click()
        confirm_detail_closed(page, content)
    except Error as error:
        raise InspectionError("Operace s otevřeným detailem se nezdařila.") from error


def inspect_one_reservation(
    *,
    url: str,
    profile_dir: Path,
    timeout_seconds: float,
    diagnose_dialog: bool = False,
    diagnose_close: bool = False,
    wait_for_enter: WaitForEnter = input,
    write: OutputWriter = print,
    context_factory: ContextFactory = persistent_browser_context,
) -> None:
    """Run one read-only inspection inside an always-closed browser context."""
    with context_factory(profile_dir, timeout_seconds) as context:
        page = context.pages[0] if context.pages else context.new_page()
        try:
            page.goto(url)
        except Error as error:
            raise InspectionError("Adresu Termino se nepodařilo otevřít.") from error
        write(
            "V prohlížeči se ručně přihlaste, přejděte na správné datum, ručně klikněte "
            "na požadovanou rezervaci a nechte její detail otevřený."
        )
        wait_for_enter("Potom se vraťte do terminálu a stiskněte Enter...")
        if diagnose_dialog:
            diagnose_dialog_structure(page, write)
        elif diagnose_close:
            content = find_detail_content(page)
            diagnose_close_buttons(page, content, write)
        else:
            inspect_open_detail(page, write)
