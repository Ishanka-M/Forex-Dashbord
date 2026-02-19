"""
Combine Engine: AI verification and deep analysis for trades.
Receives all required data as arguments; no dependency on Streamlit or external state.
"""

import puter
import google.generativeai as genai
import re
from typing import Tuple, List, Dict, Any

def ai_verify_trade(
    trade: Dict[str, Any],
    news_str: str,
    live_price: float,
    gemini_keys: List[str]
) -> Tuple[bool, str, str]:
    """
    Use hybrid AI to verify if a trade is likely profitable.
    Returns (is_profitable: bool, verification_message: str, provider: str)
    """
    pair = trade['pair']
    prompt = f"""
    You are an expert forex and crypto trader. Evaluate the following trade setup and determine if it is likely to be profitable.
    
    **Trade Details:**
    - Asset: {pair}
    - Timeframe: {trade['tf']}
    - Direction: {trade['dir']}
    - Entry Price: {trade['entry']:.5f}
    - Stop Loss: {trade['sl']:.5f}
    - Take Profit: {trade['tp']:.5f}
    - Confidence Score (algo): {trade['conf']}%
    - Current Live Price: {live_price:.5f}
    
    **Recent News Headlines:**
    {news_str}
    
    **Task:**
    Based on the technical setup and news sentiment, answer with a simple YES or NO: Is this trade likely to hit its take profit before stop loss?
    Provide a brief one-sentence reason for your answer.
    
    **Output Format:**
    YES/NO: [reason]
    """
    
    response_text = ""
    provider_name = ""
    
    # Try Gemini keys
    for idx, key in enumerate(gemini_keys):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            response_text = response.text
            provider_name = f"Gemini (Key {idx+1})"
            break
        except Exception:
            continue
    
    # Fallback to Puter
    if not response_text:
        try:
            puter_resp = puter.ai.chat(prompt)
            response_text = puter_resp.message.content
            provider_name = "Puter AI"
        except Exception:
            return False, "AI verification failed", "Error"
    
    # Parse response
    is_profitable = False
    verification_msg = response_text.strip()
    if response_text.upper().startswith("YES"):
        is_profitable = True
    elif response_text.upper().startswith("NO"):
        is_profitable = False
    else:
        # Try to find YES/NO anywhere
        if "YES" in response_text.upper():
            is_profitable = True
        elif "NO" in response_text.upper():
            is_profitable = False
        else:
            is_profitable = False  # default
    
    return is_profitable, verification_msg, provider_name


def get_deep_hybrid_analysis(
    trade: Dict[str, Any],
    news_str: str,
    live_price: float,
    gemini_keys: List[str]
) -> Tuple[str, str]:
    """
    Run deep analysis using Gemini + Puter for a scanner trade.
    Returns (analysis_text, provider_name)
    """
    pair = trade['pair']
    prompt = f"""
    Act as a Senior Hedge Fund Risk Manager & Technical Analyst.
    Perform a deep analysis of the following trade setup:
    
    **Asset:** {pair}
    **Timeframe:** {trade['tf']}
    **Direction:** {trade['dir']}
    **Entry:** {trade['entry']:.5f}
    **Stop Loss:** {trade['sl']:.5f}
    **Take Profit:** {trade['tp']:.5f}
    **Confidence:** {trade['conf']}%
    **Current Live Price:** {live_price:.5f}
    
    **Recent News Headlines:**
    {news_str}
    
    **Task:**
    1. Evaluate the risk-reward ratio of this trade.
    2. Check if the current price is near entry and if it's a good moment to enter.
    3. Provide a detailed analysis in SINHALA (use English for technical terms).
    4. Suggest any adjustments to SL/TP based on recent price action.
    5. Give a short-term price forecast (next 5-10 candles) in terms of direction and approximate targets.
    
    **FINAL OUTPUT FORMAT (STRICT):**
    [Sinhala Analysis]
    
    RISK:REWARD = x:y
    FORECAST: [Brief forecast description]
    """
    
    response_text = ""
    provider_name = ""
    
    # Try Gemini
    for idx, key in enumerate(gemini_keys):
        try:
            genai.configure(api_key=key)
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            response_text = response.text
            provider_name = f"Gemini 1.5 Flash (Key {idx+1}) ⚡"
            break
        except Exception:
            continue
    
    # Fallback to Puter
    if not response_text:
        try:
            puter_resp = puter.ai.chat(prompt)
            response_text = puter_resp.message.content
            provider_name = "Puter AI (Fallback) 🔵"
        except Exception:
            return "Deep analysis failed. Please try again.", "Error"
    
    return response_text, provider_name
