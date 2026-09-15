import os
import re
import asyncio
from telethon import TelegramClient, events
from telethon.tl.types import DocumentAttributeAudio
from services import (
    _get_playlist_urls,
    _download_track_sync,
    _search_music_by_text_sync,
    get_lyrics,
    execute_tracked_task,
)

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


async def send_or_edit_response(event, text, status_msg=None):
    if event.out:
        if status_msg:
            await status_msg.edit(text)
            return status_msg
        await event.edit(text)
        return event
    else:
        if status_msg:
            await status_msg.edit(text)
            return status_msg
        return await event.respond(text)


def register_media_handlers(client: TelegramClient):

    @client.on(events.NewMessage(pattern=r"(?s)^\.music\s+(.*)", func=is_owner_or_friend))
    async def handle_music(event):
        MAX_PLAYLIST_SIZE = 50
        query = event.pattern_match.group(1).strip()
        if not query:
            return await send_or_edit_response(event, "**Введи название трека или ссылку.**")

        is_playlist = bool(
            re.search(
                r"(soundcloud\.com/.+/sets/|open\.spotify\.com/playlist/|youtube\.com/playlist|youtube\.com/watch\?.*list=)",
                query,
            )
        )

        async def _run():
            status_msg = await send_or_edit_response(
                event,
                f"**{'Паршу плейлист' if is_playlist else 'Качаю трек'}:** `{query}`..."
            )
            try:
                loop = asyncio.get_running_loop()

                if is_playlist:
                    urls = await loop.run_in_executor(None, _get_playlist_urls, query)
                    if not urls:
                        return await send_or_edit_response(
                            event,
                            "**Пиздец, не найдено треков. Мертвая ссылка.**",
                            status_msg=status_msg,
                        )

                    if len(urls) > MAX_PLAYLIST_SIZE:
                        return await send_or_edit_response(
                            event,
                            f"**Плейлист слишком большой ({len(urls)} > {MAX_PLAYLIST_SIZE}). Максимум {MAX_PLAYLIST_SIZE}.**",
                            status_msg=status_msg,
                        )

                    await send_or_edit_response(
                        event,
                        f"**Найдено {len(urls)} треков. Начинаю закидывать в чат...**",
                        status_msg=status_msg,
                    )

                    reply_to_id = event.reply_to_msg_id if event.out else event.id

                    for i, url in enumerate(urls, 1):
                        audio_file, thumb_file = None, None
                        try:
                            (
                                audio_file,
                                thumb_file,
                                title,
                                artist,
                                duration,
                            ) = await loop.run_in_executor(
                                None, _download_track_sync, url
                            )
                            attributes = [
                                DocumentAttributeAudio(
                                    duration=duration,
                                    title=title,
                                    performer=artist,
                                )
                            ]

                            await client.send_file(
                                event.chat_id,
                                file=audio_file,
                                thumb=thumb_file,
                                attributes=attributes,
                                reply_to=reply_to_id,
                            )
                        except Exception as e:
                            await client.send_message(
                                event.chat_id, f"**Сбой на треке {i}:** {e}"
                            )
                        finally:
                            if audio_file and os.path.exists(audio_file):
                                os.remove(audio_file)
                            if thumb_file and os.path.exists(thumb_file):
                                os.remove(thumb_file)

                    await event.respond("**Плейлист полностью загружен.**")
                else:
                    audio_file, thumb_file = None, None
                    try:
                        (
                            audio_file,
                            thumb_file,
                            title,
                            artist,
                            duration,
                        ) = await loop.run_in_executor(None, _download_track_sync, query)
                        attributes = [
                            DocumentAttributeAudio(
                                duration=duration, title=title, performer=artist
                            )
                        ]

                        reply_to_id = event.reply_to_msg_id if event.out else event.id

                        await client.send_file(
                            event.chat_id,
                            file=audio_file,
                            thumb=thumb_file,
                            attributes=attributes,
                            reply_to=reply_to_id,
                        )
                    finally:
                        if audio_file and os.path.exists(audio_file):
                            os.remove(audio_file)
                        if thumb_file and os.path.exists(thumb_file):
                            os.remove(thumb_file)

                if event.out:
                    await event.delete()
                else:
                    await status_msg.delete()
            except Exception as e:
                await send_or_edit_response(event, f"**Критический сбой:** {e}", status_msg=status_msg)

        await execute_tracked_task(client, event, _run(), "audio")

    @client.on(events.NewMessage(pattern=r"(?s)^\.musictext\s+(.*)", func=is_owner_or_friend))
    async def handle_musictext(event):
        query = event.pattern_match.group(1).strip()
        if not query:
            return await send_or_edit_response(event, "**Введи название трека.**")

        async def _run():
            status_msg = await send_or_edit_response(event, f"**Ищу оригинальный текст:** `{query}`...")

            res = await get_lyrics(query)

            if not res or not res.get("text"):
                return await send_or_edit_response(
                    event,
                    f"**Глухо, текст песни не найден в базах:** `{query}`",
                    status_msg=status_msg,
                )

            lyrics_text = res["text"]
            source = res.get("source", "неизвестен")

            header = f"**Текст песни:** `{query}`\n**Источник:** `{source}`\n\n"

            full_msg = header + lyrics_text
            if len(full_msg) <= 4000:
                await send_or_edit_response(event, full_msg, status_msg=status_msg)
            else:
                await send_or_edit_response(event, full_msg[:4000], status_msg=status_msg)
                for i in range(4000, len(full_msg), 4000):
                    await client.send_message(event.chat_id, full_msg[i : i + 4000])

        await execute_tracked_task(client, event, _run(), "typing")

    @client.on(events.NewMessage(pattern=r"(?s)^\.findmusic\s+(.*)", func=is_owner_or_friend))
    async def handle_findmusic(event):
        query = event.pattern_match.group(1).strip()
        if not query:
            return await send_or_edit_response(event, "**Введи слова или описание песни.**")

        async def _run():
            status_msg = await send_or_edit_response(event, f"**Ищу треки по тексту:** `{query}`...")
            loop = asyncio.get_running_loop()

            try:
                entries = await loop.run_in_executor(
                    None, _search_music_by_text_sync, query
                )
            except Exception as e:
                return await send_or_edit_response(event, f"**Пиздец, отвал поиска:** {e}", status_msg=status_msg)

            if not entries:
                return await send_or_edit_response(event, "**Нихуя не найдено по этому тексту.**", status_msg=status_msg)

            msg_text = f"**Возможные треки по запросу:** `{query}`\n\n"
            for i, e in enumerate(entries, 1):
                title = e.get("title", "Без названия")
                channel = e.get("uploader", e.get("channel", "Неизвестно"))
                url = e.get("url", "")

                if not url.startswith("http"):
                    url = f"https://www.youtube.com/watch?v={url}"

                msg_text += f"**{i}. {title}**\n👤 Канал: `{channel}`\n🔗 Качнуть: `.music {url}`\n\n"

            await send_or_edit_response(event, msg_text, status_msg=status_msg)

        await execute_tracked_task(client, event, _run(), "typing")
