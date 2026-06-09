#!/bin/bash
# deploy.sh — первичная установка на чистый CentOS
# Запуск: sudo bash deploy.sh
# ВАЖНО: это полуавтомат. Читайте README.md — вам всё равно нужно:
# 1) Заполнить .env
# 2) Настроить БД (пароль)
# 3) Получить SSL-сертификат через certbot

set -e

echo "=== YouTrade Bot Deploy Script ==="
echo

if [ "$EUID" -ne 0 ]; then
  echo "Error: запускайте через sudo"
  exit 1
fi

echo ">>> Устанавливаем системные пакеты..."
dnf install -y epel-release
dnf install -y python3.11 python3.11-devel python3.11-pip \
               postgresql-server postgresql-contrib \
               nginx certbot python3-certbot-nginx \
               git gcc firewalld policycoreutils-python-utils

echo ">>> Создаём пользователя youtrade..."
id youtrade &>/dev/null || useradd -m -s /bin/bash youtrade

mkdir -p /opt/youtrade-bot
chown youtrade:youtrade /opt/youtrade-bot

echo ">>> Создаём venv..."
cd /opt/youtrade-bot
if [ ! -d venv ]; then
  sudo -u youtrade python3.11 -m venv venv
fi
sudo -u youtrade ./venv/bin/pip install --upgrade pip
sudo -u youtrade ./venv/bin/pip install -r requirements.txt

echo ">>> Настраиваем firewall..."
systemctl enable --now firewalld
firewall-cmd --permanent --add-service=http
firewall-cmd --permanent --add-service=https
firewall-cmd --reload

echo ">>> Разрешаем nginx-проксирование (SELinux)..."
setsebool -P httpd_can_network_connect 1

echo ">>> Инициализируем PostgreSQL..."
if [ ! -f /var/lib/pgsql/data/pg_hba.conf ]; then
  postgresql-setup --initdb
fi
systemctl enable --now postgresql

echo
echo "=== Базовая установка закончена. ==="
echo
echo "Дальше:"
echo "1) Создайте БД: sudo -u postgres psql"
echo "   CREATE USER youtrade_bot WITH PASSWORD 'пароль';"
echo "   CREATE DATABASE youtrade_bot OWNER youtrade_bot;"
echo "2) Настройте /var/lib/pgsql/data/pg_hba.conf (md5 для youtrade_bot)"
echo "3) Заполните .env (cp .env.example .env, затем nano .env)"
echo "4) Миграции: sudo -u youtrade ./venv/bin/python -m app.migrate"
echo "5) SSL: sudo certbot --nginx -d bot.youtrade.kz"
echo "6) Скопируйте systemd service из README.md в /etc/systemd/system/youtrade-bot.service"
echo "7) sudo systemctl enable --now youtrade-bot"
echo "8) Регистрируем webhook: sudo -u youtrade ./venv/bin/python -m app.set_webhook"
echo
echo "Полная инструкция — в README.md"
