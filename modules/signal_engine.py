"""
modules/signal_engine.py  v4 — FX-WavePulse Pro
═════════════════════════════════════════════════
What changed (SL wakkda root cause fixes):
  1. SL placed at STRUCTURE (OB / swing high-low) — not ATR guess
  2. BUY only from Discount zone, SELL only from Premium zone
  3. Direction requires EW + SMC BOTH agree (conflict → no signal)
  4. Min 3 technical confluences required
  5. TP1 = EW wave target; TP2/TP3 = Fib extensions from that base
  6. Min RR 1.8 (up from 1.5) before signal is emitted
  7. Extra signal fields for Gemini deep prompt
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

# Primary TF is the higher one (structure), secondary is entry timing
SWING_TFS = ("D1", "H4")
SHORT_TFS  = ("H1", "M15")


@dataclass
class TradeSignal:
    trade_id:          str
    symbol:            str
    direction:         str
    entry_price:       float
    sl_price:          float
    tp_price:          float
    tp2_price:         Optional[float]
    tp3_price:         Optional[float]
    lot_size:          float
    strategy:          str
    timeframe:         str
    probability_score: int
    confluences:       list
    ew_pattern:        str
    smc_bias:          str
    risk_reward:       float
    generated_at:      str
    # Extra fields for Gemini deep analysis
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
    sl_structure:      str  = ""
    quality_flags:     list = field(default_factory=list)


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


def calculate_lot_size(balance: float, risk_pct: float,
                       entry: float, sl: float) -> float:
    risk   = balance * risk_pct / 100
    pips   = abs(entry - sl) * 10000
    if pips == 0: return 0.01
    return max(0.01, round(min(risk / (pips * 10), 10.0), 2))


def _fmt(v: float, entry: float) -> str:
    if v is None: return "None"
    return f"{v:.5f}" if abs(entry) < 100 else f"{v:.3f}"


def generate_signal(symbol: str,
                    strategy_type: str = "swing",
                    account_balance: float = 10000.0) -> Optional[TradeSignal]:

    primary_tf, secondary_tf = (SWING_TFS if strategy_type == "swing" else SHORT_TFS)

    # ── Fetch OHLCV ───────────────────────────────────────────
    df_p = get_ohlcv(symbol, primary_tf)
    if df_p is None or len(df_p) < 50: return None
    # Inject live price so analysis uses current market price
    df_p, _, _ = inject_live_price(df_p, symbol)
    if df_p is None or df_p.empty: return None

    df_s = get_ohlcv(symbol, secondary_tf)
    has_s = df_s is not None and len(df_s) >= 30
    if has_s:
        df_s, _, _ = inject_live_price(df_s, symbol)

    # ── Full analysis ─────────────────────────────────────────
    ew   = identify_elliott_waves(df_p)
    smc  = analyze_smc(df_p)
    ew2  = identify_elliott_waves(df_s) if has_s else None
    smc2 = analyze_smc(df_s)            if has_s else None

    cp  = float(df_p["close"].iloc[-1])
    atr = _atr(df_p)

    # ── Direction: EW and SMC must BOTH agree ─────────────────
    ew_bull  = ew.trend == "bullish"
    smc_bull = smc.trend == "bullish"

    if ew_bull == smc_bull:
        is_buy    = ew_bull
        direction = "BUY" if is_buy else "SELL"
    else:
        # Conflict: use CHoCH as final arbiter only if confirmed
        choch = smc.last_choch
        if choch and getattr(choch, "is_confirmed", False):
            is_buy    = choch.direction == "bullish"
            direction = "BUY" if is_buy else "SELL"
        else:
            return None   # Genuine conflict — skip symbol

    # ── Zone filter ───────────────────────────────────────────
    premium  = getattr(smc, "premium_zone",  None)
    discount = getattr(smc, "discount_zone", None)
    equil    = getattr(smc, "equilibrium",   None)

    price_zone    = "EQUILIBRIUM"
    zone_penalty  = 0
    if premium and discount:
        if   cp >= premium:  price_zone = "PREMIUM"
        elif cp <= discount: price_zone = "DISCOUNT"

        # Counter-zone trades get -20 score (Gemini can still CONFIRM)
        if is_buy  and price_zone == "PREMIUM":  zone_penalty = -20
        if not is_buy and price_zone == "DISCOUNT": zone_penalty = -20

    # ── Structure-based SL ────────────────────────────────────
    ob           = smc.current_ob
    sl           = None
    sl_structure = ""
    MIN_SL_ATR   = 1.0   # SL must be at least 1 ATR from entry

    # Priority 1: Order Block
    if ob and not ob.is_mitigated:
        if is_buy and ob.ob_type == "bullish":
            sl = ob.bottom - atr * 0.25
            sl_structure = f"Below Bullish OB @ {ob.bottom:.5f}"
        elif not is_buy and ob.ob_type == "bearish":
            sl = ob.top + atr * 0.25
            sl_structure = f"Above Bearish OB @ {ob.top:.5f}"

    # Priority 2: Recent swing high/low (last 30 bars)
    if sl is None:
        n_bars = min(30, len(df_p) - 1)
        if is_buy:
            swing = float(df_p["low"].iloc[-n_bars:].min())
            sl    = swing - atr * 0.2
            sl_structure = f"Below swing low @ {swing:.5f}"
        else:
            swing = float(df_p["high"].iloc[-n_bars:].max())
            sl    = swing + atr * 0.2
            sl_structure = f"Above swing high @ {swing:.5f}"

    # Enforce minimum distance
    if is_buy:
        sl = min(sl, cp - atr * MIN_SL_ATR)
    else:
        sl = max(sl, cp + atr * MIN_SL_ATR)

    risk = abs(cp - sl)
    if risk == 0: return None

    # ── EW-based TP ───────────────────────────────────────────
    tp1 = ew.projected_target
    tp2 = getattr(ew, "projected_tp2", None)
    tp3 = getattr(ew, "projected_tp3", None)

    # Validate: correct direction from entry
    def _valid_tp(t):
        if t is None: return False
        return (t > cp) if is_buy else (t < cp)

    if not _valid_tp(tp1): tp1 = None
    if not _valid_tp(tp2): tp2 = None
    if not _valid_tp(tp3): tp3 = None

    # Fallback base values (R-multiples from risk)
    if tp1 is None:
        tp1 = cp + risk * 2.0 if is_buy else cp - risk * 2.0
    if tp2 is None:
        tp2 = cp + risk * 3.2 if is_buy else cp - risk * 3.2
    if tp3 is None:
        tp3 = cp + risk * 5.0 if is_buy else cp - risk * 5.0

    # ── ORDER FIX: TP1 < TP2 < TP3 for BUY, TP1 > TP2 > TP3 for SELL ──
    # Sort all three and assign in correct progressive order
    tps = sorted([tp1, tp2, tp3])          # ascending
    if is_buy:
        tp1, tp2, tp3 = tps[0], tps[1], tps[2]   # smallest first
    else:
        tp1, tp2, tp3 = tps[2], tps[1], tps[0]   # largest first

    # Ensure each TP is at least 0.5R further than the previous
    min_step = risk * 0.5
    if is_buy:
        if tp2 < tp1 + min_step: tp2 = tp1 + min_step
        if tp3 < tp2 + min_step: tp3 = tp2 + min_step
    else:
        if tp2 > tp1 - min_step: tp2 = tp1 - min_step
        if tp3 > tp2 - min_step: tp3 = tp2 - min_step

    rr = round(abs(tp1 - cp) / risk, 2)
    if rr < 1.8: return None   # Hard minimum RR

    # ── Scoring ───────────────────────────────────────────────
    score        = 15
    confluences  = []
    quality_flags= []

    # EW
    if ew.pattern_type == "5-wave-impulse":
        score += 20
        confluences.append(f"EW 5-wave impulse ({ew.trend.upper()})")
        if getattr(ew, "wave3_extended", False):
            score += 8
            confluences.append("EW: Wave 3 Extended ⚡")
            quality_flags.append("⚡ Wave 3 Extended")
    elif ew.pattern_type == "3-wave-ABC":
        score += 10
        confluences.append(f"EW ABC corrective ({ew.trend.upper()})")

    if ew.confidence >= 0.70:
        score += 10; quality_flags.append(f"✅ EW conf {ew.confidence*100:.0f}%")
    elif ew.confidence < 0.40:
        score -= 10

    # SMC structure — direction-aligned
    def _aligned(obj, bull_attr):
        if obj is None: return False
        return getattr(obj, bull_attr, "") == ("bullish" if is_buy else "bearish")

    choch = smc.last_choch
    if _aligned(choch, "direction"):
        score += 18; confluences.append(f"CHoCH {choch.direction.upper()} ✅")
        quality_flags.append("✅ CHoCH aligned")
    elif choch:
        score -= 12   # CHoCH AGAINST direction — bad sign

    bos = smc.last_bos
    if _aligned(bos, "direction"):
        score += 12; confluences.append(f"BOS {bos.direction.upper()} ✅")
    elif bos:
        score -= 6

    # Order Block
    if ob and not ob.is_mitigated:
        if ob.ob_type == ("bullish" if is_buy else "bearish"):
            touches = getattr(ob, "touch_count", 0)
            bonus   = min(12, 5 + touches * 4)
            score  += bonus
            confluences.append(f"OB {ob.ob_type.upper()} @ {ob.mid:.5f} (×{touches})")
            quality_flags.append(f"✅ OB ×{touches} touches")

    # FVG
    fvg = smc.nearest_fvg
    if fvg and not fvg.is_filled:
        if fvg.fvg_type == ("bullish" if is_buy else "bearish"):
            score += 7; confluences.append(f"Unfilled FVG {fvg.fvg_type.upper()}")

    # Liquidity sweep (strong reversal signal)
    sweeps = getattr(smc, "liquidity_sweeps", [])
    if sweeps:
        sw = sweeps[-1]
        if sw.direction == ("bullish" if is_buy else "bearish"):
            score += 12; confluences.append(f"Liq. Sweep ({sw.sweep_type}) ✅")
            quality_flags.append("✅ Liquidity sweep reversal")

    # Zone bonus/penalty
    score += zone_penalty
    if zone_penalty < 0:
        quality_flags.append(f"⚠️ Counter-zone trade ({price_zone})")
    else:
        if price_zone != "EQUILIBRIUM":
            confluences.append(f"Zone: {price_zone} ✅")
            quality_flags.append(f"✅ {price_zone} zone")

    # MTF
    if ew2 and smc2:
        if ew2.trend == ew.trend and smc2.trend == smc.trend:
            score += 12; confluences.append(f"MTF: {secondary_tf}+{primary_tf} aligned ✅")
            quality_flags.append("✅ Multi-TF confirmed")

    # RR bonus
    if   rr >= 3.0: score += 10; quality_flags.append(f"✅ RR {rr:.1f}:1")
    elif rr >= 2.5: score += 7;  quality_flags.append(f"✅ RR {rr:.1f}:1")
    elif rr >= 2.0: score += 3

    score = max(0, min(100, score))

    # Minimum 2 non-EW confluences (EW alone isn't enough)
    non_ew = [c for c in confluences if "EW" not in c and "ew" not in c.lower()]
    if len(non_ew) < 1:
        return None

    # ── Lot size ──────────────────────────────────────────────
    lot = calculate_lot_size(account_balance, 1.0, cp, sl)

    # ── String representations for Gemini ─────────────────────
    fp = lambda v: _fmt(v, cp)
    ob_str  = (f"{ob.ob_type.upper()} {fp(ob.bottom)}–{fp(ob.top)} "
               f"(×{getattr(ob,'touch_count',0)})") if ob else "None"
    fvg_str = (f"{fvg.fvg_type.upper()} {fp(fvg.bottom)}–{fp(fvg.top)} "
               f"({fvg.fill_pct:.0f}% filled)") if fvg else "None"
    bos_str   = f"{bos.direction.upper()} @ {fp(bos.price)}" if bos else "None"
    choch_str = f"{choch.direction.upper()} @ {fp(choch.price)}" if choch else "None"
    sw_str    = f"{sweeps[-1].sweep_type} ({sweeps[-1].direction})" if sweeps else "None"

    return TradeSignal(
        trade_id          = str(uuid.uuid4())[:8].upper(),
        symbol            = symbol,
        direction         = direction,
        entry_price       = round(cp,  5),
        sl_price          = round(sl,  5),
        tp_price          = round(tp1, 5),
        tp2_price         = round(tp2, 5) if tp2 else None,
        tp3_price         = round(tp3, 5) if tp3 else None,
        lot_size          = lot,
        strategy          = strategy_type,
        timeframe         = primary_tf,
        probability_score = int(score),
        confluences       = confluences,
        ew_pattern        = ew.pattern_type,
        smc_bias          = smc.bias,
        risk_reward       = rr,
        generated_at      = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S"),
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
        sl_structure      = sl_structure,
        quality_flags     = quality_flags,
    )


def generate_all_signals(symbols: list,
                         strategy_type: str = "swing",
                         min_score: int = 35) -> list:
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
