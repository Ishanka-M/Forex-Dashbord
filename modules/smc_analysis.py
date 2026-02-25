"""
modules/smc_analysis.py
Smart Money Concepts (SMC) Analysis Engine
Identifies: Order Blocks, BOS, CHoCH, Fair Value Gaps
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class OrderBlock:
    index: int
    ob_type: str       # "bullish" | "bearish"
    top: float
    bottom: float
    mid: float
    strength: float    # 0-1 based on move after OB
    is_mitigated: bool
    timestamp: Optional[str] = None


@dataclass
class FairValueGap:
    index: int
    fvg_type: str   # "bullish" | "bearish"
    top: float
    bottom: float
    mid: float
    is_filled: bool
    timestamp: Optional[str] = None


@dataclass
class StructurePoint:
    index: int
    price: float
    structure_type: str  # "BOS" | "CHoCH"
    direction: str       # "bullish" | "bearish"
    timestamp: Optional[str] = None


@dataclass
class SMCResult:
    order_blocks: list[OrderBlock]
    fair_value_gaps: list[FairValueGap]
    structure_points: list[StructurePoint]
    trend: str           # "bullish" | "bearish" | "neutral"
    current_ob: Optional[OrderBlock]
    nearest_fvg: Optional[FairValueGap]
    last_bos: Optional[StructurePoint]
    last_choch: Optional[StructurePoint]
    bias: str
    confidence: float


def find_order_blocks(df: pd.DataFrame, lookback: int = 50) -> list[OrderBlock]:
    """
    Identify Order Blocks:
    - Bearish OB: Last up-close candle before strong bearish move
    - Bullish OB: Last down-close candle before strong bullish move
    """
    obs = []
    df_slice = df.iloc[-lookback:] if len(df) > lookback else df
    closes = df_slice["close"].values
    opens = df_slice["open"].values
    highs = df_slice["high"].values
    lows = df_slice["low"].values

    atr = _calculate_atr(df_slice, 14)

    for i in range(3, len(df_slice) - 3):
        # Bullish OB: Bearish candle (close < open) followed by strong bullish move
        if closes[i] < opens[i]:  # Bearish candle
            # Check if next candles make a strong bullish move
            next_range = closes[i+1:i+4]
            if len(next_range) >= 2 and closes[i+2] > highs[i]:
                move_size = closes[i+2] - lows[i]
                strength = min(move_size / (atr * 2), 1.0) if atr > 0 else 0.5
                current_price = closes[-1]
                is_mitigated = current_price >= lows[i] and current_price <= highs[i]
                
                obs.append(OrderBlock(
                    index=df_slice.index[i] if hasattr(df_slice.index[i], '__index__') else i,
                    ob_type="bullish",
                    top=highs[i],
                    bottom=lows[i],
                    mid=(highs[i] + lows[i]) / 2,
                    strength=round(strength, 3),
                    is_mitigated=is_mitigated,
                    timestamp=str(df_slice.index[i]) if len(df_slice) > 0 else None
                ))

        # Bearish OB: Bullish candle (close > open) followed by strong bearish move
        if closes[i] > opens[i]:  # Bullish candle
            if len(closes) > i + 2 and closes[i+2] < lows[i]:
                move_size = highs[i] - closes[i+2]
                strength = min(move_size / (atr * 2), 1.0) if atr > 0 else 0.5
                current_price = closes[-1]
                is_mitigated = current_price >= lows[i] and current_price <= highs[i]
                
                obs.append(OrderBlock(
                    index=i,
                    ob_type="bearish",
                    top=highs[i],
                    bottom=lows[i],
                    mid=(highs[i] + lows[i]) / 2,
                    strength=round(strength, 3),
                    is_mitigated=is_mitigated,
                    timestamp=str(df_slice.index[i])
                ))

    return obs


def find_fair_value_gaps(df: pd.DataFrame, lookback: int = 50) -> list[FairValueGap]:
    """
    Identify Fair Value Gaps (Imbalances):
    - Bullish FVG: Gap between candle[i-1].high and candle[i+1].low
    - Bearish FVG: Gap between candle[i-1].low and candle[i+1].high
    """
    fvgs = []
    df_slice = df.iloc[-lookback:] if len(df) > lookback else df
    highs = df_slice["high"].values
    lows = df_slice["low"].values
    closes = df_slice["close"].values

    current_price = closes[-1]

    for i in range(1, len(df_slice) - 1):
        # Bullish FVG: Gap up
        if lows[i+1] > highs[i-1]:
            gap_top = lows[i+1]
            gap_bottom = highs[i-1]
            gap_mid = (gap_top + gap_bottom) / 2
            is_filled = current_price <= gap_top and current_price >= gap_bottom
            
            fvgs.append(FairValueGap(
                index=i,
                fvg_type="bullish",
                top=gap_top,
                bottom=gap_bottom,
                mid=gap_mid,
                is_filled=is_filled,
                timestamp=str(df_slice.index[i])
            ))

        # Bearish FVG: Gap down
        if highs[i+1] < lows[i-1]:
            gap_top = lows[i-1]
            gap_bottom = highs[i+1]
            gap_mid = (gap_top + gap_bottom) / 2
            is_filled = current_price >= gap_bottom and current_price <= gap_top
            
            fvgs.append(FairValueGap(
                index=i,
                fvg_type="bearish",
                top=gap_top,
                bottom=gap_bottom,
                mid=gap_mid,
                is_filled=is_filled,
                timestamp=str(df_slice.index[i])
            ))

    return fvgs


def identify_market_structure(df: pd.DataFrame, swing_order: int = 5) -> list[StructurePoint]:
    """
    Identify Break of Structure (BOS) and Change of Character (CHoCH).
    BOS: Price breaks a significant high/low in the direction of the trend.
    CHoCH: Price breaks a significant high/low AGAINST the current trend.
    """
    from scipy.signal import argrelextrema
    structure_points = []

    highs = df["high"].values
    lows = df["low"].values
    closes = df["close"].values

    if len(closes) < 20:
        return structure_points

    local_max_idx = argrelextrema(highs, np.greater_equal, order=swing_order)[0]
    local_min_idx = argrelextrema(lows, np.less_equal, order=swing_order)[0]

    # Track last significant HH/HL/LH/LL
    prev_high = None
    prev_low = None
    current_trend = "neutral"

    all_pivots = sorted(
        [(i, highs[i], "high") for i in local_max_idx] +
        [(i, lows[i], "low") for i in local_min_idx],
        key=lambda x: x[0]
    )

    for i, (idx, price, ptype) in enumerate(all_pivots):
        if ptype == "high" and prev_high is not None:
            if price > prev_high:
                if current_trend == "bullish":
                    # BOS bullish - higher high
                    structure_points.append(StructurePoint(
                        index=idx, price=price, structure_type="BOS",
                        direction="bullish",
                        timestamp=str(df.index[idx]) if idx < len(df) else None
                    ))
                elif current_trend == "bearish":
                    # CHoCH - breaking bearish trend
                    structure_points.append(StructurePoint(
                        index=idx, price=price, structure_type="CHoCH",
                        direction="bullish",
                        timestamp=str(df.index[idx]) if idx < len(df) else None
                    ))
                    current_trend = "bullish"
            current_trend = "bullish" if price > prev_high else current_trend

        if ptype == "low" and prev_low is not None:
            if price < prev_low:
                if current_trend == "bearish":
                    structure_points.append(StructurePoint(
                        index=idx, price=price, structure_type="BOS",
                        direction="bearish",
                        timestamp=str(df.index[idx]) if idx < len(df) else None
                    ))
                elif current_trend == "bullish":
                    structure_points.append(StructurePoint(
                        index=idx, price=price, structure_type="CHoCH",
                        direction="bearish",
                        timestamp=str(df.index[idx]) if idx < len(df) else None
                    ))
                    current_trend = "bearish"

        if ptype == "high":
            prev_high = price
        else:
            prev_low = price

    return structure_points


def analyze_smc(df: pd.DataFrame) -> SMCResult:
    """Full SMC analysis pipeline."""
    if len(df) < 20:
        return SMCResult(
            order_blocks=[], fair_value_gaps=[], structure_points=[],
            trend="neutral", current_ob=None, nearest_fvg=None,
            last_bos=None, last_choch=None, bias="Insufficient data",
            confidence=0.0
        )

    order_blocks = find_order_blocks(df)
    fvgs = find_fair_value_gaps(df)
    structure = identify_market_structure(df)

    current_price = df["close"].iloc[-1]

    # Determine trend from structure
    recent_bos = [s for s in structure if s.structure_type == "BOS"]
    recent_choch = [s for s in structure if s.structure_type == "CHoCH"]

    last_bos = recent_bos[-1] if recent_bos else None
    last_choch = recent_choch[-1] if recent_choch else None

    trend = "neutral"
    if last_choch:
        trend = last_choch.direction
    elif last_bos:
        trend = last_bos.direction

    # Find nearest unmitigated OB
    unmitigated_obs = [ob for ob in order_blocks if not ob.is_mitigated]
    current_ob = None
    if unmitigated_obs:
        dists = [(abs(ob.mid - current_price), ob) for ob in unmitigated_obs]
        dists.sort(key=lambda x: x[0])
        current_ob = dists[0][1] if dists else None

    # Find nearest unfilled FVG
    unfilled_fvgs = [f for f in fvgs if not f.is_filled]
    nearest_fvg = None
    if unfilled_fvgs:
        dists = [(abs(f.mid - current_price), f) for f in unfilled_fvgs]
        dists.sort(key=lambda x: x[0])
        nearest_fvg = dists[0][1] if dists else None

    # Calculate confidence
    confidence = 0.5
    if last_choch: confidence += 0.15
    if last_bos: confidence += 0.1
    if current_ob: confidence += 0.15
    if nearest_fvg: confidence += 0.1

    # Bias description
    bias = f"{trend.capitalize()} bias"
    if current_ob:
        bias += f" | OB @ {current_ob.bottom:.5f}-{current_ob.top:.5f}"
    if nearest_fvg:
        bias += f" | FVG @ {nearest_fvg.bottom:.5f}-{nearest_fvg.top:.5f}"

    return SMCResult(
        order_blocks=order_blocks[-10:],
        fair_value_gaps=fvgs[-10:],
        structure_points=structure[-20:],
        trend=trend,
        current_ob=current_ob,
        nearest_fvg=nearest_fvg,
        last_bos=last_bos,
        last_choch=last_choch,
        bias=bias,
        confidence=round(min(confidence, 1.0), 3)
    )


def _calculate_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Calculate Average True Range."""
    if len(df) < period:
        return 0.001
    high = df["high"].values
    low = df["low"].values
    close = df["close"].values
    tr = np.maximum(high[1:] - low[1:],
                    np.maximum(abs(high[1:] - close[:-1]),
                               abs(low[1:] - close[:-1])))
    return np.mean(tr[-period:])
