"""Напоминания клиентам о визите.

Задачи живут в памяти планировщика, а при запуске бота
восстанавливаются из базы по будущим записям.
"""

import logging
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config
from bot.db import Booking, Database
from bot.salon import MASTERS, SERVICES, TEXTS, TZ, details, now

logger = logging.getLogger(__name__)


class Reminders:
    def __init__(self, bot: Bot, db: Database) -> None:
        self.bot = bot
        self.db = db
        self.scheduler = AsyncIOScheduler(timezone=TZ)

    def start(self) -> None:
        self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.shutdown(wait=False)

    async def restore(self) -> None:
        for booking in await self.db.future_active(now()):
            self.schedule(booking)

    def schedule(self, booking: Booking) -> None:
        self.cancel(booking.id)
        current = now()
        for hours in config.REMINDER_HOURS:
            run_at = booking.start - timedelta(hours=hours)
            if run_at <= current:
                continue
            self.scheduler.add_job(
                self._send,
                "date",
                run_date=run_at.replace(tzinfo=TZ),
                args=[booking.id, hours],
                id=_job_id(booking.id, hours),
            )

    def cancel(self, booking_id: int) -> None:
        for hours in config.REMINDER_HOURS:
            try:
                self.scheduler.remove_job(_job_id(booking_id, hours))
            except JobLookupError:
                pass

    async def _send(self, booking_id: int, hours: int) -> None:
        booking = await self.db.get_booking(booking_id)
        if booking is None or booking.status != "active":
            return
        text = TEXTS["reminder"].format(
            hours=hours,
            details=details(SERVICES[booking.service_id], MASTERS[booking.master_id].name, booking.start),
        )
        try:
            await self.bot.send_message(booking.user_id, text)
        except TelegramAPIError:
            logger.exception("Не удалось отправить напоминание по записи %s", booking_id)


def _job_id(booking_id: int, hours: int) -> str:
    return f"reminder:{booking_id}:{hours}"
