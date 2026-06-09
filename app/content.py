"""
Контент для welcome-флоу и сообщений бота.
Обновляется вручную по мере поступления новых данных.
"""
from pathlib import Path

WELCOME_DIR = Path(__file__).parent.parent / "welcome"

PAYOUTS_WEEK = {
    "period": "06.04.2026 — 12.04.2026",
    "total_amount": 31850,
    "total_count": 24,
    "average": 1327,
    "top": [
        ("Улыкбек Р.", 4450),
        ("Ulyana M.", 3438),
        ("Zhazira M.", 3165),
        ("Vitaliy G.", 2517),
        ("Назира О.", 2317),
    ],
}

WELCOME_MEDIA = {
    "team_traders": str(WELCOME_DIR / "team_adilbek_traders.jpg"),
    "cert_ulyana": str(WELCOME_DIR / "cert_ulyana.jpg"),
    "cert_ulykbek": str(WELCOME_DIR / "cert_ulykbek.jpg"),
}

TRUST_LINKS = {
    "astana_hub": "https://astanahub.com/account/company/6248/",
    "office_2gis": "https://2gis.kz/almaty/firm/70000001025758522",
    "website": "https://youtradeprop.com",
}


def _num(n: int) -> str:
    """Форматируем число с пробелами: 31850 -> 31 850"""
    return f"{n:,}".replace(",", " ")


def _plural_payouts(n: int) -> str:
    """Правильное склонение: 1 выплата, 2-4 выплаты, 5+ выплат"""
    if n % 10 == 1 and n % 100 != 11:
        return "выплата"
    if 2 <= n % 10 <= 4 and not (12 <= n % 100 <= 14):
        return "выплаты"
    return "выплат"


def format_payouts_block() -> str:
    p = PAYOUTS_WEEK
    top_lines = []
    medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
    for i, (name, amount) in enumerate(p["top"]):
        prefix = medals[i] if i < len(medals) else f"{i+1}."
        top_lines.append(f"{prefix} {name} — ${_num(amount)}")
    top_str = "\n".join(top_lines)
    total = f"${_num(p['total_amount'])}"
    count = p["total_count"]
    plural = _plural_payouts(count)
    return (
        f"За прошлую неделю выплатили {total} нашим трейдерам ({count} {plural}).\n\n"
        f"🏆 Топ-5 выплат недели:\n{top_str}\n\n"
        "Это обычные люди, которые прошли челлендж и торгуют по правилам."
    )


WELCOME_MESSAGES = [
    {
        "text": (
            "Добро пожаловать в YouTrade! 👋\n\n"
            "Мы — проп-компания, резидент Astana Hub (государственный IT-хаб Казахстана).\n"
            "Даём капитал до $200,000 трейдерам. Забираете 80% прибыли.\n\n"
            "Это платная услуга. Входной билет — $39.\n\n"
            "За эти деньги вы получаете:\n"
            "→ Доступ к капиталу до $200,000\n"
            "→ 80% всей прибыли\n"
            "→ Профессиональную платформу MatchTrader\n"
            "→ Личного менеджера после покупки\n"
            "→ Обучалку и поддержку\n\n"
            "Проверить нас можно тут:\n"
            f"🏛 Astana Hub: {TRUST_LINKS['astana_hub']}\n"
            f"📍 Офис в Алматы: {TRUST_LINKS['office_2gis']}"
        ),
        "media": None,
        "delay_after": 3,
    },
    {
        "text": format_payouts_block(),
        "media": None,
        "delay_after": 2,
    },
    {
        "text": "Вот наши трейдеры с сертификатами о выплатах, в офисе с основателем Адильбеком Кубаевым:",
        "media": WELCOME_MEDIA["team_traders"],
        "delay_after": 2,
    },
    {
        "text": "Примеры сертификатов которые получают наши трейдеры при выплатах:",
        "media": [WELCOME_MEDIA["cert_ulyana"], WELCOME_MEDIA["cert_ulykbek"]],
        "delay_after": 2,
    },
    {
        "text": (
            f"Больше фото команды и видео от реальных трейдеров — на нашем сайте:\n"
            f"{TRUST_LINKS['website']}"
        ),
        "media": None,
        "delay_after": 3,
    },
    {
        "text": (
            "Меня зовут Аружан, я помогу разобраться и подобрать подходящий вариант.\n\n"
            "Если впервые слышите про проп-трейдинг — не переживайте. "
            "У нас есть бесплатное демо для практики и интерактивная обучалка из 7 уроков.\n\n"
            "Расскажите коротко: торгуете сейчас или только планируете начать?"
        ),
        "media": None,
        "delay_after": 0,
    },
]
