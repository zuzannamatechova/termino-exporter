from dataclasses import FrozenInstanceError
from datetime import date, datetime, time
from decimal import Decimal
from typing import get_type_hints

import pytest

import termino_exporter
from termino_exporter.models import Reservation


def test_package_can_be_imported() -> None:
    assert termino_exporter.__version__ == "0.1.0"


def test_reservation_can_be_created_without_values() -> None:
    assert Reservation().reservation_id is None


def test_reservation_date_annotation_can_be_evaluated() -> None:
    assert get_type_hints(Reservation)["date"] == date | None


def test_reservation_can_be_created_with_invented_values() -> None:
    reservation = Reservation(
        reservation_id="TEST-001",
        date=date(2030, 1, 15),
        start_time=time(10, 0),
        end_time=time(11, 0),
        client_name="TEST OSOBA",
        phone="TEST-TELEFON",
        email="test@example.invalid",
        service_or_package="Testovací služba",
        people_count=1,
        employee="Testovací zaměstnanec",
        reservation_type="Testovací typ",
        created_at=datetime(2030, 1, 1, 9, 30),
        duration_minutes=60,
        price=Decimal("1200.00"),
    )

    assert reservation.client_name == "TEST OSOBA"
    assert reservation.price == Decimal("1200.00")


def test_reservation_is_immutable() -> None:
    reservation = Reservation()

    with pytest.raises(FrozenInstanceError):
        reservation.client_name = "JINÁ TEST OSOBA"  # type: ignore[misc]
