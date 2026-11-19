"""«Мои записи»: список, отмена и перенос."""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot.db import Booking, Database
from bot.handlers.admin import notify_admin
from bot.reminders import Reminders
from bot.salon import MASTERS, SERVICES, TEXTS, details, fmt_date, fmt_time, now
from bot.slots import booking_lock, find_free_times, upcoming_days
from bot.states import RescheduleFlow

router = Router()


def _details(booking: Booking) -> str:
    return details(SERVICES[booking.service_id], MASTERS[booking.master_id].name, booking.start)


async def _own_upcoming(db: Database, booking_id: int, user_id: int) -> Booking | None:
    booking = await db.get_booking(booking_id)
    if (
        booking is None
        or booking.user_id != user_id
        or booking.status != "active"
        or booking.start <= now()
    ):
        return None
    return booking


@router.message(F.text == TEXTS["btn_my_bookings"])
async def my_bookings(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    bookings = await db.user_upcoming(message.from_user.id, now())
    if not bookings:
        await message.answer(TEXTS["no_bookings"])
        return
    await message.answer(TEXTS["my_bookings"])
    for booking in bookings:
        await message.answer(_details(booking), reply_markup=kb.booking_actions(booking.id))


@router.callback_query(kb.BookingCb.filter(F.action == "cancel"))
async def cancel_booking(
    call: CallbackQuery, callback_data: kb.BookingCb, db: Database, reminders: Reminders
) -> None:
    booking = await _own_upcoming(db, callback_data.id, call.from_user.id)
    if booking is None:
        await call.answer(TEXTS["booking_unavailable"], show_alert=True)
        return
    await db.cancel_booking(booking.id)
    reminders.cancel(booking.id)

    text = _details(booking)
    await call.message.edit_text(TEXTS["booking_cancelled"].format(details=text))
    await call.answer()
    await notify_admin(
        call.bot,
        TEXTS["admin_cancelled"].format(details=text, name=booking.client_name, phone=booking.phone),
    )


@router.callback_query(kb.BookingCb.filter(F.action == "reschedule"))
async def start_reschedule(
    call: CallbackQuery, callback_data: kb.BookingCb, state: FSMContext, db: Database
) -> None:
    booking = await _own_upcoming(db, callback_data.id, call.from_user.id)
    if booking is None:
        await call.answer(TEXTS["booking_unavailable"], show_alert=True)
        return
    await state.clear()
    await state.update_data(booking_id=booking.id)
    await state.set_state(RescheduleFlow.date)
    days = upcoming_days([booking.master_id])
    await call.message.edit_text(TEXTS["choose_date"], reply_markup=kb.dates(days))
    await call.answer()


async def _free_times(db: Database, booking: Booking, day: date) -> dict[datetime, list[str]]:
    # Мастер и услуга остаются прежними; текущая запись не считается занятой.
    return await find_free_times(
        db, day, SERVICES[booking.service_id], [booking.master_id], exclude_booking_id=booking.id
    )


@router.callback_query(RescheduleFlow.date, kb.DateCb.filter())
async def reschedule_date(
    call: CallbackQuery, callback_data: kb.DateCb, state: FSMContext, db: Database
) -> None:
    data = await state.get_data()
    booking = await _own_upcoming(db, data["booking_id"], call.from_user.id)
    if booking is None:
        await state.clear()
        await call.answer(TEXTS["booking_unavailable"], show_alert=True)
        return
    day = date.fromisoformat(callback_data.value)
    free = await _free_times(db, booking, day)
    if not free:
        await call.answer(TEXTS["no_slots"], show_alert=True)
        return
    await state.update_data(day=callback_data.value)
    await state.set_state(RescheduleFlow.time)
    await call.message.edit_text(
        TEXTS["choose_time"].format(date=fmt_date(day)), reply_markup=kb.times(list(free))
    )
    await call.answer()


@router.callback_query(RescheduleFlow.time, kb.TimeCb.filter())
async def reschedule_time(
    call: CallbackQuery,
    callback_data: kb.TimeCb,
    state: FSMContext,
    db: Database,
    reminders: Reminders,
) -> None:
    data = await state.get_data()
    start = datetime.combine(
        date.fromisoformat(data["day"]), datetime.strptime(callback_data.value, "%H%M").time()
    )

    async with booking_lock:
        old = await _own_upcoming(db, data["booking_id"], call.from_user.id)
        if old is None:
            await state.clear()
            await call.answer(TEXTS["booking_unavailable"], show_alert=True)
            return
        if start not in await _free_times(db, old, start.date()):
            await state.set_state(RescheduleFlow.date)
            days = upcoming_days([old.master_id])
            await call.message.edit_text(TEXTS["slot_taken"], reply_markup=kb.dates(days))
            await call.answer()
            return
        duration = old.end - old.start
        booking = await db.reschedule_booking(old.id, start, start + duration)

    reminders.schedule(booking)
    await state.clear()

    text = _details(booking)
    await call.message.edit_text(TEXTS["rescheduled"].format(details=text))
    await call.answer()
    await notify_admin(
        call.bot,
        TEXTS["admin_rescheduled"].format(
            old=f"{fmt_date(old.start.date())}, {fmt_time(old.start)}",
            details=text,
            name=booking.client_name,
            phone=booking.phone,
        ),
    )
