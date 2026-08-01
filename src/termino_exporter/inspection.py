"""Read-only inspection of one manually opened Termino reservation."""

import sys
from collections.abc import Callable
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
    diagnose_close_buttons,
    named_visible_button_handles,
)
from termino_exporter.diagnosis import diagnose_dialog_structure
from termino_exporter.extraction import (
    FIND_SCROLL_CONTAINER_SCRIPT as FIND_SCROLL_CONTAINER_SCRIPT,
)
from termino_exporter.extraction import (
    MAX_CONTENT_ANCESTOR_DEPTH as MAX_CONTENT_ANCESTOR_DEPTH,
)
from termino_exporter.extraction import (
    MAX_STRUCTURE_ANCESTOR_DEPTH,
    ReservationExtractionError,
    extract_reservation_data,
    find_detail_structure,
)
from termino_exporter.extraction import (
    find_detail_content as extract_detail_content,
)
from termino_exporter.models import Reservation
from termino_exporter.parsing import ReservationParseError, parse_reservation_fields

ContextFactory = Callable[[Path, float], AbstractContextManager[BrowserContext]]
OutputWriter = Callable[[str], None]
WaitForEnter = Callable[[str], str]
FlushOutput = Callable[[], None]
NamedButtonFinder = Callable[[Page, ElementHandle, str], list[ElementHandle]]
ExpandDetail = Callable[[Page, ElementHandle], None]

MAX_CLOSE_ANCESTOR_DEPTH = MAX_STRUCTURE_ANCESTOR_DEPTH
CLOSE_CONFIRM_TIMEOUT_MS = 3_000
EXPAND_CLICK_TIMEOUT_MS = 3_000
MAX_SUCCESSFUL_EXPANSIONS = 10
MATCHES_NAMED_BUTTON_SCRIPT = "(button, matches) => matches.includes(button)"


class InspectionError(RuntimeError):
    """Expected error during read-only reservation inspection."""


class DetailStructureError(InspectionError):
    """The manually opened detail did not have the required safe DOM structure."""


class CloseControlError(InspectionError):
    """The detail did not have exactly one safe close control."""


class ExpansionError(InspectionError):
    """The full detail could not be expanded safely."""


class ReservationProcessingError(InspectionError):
    """Structured extraction or parsing failed without exposing reservation values."""


def _flush_stdout() -> None:
    sys.stdout.flush()


def _visible_matches(locator: Locator) -> list[Locator]:
    matches: list[Locator] = []
    for index in range(locator.count()):
        candidate = locator.nth(index)
        if candidate.is_visible():
            matches.append(candidate)
    return matches


def _visible_named_buttons_inside(
    page: Page,
    content: ElementHandle,
    name: str,
) -> list[ElementHandle]:
    """Return fresh visible named buttons that are descendants of content."""
    named_buttons = named_visible_button_handles(page, (name,))
    matches: list[ElementHandle] = []
    for button in content.query_selector_all("button"):
        if button.is_visible() and button.evaluate(
            MATCHES_NAMED_BUTTON_SCRIPT,
            named_buttons,
        ):
            matches.append(button)
    return matches


def _handle_is_in_fresh_matches(
    candidate: ElementHandle,
    fresh_matches: list[ElementHandle],
) -> bool:
    """Safely confirm that a still-attached handle now has a freshly matched name."""
    try:
        return bool(
            candidate.evaluate(
                MATCHES_NAMED_BUTTON_SCRIPT,
                fresh_matches,
            )
        )
    except Error:
        return False


def expand_all_more_buttons(
    page: Page,
    content: ElementHandle,
    *,
    find_buttons: NamedButtonFinder = _visible_named_buttons_inside,
    click_timeout_ms: float = EXPAND_CLICK_TIMEOUT_MS,
) -> None:
    """Expand every current More button once, with bounded verified progress."""
    successful_expansions = 0
    while True:
        more_buttons = find_buttons(page, content, "Více")
        if not more_buttons:
            return
        if successful_expansions >= MAX_SUCCESSFUL_EXPANSIONS:
            raise ExpansionError("Detail obsahuje příliš mnoho prvků k rozbalení.")

        before_more_count = len(more_buttons)
        before_less_count = len(find_buttons(page, content, "Méně"))
        candidate = more_buttons.pop()
        before_text_length = len(content.inner_text())
        candidate.click(timeout=click_timeout_ms)

        refreshed_more_buttons = find_buttons(page, content, "Více")
        refreshed_less_buttons = find_buttons(page, content, "Méně")
        after_text_length = len(content.inner_text())
        candidate_changed_to_less = _handle_is_in_fresh_matches(
            candidate,
            refreshed_less_buttons,
        )
        if (
            len(refreshed_more_buttons) < before_more_count
            or len(refreshed_less_buttons) > before_less_count
            or after_text_length > before_text_length
            or candidate_changed_to_less
        ):
            successful_expansions += 1
            continue

        raise ExpansionError("Rozbalení obsahu detailu se nepodařilo potvrdit.")


def find_detail_content(page: Page) -> ElementHandle:
    """Find the nearest common genuinely scrollable ancestor of Datum and Čas."""
    try:
        return extract_detail_content(page)
    except ReservationExtractionError as error:
        raise DetailStructureError(
            "Nebyl nalezen společný rolovací obsah detailu rezervace."
        ) from error


def find_safe_close_control(
    page: Page,
    content: ElementHandle,
) -> ElementHandle:
    """Find one structurally safe close button in the nearest bounded root."""
    try:
        return find_detail_structure(page, content).close_control
    except ReservationExtractionError as error:
        raise CloseControlError("Detail nemá jednoznačně rozpoznaný zavírací prvek.") from error


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


def _format_value(value: object, format_spec: str | None = None) -> str:
    if value is None:
        return "Neuvedeno"
    if format_spec is not None:
        return format(value, format_spec)
    return str(value)


def format_structured_reservation(reservation: Reservation) -> str:
    """Format an explicit safe allowlist that intentionally excludes raw_detail."""
    lines = [
        "----- Strukturovaná rezervace -----",
        f"Jméno klienta: {_format_value(reservation.client_name)}",
        f"Datum: {_format_value(reservation.date, '%d.%m.%Y')}",
        f"Čas od: {_format_value(reservation.start_time, '%H:%M')}",
        f"Čas do: {_format_value(reservation.end_time, '%H:%M')}",
        f"Služba nebo balíček: {_format_value(reservation.service_or_package)}",
        f"Počet osob: {_format_value(reservation.people_count)}",
        f"Cena: {_format_value(reservation.price, 'f')}",
        f"Pracoviště: {_format_value(reservation.workplace)}",
        f"Zaměstnanec: {_format_value(reservation.employee)}",
        f"Délka v minutách: {_format_value(reservation.duration_minutes)}",
        f"E-mail: {_format_value(reservation.email)}",
        f"Telefon: {_format_value(reservation.phone)}",
        f"Zdroj: {_format_value(reservation.source)}",
        f"Typ: {_format_value(reservation.reservation_type)}",
        f"Stav rezervace: {_format_value(reservation.status)}",
        f"Vytvořena: {_format_value(reservation.created_at, '%d.%m.%Y %H:%M')}",
        f"Poznámka: {_format_value(reservation.note)}",
        "----- Konec strukturované rezervace -----",
    ]
    return "\n".join(lines)


def inspect_open_detail(
    page: Page,
    write: OutputWriter = print,
    flush_output: FlushOutput = _flush_stdout,
    expand_detail: ExpandDetail = expand_all_more_buttons,
) -> Reservation:
    """Extract, parse, print, and safely close one manually opened detail."""
    try:
        initial_structure = find_detail_structure(page)
        expand_detail(page, initial_structure.scroll_container)
        fresh_structure = find_detail_structure(page)
        extracted = extract_reservation_data(page, fresh_structure)
        reservation = parse_reservation_fields(
            extracted.fields,
            client_name=extracted.client_name,
            raw_detail=extracted.raw_detail,
        )
        write(format_structured_reservation(reservation))
        flush_output()
        fresh_structure.close_control.click()
        confirm_detail_closed(page, fresh_structure.scroll_container)
        return reservation
    except (ReservationExtractionError, ReservationParseError) as error:
        raise ReservationProcessingError(
            f"Zpracování rezervace se nezdařilo ({error.code})."
        ) from error
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
