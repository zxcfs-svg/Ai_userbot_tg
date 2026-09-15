import io
import re
from telethon import TelegramClient, events

ALLOWED_FRIEND_ID = None

def is_owner_or_friend(event):
    if event.out:
        return True
    sender_id = getattr(event, "sender_id", None)
    if sender_id == ALLOWED_FRIEND_ID:
        return True
    if hasattr(event, "from_id") and getattr(event.from_id, "user_id", None) == ALLOWED_FRIEND_ID:
        return True
    return False

def register_dump_handlers(client: TelegramClient):

    @client.on(events.NewMessage(pattern=r"(?s)^\.dump\s+(?:\*?)(\d+)(?:\s+([0-9,\s]+))?", func=is_owner_or_friend))
    async def handle_dump(event):

        await event.delete()

        limit = int(event.pattern_match.group(1))
        raw_ids = event.pattern_match.group(2)
        
        target_ids = []
        if raw_ids:

            target_ids = [int(x.strip()) for x in re.split(r'[,\s]+', raw_ids) if x.strip().isdigit()]

        messages = []

        async for msg in client.iter_messages(event.chat_id, limit=limit):
            messages.append(msg)

        if not messages:
            return


        messages.reverse()


        msg_cache = {m.id: m for m in messages}
        
        lines = []
        for msg in messages:
            sender_id = msg.sender_id
            

            if target_ids and sender_id not in target_ids:
                continue


            sender_name = str(sender_id)
            if msg.sender:
                sender_name = getattr(msg.sender, 'first_name', str(sender_id)) or str(sender_id)


            time_str = msg.date.astimezone().strftime("%d.%m.%Y %H:%M:%S")


            media_tags = []
            if msg.photo: media_tags.append("[Фото]")
            if msg.video: media_tags.append("[Видео]")
            if msg.voice: media_tags.append("[Голосовое сообщение]")
            if msg.video_note: media_tags.append("[Кружок]")
            if msg.document and not msg.video and not msg.voice and not msg.video_note:
                media_tags.append("[Файл]")

            media_str = " ".join(media_tags)


            reply_str = ""
            if msg.reply_to_msg_id:
                rep_msg = msg_cache.get(msg.reply_to_msg_id)
                if rep_msg and rep_msg.sender:
                    rep_name = getattr(rep_msg.sender, 'first_name', str(rep_msg.sender_id)) or str(rep_msg.sender_id)
                    reply_str = f"ответ для {rep_name}: "
                else:
                    reply_str = "ответ: "

            text = msg.text or ""
            

            content = f"{media_str} {text}".strip()
            line = f"{sender_name} [{time_str}] : {reply_str}{content}"
            lines.append(line)

        if not lines:
            return


        dump_text = "\n".join(lines)
        file_obj = io.BytesIO(dump_text.encode('utf-8'))
        file_obj.name = f"dump_{event.chat_id}.txt"


        await client.send_file(
            'me', 
            file_obj, 
            caption=f"**Дамп готов.**\nЧат: `{event.chat_id}`\nСобрано сообщений: `{len(lines)}`\nЛимит парсинга: `{limit}`"
        )
