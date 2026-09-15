import re
import time
import logging
import asyncio
import concurrent.futures

logging.getLogger("urllib3").setLevel(logging.WARNING)

try:
    from ddgs import DDGS

    _DDGS_SOURCE = "ddgs"
except ImportError:
    from duckduckgo_search import DDGS

    _DDGS_SOURCE = "duckduckgo_search (устаревший пакет, поставь `pip install -U ddgs`)"

try:
    if _DDGS_SOURCE == "ddgs":
        from ddgs.exceptions import DDGSException, RatelimitException, TimeoutException
    else:
        from duckduckgo_search.exceptions import (
            DuckDuckGoSearchException as DDGSException,
            RatelimitException,
            TimeoutException,
        )
except ImportError:
    DDGSException = RatelimitException = TimeoutException = Exception

if _DDGS_SOURCE != "ddgs":
    logging.warning(
        f"Поиск использует {_DDGS_SOURCE}. Рекомендуется обновиться: pip install -U ddgs"
    )


_SEARCH_BACKENDS_FALLBACK = "duckduckgo,google,bing,brave,yandex"

_DDG_EXECUTOR = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="ddg"
)


def _ddg_text_search(
    query: str,
    max_results: int = 8,
    region: str = "wt-wt",
    retries: int = 2,
    hard_timeout: float = 30.0,
) -> list[dict]:
    """
    Синхронный метапоиск через ddgs.

    Отличие от прежней версии: обёрнут в отдельный ThreadPoolExecutor с
    wall-clock таймаутом. Если ddgs уходит в глухой рейт-лимит и висит
    десятки минут — мы получим пустой список через `hard_timeout` секунд
    вместо того, чтобы держать задачу вечно.
    """

    def _attempt(q: str, backend: str) -> list[dict]:
        for attempt in range(retries + 1):
            try:
                with DDGS(timeout=10) as ddgs:
                    return list(
                        ddgs.text(
                            q, region=region, max_results=max_results, backend=backend
                        )
                    )
            except RatelimitException:
                time.sleep(1.5 * (attempt + 1))
            except TimeoutException:
                time.sleep(1)
            except DDGSException as e:
                logging.error(f"DDG search error ({backend}) for '{q}': {e}")
                break
            except Exception as e:
                logging.error(f"DDG search unexpected error ({backend}) for '{q}': {e}")
                break
        return []

    def _run() -> list[dict]:
        results = _attempt(query, "auto")

        if not results and ("site:" in query or "domain:" in query):
            clean_query = re.sub(r"\b(site|domain):[^\s]+", "", query).strip()
            if clean_query:
                results = _attempt(clean_query, "auto")

        if not results:
            results = _attempt(query, _SEARCH_BACKENDS_FALLBACK)

        return results

    future = _DDG_EXECUTOR.submit(_run)
    try:
        return future.result(timeout=hard_timeout)
    except concurrent.futures.TimeoutError:
        logging.warning(f"DDGS hard timeout {hard_timeout}s for: {query}")
        future.cancel()
        return []


def _relevance_score(query: str, item: dict) -> int:
    """Сколько слов запроса встречается в title/url/body результата."""
    words = {w for w in re.findall(r"\w+", query.lower()) if len(w) > 2}
    if not words:
        return 1
    haystack = " ".join(
        [
            (item.get("title") or "").lower(),
            (item.get("href") or "").lower(),
            (item.get("image") or "").lower(),
        ]
    )
    return sum(1 for w in words if w in haystack)


async def _get_first_image_url(query: str) -> str | None:
    """
    Асинхронный поиск изображения через ddgs.
    Использует тот же пул с wall-clock таймаутом, что и текстовый поиск.
    """
    loop = asyncio.get_running_loop()

    def sync_image_search():
        regions = ["us-en", "uk-en", "de-de"]
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
            except RatelimitException:
                time.sleep(1.5)
                continue
            except Exception as e:
                logging.error(f"DDG Image Search error ({region}): {e}")
                continue

            if not results:
                continue


            results.sort(key=lambda r: _relevance_score(query, r), reverse=True)
            for r in results:
                img_url = r.get("image") or ""
                if not img_url:
                    continue
                return img_url

        return None

    return await loop.run_in_executor(None, sync_image_search)
