"""Тесты News Bot: парсинг RSS/Atom, дедупликация, подписки."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db import Database  # noqa: E402
from rss_parser import NewsItem, demo_feed, parse_feed  # noqa: E402

# Кириллица в XML: литерал должен быть str (bytes-литералы в Python 3.13
# не допускают не-ASCII), а в parse_feed передаём закодированные байты.
RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Test</title>
  <item><title>Первая новость</title><link>https://x.test/1</link>
    <pubDate>Tue, 05 Aug 2026 10:00:00 +0300</pubDate></item>
  <item><title>Вторая &amp; новость</title><link>https://x.test/2</link></item>
</channel></rss>""".encode("utf-8")

ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Atom feed</title>
  <entry><title>Atom-новость</title>
    <link href="https://x.test/atom"/><updated>2026-08-05T09:00:00Z</updated></entry>
</feed>""".encode("utf-8")

RSS_1251 = (
    "<?xml version='1.0' encoding='windows-1251'?><rss version='2.0'><channel>"
    "<title>Лента</title><item><title>Новость на русском</title>"
    "<link>https://x.test/rus</link></item></channel></rss>"
).encode("windows-1251")


# ------------------------------------------------------------ парсинг RSS

def test_parse_rss_items():
    items = parse_feed(RSS_XML, source="Test")
    assert len(items) == 2
    assert items[0].title == "Первая новость"
    assert items[0].link == "https://x.test/1"
    assert items[0].published  # RFC-822 дата разобрана


def test_parse_rss_unescapes_html_entities():
    items = parse_feed(RSS_XML)
    assert items[1].title == "Вторая & новость"


def test_parse_atom():
    items = parse_feed(ATOM_XML, source="Atom feed")
    assert len(items) == 1
    assert items[0].title == "Atom-новость"
    assert items[0].link == "https://x.test/atom"
    assert items[0].published.startswith("2026-08-05")


def test_parse_windows_1251():
    """Ленты в windows-1251 разбираются из байтов (expat сам читает кодировку)."""
    items = parse_feed(RSS_1251)
    assert len(items) == 1
    assert items[0].title == "Новость на русском"


def test_demo_feed_shape():
    items = demo_feed("Демо", amount=3)
    assert len(items) == 3
    assert all(isinstance(i, NewsItem) for i in items)
    assert all(i.title and i.link for i in items)


# --------------------------------------------------- БД: дедуп и подписки

def test_db_dedup_and_subscriptions(tmp_path):
    db_path = str(tmp_path / "news.db")

    async def run():
        db = Database(db_path)
        await db.init()

        # дедупликация: повторное сохранение той же новости = 0 новых
        items = [NewsItem(title="A", link="https://x/1"), NewsItem(title="B", link="https://x/2")]
        first = await db.save_articles(items)
        assert len(first) == 2 and first[0].link == "https://x/1"
        assert await db.save_articles(items) == []  # новые не вернулись
        assert await db.total_articles() == 2

        latest = await db.latest(limit=5)
        assert latest[0]["title"] == "B"  # свежайшая первой

        # подписки
        assert await db.subscribe(42, "https://feed.test/rss", "Test Feed") is True
        assert await db.subscribe(42, "https://feed.test/rss", "Test Feed") is False  # дубль
        assert len(await db.user_subscriptions(42)) == 1
        assert await db.unsubscribe(42, "https://feed.test/rss") is True
        assert await db.user_subscriptions(42) == []

        assert await db.all_subscriptions() == []

    asyncio.run(run())
