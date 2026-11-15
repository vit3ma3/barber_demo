"""Точка входа: python -m bot"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, BotCommandScopeChat

from bot.db import Database
from bot.handlers import admin, booking, common, my_bookings
from bot.reminders import Reminders
from bot.salon import TEXTS
from bot.settings import settings

logger = logging.getLogger(__name__)


async def set_commands(bot: Bot) -> None:
    start = BotCommand(command="start", description=TEXTS["cmd_start"])
    await bot.set_my_commands([start])
    try:
        await bot.set_my_commands(
            [
                start,
                BotCommand(command="today", description=TEXTS["cmd_today"]),
                BotCommand(command="tomorrow", description=TEXTS["cmd_tomorrow"]),
                BotCommand(command="block", description=TEXTS["cmd_block"]),
                BotCommand(command="blocks", description=TEXTS["cmd_blocks"]),
            ],
            scope=BotCommandScopeChat(chat_id=settings.admin_id),
        )
    except TelegramAPIError:
        logger.warning("Не удалось задать команды администратора: он ещё не запускал бота?")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    db = Database(settings.db_path)
    await db.connect()
    bot = Bot(settings.bot_token)
    reminders = Reminders(bot, db)
    await reminders.restore()
    reminders.start()

    dp = Dispatcher()
    # Порядок важен: кнопки меню и команды должны срабатывать раньше
    # текстовых шагов сценариев, а fallback — последним.
    dp.include_routers(
        common.router,
        admin.router,
        booking.router,
        my_bookings.router,
        common.fallback_router,
    )

    try:
        await set_commands(bot)
        await dp.start_polling(bot, db=db, reminders=reminders)
    finally:
        reminders.shutdown()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
