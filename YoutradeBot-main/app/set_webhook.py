"""
Регистрируем webhook в Telegram.

    python -m app.set_webhook
"""
import asyncio
import httpx
from app.config import settings


async def main():
    url = f"{settings.WEBHOOK_BASE_URL}/webhook"
    api_url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/setWebhook"

    async with httpx.AsyncClient() as client:
        response = await client.post(api_url, json={
            "url": url,
            "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
            "drop_pending_updates": True,
        })
        print(f"Setting webhook to {url}")
        print(f"Response: {response.json()}")


if __name__ == "__main__":
    asyncio.run(main())
