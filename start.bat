@echo off
rem Launch script for Telegram News Bot (Project 9).
rem Reads TG_TOKEN from the root .env, sets NEWS_BOT_TOKEN, runs the bot.
cd /d "%~dp0"

for /f "usebackq tokens=1,* delims==" %%a in ("..\.env") do (
    if "%%a"=="TG_TOKEN" set "NEWS_BOT_TOKEN=%%b"
)
if not defined NEWS_BOT_TOKEN (
    echo [ERROR] TG_TOKEN not found in ..\.env
    pause
    exit /b 1
)

rem 0 = real RSS/Atom feeds (needs internet) | 1 = demo mode (offline)
set "NEWS_DEMO_MODE=1"
set "PYTHONIOENCODING=utf-8"

..\.venv\Scripts\python.exe -u bot.py
