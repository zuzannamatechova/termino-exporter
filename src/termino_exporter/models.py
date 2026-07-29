"""Domain models used by Termino Exporter."""

from dataclasses import dataclass
from datetime import date as Date
from datetime import time as Time
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Reservation:
    """Information read from one client reservation."""

    reservation_id: str | None = None
    date: Date | None = None
    start_time: Time | None = None
    end_time: Time | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    service: str | None = None
    package_name: str | None = None
    workplace: str | None = None
    duration_minutes: int | None = None
    price: Decimal | None = None
    status: str | None = None
    source: str | None = None
    note: str | None = None
    raw_detail: str | None = None
