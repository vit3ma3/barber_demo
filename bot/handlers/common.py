"""Главное меню, услуги, контакты и выход из любого сценария."""

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

import config
from bot import keyboards as kb
from bot.salon import SERVICES, TEXTS

router = Router()
# Подключается последним: отвечает на кнопки, которые не подошли ни одному обработчику.
fallback_router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = TEXTS["welcome"]
    if config.IS_DEMO:
        text += "\n\n" + TEXTS["demo_note"]
    await message.answer(text, reply_markup=kb.main_menu())


@router.message(F.text == TEXTS["btn_prices"])
async def prices(message: Message) -> None:
    lines = [
        TEXTS["price_line"].format(
            name=s.name, price=s.price, currency=config.CURRENCY, duration=s.duration
        )
        for s in SERVICES.values()
    ]
    await message.answer(TEXTS["prices_header"] + "\n".join(lines))


@router.message(F.text == TEXTS["btn_contacts"])
async def contacts(message: Message) -> None:
    await message.answer(TEXTS["contacts"])


@router.message(F.text == TEXTS["btn_cancel_flow"])
async def cancel_flow_by_text(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(TEXTS["flow_cancelled"], reply_markup=kb.main_menu())


@router.callback_query(F.data == kb.CANCEL_FLOW)
async def cancel_flow(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.delete()
    await call.message.answer(TEXTS["flow_cancelled"], reply_markup=kb.main_menu())
    await call.answer()


@fallback_router.callback_query()
async def stale_button(call: CallbackQuery) -> None:
    await call.answer(TEXTS["stale_button"], show_alert=True)
