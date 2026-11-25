"""Фильтры: это вакансия аффилиат-менеджера? это скам? можно ли без опыта?"""
import hashlib
import re

# --- Должность: аффилиат-менеджер (все уровни) ---
# Ловим: affiliate manager, аффилиат/аффилейт/афилиат менеджер, афф-менеджер,
# аффменеджер, head of affiliate(s), affiliate team lead, affiliate lead и т.п.
_AFF = r"(?<![a-zа-яё])(?:affiliate|аф+[іи]л[іиеэ]+[аэе]?[йи]?т|аф+[іи]лейт|аф+)"
AM_PATTERNS = [
    rf"{_AFF}[\s\-_/]*(?:account\s*)?(?:manager|менеджер|менеджера|менеджеров|менеджерів)",
    rf"{_AFF}[\s\-_/]*(?:team\s*lead|teamlead|тимлид|тім\s*лід|lead|лид)",
    r"head\s+of\s+affiliates?",
    r"хед\s+аф+",
    r"\bаф+менеджер",
    r"#affiliate_?manager",
    r"#аф+_?менеджер",
]
AM_RE = re.compile("|".join(AM_PATTERNS), re.IGNORECASE)

# --- Признаки "можно без опыта / джун" ---
ENTRY_RE = re.compile(
    r"без\s+опыта|без\s+досвіду|опыт\s+не\s+(?:обязателен|нужен|важен)|досвід\s+не\s+(?:обов|потр)|"
    r"обучим|навчимо|научим|обучение\s+с\s+нуля|навчання\s+з\s+нуля|стаж[её]р|стажув|intern|junior|джун|trainee|опыт\s+от\s+0",
    re.IGNORECASE,
)
# Признаки, что новичков НЕ берут (перебивают ENTRY_RE)
NOT_ENTRY_RE = re.compile(
    r"(?:не\s+рассматр\w*|не\s+берём|не\s+берем|не\s+ищем|не\s+подходит)[^.\n]{0,60}(?:без\s+опыта|с\s+нуля|джун|junior|новичк)|"
    r"без\s+опыта\s+не|"
    r"опыт\w*\s+(?:работы\s+)?(?:[^.\n]{0,30})?от\s+(?:[1-9]|одного|года|полугода)|от\s+[1-9]\s*(?:\+\s*)?(?:год|лет|мес)|"
    r"\bsenior\b|\bmiddle\b|\blead\b|наличие\s+(?:собственной\s+|своей\s+)?базы|собственн\w+\s+баз",
    re.IGNORECASE,
)

# --- Признаки скама ---
SCAM_RE = re.compile(
    r"\d[\d\s]*\s*(?:₽|руб|\$|usd|грн|uah)\s*(?:в|за)\s*день|"
    r"(?:в|за)\s*день\s*от\s*\d|пассивн\w*\s+доход|без\s+вложений|"
    r"заработок\s+от\s+\d+\s*(?:₽|руб|\$)\s*(?:в|за)\s*(?:день|сутки|час)|"
    r"пиши\s+\+\s*в\s+лс|только\s+телефон\s+и\s+интернет",
    re.IGNORECASE,
)

# --- Признаки того, что пост — это вакансия, а не статья/новость ---
VACANCY_RE = re.compile(
    r"ваканси|vacanc|hiring|we.?re\s+looking|looking\s+for|ищем|шукаємо|требуется|потрібен|"
    r"открыта\s+позици|відкрита\s+позиці|зарплат|заробітн|оклад|salary|з/п|зп\s|"
    r"резюме|\bcv\b|откликнуться|відгукнутися|пишите|пиши\s|писать\s|контакт|requirements|обязанности|обов.язки|требования|вимоги",
    re.IGNORECASE,
)


def looks_like_vacancy(text: str) -> bool:
    return bool(VACANCY_RE.search(text or ""))

# --- Есть ли в вакансии контакт для отклика ---
CONTACT_RE = re.compile(
    r"(?<![\w/])@[A-Za-z][A-Za-z0-9_]{3,}|t\.me/|telegram\.me/|wa\.me/|"
    r"[\w.+-]+@[\w-]+\.[a-z]{2,}|"
    r"\+\d{1,3}[\s()\-]*\d[\d\s()\-]{7,}\d|(?<!\d)0\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)",
    re.IGNORECASE,
)


def has_contact(text: str) -> bool:
    """Без строки «Источник» — там ссылка на канал, это не контакт."""
    body = "\n".join(l for l in (text or "").splitlines() if "Источник" not in l)
    return bool(CONTACT_RE.search(body))

# --- Резюме соискателей (это не вакансии) ---
RESUME_RE = re.compile(
    r"#резюме|#resume|#cv\b|#ищу_?работу|#шукаю_?роботу|ищу\s+работу|шукаю\s+роботу|"
    r"открыт[аы]?\s+к\s+предложени|відкрит[аи]?\s+до\s+пропозиці|рассмотрю\s+предложени|"
    r"резюме\s+в\s+pdf|о\s+себе\b|про\s+себе\b|мой\s+опыт|мій\s+досвід|looking\s+for\s+a\s+job|open\s+to\s+work",
    re.IGNORECASE,
)


def is_resume(text: str) -> bool:
    return bool(RESUME_RE.search(text or ""))

# --- Похожесть текстов: ловим одну и ту же вакансию с мелкими правками ---
def words(text: str) -> set:
    t = (text or "").lower()
    t = re.sub(r"https?://\S+|#\w+", " ", t)
    return set(re.findall(r"[a-zа-яёіїєґ0-9@_]{3,}", t))


def similarity(a: set, b: set) -> float:
    return len(a & b) / max(1, min(len(a), len(b)))


def is_am_vacancy(text: str) -> bool:
    return bool(text) and bool(AM_RE.search(text))


def is_scam(text: str) -> bool:
    return bool(SCAM_RE.search(text or ""))


def is_entry_level(text: str) -> bool:
    t = text or ""
    return bool(ENTRY_RE.search(t)) and not NOT_ENTRY_RE.search(t)


def fingerprint(text: str) -> str:
    """Отпечаток текста для удаления дублей: одна вакансия в разных каналах."""
    t = (text or "").lower()
    t = re.sub(r"https?://\S+|t\.me/\S+|@\w+", " ", t)  # ссылки и юзернеймы
    t = re.sub(r"[^a-zа-яёіїєґ0-9]+", " ", t)           # эмодзи и знаки
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t[:400].encode()).hexdigest()
