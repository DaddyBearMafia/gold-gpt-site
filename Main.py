import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import time
import requests
import json
import os
from datetime import datetime, timezone, timedelta

BOT_TOKEN = "7985057072:AAGniOrqXUvFpRSjL5x-qUIQplZiXdkvA6w"
CHAT_ID = "7419768438"
SYMBOLS = ["XAUUSD", "DXY", "SILVER"]
SAVE_PATH = os.path.join(os.getcwd(), "gold_gpt_data.txt")


def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message[:4096], "parse_mode": "Markdown"}
    requests.post(url, data=payload)


def save_to_txt(content):
    with open(SAVE_PATH, "w", encoding="utf-8") as f:
        f.write(content)


def initialize_mt5():
    if not mt5.initialize():
        if not mt5.initialize(path="C:\\Program Files\\MetaTrader 5\\terminal64.exe"):
            print("MT5 initialization failed.")
            print("Error:", mt5.last_error())
            raise RuntimeError("MT5 initialization failed")
    detect_optional_symbols()


def detect_optional_symbols():
    available = [s.name for s in mt5.symbols_get()]
    if any("10Y" in s or "TNOTE" in s or "ZNU" in s for s in available):
        for s in available:
            if ("10Y" in s or "TNOTE" in s or "ZNU" in s) and s not in SYMBOLS:
                SYMBOLS.append(s)
                print(f"Detected and added optional bond symbol: {s}")
                break
    else:
        print("US10Y not found. Skipping bond alignment.")


def shutdown_mt5():
    mt5.shutdown()


def compute_rsi(series, period=14):
    delta = series.diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_gain = pd.Series(gain).rolling(window=period).mean()
    avg_loss = pd.Series(loss).rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_macd(series):
    exp1 = series.ewm(span=12, adjust=False).mean()
    exp2 = series.ewm(span=26, adjust=False).mean()
    macd = exp1 - exp2
    signal = macd.ewm(span=9, adjust=False).mean()
    return macd, signal


def compute_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(period).mean()
    return atr


def compute_vwap(df):
    return (df['close'] * df['tick_volume']).cumsum() / df['tick_volume'].replace(0, np.nan).cumsum()


def compute_bollinger_bandwidth(df, period=20):
    sma = df['close'].rolling(period).mean()
    std = df['close'].rolling(period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    return (upper - lower) / sma


def compute_pivots(df):
    if len(df) < 2:
        return {'PP': None, 'R1': None, 'S1': None, 'R2': None, 'S2': None}
    last_day = df.iloc[-2]
    high = last_day['high']
    low = last_day['low']
    close = last_day['close']
    pp = (high + low + close) / 3
    r1 = 2 * pp - low
    s1 = 2 * pp - high
    r2 = pp + (high - low)
    s2 = pp - (high - low)
    return {'PP': pp, 'R1': r1, 'S1': s1, 'R2': r2, 'S2': s2}


def detect_fractals(df):
    if 'high' not in df.columns or 'low' not in df.columns:
        return df
    highs = df['high']
    lows = df['low']
    df['fractal_high'] = ((highs.shift(2) < highs.shift(1)) & (highs.shift(1) < highs) & (highs > highs.shift(-1)) & (highs.shift(-1) > highs.shift(-2)))
    df['fractal_low'] = ((lows.shift(2) > lows.shift(1)) & (lows.shift(1) > lows) & (lows < lows.shift(-1)) & (lows.shift(-1) < lows.shift(-2)))
    return df


def tag_session(df):
    df['hour'] = df['time'].dt.hour
    def map_session(h):
        if 0 <= h < 7:
            return 'Asia'
        elif 7 <= h < 8:
            return 'London Open Ramp'
        elif 8 <= h < 13:
            return 'London'
        elif 13 <= h < 14:
            return 'NY Overlap Spike'
        elif 14 <= h < 17:
            return 'NY'
        else:
            return 'After-Hours'
    df['session'] = df['hour'].apply(map_session)
    return df


def compute_slope(series):
    return series.diff()


def detect_spikes(df):
    df['atr_spike'] = df['atr'] > df['atr'].rolling(10).mean() * 1.5
    df['volume_spike'] = df['tick_volume'] > df['tick_volume'].rolling(10).mean() * 1.5
    return df


def get_full_raw_data(symbol):
    info = mt5.symbol_info(symbol)
    tick = mt5.symbol_info_tick(symbol)
    df_m1 = pd.DataFrame(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M1, 0, 500))
    df_m15 = pd.DataFrame(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 500))
    df_m30 = pd.DataFrame(mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M30, 0, 500))

    if df_m1.empty or df_m15.empty or df_m30.empty:
        return {
            "symbol": symbol,
            "symbol_info": info._asdict() if info else {},
            "tick_info": tick._asdict() if tick else {},
            "ohlcv_m1": [],
            "ohlcv_m15": [],
            "ohlcv_m30": [],
            "pivots": {}
        }

    for df in [df_m1, df_m15, df_m30]:
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df['ema9'] = df['close'].ewm(span=9).mean()
        df['ema21'] = df['close'].ewm(span=21).mean()
        df['ema50'] = df['close'].ewm(span=50).mean()
        df['ema100'] = df['close'].ewm(span=100).mean()
        df['ema200'] = df['close'].ewm(span=200).mean()
        df['ema_slope'] = compute_slope(df['ema21'])
        df['rsi'] = compute_rsi(df['close'], 5)
        df['macd'], df['macd_signal'] = compute_macd(df['close'])
        df['macd_hist'] = df['macd'] - df['macd_signal']
        df['atr'] = compute_atr(df)
        df['vwap'] = compute_vwap(df)
        df['bb_width'] = compute_bollinger_bandwidth(df)
        df['body'] = abs(df['close'] - df['open'])
        df['range'] = df['high'] - df['low']
        df['volume_avg'] = df['tick_volume'].rolling(10).mean()
        df = detect_fractals(df)
        df = tag_session(df)
        df = detect_spikes(df)

    pivots = compute_pivots(df_m30)
    return {
        "symbol": symbol,
        "symbol_info": info._asdict(),
        "tick_info": tick._asdict(),
        "ohlcv_m1": df_m1.tail(10).to_dict(orient='records'),
        "ohlcv_m15": df_m15.tail(10).to_dict(orient='records'),
        "ohlcv_m30": df_m30.tail(10).to_dict(orient='records'),
        "pivots": pivots
    }


def build_gpt_prompt(full_data):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    now_uk = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M UK")
    lines = []
    for data in full_data:
        if not data['ohlcv_m1']:
            lines.append(f"[WARNING] No data for {data['symbol']}")
            continue
        ts = data['ohlcv_m1'][-1]['time']
        price = data['tick_info']['bid']
        spread = data['symbol_info']['spread']
        lines.append(f"[GPT SCALPING SNAPSHOT – {data['symbol']} – {ts}] ({now_utc} / {now_uk})")
        lines.append(f"Price: {price} | Spread: {spread}")
        lines.append("[M1 Data]")
        lines.append(str(data['ohlcv_m1'][-1]))
        lines.append("[M15 Data]")
        lines.append(str(data['ohlcv_m15'][-1]))
        lines.append("[M30 Data]")
        lines.append(str(data['ohlcv_m30'][-1]))
        lines.append("[Pivots]")
        lines.append(str(data['pivots']))
        lines.append("[Tick Info]")
        lines.append(str(data['tick_info']))
        lines.append("[Meta Summary]")
        lines.append(str({
            'bid': price,
            'ask': data['symbol_info']['ask'],
            'volume': data['symbol_info']['volume'],
            'session_open': data['symbol_info']['session_open'],
            'session_close': data['symbol_info']['session_close'],
            'swap_long': data['symbol_info']['swap_long'],
            'swap_short': data['symbol_info']['swap_short']
        }))
        lines.append("\n")

    lines.append("ACTION PROMPT TO GPT:")
    lines.append("Run Line Theory 15 and 30 full MA stack checks. Validate pink/yellow/cyan relationships and white MA slope for macro trend alignment.")
    lines.append("Evaluate Method 4.4 breakout quality: body ratio, volume spike, ATR confirmation, breakout candle location, retest within 1–4 bars, SL/TP RR range.")
    lines.append("Check RSI(5) M1/M15/M30, MACD crossovers, and BB width status. Confirm squeeze, expansion, or climax.")
    lines.append("Apply Validity Checker: session tag, VWAP alignment, ±45min news filter, zone retest fatigue, confidence %, time-decayed risk.")
    lines.append("If DXY/Silver/US10Y data is missing or diverges → reduce confidence.")
    lines.append("Return response in this exact format:")
    lines.append("- SIGNAL: BUY / SELL / AVOID")
    lines.append("- ENTRY: price or range")
    lines.append("- SL / TP1 / TP2")
    lines.append("- CONFIDENCE: %")
    lines.append("- RISK PROFILE: now/in_5/in_15")
    lines.append("- TREND CONTEXT")
    lines.append("- MOMENTUM CONTEXT")
    lines.append("- STRUCTURE CONTEXT")
    lines.append("- INTERMARKET CONTEXT")
    return "\n".join(lines)


if __name__ == "__main__":
    try:
        while True:
            initialize_mt5()
            all_data = [get_full_raw_data(sym) for sym in SYMBOLS]
            gpt_prompt = build_gpt_prompt(all_data)
            save_to_txt(gpt_prompt)
            shutdown_mt5()
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopped by user.")
