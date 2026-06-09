#!/bin/bash
# update.sh — обновление кода на уже развёрнутом сервере
# Запуск: sudo bash update.sh /path/to/new-code.tar.gz

set -e

if [ -z "$1" ]; then
  echo "Использование: sudo bash update.sh /path/to/new-code.tar.gz"
  exit 1
fi

ARCHIVE="$1"
if [ ! -f "$ARCHIVE" ]; then
  echo "Файл не найден: $ARCHIVE"
  exit 1
fi

echo ">>> Бэкап .env..."
sudo -u youtrade cp /opt/youtrade-bot/.env /opt/youtrade-bot/.env.backup.$(date +%Y%m%d_%H%M%S)

echo ">>> Бэкап БД..."
sudo -u postgres pg_dump youtrade_bot > /tmp/youtrade_backup_$(date +%Y%m%d_%H%M%S).sql

echo ">>> Разворачиваем новый код..."
sudo -u youtrade tar -xzf "$ARCHIVE" -C /opt/ --overwrite
chown -R youtrade:youtrade /opt/youtrade-bot

echo ">>> Обновляем зависимости..."
sudo -u youtrade /opt/youtrade-bot/venv/bin/pip install -r /opt/youtrade-bot/requirements.txt

echo ">>> Применяем миграции..."
cd /opt/youtrade-bot
sudo -u youtrade ./venv/bin/python -m app.migrate

echo ">>> Перезапускаем сервис..."
systemctl restart youtrade-bot
sleep 2
systemctl status youtrade-bot --no-pager

echo
echo "=== Обновление завершено! ==="
echo "Логи: sudo journalctl -u youtrade-bot -f"
