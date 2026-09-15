📱 UserBot для Telegram

Многофункциональный юзербот на базе Telethon с ИИ, поиском, музыкой, видео, конвертацией и модерацией.

---

🚀 Возможности

🤖 ИИ (Gemini)

· .ai — запрос к Gemini (2 тира: быстрый и умный)
· .aifile — длинный ответ отдельным .txt файлом
· .last — дополнить предыдущий запрос
· .clear — сбросить контекст чата
· Поддержка изображений/файлов (до 15 МБ) через реплай
· Подмешивание N предыдущих сообщений в контекст (*N)

🔍 Поиск

· .search — поиск в DuckDuckGo → парсинг страниц → фактологический ответ ИИ
· .photo — поиск и отправка картинки с фильтрацией мусорных домен

🎵 Музыка

· .music — скачать аудио с YouTube (трек/ссылка/плейлист до 50 треков)
· .musictext — найти текст песни
· .findmusic — поиск трека по строкам или описанию

🎬 Видео

· .tt — скачать TikTok без водяного знака (yt-dlp + tikwm API)
· .yt — скачать YouTube в максимальном качестве (video+audio через ffmpeg)

🔄 Конвертация

· .convert <формат> — конвертирует прикреплённый/отвеченный файл

Поддерживаемые форматы:

· 🖼 Картинки: png, jpg, webp, bmp, tiff, gif, ico
· 🎵 Аудио: mp3, wav, ogg, opus, m4a, flac, aac
· 🎬 Видео: mp4, mkv, webm, avi, mov
· Видео → GIF, Видео → аудио (вытянуть звук)

🛡 Модерация

· .mute <10m|10h|10d> — мут пользователя (реплаем или в ЛС)
· .unmute — снять мут
· .delsms <N> [0|1] — удалить сообщения
  · без режима — только свои
  · 0 — все подряд
  · 1 — только чужие

⚙️ Разное

· .agro <1|2> <N> <стиль> — спам-монолог на N слов (стриминг от ИИ)
· .dump <N> [ids] — выгрузить N сообщений чата в .txt (уходит в «Избранное»)
· .stop — отменить текущую задачу
· .help [тема | all] — подробная справка

---

📦 Установка

1. Требования

· Python 3.10+
· ffmpeg (для видео/аудио конвертации и YouTube)
· yt-dlp (для скачивания видео)
· Pillow (для быстрой конвертации картинок)

2. Установка ffmpeg

Ubuntu/Debian:

```bash
sudo apt update && sudo apt install -y ffmpeg
```

macOS:

```bash
brew install ffmpeg
```

Windows: скачать с ffmpeg.org и добавить в PATH.

3. Клонирование и установка зависимостей

```bash
git clone <repo_url>
cd <repo_dir>
pip install -r requirements.txt
```

Или вручную:

```bash
pip install telethon python-dotenv aiohttp pillow yt-dlp duckduckgo-search google-generativeai beautifulsoup4 lxml
```

4. Получение API-ключей

Telegram API (обязательно):

1. Зайти на https://my.telegram.org
2. Создать приложение → получить api_id и api_hash

Gemini API (обязательно для ИИ):

1. Зайти на https://aistudio.google.com/app/apikey
2. Создать API-ключ

5. Настройка .env

Создай файл .env в корне проекта:

```env
API_ID=1234567
API_HASH=your_api_hash_here
GEMINI_API_KEY=your_gemini_api_key_here
```

6. Первый запуск

```bash
python main.py
```

При первом запуске Telethon попросит:

· номер телефона (в формате +79991234567)
· код подтверждения из Telegram
· пароль 2FA (если включён)

После успешного входа создастся файл my_session.session — сессия сохранится.

---

🗂 Структура проекта

```
.
├── main.py              # Точка входа, инициализация клиента
├── services.py          # Реэкспорт утилит (единая точка импорта)
├── .env                 # Секреты (не коммитить!)
├── log.txt              # Логи (создаётся при запуске)
│
├── ai/                  # ИИ-клиент и стриминг ответов
├── core/                # Состояние чатов, общие утилиты
├── handlers/            # Все хэндлеры команд
│   ├── __init__.py
│   ├── ai_tools.py      # .ai, .aifile, .search, .photo, .last, .help
│   ├── media.py         # .music, .musictext, .findmusic
│   ├── video.py         # .tt, .yt
│   ├── convert.py       # .convert
│   ├── moderation.py    # .mute, .unmute, .delsms
│   ├── fun.py           # .agro
│   └── dump.py          # .dump
├── search/              # DDG, парсинг страниц, музыка, лирика
└── my_session.session   # Сессия Telegram (создаётся автоматически)
```

---

⚙️ Кастомизация

Доступ только для владельца и друга

В каждом хэндлере есть переменная ALLOWED_FRIEND_ID. Замени None на ID друга, чтобы дать доступ:

```python
ALLOWED_FRIEND_ID = 123456789  # его user_id
```

Узнать ID можно через @userinfobot в Telegram.

Блокировка доменов в поиске

В handlers/ai_tools.py:

```python
BLOCKED_DOMAINS = (".ru", ".rf", ".su", "rbk.ru", "yandex", "mail.ru", "vk.com", "ok.ru")
```

Токсичный режим для конкретного пользователя

```python
DALBOEBS = [123456789]  # ID пользователей, которых бот будет поливать матом
```

Уровни логов

В main.py:

```python
logging.basicConfig(level=logging.WARNING, ...)  # или INFO / DEBUG
```

---

🔧 Troubleshooting

Проблема Решение
ffmpeg не найден Установи ffmpeg и добавь в PATH
yt_dlp не установлен pip install -U --pre yt-dlp
RuntimeError: API_ID или API_HASH отсутствуют Проверь .env
API_ID должен быть числом В .env без кавычек, только цифры
Скачалось только аудио с YouTube Установи ffmpeg — без него yt-dlp не склеит видео+аудио
database is locked (session) Закрой все запущенные копии бота
FloodWait от Telegram Подожди указанное время, бот сам обрабатывает

---

📝 Использование

Все команды начинаются с точки: .команда.

Примеры:

```
.ai 2 *10 Что нового в Python 3.13?
.aifile Напиши подробный гайд по asyncio
.search курс биткоина сегодня
.photo кот в шляпе
.music Linkin Park - Numb
.musictext Radiohead - Creep
.findmusic "I'm a creep, I'm a weirdo"
.tt https://vm.tiktok.com/xxxxx
.yt https://youtu.be/dQw4w9WgXcQ
.convert png          (реплаем на .webp файл)
.mute 10m             (реплаем на сообщение)
.delsms 20 1          (удалить 20 чужих сообщений)
.agro 1 200 злой      (200 слов злого монолога, быстро)
.help ai              (справка по ИИ)
```

---