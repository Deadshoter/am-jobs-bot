"""Чтение публичных Telegram-каналов через их веб-версию t.me/s/<канал>.

Без аккаунта, без ключей API и без кодов входа. Работает только для публичных
каналов (у которых есть @юзернейм). Закрытые чаты так не читаются.
"""
import logging
from datetime import datetime

import requests
from bs4 import BeautifulSoup

from sites import HEADERS

log = logging.getLogger("tg")


def fetch_channel(username: str) -> list[dict]:
    """Последние ~20 постов канала: [{"id", "url", "date", "text"}]."""
    url = f"https://t.me/s/{username}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=25)
        r.raise_for_status()
    except Exception as e:
        log.warning("@%s недоступен: %s", username, e)
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    out = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        post = msg["data-post"]  # "channel/123"
        body = msg.select_one(".tgme_widget_message_text")
        if not body:
            continue
        for br in body.find_all("br"):
            br.replace_with("\n")
        text = body.get_text().strip()
        t = msg.select_one("time[datetime]")
        date = None
        if t:
            try:
                date = datetime.fromisoformat(t["datetime"])
            except ValueError:
                pass
        out.append({
            "id": post,
            "url": f"https://t.me/{post}",
            "date": date,
            "text": text,
        })
    if not out and "tgme_channel_info" not in r.text:
        log.warning("@%s: веб-версия закрыта (это группа или приватный канал)", username)
    return out
