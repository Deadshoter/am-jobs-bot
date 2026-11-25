"""AM Jobs Bot — один прогон. GitHub Actions запускает его каждые 15 минут.

За прогон:
1. читает Telegram-каналы (через веб-версию t.me/s) и сайты Djinni / Work.ua / Robota.ua;
2. отбирает вакансии Affiliate Manager, убирает скам, дубли и всё старше 7 дней;
3. складывает новые в очередь;
4. публикует ОДНУ вакансию из очереди в канал (то есть максимум 1 пост в 15 минут),
   ночью (23:00–08:00 по Киеву) не публикует;
5. сохраняет память бота в state.json.
"""
import html
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

import filters
import sites
import tg_web

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("bot")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
TARGET = os.environ.get("TARGET_CHANNEL", "@Focus_Affiliate")
MAX_AGE = timedelta(days=int(os.environ.get("MAX_AGE_DAYS", "7")))
TZ = ZoneInfo("Europe/Kiev")
QUIET_FROM, QUIET_TO = 23, 8
DRY = os.environ.get("DRY_RUN") == "1"
STATE_FILE = "state.json"
SEEN_TTL = 30 * 24 * 3600  # помним вакансию 30 дней


# ---------------- память ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            st = json.load(f)
    else:
        st = {}
    st.setdefault("seen", {})
    st.setdefault("queue", [])
    st.setdefault("sites_ready", [])
    return st


def save_state(st):
    now = time.time()
    st["seen"] = {k: v for k, v in st["seen"].items() if now - v < SEEN_TTL}
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=0)


# ---------------- помощники ----------------
def now_utc():
    return datetime.now(timezone.utc)


def is_fresh(ts: float) -> bool:
    return now_utc().timestamp() - ts <= MAX_AGE.total_seconds()


def quiet_now() -> bool:
    h = datetime.now(TZ).hour
    return h >= QUIET_FROM or h < QUIET_TO


def read_sources(path="sources.txt"):
    out = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.search(r"(?:t\.me/|@)([A-Za-z0-9_]{4,})", line)
        if m:
            out.append(m.group(1))
    return out


def build_post(body, source_name, source_url, title=""):
    body = body.strip()
    if len(body) > 1800:
        body = body[:1800].rsplit(" ", 1)[0] + "…"
    entry = filters.is_entry_level(title + " " + body)
    parts = ["💼 <b>Вакансия: Affiliate Manager</b>"]
    if entry:
        parts.append("🟢 <b>Можно без опыта / Junior</b>")
    parts.append("")
    if title:
        parts.append(f"<b>{html.escape(title)}</b>")
    parts.append(html.escape(body))
    parts.append("")
    parts.append(f'📌 Источник: <a href="{html.escape(source_url)}">{html.escape(source_name)}</a>')
    parts.append("#вакансия #affiliate_manager" + (" #без_опыта" if entry else ""))
    return "\n".join(parts)


def accept(st, text, keys):
    if not filters.is_am_vacancy(text):
        return False
    if filters.is_scam(text):
        log.info("Скам отфильтрован: %s", text[:70].replace("\n", " "))
        return False
    keys = keys + ["fp:" + filters.fingerprint(text)]
    if any(k in st["seen"] for k in keys):
        return False
    t = time.time()
    for k in keys:
        st["seen"][k] = t
    return True


# ---------------- сбор ----------------
def collect(st):
    added = 0
    # Telegram
    for ch in read_sources():
        posts = tg_web.fetch_channel(ch)
        for p in posts:
            ts = p["date"].timestamp() if p["date"] else time.time()
            if not is_fresh(ts):
                continue
            if accept(st, p["text"], ["tg:" + p["id"]]):
                st["queue"].append({"ts": ts, "post": build_post(p["text"], "@" + ch, p["url"])})
                added += 1
        log.info("@%s: постов %d", ch, len(posts))
    # Сайты
    for name, fn in sites.ALL_SITES.items():
        try:
            items = fn()
        except Exception as e:
            log.warning("%s: ошибка %s", name, e)
            continue
        first = name not in st["sites_ready"]
        for it in items:
            if not filters.is_am_vacancy(it["title"]):
                continue
            key = f"site:{name}:{it['url']}"
            if first:
                st["seen"][key] = time.time()  # первый запуск: запоминаем, не публикуем
                continue
            if accept(st, it["title"] + "\n" + it["text"], [key]):
                body = it["text"]
                if body.startswith(it["title"]):
                    body = body[len(it["title"]):]
                st["queue"].append({"ts": time.time(),
                                    "post": build_post(body, name, it["url"], it["title"])})
                added += 1
        if first and items:
            st["sites_ready"].append(name)
        log.info("%s: найдено %d%s", name, len(items), " (первый запуск — запомнил)" if first else "")
    return added


# ---------------- публикация ----------------
def publish_one(st):
    st["queue"] = [q for q in st["queue"] if is_fresh(q["ts"])]
    st["queue"].sort(key=lambda q: q["ts"])
    if not st["queue"]:
        log.info("Очередь пуста")
        return
    if quiet_now() and not DRY:
        log.info("Ночь — не публикую. В очереди %d", len(st["queue"]))
        return
    item = st["queue"][0]
    if not BOT_TOKEN and not DRY:
        log.warning("Нет BOT_TOKEN — жду, пока его добавят в Secrets. В очереди %d", len(st["queue"]))
        return
    if DRY:
        print("\n" + "=" * 50 + "\n" + item["post"] + "\n" + "=" * 50)
        st["queue"].pop(0)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
        json={"chat_id": TARGET, "text": item["post"], "parse_mode": "HTML",
              "disable_web_page_preview": True},
        timeout=30,
    )
    if r.ok:
        st["queue"].pop(0)
        log.info("Опубликовано. В очереди осталось %d", len(st["queue"]))
    else:
        log.error("Telegram не принял пост: %s", r.text[:300])


def main():
    st = load_state()
    added = collect(st)
    log.info("Новых вакансий в очередь: %d", added)
    publish_one(st)
    save_state(st)


if __name__ == "__main__":
    main()
