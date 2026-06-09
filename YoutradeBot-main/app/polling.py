"""
Локальный режим через polling — для разработки без HTTPS.

    python -m app.polling

Не использовать в продакшене. На сервере — webhook через main.py.
"""
import asyncio
import httpx
from app.config import settings
from app.db import init_db
from app.bot import process_update


async def main():
    await init_db()
    print("DB ready.")

    base = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}"

    async with httpx.AsyncClient(timeout=60.0) as client:
        await client.post(f"{base}/deleteWebhook")
        offset = 0
        print("Polling started. Send /start to the bot...")

        while True:
            try:
                r = await client.get(
                    f"{base}/getUpdates",
                    params={"offset": offset, "timeout": 30},
                )
                data = r.json()
                for update in data.get("result", []):
                    offset = update["update_id"] + 1
                    await process_update(update)
            except Exception as e:
                print(f"[polling error] {e}")
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
