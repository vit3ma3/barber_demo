"""Хранение записей и закрытого времени в SQLite.

Время хранится строкой ISO в часовом поясе салона (без tzinfo),
поэтому строки можно сравнивать прямо в SQL.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import aiosqlite

SCHEMA = """
CREATE TABLE IF NOT EXISTS bookings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    client_name TEXT    NOT NULL,
    phone       TEXT    NOT NULL,
    service_id  TEXT    NOT NULL,
    master_id   TEXT    NOT NULL,
    start_at    TEXT    NOT NULL,
    end_at      TEXT    NOT NULL,
    status      TEXT    NOT NULL DEFAULT 'active',
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bookings_master_start ON bookings (master_id, start_at);
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings (user_id);

CREATE TABLE IF NOT EXISTS blocks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    master_id TEXT NOT NULL,
    start_at  TEXT NOT NULL,
    end_at    TEXT NOT NULL
);
"""

Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class Booking:
    id: int
    user_id: int
    client_name: str
    phone: str
    service_id: str
    master_id: str
    start: datetime
    end: datetime
    status: str

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Booking":
        return cls(
            id=row["id"],
            user_id=row["user_id"],
            client_name=row["client_name"],
            phone=row["phone"],
            service_id=row["service_id"],
            master_id=row["master_id"],
            start=datetime.fromisoformat(row["start_at"]),
            end=datetime.fromisoformat(row["end_at"]),
            status=row["status"],
        )


@dataclass(frozen=True)
class Block:
    id: int
    master_id: str
    start: datetime
    end: datetime

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "Block":
        return cls(
            id=row["id"],
            master_id=row["master_id"],
            start=datetime.fromisoformat(row["start_at"]),
            end=datetime.fromisoformat(row["end_at"]),
        )


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "Database.connect() не вызван"
        return self._conn

    # --- Записи --------------------------------------------------------------

    async def add_booking(
        self,
        user_id: int,
        client_name: str,
        phone: str,
        service_id: str,
        master_id: str,
        start: datetime,
        end: datetime,
    ) -> Booking:
        cursor = await self.conn.execute(
            "INSERT INTO bookings (user_id, client_name, phone, service_id, master_id, start_at, end_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, client_name, phone, service_id, master_id, start.isoformat(), end.isoformat()),
        )
        await self.conn.commit()
        booking = await self.get_booking(cursor.lastrowid)
        assert booking is not None
        return booking

    async def get_booking(self, booking_id: int) -> Booking | None:
        cursor = await self.conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,))
        row = await cursor.fetchone()
        return Booking.from_row(row) if row else None

    async def user_upcoming(self, user_id: int, now: datetime) -> list[Booking]:
        cursor = await self.conn.execute(
            "SELECT * FROM bookings WHERE user_id = ? AND status = 'active' AND start_at > ?"
            " ORDER BY start_at",
            (user_id, now.isoformat()),
        )
        return [Booking.from_row(row) for row in await cursor.fetchall()]

    async def future_active(self, now: datetime) -> list[Booking]:
        cursor = await self.conn.execute(
            "SELECT * FROM bookings WHERE status = 'active' AND start_at > ?",
            (now.isoformat(),),
        )
        return [Booking.from_row(row) for row in await cursor.fetchall()]

    async def bookings_on(self, day: date) -> list[Booking]:
        start, end = _day_bounds(day)
        cursor = await self.conn.execute(
            "SELECT * FROM bookings WHERE status = 'active' AND start_at >= ? AND start_at < ?"
            " ORDER BY start_at, master_id",
            (start.isoformat(), end.isoformat()),
        )
        return [Booking.from_row(row) for row in await cursor.fetchall()]

    async def cancel_booking(self, booking_id: int) -> None:
        await self.conn.execute("UPDATE bookings SET status = 'cancelled' WHERE id = ?", (booking_id,))
        await self.conn.commit()

    async def reschedule_booking(self, booking_id: int, start: datetime, end: datetime) -> Booking:
        await self.conn.execute(
            "UPDATE bookings SET start_at = ?, end_at = ? WHERE id = ?",
            (start.isoformat(), end.isoformat(), booking_id),
        )
        await self.conn.commit()
        booking = await self.get_booking(booking_id)
        assert booking is not None
        return booking

    async def count_overlapping_bookings(self, master_id: str, start: datetime, end: datetime) -> int:
        cursor = await self.conn.execute(
            "SELECT COUNT(*) FROM bookings WHERE master_id = ? AND status = 'active'"
            " AND start_at < ? AND end_at > ?",
            (master_id, end.isoformat(), start.isoformat()),
        )
        (count,) = await cursor.fetchone()
        return count

    # --- Занятость мастера ---------------------------------------------------

    async def busy_intervals(
        self, master_id: str, day: date, exclude_booking_id: int | None = None
    ) -> list[Interval]:
        """Записи и закрытое время мастера, пересекающиеся с днём."""
        start, end = _day_bounds(day)
        params = (master_id, end.isoformat(), start.isoformat())
        cursor = await self.conn.execute(
            "SELECT start_at, end_at FROM bookings WHERE master_id = ? AND status = 'active'"
            " AND start_at < ? AND end_at > ? AND id != ?",
            (*params, exclude_booking_id or 0),
        )
        rows = list(await cursor.fetchall())
        cursor = await self.conn.execute(
            "SELECT start_at, end_at FROM blocks WHERE master_id = ? AND start_at < ? AND end_at > ?",
            params,
        )
        rows += await cursor.fetchall()
        return [(datetime.fromisoformat(s), datetime.fromisoformat(e)) for s, e in rows]

    # --- Закрытое время ------------------------------------------------------

    async def add_block(self, master_id: str, start: datetime, end: datetime) -> Block:
        cursor = await self.conn.execute(
            "INSERT INTO blocks (master_id, start_at, end_at) VALUES (?, ?, ?)",
            (master_id, start.isoformat(), end.isoformat()),
        )
        await self.conn.commit()
        return Block(id=cursor.lastrowid, master_id=master_id, start=start, end=end)

    async def future_blocks(self, now: datetime) -> list[Block]:
        cursor = await self.conn.execute(
            "SELECT * FROM blocks WHERE end_at > ? ORDER BY start_at", (now.isoformat(),)
        )
        return [Block.from_row(row) for row in await cursor.fetchall()]

    async def delete_block(self, block_id: int) -> Block | None:
        cursor = await self.conn.execute("SELECT * FROM blocks WHERE id = ?", (block_id,))
        row = await cursor.fetchone()
        if row is None:
            return None
        await self.conn.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
        await self.conn.commit()
        return Block.from_row(row)


def _day_bounds(day: date) -> Interval:
    start = datetime.combine(day, datetime.min.time())
    return start, start + timedelta(days=1)
