from datetime import date, datetime

from aiogram import F
from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
from bot.db import Block
from bot.salon import MASTERS, SERVICES, TEXTS, fmt_date, fmt_time

ANY_MASTER = "any"
CANCEL_FLOW = "cancel_flow"
CONFIRM = "confirm"
BLOCK_DAY = "block_day"
BLOCK_INTERVAL = "block_interval"

MENU_BUTTONS = {
    TEXTS[key]
    for key in ("btn_book", "btn_my_bookings", "btn_prices", "btn_contacts", "btn_cancel_flow")
}
# Текст, введённый на шаге сценария: не кнопка меню и не команда.
FREE_TEXT = F.text & ~F.text.in_(MENU_BUTTONS) & ~F.text.startswith("/")


class ServiceCb(CallbackData, prefix="svc"):
    id: str


class MasterCb(CallbackData, prefix="mst"):
    id: str


class DateCb(CallbackData, prefix="date"):
    value: str  # YYYY-MM-DD


class TimeCb(CallbackData, prefix="time"):
    value: str  # HHMM — двоеточие зарезервировано разделителем callback data


class BookingCb(CallbackData, prefix="bk"):
    action: str  # cancel | reschedule
    id: int


class UnblockCb(CallbackData, prefix="unblk"):
    id: int


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS["btn_book"]), KeyboardButton(text=TEXTS["btn_my_bookings"])],
            [KeyboardButton(text=TEXTS["btn_prices"]), KeyboardButton(text=TEXTS["btn_contacts"])],
        ],
        resize_keyboard=True,
    )


def phone_request() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=TEXTS["btn_send_phone"], request_contact=True)],
            [KeyboardButton(text=TEXTS["btn_cancel_flow"])],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def _with_cancel(builder: InlineKeyboardBuilder, *row_sizes: int) -> InlineKeyboardMarkup:
    builder.adjust(*row_sizes)
    builder.row(InlineKeyboardButton(text=TEXTS["btn_cancel_flow"], callback_data=CANCEL_FLOW))
    return builder.as_markup()


def services() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for service in SERVICES.values():
        builder.button(
            text=f"{service.name} · {service.price} {config.CURRENCY} · {service.duration} мин",
            callback_data=ServiceCb(id=service.id),
        )
    return _with_cancel(builder, 1)


def masters(with_any: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for master in MASTERS.values():
        builder.button(text=master.name, callback_data=MasterCb(id=master.id))
    if with_any:
        builder.button(text=TEXTS["btn_any_master"], callback_data=MasterCb(id=ANY_MASTER))
    return _with_cancel(builder, 2)


def dates(days: list[date]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for day in days:
        builder.button(text=fmt_date(day), callback_data=DateCb(value=day.isoformat()))
    return _with_cancel(builder, 3)


def times(slots: list[datetime]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for slot in slots:
        builder.button(text=fmt_time(slot), callback_data=TimeCb(value=f"{slot:%H%M}"))
    return _with_cancel(builder, 4)


def confirm() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_confirm"], callback_data=CONFIRM)
    return _with_cancel(builder, 1)


def booking_actions(booking_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_reschedule"], callback_data=BookingCb(action="reschedule", id=booking_id))
    builder.button(text=TEXTS["btn_cancel_booking"], callback_data=BookingCb(action="cancel", id=booking_id))
    return builder.as_markup()


def block_kind() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_block_day"], callback_data=BLOCK_DAY)
    builder.button(text=TEXTS["btn_block_interval"], callback_data=BLOCK_INTERVAL)
    return _with_cancel(builder, 2)


def unblock(block: Block) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=TEXTS["btn_unblock"], callback_data=UnblockCb(id=block.id))
    return builder.as_markup()
