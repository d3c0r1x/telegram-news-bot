"""RSS/Atom парсер на чистом stdlib (xml.etree) + httpx-клиент.

Поддерживает обе основные схемы:
  - RSS 2.0:  <rss><channel><item><title>/<link>/<pubDate>…
  - Atom:     <feed><entry><title>/<link href=…>/<updated>…

Продвинутый уровень:
  - namespace-агностичный поиск: ищем элементы по ЛОКАЛЬНОМУ имени
    (без «{http://…}» и префиксов вроде «dc:»), поэтому ленты с любыми
    пространствами имён и без них парсятся одинаково;
  - устойчивость к кодировкам: expat сам читает кодировку из байтов
    (RSS бывает windows-1251, iso-8859-1 и пр.);
  - единый парсер RSS и Atom — схема определяется по корневому тегу;
  - демо-режим с оффлайн-пулом новостей (тесты и запуск без сети);
  - pydantic-модель NewsItem (валидация полей).
"""
from __future__ import annotations

import html as _html
import random
import xml.etree.ElementTree as ET
from datetime import datetime

import httpx
from pydantic import BaseModel

import config

# Оффлайн-пул «новостей» для демо-режима и фолбэка
DEMO_POOL = [
    ("Курс доллара снизился на фоне роста нефтяных котировок", "https://demo.example/1"),
    ("В столице открылась новая линия метро", "https://demo.example/2"),
    ("Учёные представили прорыв в возобновляемой энергетике", "https://demo.example/3"),
    ("ИИ-ассистенты стали писать половину кода в крупных IT-компаниях", "https://demo.example/4"),
    ("Стартап собрал рекордный раунд инвестиций", "https://demo.example/5"),
    ("Анонсирован новый стандарт быстрой зарядки", "https://demo.example/6"),
]


class NewsItem(BaseModel):
    """Одна новость: заголовок, ссылка, дата, название источника."""

    title: str
    link: str
    published: str = ""  # ISO-строка; пусто, если даты нет в ленте
    source: str = ""


# ------------------------------------------------------- namespace-утилиты


def _local_name(tag: str) -> str:
    """Локальное имя тега без namespace и префикса.

    '{http://www.w3.org/2005/Atom}entry' -> 'entry'
    'dc:date'                            -> 'date'
    'pubDate'                            -> 'pubDate'
    """
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _iter_elements(root: ET.Element, local_name: str) -> list[ET.Element]:
    """Все потомки с данным локальным именем (namespace-агностично)."""
    return [el for el in root.iter() if _local_name(el.tag) == local_name]


def _first_text(element: ET.Element, *names: str) -> str:
    """Первое непустое текстовое значение среди локальных имён names."""
    wanted = {_local_name(n) for n in names}
    for el in element.iter():
        if _local_name(el.tag) in wanted and el.text and el.text.strip():
            return _html.unescape(el.text.strip())
    return ""


def _parse_date(value: str) -> str:
    """RFC-822 (RSS) и ISO-8601 (Atom) → единый ISO-формат; пусто при ошибке.

    RFC-822: 'Tue, 05 Aug 2026 10:00:00 +0300' — у публикаторов бывают разные
    локальные форматы, поэтому пробуем основные варианты и отдаём как есть,
    если не вышло (лента — источник ненадёжный, бот не должен падать).
    """
    value = (value or "").strip()
    if not value:
        return ""
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.isoformat(timespec="seconds")
        except ValueError:
            continue
    return value


def parse_feed(xml_bytes: bytes, source: str = "") -> list[NewsItem]:
    """Разбирает RSS 2.0 или Atom из байтов в список NewsItem.

    Байты (а не str) — чтобы expat сам применил кодировку из декларации.
    """
    root = ET.fromstring(xml_bytes)
    tag = _local_name(root.tag).lower()
    items: list[NewsItem] = []

    if tag in ("rss", "rdf"):
        # RSS 2.0 / RDF: элементы внутри channel/item
        for item in _iter_elements(root, "item"):
            title = _first_text(item, "title")
            link = _first_text(item, "link")
            published = _parse_date(_first_text(item, "pubDate", "dc:date"))
            if title and link:
                items.append(NewsItem(title=title, link=link, published=published, source=source))
    elif tag == "feed":
        # Atom: <entry><title>/<link href>/<updated>
        for entry in _iter_elements(root, "entry"):
            title = _first_text(entry, "title")
            link = ""
            for el in _iter_elements(entry, "link"):
                href = el.get("href")
                if href:
                    link = href.strip()
                    break
            published = _parse_date(_first_text(entry, "updated", "published"))
            if title and link:
                items.append(NewsItem(title=title, link=link, published=published, source=source))
    return items


def demo_feed(source: str = "Демо-лента", amount: int = 5) -> list[NewsItem]:
    """Оффлайн-«лента» из демо-пула (перемешанная выборка)."""
    return [
        NewsItem(title=t, link=l, source=source)
        for t, l in random.sample(DEMO_POOL, k=min(amount, len(DEMO_POOL)))
    ]


class FeedFetcher:
    """Загрузчик ленты: httpx + raise_for_status; демо-режим — без сети."""

    def __init__(self, timeout: float = config.RSS_TIMEOUT) -> None:
        self.timeout = timeout
        self.demo_mode = config.DEMO_MODE

    async def fetch(self, url: str, source: str = "") -> list[NewsItem]:
        if self.demo_mode:
            return demo_feed(source or url)
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers={"User-Agent": "telegram-news-bot/1.0"})
            resp.raise_for_status()
        return parse_feed(resp.content, source or url)
