"""Сценарий записи: услуга → мастер → дата → время → имя → телефон → подтверждение."""

import re
from datetime import date, datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.db import Database
from bot.handlers.admin import notify_admin
from bot.reminders import Reminders
from bot.salon import MASTERS, SERVICES, TEXTS, details, fmt_date
from bot.slots import booking_lock, find_free_times, upcoming_days
from bot.states import BookingFlow

router = Router()

PHONE_RE = re.compile(r"\+?[\d\s()\-]{10,20}")


def _candidates(master_id: str) -> list[str]:
    return list(MASTERS) if master_id == kb.ANY_MASTER else [master_id]


def _start_time(data: dict) -> datetime:
    return datetime.combine(
        date.fromisoformat(data["day"]), datetime.strptime(data["time"], "%H%M").time()
    )


@router.message(F.text == TEXTS["btn_book"])
async def start_booking(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(BookingFlow.service)
    await message.answer(TEXTS["choose_service"], reply_markup=kb.services())


@router.callback_query(BookingFlow.service, kb.ServiceCb.filter())
async def choose_service(call: CallbackQuery, callback_data: kb.ServiceCb, state: FSMContext) -> None:
    await state.update_data(service_id=callback_data.id)
    await state.set_state(BookingFlow.master)
    await call.message.edit_text(TEXTS["choose_master"], reply_markup=kb.masters())
    await call.answer()


@router.callback_query(BookingFlow.master, kb.MasterCb.filter())
async def choose_master(call: CallbackQuery, callback_data: kb.MasterCb, state: FSMContext) -> None:
    await state.update_data(master_id=callback_data.id)
    await state.set_state(BookingFlow.date)
    days = upcoming_days(_candidates(callback_data.id))
    await call.message.edit_text(TEXTS["choose_date"], reply_markup=kb.dates(days))
    await call.answer()


@router.callback_query(BookingFlow.date, kb.DateCb.filter())
async def choose_date(
    call: CallbackQuery, callback_data: kb.DateCb, state: FSMContext, db: Database
) -> None:
    data = await state.get_data()
    day = date.fromisoformat(callback_data.value)
    free = await find_free_times(db, day, SERVICES[data["service_id"]], _candidates(data["master_id"]))
    if not free:
        await call.answer(TEXTS["no_slots"], show_alert=True)
        return
    await state.update_data(day=callback_data.value)
    await state.set_state(BookingFlow.time)
    await call.message.edit_text(
        TEXTS["choose_time"].format(date=fmt_date(day)), reply_markup=kb.times(list(free))
    )
    await call.answer()


@router.callback_query(BookingFlow.time, kb.TimeCb.filter())
async def choose_time(call: CallbackQuery, callback_data: kb.TimeCb, state: FSMContext) -> None:
    await state.update_data(time=callback_data.value)
    await state.set_state(BookingFlow.name)
    await call.message.edit_text(TEXTS["ask_name"])
    await call.answer()


@router.message(BookingFlow.name, kb.FREE_TEXT)
async def enter_name(message: Message, state: FSMContext) -> None:
    name = message.text.strip()
    if not name or len(name) > 50:
        await message.answer(TEXTS["bad_name"])
        return
    await state.update_data(name=name)
    await state.set_state(BookingFlow.phone)
    await message.answer(TEXTS["ask_phone"], reply_markup=kb.phone_request())


@router.message(BookingFlow.phone, F.contact | kb.FREE_TEXT)
async def enter_phone(message: Message, state: FSMContext) -> None:
    if message.contact:
        phone = message.contact.phone_number
    else:
        phone = message.text.strip()
        digits = re.sub(r"\D", "", phone)
        if not PHONE_RE.fullmatch(phone) or not 10 <= len(digits) <= 15:
            await message.answer(TEXTS["bad_phone"])
            return
    await state.update_data(phone=phone)
    await state.set_state(BookingFlow.confirm)

    data = await state.get_data()
    master_id = data["master_id"]
    master_name = TEXTS["btn_any_master"] if master_id == kb.ANY_MASTER else MASTERS[master_id].name
    text = details(SERVICES[data["service_id"]], master_name, _start_time(data))
    await message.answer(TEXTS["confirm"].format(details=text), reply_markup=kb.confirm())


@router.callback_query(BookingFlow.confirm, F.data == kb.CONFIRM)
async def confirm(
    call: CallbackQuery, state: FSMContext, db: Database, reminders: Reminders
) -> None:
    data = await state.get_data()
    service = SERVICES[data["service_id"]]
    start = _start_time(data)

    async with booking_lock:
        free = await find_free_times(db, start.date(), service, _candidates(data["master_id"]))
        free_masters = free.get(start)
        if not free_masters:
            await state.set_state(BookingFlow.date)
            days = upcoming_days(_candidates(data["master_id"]))
            await call.message.edit_text(TEXTS["slot_taken"], reply_markup=kb.dates(days))
            await call.answer()
            return
        booking = await db.add_booking(
            user_id=call.from_user.id,
            client_name=data["name"],
            phone=data["phone"],
            service_id=service.id,
            master_id=free_masters[0],
            start=start,
            end=start + timedelta(minutes=service.duration),
        )

    reminders.schedule(booking)
    await state.clear()

    text = details(service, MASTERS[booking.master_id].name, booking.start)
    await call.message.delete()
    await call.message.answer(TEXTS["booked"].format(details=text), reply_markup=kb.main_menu())
    await call.answer()
    await notify_admin(
        call.bot,
        TEXTS["admin_new"].format(details=text, name=booking.client_name, phone=booking.phone),
    )
