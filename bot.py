import logging
import sqlite3
import random
import os
import io
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils import executor

API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ✅ Впиши сюда свой Telegram ID (узнай через @userinfobot)
ADMIN_IDS = {777849214}  # <-- ЗАМЕНИ НА СВОЙ ID

TZ = ZoneInfo("Europe/Moscow")  # Ярославль = МСК

# 🏆 Розыгрыш сертификата можно проводить только после 06.03.2026 18:00 (МСК)
DRAW_ALLOWED_FROM = datetime(2026, 3, 6, 18, 0, 0, tzinfo=TZ)

DAYS_90 = 90
CERT_AMOUNT = 1500
PROMO = "ODJAX15"

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

# --- DB ---
conn = sqlite3.connect("participants.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS participants (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    joined_at TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS giveaway_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    winner_id INTEGER,
    drawn_at TEXT
)
""")

cursor.execute("INSERT OR IGNORE INTO giveaway_state (id, winner_id, drawn_at) VALUES (1, NULL, NULL)")
conn.commit()

# --- UI ---
kb = ReplyKeyboardMarkup(resize_keyboard=True)
kb.add(KeyboardButton("✅ Участвовать"))


def now_msk() -> datetime:
    return datetime.now(TZ)


@dp.message_handler(commands=["start"])
async def start(message: types.Message):
    await message.answer(
        "Добро пожаловать в розыгрыш от кафе «Оджах» 🔥\n"
        "📍 Ярославль\n\n"
        f"🎁 Главный приз: сертификат **{CERT_AMOUNT} ₽** на ужин в ресторане.\n"
        f"🕒 Розыгрыш: **06.03.2026 в 18:00 (МСК)** среди всех участников бота.\n"
        f"⏳ Сертификат действует **{DAYS_90} дней** с момента выигрыша.\n\n"
        "🎁 Бонус каждому участнику сразу после регистрации:\n"
        "Скидка **15%** на самовывоз и посещение ресторана.\n"
        f"⏳ Скидка действует **{DAYS_90} дней** с момента участия.\n\n"
        "Нажмите кнопку ниже, чтобы участвовать 👇",
        reply_markup=kb,
        parse_mode="Markdown"
    )


@dp.message_handler(lambda m: m.text == "✅ Участвовать")
async def participate(message: types.Message):
    now = now_msk()

    user_id = message.from_user.id
    username = message.from_user.username or ""

    cursor.execute("SELECT joined_at FROM participants WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    # Уже участвует — повторно покажем бонус и срок
    if row:
        joined_at = datetime.fromisoformat(row[0])
        discount_until = (joined_at + timedelta(days=DAYS_90)).strftime("%d.%m.%Y")
        await message.answer(
            "Вы уже участвуете ✅\n\n"
            "🎁 Ваша скидка: **15%** (самовывоз и зал)\n"
            f"Срок действия скидки: **до {discount_until} включительно**\n"
            f"Промокод: **{PROMO}**\n\n"
            f"🏆 Главный приз (**{CERT_AMOUNT} ₽**) разыграем 06.03.2026 в 18:00 (МСК).",
            parse_mode="Markdown"
        )
        return

    # Новая регистрация
    joined_at_iso = now.isoformat(timespec="seconds")
    cursor.execute(
        "INSERT INTO participants (user_id, username, joined_at) VALUES (?,?,?)",
        (user_id, username, joined_at_iso)
    )
    conn.commit()

    discount_until = (now + timedelta(days=DAYS_90)).strftime("%d.%m.%Y")

    await message.answer(
        "✅ Вы зарегистрированы!\n\n"
        "🎁 Ваш бонус: скидка **15%** на самовывоз и посещение ресторана\n"
        f"Срок действия скидки: **до {discount_until} включительно**\n"
        f"Промокод: **{PROMO}**\n\n"
        f"🏆 Главный приз: сертификат **{CERT_AMOUNT} ₽** на ужин в ресторане.\n"
        "Розыгрыш: **06.03.2026 в 18:00 (МСК)** среди всех участников бота.\n"
        f"Срок действия сертификата для победителя: **{DAYS_90} дней** с момента выигрыша.",
        parse_mode="Markdown"
    )


# --------- ADMIN COMMANDS ---------

@dp.message_handler(commands=["count"])
async def count(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    cursor.execute("SELECT COUNT(*) FROM participants")
    (cnt,) = cursor.fetchone()
    await message.answer(f"Участников сейчас: {cnt}")


@dp.message_handler(commands=["export"])
async def export(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    cursor.execute("SELECT user_id, username, joined_at FROM participants ORDER BY joined_at ASC")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("Участников нет.")
        return

    out = io.StringIO()
    out.write("user_id,username,joined_at_msk,discount_until\n")

    for user_id, username, joined_at_str in rows:
        joined_at_dt = datetime.fromisoformat(joined_at_str)
        discount_until = (joined_at_dt + timedelta(days=DAYS_90)).strftime("%d.%m.%Y")
        joined_human = joined_at_dt.strftime("%d.%m.%Y %H:%M")
        safe_username = (username or "").replace(",", " ")
        out.write(f"{user_id},{safe_username},{joined_human},{discount_until}\n")

    data = out.getvalue().encode("utf-8")
    out.close()

    bio = io.BytesIO(data)
    bio.name = "odjax_participants.csv"
    bio.seek(0)

    await message.answer_document(
        types.InputFile(bio),
        caption=f"Выгрузка участников: {len(rows)} чел."
    )


@dp.message_handler(commands=["export_text"])
async def export_text(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    cursor.execute("SELECT user_id, username, joined_at FROM participants ORDER BY joined_at ASC")
    rows = cursor.fetchall()

    if not rows:
        await message.answer("Участников нет.")
        return

    lines = []
    for i, (user_id, username, joined_at_str) in enumerate(rows, start=1):
        joined_at_dt = datetime.fromisoformat(joined_at_str)
        joined_human = joined_at_dt.strftime("%d.%m.%Y %H:%M")
        discount_until = (joined_at_dt + timedelta(days=DAYS_90)).strftime("%d.%m.%Y")
        uname = f"@{username}" if username else "(без username)"
        lines.append(f"{i}) {uname} | id:{user_id} | участие: {joined_human} | скидка до: {discount_until}")

    text = "Список участников:\n\n" + "\n".join(lines)

    chunk = 3500
    for start_i in range(0, len(text), chunk):
        await message.answer(text[start_i:start_i + chunk])


@dp.message_handler(commands=["draw"])
async def draw(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    now = now_msk()
    if now < DRAW_ALLOWED_FROM:
        await message.answer("⛔ Розыгрыш будет доступен 06.03.2026 в 18:00 (МСК).")
        return

    cursor.execute("SELECT winner_id, drawn_at FROM giveaway_state WHERE id=1")
    winner_id, drawn_at_iso = cursor.fetchone()

    if winner_id is not None:
        dt = datetime.fromisoformat(drawn_at_iso).astimezone(TZ).strftime("%d.%m.%Y %H:%M (МСК)")
        await message.answer(f"Розыгрыш уже проведён ✅\nПобедитель: tg://user?id={winner_id}\nДата: {dt}")
        return

    cursor.execute("SELECT user_id FROM participants")
    users = [row[0] for row in cursor.fetchall()]
    if not users:
        await message.answer("Нет участников для розыгрыша.")
        return

    winner_id = random.choice(users)

    drawn_at_iso = now.isoformat(timespec="seconds")
    drawn_human = now.strftime("%d.%m.%Y %H:%M (МСК)")
    cert_until = (now + timedelta(days=DAYS_90)).strftime("%d.%m.%Y")

    cursor.execute("UPDATE giveaway_state SET winner_id=?, drawn_at=? WHERE id=1", (winner_id, drawn_at_iso))
    conn.commit()

    # победителю
    try:
        await bot.send_message(
            winner_id,
            f"🎉 Поздравляем!\n"
            f"Вы выиграли сертификат **{CERT_AMOUNT} ₽** от кафе «Оджах» 🔥\n\n"
            "Сертификат можно использовать при посещении ресторана (ужин в зале).\n"
            f"Срок действия сертификата: **до {cert_until} включительно** (90 дней с момента выигрыша).\n\n"
            "Чтобы получить сертификат, покажите это сообщение администратору в кафе.",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    # всем участникам — итоги
    for uid in users:
        try:
            if uid == winner_id:
                continue
            await bot.send_message(
                uid,
                "🎉 Итоги розыгрыша от кафе «Оджах»!\n\n"
                f"Победитель сертификата **{CERT_AMOUNT} ₽**: tg://user?id={winner_id}\n"
                f"Дата розыгрыша: {drawn_human}\n\n"
                "Спасибо за участие 🤍\n"
                f"🎁 Напоминаем: ваша скидка **15%** действует {DAYS_90} дней с момента регистрации. Промокод: {PROMO}",
                parse_mode="Markdown"
            )
        except Exception:
            continue

    await message.answer(f"✅ Готово! Победитель: tg://user?id={winner_id}\nДата: {drawn_human}\nСертификат до: {cert_until}")


@dp.message_handler(commands=["reset"])
async def reset(message: types.Message):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔ Команда доступна только администратору.")
        return

    cursor.execute("DELETE FROM participants")
    cursor.execute("UPDATE giveaway_state SET winner_id=NULL, drawn_at=NULL WHERE id=1")
    conn.commit()
    await message.answer("Список участников и результат розыгрыша очищены ✅")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
