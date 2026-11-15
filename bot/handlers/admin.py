"""Команды администратора и уведомления ему."""

import logging
import re
from datetime import date, datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.db import Block, Database
from bot.salon import MASTERS, SERVICES, TEXTS, fmt_date, fmt_time, now
from bot.settings import settings
from bot.slots import upcoming_days
from bot.states import BlockFlow

logger = logging.getLogger(__name__)

router = Router()
router.message.filter(F.from_user.id == settings.admin_id)
router.callback_query.filter(F.from_user.id == settings.admin_id)

INTERVAL_RE = re.compile(r"(\d{1,2}):(\d{2})\s*[-–]\s*(\d{1,2}):(\d{2})")


async def notify_admin(bot: Bot, text: str) -> None:
    try:
        await bot.send_message(settings.admin_id, text)
    except TelegramAPIError:
        # Например, админ ещё не запускал бота. Запись клиента от этого не должна ломаться.
        logger.exception("Не удалось отправить уведомление администратору")


def fmt_block(block: Block) -> str:
    if block.start.time() == time(0) and block.end - block.start == timedelta(days=1):
        period = TEXTS["admin_whole_day"]
    else:
        period = f"{fmt_time(block.start)}–{fmt_time(block.end)}"
    return f"{MASTERS[block.master_id].name}, {fmt_date(block.start.date())}, {period}"


# --- Записи на день --------------------------------------------------------


async def _day_report(db: Database, day: date) -> str:
    bookings = await db.bookings_on(day)
    if not bookings:
        return TEXTS["admin_day_empty"].format(date=fmt_date(day))
    lines = [
        TEXTS["admin_day_line"].format(
            start=fmt_time(b.start),
            end=fmt_time(b.end),
            master=MASTERS[b.master_id].name,
            service=SERVICES[b.service_id].name,
            name=b.client_name,
            phone=b.phone,
        )
        for b in bookings
    ]
    return TEXTS["admin_day_header"].format(date=fmt_date(day)) + "\n\n".join(lines)


@router.message(Command("today"))
async def today(message: Message, db: Database) -> None:
    await message.answer(await _day_report(db, now().date()))


@router.message(Command("tomorrow"))
async def tomorrow(message: Message, db: Database) -> None:
    await message.answer(await _day_report(db, now().date() + timedelta(days=1)))


# --- Закрытие времени ------------------------------------------------------


@router.message(Command("block"))
async def block_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BlockFlow.master)
    await message.answer(TEXTS["admin_block_master"], reply_markup=kb.masters(with_any=False))


@router.callback_query(BlockFlow.master, kb.MasterCb.filter())
async def block_master(call: CallbackQuery, callback_data: kb.MasterCb, state: FSMContext) -> None:
    await state.update_data(master_id=callback_data.id)
    await state.set_state(BlockFlow.date)
    await call.message.edit_text(TEXTS["choose_date"], reply_markup=kb.dates(upcoming_days()))
    await call.answer()


@router.callback_query(BlockFlow.date, kb.DateCb.filter())
async def block_date(call: CallbackQuery, callback_data: kb.DateCb, state: FSMContext) -> None:
    await state.update_data(day=callback_data.value)
    await state.set_state(BlockFlow.kind)
    await call.message.edit_text(TEXTS["admin_block_kind"], reply_markup=kb.block_kind())
    await call.answer()


@router.callback_query(BlockFlow.kind, F.data == kb.BLOCK_DAY)
async def block_whole_day(call: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    start = datetime.combine(date.fromisoformat(data["day"]), time(0))
    text = await _save_block(db, state, data["master_id"], start, start + timedelta(days=1))
    await call.message.edit_text(text)
    await call.answer()


@router.callback_query(BlockFlow.kind, F.data == kb.BLOCK_INTERVAL)
async def block_interval_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BlockFlow.interval)
    await call.message.edit_text(TEXTS["admin_ask_interval"])
    await call.answer()


@router.message(BlockFlow.interval, kb.FREE_TEXT)
async def block_interval(message: Message, state: FSMContext, db: Database) -> None:
    interval = _parse_interval(message.text)
    if interval is None:
        await message.answer(TEXTS["admin_bad_interval"])
        return
    start_time, end_time = interval

    data = await state.get_data()
    day = date.fromisoformat(data["day"])
    text = await _save_block(
        db,
        state,
        data["master_id"],
        datetime.combine(day, start_time),
        datetime.combine(day, end_time),
    )
    await message.answer(text)


def _parse_interval(text: str) -> tuple[time, time] | None:
    match = INTERVAL_RE.fullmatch(text.strip())
    if match is None:
        return None
    h1, m1, h2, m2 = map(int, match.groups())
    try:
        start, end = time(h1, m1), time(h2, m2)
    except ValueError:
        return None
    return (start, end) if start < end else None


async def _save_block(
    db: Database, state: FSMContext, master_id: str, start: datetime, end: datetime
) -> str:
    block = await db.add_block(master_id, start, end)
    await state.clear()
    text = TEXTS["admin_blocked"].format(block=fmt_block(block))
    conflicts = await db.count_overlapping_bookings(master_id, start, end)
    if conflicts:
        text += TEXTS["admin_block_conflicts"].format(count=conflicts)
    return text


@router.message(Command("blocks"))
async def list_blocks(message: Message, db: Database) -> None:
    blocks = await db.future_blocks(now())
    if not blocks:
        await message.answer(TEXTS["admin_no_blocks"])
        return
    await message.answer(TEXTS["admin_blocks_header"])
    for block in blocks:
        await message.answer(fmt_block(block), reply_markup=kb.unblock(block))


@router.callback_query(kb.UnblockCb.filter())
async def unblock(call: CallbackQuery, callback_data: kb.UnblockCb, db: Database) -> None:
    block = await db.delete_block(callback_data.id)
    if block is None:
        await call.answer(TEXTS["stale_button"], show_alert=True)
        return
    await call.message.edit_text(TEXTS["admin_unblocked"].format(block=fmt_block(block)))
    await call.answer()
