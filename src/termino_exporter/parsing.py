"""Pure parsing of structured Termino reservation fields."""

import re
from collections.abc import Mapping
from datetime import date, datetime, time
from decimal import Decimal

from termino_exporter.models import Reservation

_CZECH_WEEKDAY = r"(?:po|út|st|čt|pá|so|ne|pondělí|úterý|středa|čtvrtek|pátek|sobota|neděle)"
_DATE_PATTERN = re.compile(rf"^(?:{_CZECH_WEEKDAY}\s+)?(\d{{1,2}})\.\s*(\d{{1,2}})\.\s*(\d{{4}})$")
_TIME_RANGE_PATTERN = re.compile(r"^(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})$")
_CREATED_AT_PATTERN = re.compile(
    rf"^(?:{_CZECH_WEEKDAY}\s+)?(\d{{1,2}})\.\s*(\d{{1,2}})\.\s*(\d{{4}})"
    r"\s+(\d{1,2}):(\d{2})$"
)
_PRICE_PATTERN = re.compile(r"^(\d+)(?:,(\d{1,2}))?\s*Kč$")
_DURATION_PATTERN = re.compile(r"\((\d+)\s+min\.?\)")
_PRICE_SPACES = str.maketrans("", "", " \u00a0\u202f")


class ReservationParseError(ValueError):
    """A safe structured-field parsing failure identified only by a fixed code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def parse_czech_date(value: str) -> date:
    """Parse a Czech numeric date with an optional Czech weekday prefix."""
    match = _DATE_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ReservationParseError("INVALID_DATE")
    try:
        day, month, year = (int(part) for part in match.groups())
        return date(year, month, day)
    except ValueError as error:
        raise ReservationParseError("INVALID_DATE") from error


def parse_time_range(value: str) -> tuple[time, time]:
    """Parse a same-day start and end time range."""
    match = _TIME_RANGE_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ReservationParseError("INVALID_TIME_RANGE")
    try:
        start_hour, start_minute, end_hour, end_minute = (int(part) for part in match.groups())
        start = time(start_hour, start_minute)
        end = time(end_hour, end_minute)
    except ValueError as error:
        raise ReservationParseError("INVALID_TIME_RANGE") from error
    if end <= start:
        raise ReservationParseError("INVALID_TIME_RANGE")
    return start, end


def parse_price(value: str) -> Decimal:
    """Parse a non-negative Czech-crown amount without using floating point."""
    compact = value.strip().translate(_PRICE_SPACES)
    match = _PRICE_PATTERN.fullmatch(compact)
    if match is None:
        raise ReservationParseError("INVALID_PRICE")
    whole, fraction = match.groups()
    normalized = whole if fraction is None else f"{whole}.{fraction}"
    return Decimal(normalized)


def parse_people_count(value: str) -> int:
    """Parse a strictly positive reservation party size."""
    normalized = value.strip()
    if not normalized.isascii() or not normalized.isdigit():
        raise ReservationParseError("INVALID_PEOPLE_COUNT")
    count = int(normalized)
    if count <= 0:
        raise ReservationParseError("INVALID_PEOPLE_COUNT")
    return count


def parse_created_at(value: str) -> datetime:
    """Parse the timezone-naive local creation time shown by Termino."""
    match = _CREATED_AT_PATTERN.fullmatch(value.strip())
    if match is None:
        raise ReservationParseError("INVALID_CREATED_AT")
    try:
        day, month, year, hour, minute = (int(part) for part in match.groups())
        return datetime(year, month, day, hour, minute)
    except ValueError as error:
        raise ReservationParseError("INVALID_CREATED_AT") from error


def derive_duration_minutes(service_or_package: str) -> int | None:
    """Derive a positive duration only from an unambiguous trailing marker."""
    normalized = service_or_package.strip()
    matches = list(_DURATION_PATTERN.finditer(normalized))
    if len(matches) != 1 or matches[0].end() != len(normalized):
        return None
    match = matches[0]
    duration = int(match.group(1))
    return duration if duration > 0 else None


def _optional_text(fields: Mapping[str, str], label: str) -> str | None:
    value = fields.get(label)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _optional_note(fields: Mapping[str, str]) -> str | None:
    value = fields.get("Poznámka")
    if value is None or not value.strip():
        return None
    lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines) or None


def parse_reservation_fields(
    fields: Mapping[str, str],
    *,
    client_name: str | None = None,
    raw_detail: str | None = None,
) -> Reservation:
    """Build a reservation from already structured fields without I/O or DOM access."""
    date_text = _optional_text(fields, "Datum")
    time_text = _optional_text(fields, "Čas")
    people_text = _optional_text(fields, "Počet osob na rezervaci")
    price_text = _optional_text(fields, "Cena")
    created_at_text = _optional_text(fields, "Vytvořena")
    service_or_package = _optional_text(fields, "Služba nebo balíček")

    start_time: time | None = None
    end_time: time | None = None
    if time_text is not None:
        start_time, end_time = parse_time_range(time_text)

    normalized_client_name = client_name.strip() if client_name is not None else None
    if normalized_client_name == "":
        normalized_client_name = None

    return Reservation(
        client_name=normalized_client_name,
        date=parse_czech_date(date_text) if date_text is not None else None,
        start_time=start_time,
        end_time=end_time,
        service_or_package=service_or_package,
        people_count=(parse_people_count(people_text) if people_text is not None else None),
        workplace=_optional_text(fields, "Pracoviště"),
        employee=_optional_text(fields, "Zaměstnanec"),
        duration_minutes=(
            derive_duration_minutes(service_or_package) if service_or_package is not None else None
        ),
        price=parse_price(price_text) if price_text is not None else None,
        status=_optional_text(fields, "Stav rezervace"),
        source=_optional_text(fields, "Zdroj"),
        reservation_type=_optional_text(fields, "Typ"),
        created_at=(parse_created_at(created_at_text) if created_at_text is not None else None),
        note=_optional_note(fields),
        phone=_optional_text(fields, "Telefon"),
        email=_optional_text(fields, "E-mail"),
        raw_detail=raw_detail,
    )
