"""
modules/gemini_ai.py  v4 — FX-WavePulse Pro
════════════════════════════════════════════
• Gemini as PRIMARY signal quality judge
• Deep institutional analysis prompt (EW rules + SMC + zone + news)
• Pre-filter: RR < 1.5 and score < 35 rejected before API call
• Returns: verdict, tp1_probability, sl_quality, position_size,
           partial_close_plan, sl_adjust suggestion, news_sinhala
• 7-key rotation, graceful fallback
"""

import streamlit as st
import requests
import json
import time
import re
from datetime import datetime
import pytz

COLOMBO_TZ   = pytz.timezone("Asia/Colombo")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key="
)
_KS = "_gm_key_state"


# ══ Key rotation ═══════════════════════════════════════════════
def _get_api_keys() -> list:
    """
    Supports Secrets formats:
      1. [gemini_api_keys] section:  gemini_key_1 = "AIza..."
      2. Top-level list:             gemini_api_keys = ["AIza...", ...]
      3. Top-level comma string:     gemini_api_keys = "AIza...,AIza..."
      4. Top-level individual keys:  gemini_key_1 = "AIza..."
    """
    keys = []
    try:
        # Format 1 & 2 & 3: "gemini_api_keys" exists
        if "gemini_api_keys" in st.secrets:
            raw = st.secrets["gemini_api_keys"]
            # Format 1: section with gemini_key_N sub-keys
            if hasattr(raw, "keys"):
                for i in range(1, 10):
                    k = raw.get(f"gemini_key_{i}", "")
                    if k and k.strip(): keys.append(k.strip())
            # Format 2: list
            elif isinstance(raw, (list, tuple)):
                keys = [k.strip() for k in raw if str(k).strip()]
            # Format 3: comma-separated string
            elif isinstance(raw, str):
                keys = [k.strip() for k in raw.split(",") if k.strip()]
        # Format 4: top-level gemini_key_N
        if not keys:
            for i in range(1, 10):
                k = str(st.secrets.get(f"gemini_key_{i}", "") or "").strip()
                if k: keys.append(k)
    except Exception:
        pass
    return keys


def _init_ks(keys):
    if _KS not in st.session_state:
        st.session_state[_KS] = {
            "idx": 0,
            "usage":      {k: 0   for k in keys},
            "errors":     {k: 0   for k in keys},
            "skip_until": {k: 0.0 for k in keys},
        }


def _next_key(keys):
    if not keys: return None
    _init_ks(keys)
    s, now = st.session_state[_KS], time.time()
    for _ in range(len(keys)):
        idx       = s["idx"] % len(keys)
        key       = keys[idx]
        s["idx"]  = (idx + 1) % len(keys)
        if s["skip_until"].get(key, 0) < now:
            s["usage"][key] = s["usage"].get(key, 0) + 1
            return key
    return None


def _rate_limit(key, secs=60):
    if _KS not in st.session_state: return
    s = st.session_state[_KS]
    s["skip_until"][key] = time.time() + secs
    s["errors"][key]     = s["errors"].get(key, 0) + 1


def _clean_json(text: str) -> str:
    text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    m    = re.search(r"\{.*\}", text, re.DOTALL)
    return m.group(0) if m else text


def _call_gemini(prompt: str, max_tokens: int = 700) -> str | None:
    keys = _get_api_keys()
    if not keys: return None
    for _ in range(len(keys)):
        key = _next_key(keys)
        if not key: break
        try:
            r = requests.post(
                GEMINI_URL + key,
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": max_tokens,
                        "temperature": 0.15,
                        "topP": 0.85,
                    },
                    "safetySettings": [
                        {"category": f"HARM_CATEGORY_{c}", "threshold": "BLOCK_NONE"}
                        for c in ["HARASSMENT","HATE_SPEECH",
                                  "SEXUALLY_EXPLICIT","DANGEROUS_CONTENT"]
                    ],
                },
                headers={"Content-Type": "application/json"},
                timeout=20,
            )
            if r.status_code == 200:
                return (r.json()
                          .get("candidates",[{}])[0]
                          .get("content",{})
                          .get("parts",[{}])[0]
                          .get("text","")).strip()
            elif r.status_code == 429:
                _rate_limit(key, int(r.headers.get("Retry-After", 60)))
            else:
                _rate_limit(key, 30)
        except requests.Timeout:
            _rate_limit(key, 20)
        except Exception:
            pass
    return None


# ══ Pre-filter (no API needed) ══════════════════════════════════
def _pre_filter(rr: float, score: int, confluences: list) -> tuple[bool, str]:
    """Hard rules that reject before any Gemini call."""
    if rr < 1.5:
        return False, f"RR {rr:.2f} < 1.5 minimum"
    if score < 35:
        return False, f"Score {score}% too low (< 35%)"
    if len(confluences) < 2:
        return False, f"Only {len(confluences)} confluence(s) — need ≥ 2"
    return True, "ok"


# ══ Deep Analysis Prompt ════════════════════════════════════════
def _build_prompt(sd: dict) -> str:
    confs = "\n".join(f"  • {c}" for c in sd.get("confluences", []))
    now   = datetime.now(COLOMBO_TZ).strftime("%A %d %B %Y, %H:%M LKT")
    return f"""You are an institutional Forex trader — expert in Elliott Wave Theory (EW) and Smart Money Concepts (SMC). Analyse this trade setup critically and decide if it is worth taking.

Date/Time: {now}

━━━ TRADE SETUP ━━━
Pair:      {sd["symbol"]}
Direction: {sd["direction"]}  ({sd["strategy"].upper()} on {sd["timeframe"]})
Entry:     {sd["entry"]}
SL:        {sd["sl"]}   (risk: ~{sd["sl_pips"]} pips)
TP1:       {sd["tp1"]}  ({sd["rr1"]}R)
TP2:       {sd["tp2"]}  ({sd["rr2"]}R)
TP3:       {sd["tp3"]}  ({sd["rr3"]}R)
Score:     {sd["score"]}%

━━━ CONFLUENCES ━━━
{confs}

━━━ ELLIOTT WAVE ━━━
Pattern:     {sd["ew_pattern"]}
Trend:       {sd["ew_trend"]}
Wave:        {sd["wave"]}
EW Conf:     {sd["ew_conf"]}%
Wave3 Ext:   {sd["w3x"]}

━━━ SMART MONEY ━━━
BOS:         {sd["bos"]}
CHoCH:       {sd["choch"]}
Order Block: {sd["ob"]}
FVG:         {sd["fvg"]}
Zone:        {sd["zone"]}
Liq Sweep:   {sd["sweep"]}
SMC Bias:    {sd["smc_bias"][:150]}

━━━ YOUR ANALYSIS ━━━
Answer these questions in your verdict:
1. Does EW wave count support entry NOW (not too early/late)?
2. Are BOS/CHoCH + OB/FVG genuinely aligned with direction?
3. Is price in right zone (BUY from discount, SELL from premium)?
4. Is SL placed BEYOND real structure or just ATR-based?
5. Is TP1 at a logical EW/Fibonacci target?
6. What is the realistic probability TP1 gets hit before SL?
7. Any major news events next 48h for {sd["symbol"]}?

Respond ONLY in this exact JSON (no markdown, no extra text):
{{
  "verdict": "CONFIRM" | "CAUTION" | "REJECT",
  "confidence": 0-100,
  "reason": "2-3 specific sentences about EW + SMC quality",
  "sl_quality": "GOOD" | "TOO_TIGHT" | "TOO_WIDE" | "MISPLACED",
  "tp1_probability": 0-100,
  "best_entry": "IMMEDIATE" | "WAIT_PULLBACK" | "WAIT_OB_RETEST" | "WAIT_FVG_FILL",
  "position_size": "FULL" | "HALF" | "QUARTER" | "SKIP",
  "partial_close": "e.g. Close 50% at TP1, trail rest to TP2",
  "risk_note": "one specific risk for THIS trade",
  "news_impact": true | false,
  "news_sinhala": "1-2 Sinhala sentences about news risk OR empty string",
  "sl_adjust": null | {{"price": 0.00000, "reason": "why"}}
}}

STRICT RULES:
- REJECT if EW trend ≠ SMC bias direction
- REJECT if SL is misplaced (not beyond structure)
- REJECT if score < 40 AND pattern is unknown
- CAUTION if news event detected in next 48h
- CONFIRM only if EW + SMC + zone ALL align
- news_sinhala: impact=true නම් සිංහලෙන් ලියන්න, false නම් "" දෙන්න"""


# ══ Main confirmation ════════════════════════════════════════════
@st.cache_data(ttl=300, show_spinner=False)
def get_gemini_confirmation(
    symbol: str, direction: str,
    entry_price: float, sl_price: float, tp_price: float,
    tp2: float, tp3: float, risk_reward: float,
    probability_score: int, strategy: str, timeframe: str,
    ew_pattern: str, smc_bias: str, confluences_str: str,
    ew_trend: str = "", current_wave: str = "",
    ew_confidence: float = 0.0, wave3_extended: bool = False,
    last_bos: str = "None", last_choch: str = "None",
    current_ob: str = "None", nearest_fvg: str = "None",
    price_zone: str = "?", liq_sweeps: str = "None",
) -> dict:

    confs = [c for c in confluences_str.split("|") if c.strip()] if confluences_str else []

    # Pre-filter
    ok, reason = _pre_filter(risk_reward, probability_score, confs)
    if not ok:
        return _reject(reason)

    # Calculate pip values
    def _pips(a, b):
        diff = abs(a - b)
        return f"{diff * 10000:.1f}" if abs(a) < 100 else f"{diff:.3f}"

    def _rr(tp):
        risk = abs(entry_price - sl_price)
        if risk == 0: return "?"
        return f"{abs(tp - entry_price) / risk:.1f}"

    sd = {
        "symbol":    symbol,   "direction": direction,
        "strategy":  strategy, "timeframe": timeframe,
        "entry":     entry_price, "sl": sl_price,
        "tp1":       tp_price, "tp2": tp2 or "N/A", "tp3": tp3 or "N/A",
        "sl_pips":   _pips(entry_price, sl_price),
        "rr1":       _rr(tp_price),
        "rr2":       _rr(tp2) if tp2 else "?",
        "rr3":       _rr(tp3) if tp3 else "?",
        "score":     probability_score,
        "confluences": confs,
        "ew_pattern":  ew_pattern,  "ew_trend": ew_trend,
        "wave":        current_wave, "ew_conf": f"{ew_confidence*100:.0f}",
        "w3x":         wave3_extended,
        "bos":         last_bos,    "choch":   last_choch,
        "ob":          current_ob,  "fvg":     nearest_fvg,
        "zone":        price_zone,  "sweep":   liq_sweeps,
        "smc_bias":    smc_bias,
    }

    resp = _call_gemini(_build_prompt(sd), max_tokens=700)
    if not resp:
        return _fallback(probability_score)

    try:
        result = json.loads(_clean_json(resp))
        result.setdefault("verdict",          "CAUTION")
        result.setdefault("confidence",       probability_score)
        result.setdefault("reason",           "Analysis complete.")
        result.setdefault("sl_quality",       "GOOD")
        result.setdefault("tp1_probability",  50)
        result.setdefault("best_entry",       "IMMEDIATE")
        result.setdefault("position_size",    "FULL")
        result.setdefault("partial_close",    "Close 50% at TP1, hold for TP2")
        result.setdefault("risk_note",        "Use proper risk management.")
        result.setdefault("news_impact",      False)
        result.setdefault("news_sinhala",     "")
        result.setdefault("sl_adjust",        None)
        result["ai_powered"] = True
        return result
    except Exception:
        return _fallback(probability_score)


# ══ Helpers ═════════════════════════════════════════════════════
def _reject(reason: str) -> dict:
    return {
        "verdict": "REJECT", "confidence": 0, "reason": reason,
        "sl_quality": "?", "tp1_probability": 0,
        "best_entry": "DO_NOT_TRADE", "position_size": "SKIP",
        "partial_close": "", "risk_note": reason,
        "news_impact": False, "news_sinhala": "", "sl_adjust": None,
        "ai_powered": False, "pre_filtered": True,
    }


def _fallback(score: int) -> dict:
    if score >= 70:
        v, r, p, ps = "CONFIRM", "High confluence score.", 65, "FULL"
    elif score >= 50:
        v, r, p, ps = "CAUTION", "Moderate confluence — partial position.", 45, "HALF"
    else:
        v, r, p, ps = "REJECT", "Low score — skip this trade.", 20, "SKIP"
    return {
        "verdict": v, "confidence": score, "reason": r,
        "sl_quality": "GOOD", "tp1_probability": p,
        "best_entry": "WAIT_PULLBACK" if score < 70 else "IMMEDIATE",
        "position_size": ps, "partial_close": "Close 50% at TP1",
        "risk_note": "Gemini offline — rule-based verdict.",
        "news_impact": False, "news_sinhala": "", "sl_adjust": None,
        "ai_powered": False,
    }


# ══ News check ══════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def get_news_impact_alert(symbol: str) -> str | None:
    resp = _call_gemini(
        f'Check major Forex news next 48h for {symbol}.\n'
        f'JSON only: {{"has_news":true/false,"sinhala_alert":"text or empty"}}',
        max_tokens=150,
    )
    if not resp: return None
    try:
        d = json.loads(_clean_json(resp))
        return d.get("sinhala_alert") or None if d.get("has_news") else None
    except Exception:
        return None


# ══ Market sentiment ════════════════════════════════════════════
@st.cache_data(ttl=600, show_spinner=False)
def get_market_sentiment(symbol: str, trend: str, pattern: str, smc_bias: str) -> str:
    resp = _call_gemini(
        f"2-3 sentence Forex outlook for {symbol}.\n"
        f"Trend:{trend} EW:{pattern} SMC:{smc_bias[:80]}\nPlain text only.",
        max_tokens=150,
    )
    return resp or f"{symbol} — {trend} bias, {pattern} pattern."


# ══ Admin key status ════════════════════════════════════════════
def get_key_rotation_status() -> dict:
    keys = _get_api_keys()
    now  = time.time()
    if not keys: return {"total_keys": 0, "available": 0, "keys": []}
    _init_ks(keys)
    s = st.session_state[_KS]
    avail, info = 0, []
    for i, k in enumerate(keys):
        su = s["skip_until"].get(k, 0)
        ok = su < now
        if ok: avail += 1
        info.append({
            "index": i+1, "key_hint": f"...{k[-6:]}",
            "available": ok, "usage": s["usage"].get(k, 0),
            "errors": s["errors"].get(k, 0),
            "cooldown": max(0, int(su - now)),
        })
    return {"total_keys": len(keys), "available": avail, "keys": info}
