"""
WhatsApp бот через Botcorp API.
Зеркалит логику bot.py, но работает с WhatsApp-каналом.

Входящий webhook от Botcorp (пример):
{
  "channelId": "6a2696368f0dac7788bf530d",
  "contactId": "abc123...",
  "phone": "77001234567",
  "message": {
    "type": "text",
    "text": "Привет"
  }
}

Отправка сообщений:
POST {BOTCORP_API_URL}/messages/send
Headers: Authorization: {BOTCORP_TOKEN}
Body: { "channelId": "...", "contactId": "...", "type": "text", "text": "..." }
"""
import random
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_session
from app.models import User, Event, Message
from app.scenario import get_step, get_help_message, TOTAL_STEPS
from app.ai import ask_claude
from app.retention import COHORT_FILTERS


# ─── Клиент Botcorp API ────────────────────────────────────────────────────────

async def _botcorp_request(method: str, endpoint: str, json: dict) -> dict:
    """Универсальный запрос к Botcorp API."""
    url = f"{settings.BOTCORP_API_URL}/{endpoint}"
    headers = {
        "Authorization": f"Bearer {settings.BOTCORP_TOKEN}",
        "Content-Type": "application/json",
        "apiKey": settings.BOTCORP_TOKEN,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        if method == "POST":
            resp = await client.post(url, headers=headers, json=json)
        else:
            resp = await client.get(url, headers=headers, params=json)
    try:
        return resp.json()
    except Exception:
        return {"status": resp.status_code, "text": resp.text}


async def send_text_wa(contact_id: str, text: str) -> bool:
    """Отправить текстовое сообщение в WhatsApp через Botcorp."""
    if not settings.BOTCORP_TOKEN or not settings.BOTCORP_CHANNEL_ID:
        print("[whatsapp] BOTCORP_TOKEN или BOTCORP_CHANNEL_ID не настроены!")
        return False
    try:
        result = await _botcorp_request("POST", "messages/send", {
            "channelId": settings.BOTCORP_CHANNEL_ID,
            "contactId": contact_id,
            "type": "text",
            "text": text,
        })
        print(f"[whatsapp] send_text result: {result}")
        return True
    except Exception as e:
        print(f"[whatsapp] send_text failed: {e}")
        return False


# ─── Форматирование ────────────────────────────────────────────────────────────

def _strip_markdown(text: str) -> str:
    """
    WhatsApp не понимает Markdown-разметку Telegram (*bold*, `code`).
    Убираем символы форматирования, оставляем читаемый текст.
    """
    import re
    # убираем *bold* и _italic_
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)
    # убираем `code`
    text = re.sub(r'`(.+?)`', r'\1', text)
    return text


def _format_step_for_wa(step: dict) -> str:
    """
    Превращает шаг сценария в WA-сообщение.
    Кнопки заменяются текстовым меню (нумерованные варианты).
    """
    text = _strip_markdown(step["text"])

    if step.get("buttons"):
        options = []
        idx = 1
        for row in step["buttons"]:
            for label, action in row:
                if not action.startswith("url:"):
                    options.append(f"{idx}. {label}")
                    idx += 1
                else:
                    # URL-кнопку показываем как ссылку
                    url = action[4:]
                    options.append(f"🔗 {label}: {url}")

        if options:
            text += "\n\n" + "\n".join(options)
            # подсказка как отвечать
            non_url = [o for o in options if not o.startswith("🔗")]
            if non_url:
                text += "\n\n_(Ответьте номером варианта)_"
                text = _strip_markdown(text)

    return text


def _parse_button_choice(text: str, step: dict) -> Optional[str]:
    """
    Если пользователь ответил цифрой — возвращаем action соответствующей кнопки.
    """
    stripped = text.strip()
    if not stripped.isdigit():
        return None

    choice = int(stripped)
    idx = 1
    for row in step.get("buttons", []):
        for label, action in row:
            if not action.startswith("url:"):
                if idx == choice:
                    return action
                idx += 1
    return None


# ─── Работа с пользователями ───────────────────────────────────────────────────

async def get_or_create_wa_user(
    session: AsyncSession,
    phone: str,
    contact_id: str,
) -> tuple[User, bool]:
    """Находим или создаём пользователя по номеру телефона WhatsApp."""
    result = await session.execute(
        select(User).where(User.whatsapp_phone == phone)
    )
    user = result.scalar_one_or_none()

    if user is None:
        user = User(
            whatsapp_phone=phone,
            whatsapp_contact_id=contact_id,
            channel="whatsapp",
            source="whatsapp",
            ab_group=random.choice(["A", "B", "C"]),
        )
        session.add(user)
        await session.flush()
        await _log_event(session, user.id, "user_created")
        return user, True

    # обновляем contact_id на случай если изменился
    user.whatsapp_contact_id = contact_id
    user.last_seen_at = datetime.utcnow()
    return user, False


async def _log_event(session: AsyncSession, user_id: int, event_type: str,
                     step: Optional[int] = None, payload: Optional[str] = None):
    session.add(Event(user_id=user_id, event_type=event_type, step=step, payload=payload))


async def _log_message(session: AsyncSession, user_id: int, direction: str,
                       content: str, step: Optional[int] = None, is_ai: bool = False):
    session.add(Message(
        user_id=user_id, direction=direction, content=content[:4000],
        step=step, is_ai=is_ai
    ))


# ─── Отправка шагов ───────────────────────────────────────────────────────────

async def send_step_wa(contact_id: str, session: AsyncSession, user: User, step_num: int):
    """Отправляем шаг онбординга через WhatsApp."""
    step = get_step(step_num)
    if step is None:
        return

    message_text = _format_step_for_wa(step)
    await send_text_wa(contact_id, message_text)

    user.current_step = step_num
    if step_num > user.max_step_reached:
        user.max_step_reached = step_num

    await _log_event(session, user.id, f"step_{step_num}_shown", step=step_num)
    await _log_message(session, user.id, "out", step["text"][:200], step=step_num)

    if step_num == TOTAL_STEPS:
        user.completed_at = datetime.utcnow()
        await _log_event(session, user.id, "completed")


async def send_welcome_wa(contact_id: str, session: AsyncSession, user: User):
    """Welcome-сообщение для новых WA пользователей."""
    welcome_text = (
        "👋 Добро пожаловать в YouTrade Prop!\n\n"
        "Я Алия — ваш персональный помощник.\n"
        "За 5 минут покажу как сделать первую сделку.\n\n"
        "Напишите *старт* или *1* чтобы начать."
    )
    welcome_text = _strip_markdown(welcome_text)
    await send_text_wa(contact_id, welcome_text)
    await _log_event(session, user.id, "welcome_wa_shown")


# ─── Обработка входящих сообщений ─────────────────────────────────────────────

async def handle_wa_message(payload: dict):
    """
    Главная точка входа для входящего вебхука от Botcorp.

    Ожидаемая структура payload:
    {
      "channelId": "...",
      "contactId": "...",
      "phone": "77001234567",
      "message": { "type": "text", "text": "..." }
      -- или на верхнем уровне --
      "text": "..."
    }
    """
    print(f"[whatsapp] incoming payload: {payload}")

    # Botcorp шлёт данные внутри data.messageData
    data = payload.get("data") or {}
    msg_data = data.get("messageData") or {}
    contact_data = data.get("contactData") or {}

    # Извлекаем contact_id
    contact_id = (
        msg_data.get("contactId")
        or payload.get("contactId")
        or payload.get("contact_id")
        or payload.get("id")
        or ""
    )

    # Извлекаем телефон
    phone = (
        contact_data.get("phone")
        or payload.get("phone")
        or payload.get("from")
        or ""
    )

    # Извлекаем текст сообщения
    text = (
        msg_data.get("text")
        or payload.get("text")
        or ""
    )
    msg_type = msg_data.get("type", "text")

    # Пропускаем если это исходящее сообщение от бота
    if msg_data.get("sender") is True or msg_data.get("bot") is True:
        print(f"[whatsapp] пропускаем исходящее сообщение от бота")
        return

    text = str(text).strip()

    if not contact_id or not text:
        print(f"[whatsapp] пропускаем: нет contact_id или текста. payload={payload}")
        return

    # Нормализуем номер телефона (убираем + и пробелы)
    phone = phone.lstrip("+").replace(" ", "").replace("-", "")

    async with get_session() as session:
        user, is_new = await get_or_create_wa_user(session, phone or contact_id, contact_id)

        if is_new:
            await _log_event(session, user.id, "started")
            await send_welcome_wa(contact_id, session, user)
            user.current_step = -1
            return

        await _log_message(session, user.id, "in", text, step=user.current_step)

        # ── Команды сброса ──
        text_lower = text.lower()
        if text_lower in ["старт", "start", "/start", "начать", "начало", "0"]:
            await send_step_wa(contact_id, session, user, 0)
            return

        # ── Стоп-слова ──
        if any(kw in text_lower for kw in COHORT_FILTERS.get("stop_keywords", [])):
            if not user.unsubscribed:
                user.unsubscribed = True
                await _log_event(session, user.id, "unsubscribed")
                await send_text_wa(contact_id, "Понял, больше не пишу. Если передумаете — напишите что-нибудь.")
            return

        # ── Флаг "нет денег" ──
        user.incoming_messages_count += 1
        if any(kw in text_lower for kw in COHORT_FILTERS.get("no_money_keywords", [])):
            if not user.mentioned_no_money:
                user.mentioned_no_money = True
                await _log_event(session, user.id, "mentioned_no_money")

        # ── Human takeover ──
        if user.human_takeover:
            await _log_event(session, user.id, "message_during_takeover")
            return

        # ── Обработка нажатия кнопки (цифрой) ──
        current_step_data = get_step(user.current_step) if user.current_step >= 0 else None
        if current_step_data:
            action = _parse_button_choice(text, current_step_data)
            if action:
                await _handle_wa_action(contact_id, session, user, action)
                return

        # ── Быстрые ответы "да" / "нет" ──
        if text_lower in ["да", "yes", "ок", "ok", "готов", "готова", "дальше", "next", "поехали", "2"]:
            if user.current_step >= 0 and user.current_step < TOTAL_STEPS:
                await send_step_wa(contact_id, session, user, user.current_step + 1)
                return

        # ── AI-ответ ──
        context = {
            "current_step": user.current_step if user.purchased else None,
            "purchased": user.purchased,
            "ab_group": user.ab_group,
            "source": "whatsapp",
            "welcome_completed": user.current_step >= -1,
        }

        # Отправляем индикатор что печатаем (просто пауза — WA не поддерживает typing)
        response = await ask_claude(text, context=context)
        await send_text_wa(contact_id, response)
        await _log_message(session, user.id, "out", response, step=user.current_step, is_ai=True)
        await _log_event(session, user.id, "ai_response", step=user.current_step)

        if user.first_ai_reply_at is None:
            user.first_ai_reply_at = datetime.utcnow()


async def _handle_wa_action(contact_id: str, session: AsyncSession, user: User, action: str):
    """Обрабатываем действие кнопки (выбор цифрой)."""
    await _log_event(session, user.id, "button_clicked", step=user.current_step, payload=action)

    if action == "next":
        next_step = user.current_step + 1
        if next_step > TOTAL_STEPS:
            await send_text_wa(contact_id, "Вы уже прошли весь курс! Напишите 'старт' чтобы пройти снова.")
            return
        await send_step_wa(contact_id, session, user, next_step)

    elif action == "help":
        help_text = get_help_message(user.current_step)
        await send_text_wa(contact_id, help_text)
        await _log_message(session, user.id, "out", help_text, step=user.current_step)

    elif action == "ask":
        await send_text_wa(
            contact_id,
            "Спрашивайте что угодно — отвечу в свободной форме. "
            "Потом сможем вернуться к шагам (напишите 'старт')."
        )

    elif action == "practice":
        await send_text_wa(
            contact_id,
            f"Отличная идея! Продолжайте тренироваться в демо:\n{settings.MATCHTRADER_URL}\n\n"
            f"Когда будете готовы — пишите 'старт' или сразу:\n{settings.CHALLENGE_URL}"
        )


# ─── Отправка retention-пуша через WA ─────────────────────────────────────────

async def send_push_wa(user: User, text: str) -> bool:
    """Отправляет retention-пуш пользователю WhatsApp."""
    if not user.whatsapp_contact_id:
        print(f"[whatsapp] нет contact_id для user {user.id}")
        return False
    try:
        ok = await send_text_wa(user.whatsapp_contact_id, text)
        print(f"[whatsapp] retention push sent to user {user.id}: {ok}")
        return ok
    except Exception as e:
        print(f"[whatsapp] retention push failed for user {user.id}: {e}")
        return False
