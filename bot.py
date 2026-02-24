"""
Telegram bot для відображення S/R зон з Binance.

Команди:
  /start — привітання
  /help  — допомога

Запит монети:
  VET 4h   — аналіз VET на 4h
  BTC 1h   — аналіз BTC на 1h
  ETH      — аналіз ETH (default: 4h)
"""

import os
import logging
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from binance_client import (
    normalize_symbol,
    fetch_all_timeframes,
    get_current_price,
    validate_symbol,
)
from zone_detector import detect_zones_multi_tf, get_nearest_zones
from chart import generate_chart

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

VALID_TIMEFRAMES = {"1h", "4h", "12h"}
DEFAULT_TIMEFRAME = "4h"

HELP_TEXT = """
📊 *S/R Zone Bot*

Надішли запит у форматі:
  `VET 4h` — аналіз VET/USDT на 4h
  `BTC 1h` — аналіз BTC/USDT на 1h
  `ETH`    — аналіз ETH/USDT (default: 4h)

Доступні таймфрейми: `1h`, `4h`, `12h`

Бот показує зони Support та Resistance з усіх таймфреймів (1h, 4h, 12h) на обраному графіку.
"""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привіт! Я аналізую S/R зони з Binance.\n\n" + HELP_TEXT,
        parse_mode="Markdown",
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def analyze_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обробляє запит типу 'VET 4h' або 'vet 1h'."""
    text = update.message.text.strip()
    parts = text.upper().split()

    if not parts:
        return

    # Парсимо символ і таймфрейм
    raw_symbol = parts[0]
    timeframe = DEFAULT_TIMEFRAME

    if len(parts) >= 2:
        tf_candidate = parts[1].lower()
        if tf_candidate in VALID_TIMEFRAMES:
            timeframe = tf_candidate
        else:
            await update.message.reply_text(
                f"❌ Невідомий таймфрейм: `{parts[1]}`\nДоступні: 1h, 4h, 12h",
                parse_mode="Markdown",
            )
            return

    symbol = normalize_symbol(raw_symbol)

    # Повідомлення про початок аналізу
    status_msg = await update.message.reply_text(
        f"🔍 Аналізую *{symbol}* на *{timeframe}*...",
        parse_mode="Markdown",
    )

    # Валідація символу
    if not validate_symbol(symbol):
        await status_msg.edit_text(
            f"❌ Символ `{symbol}` не знайдений на Binance Futures.",
            parse_mode="Markdown",
        )
        return

    # Отримуємо поточну ціну
    current_price = get_current_price(symbol)
    if current_price is None:
        await status_msg.edit_text("❌ Не вдалося отримати поточну ціну.")
        return

    # Отримуємо свічки з усіх таймфреймів
    await status_msg.edit_text(f"📥 Завантажую дані з Binance...")
    candles_by_tf = fetch_all_timeframes(symbol)

    main_candles = candles_by_tf.get(timeframe)
    if not main_candles:
        await status_msg.edit_text(
            f"❌ Не вдалося отримати свічки для {symbol} {timeframe}."
        )
        return

    # Детектуємо зони на всіх таймфреймах
    await status_msg.edit_text("⚙️ Обчислюю зони S/R...")
    zones_by_tf = detect_zones_multi_tf(candles_by_tf)

    # Збираємо всі зони разом для пошуку найближчих
    all_zones = []
    for tf_zones in zones_by_tf.values():
        all_zones.extend(tf_zones)

    nearest = get_nearest_zones(all_zones, current_price)

    resistance_zones = nearest["resistance"]
    support_zones = nearest["support"]

    # Генеруємо графік
    await status_msg.edit_text("🖼 Генерую графік...")
    try:
        chart_buf = generate_chart(
            symbol=symbol,
            timeframe=timeframe,
            candles=main_candles,
            zones_by_tf=zones_by_tf,
            current_price=current_price,
            nearest_zones=nearest,
        )
    except Exception as e:
        logger.error(f"Chart generation error: {e}")
        await status_msg.edit_text("❌ Помилка генерації графіка.")
        return

    # Формуємо текстове повідомлення
    msg_lines = [
        f"🔍 *Key Levels for #{symbol}* ({timeframe})",
        f"Current Price: `{current_price}`",
        "",
    ]

    if resistance_zones:
        msg_lines.append("🔴 *RESISTANCE Levels:*")
        for z in resistance_zones:
            dist = z.distance_pct(current_price)
            # Визначаємо TF зони
            tf_label = _get_zone_tf(z, zones_by_tf)
            msg_lines.append(
                f"• Zone: `{z.zone_low:.5g} - {z.zone_high:.5g}`"
                f"  Distance: `+{dist:.2f}%`"
                f"  Strength: `{z.strength}`"
                f"  Age: `{int(z.age_days)}d`"
                f"  TF: `{tf_label}`"
            )
    else:
        msg_lines.append("🔴 *RESISTANCE:* зони не знайдені")

    msg_lines.append("")

    if support_zones:
        msg_lines.append("🟢 *SUPPORT Levels:*")
        for z in support_zones:
            dist = z.distance_pct(current_price)
            tf_label = _get_zone_tf(z, zones_by_tf)
            msg_lines.append(
                f"• Zone: `{z.zone_low:.5g} - {z.zone_high:.5g}`"
                f"  Distance: `{dist:.2f}%`"
                f"  Strength: `{z.strength}`"
                f"  Age: `{int(z.age_days)}d`"
                f"  TF: `{tf_label}`"
            )
    else:
        msg_lines.append("🟢 *SUPPORT:* зони не знайдені")

    message_text = "\n".join(msg_lines)

    # Видаляємо статусне повідомлення
    await status_msg.delete()

    # Відправляємо фото з підписом
    await update.message.reply_photo(
        photo=chart_buf,
        caption=message_text,
        parse_mode="Markdown",
    )


def _get_zone_tf(zone, zones_by_tf: dict) -> str:
    """Визначає таймфрейм зони."""
    for tf, zones in zones_by_tf.items():
        for z in zones:
            if id(z) == id(zone):
                return tf
    return "?"


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable is not set!")

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, analyze_handler)
    )

    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
