"""AM Jobs Bot — один прогон. GitHub Actions запускает его каждые 15 минут.

За прогон:
1. читает Telegram-каналы (через веб-версию t.me/s) и сайты Djinni / Work.ua / Robota.ua;
2. отбирает вакансии Affiliate Manager, убирает скам, дубли и всё старше 7 дней;
3. складывает новые в очередь;
4. публикует до 10 вакансий в день, по одной в час, с 9:00 до 19:00 по Киеву;
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
TZ = ZoneInfo("Europe/Kyiv")
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
    st["recent"] = [x for x in st.get("recent", []) if now - x["ts"] < 14 * 24 * 3600][-600:]
    st["posted"] = [x for x in st.get("posted", []) if now - x["ts"] < 14 * 24 * 3600][-300:]
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
    parts.append("#вакансия #affiliate_manager" + (" #без_опыта" if entry else ""))
    return "\n".join(parts)


def accept(st, text, keys):
    if not filters.is_am_vacancy(text) or not filters.looks_like_vacancy(text):
        return False
    if not filters.has_contact(text):
        return False  # нет контакта для отклика — не публикуем
    if filters.is_resume(text):
        return False  # резюме соискателя, а не вакансия
    if filters.is_digest(text):
        return False  # подборка/дайджест вакансий, а не одна вакансия AM
    if filters.is_scam(text):
        log.info("Скам отфильтрован: %s", text[:70].replace("\n", " "))
        return False
    keys = keys + ["fp:" + filters.fingerprint(text)]
    if any(k in st["seen"] for k in keys):
        return False
    w = filters.words(text)
    for rec in st.setdefault("recent", []):
        if filters.similarity(w, set(rec["w"])) >= 0.7:
            return False  # та же вакансия с мелкими правками
    st["recent"].append({"ts": time.time(), "w": sorted(w)[:300]})
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
            if ch.lower() == "reg2bet" and "#r2bwork" not in p["text"].lower():
                continue  # R2B — медиа: берём только посты с тегом вакансий
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
POSTS_PER_DAY = 10
POST_FROM, POST_TO = 9, 19   # публикуем с 9:00 до 19:00 по Киеву


def publish_one(st):
    st["queue"] = [q for q in st["queue"] if is_fresh(q["ts"])
                   and filters.looks_like_vacancy(q["post"])
                   and filters.has_contact(q["post"])
                   and not filters.is_resume(q["post"])
                   and not filters.is_digest(q["post"])
                   and not ("@reg2bet" in q["post"] and "#r2bwork" not in q["post"].lower())]
    st["queue"].sort(key=lambda q: q["ts"], reverse=True)  # сначала самые свежие
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    if st.get("day") != today:
        st["day"], st["posted_today"] = today, 0
    if not st["queue"]:
        log.info("Очередь пуста")
        return
    if not (POST_FROM <= now.hour < POST_TO) and not DRY:
        log.info("Вне окна 9:00–19:00 — не публикую. В очереди %d", len(st["queue"]))
        return
    # одна вакансия в час: к HH:00 должно быть опубликовано (HH-8) вакансий, максимум 10
    allowed = min(POSTS_PER_DAY, now.hour - POST_FROM + 1)
    if st["posted_today"] >= allowed and not DRY:
        log.info("Лимит на этот час исчерпан (%d/%d за день). В очереди %d",
                 st["posted_today"], POSTS_PER_DAY, len(st["queue"]))
        return
    while st["queue"]:
        wq = filters.words(st["queue"][0]["post"])
        if any(filters.similarity(wq, set(x["w"])) >= 0.7 for x in st.setdefault("posted", [])):
            st["queue"].pop(0)  # дубль уже опубликованной вакансии
            continue
        break
    if not st["queue"]:
        log.info("Очередь пуста")
        return
    item = st["queue"][0]
    item["post"] = "\n".join(l for l in item["post"].splitlines() if "Источник:" not in l)
    if "🟢" in item["post"] and not filters.is_entry_level(item["post"]):
        item["post"] = "\n".join(l for l in item["post"].splitlines() if "🟢" not in l).replace(" #без_опыта", "")
    if not BOT_TOKEN and not DRY:
        log.warning("Нет BOT_TOKEN. В очереди %d", len(st["queue"]))
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
        st["posted_today"] += 1
        st.setdefault("posted", []).append({"ts": time.time(), "w": sorted(filters.words(item["post"]))[:300]})
        log.info("Опубликовано (%d/%d сегодня). В очереди %d",
                 st["posted_today"], POSTS_PER_DAY, len(st["queue"]))
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
