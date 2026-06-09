# QUICKSTART для разработчика

**Цель:** поднять Telegram бота "Алия" на CentOS 8/9 за пару часов.

## TL;DR

1. Залить архив на сервер, распаковать в `/opt/youtrade-bot/`
2. `bash deploy.sh` — поставит python, postgres, nginx
3. Создать БД, заполнить `.env`
4. Получить SSL (`certbot --nginx -d bot.youtrade.kz`)
5. Создать systemd-service (копипаст из README)
6. `python -m app.migrate` → `systemctl start youtrade-bot`
7. `python -m app.set_webhook` — регистрация webhook в Telegram

Подробности — в `README.md`.

---

## Что понадобится от Романа

Роман должен прислать:

1. **Telegram Bot Token** — создаётся через @BotFather в Telegram
2. **Claude API Key** — из https://console.anthropic.com
3. **Поддомен** — например `bot.youtrade.kz` с DNS на ваш сервер
4. **8 скриншотов MatchTrader** (положить в `/opt/youtrade-bot/screenshots/` с именами `01_login.jpg` … `08_prop_tab.jpg`)

---

## Что делать если что-то сломалось

### Проверка что бот жив
```bash
sudo systemctl status youtrade-bot
curl https://bot.youtrade.kz/health
```

### Логи
```bash
sudo journalctl -u youtrade-bot -f
```

### Статус webhook в Telegram
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```
Должно быть `"url": "https://bot.youtrade.kz/webhook"` и без `last_error_date`.

### Типичные проблемы

**"Connection refused" в nginx error.log** — SELinux:
```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl restart nginx
```

**"FATAL: password authentication failed"** — неверный пароль БД в `.env` или не настроен md5 в `pg_hba.conf`.

**"no module named app"** — не активировали venv. Запускать через `./venv/bin/python`, а не `python`.

---

## Админка

После деплоя:
```
https://bot.youtrade.kz/admin?key=<ADMIN_DASHBOARD_KEY>
```

Показывает:
- Общее число юзеров
- Активность 24ч/7д
- Воронку по шагам (0–8)
- A/B группы
- Последние 30 вопросов юзеров

---

## Архитектура

```
Пользователь → Telegram → ваш домен (nginx) → Python (uvicorn:8000) → PostgreSQL
                                                       ↓
                                               Claude API (для свободных вопросов)
```

Бот работает через webhook (не polling). Telegram сам дёргает ваш сервер когда есть новое сообщение.

---

## Контакт

Роман: WhatsApp +7 708 190 6251
