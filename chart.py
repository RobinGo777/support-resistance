"""
Chart generator — малює свічковий графік з зонами S/R у темному стилі TradingView.
"""

import io
from typing import List, Dict, Optional
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import matplotlib.ticker as ticker
import numpy as np

from zone_detector import Zone


# Кольори у стилі TradingView dark
BG_COLOR = "#131722"
GRID_COLOR = "#1e2230"
TEXT_COLOR = "#b2b5be"
UP_COLOR = "#26a69a"      # зелена свічка
DOWN_COLOR = "#ef5350"    # червона свічка
SUPPORT_COLOR = "#26a69a"      # зелена зона
RESISTANCE_COLOR = "#ef5350"   # червона зона
SUPPORT_ALPHA = 0.25
RESISTANCE_ALPHA = 0.25
PRICE_LINE_COLOR = "#b2b5be"


def _draw_candles(ax, candles: List[Dict], x_offset: int = 0):
    """Малює свічки на осі."""
    for i, c in enumerate(candles):
        x = i + x_offset
        is_up = c["close"] >= c["open"]
        color = UP_COLOR if is_up else DOWN_COLOR
        body_low = min(c["open"], c["close"])
        body_high = max(c["open"], c["close"])
        body_height = max(body_high - body_low, 1e-10)

        # Тіло свічки
        ax.add_patch(plt.Rectangle(
            (x - 0.35, body_low),
            0.7,
            body_height,
            color=color,
            zorder=3,
        ))
        # Тінь (wick)
        ax.plot(
            [x, x], [c["low"], body_low],
            color=color, linewidth=0.8, zorder=2
        )
        ax.plot(
            [x, x], [body_high, c["high"]],
            color=color, linewidth=0.8, zorder=2
        )


def _draw_zone(ax, zone: Zone, x_start: float, x_end: float,
               label: str, tf_label: str):
    """Малює прямокутну зону з підписом."""
    is_res = zone.type == "resistance"
    color = RESISTANCE_COLOR if is_res else SUPPORT_COLOR
    alpha = RESISTANCE_ALPHA if is_res else SUPPORT_ALPHA
    edge_color = RESISTANCE_COLOR if is_res else SUPPORT_COLOR

    height = zone.zone_high - zone.zone_low

    # Прямокутник зони
    rect = plt.Rectangle(
        (x_start, zone.zone_low),
        x_end - x_start,
        height,
        facecolor=color,
        alpha=alpha,
        edgecolor=edge_color,
        linewidth=0.8,
        zorder=1,
    )
    ax.add_patch(rect)

    # Лінія зовнішньої межі (пунктир)
    outer_y = zone.zone_high if is_res else zone.zone_low
    ax.axhline(
        y=outer_y,
        xmin=0, xmax=1,
        color=edge_color,
        linewidth=0.6,
        linestyle="--",
        alpha=0.5,
        zorder=1,
    )

    # Підпис всередині зони
    mid_x = (x_start + x_end) / 2
    mid_y = (zone.zone_low + zone.zone_high) / 2
    zone_type = "RESISTANCE" if is_res else "SUPPORT"
    text = f"{zone_type}: {zone.zone_low:.5g} - {zone.zone_high:.5g} (Age: {int(zone.age_days)}d)"
    if tf_label:
        text = f"[{tf_label}] {text}"

    ax.text(
        mid_x, mid_y, text,
        color="white",
        fontsize=6.5,
        ha="center",
        va="center",
        fontweight="bold",
        zorder=5,
        bbox=dict(
            boxstyle="round,pad=0.2",
            facecolor=color,
            alpha=0.7,
            edgecolor="none",
        )
    )


def generate_chart(
    symbol: str,
    timeframe: str,
    candles: List[Dict],
    zones_by_tf: Dict[str, List[Zone]],
    current_price: float,
    nearest_zones: Dict[str, List[Zone]],
) -> io.BytesIO:
    """
    Генерує графік і повертає BytesIO об'єкт з PNG.

    candles — свічки основного таймфрейму (для відображення)
    zones_by_tf — зони з усіх таймфреймів
    nearest_zones — {'resistance': [...], 'support': [...]} найближчі зони
    """
    # Беремо останні 120 свічок для відображення
    display_candles = candles[-120:] if len(candles) > 120 else candles
    n = len(display_candles)

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor(BG_COLOR)
    ax.set_facecolor(BG_COLOR)

    # Малюємо свічки
    _draw_candles(ax, display_candles)

    # Визначаємо які зони показувати — тільки найближчі
    zones_to_show = (
        nearest_zones.get("resistance", []) +
        nearest_zones.get("support", [])
    )

    # Зони малюємо на всю ширину графіка
    x_start = 0
    x_end = n - 1

    # Визначаємо TF label для кожної зони
    # (будуємо зворотній словник zone -> tf)
    zone_tf_map = {}
    for tf, zones in zones_by_tf.items():
        for z in zones:
            zone_tf_map[id(z)] = tf

    for zone in zones_to_show:
        tf_label = zone_tf_map.get(id(zone), "")
        _draw_zone(ax, zone, x_start, x_end, "", tf_label)

    # Поточна ціна — горизонтальна лінія
    ax.axhline(
        y=current_price,
        color=PRICE_LINE_COLOR,
        linewidth=0.8,
        linestyle="-",
        alpha=0.7,
        zorder=4,
    )

    # Підпис поточної ціни праворуч
    ax.text(
        n - 0.5, current_price,
        f" {current_price:.5g}",
        color="white",
        fontsize=8,
        va="center",
        ha="left",
        fontweight="bold",
        zorder=6,
        bbox=dict(
            boxstyle="round,pad=0.2",
            facecolor="#ef5350" if current_price < display_candles[-1]["open"] else "#26a69a",
            alpha=0.9,
            edgecolor="none",
        )
    )

    # Налаштування осей
    prices = []
    for c in display_candles:
        prices.extend([c["high"], c["low"]])
    for z in zones_to_show:
        prices.extend([z.zone_low, z.zone_high])

    if prices:
        price_min = min(prices)
        price_max = max(prices)
        margin = (price_max - price_min) * 0.08
        ax.set_ylim(price_min - margin, price_max + margin)

    ax.set_xlim(-1, n + 2)

    # Сітка
    ax.grid(True, color=GRID_COLOR, linewidth=0.5, alpha=0.8)
    ax.tick_params(colors=TEXT_COLOR, labelsize=7)
    for spine in ax.spines.values():
        spine.set_color(GRID_COLOR)

    # X-axis: показуємо дати
    step = max(1, n // 8)
    x_ticks = list(range(0, n, step))
    x_labels = []
    for xi in x_ticks:
        ts = display_candles[xi]["open_time"] / 1000
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        if timeframe in ("1h", "4h"):
            x_labels.append(dt.strftime("%b %d"))
        else:
            x_labels.append(dt.strftime("%b %d"))
    ax.set_xticks(x_ticks)
    ax.set_xticklabels(x_labels, color=TEXT_COLOR, fontsize=7)

    # Заголовок
    ax.set_title(
        f"{symbol} · {timeframe} · Binance",
        color=TEXT_COLOR,
        fontsize=10,
        pad=8,
        loc="left",
    )

    plt.tight_layout(pad=0.5)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, facecolor=BG_COLOR, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return buf
