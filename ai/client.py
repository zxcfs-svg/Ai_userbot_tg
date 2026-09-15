import os
import asyncio
import logging
import aiohttp
import base64
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()


class GeminiClient:
    def __init__(self):
        self.models = {
            1: "gemini-3.5-flash-lite",
            2: "gemini-3.8-flash",
        }

        raw_keys = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY", "")
        self.keys = [k.strip() for k in raw_keys.split(",") if k.strip()]

        if not self.keys:
            raise RuntimeError("Пиздец: ключи не найдены в .env")

        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session

        async with self._session_lock:
            if self._session is None or self._session.closed:
                timeout = aiohttp.ClientTimeout(total=30, connect=10)
                connector = aiohttp.TCPConnector(limit=32, ttl_dns_cache=300)
                self._session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector,
                )
        return self._session

    async def close(self):
        if self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def fetch_ai_stream(
        self,
        tier: int,
        prompt: str,
        system_instruction: str = "Ответь коротко и по факту.",
        media_data: dict = None,
    ):
        model = self.models.get(tier, self.models[1])

        contents = []
        if prompt:
            contents.append(prompt)

        if media_data:
            raw_bytes = base64.b64decode(media_data["data"])
            contents.append(
                types.Part.from_bytes(
                    data=raw_bytes,
                    mime_type=media_data["mime_type"],
                )
            )

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        )

        last_error = None


        for attempt in range(2):
            for key in self.keys:
                try:
                    async with genai.Client(api_key=key).aio as client:
                        response_stream = await client.models.generate_content_stream(
                            model=model,
                            contents=contents,
                            config=config,
                        )

                        async for chunk in response_stream:
                            if chunk.text:
                                yield model, chunk.text
                        return

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    last_error = f"{type(e).__name__}: {e}"
                    logging.warning(f"Gemini key failed (attempt {attempt+1}): {last_error}")
                    continue

            if attempt == 0:
                await asyncio.sleep(1.0)

        raise RuntimeError(f"Сбой ключей. Последняя ошибка: {last_error}")


ai_client = GeminiClient()