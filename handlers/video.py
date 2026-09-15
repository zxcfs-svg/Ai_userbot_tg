import os
import re
import json
import shutil
import asyncio
import tempfile
import aiohttp
from telethon import TelegramClient, events
from services import execute_tracked_task

try:
    import yt_dlp
except ImportError:
    yt_dlp = None

ALLOWED_FRIEND_ID = None

TIKWM_API = "https://www.tikwm.com/api/"

_FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None



def extract_tiktok_url(text: str) -> str | None:
    match = re.search(r'https?://[^\s"\'<>]+', text)
    if not match:
        return None
    url = match.group(0).rstrip('.,;:!?)')
    if re.search(r'(tiktok\.com|vm\.tiktok\.com|vt\.tiktok\.com)', url):
        return url
    return None


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


def _fmt_err(e: Exception) -> str:
    s = str(e).strip()
    return s if s else repr(e)


def _tmp_dir() -> str:
    d = os.path.join(tempfile.gettempdir(), "video_downloads")
    os.makedirs(d, exist_ok=True)
    return d



def _download_tiktok_via_ytdlp(url: str) -> tuple[str, str, str, str]:
    if yt_dlp is None:
        raise RuntimeError("yt_dlp не установлен. `pip install -U --pre yt-dlp`")

    tmp = _tmp_dir()
    outtmpl = os.path.join(tmp, "%(id)s.%(ext)s")

    opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "format": "best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "socket_timeout": 20,
        "retries": 3,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Referer": "https://www.tiktok.com/",
        },
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)

        if not os.path.exists(filepath):
            base, _ = os.path.splitext(filepath)
            for ext in (".mp4", ".mkv", ".webm", ".mov"):
                if os.path.exists(base + ext):
                    filepath = base + ext
                    break

        title = info.get("title") or info.get("description") or "TikTok video"
        uploader = (
            info.get("uploader")
            or info.get("uploader_id")
            or info.get("channel")
            or "unknown"
        )
        vid = str(info.get("id") or "tiktok")

    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise RuntimeError("yt-dlp: файл пустой или не создан")

    return filepath, title, uploader, vid



async def _tiktok_via_tikwm_download(
    session: aiohttp.ClientSession, url: str
) -> tuple[str, str, str, str]:
    async with session.get(
        TIKWM_API,
        params={"url": url, "hd": "1"},
        timeout=aiohttp.ClientTimeout(total=20),
        headers={"User-Agent": "Mozilla/5.0"},
    ) as resp:
        resp.raise_for_status()
        text = await resp.text()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            raise RuntimeError(f"tikwm: не JSON: {text[:200]!r}")

    if not isinstance(data, dict):
        raise RuntimeError(f"tikwm: неожиданный ответ: {data!r}")

    if data.get("code") != 0:
        raise RuntimeError(f"tikwm: {data.get('msg') or data}")

    d = data.get("data") or {}
    if not isinstance(d, dict):
        raise RuntimeError(f"tikwm: data не словарь: {d!r}")

    play = d.get("hdplay") or d.get("play")
    if not play:
        raise RuntimeError(f"tikwm: нет ссылки на видео: {d!r}")
    if play.startswith("/"):
        play = "https://www.tikwm.com" + play

    title = d.get("title") or "TikTok video"
    author = d.get("author") or {}
    uploader = (
        author.get("unique_id") if isinstance(author, dict) else None
    ) or "unknown"
    vid = str(d.get("id") or "tiktok")

    filepath = os.path.join(_tmp_dir(), f"tikwm_{vid}.mp4")
    async with session.get(
        play,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://www.tikwm.com/",
            "Accept": "*/*",
        },
    ) as resp:
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            async for chunk in resp.content.iter_chunked(64 * 1024):
                f.write(chunk)

    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise RuntimeError("tikwm: файл не скачался или пустой")

    return filepath, title, uploader, vid



async def download_tiktok(url: str) -> tuple[str, str, str, str]:
    errors = []


    if yt_dlp is not None:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, _download_tiktok_via_ytdlp, url
            )
        except Exception as e:
            errors.append(f"yt-dlp: {_fmt_err(e)}")


    try:
        timeout = aiohttp.ClientTimeout(total=60)
        connector = aiohttp.TCPConnector(limit=8, ttl_dns_cache=300)
        async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
            return await _tiktok_via_tikwm_download(session, url)
    except Exception as e:
        errors.append(f"tikwm: {_fmt_err(e)}")

    raise RuntimeError("TikTok недоступен. " + " | ".join(errors))



def _youtube_format_selector() -> str:
    if _FFMPEG_AVAILABLE:
        return (
            "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo[vcodec^=avc1]+bestaudio/"
            "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo+bestaudio/"
            "best[ext=mp4]/best"
        )
    return "best[ext=mp4][vcodec^=avc1]/best[ext=mp4]/best"


def _download_youtube_sync(url: str) -> tuple:
    if yt_dlp is None:
        raise RuntimeError("yt_dlp не установлен. `pip install -U --pre yt-dlp`")

    tmp_dir = _tmp_dir()
    outtmpl = os.path.join(tmp_dir, "%(id)s.%(ext)s")

    ydl_opts = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "restrictfilenames": True,
        "format": _youtube_format_selector(),
        "merge_output_format": "mp4",
        "socket_timeout": 20,
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 4,
        "postprocessors": (
            [{"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}]
            if _FFMPEG_AVAILABLE else []
        ),
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filepath = ydl.prepare_filename(info)

        if not os.path.exists(filepath):
            base, _ = os.path.splitext(filepath)
            for ext in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3"):
                if os.path.exists(base + ext):
                    filepath = base + ext
                    break

        title = info.get("title") or "video"
        uploader = info.get("uploader") or info.get("channel") or "unknown"
        duration = int(info.get("duration") or 0)

        requested = info.get("requested_downloads") or []
        has_video = False
        for rd in requested:
            vcodec = rd.get("vcodec")
            if vcodec and vcodec != "none":
                has_video = True
                break
        if not requested:
            has_video = True

    if not has_video:
        raise RuntimeError(
            "yt-dlp скачал только аудио (нет видеопотока). "
            "Проверь, установлен ли ffmpeg в PATH."
        )

    if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
        raise RuntimeError("YouTube: файл пустой или не создан")

    return filepath, title, uploader, duration



def register_video_handlers(client: TelegramClient):

    @client.on(events.NewMessage(pattern=r"(?s)^\.tt\s+(.*)", func=is_owner_or_friend))
    async def handle_tiktok(event):
        raw_text = event.pattern_match.group(1).strip()
        url = extract_tiktok_url(raw_text)

        if not url:
            return await send_or_edit_response(
                event, "**Не нашёл ссылку TikTok в сообщении.**"
            )

        async def _run():
            status_msg = await send_or_edit_response(
                event, f"**Качаю TikTok:** `{url}`..."
            )
            video_file = None
            try:
                video_file, title, uploader, _ = await download_tiktok(url)
                size_mb = os.path.getsize(video_file) / (1024 * 1024)

                caption = f"**{title}**\n👤 `{uploader}`\n📦 `{size_mb:.1f} MB`"
                reply_to_id = event.reply_to_msg_id if event.out else event.id

                await client.send_file(
                    event.chat_id,
                    file=video_file,
                    caption=caption,
                    reply_to=reply_to_id,
                    supports_streaming=True,
                )

                if event.out:
                    await event.delete()
                else:
                    await status_msg.delete()

            except Exception as e:
                await send_or_edit_response(
                    event, f"**Сбой TikTok:** `{_fmt_err(e)}`", status_msg=status_msg
                )
            finally:
                if video_file and os.path.exists(video_file):
                    try:
                        os.remove(video_file)
                    except OSError:
                        pass

        await execute_tracked_task(client, event, _run(), "video")

    @client.on(events.NewMessage(pattern=r"(?s)^\.yt\s+(.*)", func=is_owner_or_friend))
    async def handle_youtube(event):
        url = event.pattern_match.group(1).strip()
        if not url:
            return await send_or_edit_response(event, "**Дай ссылку на YouTube.**")
        if not re.search(r"(youtube\.com|youtu\.be)", url):
            return await send_or_edit_response(event, "**Это не похоже на ссылку YouTube.**")

        async def _run():
            status_msg = await send_or_edit_response(event, f"**Качаю YouTube в максе:** `{url}`...")
            video_file = None
            try:
                loop = asyncio.get_running_loop()
                video_file, title, uploader, duration = await loop.run_in_executor(
                    None, _download_youtube_sync, url
                )

                size_mb = os.path.getsize(video_file) / (1024 * 1024)
                if size_mb > 2000:
                    return await send_or_edit_response(
                        event,
                        f"**Файл слишком жирный:** `{size_mb:.0f} MB` (лимит 2000 MB)",
                        status_msg=status_msg,
                    )

                caption = f"**{title}**\n👤 `{uploader}`\n📦 `{size_mb:.1f} MB`"
                if duration:
                    mins, secs = divmod(duration, 60)
                    caption += f"\n⏱ `{mins}:{secs:02d}`"

                reply_to_id = event.reply_to_msg_id if event.out else event.id

                await client.send_file(
                    event.chat_id,
                    file=video_file,
                    caption=caption,
                    reply_to=reply_to_id,
                    supports_streaming=True,
                )

                if event.out:
                    await event.delete()
                else:
                    await status_msg.delete()

            except Exception as e:
                await send_or_edit_response(
                    event, f"**Сбой YouTube:** `{_fmt_err(e)}`", status_msg=status_msg
                )
            finally:
                if video_file and os.path.exists(video_file):
                    try:
                        os.remove(video_file)
                    except OSError:
                        pass

        await execute_tracked_task(client, event, _run(), "video")