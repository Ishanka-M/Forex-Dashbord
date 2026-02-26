"""
modules/signal_engine.py
Trade Signal Generator — EW + SMC + Multi-timeframe
Fixed: lower score threshold, tie-breaking, trend fallback signals
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import pytz
import uuid

from modules.elliott_wave import identify_elliott_waves
from modules.smc_analysis import analyze_smc
from modules.market_data import get_ohlcv

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

SWING_TIMEFRAMES  = ["H4", "D1"]
SHORT_TIMEFRAMES  = ["M15", "H1"]


@dataclass
class TradeSignal:
    trade_id:          str
    symbol:            str
    direction:         str
    entry_price:       float
    sl_price:          float
    tp_price:          float
    tp2_price:         float | None     # EW 1.618 extension
    tp3_price:         float | None     # EW 2.618 extension
    lot_size:          float
    strategy:          str
    timeframe:         str
    probability_score: int
    confluences:       list
    ew_pattern:        str
    smc_bias:          str
    risk_reward:       float
    generated_at:      str


# ── Lot Size Calculator ──────────────────────────────────────────────────────
def calculate_lot_size(balance: float, risk_pct: float,
                       entry: float, sl: float) -> float:
    risk_amount = balance * (risk_pct / 100)
    pip_diff    = abs(entry - sl) * 10000
    if pip_diff == 0:
        return 0.01
    lot = risk_amount / (pip_diff * 10)
    return max(0.01, round(min(lot, 10.0), 2))


# ── ATR ──────────────────────────────────────────────────────────────────────
def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return float(df["close"].iloc[-1]) * 0.001
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    tr = np.maximum(h[1:] - l[1:],
         np.maximum(np.abs(h[1:] - c[:-1]),
                    np.abs(l[1:] - c[:-1])))
    return float(np.mean(tr[-period:]))


# ── Core Signal Generator ────────────────────────────────────────────────────
def generate_signal(symbol: str,
                    strategy_type: str = "swing",
                    account_balance: float = 10000) -> Optional[TradeSignal]:

    timeframes   = SWING_TIMEFRAMES  if strategy_type == "swing" else SHORT_TIMEFRAMES
    primary_tf   = timeframes[-1]
    secondary_tf = timeframes[0]

    # ── Fetch data ────────────────────────────────────────────────────────
    df_primary = get_ohlcv(symbol, primary_tf)
    if df_primary is None or df_primary.empty or len(df_primary) < 30:
        return None

    df_secondary = get_ohlcv(symbol, secondary_tf)
    has_secondary = (df_secondary is not None and
                     not df_secondary.empty and
                     len(df_secondary) >= 30)

    # ── Analysis ──────────────────────────────────────────────────────────
    ew   = identify_elliott_waves(df_primary)
    smc  = analyze_smc(df_primary)
    ew2  = identify_elliott_waves(df_secondary) if has_secondary else None
    smc2 = analyze_smc(df_secondary)             if has_secondary else None

    current_price = float(df_primary["close"].iloc[-1])
    atr           = _atr(df_primary)

    # ── Scoring ───────────────────────────────────────────────────────────
    score       = 0
    confluences = []
    bull_votes  = 0
    bear_votes  = 0

    # Elliott Wave
    if ew.pattern_type == "5-wave-impulse":
        score += 25
        confluences.append(f"EW: 5-Wave Impulse ({ew.trend.upper()})")
        if ew.trend == "bullish": bull_votes += 3
        else:                     bear_votes += 3
    elif ew.pattern_type == "3-wave-ABC":
        score += 12
        confluences.append("EW: ABC Corrective")
        if ew.trend == "bullish": bull_votes += 1
        else:                     bear_votes += 1
    else:
        # Unknown pattern — use simple trend direction
        if ew.trend == "bullish": bull_votes += 1
        else:                     bear_votes += 1

    if ew.confidence >= 0.65:
        score += 10
        confluences.append(f"EW Confidence: {ew.confidence*100:.0f}%")
    elif ew.confidence >= 0.45:
        score += 5

    # SMC Structure
    if smc.last_choch:
        score += 20
        confluences.append(f"SMC: CHoCH ({smc.last_choch.direction.upper()})")
        if smc.last_choch.direction == "bullish": bull_votes += 3
        else:                                      bear_votes += 3

    if smc.last_bos:
        score += 15
        confluences.append(f"SMC: BOS ({smc.last_bos.direction.upper()})")
        if smc.last_bos.direction == "bullish": bull_votes += 2
        else:                                    bear_votes += 2

    if smc.current_ob and not smc.current_ob.is_mitigated:
        score += 12
        lbl = "Bullish" if smc.current_ob.ob_type == "bullish" else "Bearish"
        confluences.append(f"SMC: {lbl} OB @ {smc.current_ob.mid:.5f}")
        if smc.current_ob.ob_type == "bullish": bull_votes += 2
        else:                                    bear_votes += 2

    if smc.nearest_fvg and not smc.nearest_fvg.is_filled:
        score += 8
        confluences.append(f"SMC: Unfilled FVG @ {smc.nearest_fvg.bottom:.5f}–{smc.nearest_fvg.top:.5f}")
        if smc.nearest_fvg.fvg_type == "bullish": bull_votes += 1
        else:                                       bear_votes += 1

    # Overall SMC trend
    if smc.trend == "bullish": bull_votes += 2
    elif smc.trend == "bearish": bear_votes += 2

    # Multi-timeframe confluence
    if ew2 and smc2:
        if ew2.trend == ew.trend:
            score += 10
            confluences.append(f"MTF: {secondary_tf} confirms {primary_tf}")
            if ew2.trend == "bullish": bull_votes += 2
            else:                       bear_votes += 2
        if smc2.trend == smc.trend:
            score += 5
            if smc2.trend == "bullish": bull_votes += 1
            else:                        bear_votes += 1

    # ── Direction ─────────────────────────────────────────────────────────
    if bull_votes == bear_votes:
        # Tie-break: use 20-bar price vs MA
        ma20 = float(df_primary["close"].iloc[-20:].mean())
        direction = "BUY" if current_price > ma20 else "SELL"
        confluences.append(f"Tie-break: price {'above' if direction=='BUY' else 'below'} MA20")
    else:
        direction = "BUY" if bull_votes > bear_votes else "SELL"

    # ── SL / TP ───────────────────────────────────────────────────────────
    if strategy_type == "swing":
        # Fibonacci-based
        fib  = ew.fib_levels
        if direction == "BUY":
            sl  = fib.get("0.500", current_price - atr * 2.0)
            sl  = min(sl, current_price - atr * 1.5)   # ensure sl is below entry
            tp  = ew.projected_target or (current_price + abs(current_price - sl) * 2.0)
        else:
            sl  = fib.get("0.500", current_price + atr * 2.0)
            sl  = max(sl, current_price + atr * 1.5)
            tp  = ew.projected_target or (current_price - abs(current_price - sl) * 2.0)
    else:
        # ATR-based with FVG reference
        if direction == "BUY":
            sl  = current_price - atr * 1.5
            tp  = current_price + atr * 3.0
            if smc.nearest_fvg and not smc.nearest_fvg.is_filled:
                if smc.nearest_fvg.fvg_type == "bullish":
                    sl = min(sl, smc.nearest_fvg.bottom - atr * 0.3)
                    tp = max(tp, smc.nearest_fvg.top + atr * 0.5)
        else:
            sl  = current_price + atr * 1.5
            tp  = current_price - atr * 3.0
            if smc.nearest_fvg and not smc.nearest_fvg.is_filled:
                if smc.nearest_fvg.fvg_type == "bearish":
                    sl = max(sl, smc.nearest_fvg.top + atr * 0.3)
                    tp = min(tp, smc.nearest_fvg.bottom - atr * 0.5)

    # Safety: ensure SL and TP are on correct sides
    if direction == "BUY":
        if sl >= current_price: sl = current_price - atr * 1.5
        if tp <= current_price: tp = current_price + atr * 2.5
    else:
        if sl <= current_price: sl = current_price + atr * 1.5
        if tp >= current_price: tp = current_price - atr * 2.5

    risk   = abs(current_price - sl)
    reward = abs(tp - current_price)
    rr     = round(reward / risk, 2) if risk > 0 else 1.0

    if rr < 1.5:
        score = max(0, score - 15)
    score = max(score, 20)

    lot  = calculate_lot_size(account_balance, 1.0, current_price, sl)

    # ── TP2 / TP3 from EW extensions ──────────────────────────────────────
    tp2 = getattr(ew, "projected_tp2", None)
    tp3 = getattr(ew, "projected_tp3", None)

    # Fallback: calculate from ATR if EW didn't provide them
    if tp2 is None:
        tp2 = round(current_price + atr * 4.0, 5) if direction == "BUY" else round(current_price - atr * 4.0, 5)
    if tp3 is None:
        tp3 = round(current_price + atr * 6.0, 5) if direction == "BUY" else round(current_price - atr * 6.0, 5)

    return TradeSignal(
        trade_id          = str(uuid.uuid4())[:8].upper(),
        symbol            = symbol,
        direction         = direction,
        entry_price       = round(current_price, 5),
        sl_price          = round(sl, 5),
        tp_price          = round(tp, 5),
        tp2_price         = round(tp2, 5) if tp2 else None,
        tp3_price         = round(tp3, 5) if tp3 else None,
        lot_size          = lot,
        strategy          = strategy_type,
        timeframe         = primary_tf,
        probability_score = min(int(score), 100),
        confluences       = confluences,
        ew_pattern        = ew.pattern_type,
        smc_bias          = smc.bias,
        risk_reward       = rr,
        generated_at      = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    )


# ── Batch Signal Generator ───────────────────────────────────────────────────
def generate_all_signals(symbols: list,
                         strategy_type: str = "swing",
                         min_score: int = 20) -> list:
    """Generate signals for all symbols. Returns list sorted by score desc."""
    signals = []
    for symbol in symbols:
        try:
            sig = generate_signal(symbol, strategy_type)
            if sig and sig.probability_score >= min_score:
                signals.append(sig)
        except Exception:
            pass
    signals.sort(key=lambda x: x.probability_score, reverse=True)
    return signals
