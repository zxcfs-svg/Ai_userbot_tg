import logging
import os
from dotenv import load_dotenv
from telethon import TelegramClient

from ai import ai_client
from handlers import register_handlers

load_dotenv()

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("log.txt", mode="w", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

api_id_str = os.environ.get("API_ID")
api_hash = os.environ.get("API_HASH")

if not api_id_str or not api_hash:
    raise RuntimeError("Сбой: API_ID или API_HASH отсутствуют в .env.")

try:
    api_id = int(api_id_str)
except ValueError:
    raise RuntimeError("Ошибка: API_ID должен быть числом.")

client = TelegramClient("my_session", api_id, api_hash)
register_handlers(client)


async def main():
    try:
        await client.start()
        logging.info("Бот запущен, сессия сохранена.")
        await client.run_until_disconnected()
    finally:
        logging.info("Завершение работы, закрытие сессий...")
        await ai_client.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
    