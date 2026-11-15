"""Данные салона из config.py в удобном для кода виде и форматирование."""

from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import config

TZ = ZoneInfo(config.TIMEZONE)
TEXTS = config.TEXTS


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    price: int
    duration: int  # минуты


@dataclass(frozen=True)
class Master:
    id: str
    name: str
    schedule: dict[int, tuple[time, time]]

    def work_hours(self, day: date) -> tuple[time, time] | None:
        return self.schedule.get(day.weekday())


SERVICES = {s["id"]: Service(**s) for s in config.SERVICES}
MASTERS = {
    m["id"]: Master(
        id=m["id"],
        name=m["name"],
        schedule={
            weekday: (time.fromisoformat(start), time.fromisoformat(end))
            for weekday, (start, end) in m["schedule"].items()
        },
    )
    for m in config.MASTERS
}


def now() -> datetime:
    """Текущее время салона без tzinfo — в таком виде время хранится в БД."""
    return datetime.now(TZ).replace(tzinfo=None, microsecond=0)


def fmt_date(day: date) -> str:
    return f"{day:%d.%m} ({config.WEEKDAY_NAMES[day.weekday()]})"


def fmt_time(moment: datetime | time) -> str:
    return f"{moment:%H:%M}"


def details(service: Service, master_name: str, start: datetime) -> str:
    return TEXTS["details"].format(
        service=service.name,
        master=master_name,
        date=fmt_date(start.date()),
        time=fmt_time(start),
        price=service.price,
        currency=config.CURRENCY,
    )
