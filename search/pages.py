import re
import logging
import asyncio
import urllib.parse

import aiohttp

from ai.client import ai_client
from search.ddg import _ddg_text_search


def _extract_readable_text(html: str) -> str:
    """Достает читаемый текст страницы без скриптов/меню/футера. CPU-bound."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(
            ["script", "style", "nav", "header", "footer", "form", "noscript", "svg", "aside"]
        ):
            tag.decompose()
        text = soup.get_text("\n")
    except ImportError:
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)

    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    clean = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", clean)


async def _fetch_page_text(
    url: str,
    timeout: int = 12,
    max_chars: int = 4000,
    max_bytes: int = 5_000_000,
) -> str:
    """Fetch with size limit and timeout. BeautifulSoup уведён в executor."""
    if not url:
        return ""
    try:
        session = await ai_client.get_session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
        client_timeout = aiohttp.ClientTimeout(total=timeout)
        async with session.get(url, headers=headers, timeout=client_timeout) as resp:
            if resp.status != 200:
                return ""

            content_length = resp.content_length
            if content_length and content_length > max_bytes:
                return ""

            html = await resp.text(errors="replace")
            if len(html) > max_bytes:
                return ""
    except Exception as e:
        logging.error(f"Page fetch error ({url}): {e}")
        return ""


    loop = asyncio.get_running_loop()
    text = await loop.run_in_executor(None, _extract_readable_text, html)
    return text[:max_chars]


async def _fetch_lyrics_ovh(artist: str, title: str) -> str | None:
    """Структурированный источник текстов песен."""
    try:
        session = await ai_client.get_session()
        url = (
            f"https://api.lyrics.ovh/v1/"
            f"{urllib.parse.quote(artist)}/{urllib.parse.quote(title)}"
        )
        client_timeout = aiohttp.ClientTimeout(total=10)
        async with session.get(url, timeout=client_timeout) as resp:
            if resp.status != 200:
                return None
            data = await resp.json(content_type=None)
            lyrics = (data or {}).get("lyrics")
            if lyrics and len(lyrics.strip()) > 20:
                return lyrics.strip().replace("\r\n", "\n")
    except Exception as e:
        logging.error(f"lyrics.ovh error ({artist} - {title}): {e}")
    return None


async def _extract_genius_lyrics(url: str) -> str | None:
    """Вытаскивает реальный текст со страницы Genius."""
    try:
        session = await ai_client.get_session()
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }
        client_timeout = aiohttp.ClientTimeout(total=12)
        async with session.get(url, headers=headers, timeout=client_timeout) as resp:
            if resp.status != 200:
                return None
            html = await resp.text(errors="ignore")
    except Exception as e:
        logging.error(f"Genius fetch error ({url}): {e}")
        return None

    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logging.error("BeautifulSoup не установлен: pip install beautifulsoup4")
        return None

    def _parse(html_text: str) -> str | None:
        soup = BeautifulSoup(html_text, "html.parser")
        blocks = soup.find_all(attrs={"data-lyrics-container": "true"})
        if not blocks:
            return None

        parts = []
        for block in blocks:
            for br in block.find_all("br"):
                br.replace_with("\n")
            parts.append(block.get_text())

        raw = "\n".join(parts).strip()
        raw = re.sub(r"\d*Embed\s*$", "", raw).strip()
        raw = raw.replace("You might also like", "")
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw if len(raw) > 40 else None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _parse, html)


def _split_artist_title(query: str) -> list[tuple[str, str]]:
    """Разбивает строку вида 'Артист - Трек'."""
    parts = re.split(r"\s*[-–—]\s*", query, maxsplit=1)
    if len(parts) != 2:
        return []
    a, b = parts[0].strip(), parts[1].strip()
    if not a or not b:
        return []
    return [(a, b), (b, a)]


async def get_lyrics(query: str) -> dict | None:
    """Ищет реальный текст песни (lyrics.ovh -> Genius)."""
    for artist, title in _split_artist_title(query):
        lyrics = await _fetch_lyrics_ovh(artist, title)
        if lyrics:
            return {"text": lyrics, "source": f"lyrics.ovh: {artist} - {title}"}

    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, _ddg_text_search, f"{query} lyrics site:genius.com", 3
    )
    if not results:
        results = await loop.run_in_executor(
            None, _ddg_text_search, f"{query} genius lyrics", 5
        )

    for r in results:
        href = r.get("href", "") or ""
        if "genius.com" in href:
            lyrics = await _extract_genius_lyrics(href)
            if lyrics:
                return {"text": lyrics, "source": href}

    return None
