"""Конфигурация Telegram News Bot через переменные окружения."""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

BOT_TOKEN = os.getenv("NEWS_BOT_TOKEN", "")
DB_PATH = os.getenv("NEWS_DB_PATH", os.path.join(BASE_DIR, "news.db"))

# 1 = демо-режим (оффлайн-новости, сеть не нужна) | 0 = реальные RSS/Atom ленты
DEMO_MODE = os.getenv("NEWS_DEMO_MODE", "1") == "1"

# Встроенные ленты (бесплатные, без ключа). Формат: название | URL
DEFAULT_FEEDS = [
    {"name": "Lenta.ru", "url": "https://lenta.ru/rss"},
    {"name": "Habr (всё)", "url": "https://habr.com/ru/rss/all/"},
    {"name": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Коммерсантъ", "url": "https://www.kommersant.ru/RSS/news.xml"},
]

# Лента по умолчанию (если пользователь не выбрал свою)
DEFAULT_FEED_URL = DEFAULT_FEEDS[0]["url"]

RSS_TIMEOUT = float(os.getenv("NEWS_RSS_TIMEOUT", "10"))
MAX_ITEMS = int(os.getenv("NEWS_MAX_ITEMS", "5"))

# Час ежедневного дайджеста (локальное время)
DIGEST_HOUR = int(os.getenv("NEWS_DIGEST_HOUR", "9"))

# --- Продвинутый уровень ---
# TTL кэша ленты (секунды): RSS-ленты обновляются раз в 10–30 минут
CACHE_TTL_SECONDS = float(os.getenv("NEWS_CACHE_TTL_SECONDS", "600"))
# Минимальный интервал между сообщениями пользователя (секунды)
THROTTLE_MIN_INTERVAL = float(os.getenv("THROTTLE_MIN_INTERVAL", "0.7"))
