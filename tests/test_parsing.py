import inspect
from datetime import date, datetime, time
from decimal import Decimal

import pytest

import termino_exporter.parsing as parsing
from termino_exporter.parsing import (
    ReservationParseError,
    derive_duration_minutes,
    parse_created_at,
    parse_czech_date,
    parse_people_count,
    parse_price,
    parse_reservation_fields,
    parse_time_range,
)


def test_complete_structured_reservation() -> None:
    fields = {
        "Datum": "po 27. 7. 2030",
        "Čas": "14:00 - 15:45",
        "Služba nebo balíček": "Testovací služba (105 min.)",
        "Počet osob na rezervaci": "2",
        "Cena": "1\u00a0600,50 Kč",
        "Pracoviště": "Testovací pracoviště",
        "Zaměstnanec": "Testovací zaměstnanec",
        "Poznámka": "Testovací poznámka",
        "E-mail": "test@example.invalid",
        "Telefon": "TEST-TELEFON",
        "Zdroj": "Testovací zdroj",
        "Typ": "Testovací typ",
        "Stav rezervace": "Testovací stav",
        "Vytvořena": "čtvrtek 25. 7. 2030 7:04",
    }

    reservation = parse_reservation_fields(
        fields,
        client_name="  TEST OSOBA  ",
        raw_detail="OČIŠTĚNÝ TESTOVACÍ DETAIL",
    )

    assert reservation.client_name == "TEST OSOBA"
    assert reservation.date == date(2030, 7, 27)
    assert reservation.start_time == time(14, 0)
    assert reservation.end_time == time(15, 45)
    assert reservation.service_or_package == "Testovací služba (105 min.)"
    assert reservation.people_count == 2
    assert reservation.price == Decimal("1600.50")
    assert reservation.workplace == "Testovací pracoviště"
    assert reservation.employee == "Testovací zaměstnanec"
    assert reservation.note == "Testovací poznámka"
    assert reservation.email == "test@example.invalid"
    assert reservation.phone == "TEST-TELEFON"
    assert reservation.source == "Testovací zdroj"
    assert reservation.reservation_type == "Testovací typ"
    assert reservation.status == "Testovací stav"
    assert reservation.created_at == datetime(2030, 7, 25, 7, 4)
    assert reservation.duration_minutes == 105
    assert reservation.raw_detail == "OČIŠTĚNÝ TESTOVACÍ DETAIL"
    assert reservation.first_name is None
    assert reservation.last_name is None
    assert reservation.service is None
    assert reservation.package_name is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("27. 7. 2030", date(2030, 7, 27)),
        ("po 27. 7. 2030", date(2030, 7, 27)),
        ("pondělí 27. 7. 2030", date(2030, 7, 27)),
    ],
)
def test_parse_czech_date(value: str, expected: date) -> None:
    assert parse_czech_date(value) == expected


@pytest.mark.parametrize("value", ["není datum", "31. 2. 2030"])
def test_invalid_date_has_safe_code(value: str) -> None:
    with pytest.raises(ReservationParseError) as caught:
        parse_czech_date(value)
    assert str(caught.value) == "INVALID_DATE"
    assert value not in repr(caught.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("14:00 - 15:45", (time(14, 0), time(15, 45))),
        ("8:05 - 9:00", (time(8, 5), time(9, 0))),
    ],
)
def test_parse_time_range(value: str, expected: tuple[time, time]) -> None:
    assert parse_time_range(value) == expected


@pytest.mark.parametrize("value", ["neplatný čas", "15:45 - 14:00", "24:00 - 25:00"])
def test_invalid_time_range_has_safe_code(value: str) -> None:
    with pytest.raises(ReservationParseError) as caught:
        parse_time_range(value)
    assert str(caught.value) == "INVALID_TIME_RANGE"
    assert value not in repr(caught.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1600 Kč", Decimal("1600")),
        ("1 600 Kč", Decimal("1600")),
        ("1\u00a0600 Kč", Decimal("1600")),
        ("1\u202f600 Kč", Decimal("1600")),
        ("1600,50 Kč", Decimal("1600.50")),
    ],
)
def test_parse_price(value: str, expected: Decimal) -> None:
    assert parse_price(value) == expected


@pytest.mark.parametrize("value", ["zdarma", "-100 Kč", "12.3 Kč"])
def test_invalid_price_has_safe_code(value: str) -> None:
    with pytest.raises(ReservationParseError) as caught:
        parse_price(value)
    assert str(caught.value) == "INVALID_PRICE"
    assert value not in repr(caught.value)


def test_positive_people_count() -> None:
    assert parse_people_count("2") == 2


@pytest.mark.parametrize("value", ["0", "-1", "dvě"])
def test_invalid_people_count_has_safe_code(value: str) -> None:
    with pytest.raises(ReservationParseError) as caught:
        parse_people_count(value)
    assert str(caught.value) == "INVALID_PEOPLE_COUNT"
    assert value not in repr(caught.value)


def test_multiline_note_normalizes_line_endings_and_keeps_internal_lines() -> None:
    reservation = parse_reservation_fields(
        {"Poznámka": "\r\n\r\nPrvní testovací řádek\r\n\r\nMéně\rDruhý řádek\r\n"}
    )
    assert reservation.note == "První testovací řádek\n\nMéně\nDruhý řádek"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("30. 7. 2030 7:04", datetime(2030, 7, 30, 7, 4)),
        ("čtvrtek 30. 7. 2030 7:04", datetime(2030, 7, 30, 7, 4)),
    ],
)
def test_parse_created_at(value: str, expected: datetime) -> None:
    result = parse_created_at(value)
    assert result == expected
    assert result.tzinfo is None


@pytest.mark.parametrize("value", ["není čas vytvoření", "31. 2. 2030 7:04"])
def test_invalid_created_at_has_safe_code(value: str) -> None:
    with pytest.raises(ReservationParseError) as caught:
        parse_created_at(value)
    assert str(caught.value) == "INVALID_CREATED_AT"
    assert value not in repr(caught.value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("Testovací služba (105 min.)", 105),
        ("Testovací služba (60 min)", 60),
        ("Testovací služba 105 pro 2 osoby", None),
        ("Testovací služba (30 min.) a doplněk (60 min.)", None),
        ("Testovací služba (0 min.)", None),
    ],
)
def test_derive_duration_minutes(value: str, expected: int | None) -> None:
    assert derive_duration_minutes(value) == expected


def test_duration_does_not_change_original_service_or_package() -> None:
    original = "Testovací služba (105 min.)"
    reservation = parse_reservation_fields({"Služba nebo balíček": original})
    assert reservation.service_or_package == original
    assert reservation.duration_minutes == 105


def test_missing_blank_and_unknown_fields_are_ignored() -> None:
    reservation = parse_reservation_fields(
        {
            "Datum": "  ",
            "Poznámka": "\r\n  \r\n",
            "Neznámé testovací pole": "IGNOROVANÁ TESTOVACÍ HODNOTA",
        },
        client_name="  ",
    )
    assert reservation.date is None
    assert reservation.note is None
    assert reservation.client_name is None
    assert reservation.email is None


def test_raw_detail_is_only_passed_through_and_not_used_for_parsing() -> None:
    raw_detail = "Datum\nNEPLATNÉ TESTOVACÍ DATUM"
    reservation = parse_reservation_fields({}, raw_detail=raw_detail)
    assert reservation.raw_detail is raw_detail
    assert reservation.date is None


def test_parse_error_does_not_expose_any_input_data() -> None:
    fields = {
        "Datum": "TAJNÁ TESTOVACÍ HODNOTA",
        "E-mail": "test@example.invalid",
        "Telefon": "TEST-TELEFON",
        "Poznámka": "TAJNÁ TESTOVACÍ POZNÁMKA",
    }
    with pytest.raises(ReservationParseError) as caught:
        parse_reservation_fields(
            fields,
            client_name="TEST OSOBA",
            raw_detail="TAJNÝ TESTOVACÍ DETAIL",
        )
    rendered = f"{caught.value!s} {caught.value!r}"
    for secret in (*fields.values(), "TEST OSOBA", "TAJNÝ TESTOVACÍ DETAIL"):
        assert secret not in rendered


def test_parsing_module_has_no_playwright_dependency_or_io() -> None:
    source = inspect.getsource(parsing)
    assert "playwright" not in source.lower()
    assert "open(" not in source
    assert "print(" not in source
