"""
Создание таблиц в БД. Запускать один раз при установке.

    python -m app.migrate
"""
import asyncio
from app.db import init_db


async def main():
    print("Creating tables...")
    await init_db()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
