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

from PIL import Image, ImageDraw, ImageFont


# ---------------- CONFIG ----------------
API_TOKEN = os.getenv("BOT_TOKEN")
if not API_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")

# ✅ Впиши сюда свой Telegram ID (узнай через @userinfobot)
ADMIN_IDS = {777849214}  # <-- ЗАМЕНИ НА СВОЙ ID

TZ = ZoneInfo("Europe/Moscow")  # Ярославль = МСК

# 🏆 Розыгрыш можно проводить только после 06.03.2026 18:00 (МСК)
DRAW_ALLOWED_FROM = datetime(2026, 3, 6, 18, 0, 0, tzinfo=TZ)

DAYS_90 = 90
CERT_AMOUNT = 1500
PROMO = "ODJAX15"

# Файл шаблона сертификата (должен лежать в репозитории рядом с bot.py)
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CERT_TEMPLATE_PATH = os.path.join(BASE_DIR, "certificate_template.png")
# Координаты для текста на сертификате (подгонишь один раз под свой макет)
# (x, y) в пикселях
NAME_POS = (120, 680)        # "Получатель: ..."
ISSUE_DATE_POS = (120, 740)  # "Дата выдачи: ..."
EXP_DATE_POS = (120, 790)    # "Действителен до: ..."

# Цвет текста (белый)
TEXT_COLOR = (255, 255, 255, 255)

# Размеры шрифта
NAME_FONT_SIZE = 52
DATE_FONT_SIZE = 36

# ---------------- APP ----------------
logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

kb = ReplyKeyboardMarkup(resize_keyboard=True)
kb.add(KeyboardButton("✅ Участвовать"))

# ---------------- DB ----------------
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


def now_msk() -> datetime:
    return datetime.now(TZ)


def load_font(size: int) -> ImageFont.ImageFont:
    """
    Пытаемся загрузить нормальный ttf-шрифт.
    На Railway часто есть DejaVuSans. Если нет — используем дефолтный.
    """
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def generate_certificate_image(winner_name: str, issue_dt: datetime) -> io.BytesIO:
    """
    Генерирует именной сертификат на основе certificate_template.png
    Вписывает:
      - имя победителя
      - дата выдачи
      - дата окончания (issue + 90 дней)
    Возвращает BytesIO PNG.
    """
    if not os.path.exists(CERT_TEMPLATE_PATH):
        raise FileNotFoundError(
            f"Не найден шаблон сертификата: {CERT_TEMPLATE_PATH}. "
            f"Загрузи его в репозиторий рядом с bot.py"
        )

    img = Image.open(CERT_TEMPLATE_PATH).convert("RGBA")
    draw = ImageDraw.Draw(img)

    name_font = load_font(NAME_FONT_SIZE)
    date_font = load_font(DATE_FONT_SIZE)

    expire_dt = issue_dt + timedelta(days=DAYS_90)

    # Текст
    name_text = f"{winner_name}"
    issue_text = issue_dt.strftime("%d.%m.%Y")
    exp_text = expire_dt.strftime("%d.%m.%Y")

    # Рисуем
    draw.text(NAME_POS, name_text, fill=TEXT_COLOR, font=name_font)
    draw.text(ISSUE_DATE_POS, issue_text, fill=TEXT_COLOR, font=date_font)
    draw.text(EXP_DATE_POS, exp_text, fill=TEXT_COLOR, font=date_font)

    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    out.name = "odjax_certificate.png"
    return out


# ---------------- USER ----------------
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


# ---------------- ADMIN ----------------
def is_admin(message: types.Message) -> bool:
    return message.from_user and message.from_user.id in ADMIN_IDS


@dp.message_handler(commands=["count"])
async def count(message: types.Message):
    if not is_admin(message):
        await message.answer("⛔ Команда доступна только администратору.")
        return
    cursor.execute("SELECT COUNT(*) FROM participants")
    (cnt,) = cursor.fetchone()
    await message.answer(f"Участников сейчас: {cnt}")


@dp.message_handler(commands=["export"])
async def export(message: types.Message):
    if not is_admin(message):
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
    if not is_admin(message):
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
    if not is_admin(message):
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

    # Имя победителя (берём из Telegram)
    try:
        chat = await bot.get_chat(winner_id)
        winner_name = chat.full_name or "Победитель"
    except Exception:
        winner_name = "Победитель"

    # Генерируем сертификат (картинка)
    try:
        cert_img = generate_certificate_image(winner_name=winner_name, issue_dt=now)
    except Exception as e:
        await message.answer(f"⚠️ Не удалось сгенерировать сертификат: {e}")
        return

    # Отправляем победителю сертификат картинкой
    try:
        await bot.send_photo(
            winner_id,
            types.InputFile(cert_img),
            caption=(
                "🎉 Поздравляем! Вы выиграли сертификат от кафе «Оджах» 🔥\n\n"
                f"Номинал: {CERT_AMOUNT} ₽\n"
                "Использование: ужин в ресторане (в зале)\n"
                f"Действителен до: {cert_until} (90 дней с момента выигрыша)\n\n"
                "Покажите этот сертификат администратору в кафе."
            )
        )
    except Exception:
        # если победитель не открывал бота — сообщения могут не дойти
        pass

    # Сообщаем всем участникам итоги
    for uid in users:
        try:
            if uid == winner_id:
                continue
            await bot.send_message(
                uid,
                "🎉 Итоги розыгрыша от кафе «Оджах»!\n\n"
                f"Победитель сертификата {CERT_AMOUNT} ₽: tg://user?id={winner_id}\n"
                f"Дата розыгрыша: {drawn_human}\n\n"
                "Спасибо за участие 🤍\n"
                f"🎁 Напоминаем: ваша скидка 15% действует {DAYS_90} дней с момента регистрации. Промокод: {PROMO}"
            )
        except Exception:
            continue

    await message.answer(
        f"✅ Готово! Победитель: tg://user?id={winner_id}\n"
        f"Дата: {drawn_human}\n"
        f"Сертификат до: {cert_until}\n\n"
        "Сертификат отправлен победителю в личные сообщения (если бот ему доступен)."
    )


@dp.message_handler(commands=["reset"])
async def reset(message: types.Message):
    if not is_admin(message):
        await message.answer("⛔ Команда доступна только администратору.")
        return
    cursor.execute("DELETE FROM participants")
    cursor.execute("UPDATE giveaway_state SET winner_id=NULL, drawn_at=NULL WHERE id=1")
    conn.commit()
    await message.answer("Список участников и результат розыгрыша очищены ✅")


if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
