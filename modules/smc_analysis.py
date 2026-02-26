"""
modules/smc_analysis.py  v3 — FX-WavePulse Pro
Improvements over v2:
  • Multi-touch Order Block validation (price returns to OB = stronger)
  • Displacement candle detection (large engulfing = real break)
  • Refined CHoCH vs BOS distinction
  • FVG fill tracking with partial fill detection
  • Premium/Discount zone classification
  • Liquidity sweep detection (stop hunt pattern)
  • Confidence scoring from multiple factors
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class OrderBlock:
    index:        int
    ob_type:      str        # "bullish" | "bearish"
    top:          float
    bottom:       float
    mid:          float
    strength:     float      # 0-1
    is_mitigated: bool
    touch_count:  int   = 0  # how many times price returned to OB
    displacement: float = 0  # size of move that created OB (ATR multiple)


@dataclass
class FairValueGap:
    index:      int
    fvg_type:   str    # "bullish" | "bearish"
    top:        float
    bottom:     float
    mid:        float
    is_filled:  bool
    fill_pct:   float = 0.0   # 0-100% how much filled


@dataclass
class StructurePoint:
    index:          int
    price:          float
    structure_type: str   # "BOS" | "CHoCH"
    direction:      str   # "bullish" | "bearish"
    is_confirmed:   bool  = True
    displacement:   float = 0.0  # candle body size / ATR


@dataclass
class LiquiditySweep:
    index:     int
    sweep_type: str   # "buy_side" | "sell_side"
    level:     float  # the liquidity level swept
    direction: str    # "bullish" | "bearish" (direction after sweep)


@dataclass
class SMCResult:
    order_blocks:     list
    fair_value_gaps:  list
    structure_points: list
    liquidity_sweeps: list
    trend:            str
    current_ob:       Optional[OrderBlock]
    nearest_fvg:      Optional[FairValueGap]
    last_bos:         Optional[StructurePoint]
    last_choch:       Optional[StructurePoint]
    bias:             str
    confidence:       float
    premium_zone:     Optional[float]   # 61.8% level of range
    discount_zone:    Optional[float]   # 38.2% level of range
    equilibrium:      Optional[float]   # 50% level of range


def _atr(df, period=14) -> float:
    try:
        hi, lo, cl = df["high"].values, df["low"].values, df["close"].values
        tr = np.maximum(hi[1:]-lo[1:],
             np.maximum(abs(hi[1:]-cl[:-1]), abs(lo[1:]-cl[:-1])))
        return float(np.mean(tr[-period:])) if len(tr) >= period else float(np.mean(tr))
    except: return 0.001


def _body(o, c): return abs(c - o)
def _range(h, l): return h - l


def find_order_blocks(df: pd.DataFrame, lookback: int = 60) -> list:
    obs  = []
    sl   = df.iloc[-lookback:] if len(df) > lookback else df
    atr  = _atr(sl)
    if atr == 0: return obs

    opens  = sl["open"].values
    closes = sl["close"].values
    highs  = sl["high"].values
    lows   = sl["low"].values
    n      = len(sl)

    for i in range(2, n - 3):
        body_i = _body(opens[i], closes[i])

        # ── Bullish OB: last bearish candle before strong bull move ──
        if closes[i] < opens[i]:   # bearish candle
            # Measure subsequent bull displacement
            bull_disp = closes[i+1:min(i+4,n)].max() - closes[i]
            if bull_disp >= atr * 1.5:
                top    = max(opens[i], closes[i])
                bottom = min(opens[i], closes[i])
                # Mitigation: did price later return below OB bottom?
                future_lo  = lows[i+1:]
                mitigated  = bool(future_lo.min() < bottom) if len(future_lo) else False
                # Touch count: how many times price entered OB zone
                touches    = sum(1 for j in range(i+1, n)
                                 if bottom <= closes[j] <= top + atr*0.3)
                # Strength = displacement / ATR
                strength   = min(1.0, bull_disp / (atr * 3))
                obs.append(OrderBlock(
                    index=int(sl.index[i]) if hasattr(sl.index[i],"__int__") else i,
                    ob_type="bullish", top=float(top), bottom=float(bottom),
                    mid=float((top+bottom)/2), strength=strength,
                    is_mitigated=mitigated, touch_count=touches,
                    displacement=bull_disp/atr,
                ))

        # ── Bearish OB: last bullish candle before strong bear move ──
        if closes[i] > opens[i]:   # bullish candle
            bear_disp = closes[i] - closes[i+1:min(i+4,n)].min()
            if bear_disp >= atr * 1.5:
                top    = max(opens[i], closes[i])
                bottom = min(opens[i], closes[i])
                future_hi  = highs[i+1:]
                mitigated  = bool(future_hi.max() > top) if len(future_hi) else False
                touches    = sum(1 for j in range(i+1, n)
                                 if bottom - atr*0.3 <= closes[j] <= top)
                strength   = min(1.0, bear_disp / (atr * 3))
                obs.append(OrderBlock(
                    index=int(sl.index[i]) if hasattr(sl.index[i],"__int__") else i,
                    ob_type="bearish", top=float(top), bottom=float(bottom),
                    mid=float((top+bottom)/2), strength=strength,
                    is_mitigated=mitigated, touch_count=touches,
                    displacement=bear_disp/atr,
                ))

    # Sort by strength desc, prefer unmitigated multi-touch OBs
    obs.sort(key=lambda x: (not x.is_mitigated, x.touch_count, x.strength), reverse=True)
    return obs[:8]   # top 8


def find_fair_value_gaps(df: pd.DataFrame, lookback: int = 60) -> list:
    fvgs = []
    sl   = df.iloc[-lookback:] if len(df) > lookback else df
    atr  = _atr(sl)
    if atr == 0: return fvgs

    highs  = sl["high"].values
    lows   = sl["low"].values
    closes = sl["close"].values
    n      = len(sl)

    for i in range(1, n - 1):
        gap_up = lows[i+1] - highs[i-1]       # bullish FVG
        gap_dn = lows[i-1] - highs[i+1]       # bearish FVG

        # Bullish FVG: candle[i-1] high < candle[i+1] low
        if gap_up > atr * 0.3:
            top    = float(lows[i+1])
            bottom = float(highs[i-1])
            # Check fill: future low dips into gap
            future_lo = lows[i+2:] if i+2 < n else np.array([])
            filled    = bool(future_lo.min() <= bottom) if len(future_lo) else False
            fill_pct  = 0.0
            if not filled and len(future_lo):
                deepest = min(future_lo.min(), top)
                rng     = top - bottom
                fill_pct = max(0.0, min(100.0, (top - deepest) / rng * 100)) if rng else 0.0
            fvgs.append(FairValueGap(
                index=int(sl.index[i]) if hasattr(sl.index[i],"__int__") else i,
                fvg_type="bullish", top=top, bottom=bottom,
                mid=float((top+bottom)/2), is_filled=filled, fill_pct=fill_pct,
            ))

        # Bearish FVG
        if gap_dn > atr * 0.3:
            top    = float(lows[i-1])
            bottom = float(highs[i+1])
            future_hi = highs[i+2:] if i+2 < n else np.array([])
            filled    = bool(future_hi.max() >= top) if len(future_hi) else False
            fill_pct  = 0.0
            if not filled and len(future_hi):
                highest  = max(future_hi.max(), bottom)
                rng      = top - bottom
                fill_pct = max(0.0, min(100.0, (highest - bottom) / rng * 100)) if rng else 0.0
            fvgs.append(FairValueGap(
                index=int(sl.index[i]) if hasattr(sl.index[i],"__int__") else i,
                fvg_type="bearish", top=top, bottom=bottom,
                mid=float((top+bottom)/2), is_filled=filled, fill_pct=fill_pct,
            ))

    # Recent unfilled FVGs first
    fvgs.sort(key=lambda x: (not x.is_filled, x.index), reverse=True)
    return fvgs[:8]


def find_structure_points(df: pd.DataFrame, lookback: int = 100) -> list:
    """
    Detect BOS and CHoCH.
    BOS: Break of structure in trend direction (continuation)
    CHoCH: Change of character (potential reversal)
    """
    sps  = []
    sl   = df.iloc[-lookback:] if len(df) > lookback else df
    atr  = _atr(sl)
    if atr == 0: return sps

    highs  = sl["high"].values
    lows   = sl["low"].values
    closes = sl["close"].values
    opens  = sl["open"].values
    n      = len(sl)

    # Track last significant swing high/low
    window = max(5, n // 10)
    swing_highs, swing_lows = [], []

    for i in range(window, n - 1):
        local_hi = highs[max(0,i-window):i].max()
        local_lo = lows[max(0,i-window):i].min()

        # BOS Bullish: close breaks above recent swing high with displacement
        if closes[i] > local_hi and _body(opens[i],closes[i]) > atr * 0.7:
            disp = _body(opens[i], closes[i]) / atr
            # CHoCH if previous structure was bearish (trend reversal)
            stype = "CHoCH" if swing_lows and closes[i-1] < closes[max(0,i-window)] else "BOS"
            sps.append(StructurePoint(
                index=i, price=float(closes[i]),
                structure_type=stype, direction="bullish",
                displacement=disp, is_confirmed=disp > 0.8,
            ))
            swing_highs.append(closes[i])

        # BOS Bearish: close breaks below recent swing low
        elif closes[i] < local_lo and _body(opens[i],closes[i]) > atr * 0.7:
            disp = _body(opens[i], closes[i]) / atr
            stype = "CHoCH" if swing_highs and closes[i-1] > closes[max(0,i-window)] else "BOS"
            sps.append(StructurePoint(
                index=i, price=float(closes[i]),
                structure_type=stype, direction="bearish",
                displacement=disp, is_confirmed=disp > 0.8,
            ))
            swing_lows.append(closes[i])

    return sps[-12:]   # keep most recent 12


def find_liquidity_sweeps(df: pd.DataFrame, lookback: int = 50) -> list:
    """Detect stop hunts: spike beyond key level then reversal."""
    sweeps = []
    sl     = df.iloc[-lookback:] if len(df) > lookback else df
    atr    = _atr(sl)
    if atr == 0: return sweeps

    highs  = sl["high"].values
    lows   = sl["low"].values
    closes = sl["close"].values
    n      = len(sl)
    win    = max(5, n // 8)

    for i in range(win, n - 2):
        prev_hi = highs[max(0,i-win):i].max()
        prev_lo = lows[max(0,i-win):i].min()

        # Buy-side liquidity sweep: spike above prev high then close below
        if highs[i] > prev_hi + atr*0.2 and closes[i] < prev_hi:
            sweeps.append(LiquiditySweep(
                index=i, sweep_type="buy_side",
                level=float(prev_hi), direction="bearish",
            ))

        # Sell-side liquidity sweep: spike below prev low then close above
        if lows[i] < prev_lo - atr*0.2 and closes[i] > prev_lo:
            sweeps.append(LiquiditySweep(
                index=i, sweep_type="sell_side",
                level=float(prev_lo), direction="bullish",
            ))

    return sweeps[-6:]


def analyze_smc(df: pd.DataFrame) -> SMCResult:
    if len(df) < 20:
        return SMCResult(
            order_blocks=[], fair_value_gaps=[], structure_points=[],
            liquidity_sweeps=[], trend="neutral", current_ob=None,
            nearest_fvg=None, last_bos=None, last_choch=None,
            bias="Insufficient data", confidence=0.0,
            premium_zone=None, discount_zone=None, equilibrium=None,
        )

    obs      = find_order_blocks(df)
    fvgs     = find_fair_value_gaps(df)
    sps      = find_structure_points(df)
    sweeps   = find_liquidity_sweeps(df)
    atr      = _atr(df)

    closes   = df["close"].values
    cp       = float(closes[-1])

    # ── Trend from structure ──────────────────────────────────
    bull_bos  = sum(1 for s in sps if s.structure_type=="BOS"   and s.direction=="bullish" and s.is_confirmed)
    bear_bos  = sum(1 for s in sps if s.structure_type=="BOS"   and s.direction=="bearish" and s.is_confirmed)
    bull_choch= sum(1 for s in sps if s.structure_type=="CHoCH" and s.direction=="bullish")
    bear_choch= sum(1 for s in sps if s.structure_type=="CHoCH" and s.direction=="bearish")

    # Price vs 20-bar EMA
    ema20 = float(pd.Series(closes).ewm(span=20, adjust=False).mean().iloc[-1])

    bull_score = bull_bos*2 + bull_choch + (1 if cp > ema20 else 0)
    bear_score = bear_bos*2 + bear_choch + (1 if cp < ema20 else 0)

    if   bull_score > bear_score: trend = "bullish"
    elif bear_score > bull_score: trend = "bearish"
    else:
        trend = "bullish" if closes[-1] > closes[max(0,len(closes)-20)] else "bearish"

    # ── Current OB (nearest relevant unmitigated) ─────────────
    current_ob = None
    for ob in obs:
        if ob.is_mitigated: continue
        if trend == "bullish" and ob.ob_type == "bullish" and ob.top < cp:
            current_ob = ob; break
        if trend == "bearish" and ob.ob_type == "bearish" and ob.bottom > cp:
            current_ob = ob; break

    # ── Nearest unfilled FVG ──────────────────────────────────
    nearest_fvg = None
    for fvg in fvgs:
        if not fvg.is_filled:
            nearest_fvg = fvg; break

    # ── Last BOS and CHoCH ────────────────────────────────────
    last_bos   = next((s for s in reversed(sps) if s.structure_type=="BOS"),   None)
    last_choch = next((s for s in reversed(sps) if s.structure_type=="CHoCH"), None)

    # ── Premium / Discount / Equilibrium ─────────────────────
    recent_hi = float(df["high"].iloc[-50:].max())
    recent_lo = float(df["low"].iloc[-50:].min())
    rng       = recent_hi - recent_lo
    premium   = recent_lo + rng * 0.618
    discount  = recent_lo + rng * 0.382
    equil     = recent_lo + rng * 0.500
    zone_label = ""
    if cp >= premium:
        zone_label = "PREMIUM (sell bias)"
    elif cp <= discount:
        zone_label = "DISCOUNT (buy bias)"
    else:
        zone_label = "EQUILIBRIUM"

    # ── Liquidity sweeps add bias ─────────────────────────────
    recent_sweep = sweeps[-1] if sweeps else None
    sweep_bias   = ""
    if recent_sweep:
        if recent_sweep.direction == "bullish":
            sweep_bias = " · Sell-side swept → bull reversal possible"
        else:
            sweep_bias = " · Buy-side swept → bear reversal possible"

    # ── Confidence ────────────────────────────────────────────
    conf = 0.3
    if current_ob:    conf += 0.2 * current_ob.strength
    if last_choch:    conf += 0.15
    if last_bos:      conf += 0.10
    if nearest_fvg and not nearest_fvg.is_filled: conf += 0.10
    if recent_sweep:  conf += 0.10
    conf = min(conf, 1.0)

    # ── Bias description ──────────────────────────────────────
    ob_desc  = f"OB @ {current_ob.mid:.5f} (×{current_ob.touch_count}touches)" if current_ob else "No key OB"
    fvg_desc = f"FVG {nearest_fvg.fvg_type} {nearest_fvg.fill_pct:.0f}% filled" if nearest_fvg else "No FVG"
    bias = (
        f"{'Bullish' if trend=='bullish' else 'Bearish'} · {zone_label}"
        f" · {ob_desc} · {fvg_desc}{sweep_bias}"
    )

    return SMCResult(
        order_blocks     = obs,
        fair_value_gaps  = fvgs,
        structure_points = sps,
        liquidity_sweeps = sweeps,
        trend            = trend,
        current_ob       = current_ob,
        nearest_fvg      = nearest_fvg,
        last_bos         = last_bos,
        last_choch       = last_choch,
        bias             = bias,
        confidence       = round(conf, 3),
        premium_zone     = round(premium, 5),
        discount_zone    = round(discount, 5),
        equilibrium      = round(equil, 5),
    )
