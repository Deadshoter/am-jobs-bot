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
    r"без\s+опыта|без\s+досвіду|опыт\s+не\s+(?:обязателен|нужен|важен)|"
    r"досвід\s+не\s+(?:обов|потр)|обучим|навчимо|обучение\s+с\s+нуля|с\s+нуля|"
    r"стаж[её]р|стажув|intern|junior|джун|trainee|опыт\s+от\s+0|опыт\s+до\s+(?:6|полу)",
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


def is_am_vacancy(text: str) -> bool:
    return bool(text) and bool(AM_RE.search(text))


def is_scam(text: str) -> bool:
    return bool(SCAM_RE.search(text or ""))


def is_entry_level(text: str) -> bool:
    return bool(ENTRY_RE.search(text or ""))


def fingerprint(text: str) -> str:
    """Отпечаток текста для удаления дублей: одна вакансия в разных каналах."""
    t = (text or "").lower()
    t = re.sub(r"https?://\S+|t\.me/\S+|@\w+", " ", t)  # ссылки и юзернеймы
    t = re.sub(r"[^a-zа-яёіїєґ0-9]+", " ", t)           # эмодзи и знаки
    t = re.sub(r"\s+", " ", t).strip()
    return hashlib.sha1(t[:400].encode()).hexdigest()
