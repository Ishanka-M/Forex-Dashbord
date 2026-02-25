"""
modules/signal_engine.py
Trade Signal Generator combining Elliott Wave + SMC + Multi-timeframe
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import pytz
import uuid

from modules.elliott_wave import identify_elliott_waves, ElliottWaveResult
from modules.smc_analysis import analyze_smc, SMCResult
from modules.market_data import get_ohlcv

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

SWING_TIMEFRAMES = ["H4", "D1"]
SHORT_TIMEFRAMES = ["M5", "M15", "H1"]


@dataclass
class TradeSignal:
    trade_id: str
    symbol: str
    direction: str        # "BUY" | "SELL"
    entry_price: float
    sl_price: float
    tp_price: float
    lot_size: float
    strategy: str         # "swing" | "short"
    timeframe: str
    probability_score: int  # 0-100
    confluences: list[str]
    ew_pattern: str
    smc_bias: str
    risk_reward: float
    generated_at: str


def calculate_lot_size(account_balance: float, risk_pct: float, entry: float, sl: float) -> float:
    """Calculate lot size based on risk percentage."""
    risk_amount = account_balance * (risk_pct / 100)
    pip_diff = abs(entry - sl) * 10000
    if pip_diff == 0:
        return 0.01
    pip_value = 10  # $10 per pip for standard lot on most pairs
    lot = risk_amount / (pip_diff * pip_value)
    return max(0.01, round(min(lot, 10.0), 2))


def generate_signal(symbol: str, strategy_type: str = "swing", account_balance: float = 10000) -> Optional[TradeSignal]:
    """
    Generate a trade signal for a symbol combining EW + SMC.
    strategy_type: "swing" or "short"
    """
    timeframes = SWING_TIMEFRAMES if strategy_type == "swing" else SHORT_TIMEFRAMES

    ew_results = {}
    smc_results = {}
    
    for tf in timeframes:
        df = get_ohlcv(symbol, tf)
        if df is not None and not df.empty and len(df) > 30:
            ew_results[tf] = identify_elliott_waves(df)
            smc_results[tf] = analyze_smc(df)

    if not ew_results:
        return None

    # Use primary timeframe (last in list = highest)
    primary_tf = timeframes[-1]
    secondary_tf = timeframes[0] if len(timeframes) > 1 else primary_tf

    ew = ew_results.get(primary_tf)
    smc = smc_results.get(primary_tf)
    ew_lower = ew_results.get(secondary_tf)
    smc_lower = smc_results.get(secondary_tf)

    if not ew or not smc:
        return None

    df = get_ohlcv(symbol, primary_tf)
    if df is None or df.empty:
        return None

    current_price = df["close"].iloc[-1]
    confluences = []
    score = 0

    # --- Elliott Wave Score ---
    if ew.pattern_type == "5-wave-impulse":
        score += 25
        confluences.append(f"EW: 5-Wave Impulse ({ew.trend.upper()})")
    elif ew.pattern_type == "3-wave-ABC":
        score += 15
        confluences.append(f"EW: ABC Corrective")
    
    if ew.confidence > 0.7:
        score += 10
        confluences.append(f"EW Confidence: {ew.confidence*100:.0f}%")
    elif ew.confidence > 0.5:
        score += 5

    # --- SMC Score ---
    if smc.last_choch:
        score += 20
        confluences.append(f"SMC: CHoCH ({smc.last_choch.direction.upper()})")
    if smc.last_bos:
        score += 15
        confluences.append(f"SMC: BOS ({smc.last_bos.direction.upper()})")
    if smc.current_ob and not smc.current_ob.is_mitigated:
        score += 15
        ob_type = "Bullish" if smc.current_ob.ob_type == "bullish" else "Bearish"
        confluences.append(f"SMC: {ob_type} OB @ {smc.current_ob.mid:.5f}")
    if smc.nearest_fvg and not smc.nearest_fvg.is_filled:
        score += 10
        confluences.append(f"SMC: FVG @ {smc.nearest_fvg.bottom:.5f}-{smc.nearest_fvg.top:.5f}")

    # --- Multi-timeframe confluence ---
    if ew_lower and smc_lower:
        if ew_lower.trend == ew.trend:
            score += 10
            confluences.append(f"MTF: {secondary_tf} aligns with {primary_tf}")

    # --- Direction determination ---
    bullish_votes = 0
    bearish_votes = 0

    if ew.trend == "bullish": bullish_votes += 2
    if ew.trend == "bearish": bearish_votes += 2
    if smc.trend == "bullish": bullish_votes += 2
    if smc.trend == "bearish": bearish_votes += 2
    if ew_lower and ew_lower.trend == "bullish": bullish_votes += 1
    if ew_lower and ew_lower.trend == "bearish": bearish_votes += 1

    if bullish_votes == bearish_votes:
        return None
    
    direction = "BUY" if bullish_votes > bearish_votes else "SELL"

    # --- Entry, SL, TP ---
    if strategy_type == "swing":
        # Fibonacci-based SL/TP
        fib = ew.fib_levels
        if direction == "BUY":
            entry = current_price
            sl = fib.get("0.382", current_price * 0.998)
            tp = ew.projected_target or (current_price + abs(current_price - sl) * 2.5)
        else:
            entry = current_price
            sl = fib.get("0.382", current_price * 1.002)
            tp = ew.projected_target or (current_price - abs(current_price - sl) * 2.5)
    else:
        # SMC-based SL/TP using FVG and swing highs/lows
        atr = _get_atr(df)
        if direction == "BUY":
            entry = current_price
            sl = (smc.nearest_fvg.bottom if smc.nearest_fvg else current_price - atr * 1.5)
            tp = (smc.nearest_fvg.top if smc.nearest_fvg else current_price + atr * 2.5)
            if tp <= entry:
                tp = entry + atr * 2.5
        else:
            entry = current_price
            sl = (smc.nearest_fvg.top if smc.nearest_fvg else current_price + atr * 1.5)
            tp = (smc.nearest_fvg.bottom if smc.nearest_fvg else current_price - atr * 2.5)
            if tp >= entry:
                tp = entry - atr * 2.5

    risk = abs(entry - sl)
    reward = abs(tp - entry)
    rr = round(reward / risk, 2) if risk > 0 else 1.0

    # Only signal if RR >= 1.5
    if rr < 1.5:
        score = max(0, score - 20)

    lot = calculate_lot_size(account_balance, 1.0, entry, sl)

    return TradeSignal(
        trade_id=str(uuid.uuid4())[:8].upper(),
        symbol=symbol,
        direction=direction,
        entry_price=round(entry, 5),
        sl_price=round(sl, 5),
        tp_price=round(tp, 5),
        lot_size=lot,
        strategy=strategy_type,
        timeframe=primary_tf,
        probability_score=min(score, 100),
        confluences=confluences,
        ew_pattern=ew.pattern_type,
        smc_bias=smc.bias,
        risk_reward=rr,
        generated_at=datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
    )


def generate_all_signals(symbols: list[str], strategy_type: str = "swing") -> list[TradeSignal]:
    """Generate signals for all symbols."""
    signals = []
    for symbol in symbols:
        try:
            sig = generate_signal(symbol, strategy_type)
            if sig and sig.probability_score >= 40:
                signals.append(sig)
        except Exception as e:
            pass
    signals.sort(key=lambda x: x.probability_score, reverse=True)
    return signals


def _get_atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period:
        return abs(df["close"].iloc[-1]) * 0.001
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(abs(high[1:] - close[:-1]),
                               abs(low[1:] - close[:-1])))
    return float(np.mean(tr[-period:]))
