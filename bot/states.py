from aiogram.fsm.state import State, StatesGroup


class BookingFlow(StatesGroup):
    service = State()
    master = State()
    date = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()


class RescheduleFlow(StatesGroup):
    date = State()
    time = State()


class BlockFlow(StatesGroup):
    master = State()
    date = State()
    kind = State()
    interval = State()
