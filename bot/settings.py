"""Секреты и параметры окружения из .env."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_id: int
    db_path: str


def _load() -> Settings:
    token = os.getenv("BOT_TOKEN")
    admin_id = os.getenv("ADMIN_ID")
    if not token or not admin_id:
        raise RuntimeError("Заполните BOT_TOKEN и ADMIN_ID в файле .env (образец — .env.example)")
    return Settings(bot_token=token, admin_id=int(admin_id), db_path=os.getenv("DB_PATH", "barber.db"))


settings = _load()
