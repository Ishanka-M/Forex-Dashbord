"""
modules/elliott_wave.py  v3 — FX-WavePulse Pro
Improvements over v2:
  • 6-point pivot scan (0-1-2-3-4-5) for strict alternation
  • Adaptive swing order (scales with data length)
  • Wave 3 extended detection (161.8% / 261.8%)
  • Alternation rule (wave 2 vs wave 4 character)
  • TP1/TP2/TP3 from wave 4 base using Fibonacci extensions
  • ABC corrective: B retracement quality scoring
  • Confidence score from rule compliance (0-100%)
"""

import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
from dataclasses import dataclass, field
from typing import Optional
import warnings
warnings.filterwarnings("ignore")


@dataclass
class WavePoint:
    index:      int
    price:      float
    wave_label: str
    wave_type:  str    # "impulse" | "corrective"
    direction:  str    # "bullish" | "bearish"


@dataclass
class ElliottWaveResult:
    pattern_type:     str
    wave_points:      list
    current_wave:     str
    projected_target: Optional[float]   # TP1
    projected_tp2:    Optional[float]   # 1.618 extension
    projected_tp3:    Optional[float]   # 2.618 extension
    projected_sl:     Optional[float]
    confidence:       float
    trend:            str
    fib_levels:       dict
    description:      str
    wave3_extended:   bool = False


FIB = {"0.236":0.236,"0.382":0.382,"0.500":0.500,"0.618":0.618,
       "0.786":0.786,"1.000":1.000,"1.272":1.272,"1.618":1.618,
       "2.000":2.000,"2.618":2.618,"4.236":4.236}


def _aorder(df):
    n = len(df)
    if n >= 500: return 10
    if n >= 200: return 7
    if n >= 100: return 5
    return 3

def _sz(a,b): return abs(b-a)


def find_swing_points(df: pd.DataFrame, order: int = None):
    if order is None: order = _aorder(df)
    H = df["high"].values
    L = df["low"].values
    maxima = argrelextrema(H, np.greater_equal, order=order)[0]
    minima = argrelextrema(L, np.less_equal,    order=order)[0]

    def dedup_hi(arr):
        out = []
        for i in arr:
            if out and i - out[-1] <= order:
                if H[i] > H[out[-1]]: out[-1] = i
            else: out.append(i)
        return np.array(out)

    def dedup_lo(arr):
        out = []
        for i in arr:
            if out and i - out[-1] <= order:
                if L[i] < L[out[-1]]: out[-1] = i
            else: out.append(i)
        return np.array(out)

    return dedup_hi(maxima), dedup_lo(minima)


def calculate_fibonacci_levels(start: float, end: float, direction: str = "up") -> dict:
    diff = abs(end - start)
    out  = {}
    for name, ratio in FIB.items():
        if direction == "up":
            out[f"ret_{name}"] = end   - diff * ratio
            out[f"ext_{name}"] = start + diff * ratio
        else:
            out[f"ret_{name}"] = end   + diff * ratio
            out[f"ext_{name}"] = start - diff * ratio
    return out


def _clean_pivots(pivots):
    """Remove consecutive same-type pivots, keeping the more extreme."""
    clean = [pivots[0]] if pivots else []
    for pv in pivots[1:]:
        if pv["type"] == clean[-1]["type"]:
            if pv["type"] == "high":
                if pv["price"] > clean[-1]["price"]: clean[-1] = pv
            else:
                if pv["price"] < clean[-1]["price"]: clean[-1] = pv
        else:
            clean.append(pv)
    return clean


def _validate_5wave(waves: list):
    """
    Validate 5-wave impulse. Returns (valid, confidence 0-1, details).
    Needs 6 points: [0,1,2,3,4,5]
    """
    if len(waves) < 6: return False, 0.0, {}

    p       = [w["price"] for w in waves]
    is_bull = p[1] > p[0]
    score, checks = 0.0, 0.0
    det = {}

    w1 = _sz(p[0],p[1])
    w2 = _sz(p[1],p[2])
    w3 = _sz(p[2],p[3])
    w4 = _sz(p[3],p[4])
    w5 = _sz(p[4],p[5])

    # Rule 1: Wave 2 < 100% of Wave 1
    checks += 2
    if w1 > 0:
        r2 = w2/w1
        det["w2_retrace"] = f"{r2:.1%}"
        if r2 < 1.0:
            score += 1.0
            if 0.382 <= r2 <= 0.618: score += 1.0; det["w2_ideal"] = True

    # Rule 2: Wave 3 never shortest
    checks += 3
    if w3 > w1 and w3 > w5:
        score += 2.0; det["w3_longest"] = True
    elif w3 > w1 or w3 > w5:
        score += 0.5

    # Wave 3 extension
    checks += 1
    if w1 > 0:
        r3 = w3/w1; det["w3_ext_ratio"] = f"{r3:.2f}x"
        if r3 >= 1.618: score += 1.0; det["w3_extended"] = True
        elif r3 >= 1.2:  score += 0.5

    # Rule 3: Wave 4 no overlap Wave 1
    checks += 2
    if is_bull:
        if p[4] > p[1]: score += 2.0; det["no_overlap"] = True
        elif p[4] > p[0]: score += 0.5
    else:
        if p[4] < p[1]: score += 2.0; det["no_overlap"] = True
        elif p[4] < p[0]: score += 0.5

    # Rule 4: Wave 4 Fibonacci (23.6%–38.2% of Wave 3)
    checks += 1
    if w3 > 0:
        r4 = w4/w3
        if 0.236 <= r4 <= 0.382: score += 1.0; det["w4_fib"] = True
        elif r4 <= 0.5: score += 0.3

    # Rule 5: Alternation (W2 vs W4 different character)
    checks += 0.5
    if w1 > 0 and w3 > 0:
        if abs(w2/w1 - w4/w3) > 0.1: score += 0.5; det["alternation"] = True

    # Rule 6: Wave 5 reasonable (50%–161.8% of Wave 1)
    checks += 0.5
    if w1 > 0:
        r5 = w5/w1
        if 0.5 <= r5 <= 1.618: score += 0.5; det["w5_ok"] = True

    conf     = min(score / checks, 1.0) if checks > 0 else 0.0
    is_valid = conf > 0.40
    return is_valid, conf, det


def identify_elliott_waves(df: pd.DataFrame, order: int = None) -> ElliottWaveResult:

    _NULL = ElliottWaveResult(
        pattern_type="unknown", wave_points=[], current_wave="?",
        projected_target=None, projected_tp2=None, projected_tp3=None,
        projected_sl=None, confidence=0.25, trend="neutral",
        fib_levels={}, description="Insufficient data"
    )

    if len(df) < 30: return _NULL

    best_impulse = None
    best_conf    = 0.0
    best_det     = {}

    # Try 3 different sensitivity levels
    base = _aorder(df)
    for try_ord in [base, max(3, base-2), min(20, base+4)]:
        hi_idx, lo_idx = find_swing_points(df, order=try_ord)
        if len(hi_idx) < 3 or len(lo_idx) < 3: continue

        pivots = []
        for i in hi_idx[-25:]:
            pivots.append({"index":int(i), "price":float(df["high"].iloc[i]), "type":"high"})
        for i in lo_idx[-25:]:
            pivots.append({"index":int(i), "price":float(df["low"].iloc[i]),  "type":"low"})
        pivots.sort(key=lambda x: x["index"])
        pivots = _clean_pivots(pivots)

        # Scan 6-point windows
        for i in range(len(pivots)-5):
            cand  = pivots[i:i+6]
            types = [c["type"] for c in cand]
            bull  = ["low","high","low","high","low","high"]
            bear  = ["high","low","high","low","high","low"]
            if types not in (bull, bear): continue
            is_bull = types == bull
            ok, conf, det = _validate_5wave(cand)
            if conf > best_conf:
                best_conf    = conf
                best_impulse = (cand, "bullish" if is_bull else "bearish")
                best_det     = det

        if best_conf >= 0.70: break   # Good enough

    # ── 5-wave impulse result ─────────────────────────────────
    if best_impulse and best_conf > 0.38:
        waves_data, trend = best_impulse
        p   = [w["price"] for w in waves_data]
        cp  = float(df["close"].iloc[-1])
        w1  = _sz(p[0],p[1])
        w3  = _sz(p[2],p[3])
        w3x = best_det.get("w3_extended", False)

        wave_pts = [
            WavePoint(w["index"], w["price"], str(i), "impulse", trend)
            for i, w in enumerate(waves_data)
        ]

        base_fib = calculate_fibonacci_levels(p[0], p[2], trend)

        # TP projections from wave 4 base
        b = p[4]
        if trend == "bullish":
            tp1 = b + w1 * 1.000
            tp2 = b + w1 * 1.618
            tp3 = b + w1 * 2.618
            sl  = p[3]                # Wave 4 low
            cw  = "5" if cp > p[3] else "4"
        else:
            tp1 = b - w1 * 1.000
            tp2 = b - w1 * 1.618
            tp3 = b - w1 * 2.618
            sl  = p[3]
            cw  = "5" if cp < p[3] else "4"

        desc = (
            f"{'Bullish' if trend=='bullish' else 'Bearish'} 5-wave impulse"
            f" · Wave {cw}"
            + (" · Wave 3 Extended ×{:.1f}".format(w3/w1) if w3x and w1 > 0 else "")
            + f" · Confidence {best_conf*100:.0f}%"
        )

        return ElliottWaveResult(
            pattern_type     = "5-wave-impulse",
            wave_points      = wave_pts,
            current_wave     = cw,
            projected_target = round(tp1, 5),
            projected_tp2    = round(tp2, 5),
            projected_tp3    = round(tp3, 5),
            projected_sl     = round(sl,  5),
            confidence       = round(best_conf, 3),
            trend            = trend,
            fib_levels       = base_fib,
            description      = desc,
            wave3_extended   = w3x,
        )

    # ── 3-wave ABC corrective ─────────────────────────────────
    hi_idx, lo_idx = find_swing_points(df, order=_aorder(df))
    pivots_abc = []
    for i in hi_idx[-15:]:
        pivots_abc.append({"index":int(i),"price":float(df["high"].iloc[i]),"type":"high"})
    for i in lo_idx[-15:]:
        pivots_abc.append({"index":int(i),"price":float(df["low"].iloc[i]), "type":"low"})
    pivots_abc.sort(key=lambda x: x["index"])
    pivots_abc = _clean_pivots(pivots_abc)

    best_abc, best_ac = None, 0.0
    for i in range(len(pivots_abc)-2):
        cand   = pivots_abc[i:i+3]
        types  = [c["type"] for c in cand]
        prices = [c["price"] for c in cand]
        if types[0]==types[1] or types[1]==types[2]: continue
        a_sz = _sz(prices[0],prices[1])
        b_sz = _sz(prices[1],prices[2])
        if a_sz == 0: continue
        br   = b_sz/a_sz
        conf = 0.0
        if   0.50 <= br <= 0.618: conf = 0.72   # Ideal B retrace
        elif 0.382 <= br <= 0.786: conf = 0.55
        elif br < 1.0:             conf = 0.35
        if conf > best_ac:
            best_ac  = conf
            best_abc = (cand, "bearish" if types[0]=="high" else "bullish", a_sz)

    if best_abc and best_ac > 0.30:
        cand, trend, a_sz = best_abc
        prices = [c["price"] for c in cand]
        sign   = 1 if trend=="bearish" else -1
        c_tp1  = prices[1] + sign * a_sz * 1.000
        c_tp2  = prices[1] + sign * a_sz * 1.272
        c_tp3  = prices[1] + sign * a_sz * 1.618
        fib    = calculate_fibonacci_levels(prices[0],prices[1],"down" if trend=="bearish" else "up")
        return ElliottWaveResult(
            pattern_type     = "3-wave-ABC",
            wave_points      = [
                WavePoint(cand[0]["index"],prices[0],"A","corrective",trend),
                WavePoint(cand[1]["index"],prices[1],"B","corrective",trend),
                WavePoint(cand[2]["index"],prices[2],"C","corrective",trend),
            ],
            current_wave     = "C",
            projected_target = round(c_tp1,5),
            projected_tp2    = round(c_tp2,5),
            projected_tp3    = round(c_tp3,5),
            projected_sl     = round(prices[0],5),
            confidence       = best_ac,
            trend            = trend,
            fib_levels       = fib,
            description      = (
                f"ABC corrective ({trend}) · Conf {best_ac*100:.0f}%"
                f" · TP1={round(c_tp1,5)}"
            ),
        )

    # ── Fallback ──────────────────────────────────────────────
    closes = df["close"].values
    trend  = "bullish" if closes[-1] > closes[max(0,len(closes)-20)] else "bearish"
    rhi    = float(df["high"].iloc[-30:].max())
    rlo    = float(df["low"].iloc[-30:].min())
    fib    = calculate_fibonacci_levels(rlo, rhi, "up" if trend=="bullish" else "down")
    atr    = float(df["close"].diff().abs().iloc[-14:].mean()) * 14
    cp2    = float(closes[-1])
    s      = 1 if trend=="bullish" else -1
    tp1, tp2, tp3 = cp2+s*atr, cp2+s*atr*1.618, cp2+s*atr*2.618

    return ElliottWaveResult(
        pattern_type     = "unknown",
        wave_points      = [],
        current_wave     = "?",
        projected_target = round(tp1,5),
        projected_tp2    = round(tp2,5),
        projected_tp3    = round(tp3,5),
        projected_sl     = None,
        confidence       = 0.25,
        trend            = trend,
        fib_levels       = fib,
        description      = f"No clear EW pattern — {trend} bias. ATR projections.",
    )
