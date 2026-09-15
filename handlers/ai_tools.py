import base64
import io
import re
import asyncio
import logging
import time
import aiohttp
from telethon import TelegramClient, events
from ai import ai_client
from services import (
    chat_states,
    chat_tasks,
    _ddg_text_search,
    _fetch_page_text,
    _stream_helper,
    _relevance_score,
    execute_tracked_task,
)

BLOCKED_DOMAINS = (".ru", ".rf", ".su", "rbk.ru", "yandex", "mail.ru", "vk.com", "ok.ru")
ALLOWED_FRIEND_ID = 



HELP_MAIN = (
    "**📖 Справка по командам**\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "**🤖 ИИ**\n"
    "  `.ai` — запрос к Gemini\n"
    "  `.aifile` — длинный ответ отдельным .txt-файлом\n"
    "  `.last` — дополнить предыдущий запрос\n"
    "  `.clear` — сбросить контекст текущего чата\n"
    "\n"
    "**🔍 Поиск**\n"
    "  `.search` — поиск в сети → парсинг страниц → ответ ИИ\n"
    "  `.photo` — найти и прислать картинку\n"
    "\n"
    "**🎵 Музыка**\n"
    "  `.music` — скачать аудио с YouTube\n"
    "  `.musictext` — точный текст песни\n"
    "  `.findmusic` — найти трек по строкам\n"
    "\n"
    "**🎬 Видео**\n"
    "  `.tt` — скачать видео из TikTok без водяного знака\n"
    "  `.yt` — скачать видео из YouTube в макс. качестве\n"
    "\n"
    "**🔄 Конвертация**\n"
    "  `.convert` — конвертировать файл в другой формат\n"
    "\n"
    "**🛡 Модерация**\n"
    "  `.mute` — мут (реплаем или в ЛС)\n"
    "  `.unmute` — снять мут\n"
    "  `.delsms` — удалить N сообщений\n"
    "\n"
    "**⚙️ Разное**\n"
    "  `.agro` — спам-монолог на N слов\n"
    "  `.dump` — выгрузить чат в .txt (уйдёт в «Избранное»)\n"
    "  `.stop` — отменить текущую задачу\n"
    "  `.help` — подробнее про конкретную тему\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "**`.help all`** — полная справка со значениями\n"
)

HELP_ALL = (
    "**📖 Полная справка по командам**\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "**🤖 ИИ**\n"
    "  `.ai [1|2] [*N] <запрос>`\n"
    "  `.aifile <запрос>`\n"
    "  `.last <текст>`\n"
    "  `.clear`\n"
    "\n"
    "**🔍 Поиск**\n"
    "  `.search <запрос>`\n"
    "  `.photo <запрос>`\n"
    "\n"
    "**🎵 Музыка**\n"
    "  `.music <трек | ссылка | плейлист>`\n"
    "  `.musictext <артист - трек>`\n"
    "  `.findmusic <слова/описание>`\n"
    "\n"
    "**🎬 Видео**\n"
    "  `.tt <ссылка TikTok>`\n"
    "  `.yt <ссылка YouTube>`\n"
    "\n"
    "**🔄 Конвертация**\n"
    "  `.convert <формат>` (реплаем на файл или подписью к файлу)\n"
    "\n"
    "**🛡 Модерация**\n"
    "  `.mute <10m|10h|10d>`\n"
    "  `.unmute`\n"
    "  `.delsms <N> [0|1]`\n"
    "\n"
    "**⚙️ Разное**\n"
    "  `.agro <1|2> <N> <стиль>`\n"
    "  `.dump <N> [ids]`\n"
    "  `.stop`\n"
    "  `.help <тема | all>`\n"
    "\n"
    "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    "\n"
    "**🤖 ИИ**\n"
    "  `.ai` — запрос к Gemini (`1` — быстрый flash-lite, `2` — умный flash; `*N` — N предыдущих сообщений в контекст; реплай на фото/файл — модель его увидит)\n"
    "  `.aifile` — длинный ответ отдельным .txt-файлом\n"
    "  `.last` — дополнить предыдущий запрос\n"
    "  `.clear` — сбросить контекст текущего чата\n"
    "\n"
    "**🔍 Поиск**\n"
    "  `.search` — поиск в сети → парсинг страниц → ответ ИИ\n"
    "  `.photo` — найти и прислать картинку\n"
    "\n"
    "**🎵 Музыка**\n"
    "  `.music` — скачать аудио с YouTube\n"
    "  `.musictext` — точный текст песни\n"
    "  `.findmusic` — найти трек по строкам\n"
    "\n"
    "**🎬 Видео**\n"
    "  `.tt` — скачать видео из TikTok без водяного знака (через yt-dlp + mobile API)\n"
    "  `.yt` — скачать видео из YouTube в максимальном качестве (video+audio через ffmpeg)\n"
    "\n"
    "**🔄 Конвертация**\n"
    "  `.convert` — конвертирует прикреплённый/отвеченный файл в нужный формат.\n"
    "  Поддержка: `png, jpg, webp, bmp, tiff, gif, ico, mp3, wav, ogg, opus, m4a, flac, aac, mp4, mkv, webm, avi, mov`.\n"
    "  Работает: реплай `.convert png` на файл или подпись `.convert png` к самому файлу.\n"
    "  Картинки → картинки (Pillow), аудио/видео → ffmpeg, видео → gif, видео → аудио (вытянуть звук).\n"
    "\n"
    "**🛡 Модерация**\n"
    "  `.mute` — мут (реплаем или в ЛС)\n"
    "  `.unmute` — снять мут\n"
    "  `.delsms` — удалить N сообщений (без режима — только свои, `0` — все, `1` — только чужие)\n"
    "\n"
    "**⚙️ Разное**\n"
    "  `.agro` — спам-монолог на N слов (`1` — быстро по 1–3 слова, `2` — медленно по 10–15)\n"
    "  `.dump` — выгрузить чат в .txt (уйдёт в «Избранное»)\n"
    "  `.stop` — отменить текущую задачу\n"
    "  `.help` — подробнее про конкретную тему\n"
)

HELP_TOPICS = {
    "ai": (
        "**🤖 ИИ — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.ai [1|2] [*N] <запрос>`\n"
        "`.aifile <запрос>`\n"
        "`.last <текст>`\n"
        "`.clear`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.ai`\n"
        "  Основная команда. Отправляет запрос в Gemini.\n"
        "  • Тир `1` — быстрая модель (flash-lite).\n"
        "  • Тир `2` — умная модель (flash).\n"
        "  • `*N` (1–100) — сколько предыдущих сообщений чата подмешать в контекст.\n"
        "  • Можно ответить (реплаем) на фото/файл до 15 МБ — модель его увидит.\n"
        "\n"
        "`.aifile`\n"
        "  То же, что `.ai`, но ответ приходит отдельным .txt-файлом.\n"
        "  Удобно для длинных простыней.\n"
        "\n"
        "`.last`\n"
        "  Дополняет предыдущий запрос (из `chat_states`) и перезапускает генерацию.\n"
        "\n"
        "`.clear`\n"
        "  Сбрасывает сохранённый контекст текущего чата.\n"
    ),
    "search": (
        "**🔍 Поиск — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.search <запрос>`\n"
        "`.photo <запрос>`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.search`\n"
        "  Идёт в DuckDuckGo, фильтрует мусорные домены (BLOCKED_DOMAINS),\n"
        "  сортирует по релевантности, парсит топ-2 страницы и отдаёт всё ИИ\n"
        "  для формирования фактологического ответа.\n"
        "\n"
        "`.photo`\n"
        "  Ищет картинку через DDGS по регионам (us/uk/de).\n"
        "  Берёт первый релевантный результат, а не random.choice.\n"
    ),
    "music": (
        "**🎵 Музыка — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.music <трек | ссылка | плейлист>`\n"
        "`.musictext <артист - трек>`\n"
        "`.findmusic <слова/описание>`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.music`\n"
        "  Скачивает аудио с YouTube. Понимает прямые ссылки и поисковые запросы.\n"
        "  Для плейлистов — до 50 треков за раз.\n"
        "\n"
        "`.musictext`\n"
        "  Достаёт точный текст песни.\n"
        "\n"
        "`.findmusic`\n"
        "  Ищет трек по фрагменту строк или описанию.\n"
    ),
    "video": (
        "**🎬 Видео — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.tt <ссылка TikTok>`\n"
        "`.yt <ссылка YouTube>`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.tt`\n"
        "  Скачивает видео из TikTok **без водяного знака**.\n"
        "  Работает через yt-dlp с обходом через mobile API TikTok.\n"
        "  Понимает короткие ссылки (vm.tiktok.com / vt.tiktok.com).\n"
        "\n"
        "`.yt`\n"
        "  Скачивает видео из YouTube в **максимальном качестве**.\n"
        "  Видео + аудио склеиваются через ffmpeg в mp4.\n"
        "  Понимает youtu.be и полные ссылки. Лимит — 2000 МБ.\n"
    ),
    "convert": (
        "**🔄 Конвертация — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.convert <формат>`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "**Как использовать:**\n"
        "  • Реплаем: ответь `.convert png` на чужой файл.\n"
        "  • Подписью: кинь файл с подписью `.convert png`.\n"
        "\n"
        "**Поддерживаемые форматы:**\n"
        "  • Картинки: `png, jpg, jpeg, webp, bmp, tiff, gif, ico`\n"
        "  • Аудио: `mp3, wav, ogg, opus, m4a, flac, aac`\n"
        "  • Видео: `mp4, mkv, webm, avi, mov`\n"
        "\n"
        "**Что умеет:**\n"
        "  • Картинка → картинка (через Pillow, быстрее и без потерь качества).\n"
        "  • Аудио → аудио, видео → видео (через ffmpeg).\n"
        "  • Видео → gif (10 fps, 480px).\n"
        "  • Видео → аудио (вытянуть звук из клипа).\n"
        "\n"
        "Файл отправляется как документ, чтобы Telegram не пережимал.\n"
    ),
    "mod": (
        "**🛡 Модерация — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.mute <10m|10h|10d>`\n"
        "`.unmute`\n"
        "`.delsms <N> [0|1]`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.mute`\n"
        "  Мут пользователя. Работает реплаем на сообщение или в ЛС.\n"
        "\n"
        "`.unmute`\n"
        "  Снимает мут.\n"
        "\n"
        "`.delsms`\n"
        "  Удаляет N сообщений.\n"
        "  • без режима — только свои\n"
        "  • `0` — все подряд\n"
        "  • `1` — только чужие\n"
    ),
    "other": (
        "**⚙️ Разное — подробнее**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.agro <1|2> <N> <стиль>`\n"
        "`.dump <N> [ids]`\n"
        "`.stop`\n"
        "`.help <тема | all>`\n"
        "\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "\n"
        "`.agro`\n"
        "  Спам-монолог на N слов в заданном стиле.\n"
        "  • `1` — быстро, порциями по 1–3 слова\n"
        "  • `2` — медленно, порциями по 10–15 слов\n"
        "\n"
        "`.dump`\n"
        "  Выгружает N сообщений чата в .txt и отправляет в «Избранное».\n"
        "  С `ids` — только указанные ID.\n"
        "\n"
        "`.stop`\n"
        "  Отменяет текущую активную задачу в чате.\n"
        "\n"
        "`.help`\n"
        "  Подробнее про тему. Темы: `ai`, `search`, `music`, `video`, `convert`, `mod`, `other`.\n"
    ),
}

HELP_ALIASES = {
    "ии": "ai",
    "поиск": "search",
    "музыка": "music",
    "видео": "video",
    "конверт": "convert",
    "конвертация": "convert",
    "конвертировать": "convert",
    "модерация": "mod",
    "модер": "mod",
    "разное": "other",
    "прочее": "other",
    "все": "all",
    "всё": "all",
}



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



def register_ai_handlers(client: TelegramClient):

    @client.on(events.NewMessage(pattern=r"(?s)^\.ai\s*([1-2])?\s*(.*)", func=is_owner_or_friend))
    async def handle_ai(event):
        async def _run():
            tier_raw = event.pattern_match.group(1)
            raw_payload = event.pattern_match.group(2).strip()
            tier = int(tier_raw) if tier_raw else 1

            sender_id = getattr(event, "sender_id", None)
            if sender_id is None and hasattr(event, "from_id"):
                sender_id = getattr(event.from_id, "user_id", None)

            if not raw_payload and not event.is_reply:
                return await send_or_edit_response(event, "**Введи запрос или ответь на медиа.**")

            media_data = None
            reply = await event.get_reply_message()

            target_msg = reply if (reply and reply.media) else event
            if target_msg.media:
                if (
                    hasattr(target_msg.file, "size")
                    and target_msg.file.size > 15 * 1024 * 1024
                ):
                    return await send_or_edit_response(event, "**Ошибка: размер файла превышает 15 МБ.**")

                media_bytes = await target_msg.download_media(bytes)
                mime_type = "image/jpeg"
                if target_msg.document:
                    mime_type = target_msg.document.mime_type
                media_data = {
                    "mime_type": mime_type,
                    "data": base64.b64encode(media_bytes).decode("utf-8"),
                }

            context_count = 0
            prompt = raw_payload

            match = re.search(r"\*(\d{1,3})\b", raw_payload)
            if match:
                parsed_count = int(match.group(1))
                if 1 <= parsed_count <= 100:
                    context_count = parsed_count
                    prompt = re.sub(r"\*(\d{1,3})\b", "", raw_payload).strip()

            prompt = re.sub(r"\s+", " ", prompt).strip()
            if not prompt and not media_data:
                return await send_or_edit_response(event, "**Ошибка: пустой запрос и отсутствие медиа.**")

            status_msg = await send_or_edit_response(event, "**Генерирую...**")
            final_prompt = prompt

            if context_count > 0:
                history_text = []
                async for msg in client.iter_messages(
                    event.chat_id, limit=context_count, offset_id=event.id
                ):
                    if msg.text:
                        sender = "Я" if msg.out else "Собеседник"
                        history_text.append(f"{sender}: {msg.text}")

                if history_text:
                    history_text.reverse()
                    chat_context = "\n".join(history_text)
                    final_prompt = f"Контекст:\n{chat_context}\n\nЗапрос: {prompt}"

            chat_states[event.chat_id] = {"tier": tier, "prompt": final_prompt}

            try:
                await _stream_helper(
                    event,
                    tier,
                    final_prompt,
                    "Gemini",
                    media_data=media_data,
                    target_msg=status_msg,
                )
            except asyncio.CancelledError:
                await event.respond("**Остановлено.**")
            except Exception as e:
                await send_or_edit_response(event, f"**Пиздец, ошибка**: {e}", status_msg=status_msg)

        await execute_tracked_task(client, event, _run(), "typing")

    @client.on(events.NewMessage(pattern=r"(?s)^\.aifile\s+(.*)", func=is_owner_or_friend))
    async def handle_aifile(event):
        prompt = event.pattern_match.group(1).strip()
        if not prompt:
            return await send_or_edit_response(event, "**Введи запрос.**")

        async def _run():
            status_msg = await send_or_edit_response(event, "**Генерирую ответ в файл...**")
            try:
                result = ""
                async for _, chunk in ai_client.fetch_ai_stream(1, prompt):
                    if chunk:
                        result += chunk

                file_obj = io.BytesIO(result.encode("utf-8"))
                file_obj.name = "answer.txt"
                await client.send_file(
                    event.chat_id,
                    file_obj,
                    caption="**Результат генерации:**",
                    reply_to=event.id,
                )
                if event.out:
                    await event.delete()
                else:
                    await status_msg.delete()
            except Exception as e:
                await send_or_edit_response(event, f"**Ошибка**: {e}", status_msg=status_msg)

        await execute_tracked_task(client, event, _run(), "typing")

    @client.on(events.NewMessage(pattern=r"(?s)^\.search\s+(.*)", func=is_owner_or_friend))
    async def handle_search(event):
        query = event.pattern_match.group(1).strip()
        if not query:
            return await send_or_edit_response(event, "**Введи поисковый запрос.**")

        async def _run():
            status_msg = await send_or_edit_response(event, f"**поиск по запросу:** `{query}`...")
            loop = asyncio.get_running_loop()
            raw_results = await loop.run_in_executor(None, _ddg_text_search, query, 8)

            results = [
                r
                for r in raw_results
                if not any(
                    domain in (r.get("href") or "").lower() for domain in BLOCKED_DOMAINS
                )
            ]

            if not results:
                return await send_or_edit_response(
                    event,
                    f"**Глухо, доступных ресурсов не найдено по запросу:** `{query}`",
                    status_msg=status_msg,
                )

            results.sort(key=lambda r: _relevance_score(query, r), reverse=True)

            pages_text = []
            for r in results[:2]:
                url = r.get("href")
                if url:
                    content = await _fetch_page_text(url, timeout=6, max_chars=3000)
                    if content:
                        pages_text.append(f"Источник [{r.get('title')}]({url}):\n{content}")

            if pages_text:
                search_context = "\n\n---\n\n".join(pages_text)
            else:
                search_context = "\n\n".join(
                    f"[{r.get('title')}]({r.get('href')})\n{r.get('body')}"
                    for r in results[:4]
                )

            prompt = (
                f"Вопрос/Запрос пользователя: {query}\n\n"
                f"Данные из сети:\n{search_context}\n\n"
                "Сформируй четкий, фактологически точный ответ на основе данных. Не выдумывай того, чего нет в источнике."
            )

            try:
                chat_states[event.chat_id] = {"tier": 1, "prompt": prompt}
                await _stream_helper(event, 1, prompt, "Search-AI", target_msg=status_msg)
            except Exception as e:
                await send_or_edit_response(event, f"**Сбой:** {e}", status_msg=status_msg)

        await execute_tracked_task(client, event, _run(), "typing")

    @client.on(events.NewMessage(pattern=r"(?s)^\.last\s+(.*)", func=is_owner_or_friend))
    async def handle_last(event):
        state = chat_states.get(event.chat_id)
        if not state or not state.get("prompt"):
            return await send_or_edit_response(event, "**Ошибка: нет истории для дополнения.**")

        addition = event.pattern_match.group(1).strip()
        state["prompt"] = f"{state['prompt']}\nДополнение: {addition}"

        chat_states[event.chat_id] = state

        async def _run():
            status_msg = await send_or_edit_response(event, "**Дополняю запрос...**")
            try:
                await _stream_helper(event, state["tier"], state["prompt"], "Gemini", target_msg=status_msg)
            except Exception as e:
                await send_or_edit_response(event, f"**Ошибка**: {e}", status_msg=status_msg)

        await execute_tracked_task(client, event, _run(), "typing")

    @client.on(events.NewMessage(pattern=r"(?s)^\.photo\s+(.*)", func=is_owner_or_friend))
    async def handle_photo(event):
        query = event.pattern_match.group(1).strip()
        if not query:
            return await send_or_edit_response(event, "**Введи запрос для поиска.**")

        async def _run():
            status_msg = await send_or_edit_response(event, f"**Ищу фото: `{query}`...**")
            loop = asyncio.get_running_loop()

            def sync_image_search():
                """
                Ищем картинку по нескольким регионам. Берём НЕ случайный, а первый
                релевантный результат (совпадение слов запроса в title/url).
                Если совсем нет совпадений — отдаём первый не заблокированный,
                но НЕ через random.choice (иначе вылезает Everstart на Ариму Кишу).
                """
                try:
                    from ddgs import DDGS
                except ImportError:
                    from duckduckgo_search import DDGS

                regions = ["us-en", "uk-en", "de-de"]
                query_words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}

                for region in regions:
                    try:
                        with DDGS(timeout=15) as ddgs:
                            results = list(
                                ddgs.images(
                                    query,
                                    region=region,
                                    max_results=20,
                                    safesearch="off",
                                    type_image="photo",
                                    backend="auto",
                                )
                            )
                    except Exception as e:
                        logging.error(f"DDG Image Search error ({region}): {e}")
                        time.sleep(1.5)
                        continue

                    if not results:
                        continue

                    if query_words:
                        for r in results:
                            img_url = r.get("image") or ""
                            if not img_url:
                                continue
                            if any(d in img_url.lower() for d in BLOCKED_DOMAINS):
                                continue
                            title = (r.get("title") or "").lower()
                            if any(w in title for w in query_words):
                                return img_url

                    for r in results:
                        img_url = r.get("image") or ""
                        if not img_url:
                            continue
                        if any(d in img_url.lower() for d in BLOCKED_DOMAINS):
                            continue
                        return img_url

                return None

            image_url = await loop.run_in_executor(None, sync_image_search)

            if not image_url:
                return await send_or_edit_response(
                    event,
                    f"**Не найдено доступных фото по запросу:** `{query}`",
                    status_msg=status_msg,
                )

            try:
                session = await ai_client.get_session()
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with session.get(
                    image_url,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=8),
                ) as resp:
                    if resp.status != 200:
                        return await send_or_edit_response(
                            event,
                            f"**Сбой загрузки фото (код {resp.status})**",
                            status_msg=status_msg,
                        )
                    image_bytes = await resp.read()

                file_obj = io.BytesIO(image_bytes)
                file_obj.name = "image.jpg"

                if event.out:
                    await event.delete()
                else:
                    await status_msg.delete()

                reply_to_id = event.reply_to_msg_id if event.out else event.id
                await client.send_file(
                    event.chat_id,
                    file=file_obj,
                    caption=f"**Результат:** `{query}`",
                    reply_to=reply_to_id,
                )
            except Exception as e:
                await client.send_message(
                    event.chat_id,
                    f"**Ошибка сети/доступа (`{image_url[:30]}...`):** {e}",
                )

        await execute_tracked_task(client, event, _run(), "photo")

    @client.on(events.NewMessage(pattern=r"^\.clear$", func=is_owner_or_friend))
    async def handle_clear(event):
        chat_states.pop(event.chat_id, None)
        await send_or_edit_response(event, "**Контекст очищен.**")

    @client.on(events.NewMessage(pattern=r"^\.stop$", func=is_owner_or_friend))
    async def handle_stop(event):
        task = chat_tasks.get(event.chat_id)
        if task and not task.done():
            task.cancel()
            await send_or_edit_response(event, "**Задача отрублена.**")
        else:
            await send_or_edit_response(event, "**Нет активных задач.**")

    @client.on(events.NewMessage(pattern=r"(?s)^\.help(?:\s+(.*))?", func=is_owner_or_friend))
    async def handle_help(event):
        topic = event.pattern_match.group(1)
        if not topic:
            return await send_or_edit_response(event, HELP_MAIN)

        topic_key = topic.strip().lower()
        topic_key = HELP_ALIASES.get(topic_key, topic_key)

        if topic_key == "all":
            return await send_or_edit_response(event, HELP_ALL)