"""
modules/gemini_ai.py
Gemini AI Signal Confirmation Engine
- 7 API key rotation (free tier friendly)
- Analyses EW + SMC signals and gives BUY/SELL/SKIP verdict
- Rate limit aware — auto-rotates to next key on 429
"""

import streamlit as st
import requests
import json
import time
from datetime import datetime
import pytz

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

# ── Gemini Model ─────────────────────────────────────────────────────────────
GEMINI_MODEL = "gemini-3-flash-preview"          # Free tier, fast
GEMINI_URL   = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent?key="
)

# ── Key Rotation State ────────────────────────────────────────────────────────
_KEY_STATE_KEY = "_gemini_key_state"   # st.session_state key


def _get_api_keys() -> list[str]:
    """Load API keys from Streamlit secrets."""
    keys = []
    try:
        # Support both list format and individual keys
        if "gemini_api_keys" in st.secrets:
            raw = st.secrets["gemini_api_keys"]
            if isinstance(raw, str):
                keys = [k.strip() for k in raw.split(",") if k.strip()]
            else:
                keys = list(raw)
        else:
            # Fallback: individual keys gemini_key_1 … gemini_key_7
            for i in range(1, 8):
                k = st.secrets.get(f"gemini_key_{i}", "")
                if k:
                    keys.append(k)
    except Exception:
        pass
    return keys


def _init_key_state(keys: list[str]):
    """Initialise rotation state in session."""
    if _KEY_STATE_KEY not in st.session_state:
        st.session_state[_KEY_STATE_KEY] = {
            "index":        0,
            "usage":        {k: 0 for k in keys},
            "errors":       {k: 0 for k in keys},
            "last_used":    {k: 0.0 for k in keys},
            "skip_until":   {k: 0.0 for k in keys},
        }


def _next_key(keys: list[str]) -> str | None:
    """
    Pick the next available API key using round-robin rotation.
    Skips keys that are rate-limited (skip_until > now).
    Returns None if all keys are exhausted.
    """
    if not keys:
        return None

    _init_key_state(keys)
    state = st.session_state[_KEY_STATE_KEY]
    now   = time.time()

    # Try each key starting from current index
    for _ in range(len(keys)):
        idx = state["index"] % len(keys)
        key = keys[idx]
        state["index"] = (idx + 1) % len(keys)

        if state["skip_until"].get(key, 0) < now:
            state["usage"][key] = state["usage"].get(key, 0) + 1
            state["last_used"][key] = now
            return key

    return None   # All keys rate-limited


def _mark_rate_limited(key: str, retry_after: int = 60):
    """Mark a key as rate-limited for retry_after seconds."""
    if _KEY_STATE_KEY not in st.session_state:
        return
    state = st.session_state[_KEY_STATE_KEY]
    state["skip_until"][key]  = time.time() + retry_after
    state["errors"][key]      = state["errors"].get(key, 0) + 1


# ══════════════════════════════════════════════════════
# CORE API CALL
# ══════════════════════════════════════════════════════

def _call_gemini(prompt: str, max_tokens: int = 512) -> str | None:
    """
    Call Gemini API with automatic key rotation.
    Returns text response or None on failure.
    """
    keys = _get_api_keys()
    if not keys:
        return None

    # Try up to len(keys) times with different keys
    for attempt in range(len(keys)):
        key = _next_key(keys)
        if not key:
            break   # All keys exhausted

        try:
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "maxOutputTokens": max_tokens,
                    "temperature":     0.2,
                    "topP":            0.8,
                },
                "safetySettings": [
                    {"category": "HARM_CATEGORY_HARASSMENT",       "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_HATE_SPEECH",      "threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT","threshold": "BLOCK_NONE"},
                    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT","threshold": "BLOCK_NONE"},
                ],
            }

            resp = requests.post(
                GEMINI_URL + key,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=15,
            )

            if resp.status_code == 200:
                data = resp.json()
                text = (
                    data.get("candidates", [{}])[0]
                        .get("content", {})
                        .get("parts", [{}])[0]
                        .get("text", "")
                )
                return text.strip()

            elif resp.status_code == 429:
                retry_after = int(resp.headers.get("Retry-After", 60))
                _mark_rate_limited(key, retry_after)
                continue   # Try next key

            else:
                _mark_rate_limited(key, 30)
                continue

        except requests.Timeout:
            _mark_rate_limited(key, 20)
            continue
        except Exception:
            continue

    return None


# ══════════════════════════════════════════════════════
# SIGNAL CONFIRMATION
# ══════════════════════════════════════════════════════

def build_signal_prompt(signal_data: dict) -> str:
    """Build a structured prompt for Gemini to analyse a trade signal."""
    return f"""You are a professional Forex trading analyst specialising in Elliott Wave Theory and Smart Money Concepts (SMC).

Analyse this trade signal and give a confirmation verdict.

## Signal Details
- Symbol:     {signal_data.get('symbol')}
- Direction:  {signal_data.get('direction')}
- Strategy:   {signal_data.get('strategy', '').upper()} ({signal_data.get('timeframe')})
- Entry:      {signal_data.get('entry_price')}
- Stop Loss:  {signal_data.get('sl_price')}
- Take Profit:{signal_data.get('tp_price')}
- Risk/Reward:{signal_data.get('risk_reward')}
- Score:      {signal_data.get('probability_score')}%

## Confluences Detected
{chr(10).join('• ' + c for c in signal_data.get('confluences', []))}

## EW Analysis
- Pattern: {signal_data.get('ew_pattern')}

## SMC Bias
{signal_data.get('smc_bias')}

## Task
Respond ONLY in this exact JSON format (no markdown, no extra text):
{{
  "verdict": "CONFIRM" | "REJECT" | "CAUTION",
  "confidence": 0-100,
  "reason": "1-2 sentence explanation",
  "risk_note": "one specific risk to watch",
  "best_entry": "IMMEDIATE" | "WAIT_FOR_PULLBACK" | "WAIT_FOR_RETEST"
}}"""


@st.cache_data(ttl=300, show_spinner=False)
def get_gemini_confirmation(
    symbol: str,
    direction: str,
    entry_price: float,
    sl_price: float,
    tp_price: float,
    risk_reward: float,
    probability_score: int,
    strategy: str,
    timeframe: str,
    ew_pattern: str,
    smc_bias: str,
    confluences_str: str,   # join confluences list to str for cache key
) -> dict:
    """
    Get Gemini AI confirmation for a trade signal.
    Cached 5 minutes per unique signal.
    Returns dict with verdict, confidence, reason, risk_note, best_entry.
    """
    signal_data = {
        "symbol":            symbol,
        "direction":         direction,
        "entry_price":       entry_price,
        "sl_price":          sl_price,
        "tp_price":          tp_price,
        "risk_reward":       risk_reward,
        "probability_score": probability_score,
        "strategy":          strategy,
        "timeframe":         timeframe,
        "ew_pattern":        ew_pattern,
        "smc_bias":          smc_bias,
        "confluences":       confluences_str.split("|"),
    }

    prompt   = build_signal_prompt(signal_data)
    response = _call_gemini(prompt, max_tokens=300)

    if not response:
        return _fallback_verdict(probability_score)

    # Parse JSON response
    try:
        # Strip markdown fences if present
        clean = response.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = json.loads(clean)
        # Validate required fields
        result.setdefault("verdict",    "CAUTION")
        result.setdefault("confidence", probability_score)
        result.setdefault("reason",     "Analysis complete.")
        result.setdefault("risk_note",  "Always use proper risk management.")
        result.setdefault("best_entry", "IMMEDIATE")
        result["ai_powered"] = True
        return result
    except Exception:
        return _fallback_verdict(probability_score)


def _fallback_verdict(score: int) -> dict:
    """Rule-based fallback when Gemini API is unavailable."""
    if score >= 70:
        verdict    = "CONFIRM"
        confidence = score
        reason     = "High confluence score — EW + SMC alignment strong."
    elif score >= 50:
        verdict    = "CAUTION"
        confidence = score
        reason     = "Moderate confluence — wait for additional confirmation."
    else:
        verdict    = "REJECT"
        confidence = score
        reason     = "Low confluence score — insufficient signal strength."

    return {
        "verdict":    verdict,
        "confidence": confidence,
        "reason":     reason,
        "risk_note":  "Always use proper position sizing and risk management.",
        "best_entry": "WAIT_FOR_PULLBACK" if score < 70 else "IMMEDIATE",
        "ai_powered": False,
    }


# ══════════════════════════════════════════════════════
# MARKET SENTIMENT  (bonus feature)
# ══════════════════════════════════════════════════════

@st.cache_data(ttl=600, show_spinner=False)
def get_market_sentiment(symbol: str, trend: str, pattern: str, smc_bias: str) -> str:
    """Get a brief Gemini market sentiment summary for a symbol."""
    prompt = f"""You are a Forex market analyst. Give a 2-3 sentence market outlook for {symbol}.

Current data:
- Trend: {trend}
- EW Pattern: {pattern}  
- SMC Bias: {smc_bias}

Be concise and specific. No disclaimers. Plain text only."""

    result = _call_gemini(prompt, max_tokens=150)
    return result or f"{symbol} — {trend} trend with {pattern} pattern detected."


# ══════════════════════════════════════════════════════
# KEY STATUS (for Admin panel display)
# ══════════════════════════════════════════════════════

def get_key_rotation_status() -> dict:
    """Return current API key rotation stats for admin display."""
    keys  = _get_api_keys()
    now   = time.time()

    if not keys:
        return {"total_keys": 0, "available": 0, "keys": []}

    _init_key_state(keys)
    state = st.session_state[_KEY_STATE_KEY]

    key_info = []
    available = 0
    for i, k in enumerate(keys):
        skip_until = state["skip_until"].get(k, 0)
        is_avail   = skip_until < now
        if is_avail:
            available += 1
        key_info.append({
            "index":     i + 1,
            "key_hint":  f"...{k[-6:]}",
            "available": is_avail,
            "usage":     state["usage"].get(k, 0),
            "errors":    state["errors"].get(k, 0),
            "cooldown":  max(0, int(skip_until - now)),
        })

    return {
        "total_keys": len(keys),
        "available":  available,
        "keys":       key_info,
    }
