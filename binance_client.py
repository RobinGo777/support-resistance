import requests
from typing import List, Dict, Optional

BINANCE_BASE_URL = "https://fapi.binance.com"  # Futures (perpetual contracts)

TIMEFRAME_MAP = {
    "1h": "1h",
    "4h": "4h",
    "12h": "12h",
}

# Кількість свічок для кожного таймфрейму
CANDLE_LIMITS = {
    "1h": 500,
    "4h": 300,
    "12h": 200,
}


def normalize_symbol(raw: str) -> str:
    """
    Нормалізує символ: 'vet', 'VET', 'VETUSDT' -> 'VETUSDT'
    """
    s = raw.strip().upper()
    if not s.endswith("USDT"):
        s += "USDT"
    return s


def fetch_candles(symbol: str, interval: str, limit: int) -> Optional[List[Dict]]:
    """
    Отримує свічки з Binance Futures API.
    Повертає список словників з полями:
      open_time, open, high, low, close, volume
    або None якщо помилка.
    """
    url = f"{BINANCE_BASE_URL}/fapi/v1/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        raw = resp.json()
        candles = []
        for c in raw:
            candles.append({
                "open_time": int(c[0]),
                "open": float(c[1]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
                "volume": float(c[5]),
            })
        return candles
    except Exception as e:
        print(f"[binance_client] Error fetching {symbol} {interval}: {e}")
        return None


def fetch_all_timeframes(symbol: str) -> Dict[str, Optional[List[Dict]]]:
    """
    Повертає свічки для всіх трьох таймфреймів.
    """
    result = {}
    for tf, binance_tf in TIMEFRAME_MAP.items():
        limit = CANDLE_LIMITS[tf]
        result[tf] = fetch_candles(symbol, binance_tf, limit)
    return result


def get_current_price(symbol: str) -> Optional[float]:
    """
    Отримує поточну ціну з Binance Futures.
    """
    url = f"{BINANCE_BASE_URL}/fapi/v1/ticker/price"
    try:
        resp = requests.get(url, params={"symbol": symbol}, timeout=5)
        resp.raise_for_status()
        return float(resp.json()["price"])
    except Exception as e:
        print(f"[binance_client] Error fetching price {symbol}: {e}")
        return None


def validate_symbol(symbol: str) -> bool:
    """
    Перевіряє чи існує символ на Binance Futures.
    """
    url = f"{BINANCE_BASE_URL}/fapi/v1/exchangeInfo"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        symbols = [s["symbol"] for s in resp.json()["symbols"]]
        return symbol in symbols
    except Exception as e:
        print(f"[binance_client] Error validating {symbol}: {e}")
        return False
