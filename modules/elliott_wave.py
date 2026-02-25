"""
modules/elliott_wave.py
Elliott Wave Theory Analysis Engine
Identifies 5-wave impulse and 3-wave corrective (ABC) patterns
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from dataclasses import dataclass
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class WavePoint:
    index: int
    price: float
    wave_label: str
    wave_type: str  # "impulse" | "corrective"
    direction: str  # "up" | "down"


@dataclass
class ElliottWaveResult:
    pattern_type: str         # "5-wave-impulse" | "3-wave-ABC" | "unknown"
    wave_points: list[WavePoint]
    current_wave: str         # "1","2","3","4","5","A","B","C"
    projected_target: Optional[float]
    projected_sl: Optional[float]
    confidence: float         # 0.0 - 1.0
    trend: str                # "bullish" | "bearish" | "neutral"
    fib_levels: dict
    description: str


FIBONACCI_RATIOS = {
    "0.236": 0.236,
    "0.382": 0.382,
    "0.500": 0.500,
    "0.618": 0.618,
    "0.786": 0.786,
    "1.000": 1.000,
    "1.272": 1.272,
    "1.618": 1.618,
    "2.618": 2.618,
}


def find_swing_points(df: pd.DataFrame, order: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """Find local swing highs and lows using scipy."""
    closes = df["close"].values
    highs = df["high"].values
    lows = df["low"].values

    # Use 'order' bars on each side
    local_maxima = argrelextrema(highs, np.greater_equal, order=order)[0]
    local_minima = argrelextrema(lows, np.less_equal, order=order)[0]
    
    return local_maxima, local_minima


def calculate_fibonacci_levels(wave_start: float, wave_end: float, direction: str = "up") -> dict:
    """Calculate Fibonacci retracement and extension levels."""
    diff = abs(wave_end - wave_start)
    levels = {}
    
    for name, ratio in FIBONACCI_RATIOS.items():
        if direction == "up":
            levels[name] = wave_end - (diff * ratio)
        else:
            levels[name] = wave_end + (diff * ratio)
    
    # Extension levels
    ext_ratios = {"1.272_ext": 1.272, "1.618_ext": 1.618, "2.618_ext": 2.618}
    for name, ratio in ext_ratios.items():
        if direction == "up":
            levels[name] = wave_start + (diff * ratio)
        else:
            levels[name] = wave_start - (diff * ratio)
    
    return levels


def validate_impulse_rules(waves: list) -> tuple[bool, float]:
    """
    Validate Elliott Wave Rules for 5-wave impulse:
    Rule 1: Wave 2 never retraces more than 100% of Wave 1
    Rule 2: Wave 3 is never the shortest among 1, 3, 5
    Rule 3: Wave 4 never enters Wave 1's price territory (except in diagonals)
    Returns (is_valid, confidence_score)
    """
    if len(waves) < 5:
        return False, 0.0

    p = [w["price"] for w in waves]
    score = 0.0
    checks = 0

    # Rule 1: Wave 2 retracement
    w1_range = abs(p[1] - p[0])
    w2_retrace = abs(p[2] - p[1])
    if w2_retrace < w1_range:
        score += 1.0
        if 0.382 * w1_range <= w2_retrace <= 0.786 * w1_range:
            score += 0.5  # Ideal retracement
    checks += 1.5

    # Rule 2: Wave 3 not shortest
    w1_len = abs(p[1] - p[0])
    w3_len = abs(p[3] - p[2])
    w5_len = abs(p[4] - p[3]) if len(p) > 4 else 0
    if w3_len > w1_len and w3_len > w5_len:
        score += 1.5
    elif w3_len >= w1_len or w3_len >= w5_len:
        score += 0.5
    checks += 1.5

    # Rule 3: Wave 4 doesn't overlap Wave 1
    is_bullish = p[1] > p[0]
    if is_bullish:
        if p[4] > p[1]:  # Wave 4 low above Wave 1 high
            score += 1.0
    else:
        if p[4] < p[1]:  # Wave 4 high below Wave 1 low
            score += 1.0
    checks += 1.0

    # Wave 3 often ~1.618x Wave 1
    if w1_len > 0:
        ratio = w3_len / w1_len
        if 1.5 <= ratio <= 2.0:
            score += 0.5
    checks += 0.5

    confidence = min(score / checks, 1.0) if checks > 0 else 0.0
    return confidence > 0.5, confidence


def identify_elliott_waves(df: pd.DataFrame, order: int = 5) -> ElliottWaveResult:
    """
    Main Elliott Wave identification function.
    Returns ElliottWaveResult with wave counts, targets, and confidence.
    """
    if len(df) < 30:
        return ElliottWaveResult(
            pattern_type="unknown", wave_points=[], current_wave="?",
            projected_target=None, projected_sl=None, confidence=0.0,
            trend="neutral", fib_levels={}, description="Insufficient data"
        )

    highs_idx, lows_idx = find_swing_points(df, order=order)

    if len(highs_idx) < 2 or len(lows_idx) < 2:
        return ElliottWaveResult(
            pattern_type="unknown", wave_points=[], current_wave="?",
            projected_target=None, projected_sl=None, confidence=0.0,
            trend="neutral", fib_levels={}, description="Cannot identify swing points"
        )

    # Build combined pivot list
    pivots = []
    for idx in highs_idx[-15:]:
        pivots.append({"index": idx, "price": df["high"].iloc[idx], "type": "high"})
    for idx in lows_idx[-15:]:
        pivots.append({"index": idx, "price": df["low"].iloc[idx], "type": "low"})
    pivots = sorted(pivots, key=lambda x: x["index"])

    # Try to find 5-wave impulse pattern
    best_impulse = None
    best_confidence = 0.0

    for i in range(len(pivots) - 4):
        # Need alternating high-low or low-high
        candidate = pivots[i:i+5]
        types = [p["type"] for p in candidate]
        
        is_bullish_attempt = types[0] == "low"
        is_bearish_attempt = types[0] == "high"
        
        if is_bullish_attempt and types == ["low", "high", "low", "high", "low"]:
            is_valid, conf = validate_impulse_rules(candidate)
            if conf > best_confidence:
                best_confidence = conf
                best_impulse = (candidate, "bullish")
        
        if is_bearish_attempt and types == ["high", "low", "high", "low", "high"]:
            is_valid, conf = validate_impulse_rules(candidate)
            if conf > best_confidence:
                best_confidence = conf
                best_impulse = (candidate, "bearish")

    if best_impulse and best_confidence > 0.4:
        waves_data, trend = best_impulse
        current_price = df["close"].iloc[-1]
        last_wave = waves_data[-1]
        wave_labels = ["0", "1", "2", "3", "4", "5"] if trend == "bullish" else ["0", "1", "2", "3", "4", "5"]
        
        wave_points = [
            WavePoint(w["index"], w["price"], str(i), "impulse", trend)
            for i, w in enumerate(waves_data)
        ]

        # Determine current wave based on price position
        wave_prices = [w["price"] for w in waves_data]
        
        fib_levels = calculate_fibonacci_levels(wave_prices[0], wave_prices[2], trend)
        
        # Project Wave 5 or next corrective
        w1_size = abs(wave_prices[1] - wave_prices[0])
        if trend == "bullish":
            projected_target = wave_prices[4] + w1_size * 1.0  # ~1:1 with wave 1
            projected_sl = wave_prices[3]  # Wave 4 low
            current_wave = "5" if current_price > wave_prices[3] else "4"
        else:
            projected_target = wave_prices[4] - w1_size * 1.0
            projected_sl = wave_prices[3]
            current_wave = "5" if current_price < wave_prices[3] else "4"

        return ElliottWaveResult(
            pattern_type="5-wave-impulse",
            wave_points=wave_points,
            current_wave=current_wave,
            projected_target=round(projected_target, 5),
            projected_sl=round(projected_sl, 5),
            confidence=round(best_confidence, 3),
            trend=trend,
            fib_levels=fib_levels,
            description=f"{trend.capitalize()} 5-wave impulse. Currently in Wave {current_wave}."
        )

    # Try 3-wave ABC corrective
    for i in range(len(pivots) - 2):
        candidate = pivots[i:i+3]
        types = [p["type"] for p in candidate]
        prices = [p["price"] for p in candidate]

        a_size = abs(prices[1] - prices[0])
        b_size = abs(prices[2] - prices[1])

        is_valid_abc = (
            b_size < a_size and  # B < A
            b_size >= 0.382 * a_size  # B retraces at least 38.2% of A
        )

        if is_valid_abc:
            trend = "bearish" if types[0] == "high" else "bullish"
            c_target = prices[1] + (a_size * 1.0 if trend == "bearish" else -a_size * 1.0)
            fib_levels = calculate_fibonacci_levels(prices[0], prices[1], "down" if trend == "bearish" else "up")

            return ElliottWaveResult(
                pattern_type="3-wave-ABC",
                wave_points=[
                    WavePoint(candidate[0]["index"], prices[0], "A", "corrective", trend),
                    WavePoint(candidate[1]["index"], prices[1], "B", "corrective", trend),
                    WavePoint(candidate[2]["index"], prices[2], "C", "corrective", trend),
                ],
                current_wave="C",
                projected_target=round(c_target, 5),
                projected_sl=round(prices[0], 5),
                confidence=0.55,
                trend=trend,
                fib_levels=fib_levels,
                description=f"ABC corrective pattern. Wave C targeting {round(c_target, 5)}."
            )

    # Fallback: Trend analysis
    closes = df["close"].values
    trend = "bullish" if closes[-1] > closes[-20] else "bearish"
    recent_high = df["high"].iloc[-20:].max()
    recent_low = df["low"].iloc[-20:].min()
    fib_levels = calculate_fibonacci_levels(recent_low, recent_high, "up" if trend == "bullish" else "down")

    return ElliottWaveResult(
        pattern_type="unknown",
        wave_points=[],
        current_wave="?",
        projected_target=None,
        projected_sl=None,
        confidence=0.3,
        trend=trend,
        fib_levels=fib_levels,
        description=f"Pattern unclear. General {trend} trend detected."
    )
