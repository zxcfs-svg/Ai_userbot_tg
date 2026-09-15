import os
import tempfile


def _download_track_sync(query: str):
    import yt_dlp

    out_dir = tempfile.gettempdir()

    opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{out_dir}/%(id)s.%(ext)s",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "320",
            }
        ],
        "writethumbnail": True,
        "quiet": True,
        "default_search": "ytsearch",
        "socket_timeout": 15,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=True)
        if "entries" in info:
            info = info["entries"][0]
        base_name = os.path.join(out_dir, info["id"])
        audio_file = f"{base_name}.mp3"
        thumb_file = None
        for ext in ["jpg", "webp", "png"]:
            if os.path.exists(f"{base_name}.{ext}"):
                thumb_file = f"{base_name}.{ext}"
                break
        duration = int(info.get("duration", 0))
        return (
            audio_file,
            thumb_file,
            info.get("title", "Unknown"),
            info.get("uploader", "Unknown"),
            duration,
        )


def _get_playlist_urls(query: str) -> list[str]:
    import yt_dlp

    opts = {"extract_flat": True, "quiet": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(query, download=False)
        if info and "entries" in info:
            urls = []
            for e in info["entries"]:
                if e.get("url"):
                    urls.append(e["url"])
                elif e.get("id"):
                    urls.append(f"https://www.youtube.com/watch?v={e['id']}")
            return urls
        return [info.get("webpage_url") or query] if info else []


def _search_music_by_text_sync(query: str) -> list[dict]:
    import yt_dlp

    opts = {"extract_flat": True, "quiet": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch5:{query}", download=False)
        return info.get("entries", []) if info else []
