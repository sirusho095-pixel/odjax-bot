import logging
import sqlite3
import random
import os
import io
from datetime import datetime, time
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ✅ Впиши сюда свой Telegram ID (узнай через @userinfobot)
ADMIN_IDS = {777849214}  # например: {123456789}

TZ = ZoneInfo("Europe/Moscow")  # Ярославль = МСК
PARTICIPATION_START = time(15, 0)   # 15:00
PARTICIPATION_END = time(19, 30)    # 19:30

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# DB
conn = sqlite3.connect("participants.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS participants (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    joined_at TEXT
)
""")
conn.commit()

kb = ReplyKeyboardMarkup(resize_keyboard=True)
kb.add(KeyboardButton("✅ Участвовать"))

def is_within_time_window() -> bool:
    now = datetime.now(TZ).time()
    return PARTICIPATION_START <= now <= PARTICIPATION_END

@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "Добро пожаловать в розыгрыш от кафе «Оджах» 🔥\n"
        "📍 Ярославль\n\n"
        "🎁 Приз: сертификат **1500 ₽** на ужин\n\n"
        "🕒 Участие: **с 15:00 до 19:30** (МСК)\n"
        "🎉 Итоги: **в 19:30**\n\n"
        "Нажмите кнопку ниже, чтобы участвовать 👇",
        reply_markup=kb,
        parse_mode="Markdown"
    )

@dp.message_handler(lambda m: m.text == "✅ Участвовать")
async def participate(message: types.Message):
    if not is_within_time_window():
        await message.answer("⛔ Регистрация закрыта. Участвовать можно только с 15:00 до 19:30 (МСК).")
        return

    user_id = message.from_user.id
    username = message.from_user.username or ""

    cursor.execute("SELECT 1 FROM participants WHERE user_id=?", (user_id,))
    if cursor.fetchone():
        await message.answer(
            "Вы уже участвуете ✅\n\n"
            "🎁 Ваш бонус: скидка **15%** на **3 месяца**\n"
            "Промокод: **ODJAX15**",
            parse_mode="Markdown"
        )
        return

    joined_at = datetime.now(TZ).isoformat(timespec="seconds")
    cursor.execute(
        "INSERT INTO participants (user_id, username, joined_at) VALUES (?,?,?)",
        (user_id, username, joined_at)
    )
    conn.commit()

    await message.answer(
        "✅ Вы зарегистрированы!\n\n"
        "🎉 Итоги сегодня в **19:30** (МСК).\n\n"
        "🎁 Ваш бонус: скидка **15%** на **3 месяца**\n"
        "Промокод: **ODJAX15**",
        parse_mode="Markdown"
    )

@dp.message_handler(commands=["count"])
async def count(message: types.Message):
    @dp.message_handler(commands=["export"])
async def export(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT user_id, username, joined_at FROM participants ORDER BY joined_at ASC")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("Участников нет.")
        return

    output = io.StringIO()
    output.write("user_id,username,joined_at_msk,discount_until\n")

    for user_id, username, joined_at_str in rows:
        joined_at_dt = datetime.fromisoformat(joined_at_str)
        discount_until = (joined_at_dt + timedelta(days=DAYS_90)).strftime("%d.%m.%Y")
        joined_human = joined_at_dt.strftime("%d.%m.%Y %H:%M")
        safe_username = (username or "").replace(",", " ")
        output.write(f"{user_id},{safe_username},{joined_human},{discount_until}\n")

    data = output.getvalue().encode("utf-8")
    output.close()

    await message.answer_document(
        types.InputFile(io.BytesIO(data), filename="odjax_participants.csv"),
        caption=f"Выгрузка участников: {len(rows)} чел."
    )
    if message.from_user.id not in ADMIN_IDS:
        return
    cursor.execute("SELECT COUNT(*) FROM participants")
    (cnt,) = cursor.fetchone()
    await message.answer(f"Участников сейчас: {cnt}")

@dp.message_handler(commands=["draw"])
async def draw(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return

    cursor.execute("SELECT user_id FROM participants")
    users = [row[0] for row in cursor.fetchall()]
    if not users:
        await message.answer("Нет участников.")
        return

    winner_id = random.choice(users)
    await message.answer(f"🎉 Победитель: tg://user?id={winner_id}")

@dp.message_handler(commands=["reset"])
async def reset(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    cursor.execute("DELETE FROM participants")
    conn.commit()
    await message.answer("Список участников очищен ✅")

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
@dp.message_handler(commands=["id"])
async def my_id(message: types.Message):
    await message.answer(f"Ваш Telegram ID: {message.from_user.id}")
