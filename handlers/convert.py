import os
import re
import shutil
import asyncio
import subprocess
import time
import uuid
from telethon import TelegramClient, events
from services import execute_tracked_task

ALLOWED_FRIEND_ID = None

TMP_DIR = "/tmp/convert_tmp"
os.makedirs(TMP_DIR, exist_ok=True)

IMAGE_EXTS = {"png", "jpg", "jpeg", "webp", "bmp", "tiff", "gif", "ico", "heic"}
AUDIO_EXTS = {"mp3", "wav", "ogg", "opus", "m4a", "flac", "aac", "wma"}
VIDEO_EXTS = {"mp4", "mkv", "webm", "avi", "mov", "flv", "wmv", "m4v", "ts"}

ALIASES = {
    "jpg": "jpg",
    "jpeg": "jpg",
    "png": "png",
    "webp": "webp",
    "bmp": "bmp",
    "tiff": "tiff",
    "gif": "gif",
    "ico": "ico",
    "mp3": "mp3",
    "wav": "wav",
    "ogg": "ogg",
    "opus": "opus",
    "m4a": "m4a",
    "flac": "flac",
    "aac": "aac",
    "mp4": "mp4",
    "mkv": "mkv",
    "webm": "webm",
    "avi": "avi",
    "mov": "mov",
    "gifv": "mp4",
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


def _which(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def _run_ffmpeg(args: list, timeout: int = 300) -> None:
    if not _which("ffmpeg"):
        raise RuntimeError("ffmpeg не найден в системе. Установи: `apt install ffmpeg`")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="ignore")[-500:]
        raise RuntimeError(f"ffmpeg ошибка: {err}")


def _convert_image(src: str, dst: str, target_ext: str) -> None:
    """Конвертация картинок через Pillow (если установлен), иначе ffmpeg."""
    try:
        from PIL import Image
    except ImportError:
        Image = None

    if Image is not None:
        img = Image.open(src)

        if target_ext in ("jpg", "jpeg"):
            if img.mode in ("RGBA", "LA", "P"):
                img = img.convert("RGB")

        if target_ext == "gif":
            img.save(dst, save_all=True)
        else:
            img.save(dst)
        return


    _run_ffmpeg(["-i", src, dst])


def _convert_audio(src: str, dst: str, target_ext: str) -> None:
    _run_ffmpeg(["-i", src, dst])


def _convert_video(src: str, dst: str, target_ext: str) -> None:

    if target_ext == "gif":

        _run_ffmpeg([
            "-i", src,
            "-vf", "fps=10,scale=480:-1:flags=lanczos",
            "-loop", "0",
            dst,
        ])
    else:
        _run_ffmpeg([
            "-i", src,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            dst,
        ])


def _detect_category(ext: str) -> str:
    ext = ext.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "unknown"


def _convert_sync(src: str, target_ext: str) -> str:
    """Определяет категорию исходника и конвертит. Возвращает путь к результату."""
    src_ext = os.path.splitext(src)[1].lstrip(".").lower()
    target_ext = target_ext.lower()

    if src_ext == target_ext:
        raise RuntimeError(f"Файл уже в формате `{target_ext}`")


    dst = os.path.join(TMP_DIR, f"converted_{uuid.uuid4().hex}.{target_ext}")

    src_cat = _detect_category(src_ext)
    dst_cat = _detect_category(target_ext)

    if src_cat == "unknown":
        raise RuntimeError(f"Неизвестный формат исходника: `.{src_ext}`")
    if dst_cat == "unknown":
        raise RuntimeError(f"Неизвестный целевой формат: `.{target_ext}`")


    if src_cat == "image" and dst_cat == "image":
        _convert_image(src, dst, target_ext)

    elif src_cat == "audio" and dst_cat == "audio":
        _convert_audio(src, dst, target_ext)

    elif src_cat == "video" and target_ext == "gif":
        _convert_video(src, dst, target_ext)

    elif src_cat == "video" and dst_cat == "video":
        _convert_video(src, dst, target_ext)

    elif src_cat == "video" and dst_cat == "audio":
        _run_ffmpeg([
            "-i", src,
            "-vn",
            "-c:a", "libmp3lame" if target_ext == "mp3" else "copy",
            dst,
        ])

    else:
        raise RuntimeError(f"Конвертация `{src_ext}` → `{target_ext}` не поддерживается")

    if not os.path.exists(dst) or os.path.getsize(dst) == 0:
        raise RuntimeError("Конвертация не дала результата (пустой файл)")

    return dst


def register_convert_handlers(client: TelegramClient):

    @client.on(events.NewMessage(pattern=r"(?s)^\.convert\s+(\S+)\s*$", func=is_owner_or_friend))
    async def handle_convert(event):
        target_raw = event.pattern_match.group(1).strip().lstrip(".").lower()

        if target_raw not in ALIASES:
            return await send_or_edit_response(
                event,
                f"**Неизвестный формат:** `{target_raw}`\n"
                f"**Доступно:** `{', '.join(sorted(set(ALIASES.values())))}`",
            )

        target_ext = ALIASES[target_raw]


        reply = await event.get_reply_message()
        target_msg = reply if reply and reply.file else event

        if not target_msg.file:
            return await send_or_edit_response(
                event,
                "**Кинь файл или ответь `.convert <формат>` на файл.**",
            )

        orig_name = target_msg.file.name or f"file.{target_msg.file.ext.lstrip('.')}"

        async def _run():
            status_msg = await send_or_edit_response(
                event, f"**Конвертирую** `{orig_name}` → `.{target_ext}`..."
            )
            src_path = None
            dst_path = None
            try:
                loop = asyncio.get_running_loop()


                src_path = await target_msg.download_media(file=TMP_DIR)


                dst_path = await loop.run_in_executor(None, _convert_sync, src_path, target_ext)


                base_name = os.path.splitext(orig_name)[0]
                out_name = f"{base_name}.{target_ext}"
                out_dir = os.path.dirname(dst_path)
                final_path = os.path.join(out_dir, out_name)
                if os.path.exists(final_path):
                    os.remove(final_path)
                os.rename(dst_path, final_path)
                dst_path = final_path


                reply_to_id = event.reply_to_msg_id if event.out else event.id
                await client.send_file(
                    event.chat_id,
                    file=dst_path,
                    reply_to=reply_to_id,
                    force_document=True,
                )

                if event.out:
                    await event.delete()
                else:
                    await status_msg.delete()

            except Exception as e:
                await send_or_edit_response(event, f"**Сбой конвертации:** `{e}`", status_msg=status_msg)
            finally:
                for p in (src_path, dst_path):
                    if p and os.path.exists(p):
                        try:
                            os.remove(p)
                        except OSError:
                            pass

        await execute_tracked_task(client, event, _run(), "document")