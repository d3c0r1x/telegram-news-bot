# Telegram News Bot 📰

Новостной бот для Telegram: читает **RSS 2.0 и Atom** ленты, показывает свежие
новости, запоминает уже виденные (дедупликация) и присылает ежедневный дайджест
только из новых материалов. Парсер написан на стандартной библиотеке
(`xml.etree`) — без сторонних RSS-библиотек.

## Возможности

| Команда | Описание |
|---|---|
| `/news [URL]` | Свежие новости (по умолчанию Lenta.ru; своя лента — по URL) |
| `/sources` | Встроенные ленты: Lenta, Habr, BBC World, Коммерсантъ |
| `/digest on\|off` | Ежедневный дайджест подписанной ленты в 9:00 |
| `/latest` | Последние сохранённые новости из БД |
| `/stats` | Сколько новостей обработано, число подписок |

## Продвинутый уровень (v2)

- **Единый парсер RSS и Atom** на stdlib: схема определяется по корневому тегу,
  кодировки лент (включая windows-1251) читаются из байтов самим expat,
  HTML-сущности разворачиваются (`html.unescape`), RFC-822 и ISO-8601 даты
  приводятся к единому формату;
- **Дедупликация по `UNIQUE(link)`** — одна новость никогда не придёт дважды,
  даже если лента обновилась заново (`INSERT OR IGNORE`, возвращает число новых);
- **TTL-кэш лент** (10 мин — типичный интервал обновления RSS);
- **Устойчивость к «грязным» лентам** — парсер не падает на отсутствующих полях;
- **Middlewares** — троттлинг и логирование;
- **APScheduler cron** — дайджест шлёт только новые материалы.

## Структура

```
telegram-news-bot/
├── bot.py            # aiogram v3: команды, дайджест, сборка Dispatcher
├── config.py         # переменные окружения + встроенные ленты
├── rss_parser.py     # stdlib-парсер RSS/Atom + httpx-загрузчик + демо-пул
├── db.py             # aiosqlite: дедупликация статей, подписки
├── utils.py          # TTL-кэш, retry с джиттером (stdlib)
├── middlewares.py    # троттлинг + логирование
├── tests/            # unit-тесты парсинга (RSS/Atom/windows-1251) и БД
├── requirements.txt
├── pyproject.toml
├── Dockerfile        # docker run -e NEWS_BOT_TOKEN=...
├── .github/workflows/ci.yml  # CI: compileall + pytest на каждый push
└── run_bot9.cmd      # запуск в Windows (читает TG_TOKEN из корневого .env)
```

## Запуск

```bash
pip install -r requirements.txt
set NEWS_BOT_TOKEN=123456:ABC...
set NEWS_DEMO_MODE=0      # 0 = реальные ленты, 1 = оффлайн-демо
python bot.py
```

Или в Windows — двойной клик по `run_bot9.cmd` (токен берётся из `..\.env`).

## Тесты

```bash
python -m pytest tests/ -q
```

Тесты покрывают: парсинг RSS 2.0, Atom, ленту в windows-1251, разворот
HTML-сущностей, дедупликацию и подписки.

## Docker

```bash
docker build -t telegram-news-bot .
docker run -e NEWS_BOT_TOKEN=... -e NEWS_DEMO_MODE=0 telegram-news-bot
```
