import time
import asyncio
import logging

from telethon.errors import FloodWaitError, MessageIdInvalidError

from ai.client import ai_client
from core.state import chat_tasks


async def _stream_helper(
    event,
    tier: int,
    prompt: str,
    prefix: str,
    system_instruction: str = None,
    media_data: dict = None,
    target_msg=None,
):
    """
    Стриминг ответа от ИИ с защитой буфера.
    FloodWait на edit не подвешивает поток — ставит cooldown на конкретное сообщение.
    MessageIdInvalidError — сообщение удалено/недоступно, просто пропускаем.
    """
    last_update = time.time()
    last_rendered_text = ""
    current_model = ""
    full_accumulated_text = ""

    flood_cooldowns: dict[int, float] = {}


    if target_msg is not None:
        start_msg = target_msg
    elif event.out:
        start_msg = event
    else:
        start_msg = await event.respond("▌")

    msg_parts = [start_msg]

    kwargs = {}
    if system_instruction:
        kwargs["system_instruction"] = system_instruction
    if media_data:
        kwargs["media_data"] = media_data

    async for model, chunk in ai_client.fetch_ai_stream(tier, prompt, **kwargs):
        current_model = model
        if not chunk:
            continue

        full_accumulated_text += chunk

        chunks = [
            full_accumulated_text[i : i + 4000]
            for i in range(0, len(full_accumulated_text), 4000)
        ]


        while len(msg_parts) < len(chunks):
            try:
                new_msg = await msg_parts[-1].respond("▌")
                msg_parts.append(new_msg)
            except FloodWaitError as e:
                await asyncio.sleep(min(e.seconds, 3))
            except MessageIdInvalidError:
                break
            except Exception:
                break

        current_idx = min(len(chunks) - 1, len(msg_parts) - 1)
        current_part_text = chunks[current_idx]

        now = time.time()
        if now - last_update <= 0.6:
            continue

        if now < flood_cooldowns.get(current_idx, 0):
            continue

        if current_part_text == last_rendered_text:
            continue

        header = f"**{prefix} | {model}**:\n" if current_idx == 0 else ""
        try:
            await asyncio.wait_for(
                msg_parts[current_idx].edit(header + current_part_text + " ▌"),
                timeout=5.0,
            )
            last_rendered_text = current_part_text
            last_update = now
        except FloodWaitError as e:
            flood_cooldowns[current_idx] = now + min(e.seconds, 15)
            logging.warning(
                f"Stream edit FloodWait {e.seconds}s — cooldown on part {current_idx}"
            )
        except MessageIdInvalidError:

            flood_cooldowns[current_idx] = float("inf")
            continue
        except asyncio.TimeoutError:
            logging.warning(f"Stream edit timeout on part {current_idx}, skip")
            continue
        except asyncio.CancelledError:
            raise
        except Exception:
            pass


    final_chunks = [
        full_accumulated_text[i : i + 4000]
        for i in range(0, max(1, len(full_accumulated_text)), 4000)
    ]
    for i, msg in enumerate(msg_parts):
        header = f"**{prefix} | {current_model}**:\n" if i == 0 else ""
        final_text = final_chunks[i] if i < len(final_chunks) else ""
        if not final_text:
            continue

        payload = header + final_text
        try:
            await asyncio.wait_for(msg.edit(payload), timeout=5.0)
        except FloodWaitError as e:
            await asyncio.sleep(min(e.seconds, 20))
            try:
                await msg.edit(payload)
            except MessageIdInvalidError:
                continue
            except Exception:
                pass
        except MessageIdInvalidError:
            continue
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            raise
        except Exception:
            pass


async def execute_tracked_task(client, event, coro, action="typing"):
    """Менеджер задач с отменой предыдущей и гарантированной очисткой."""
    chat_id = event.chat_id

    existing = chat_tasks.get(chat_id)
    if existing is not None and not existing.done():
        existing.cancel()
        try:
            await existing
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logging.error(f"Prev task await error: {e}")

    async def wrapped():
        async with client.action(chat_id, action):
            await coro

    task = asyncio.create_task(wrapped())
    chat_tasks[chat_id] = task

    try:
        await task
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logging.error(f"Tracked task error: {e}")
    finally:
        current = chat_tasks.get(chat_id)
        if current is task:
            chat_tasks.pop(chat_id, None)