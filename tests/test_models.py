from dataclasses import FrozenInstanceError
from datetime import date, time
from decimal import Decimal

import pytest

import termino_exporter
from termino_exporter.models import Reservation


def test_package_can_be_imported() -> None:
    assert termino_exporter.__version__ == "0.1.0"


def test_reservation_can_be_created_without_values() -> None:
    assert Reservation().reservation_id is None


def test_reservation_can_be_created_with_invented_values() -> None:
    reservation = Reservation(
        reservation_id="TEST-001",
        date=date(2030, 1, 15),
        start_time=time(10, 0),
        end_time=time(11, 0),
        first_name="Anna",
        last_name="Testová",
        phone="+420 700 000 001",
        email="anna.testova@example.com",
        service="Testovací služba",
        duration_minutes=60,
        price=Decimal("1200.00"),
    )

    assert reservation.first_name == "Anna"
    assert reservation.price == Decimal("1200.00")


def test_reservation_is_immutable() -> None:
    reservation = Reservation()

    with pytest.raises(FrozenInstanceError):
        reservation.first_name = "Jana"  # type: ignore[misc]
