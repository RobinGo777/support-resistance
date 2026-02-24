"""
Zone Detector — реалізація логіки S/R зон згідно специфікації.

Алгоритм:
1. Pivot Detection (фрактал 5 свічок)
2. Ініціалізація зони по wick (зовнішня межа) і close (внутрішня межа)
3. Structure Refinement — динамічне звуження зони по closes після pivot
4. Merging — злиття близьких зон
5. Breakout — інвалідація зони при закритті ціни за зовнішньою межею
6. Фільтрація сусідніх свічок — зона не перетинає тіла сусідніх свічок
"""

from dataclasses import dataclass, field
from typing import List, Optional, Dict
from datetime import datetime, timezone


@dataclass
class Zone:
    type: str          # 'support' | 'resistance'
    zone_low: float    # нижня межа зони
    zone_high: float   # верхня межа зони
    origin_time: int   # timestamp першого pivot (мс)
    strength: int = 1  # кількість злитих pivots
    touches: int = 0   # кількість торкань
    status: str = "active"  # 'active' | 'broken'
    pivot_idx: int = 0  # індекс pivot свічки в масиві

    @property
    def age_days(self) -> float:
        now_ms = datetime.now(timezone.utc).timestamp() * 1000
        return (now_ms - self.origin_time) / (1000 * 60 * 60 * 24)

    def contains_price(self, price: float, threshold_pct: float = 0.005) -> bool:
        """Чи знаходиться ціна в зоні або в межах threshold."""
        margin = (self.zone_high - self.zone_low) * threshold_pct
        return (self.zone_low - margin) <= price <= (self.zone_high + margin)

    def distance_pct(self, price: float) -> float:
        """
        Дистанція від поточної ціни до найближчої межі зони у відсотках.
        Resistance: від zone_low (якщо ціна знизу)
        Support: від zone_high (якщо ціна зверху)
        """
        if self.type == "resistance":
            return (self.zone_low - price) / price * 100
        else:
            return (self.zone_high - price) / price * 100


def _find_pivots(candles: List[Dict]) -> List[Dict]:
    """
    Знаходить pivot high і pivot low за фракталом 5 свічок.
    Pivot High: candles[i].high > candles[i-2..i-1] і > candles[i+1..i+2]
    Pivot Low:  candles[i].low  < candles[i-2..i-1] і < candles[i+1..i+2]

    Повертає список: {'idx': int, 'type': 'high'|'low', 'candle': dict}
    """
    pivots = []
    n = len(candles)
    for i in range(2, n - 2):
        c = candles[i]
        # Перевірка Pivot High
        is_ph = (
            c["high"] > candles[i-1]["high"] and
            c["high"] > candles[i-2]["high"] and
            c["high"] > candles[i+1]["high"] and
            c["high"] > candles[i+2]["high"]
        )
        # Перевірка Pivot Low
        is_pl = (
            c["low"] < candles[i-1]["low"] and
            c["low"] < candles[i-2]["low"] and
            c["low"] < candles[i+1]["low"] and
            c["low"] < candles[i+2]["low"]
        )
        if is_ph:
            pivots.append({"idx": i, "type": "high", "candle": c})
        if is_pl:
            pivots.append({"idx": i, "type": "low", "candle": c})

    return pivots


def _get_body_high(candle: Dict) -> float:
    return max(candle["open"], candle["close"])


def _get_body_low(candle: Dict) -> float:
    return min(candle["open"], candle["close"])


def _init_zone_from_pivot(pivot: Dict, candles: List[Dict]) -> Optional[Zone]:
    """
    Ініціалізує зону з pivot свічки.

    Resistance:
      zone_high = pivot.high (wick — зовнішня межа)
      zone_low  = max(open, close) pivot свічки (тіло — внутрішня межа)

    Support:
      zone_low  = pivot.low (wick — зовнішня межа)
      zone_high = min(open, close) pivot свічки (тіло — внутрішня межа)

    Додаткова перевірка: zone_low має бути < zone_high.
    Також перевіряємо що зовнішня межа не перетинає тіла сусідніх свічок.
    """
    idx = pivot["idx"]
    c = pivot["candle"]

    if pivot["type"] == "high":
        zone_high = c["high"]       # wick (зовнішня)
        zone_low = _get_body_high(c)  # тіло (внутрішня)

        if zone_low >= zone_high:
            return None

        # Перевірка: zone_high не має перетинати тіла сусідніх свічок
        # (тобто сусіди не мали закриватись вище zone_low — це підтверджує що pivot справжній)
        # Але ми не обрізаємо зону по сусідах — просто валідуємо
        for neighbor_idx in [idx - 1, idx - 2, idx + 1, idx + 2]:
            if 0 <= neighbor_idx < len(candles):
                nb = candles[neighbor_idx]
                nb_body_high = _get_body_high(nb)
                # Якщо тіло сусідньої свічки перевищує zone_low pivot — це нормально,
                # але zone_low не має бути нижче тіла сусіда (інакше зона некоректна)
                # Обрізаємо zone_low до мінімуму тіл сусідів якщо потрібно
                if nb_body_high > zone_low and nb_body_high < zone_high:
                    # Піднімаємо zone_low щоб не перетинати тіло сусіда
                    zone_low = max(zone_low, nb_body_high)

        if zone_low >= zone_high:
            return None

        return Zone(
            type="resistance",
            zone_low=zone_low,
            zone_high=zone_high,
            origin_time=c["open_time"],
            pivot_idx=idx,
        )

    else:  # pivot low → support
        zone_low = c["low"]          # wick (зовнішня)
        zone_high = _get_body_low(c)  # тіло (внутрішня)

        if zone_high <= zone_low:
            return None

        # Перевірка сусідів для support
        for neighbor_idx in [idx - 1, idx - 2, idx + 1, idx + 2]:
            if 0 <= neighbor_idx < len(candles):
                nb = candles[neighbor_idx]
                nb_body_low = _get_body_low(nb)
                if nb_body_low < zone_high and nb_body_low > zone_low:
                    zone_high = min(zone_high, nb_body_low)

        if zone_high <= zone_low:
            return None

        return Zone(
            type="support",
            zone_low=zone_low,
            zone_high=zone_high,
            origin_time=c["open_time"],
            pivot_idx=idx,
        )


def _refine_zone(zone: Zone, candles: List[Dict]) -> Zone:
    """
    Structure Refinement — звужує зону по closes від pivot до кінця масиву.

    Support:
      zone_high = min(close) від pivot до поточного моменту
      (але не нижче zone_low)

    Resistance:
      zone_low = max(close) від pivot до поточного моменту
      (але не вище zone_high)

    ВАЖЛИВО: не включаємо свічки що сформували новий HH/LL після pivot.
    """
    pivot_idx = zone.pivot_idx
    n = len(candles)

    if zone.type == "support":
        min_close = zone.zone_high
        for i in range(pivot_idx, n):
            c = candles[i]
            # Зупиняємось якщо нова свічка зробила новий lower low (інвалідація pivot)
            if c["low"] < zone.zone_low:
                break
            # Зупиняємось якщо свічка закрилась за зовнішньою межею (breakout)
            if c["close"] < zone.zone_low:
                break
            min_close = min(min_close, c["close"])

        refined_high = min_close
        # zone_high не може бути нижче zone_low
        if refined_high > zone.zone_low:
            zone.zone_high = refined_high

    else:  # resistance
        max_close = zone.zone_low
        for i in range(pivot_idx, n):
            c = candles[i]
            # Зупиняємось якщо нова свічка зробила новий higher high (інвалідація pivot)
            if c["high"] > zone.zone_high:
                break
            # Зупиняємось якщо свічка закрилась за зовнішньою межею (breakout)
            if c["close"] > zone.zone_high:
                break
            max_close = max(max_close, c["close"])

        refined_low = max_close
        # zone_low не може бути вище zone_high
        if refined_low < zone.zone_high:
            zone.zone_low = refined_low

    return zone


def _is_broken(zone: Zone, candles: List[Dict]) -> bool:
    """
    Перевіряє чи зона пробита: закриття свічки за зовнішньою межею.

    Resistance breakout: close > zone_high
    Support breakout:    close < zone_low
    """
    for c in candles[zone.pivot_idx:]:
        if zone.type == "resistance" and c["close"] > zone.zone_high:
            return True
        if zone.type == "support" and c["close"] < zone.zone_low:
            return True
    return False


def _merge_zones(zones: List[Zone], threshold_pct: float = 0.005) -> List[Zone]:
    """
    Злиття зон одного типу які перетинаються або ближче ніж threshold_pct (0.5%).

    При злитті:
    - strength += 1
    - зберігається origin_time старішої зони
    - межі розширюються до максимального діапазону
    """
    if not zones:
        return zones

    merged = True
    while merged:
        merged = False
        result = []
        used = [False] * len(zones)

        for i in range(len(zones)):
            if used[i]:
                continue
            z1 = zones[i]
            for j in range(i + 1, len(zones)):
                if used[j]:
                    continue
                z2 = zones[j]

                if z1.type != z2.type:
                    continue

                # Перевірка перетину або близькості
                threshold = (z1.zone_high - z1.zone_low + z2.zone_high - z2.zone_low) / 2 * threshold_pct
                # Зони перетинаються?
                overlap = z1.zone_low <= z2.zone_high and z2.zone_low <= z1.zone_high
                # Або близькі?
                gap = max(z1.zone_low, z2.zone_low) - min(z1.zone_high, z2.zone_high)
                close_enough = gap < threshold

                if overlap or close_enough:
                    # Зливаємо: беремо старішу як базову
                    base = z1 if z1.origin_time <= z2.origin_time else z2
                    other = z2 if z1.origin_time <= z2.origin_time else z1

                    base.zone_low = min(z1.zone_low, z2.zone_low)
                    base.zone_high = max(z1.zone_high, z2.zone_high)
                    base.strength += other.strength
                    # pivot_idx — беремо від того pivot який сформував зону першим
                    base.pivot_idx = min(z1.pivot_idx, z2.pivot_idx)
                    used[j] = True
                    merged = True

            result.append(z1)

        zones = result

    return zones


def detect_zones(candles: List[Dict]) -> List[Zone]:
    """
    Головна функція — детектує всі активні зони для масиву свічок.

    Кроки:
    1. Знайти всі pivots
    2. Ініціалізувати зони
    3. Перевірити breakout — видалити пробиті
    4. Refinement — звузити межі
    5. Merging — злити близькі
    """
    if not candles or len(candles) < 5:
        return []

    pivots = _find_pivots(candles)
    zones = []

    for pivot in pivots:
        zone = _init_zone_from_pivot(pivot, candles)
        if zone is None:
            continue
        # Перевіряємо чи зона не пробита
        if _is_broken(zone, candles):
            continue
        # Refinement
        zone = _refine_zone(zone, candles)
        zones.append(zone)

    # Merging
    zones = _merge_zones(zones)

    # Фінальна перевірка валідності
    valid_zones = []
    for z in zones:
        if z.zone_low < z.zone_high and z.status == "active":
            valid_zones.append(z)

    return valid_zones


def get_nearest_zones(
    zones: List[Zone],
    current_price: float,
    max_resistance: int = 3,
    max_support: int = 4,
) -> Dict[str, List[Zone]]:
    """
    Повертає найближчі зони до поточної ціни.

    Resistance: зони вище поточної ціни, сортовані за відстанню (найближча перша)
    Support:    зони нижче поточної ціни, сортовані за відстанню (найближча перша)
    """
    resistance = []
    support = []

    for z in zones:
        if z.type == "resistance" and z.zone_low > current_price:
            resistance.append(z)
        elif z.type == "support" and z.zone_high < current_price:
            support.append(z)
        elif z.type == "resistance" and z.zone_high > current_price > z.zone_low:
            # Ціна всередині resistance зони
            resistance.append(z)
        elif z.type == "support" and z.zone_low < current_price < z.zone_high:
            # Ціна всередині support зони
            support.append(z)

    # Сортування: resistance — від найближчої до найдальшої (zone_low ascending)
    resistance.sort(key=lambda z: z.zone_low)
    # Support — від найближчої до найдальшої (zone_high descending)
    support.sort(key=lambda z: z.zone_high, reverse=True)

    return {
        "resistance": resistance[:max_resistance],
        "support": support[:max_support],
    }


def detect_zones_multi_tf(
    candles_by_tf: Dict[str, List[Dict]]
) -> Dict[str, List[Zone]]:
    """
    Детектує зони для кожного таймфрейму окремо.
    """
    result = {}
    for tf, candles in candles_by_tf.items():
        if candles:
            result[tf] = detect_zones(candles)
        else:
            result[tf] = []
    return result
