"""Расчёт свободного времени для записи."""

import asyncio
from datetime import date, datetime, time, timedelta

import config
from bot.db import Database, Interval
from bot.salon import MASTERS, Service, now

# Повторная проверка слота и сохранение записи выполняются под этой блокировкой,
# чтобы два клиента не заняли одно время одновременно.
booking_lock = asyncio.Lock()


def free_starts(
    day: date,
    work_hours: tuple[time, time] | None,
    duration: int,
    step: int,
    busy: list[Interval],
    current: datetime,
) -> list[datetime]:
    """Время начала, с которого услуга длительностью `duration` минут
    целиком помещается в рабочие часы и не пересекается с занятым временем."""
    if work_hours is None:
        return []
    start = datetime.combine(day, work_hours[0])
    close = datetime.combine(day, work_hours[1])
    length = timedelta(minutes=duration)

    result = []
    slot = start
    while slot + length <= close:
        end = slot + length
        if slot > current and all(end <= b_start or slot >= b_end for b_start, b_end in busy):
            result.append(slot)
        slot += timedelta(minutes=step)
    return result


async def find_free_times(
    db: Database,
    day: date,
    service: Service,
    master_ids: list[str],
    exclude_booking_id: int | None = None,
) -> dict[datetime, list[str]]:
    """Свободное время → мастера (в порядке из config.py), свободные в это время."""
    result: dict[datetime, list[str]] = {}
    current = now()
    for master_id in master_ids:
        busy = await db.busy_intervals(master_id, day, exclude_booking_id)
        starts = free_starts(
            day,
            MASTERS[master_id].work_hours(day),
            service.duration,
            config.SLOT_STEP_MINUTES,
            busy,
            current,
        )
        for slot in starts:
            result.setdefault(slot, []).append(master_id)
    return dict(sorted(result.items()))


def upcoming_days(master_ids: list[str]) -> list[date]:
    """Ближайшие дни, в которые работает хотя бы один из мастеров."""
    today = now().date()
    days = [today + timedelta(days=i) for i in range(config.BOOKING_DAYS_AHEAD)]
    return [day for day in days if any(MASTERS[m].work_hours(day) for m in master_ids)]
