import inspect
from datetime import date, datetime, time
from decimal import Decimal
from unittest.mock import MagicMock, call

import pytest
from playwright.sync_api import Error

import termino_exporter.extraction as extraction_module
import termino_exporter.inspection as inspection_module
import termino_exporter.parsing as parsing_module
from termino_exporter.extraction import (
    ExtractedReservationData,
    ReservationExtractionError,
)
from termino_exporter.inspection import (
    MAX_SUCCESSFUL_EXPANSIONS,
    InspectionError,
    ReservationProcessingError,
    format_structured_reservation,
    inspect_open_detail,
)
from termino_exporter.models import Reservation
from termino_exporter.parsing import ReservationParseError


def _structure(name: str) -> MagicMock:
    structure = MagicMock(name=name)
    structure.root = MagicMock(name=f"{name}-root")
    structure.header_branch = MagicMock(name=f"{name}-header")
    structure.content_branch = MagicMock(name=f"{name}-content-branch")
    structure.scroll_container = MagicMock(name=f"{name}-scroll-container")
    structure.action_branch = MagicMock(name=f"{name}-action")
    structure.close_control = MagicMock(name=f"{name}-close")
    return structure


def _reservation() -> Reservation:
    return Reservation(
        client_name="TEST OSOBA",
        date=date(2030, 7, 27),
        start_time=time(14, 0),
        end_time=time(15, 45),
        service_or_package="Testovací služba (105 min.)",
        people_count=1,
        workplace="Testovací pracoviště",
        employee="Testovací zaměstnanec",
        duration_minutes=105,
        price=Decimal("1600.50"),
        email="test@example.invalid",
        phone="TEST-TELEFON",
        source="Testovací zdroj",
        reservation_type="Testovací typ",
        status="Testovací stav",
        created_at=datetime(2030, 7, 25, 7, 4),
        note="Testovací poznámka\nDruhý testovací řádek",
        raw_detail="NEVYPISOVAT TESTOVACÍ RAW DETAIL",
    )


def test_full_phase3_flow_uses_fresh_structure_and_returns_parser_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page = MagicMock()
    initial = _structure("initial")
    fresh = _structure("fresh")
    extracted = ExtractedReservationData(
        fields={"Datum": "27. 7. 2030"},
        client_name="TEST OSOBA",
        raw_detail="OČIŠTĚNÝ TESTOVACÍ DETAIL",
    )
    reservation = _reservation()
    events: list[str] = []
    finder = MagicMock(
        side_effect=lambda _page: (
            events.append("find-initial" if not events else "find-fresh"),
            initial if len(events) == 1 else fresh,
        )[1]
    )
    expand = MagicMock(side_effect=lambda *_args: events.append("expand"))
    extractor = MagicMock(side_effect=lambda *_args: events.append("extract") or extracted)
    parser = MagicMock(side_effect=lambda *_args, **_kwargs: events.append("parse") or reservation)
    write = MagicMock(side_effect=lambda _text: events.append("write"))
    flush = MagicMock(side_effect=lambda: events.append("flush"))
    fresh.close_control.click.side_effect = lambda: events.append("close")
    confirm = MagicMock(side_effect=lambda *_args: events.append("confirm"))
    monkeypatch.setattr(inspection_module, "find_detail_structure", finder)
    monkeypatch.setattr(inspection_module, "extract_reservation_data", extractor)
    monkeypatch.setattr(inspection_module, "parse_reservation_fields", parser)
    monkeypatch.setattr(inspection_module, "confirm_detail_closed", confirm)

    result = inspect_open_detail(
        page,
        write=write,
        flush_output=flush,
        expand_detail=expand,
    )

    assert result is reservation
    assert finder.call_args_list == [call(page), call(page)]
    expand.assert_called_once_with(page, initial.scroll_container)
    extractor.assert_called_once_with(page, fresh)
    parser.assert_called_once_with(
        extracted.fields,
        client_name=extracted.client_name,
        raw_detail=extracted.raw_detail,
    )
    write.assert_called_once()
    flush.assert_called_once_with()
    fresh.close_control.click.assert_called_once_with()
    confirm.assert_called_once_with(page, fresh.scroll_container)
    assert events == [
        "find-initial",
        "expand",
        "find-fresh",
        "extract",
        "parse",
        "write",
        "flush",
        "close",
        "confirm",
    ]
    initial.close_control.click.assert_not_called()
    initial.header_branch.evaluate.assert_not_called()
    initial.content_branch.evaluate.assert_not_called()
    assert initial.content_branch is not initial.scroll_container


def test_structured_output_uses_only_explicit_allowlist_and_formats_values() -> None:
    output = format_structured_reservation(_reservation())

    expected_lines = (
        "Jméno klienta: TEST OSOBA",
        "Datum: 27.07.2030",
        "Čas od: 14:00",
        "Čas do: 15:45",
        "Služba nebo balíček: Testovací služba (105 min.)",
        "Počet osob: 1",
        "Cena: 1600.50",
        "Pracoviště: Testovací pracoviště",
        "Zaměstnanec: Testovací zaměstnanec",
        "Délka v minutách: 105",
        "E-mail: test@example.invalid",
        "Telefon: TEST-TELEFON",
        "Zdroj: Testovací zdroj",
        "Typ: Testovací typ",
        "Stav rezervace: Testovací stav",
        "Vytvořena: 25.07.2030 07:04",
        "Poznámka: Testovací poznámka\nDruhý testovací řádek",
    )
    assert output.startswith("----- Strukturovaná rezervace -----\n")
    assert output.endswith("\n----- Konec strukturované rezervace -----")
    for line in expected_lines:
        assert line in output
    for forbidden in (
        "NEVYPISOVAT TESTOVACÍ RAW DETAIL",
        "raw_detail",
        "first_name",
        "last_name",
        "package_name",
    ):
        assert forbidden not in output
    source = inspect.getsource(format_structured_reservation)
    for forbidden_call in ("repr(", "asdict(", "fields(", "__dict__", "json"):
        assert forbidden_call not in source


def test_legacy_compatibility_values_are_never_formatted() -> None:
    reservation = Reservation(
        first_name="NEVYPISOVAT TESTOVACÍ JMÉNO",
        last_name="NEVYPISOVAT TESTOVACÍ PŘÍJMENÍ",
        service="NEVYPISOVAT TESTOVACÍ SLUŽBU",
        package_name="NEVYPISOVAT TESTOVACÍ BALÍČEK",
    )

    output = format_structured_reservation(reservation)

    assert "NEVYPISOVAT" not in output


def test_none_values_are_printed_as_neuvedeno() -> None:
    output = format_structured_reservation(Reservation())
    assert output.count("Neuvedeno") == 17


@pytest.mark.parametrize("stage", ["structure", "extraction", "parser"])
def test_processing_error_prints_no_data_and_never_closes(
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
) -> None:
    page = MagicMock()
    initial = _structure("initial")
    fresh = _structure("fresh")
    finder = MagicMock(return_value=initial)
    extractor = MagicMock(
        return_value=ExtractedReservationData(
            fields={"Datum": "TAJNÁ TESTOVACÍ HODNOTA"},
            client_name="TEST OSOBA",
            raw_detail="TAJNÝ TESTOVACÍ DETAIL",
        )
    )
    parser = MagicMock(return_value=_reservation())
    if stage == "structure":
        finder.side_effect = ReservationExtractionError("DETAIL_STRUCTURE_NOT_UNIQUE")
    else:
        finder.side_effect = [initial, fresh]
    if stage == "extraction":
        extractor.side_effect = ReservationExtractionError("FIELD_STRUCTURE_AMBIGUOUS")
    if stage == "parser":
        parser.side_effect = ReservationParseError("INVALID_DATE")
    write = MagicMock()
    monkeypatch.setattr(inspection_module, "find_detail_structure", finder)
    monkeypatch.setattr(inspection_module, "extract_reservation_data", extractor)
    monkeypatch.setattr(inspection_module, "parse_reservation_fields", parser)

    with pytest.raises(ReservationProcessingError) as caught:
        inspect_open_detail(
            page,
            write=write,
            expand_detail=MagicMock(),
        )

    rendered = f"{caught.value!s} {caught.value!r}"
    for secret in (
        "TAJNÁ TESTOVACÍ HODNOTA",
        "TEST OSOBA",
        "TAJNÝ TESTOVACÍ DETAIL",
        "test@example.invalid",
    ):
        assert secret not in rendered
    write.assert_not_called()
    initial.close_control.click.assert_not_called()
    fresh.close_control.click.assert_not_called()


def test_parser_result_keeps_ambiguous_legacy_fields_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _structure("initial")
    fresh = _structure("fresh")
    extracted = ExtractedReservationData(
        fields={"Služba nebo balíček": "Testovací balíček nebo služba"},
        client_name="TEST OSOBA S VÍCE ČÁSTMI",
        raw_detail="OČIŠTĚNÝ TESTOVACÍ DETAIL",
    )
    monkeypatch.setattr(
        inspection_module,
        "find_detail_structure",
        MagicMock(side_effect=[initial, fresh]),
    )
    monkeypatch.setattr(
        inspection_module,
        "extract_reservation_data",
        MagicMock(return_value=extracted),
    )
    monkeypatch.setattr(inspection_module, "confirm_detail_closed", MagicMock())

    reservation = inspect_open_detail(
        MagicMock(),
        write=MagicMock(),
        flush_output=MagicMock(),
        expand_detail=MagicMock(),
    )

    assert reservation.client_name == "TEST OSOBA S VÍCE ČÁSTMI"
    assert reservation.service_or_package == "Testovací balíček nebo služba"
    assert reservation.first_name is None
    assert reservation.last_name is None
    assert reservation.service is None
    assert reservation.package_name is None


def test_playwright_error_is_sanitized_and_closes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _structure("initial")
    write = MagicMock()
    monkeypatch.setattr(
        inspection_module,
        "find_detail_structure",
        MagicMock(return_value=initial),
    )

    with pytest.raises(InspectionError) as caught:
        inspect_open_detail(
            MagicMock(),
            write=write,
            expand_detail=MagicMock(
                side_effect=Error("TEST OSOBA test@example.invalid Testovací poznámka")
            ),
        )

    assert str(caught.value) == "Operace s otevřeným detailem se nezdařila."
    assert "TEST OSOBA" not in repr(caught.value)
    write.assert_not_called()
    initial.close_control.click.assert_not_called()


def test_only_two_production_click_sites_and_no_click_in_extraction_or_parser() -> None:
    inspection_source = inspect.getsource(inspection_module)
    extraction_source = inspect.getsource(extraction_module)
    parsing_source = inspect.getsource(parsing_module)

    assert inspection_source.count(".click(") == 2
    assert ".click(" not in extraction_source
    assert ".click(" not in parsing_source
    assert MAX_SUCCESSFUL_EXPANSIONS == 10
