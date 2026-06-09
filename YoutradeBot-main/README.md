# YouTrade Bot — Алия

Telegram бот-проводник для онбординга новых трейдеров YouTrade Prop.

**Стек:** Python 3.11 + FastAPI + PostgreSQL + Claude API (Haiku 4.5) + python-telegram-bot
**Деплой:** CentOS 8/9 + nginx + systemd + Let's Encrypt

---

## Содержание
1. [Требования](#требования)
2. [Установка на CentOS](#установка-на-centos)
3. [Настройка .env](#настройка-env)
4. [База данных](#база-данных)
5. [Nginx + SSL](#nginx--ssl)
6. [Systemd service](#systemd-service)
7. [Регистрация webhook](#регистрация-webhook)
8. [Проверка работы](#проверка-работы)
9. [Отладка](#отладка)
10. [Обновление кода](#обновление-кода)

---

## Требования

**Сервер:**
- CentOS 8/9 или RHEL 8/9
- Python 3.11+ (на CentOS 9 уже есть, на CentOS 8 надо устанавливать)
- PostgreSQL 14+
- nginx
- Публичный домен (например, `bot.youtrade.kz`) с DNS на сервер
- Открытые порты 80 и 443 (для SSL-сертификата и webhook)
- Минимум 1GB RAM

**Ключи и доступы:**
- Telegram Bot Token (создаётся через @BotFather)
- Claude API Key (из console.anthropic.com)

---

## Установка на CentOS

### 1. Подготовка сервера

```bash
sudo dnf update -y
sudo dnf install -y epel-release
sudo dnf install -y python3.11 python3.11-devel python3.11-pip \
                    postgresql-server postgresql-contrib \
                    nginx certbot python3-certbot-nginx \
                    git gcc
```

Если Python 3.11 не ставится:
```bash
sudo dnf install -y python3 python3-devel python3-pip
```
(3.9 тоже сработает, но 3.11 быстрее)

### 2. Создаём пользователя для бота

```bash
sudo useradd -m -s /bin/bash youtrade
sudo mkdir -p /opt/youtrade-bot
sudo chown youtrade:youtrade /opt/youtrade-bot
```

### 3. Загружаем код

Вариант А — через git (если код в репозитории):
```bash
sudo -u youtrade git clone <repo-url> /opt/youtrade-bot
```

Вариант Б — загружаем tar.gz, который вам прислал Роман:
```bash
sudo -u youtrade tar -xzf youtrade-bot.tar.gz -C /opt/
sudo chown -R youtrade:youtrade /opt/youtrade-bot
```

### 4. Создаём venv и ставим зависимости

```bash
cd /opt/youtrade-bot
sudo -u youtrade python3.11 -m venv venv
sudo -u youtrade ./venv/bin/pip install --upgrade pip
sudo -u youtrade ./venv/bin/pip install -r requirements.txt
```

### 5. Настраиваем firewall

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

### 6. SELinux (важно!)

CentOS по умолчанию блокирует nginx-проксирование на Python-сервер. Разрешаем:
```bash
sudo setsebool -P httpd_can_network_connect 1
```

---

## Настройка .env

```bash
sudo -u youtrade cp /opt/youtrade-bot/.env.example /opt/youtrade-bot/.env
sudo -u youtrade nano /opt/youtrade-bot/.env
```

Заполняем:

```env
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...
TELEGRAM_WEBHOOK_SECRET=случайная_длинная_строка
CLAUDE_API_KEY=sk-ant-...
DATABASE_URL=postgresql+asyncpg://youtrade_bot:ПАРОЛЬ@localhost:5432/youtrade_bot
WEBHOOK_BASE_URL=https://bot.youtrade.kz
ADMIN_CHAT_IDS=123456789
ADMIN_DASHBOARD_KEY=случайный_ключ_для_админки
MATCHTRADER_LOGIN=demo.ytr777@mail.ru
MATCHTRADER_PASSWORD=jAcrex-petqyw-kahke4
MATCHTRADER_URL=https://mtr.youtrade.kz/login
CHALLENGE_URL=https://youtradeprop.com/challenge-purchase
WHATSAPP_NUMBER=77081906251
```

**Как сгенерировать случайные ключи:**
```bash
openssl rand -hex 32
```

**Как узнать свой Telegram ID:**
Напишите боту @userinfobot — он пришлёт ваш numeric ID.

---

## База данных

```bash
sudo postgresql-setup --initdb
sudo systemctl enable --now postgresql

sudo -u postgres psql <<EOF
CREATE USER youtrade_bot WITH PASSWORD 'ВАШ_ПАРОЛЬ';
CREATE DATABASE youtrade_bot OWNER youtrade_bot;
GRANT ALL PRIVILEGES ON DATABASE youtrade_bot TO youtrade_bot;
EOF
```

Разрешаем подключение по паролю (редактируем `/var/lib/pgsql/data/pg_hba.conf`):
```bash
sudo nano /var/lib/pgsql/data/pg_hba.conf
```

Добавьте в начало (перед другими правилами):
```
local   youtrade_bot    youtrade_bot                            md5
host    youtrade_bot    youtrade_bot    127.0.0.1/32            md5
```

Перезапускаем:
```bash
sudo systemctl restart postgresql
```

Создаём таблицы:
```bash
cd /opt/youtrade-bot
sudo -u youtrade ./venv/bin/python -m app.migrate
```

Должно напечатать `Done!`

---

## Nginx + SSL

### 1. Получаем SSL-сертификат

```bash
sudo certbot --nginx -d bot.youtrade.kz
```

Certbot попросит email, согласие с TOS, и автоматически настроит nginx. Выберите "Redirect HTTP to HTTPS".

### 2. Конфиг nginx

Редактируем `/etc/nginx/conf.d/bot.conf`:

```nginx
server {
    listen 443 ssl http2;
    server_name bot.youtrade.kz;

    ssl_certificate /etc/letsencrypt/live/bot.youtrade.kz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.youtrade.kz/privkey.pem;

    location /webhook {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Telegram-Bot-Api-Secret-Token $http_x_telegram_bot_api_secret_token;
        client_max_body_size 20M;
    }

    location /admin {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /health {
        proxy_pass http://127.0.0.1:8000;
    }
}

server {
    listen 80;
    server_name bot.youtrade.kz;
    return 301 https://$server_name$request_uri;
}
```

Перезапускаем:
```bash
sudo nginx -t
sudo systemctl restart nginx
```

---

## Systemd service

Создаём `/etc/systemd/system/youtrade-bot.service`:

```ini
[Unit]
Description=YouTrade Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=youtrade
Group=youtrade
WorkingDirectory=/opt/youtrade-bot
Environment="PATH=/opt/youtrade-bot/venv/bin"
EnvironmentFile=/opt/youtrade-bot/.env
ExecStart=/opt/youtrade-bot/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Запускаем:
```bash
sudo systemctl daemon-reload
sudo systemctl enable youtrade-bot
sudo systemctl start youtrade-bot
sudo systemctl status youtrade-bot
```

Должно показать `active (running)`.

---

## Регистрация webhook

```bash
cd /opt/youtrade-bot
sudo -u youtrade ./venv/bin/python -m app.set_webhook
```

Должно вернуть `{'ok': True, 'result': True, 'description': 'Webhook was set'}`.

Проверить статус webhook:
```bash
curl "https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getWebhookInfo"
```

Поле `url` должно быть `https://bot.youtrade.kz/webhook`, `last_error_date` должно отсутствовать.

---

## Проверка работы

1. Найдите своего бота в Telegram (по username который задавали в @BotFather)
2. Нажмите Start или напишите `/start`
3. Бот должен ответить приветственным сообщением с кнопками

Если не отвечает — см. "Отладка".

Дашборд админки открывается по адресу:
```
https://bot.youtrade.kz/admin?key=<ADMIN_DASHBOARD_KEY>
```

---

## Отладка

### Логи бота
```bash
sudo journalctl -u youtrade-bot -f
```

### Логи nginx
```bash
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log
```

### Webhook не работает

Проверить что Telegram видит сервер:
```bash
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Если `last_error_message` содержит "SSL" — проблема с сертификатом.
Если "Connection refused" — бот не запущен или SELinux блокирует.

### Бот не отвечает но webhook OK

Проверить логи:
```bash
sudo journalctl -u youtrade-bot -n 100
```

Типичные ошибки:
- `FATAL: password authentication failed` — неверный пароль БД в `.env`
- `ModuleNotFoundError` — забыли установить зависимости в venv
- `anthropic.APIError` — проблема с Claude API ключом

### SELinux блокирует nginx

Если в `/var/log/nginx/error.log` видите "Permission denied":
```bash
sudo setsebool -P httpd_can_network_connect 1
sudo systemctl restart nginx
```

---

## Обновление кода

Когда Роман пришлёт обновление:

```bash
cd /opt/youtrade-bot

sudo -u youtrade cp .env .env.backup
sudo -u youtrade tar -xzf /tmp/youtrade-bot-update.tar.gz -C /opt/ --overwrite
sudo -u youtrade ./venv/bin/pip install -r requirements.txt
sudo -u youtrade ./venv/bin/python -m app.migrate
sudo systemctl restart youtrade-bot
sudo systemctl status youtrade-bot
```

---

## Структура проекта

```
/opt/youtrade-bot/
├── app/
│   ├── main.py           # FastAPI: /webhook, /admin, /health
│   ├── bot.py            # Логика бота: handlers, шаги, AI ответы
│   ├── scenario.py       # 8 шагов онбординга + help-сообщения
│   ├── ai.py             # Claude API (Haiku 4.5) для свободных вопросов
│   ├── admin.py          # Админка с воронкой и A/B сравнением
│   ├── db.py             # SQLAlchemy async engine
│   ├── models.py         # Таблицы: users, events, messages, media_cache
│   ├── config.py         # Pydantic settings из .env
│   ├── migrate.py        # python -m app.migrate
│   ├── set_webhook.py    # python -m app.set_webhook
│   └── polling.py        # Локальный режим без HTTPS (для отладки)
├── screenshots/          # jpg/png скриншоты MatchTrader (8 штук)
├── requirements.txt
├── .env.example          # Шаблон переменных
├── .env                  # Реальные ключи (не коммитить!)
├── README.md             # этот файл
├── deploy.sh             # Скрипт первичного деплоя (опционально)
└── update.sh             # Скрипт обновления (опционально)
```

## Безопасность

- Не коммитьте `.env` в git
- Ключ `ADMIN_DASHBOARD_KEY` периодически меняйте
- Бэкапьте БД регулярно:
  ```bash
  sudo -u postgres pg_dump youtrade_bot > /root/backup_$(date +%Y%m%d).sql
  ```
