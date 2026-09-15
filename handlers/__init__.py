from telethon import TelegramClient
from handlers.moderation import register_moderation_handlers
from handlers.ai_tools import register_ai_handlers
from handlers.media import register_media_handlers
from handlers.fun import register_fun_handlers
from handlers.dump import register_dump_handlers
from handlers.video import register_video_handlers
from handlers.convert import register_convert_handlers


def register_handlers(client: TelegramClient):
    """Регистрация всех хэндлеров клиента."""
    register_moderation_handlers(client)
    register_ai_handlers(client)
    register_media_handlers(client)
    register_fun_handlers(client)
    register_dump_handlers(client)
    register_video_handlers(client)
    register_convert_handlers(client)