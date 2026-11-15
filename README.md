# Telegram-бот записи в барбершоп (демо)

Бот для онлайн-записи клиентов в салон. Демо работает на вымышленном «Барбершопе Север»,
а под реальный салон бот перенастраивается правкой одного файла — `config.py`.

**Стек:** Python 3.11+, aiogram 3, SQLite (aiosqlite), APScheduler.

## Возможности

**Клиент**
- главное меню: «Записаться», «Мои записи», «Услуги и цены», «Контакты»;
- запись по шагам: услуга → мастер или «Любой» → дата (ближайшие 7 дней) → свободное время →
  имя → телефон (кнопкой «Отправить номер» или вручную) → подтверждение;
- свободное время считается с учётом длительности услуги, графика мастера,
  уже занятых записей и закрытого администратором времени;
- «Мои записи»: отмена и перенос на другое время;
- напоминания за 24 и за 2 часа до визита.

**Администратор** (Telegram ID из `.env`)
- уведомления о новых записях, отменах и переносах;
- `/today`, `/tomorrow` — записи на сегодня и завтра;
- `/block` — закрыть время мастера: весь день или интервал (перерыв, выходной);
- `/blocks` — список закрытого времени с кнопкой «Открыть».

## Структура

```
config.py              # все настройки салона: услуги, мастера, график, тексты
bot/
├── __main__.py        # точка входа: python -m bot
├── settings.py        # чтение .env
├── salon.py           # данные из config.py в удобном виде, форматирование
├── db.py              # SQLite: записи и закрытое время
├── slots.py           # расчёт свободного времени
├── reminders.py       # напоминания через APScheduler
├── keyboards.py       # клавиатуры и callback data
├── states.py          # FSM-состояния сценариев
└── handlers/
    ├── common.py      # /start, услуги, контакты, отмена сценария
    ├── booking.py     # сценарий записи
    ├── my_bookings.py # мои записи: отмена и перенос
    └── admin.py       # команды и уведомления администратора
deploy/barber-bot.service  # unit-файл systemd
tests/test_slots.py        # тесты расчёта слотов
```

## Запуск локально

1. Создайте бота у [@BotFather](https://t.me/BotFather) и получите токен.
   Свой Telegram ID можно узнать у [@userinfobot](https://t.me/userinfobot).
2. Установите зависимости:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
3. Создайте `.env` по образцу и впишите токен и ID:
   ```bash
   cp .env.example .env
   ```
4. Запустите бота:
   ```bash
   python -m bot
   ```

Чтобы бот мог присылать администратору уведомления, администратор должен хотя бы раз нажать в нём /start.

Тесты:
```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Как настроить под другой салон

Всё меняется в `config.py`:

- `SALON_NAME`, `ADDRESS`, `PHONE`, `WORKING_HOURS` — данные салона;
- `IS_DEMO = False` — убрать пометку «демо» из приветствия;
- `TIMEZONE` — часовой пояс салона;
- `SLOT_STEP_MINUTES`, `BOOKING_DAYS_AHEAD`, `REMINDER_HOURS` — шаг сетки, горизонт записи, напоминания;
- `SERVICES` — услуги: название, цена, длительность в минутах;
- `MASTERS` — мастера и их график по дням недели (нет дня — выходной);
- `TEXTS` — все тексты и подписи кнопок.

> Не меняйте `id` услуг и мастеров, по которым уже есть записи в базе: записи ссылаются на них.

## Развёртывание на VPS (systemd)

Пример для Ubuntu/Debian. Команды выполняются от root или через `sudo`.

1. Установите Python и git, создайте пользователя для бота:
   ```bash
   apt update && apt install -y python3 python3-venv git
   useradd --system --create-home --shell /usr/sbin/nologin barber
   ```
2. Скачайте проект и установите зависимости:
   ```bash
   git clone https://github.com/vit3ma3/barber_demo.git /opt/barber_demo
   cd /opt/barber_demo
   python3 -m venv .venv
   .venv/bin/pip install -r requirements.txt
   cp .env.example .env
   nano .env            # впишите BOT_TOKEN и ADMIN_ID
   chown -R barber:barber /opt/barber_demo
   chmod 600 .env
   ```
3. Подключите сервис и запустите его:
   ```bash
   cp deploy/barber-bot.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now barber-bot
   ```
4. Проверка и логи:
   ```bash
   systemctl status barber-bot
   journalctl -u barber-bot -f
   ```

Обновление до новой версии:
```bash
cd /opt/barber_demo
sudo -u barber git pull
sudo -u barber .venv/bin/pip install -r requirements.txt
systemctl restart barber-bot
```

База (`barber.db`) лежит в папке проекта. Для резервной копии достаточно скопировать этот файл.
