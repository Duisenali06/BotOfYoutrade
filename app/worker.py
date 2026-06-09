"""
Фоновый воркер ретеншна.

Запускается отдельным процессом (systemd-сервис youtrade-worker).
Раз в 5 минут проверяет кого из юзеров надо запушить.

Логика:
1. Берём юзеров где incoming_messages_count >= 3
2. Фильтруем: не купили, не отписались, не упомянули "нет денег", не заблокировали
3. Проверяем: какой пуш следующий по индексу, прошло ли нужное время
4. Шлём, логируем, обновляем last_push_sent_index
   — Telegram-юзерам через python-telegram-bot
   — WhatsApp-юзерам через Botcorp API

Запуск вручную:
    python -m app.worker
"""
import asyncio
from datetime import datetime
from sqlalchemy import select, and_

from app.config import settings
from app.db import get_session
from app.models import User, Event
from app.retention import PUSH_SCHEDULE, render_push
from app.bot import bot
from app.whatsapp_bot import send_push_wa


CHECK_INTERVAL_SECONDS = 300


def get_urls_for_user(user: User) -> dict:
    base = settings.WEBHOOK_BASE_URL.rstrip("/")
    return {
        "pay_url": f"{base}/pay?uid={user.id}",
        "demo_url": settings.MATCHTRADER_URL,
        "academy_url": "https://youtradeprop.com/academy",
        "guide_prop_url": "https://youtradeprop.com/guides/what-is-prop",
        "guide_risk_url": "https://youtradeprop.com/guides/risk-management",
    }


async def should_send_push(user: User, push_index: int) -> bool:
    """Проверяем можно ли слать этот пуш сейчас."""
    if user.purchased:
        return False
    if user.unsubscribed or user.blocked_bot:
        return False
    if user.mentioned_no_money:
        return False
    if user.human_takeover:
        return False
    if user.incoming_messages_count < 3:
        return False
    if user.first_ai_reply_at is None:
        return False

    if push_index != user.last_push_sent_index + 1:
        return False

    if push_index >= len(PUSH_SCHEDULE):
        return False

    push = PUSH_SCHEDULE[push_index]
    time_since_first = datetime.utcnow() - user.first_ai_reply_at
    if time_since_first < push["delay"]:
        return False

    return True


async def send_push_to_user(user: User, push_index: int) -> bool:
    """Шлёт пуш юзеру через нужный канал (Telegram или WhatsApp)."""
    push = PUSH_SCHEDULE[push_index]
    urls = get_urls_for_user(user)
    rendered = render_push(push["id"], urls)

    if rendered is None:
        return False

    # ── WhatsApp-канал ──
    if user.channel == "whatsapp":
        ok = await send_push_wa(user, rendered["text"])
        if not ok:
            print(f"[retention] WA push failed for user {user.id}")
        return ok

    # ── Telegram-канал (по умолчанию) ──
    try:
        await bot.send_message(
            chat_id=user.telegram_id,
            text=rendered["text"],
            disable_web_page_preview=True,
        )
        print(f"[retention] sent push {push['id']} to user {user.id} (tg)")
        return True
    except Exception as e:
        err_str = str(e).lower()
        if "blocked" in err_str or "forbidden" in err_str or "403" in err_str:
            user.blocked_bot = True
            print(f"[retention] user {user.id} blocked the bot")
        else:
            print(f"[retention] failed to send to {user.id}: {e}")
        return False


async def process_retention_batch():
    """Один проход: найти кого пушить, отправить."""
    async with get_session() as session:
        candidates = (await session.execute(
            select(User).where(and_(
                User.purchased == False,
                User.unsubscribed == False,
                User.blocked_bot == False,
                User.mentioned_no_money == False,
                User.human_takeover == False,
                User.incoming_messages_count >= 3,
                User.first_ai_reply_at.is_not(None),
                User.last_push_sent_index < len(PUSH_SCHEDULE) - 1,
            ))
        )).scalars().all()

        print(f"[retention] checking {len(candidates)} candidates")
        sent_count = 0

        for user in candidates:
            next_index = user.last_push_sent_index + 1

            if await should_send_push(user, next_index):
                ok = await send_push_to_user(user, next_index)
                if ok:
                    user.last_push_sent_index = next_index
                    user.last_push_sent_at = datetime.utcnow()
                    session.add(Event(
                        user_id=user.id,
                        event_type="retention_push_sent",
                        payload=PUSH_SCHEDULE[next_index]["id"],
                    ))
                    sent_count += 1

        if sent_count:
            print(f"[retention] sent {sent_count} pushes")


async def main():
    print(f"[worker] starting, check every {CHECK_INTERVAL_SECONDS}s")
    while True:
        try:
            await process_retention_batch()
        except Exception as e:
            print(f"[worker error] {e}")
            import traceback
            traceback.print_exc()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())
