"""Сбор вакансий с сайтов: Djinni, Work.ua, Robota.ua.

Каждая функция возвращает список словарей:
{"source": "Djinni", "title": ..., "company": ..., "url": ..., "text": ...}
Если сайт поменял вёрстку или заблокировал запрос — функция пишет ошибку в лог
и возвращает пустой список, бот продолжает работать с остальными источниками.
"""
import logging
import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

log = logging.getLogger("sites")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ru,uk;q=0.9,en;q=0.8",
}
QUERIES = ["affiliate manager", "аффилиат менеджер", "афіліат менеджер"]


def _get(url, **kw):
    r = requests.get(url, headers=HEADERS, timeout=25, **kw)
    r.raise_for_status()
    return r


# ---------------- Djinni ----------------
def djinni():
    out = []
    for q in ["affiliate manager", "affiliate"]:
        url = "https://djinni.co/jobs/"
        try:
            html = _get(url, params={"all_keywords": q, "search_type": "full-text"}).text
        except Exception as e:
            log.warning("Djinni недоступен: %s", e)
            return out
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('a[href^="/jobs/"]'):
            href = a.get("href", "")
            if not re.match(r"^/jobs/\d+", href):
                continue
            title = a.get_text(" ", strip=True)
            if not title:
                continue
            card = a.find_parent(["li", "div"])
            text = card.get_text(" ", strip=True) if card else title
            out.append({
                "source": "Djinni",
                "title": title,
                "company": "",
                "url": urljoin("https://djinni.co", href.split("?")[0]),
                "text": text,
            })
    return out


# ---------------- Work.ua ----------------
def workua():
    out = []
    for q in ["affiliate manager", "аффилиат менеджер", "афіліат менеджер"]:
        slug = q.replace(" ", "+")
        url = f"https://www.work.ua/jobs-{slug}/"
        try:
            html = _get(url).text
        except Exception as e:
            log.warning("Work.ua недоступен (%s): %s", q, e)
            continue
        soup = BeautifulSoup(html, "html.parser")
        for a in soup.select('h2 a[href^="/jobs/"]'):
            href = a.get("href", "")
            if not re.match(r"^/jobs/\d+", href):
                continue
            title = a.get("title") or a.get_text(" ", strip=True)
            card = a.find_parent("div")
            text = card.get_text(" ", strip=True) if card else title
            out.append({
                "source": "Work.ua",
                "title": title,
                "company": "",
                "url": urljoin("https://www.work.ua", href),
                "text": text,
            })
    return out


# ---------------- Robota.ua ----------------
def robotaua():
    out = []
    for q in QUERIES:
        try:
            data = _get(
                "https://api.robota.ua/vacancy/search",
                params={"keyWords": q, "sortBy": "Date", "page": 0},
            ).json()
        except Exception as e:
            log.warning("Robota.ua недоступен (%s): %s", q, e)
            continue
        for d in data.get("documents", []) or []:
            vid, cid = d.get("id"), d.get("notebookId")
            if not vid:
                continue
            title = d.get("name", "")
            out.append({
                "source": "Robota.ua",
                "title": title,
                "company": d.get("companyName", ""),
                "url": f"https://robota.ua/company{cid}/vacancy{vid}",
                "text": " ".join(str(x) for x in [
                    title, d.get("companyName", ""), d.get("cityName", ""),
                    d.get("shortDescription", ""), d.get("salary", "") or "",
                ]),
            })
    return out


ALL_SITES = {"Djinni": djinni, "Work.ua": workua, "Robota.ua": robotaua}
