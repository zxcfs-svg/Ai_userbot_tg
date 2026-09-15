import asyncio
import logging
import time
from telethon import TelegramClient, events
from services import safe_delete_messages

muted_users = {}


def register_moderation_handlers(client: TelegramClient):

    async def _get_target_user_id(event):
        if event.is_private:
            return event.chat_id
        reply = await event.get_reply_message()
        if reply:
            return reply.sender_id
        return None

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.mute\s+(\d+)([mhd])$"))
    async def handle_mute(event):
        target_id = await _get_target_user_id(event)
        if not target_id:
            return await event.edit("В группах ответь на сообщение целевого пользователя.")

        amount = int(event.pattern_match.group(1))
        unit = event.pattern_match.group(2)

        multiplier = {"m": 60, "h": 3600, "d": 86400}[unit]
        expire = time.time() + (amount * multiplier)

        muted_users[(event.chat_id, target_id)] = expire
        await event.edit(f"Мут выдан на {amount}{unit}.")

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.unmute$"))
    async def handle_unmute(event):
        target_id = await _get_target_user_id(event)
        if not target_id:
            return await event.edit("В группах ответь на сообщение.")

        muted_users.pop((event.chat_id, target_id), None)
        await event.edit("Снят с мута.")

    async def _wipe_muted_messages(chat_id, user_id, limit=500):
        try:
            to_delete = []
            batch_size = 100
            async for msg in client.iter_messages(chat_id, limit=limit):
                if msg.sender_id == user_id:
                    to_delete.append(msg.id)
                    if len(to_delete) >= batch_size:
                        await safe_delete_messages(client, chat_id, to_delete)
                        to_delete = []
            if to_delete:
                await safe_delete_messages(client, chat_id, to_delete)
        except Exception as e:
            logging.error(f"Mute wipe error: {e}")

    @client.on(events.NewMessage(incoming=True))
    async def enforce_mute(event):
        expire = muted_users.get((event.chat_id, event.sender_id))
        if expire:
            if time.time() < expire:
                asyncio.create_task(safe_delete_messages(client, event.chat_id, [event.id]))
                asyncio.create_task(_wipe_muted_messages(event.chat_id, event.sender_id))
            else:
                muted_users.pop((event.chat_id, event.sender_id), None)

    @client.on(events.NewMessage(outgoing=True, pattern=r"^\.delsms(?:\s+(all|\d+))?(?:\s+([01]))?$"))
    async def handle_delsms(event):
        count_raw = event.pattern_match.group(1)
        mode = event.pattern_match.group(2)

        delete_all = count_raw == "all"
        count = None if delete_all else (int(count_raw) if count_raw else 1)

        await event.delete()

        to_delete = []
        deleted = 0
        limit = None if delete_all else count * 3 + 50

        async for msg in client.iter_messages(event.chat_id, limit=limit):
            if not delete_all and deleted >= count:
                break

            if mode is None and msg.out:
                to_delete.append(msg.id)
            elif mode == '0':
                to_delete.append(msg.id)
            elif mode == '1' and not msg.out:
                to_delete.append(msg.id)
            else:
                continue

            deleted += 1

            if len(to_delete) >= 100:
                await safe_delete_messages(client, event.chat_id, to_delete)
                to_delete = []

        if to_delete:
            await safe_delete_messages(client, event.chat_id, to_delete)