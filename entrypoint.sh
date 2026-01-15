#!/bin/bash
set -e

echo "=== VMESTE Entrypoint ==="

# Инициализация БД (создаёт таблицы если их нет)
echo "Checking database tables..."
python3 -c "
from app.db.connection import fetch_all, get_connection

tables = fetch_all(\"SELECT tablename FROM pg_tables WHERE schemaname = 'public'\")
if len(tables) == 0:
    print('No tables found. Running init.sql...')
    with get_connection() as conn:
        with conn.cursor() as cur:
            with open('db/init.sql', 'r') as f:
                cur.execute(f.read())
    print('Database initialized!')
else:
    print(f'Database has {len(tables)} tables. Skipping init.')
"

# Запускаем бота в фоне
echo "Starting Telegram bot..."
python3 -m bot.telegram_bot &

# Запускаем API
echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
