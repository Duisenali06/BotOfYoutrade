"""
Telegram bot logic — обработка сообщений, ведение юзера по сценарию.
"""
import random
from datetime import datetime
from typing import Optional
from pathlib import Path

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, Bot
from telegram.constants import ParseMode
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import User, Event, Message, MediaCache
from app.scenario import get_step, get_help_message, TOTAL_STEPS
from app.ai import ask_claude


bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)

SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"


async def get_or_create_user(session: AsyncSession, tg_user) -> tuple[User, bool]:
    """Возвращает юзера, bool = создан ли новый."""
    result = await session.execute(select(User).where(User.telegram_id == tg_user.id))
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
            ab_group=random.choice(["A", "B", "C"]),
        )
        session.add(user)
        await session.flush()
        await log_event(session, user.id, "user_created")
        return user, True

    user.last_seen_at = datetime.utcnow()
    return user, False


async def log_event(session: AsyncSession, user_id: int, event_type: str,
                    step: Optional[int] = None, payload: Optional[str] = None):
    session.add(Event(user_id=user_id, event_type=event_type, step=step, payload=payload))


async def log_message(session: AsyncSession, user_id: int, direction: str,
                      content: str, step: Optional[int] = None, is_ai: bool = False):
    session.add(Message(
        user_id=user_id, direction=direction, content=content[:4000], step=step, is_ai=is_ai
    ))


async def get_cached_file_id(session: AsyncSession, key: str) -> Optional[str]:
    result = await session.execute(select(MediaCache).where(MediaCache.key == key))
    cached = result.scalar_one_or_none()
    return cached.file_id if cached else None


async def cache_file_id(session: AsyncSession, key: str, file_id: str):
    result = await session.execute(select(MediaCache).where(MediaCache.key == key))
    cached = result.scalar_one_or_none()
    if cached:
        cached.file_id = file_id
    else:
        session.add(MediaCache(key=key, file_id=file_id))


async def send_screenshot(chat_id: int, session: AsyncSession, screenshot_key: str) -> bool:
    """Отправляем скрин. Кешируем file_id чтобы не загружать каждый раз."""
    if not screenshot_key:
        return False

    cached_id = await get_cached_file_id(session, screenshot_key)
    if cached_id:
        try:
            await bot.send_photo(chat_id=chat_id, photo=cached_id)
            return True
        except Exception as e:
            print(f"[send_screenshot] cached file_id failed, reuploading: {e}")

    file_path = SCREENSHOTS_DIR / f"{screenshot_key}.jpg"
    if not file_path.exists():
        file_path = SCREENSHOTS_DIR / f"{screenshot_key}.png"
    if not file_path.exists():
        print(f"[send_screenshot] file not found: {screenshot_key}")
        return False

    try:
        with open(file_path, "rb") as f:
            msg = await bot.send_photo(chat_id=chat_id, photo=f)
        if msg.photo:
            await cache_file_id(session, screenshot_key, msg.photo[-1].file_id)
        return True
    except Exception as e:
        print(f"[send_screenshot] upload failed: {e}")
        return False


def build_keyboard(buttons: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    keyboard = []
    for row in buttons:
        kb_row = []
        for label, action in row:
            if action.startswith("url:"):
                kb_row.append(InlineKeyboardButton(label, url=action[4:]))
            else:
                kb_row.append(InlineKeyboardButton(label, callback_data=action))
        keyboard.append(kb_row)
    return InlineKeyboardMarkup(keyboard)


async def send_step(chat_id: int, session: AsyncSession, user: User, step_num: int):
    """Отправляем конкретный шаг юзеру."""
    step = get_step(step_num)
    if step is None:
        return

    if step["screenshot"]:
        await send_screenshot(chat_id, session, step["screenshot"])

    keyboard = build_keyboard(step["buttons"]) if step["buttons"] else None

    await bot.send_message(
        chat_id=chat_id,
        text=step["text"],
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=keyboard,
    )

    user.current_step = step_num
    if step_num > user.max_step_reached:
        user.max_step_reached = step_num

    await log_event(session, user.id, f"step_{step_num}_shown", step=step_num)
    await log_message(session, user.id, "out", step["text"][:200], step=step_num)

    if step_num == TOTAL_STEPS:
        user.completed_at = datetime.utcnow()
        await log_event(session, user.id, "completed")


async def send_welcome_flow(chat_id: int, session: AsyncSession, user: User):
    """Прогревающая welcome-последовательность перед началом диалога с Аружан."""
    from app.content import WELCOME_MESSAGES
    from telegram import InputMediaPhoto
    import asyncio

    for i, msg in enumerate(WELCOME_MESSAGES):
        media = msg.get("media")
        try:
            if isinstance(media, list):
                media_group = [InputMediaPhoto(media=open(p, "rb")) for p in media]
                await bot.send_media_group(chat_id=chat_id, media=media_group)
                if msg["text"]:
                    await bot.send_message(chat_id=chat_id, text=msg["text"])
            elif isinstance(media, str):
                with open(media, "rb") as f:
                    await bot.send_photo(chat_id=chat_id, photo=f, caption=msg["text"] if len(msg["text"]) < 1024 else None)
                if len(msg["text"]) >= 1024:
                    await bot.send_message(chat_id=chat_id, text=msg["text"])
            else:
                await bot.send_message(chat_id=chat_id, text=msg["text"])
        except Exception as e:
            print(f"[welcome] message {i} failed: {e}")
            await bot.send_message(chat_id=chat_id, text=msg["text"])

        await log_event(session, user.id, f"welcome_{i}_shown")

        if msg.get("delay_after"):
            await asyncio.sleep(msg["delay_after"])


async def handle_start(update: Update):
    if not update.message or not update.message.from_user:
        return
    tg_user = update.message.from_user
    chat_id = update.message.chat.id

    async with get_session() as session:
        user, is_new = await get_or_create_user(session, tg_user)

        if is_new:
            await log_event(session, user.id, "started")
            await send_welcome_flow(chat_id, session, user)
            user.current_step = -1
        else:
            await send_step(chat_id, session, user, user.current_step if user.current_step >= 0 else 0)


async def handle_callback(update: Update):
    """Обработка кнопок."""
    if not update.callback_query:
        return
    query = update.callback_query
    await query.answer()

    tg_user = query.from_user
    chat_id = query.message.chat.id
    action = query.data

    async with get_session() as session:
        user, _ = await get_or_create_user(session, tg_user)
        await log_event(session, user.id, f"button_clicked", step=user.current_step, payload=action)

        if action == "next":
            next_step = user.current_step + 1
            if next_step > TOTAL_STEPS:
                await bot.send_message(chat_id=chat_id, text="Вы уже прошли весь курс! Напишите /start чтобы пройти снова.")
                return
            await send_step(chat_id, session, user, next_step)

        elif action == "help":
            help_text = get_help_message(user.current_step)
            await bot.send_message(chat_id=chat_id, text=help_text)
            await log_message(session, user.id, "out", help_text, step=user.current_step)

        elif action == "ask":
            await bot.send_message(
                chat_id=chat_id,
                text="Спрашивайте что угодно — отвечу в свободной форме. Потом сможем вернуться к шагам."
            )

        elif action == "practice":
            await bot.send_message(
                chat_id=chat_id,
                text=(
                    "Отличная идея! Продолжайте тренироваться в демо — "
                    f"{settings.MATCHTRADER_URL}\n\n"
                    "Когда будете готовы перейти на реальный счёт — возвращайтесь, "
                    "или сразу жмите: " + settings.CHALLENGE_URL
                )
            )


async def handle_text(update: Update):
    """Обработка свободного текста — через Claude (Аружан или Алия по статусу)."""
    if not update.message or not update.message.text:
        return
    tg_user = update.message.from_user
    chat_id = update.message.chat.id
    text = update.message.text.strip()

    async with get_session() as session:
        user, _ = await get_or_create_user(session, tg_user)
        await log_message(session, user.id, "in", text, step=user.current_step)

        from app.retention import COHORT_FILTERS
        user.incoming_messages_count += 1

        text_lower = text.lower()
        if any(kw in text_lower for kw in COHORT_FILTERS["no_money_keywords"]):
            if not user.mentioned_no_money:
                user.mentioned_no_money = True
                await log_event(session, user.id, "mentioned_no_money")

        if any(kw in text_lower for kw in COHORT_FILTERS["stop_keywords"]):
            if not user.unsubscribed:
                user.unsubscribed = True
                await log_event(session, user.id, "unsubscribed")
                await bot.send_message(
                    chat_id=chat_id,
                    text="Понял, больше не пишу. Если передумаете — просто напишите что-нибудь."
                )
                return

        if user.human_takeover:
            await log_event(session, user.id, "message_during_takeover")
            return

        if user.purchased:
            simple_yes = text.lower() in ["да", "yes", "ок", "ok", "готов", "готова", "дальше", "next", "да, поехали", "поехали"]
            if simple_yes and user.current_step < TOTAL_STEPS:
                next_step = user.current_step + 1
                await send_step(chat_id, session, user, next_step)
                return

        context = {
            "current_step": user.current_step if user.purchased else None,
            "purchased": user.purchased,
            "ab_group": user.ab_group,
            "source": user.source,
            "welcome_completed": user.current_step >= -1,
        }

        await bot.send_chat_action(chat_id=chat_id, action="typing")
        response = await ask_claude(text, context=context)
        await bot.send_message(chat_id=chat_id, text=response)
        await log_message(session, user.id, "out", response, step=user.current_step, is_ai=True)
        await log_event(session, user.id, "ai_response", step=user.current_step)

        if user.first_ai_reply_at is None:
            user.first_ai_reply_at = datetime.utcnow()


async def process_update(update_dict: dict):
    """Главная точка входа для каждого update от Telegram."""
    update = Update.de_json(update_dict, bot)
    if not update:
        return

    try:
        if update.message:
            if update.message.text and update.message.text.startswith("/start"):
                await handle_start(update)
            else:
                await handle_text(update)
        elif update.callback_query:
            await handle_callback(update)
    except Exception as e:
        print(f"[process_update error] {e}")
        import traceback
        traceback.print_exc()
