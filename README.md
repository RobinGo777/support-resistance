# S/R Zone Bot

Telegram бот для аналізу зон підтримки та опору на Binance Futures.

## Локальний запуск

1. Встанови залежності:
```bash
pip install -r requirements.txt
```

2. Створи `.env` файл:
```bash
cp .env.example .env
# Встав свій TELEGRAM_BOT_TOKEN
```

3. Запусти:
```bash
export TELEGRAM_BOT_TOKEN=your_token
python bot.py
```

## Деплой на Northflank

1. Запуш код на GitHub або GitLab репозиторій.

2. У Northflank створи новий сервіс:
   - **Combined Build and Deploy**
   - Вибери свій репозиторій
   - Build type: **Dockerfile**
   - Dockerfile path: `Dockerfile`

3. Додай змінну середовища:
   - `TELEGRAM_BOT_TOKEN` = твій токен від @BotFather

4. Deploy!

## Використання бота

Надішли в Telegram:
- `VET 4h` — аналіз VET/USDT на 4h
- `BTC 1h` — аналіз BTC/USDT на 1h  
- `ETH`    — аналіз ETH/USDT (default: 4h)

## Структура проекту

```
sr_bot/
├── bot.py              # Telegram bot (точка входу)
├── binance_client.py   # Binance Futures API
├── zone_detector.py    # Логіка S/R зон (pivot, merge, refine)
├── chart.py            # Генерація графіка matplotlib
├── requirements.txt
├── Dockerfile
└── .env.example
```

## Логіка зон

- **Pivot Detection**: фрактал 5 свічок
- **Resistance**: zone_high = wick High, zone_low = max(Open, Close)
- **Support**: zone_low = wick Low, zone_high = min(Open, Close)
- **Refinement**: zone_high для support = min(close від pivot до зараз)
- **Merging**: злиття зон ближче 0.5%
- **Breakout**: інвалідація при close за зовнішньою межею
- **Multi-TF**: зони з 1h, 4h, 12h відображаються разом
