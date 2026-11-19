from datetime import date, datetime, time

from bot.slots import free_starts

DAY = date(2026, 11, 16)
WORK = (time(10, 0), time(13, 0))
BEFORE_DAY = datetime(2026, 11, 15, 12, 0)


def at(hour: int, minute: int = 0) -> datetime:
    return datetime.combine(DAY, time(hour, minute))


def test_free_day_has_slots_until_service_fits_before_close():
    starts = free_starts(DAY, WORK, duration=60, step=30, busy=[], current=BEFORE_DAY)
    assert starts == [at(10), at(10, 30), at(11), at(11, 30), at(12)]


def test_day_off_has_no_slots():
    assert free_starts(DAY, None, duration=30, step=30, busy=[], current=BEFORE_DAY) == []


def test_busy_interval_blocks_overlapping_slots_but_not_adjacent():
    busy = [(at(11), at(12))]
    starts = free_starts(DAY, WORK, duration=60, step=30, busy=busy, current=BEFORE_DAY)
    # 10:30 заходит на 11:00, 11:00 и 11:30 внутри; 10:00 кончается ровно в 11:00, 12:00 начинается ровно в 12:00.
    assert starts == [at(10), at(12)]


def test_long_service_needs_whole_gap():
    busy = [(at(11), at(11, 30))]
    starts = free_starts(DAY, WORK, duration=90, step=30, busy=busy, current=BEFORE_DAY)
    assert starts == [at(11, 30)]


def test_past_slots_are_hidden():
    starts = free_starts(DAY, WORK, duration=30, step=30, busy=[], current=at(11, 10))
    assert starts == [at(11, 30), at(12), at(12, 30)]


def test_upcoming_days_skip_days_off(monkeypatch):
    import bot.slots as slots
    from bot.salon import Master

    work = {0: WORK, 2: WORK}  # пн и ср
    monkeypatch.setattr(slots, "now", lambda: datetime(2026, 11, 16, 9, 0))  # пн
    monkeypatch.setattr(slots, "MASTERS", {
        "a": Master(id="a", name="A", schedule=work),
        "b": Master(id="b", name="B", schedule={1: WORK}),  # вт
    })
    monkeypatch.setattr(slots.config, "BOOKING_DAYS_AHEAD", 7)

    assert slots.upcoming_days(["a"]) == [date(2026, 11, 16), date(2026, 11, 18)]
    # «Любой мастер» — дни, когда работает хотя бы один.
    assert slots.upcoming_days(["a", "b"]) == [date(2026, 11, 16), date(2026, 11, 17), date(2026, 11, 18)]
