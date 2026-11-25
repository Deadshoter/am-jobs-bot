# AM Jobs Bot — вакансии Affiliate Manager в @Focus_Affiliate

Работает бесплатно в облаке GitHub Actions.

Каждые 15 минут бот читает Telegram-каналы из `sources.txt` и сайты Djinni, Work.ua, Robota.ua, берёт только вакансии Affiliate Manager не старше 7 дней, убирает скам и дубли и публикует одну вакансию в канал. Ночью (23:00–08:00 по Киеву) не публикует.

Токен бота хранится в Settings → Secrets and variables → Actions под именем `BOT_TOKEN`.
