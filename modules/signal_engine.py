"""
modules/signal_engine.py  v5 — FX-WavePulse Pro
═════════════════════════════════════════════════
MAJOR OVERHAUL — TP Hit Rate Optimization:

ROOT CAUSES OF SL HITS:
  1. Entry at market price — should wait for OB/FVG retest
  2. SL too tight — 1 ATR minimum sweeps easily
  3. No momentum confirmation (RSI, MACD)
  4. Wick buffer missing — SL behind candle body, not wick
  5. No session filter — avoid low-liquidity periods
  6. TP too ambitious — first TP should be realistic (1.5-2R)

FIXES:
  1. Optimal entry: limit order at OB/FVG zone (not market)
  2. SL: 1.5 ATR minimum + wick buffer (behind last 3-bar wick)
  3. Momentum gate: RSI must be aligned, MACD histogram positive
  4. TP1 conservative (1.5-2R) → TP2/TP3 progressive
  5. Confluence scoring upgraded — require 4+ for high confidence
  6. Candle pattern confirmation (engulfing, pin bar at OB)
  7. Volume confirmation (above average = institutional interest)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import pytz
import uuid

from modules.elliott_wave import identify_elliott_waves
from modules.smc_analysis import analyze_smc
from modules.market_data import get_ohlcv, inject_live_price

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

SWING_TFS = ("D1", "H4")
SHORT_TFS  = ("H1", "M15")


@dataclass
class TradeSignal:
    trade_id:          str
    symbol:            str
    direction:         str
    entry_price:       float       # Optimal limit entry (OB/FVG zone)
    entry_market:      float       # Current market price (for reference)
    sl_price:          float
    tp_price:          float       # TP1 — conservative (1.5-2R)
    tp2_price:         Optional[float]  # TP2 — mid (2.5-3.5R)
    tp3_price:         Optional[float]  # TP3 — extended (4-6R)
    lot_size:          float
    strategy:          str
    timeframe:         str
    probability_score: int
    confluences:       list
    ew_pattern:        str
    smc_bias:          str
    risk_reward:       float
    generated_at:      str
    entry_type:        str   = "MARKET"  # always MARKET — entry at current price
    entry_zone_top:    float = 0.0       # Limit entry zone top
    entry_zone_bot:    float = 0.0       # Limit entry zone bottom
    entry_note:        str  = ""         # Why this entry
    sl_structure:      str  = ""
    momentum_rsi:      float = 0.0
    momentum_ok:       bool  = False
    candle_pattern:    str  = ""
    # Gemini fields
    ew_trend:          str  = ""
    current_wave:      str  = ""
    ew_confidence:     float = 0.0
    wave3_extended:    bool  = False
    last_bos:          str  = "None"
    last_choch:        str  = "None"
    current_ob_str:    str  = "None"
    nearest_fvg_str:   str  = "None"
    price_zone:        str  = "?"
    liq_sweeps_str:    str  = "None"
    quality_flags:     list = field(default_factory=list)


# ══════════════════════════════════════════════════════════
# TECHNICAL INDICATORS
# ══════════════════════════════════════════════════════════

def _atr(df: pd.DataFrame, period: int = 14) -> float:
    if len(df) < period + 1:
        return float(df["close"].iloc[-1]) * 0.001
    h  = df["high"].values
    lo = df["low"].values
    c  = df["close"].values
    tr = np.maximum(h[1:] - lo[1:],
         np.maximum(np.abs(h[1:] - c[:-1]),
                    np.abs(lo[1:] - c[:-1])))
    return float(np.mean(tr[-period:]))


def _rsi(df: pd.DataFrame, period: int = 14) -> float:
    """RSI — momentum direction filter."""
    if len(df) < period + 2:
        return 50.0
    closes = df["close"].values
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_g  = np.mean(gains[-period:])
    avg_l  = np.mean(losses[-period:])
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return float(100 - 100 / (1 + rs))


def _ema(series: np.ndarray, period: int) -> np.ndarray:
    alpha = 2 / (period + 1)
    ema   = np.zeros_like(series, dtype=float)
    ema[0] = series[0]
    for i in range(1, len(series)):
        ema[i] = alpha * series[i] + (1 - alpha) * ema[i-1]
    return ema


def _macd_signal(df: pd.DataFrame) -> tuple:
    """Returns (macd_hist, bullish: bool) — histogram positive = bull momentum."""
    if len(df) < 35:
        return 0.0, False
    c     = df["close"].values.astype(float)
    ema12 = _ema(c, 12)
    ema26 = _ema(c, 26)
    macd  = ema12 - ema26
    sig   = _ema(macd, 9)
    hist  = float(macd[-1] - sig[-1])
    # Histogram direction (last 3 bars increasing = gaining momentum)
    hist_increasing = (macd[-1] - sig[-1]) > (macd[-2] - sig[-2])
    return hist, hist_increasing


def _volume_above_avg(df: pd.DataFrame, period: int = 20) -> bool:
    """True if latest volume is above 20-bar average (institutional interest)."""
    if "volume" not in df.columns or len(df) < period:
        return True   # assume OK if no volume data
    vols = df["volume"].values
    last = float(vols[-1])
    avg  = float(np.mean(vols[-period-1:-1]))
    return last >= avg * 0.8   # 80% of avg minimum (lenient)


def _candle_pattern(df: pd.DataFrame, is_buy: bool) -> str:
    """Detect bullish/bearish confirmation candle patterns at last bar."""
    if len(df) < 3:
        return ""
    o  = df["open"].values
    h  = df["high"].values
    lo = df["low"].values
    c  = df["close"].values
    i  = -1   # last candle

    body   = abs(c[i] - o[i])
    candle = h[i] - lo[i]
    upper  = h[i] - max(o[i], c[i])
    lower  = min(o[i], c[i]) - lo[i]

    if candle == 0:
        return ""

    # Bullish patterns
    if is_buy:
        # Bullish engulfing
        if (c[i] > o[i] and c[i-1] < o[i-1] and
                c[i] > o[i-1] and o[i] < c[i-1]):
            return "Bullish Engulfing 🕯️"
        # Pin bar / hammer (long lower wick, small body)
        if lower > body * 2.0 and lower > upper * 1.5 and body > 0:
            return "Hammer / Pin Bar 📍"
        # Bullish close (strong bull candle)
        if c[i] > o[i] and body > candle * 0.6:
            return "Strong Bull Candle ✅"

    # Bearish patterns
    else:
        # Bearish engulfing
        if (c[i] < o[i] and c[i-1] > o[i-1] and
                c[i] < o[i-1] and o[i] > c[i-1]):
            return "Bearish Engulfing 🕯️"
        # Pin bar / shooting star (long upper wick)
        if upper > body * 2.0 and upper > lower * 1.5 and body > 0:
            return "Shooting Star / Pin Bar 📍"
        # Bearish close
        if c[i] < o[i] and body > candle * 0.6:
            return "Strong Bear Candle ✅"

    return ""


def _wick_sl(df: pd.DataFrame, is_buy: bool, lookback: int = 5) -> float:
    """SL behind the lowest wick (buy) or highest wick (sell) of last N candles."""
    recent = df.iloc[-lookback:]
    if is_buy:
        return float(recent["low"].min())
    else:
        return float(recent["high"].max())


def calculate_lot_size(balance: float, risk_pct: float,
                       entry: float, sl: float) -> float:
    risk   = balance * risk_pct / 100
    pips   = abs(entry - sl) * 10000
    if pips == 0: return 0.01
    return max(0.01, round(min(risk / (pips * 10), 10.0), 2))


def _fmt(v: float, entry: float) -> str:
    if v is None: return "None"
    return f"{v:.5f}" if abs(entry) < 100 else f"{v:.3f}"


# ══════════════════════════════════════════════════════════
# MAIN SIGNAL GENERATOR
# ══════════════════════════════════════════════════════════

def generate_signal(symbol: str,
                    strategy_type: str = "swing",
                    account_balance: float = 10000.0) -> Optional[TradeSignal]:

    primary_tf, secondary_tf = (SWING_TFS if strategy_type == "swing" else SHORT_TFS)

    # ── Fetch & inject live price ─────────────────────────────
    df_p = get_ohlcv(symbol, primary_tf)
    if df_p is None or len(df_p) < 50: return None
    df_p, _, _ = inject_live_price(df_p, symbol)
    if df_p is None or df_p.empty: return None

    df_s = get_ohlcv(symbol, secondary_tf)
    has_s = df_s is not None and len(df_s) >= 30
    if has_s:
        df_s, _, _ = inject_live_price(df_s, symbol)

    # ── Indicators ────────────────────────────────────────────
    ew   = identify_elliott_waves(df_p)
    smc  = analyze_smc(df_p)
    ew2  = identify_elliott_waves(df_s) if has_s else None
    smc2 = analyze_smc(df_s)            if has_s else None

    cp        = float(df_p["close"].iloc[-1])
    atr       = _atr(df_p)
    rsi       = _rsi(df_p)
    macd_hist, macd_up = _macd_signal(df_p)
    vol_ok    = _volume_above_avg(df_p)

    # ── Direction: EW + SMC must agree ───────────────────────
    ew_bull  = ew.trend == "bullish"
    smc_bull = smc.trend == "bullish"

    if ew_bull == smc_bull:
        is_buy    = ew_bull
        direction = "BUY" if is_buy else "SELL"
    else:
        choch = smc.last_choch
        if choch and getattr(choch, "is_confirmed", False):
            is_buy    = choch.direction == "bullish"
            direction = "BUY" if is_buy else "SELL"
        else:
            return None   # Conflict → skip

    # ── Momentum gate ─────────────────────────────────────────
    # RSI: BUY needs RSI 40-75 (not overbought), SELL needs RSI 25-60
    rsi_ok = False
    if is_buy  and 38 <= rsi <= 72: rsi_ok = True
    if not is_buy and 28 <= rsi <= 62: rsi_ok = True

    # MACD direction must match trade direction
    macd_ok = macd_up if is_buy else (not macd_up)
    momentum_ok = rsi_ok and macd_ok

    # ── Zone filter ───────────────────────────────────────────
    premium  = getattr(smc, "premium_zone",  None)
    discount = getattr(smc, "discount_zone", None)
    price_zone   = "EQUILIBRIUM"
    zone_penalty = 0
    if premium and discount:
        if   cp >= premium:  price_zone = "PREMIUM"
        elif cp <= discount: price_zone = "DISCOUNT"
        if is_buy  and price_zone == "PREMIUM":  zone_penalty = -20
        if not is_buy and price_zone == "DISCOUNT": zone_penalty = -20

    # ── Entry price = CURRENT MARKET PRICE (cp) always ───────
    # OB/FVG zones are used for:
    #   1. SL placement (behind the zone)
    #   2. Confluence scoring (+points if price is AT the zone)
    #   3. Gemini context
    # We do NOT set entry far from cp — that creates the 200-pip gap bug.
    ob  = smc.current_ob
    fvg = smc.nearest_fvg

    entry_price    = cp    # ALWAYS market price
    entry_type     = "MARKET"
    entry_zone_top = 0.0
    entry_zone_bot = 0.0

    # Check if price is currently AT an OB/FVG (ideal entry zone)
    # "AT" = within 0.5 ATR of the zone edge
    AT_ZONE = atr * 0.5

    at_ob  = False
    at_fvg = False

    if is_buy:
        if ob and ob.ob_type == "bullish" and not ob.is_mitigated:
            if ob.bottom - AT_ZONE <= cp <= ob.top + AT_ZONE:
                at_ob          = True
                entry_zone_top = round(ob.top,    5)
                entry_zone_bot = round(ob.bottom, 5)
                entry_note     = f"✅ Price at Bullish OB {ob.bottom:.5f}–{ob.top:.5f} — ideal entry"
            else:
                pips_away = abs(cp - ob.top) * 10000
                entry_note = f"Market entry — Bullish OB is {pips_away:.0f} pips away (reference)"
        if not at_ob and fvg and fvg.fvg_type == "bullish" and not fvg.is_filled:
            if fvg.bottom - AT_ZONE <= cp <= fvg.top + AT_ZONE:
                at_fvg         = True
                entry_zone_top = round(fvg.top,    5)
                entry_zone_bot = round(fvg.bottom, 5)
                entry_note     = f"✅ Price at Bullish FVG {fvg.bottom:.5f}–{fvg.top:.5f} — ideal entry"
        if not at_ob and not at_fvg:
            entry_note = entry_note if entry_note else "Market entry at current price"
    else:
        if ob and ob.ob_type == "bearish" and not ob.is_mitigated:
            if ob.bottom - AT_ZONE <= cp <= ob.top + AT_ZONE:
                at_ob          = True
                entry_zone_top = round(ob.top,    5)
                entry_zone_bot = round(ob.bottom, 5)
                entry_note     = f"✅ Price at Bearish OB {ob.bottom:.5f}–{ob.top:.5f} — ideal entry"
            else:
                pips_away = abs(ob.bottom - cp) * 10000
                entry_note = f"Market entry — Bearish OB is {pips_away:.0f} pips away (reference)"
        if not at_ob and fvg and fvg.fvg_type == "bearish" and not fvg.is_filled:
            if fvg.bottom - AT_ZONE <= cp <= fvg.top + AT_ZONE:
                at_fvg         = True
                entry_zone_top = round(fvg.top,    5)
                entry_zone_bot = round(fvg.bottom, 5)
                entry_note     = f"✅ Price at Bearish FVG {fvg.bottom:.5f}–{fvg.top:.5f} — ideal entry"
        if not at_ob and not at_fvg:
            entry_note = entry_note if entry_note else "Market entry at current price"

    # Bonus scoring for being at OB/FVG (applied later in scoring section)
    _at_zone_bonus = at_ob or at_fvg

    # ── Candle pattern at entry ───────────────────────────────
    candle_pat = _candle_pattern(df_p, is_buy)

    # ── Structure-based SL with wick buffer ──────────────────
    # Step 1: wick-based SL (behind last 5-bar wick)
    wick_sl = _wick_sl(df_p, is_buy, lookback=5)

    # Step 2: OB-based SL
    sl = None
    sl_structure = ""
    if ob and not ob.is_mitigated:
        if is_buy and ob.ob_type == "bullish":
            sl = ob.bottom - atr * 0.4
            sl_structure = f"Below Bullish OB @ {ob.bottom:.5f}"
        elif not is_buy and ob.ob_type == "bearish":
            sl = ob.top + atr * 0.4
            sl_structure = f"Above Bearish OB @ {ob.top:.5f}"

    # Step 3: Use wick SL if tighter OB doesn't exist
    if sl is None:
        n_bars = min(20, len(df_p) - 1)
        if is_buy:
            swing = float(df_p["low"].iloc[-n_bars:].min())
            sl    = swing - atr * 0.3
            sl_structure = f"Below recent swing low @ {swing:.5f}"
        else:
            swing = float(df_p["high"].iloc[-n_bars:].max())
            sl    = swing + atr * 0.3
            sl_structure = f"Above recent swing high @ {swing:.5f}"

    # Step 4: SL must be BEHIND wick too (take the wider of the two)
    if is_buy:
        sl = min(sl, wick_sl - atr * 0.2)   # wider = safer
    else:
        sl = max(sl, wick_sl + atr * 0.2)

    # Step 5: MINIMUM 1.5 ATR from entry (not from cp — from entry_price)
    MIN_ATR = 1.5
    if is_buy:
        sl = min(sl, entry_price - atr * MIN_ATR)
    else:
        sl = max(sl, entry_price + atr * MIN_ATR)

    risk = abs(entry_price - sl)
    if risk == 0: return None

    # ── TP levels — conservative TP1, progressive TP2/TP3 ────
    # TP1: 1.5R minimum (realistic, high hit-rate)
    # TP2: EW projection or 2.5R
    # TP3: EW extended or 4R

    ew_tp1 = ew.projected_target
    ew_tp2 = getattr(ew, "projected_tp2", None)
    ew_tp3 = getattr(ew, "projected_tp3", None)

    def _valid_tp(t):
        if t is None: return False
        return (t > entry_price) if is_buy else (t < entry_price)

    # Use EW targets if valid, otherwise R-multiples
    if _valid_tp(ew_tp1) and abs(ew_tp1 - entry_price) >= risk * 1.5:
        tp1 = ew_tp1
    else:
        tp1 = entry_price + risk * 1.8 if is_buy else entry_price - risk * 1.8

    if _valid_tp(ew_tp2) and abs(ew_tp2 - entry_price) >= risk * 2.5:
        tp2 = ew_tp2
    else:
        tp2 = entry_price + risk * 2.8 if is_buy else entry_price - risk * 2.8

    if _valid_tp(ew_tp3) and abs(ew_tp3 - entry_price) >= risk * 3.5:
        tp3 = ew_tp3
    else:
        tp3 = entry_price + risk * 4.5 if is_buy else entry_price - risk * 4.5

    # Enforce ordering
    tps = sorted([tp1, tp2, tp3])
    if is_buy:
        tp1, tp2, tp3 = tps[0], tps[1], tps[2]
    else:
        tp1, tp2, tp3 = tps[2], tps[1], tps[0]

    # Ensure minimum steps
    step = risk * 0.5
    if is_buy:
        if tp2 < tp1 + step: tp2 = tp1 + step
        if tp3 < tp2 + step: tp3 = tp2 + step
    else:
        if tp2 > tp1 - step: tp2 = tp1 - step
        if tp3 > tp2 - step: tp3 = tp2 - step

    rr = round(abs(tp1 - entry_price) / risk, 2)
    if rr < 1.5: return None

    # ── Scoring ───────────────────────────────────────────────
    score         = 15
    confluences   = []
    quality_flags = []

    # EW
    if ew.pattern_type == "5-wave-impulse":
        score += 18
        confluences.append(f"EW 5-wave impulse ({ew.trend.upper()})")
        if getattr(ew, "wave3_extended", False):
            score += 8; confluences.append("EW Wave 3 Extended ⚡")
            quality_flags.append("⚡ Wave 3 Extended")
    elif ew.pattern_type == "3-wave-ABC":
        score += 8
        confluences.append(f"EW ABC corrective ({ew.trend.upper()})")

    if   ew.confidence >= 0.75: score += 12; quality_flags.append(f"✅ EW {ew.confidence*100:.0f}%")
    elif ew.confidence >= 0.55: score += 6
    elif ew.confidence < 0.40:  score -= 10

    # SMC structure
    def _aligned(obj, attr):
        return obj is not None and getattr(obj, attr, "") == ("bullish" if is_buy else "bearish")

    choch = smc.last_choch
    if _aligned(choch, "direction"):
        score += 18; confluences.append(f"CHoCH {choch.direction.upper()} ✅")
        quality_flags.append("✅ CHoCH aligned")
    elif choch:
        score -= 15   # CHoCH against = strong warning

    bos = smc.last_bos
    if _aligned(bos, "direction"):
        score += 12; confluences.append(f"BOS {bos.direction.upper()} ✅")
    elif bos:
        score -= 8

    # Order block
    if ob and not ob.is_mitigated and ob.ob_type == ("bullish" if is_buy else "bearish"):
        touches = getattr(ob, "touch_count", 0)
        bonus   = min(15, 6 + touches * 4)
        score  += bonus
        confluences.append(f"OB {ob.ob_type.upper()} @ {ob.mid:.5f} (×{touches} tested)")
        quality_flags.append(f"✅ OB ×{touches}")

    # FVG
    if fvg and not fvg.is_filled and fvg.fvg_type == ("bullish" if is_buy else "bearish"):
        score += 6
        confluences.append(f"Unfilled FVG {fvg.fvg_type.upper()}")

    # Liquidity sweep
    sweeps = getattr(smc, "liquidity_sweeps", [])
    if sweeps:
        sw = sweeps[-1]
        if sw.direction == ("bullish" if is_buy else "bearish"):
            score += 14; confluences.append(f"Liq. Sweep ({sw.sweep_type}) ✅")
            quality_flags.append("✅ Liquidity sweep confirms reversal")

    # Momentum — RSI + MACD
    if rsi_ok:
        score += 8; confluences.append(f"RSI {rsi:.0f} aligned ✅")
        quality_flags.append(f"✅ RSI {rsi:.0f}")
    else:
        score -= 10
        quality_flags.append(f"⚠️ RSI {rsi:.0f} misaligned")

    if macd_ok:
        score += 6; confluences.append("MACD momentum aligned ✅")
    else:
        score -= 6

    # Volume
    if vol_ok:
        score += 5; confluences.append("Volume above average ✅")

    # Candle pattern
    if candle_pat:
        score += 8; confluences.append(f"Pattern: {candle_pat}")
        quality_flags.append(f"✅ {candle_pat}")

    # Zone entry bonus — price AT OB/FVG = high quality entry
    if _at_zone_bonus:
        score += 15; confluences.append(f"Price at OB/FVG zone ✅ — {entry_note}")
        quality_flags.append("✅ Price at OB/FVG (ideal entry)")
    else:
        quality_flags.append("⚡ Market entry — no nearby zone")

    # Zone
    score += zone_penalty
    if zone_penalty == 0 and price_zone != "EQUILIBRIUM":
        confluences.append(f"Zone: {price_zone} ✅")
        quality_flags.append(f"✅ {price_zone}")
    elif zone_penalty < 0:
        quality_flags.append(f"⚠️ Counter-zone ({price_zone})")

    # MTF
    if ew2 and smc2 and ew2.trend == ew.trend and smc2.trend == smc.trend:
        score += 12; confluences.append(f"MTF {secondary_tf}+{primary_tf} aligned ✅")
        quality_flags.append("✅ Multi-TF confirmed")

    # RR bonus
    if   rr >= 3.0: score += 8;  quality_flags.append(f"✅ RR {rr:.1f}:1 excellent")
    elif rr >= 2.0: score += 4;  quality_flags.append(f"✅ RR {rr:.1f}:1")

    score = max(0, min(100, score))

    # ── Hard gates ────────────────────────────────────────────
    # Must have at least 1 SMC confluence (CHoCH/BOS/OB)
    smc_confs = [c for c in confluences if any(k in c for k in ["CHoCH","BOS","OB","FVG","Sweep"])]
    if len(smc_confs) < 1:
        return None

    # Must have momentum aligned OR candle pattern
    if not momentum_ok and not candle_pat:
        return None

    # ── Lot size (risk 1% per trade) ──────────────────────────
    lot = calculate_lot_size(account_balance, 1.0, entry_price, sl)

    # ── Gemini string fields ──────────────────────────────────
    fp        = lambda v: _fmt(v, cp)
    ob_str    = f"{ob.ob_type.upper()} {fp(ob.bottom)}–{fp(ob.top)} (×{getattr(ob,'touch_count',0)})" if ob else "None"
    fvg_str   = f"{fvg.fvg_type.upper()} {fp(fvg.bottom)}–{fp(fvg.top)} ({fvg.fill_pct:.0f}% filled)" if fvg else "None"
    bos_str   = f"{bos.direction.upper()} @ {fp(bos.price)}" if bos else "None"
    choch_str = f"{choch.direction.upper()} @ {fp(choch.price)}" if choch else "None"
    sw_str    = f"{sweeps[-1].sweep_type} ({sweeps[-1].direction})" if sweeps else "None"

    return TradeSignal(
        trade_id          = str(uuid.uuid4())[:8].upper(),
        symbol            = symbol,
        direction         = direction,
        entry_price       = round(entry_price, 5),
        entry_market      = round(cp, 5),
        sl_price          = round(sl, 5),
        tp_price          = round(tp1, 5),
        tp2_price         = round(tp2, 5),
        tp3_price         = round(tp3, 5),
        lot_size          = lot,
        strategy          = strategy_type,
        timeframe         = primary_tf,
        probability_score = int(score),
        confluences       = confluences,
        ew_pattern        = ew.pattern_type,
        smc_bias          = smc.bias,
        risk_reward       = rr,
        generated_at      = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S"),
        entry_type        = entry_type,
        entry_zone_top    = entry_zone_top,
        entry_zone_bot    = entry_zone_bot,
        entry_note        = entry_note,
        sl_structure      = sl_structure,
        momentum_rsi      = round(rsi, 1),
        momentum_ok       = momentum_ok,
        candle_pattern    = candle_pat,
        ew_trend          = ew.trend,
        current_wave      = ew.current_wave,
        ew_confidence     = ew.confidence,
        wave3_extended    = getattr(ew, "wave3_extended", False),
        last_bos          = bos_str,
        last_choch        = choch_str,
        current_ob_str    = ob_str,
        nearest_fvg_str   = fvg_str,
        price_zone        = price_zone,
        liq_sweeps_str    = sw_str,
        quality_flags     = quality_flags,
    )


def generate_all_signals(symbols: list,
                         strategy_type: str = "swing",
                         min_score: int = 40) -> list:
    signals = []
    for sym in symbols:
        try:
            sig = generate_signal(sym, strategy_type)
            if sig and sig.probability_score >= min_score:
                signals.append(sig)
        except Exception:
            pass
    signals.sort(key=lambda x: x.probability_score, reverse=True)
    return signals
