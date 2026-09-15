import asyncio
import logging

from telethon.errors import FloodWaitError


async def safe_delete_messages(client, chat_id, msg_ids, max_retries=2):
    """Delete messages with FloodWait handling"""
    if not msg_ids:
        return True
    for attempt in range(max_retries):
        try:
            await client.delete_messages(chat_id, msg_ids)
            return True
        except FloodWaitError as e:
            logging.warning(f"FloodWait: sleeping {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logging.error(f"Delete error: {e}")
            return False
    return False
