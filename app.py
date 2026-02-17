import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Puter AI for Fallback
import google.generativeai as genai # Gemini AI
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, time as dt_time
import time
import re
import numpy as np
import requests
import urllib.parse
import xml.etree.ElementTree as ET

# --- 1. SETUP & STYLE ---
st.set_page_config(page_title="Infinite System v15.0 (Ultimate Hybrid)", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    /* --- ANIMATIONS & GLOBAL STYLES --- */
    @keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }
    @keyframes pulse-green { 0% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0.7); } 70% { box-shadow: 0 0 15px 15px rgba(0, 255, 0, 0); } 100% { box-shadow: 0 0 0 0 rgba(0, 255, 0, 0); } }
    @keyframes pulse-red { 0% { box-shadow: 0 0 0 0 rgba(255, 75, 75, 0.7); } 70% { box-shadow: 0 0 15px 15px rgba(255, 75, 75, 0); } 100% { box-shadow: 0 0 0 0 rgba(255, 75, 75, 0); } }
    @keyframes gold-glow { 0% { border-color: #ffd700; box-shadow: 0 0 5px #ffd700; } 50% { border-color: #ffaa00; box-shadow: 0 0 20px #ffaa00; } 100% { border-color: #ffd700; box-shadow: 0 0 5px #ffd700; } }

    .stApp { animation: fadeIn 0.8s ease-out forwards; }

    /* --- ALERT PANELS --- */
    .high-prob-alert {
        background: linear-gradient(135deg, #1a1a1a, #2d2d2d);
        border: 2px solid #ffd700;
        border-radius: 15px;
        padding: 20px;
        margin-bottom: 20px;
        animation: gold-glow 2s infinite;
        text-align: center;
    }
    .high-prob-title { color: #ffd700; font-size: 24px; font-weight: bold; text-transform: uppercase; letter-spacing: 2px; }
    .high-prob-pair { color: #ffffff; font-size: 32px; font-weight: 900; }
    .high-prob-desc { color: #cccccc; font-size: 16px; margin-top: 5px; }

    /* --- TEXT COLORS --- */
    .price-up { color: #00ff00; font-size: 26px; font-weight: 800; text-shadow: 0 0 10px rgba(0, 255, 0, 0.5); }
    .price-down { color: #ff4b4b; font-size: 26px; font-weight: 800; text-shadow: 0 0 10px rgba(255, 75, 75, 0.5); }
    
    /* --- BOXES --- */
    .entry-box { 
        background: rgba(0, 212, 255, 0.1);
        border: 2px solid #00d4ff; 
        padding: 20px; border-radius: 15px; margin-top: 15px; 
        color: white; backdrop-filter: blur(10px);
        box-shadow: 0 0 20px rgba(0, 212, 255, 0.2);
        transition: transform 0.3s;
    }
    .entry-box:hover { transform: scale(1.01); }
    
    .trade-metric { 
        background: linear-gradient(145deg, #1e1e1e, #2a2a2a);
        border: 1px solid #444; 
        border-radius: 12px; padding: 15px; text-align: center; transition: all 0.3s ease;
    }
    .trade-metric:hover { transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.5); border-color: #00d4ff; }
    .trade-metric h4 { margin: 0; color: #aaa; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }
    .trade-metric h2 { margin: 5px 0 0 0; color: #fff; font-size: 22px; font-weight: bold; }
    
    /* --- NEWS CARDS --- */
    .news-card { 
        background: #1e1e1e;
        padding: 12px; margin-bottom: 10px; 
        border-radius: 8px; transition: all 0.3s ease; border-right: 1px solid #333;
    }
    .news-card:hover { transform: translateX(5px); background: #252525; box-shadow: -5px 0 10px rgba(0,0,0,0.3); }
    .news-positive { border-left: 5px solid #00ff00; }
    .news-negative { border-left: 5px solid #ff4b4b; }
    .news-neutral { border-left: 5px solid #00d4ff; }
    
    /* --- SIGNAL BOXES --- */
    .sig-box { 
        padding: 12px;
        border-radius: 8px; font-size: 13px; text-align: center; 
        font-weight: bold; border: 1px solid #444; margin-bottom: 8px; box-shadow: inset 0 0 10px rgba(0,0,0,0.2);
    }
    .bull { background: linear-gradient(90deg, #004d40, #00695c); color: #00ff00; border-color: #00ff00; }
    .bear { background: linear-gradient(90deg, #4a1414, #7f0000); color: #ff4b4b; border-color: #ff4b4b; }
    .neutral { background: #262626; color: #888; }

    /* --- NOTIFICATIONS --- */
    .notif-container { 
        padding: 20px;
        border-radius: 12px; margin-bottom: 25px; 
        border-left: 8px solid; background: #121212; font-size: 18px;
    }
    .notif-buy { border-color: #00ff00; color: #00ff00; animation: pulse-green 2s infinite; }
    .notif-sell { border-color: #ff4b4b; color: #ff4b4b; animation: pulse-red 2s infinite; }
    .notif-wait { border-color: #555; color: #aaa; }
    
    /* --- CHAT --- */
    .chat-msg { padding: 10px; border-radius: 8px; margin-bottom: 8px; background: #2a2a2a; border-left: 3px solid #00d4ff; }
    .chat-user { font-weight: bold; color: #00d4ff; font-size: 13px; }

    /* --- ADMIN TABLE --- */
    .admin-table { font-size: 14px; width: 100%; border-collapse: collapse; }
    .admin-table th, .admin-table td { border: 1px solid #444; padding: 8px; text-align: left; }
    .admin-table th { background-color: #333; color: #00d4ff; }
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "chat_history" not in st.session_state: st.session_state.chat_history = []
if "high_prob_signal" not in st.session_state: st.session_state.high_prob_signal = None 
if "last_notified_trade" not in st.session_state: st.session_state.last_notified_trade = None

# --- Helper Functions (DB & Auth) ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        try: sheet = client.open("Forex_User_DB").sheet1
        except: sheet = None
        return sheet, client
    except: return None, None

def check_login(username, password):
    if username == "admin" and password == "admin123": 
        return {"Username": "Admin", "Role": "Admin", "HybridLimit": 9999, "UsageCount": 0}
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            records = sheet.get_all_records()
            user = next((i for i in records if str(i.get("Username")) == username), None)
            if user and str(user.get("Password")) == password:
                if "HybridLimit" not in user: user["HybridLimit"] = 10
                if "UsageCount" not in user: user["UsageCount"] = 0
                return user
        except: return None
    return None

def update_usage_in_db(username, new_usage):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                headers = sheet.row_values(1)
                if "UsageCount" in headers:
                    col_idx = headers.index("UsageCount") + 1
                    sheet.update_cell(cell.row, col_idx, new_usage)
        except Exception as e: print(f"DB Update Error: {e}")

def update_user_limit_in_db(username, new_limit):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                headers = sheet.row_values(1)
                if "HybridLimit" in headers:
                    col_idx = headers.index("HybridLimit") + 1
                    sheet.update_cell(cell.row, col_idx, new_limit)
                return True
        except Exception as e: return False
    return False

# NEW: Added 'phone' parameter for Mobile Number (Restored from New Code)
def add_new_user_to_db(username, password, limit, phone):
    sheet, _ = get_user_sheet()
    if sheet:
        try:
            cell = sheet.find(username)
            if cell:
                return False, "User already exists!"
            # [Username, Password, Role, HybridLimit, UsageCount, Mobile]
            sheet.append_row([username, password, "User", limit, 0, phone])
            return True, f"User {username} created successfully!"
        except Exception as e:
            return False, f"Error creating user: {e}"
    return False, "Database connection failed"

# --- WHATSAPP NOTIFICATION ENGINE (NEW FEATURE) ---
def send_whatsapp_alert(pair, direction, tf, confidence, price):
    try:
        trade_id = f"{pair}_{direction}_{tf}"
        if st.session_state.last_notified_trade == trade_id:
            return

        # Ensure secrets exist
        if "whatsapp" in st.secrets:
            phone = st.secrets["whatsapp"]["phone"]
            api_key = st.secrets["whatsapp"]["api_key"]
            
            message = (
                f"🚀 *INFINITE SYSTEM SIGNAL*\n\n"
                f"✅ *Asset:* {pair}\n"
                f"📊 *Action:* {direction}\n"
                f"⏳ *Timeframe:* {tf}\n"
                f"🔥 *Confidence:* {confidence}%\n"
                f"💰 *Current Price:* {price:.5f}\n\n"
                f"🔗 _Check Terminal for Full AI Analysis_"
            )
            
            encoded_msg = urllib.parse.quote(message)
            url = f"https://api.callmebot.com/whatsapp.php?phone={phone}&text={encoded_msg}&apikey={api_key}"
            
            response = requests.get(url)
            if response.status_code == 200:
                st.session_state.last_notified_trade = trade_id
    except Exception as e:
        print(f"WhatsApp Notification Error: {e}")

# --- News & Tools ---
def get_sentiment_class(title):
    title_lower = title.lower()
    negative_words = ['crash', 'drop', 'fall', 'plunge', 'loss', 'down', 'bear', 'weak', 'inflation', 'war', 'crisis', 'retreat', 'slump']
    positive_words = ['surge', 'rise', 'jump', 'gain', 'bull', 'up', 'strong', 'growth', 'profit', 'record', 'soar', 'rally', 'beat']
    if any(word in title_lower for word in negative_words): return "news-negative"
    elif any(word in title_lower for word in positive_words): return "news-positive"
    else: return "news-neutral"

def get_market_news(symbol):
    news_list = []
    clean_sym = symbol.replace("=X", "").replace("-USD", "")
    try:
        url = f"https://news.google.com/rss/search?q={clean_sym}+forex+market&hl=en-US&gl=US&ceid=US:en"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            for item in root.findall('.//item')[:3]:
                news_list.append({"title": item.find('title').text, "link": item.find('link').text})
    except: pass
    if not news_list:
        try:
            ticker = yf.Ticker(symbol)
            yf_news = ticker.news
            if yf_news:
                for item in yf_news[:3]:
                     news_list.append({"title": item.get('title'), "link": item.get('link')})
        except: pass
    return news_list

def get_data_period(tf):
    periods = {"1m": "5d", "5m": "5d", "15m": "1mo", "1h": "6mo", "4h": "1y", "1d": "2y", "1wk": "5y"}
    return periods.get(tf, "1mo")

# --- 4. ADVANCED SIGNAL ENGINE (FULL RESTORED LOGIC) ---
def calculate_advanced_signals(df, tf):
    if df is None or len(df) < 50: return None, 0, 0
    signals = {}
    c = df['Close'].iloc[-1]
    h = df['High'].iloc[-1]
    l = df['Low'].iloc[-1]
    
    # 1. Trend
    ma_50 = df['Close'].rolling(50).mean().iloc[-1]
    ma_200 = df['Close'].rolling(200).mean().iloc[-1] if len(df) > 200 else ma_50
    trend_dir = "bull" if (c > ma_50 and c > ma_200) else ("bear" if (c < ma_50 and c < ma_200) else "neutral")
    signals['TREND'] = (f"Trend {trend_dir.upper()}", trend_dir)

    # 2. MACD
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal_line = macd.ewm(span=9, adjust=False).mean()
    macd_signal = "bull" if (macd.iloc[-1] > signal_line.iloc[-1] and macd.iloc[-1] > 0) else ("bear" if (macd.iloc[-1] < signal_line.iloc[-1] and macd.iloc[-1] < 0) else "neutral")

    # 3. SMC & ICT
    highs, lows = df['High'].rolling(10).max(), df['Low'].rolling(10).min()
    smc_signal = "bull" if c > highs.iloc[-2] else ("bear" if c < lows.iloc[-2] else "neutral")
    signals['SMC'] = (f"{smc_signal.upper()} Structure", smc_signal)
    
    fvg_bull = df['Low'].iloc[-1] > df['High'].iloc[-3]
    fvg_bear = df['High'].iloc[-1] < df['Low'].iloc[-3]
    ict_signal = "bull" if fvg_bull else ("bear" if fvg_bear else "neutral")
    signals['ICT'] = (f"{ict_signal.upper()} FVG", ict_signal)

    # 4. Liquidity (RESTORED FULL LOGIC FROM OLD CODE)
    liq_signal = "neutral"
    liq_text = "Holding"
    if l < df['Low'].iloc[-10:-1].min():
        liq_signal = "bull" # Swept lows
        liq_text = "Liq Grab (Low)"
    elif h > df['High'].iloc[-10:-1].max():
        liq_signal = "bear" # Swept highs
        liq_text = "Liq Grab (High)"
    signals['LIQ'] = (liq_text, liq_signal)
    
    # 5. Patterns (RESTORED FULL LOGIC FROM OLD CODE)
    patt_signal = "neutral"
    patt_text = "No Pattern"
    if (df['Close'].iloc[-1] > df['Open'].iloc[-1] and df['Close'].iloc[-1] > df['Open'].iloc[-2] and df['Open'].iloc[-1] < df['Close'].iloc[-2]): 
        patt_signal = "bull"
        patt_text = "Bull Engulfing"
    elif (df['Close'].iloc[-1] < df['Open'].iloc[-1] and df['Close'].iloc[-1] < df['Open'].iloc[-2] and df['Open'].iloc[-1] > df['Close'].iloc[-2]): 
        patt_signal = "bear"
        patt_text = "Bear Engulfing"
    signals['PATT'] = (patt_text, patt_signal)
    
    # 6. Volatility
    sma_20 = df['Close'].rolling(20).mean()
    std_20 = df['Close'].rolling(20).std()
    signals['VOLATILITY'] = ("Overextended", "bear") if c > (sma_20.iloc[-1] + std_20.iloc[-1]*2) else ("Oversold", "bull") if c < (sma_20.iloc[-1] - std_20.iloc[-1]*2) else ("Normal Vol", "neutral")

    # 7. RSI
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / loss
    rsi_val = 100 - (100 / (1 + rs)).iloc[-1]
    signals['RSI'] = (f"RSI: {int(rsi_val)}", "neutral")

    # 8. Fibonacci
    ph_fib = df['High'].rolling(50).max().iloc[-1]
    pl_fib = df['Low'].rolling(50).min().iloc[-1]
    fib_range = ph_fib - pl_fib
    fib_618 = ph_fib - (fib_range * 0.618)
    signals['FIB'] = ("Golden Zone", "bull") if abs(c - fib_618) < (c * 0.001) else ("Ranging", "neutral")

    # 9. Elliott Wave (RESTORED LOGIC)
    current_pos = (c - df['Close'].tail(50).min()) / (df['Close'].tail(50).max() - df['Close'].tail(50).min())
    if trend_dir == "bull":
        ew_text = "Wave 3 (Impulse)" if 0.4 < current_pos <= 0.8 else "Wave 5 (Top)" if current_pos > 0.8 else "Wave 1 (Start)"
    else:
        ew_text = "Wave C (Drop)" if current_pos < 0.2 else "Wave Analysis"
    signals['ELLIOTT'] = (ew_text, "neutral")

    # 10. Confidence Score (DETAILED)
    confidence = 0
    weights = {'TREND': 25, 'MACD': 15, 'SMC': 20, 'ICT': 10, 'LIQ': 15, 'PATT': 15}
    if trend_dir == "bull": confidence += weights['TREND']
    elif trend_dir == "bear": confidence -= weights['TREND']
    if macd_signal == "bull": confidence += weights['MACD']
    elif macd_signal == "bear": confidence -= weights['MACD']
    if smc_signal == "bull": confidence += weights['SMC']
    elif smc_signal == "bear": confidence -= weights['SMC']
    if ict_signal == "bull": confidence += weights['ICT']
    elif ict_signal == "bear": confidence -= weights['ICT']
    if signals['LIQ'][1] == "bull": confidence += weights['LIQ']
    elif signals['LIQ'][1] == "bear": confidence -= weights['LIQ']
    if patt_signal == "bull": confidence += weights['PATT']
    elif patt_signal == "bear": confidence -= weights['PATT']

    final_signal = "bull" if confidence >= 75 else ("bear" if confidence <= -75 else "neutral")
    signals['SK'] = (f"CONFIDENCE: {abs(confidence)}%", final_signal)
    
    atr = (df['High']-df['Low']).rolling(14).mean().iloc[-1]
    return signals, atr, confidence

# --- 5. ALGO & AI ENGINES ---
def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr, tf):
    confidence = sigs['SK'][0]
    signal_dir = sigs['SK'][1]
    
    if tf in ["1m", "5m"]:
        trade_mode = "SCALPING (වේගවත්)"
        sl_mult, tp_mult = 1.2, 2.0
    else:
        trade_mode = "SWING (දිගු කාලීන)"
        sl_mult, tp_mult = 1.5, 3.5

    action = "WAIT"
    status_sinhala = "ප්‍රවේශම් වන්න. වෙළඳපල අවිනිශ්චිතයි."
    sl, tp = 0, 0

    if signal_dir == "bull": 
        action = "BUY"
        status_sinhala = "ඉතා ඉහළ සාර්ථකත්වයක් (High Probability Buy). ගැනුම්කරුවන් පාලනය අතට ගෙන ඇත."
        sl = curr_p - (atr * sl_mult)
        tp = curr_p + (atr * tp_mult)
    elif signal_dir == "bear": 
        action = "SELL"
        status_sinhala = "ඉතා ඉහළ සාර්ථකත්වයක් (High Probability Sell). විකුණුම්කරුවන් පාලනය අතට ගෙන ඇත."
        sl = curr_p + (atr * sl_mult)
        tp = curr_p - (atr * tp_mult)
    else:
        sl = curr_p - (atr * sl_mult) # Default for view
        tp = curr_p + (atr * tp_mult)

    return f"""
    ♾️ **INFINITE ALGO ENGINE V15.0 - HYBRID**
    
    📊 **වෙළඳපල විශ්ලේෂණය ({tf}):**
    • Trade Type: {trade_mode}
    • Signal Accuracy: {confidence} (Target > 75%)
    • Action: {action}
    • Trend: {sigs['TREND'][0]}
    • Liquidity: {sigs['LIQ'][0]}
    
    💡 **නිගමනය:**
    {status_sinhala}
    
    DATA: ENTRY={curr_p:.5f} | SL={sl:.5f} | TP={tp:.5f}
    """

def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf):
    algo_result = infinite_algorithmic_engine(pair, asset_data['price'], sigs, news_items, atr, tf)
    
    if user_info.get("UsageCount", 0) >= user_info.get("HybridLimit", 10) and user_info["Role"] != "Admin":
        return algo_result, "Limit Reached"

    prompt = f"""
    Act as a Senior Hedge Fund Trader. Analyze {pair} on {tf} timeframe.
    The Algorithm calculates a confidence of {sigs['SK'][0]}.
    **Infinite Algorithm Output:**
    {algo_result}
    
    **Instructions:**
    1. Verify if this is a High Probability Trade (>75%).
    2. Prioritize SWING trades (Big moves) over SCALPS.
    3. Explain the setup in Sinhala (Technical terms in English).
    4. Provide ENTRY, SL, TP based on ATR ({atr:.5f}).
    
    **FINAL OUTPUT FORMAT (STRICT):**
    [Detailed Sinhala Explanation]
    
    DATA: ENTRY=xxxxx | SL=xxxxx | TP=xxxxx
    """
    
    gemini_keys = []
    for i in range(1, 8):
        k = st.secrets.get(f"GEMINI_API_KEY_{i}")
        if k: gemini_keys.append(k)

    response_text = ""
    provider_name = ""

    # RESTORED UI LOADING ANIMATION FROM OLD CODE
    with st.status(f"🚀 Infinite AI Activating ({tf})...", expanded=True) as status:
        # 1. Try Gemini
        for idx, key in enumerate(gemini_keys):
            try:
                genai.configure(api_key=key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(prompt)
                response_text = response.text
                provider_name = f"Gemini 1.5 Flash (Key {idx+1}) ⚡"
                status.update(label=f"✅ Gemini Analysis Complete!", state="complete", expanded=False)
                break
            except: continue
        
        # 2. Try Puter Fallback
        if not response_text:
            try:
                puter_resp = puter.ai.chat(prompt)
                response_text = puter_resp.message.content
                provider_name = "Puter AI (Fallback) 🔵"
                status.update(label="✅ Puter Analysis Complete!", state="complete", expanded=False)
            except:
                status.update(label="⚠️ AI Failed, using Algo", state="error", expanded=False)
                return algo_result, "Algo Default"

    if response_text:
        update_usage_in_db(user_info["Username"], user_info["UsageCount"] + 1)
        return response_text, provider_name
        
    return algo_result, "Algo Default"

def parse_ai_response(text):
    data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
    for key in data.keys():
        match = re.search(fr"{key}\s*[:=]\s*([\d\.]+)", text, re.IGNORECASE)
        if match: data[key] = match.group(1)
    return data

# --- SCANNER (RESTORED SWING/SCALP + NEW WHATSAPP) ---
def scan_market(assets_list):
    # 1. SWING SCAN (Priority: High - 4h)
    for symbol in assets_list:
        try:
            df = yf.download(symbol, period="6mo", interval="4h", progress=False)
            if not df.empty and len(df) > 50:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                sigs, _, conf = calculate_advanced_signals(df, "4h")
                if abs(conf) >= 75:
                    res = {"pair": symbol.replace("=X", ""), "tf": "4h (Swing)", "dir": "BUY" if conf > 0 else "SELL", "conf": abs(conf), "price": df['Close'].iloc[-1]}
                    # Trigger WhatsApp (New Feature)
                    send_whatsapp_alert(res['pair'], res['dir'], res['tf'], res['conf'], res['price'])
                    return res
        except: continue

    # 2. SCALP SCAN (5m)
    for symbol in assets_list:
        try:
            df = yf.download(symbol, period="5d", interval="5m", progress=False)
            if not df.empty and len(df) > 50:
                if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
                sigs, _, conf = calculate_advanced_signals(df, "5m")
                if abs(conf) >= 80:
                    res = {"pair": symbol.replace("=X", ""), "tf": "5m (Scalp)", "dir": "BUY" if conf > 0 else "SELL", "conf": abs(conf), "price": df['Close'].iloc[-1]}
                    # Trigger WhatsApp (New Feature)
                    send_whatsapp_alert(res['pair'], res['dir'], res['tf'], res['conf'], res['price'])
                    return res
        except: continue
        
    return None

# --- 7. MAIN INTERFACE ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff;'>⚡ INFINITE SYSTEM v15.0</h1>", unsafe_allow_html=True)
    with st.form("login"):
        u, p = st.text_input("Username"), st.text_input("Password", type="password")
        if st.form_submit_button("Login"):
            user = check_login(u, p)
            if user: 
                st.session_state.logged_in, st.session_state.user = True, user
                st.rerun()
else:
    user_info = st.session_state.user
    st.sidebar.title(f"👤 {user_info['Username']}")
    auto_refresh = st.sidebar.checkbox("🔄 Auto-Monitor (WhatsApp)", value=False)
    
    nav_options = ["Terminal", "Market Scanner", "Trader Chat"]
    if user_info.get("Role") == "Admin": nav_options.append("Admin Panel")
    app_mode = st.sidebar.radio("Navigation", nav_options)
    
    # RESTORED FULL ASSET LIST FROM OLD CODE
    assets = {
        "Forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCHF=X", "USDCAD=X", "NZDUSD=X", "EURJPY=X", "GBPJPY=X"],
        "Crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD", "ADA-USD", "DOGE-USD"],
        "Metals": ["XAUUSD=X", "XAGUSD=X"] 
    }
    
    if auto_refresh:
        all_scan_assets = assets["Forex"] + assets["Crypto"] + assets["Metals"]
        # Scan subset to avoid timeout
        import random
        scan_subset = random.sample(all_scan_assets, 5)
        found = scan_market(scan_subset)
        if found: st.session_state.high_prob_signal = found

    if app_mode == "Terminal":
        if st.session_state.high_prob_signal:
            s = st.session_state.high_prob_signal
            st.markdown(f"<div class='high-prob-alert'><div class='high-prob-pair'>{s['pair']} - {s['dir']} ({s['tf']})</div><div>Confidence: {s['conf']}% | Price: {s['price']:.5f}</div></div>", unsafe_allow_html=True)
        
        market = st.sidebar.radio("Market", ["Forex", "Crypto", "Metals"])
        pair = st.sidebar.selectbox("Asset", assets[market])
        tf = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "4h", "1d", "1wk"], index=3)

        df = yf.download(pair, period=get_data_period(tf), interval=tf, progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
            curr_p = df['Close'].iloc[-1]
            st.title(f"{pair.replace('=X','')} Terminal - {curr_p:.5f}")
            sigs, atr, conf = calculate_advanced_signals(df, tf)
            
            # Notification Accuracy Update
            color = "notif-buy" if conf >= 75 else ("notif-sell" if conf <= -75 else "notif-wait")
            msg = f"<b>{'STRONG BUY' if conf>=75 else 'STRONG SELL' if conf<=-75 else 'WAITING'}:</b> Confidence {abs(conf)}% | Current Price: {curr_p:.5f}"
            st.markdown(f"<div class='notif-container {color}'>🔔 {msg}</div>", unsafe_allow_html=True)

            # Signal Grid (Merged Old & New Layout)
            cols = st.columns(3)
            cols[0].markdown(f"<div class='sig-box {sigs['TREND'][1]}'>TREND: {sigs['TREND'][0]}</div>", unsafe_allow_html=True)
            cols[1].markdown(f"<div class='sig-box {sigs['SMC'][1]}'>SMC: {sigs['SMC'][0]}</div>", unsafe_allow_html=True)
            cols[2].markdown(f"<div class='sig-box {sigs['ICT'][1]}'>ICT: {sigs['ICT'][0]}</div>", unsafe_allow_html=True)
            
            c2 = st.columns(3)
            c2[0].markdown(f"<div class='sig-box {sigs['LIQ'][1]}'>{sigs['LIQ'][0]}</div>", unsafe_allow_html=True)
            c2[1].markdown(f"<div class='sig-box {sigs['ELLIOTT'][1]}'>{sigs['ELLIOTT'][0]}</div>", unsafe_allow_html=True)
            c2[2].markdown(f"<div class='sig-box {sigs['PATT'][1]}'>{sigs['PATT'][0]}</div>", unsafe_allow_html=True)

            st.plotly_chart(go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])]), use_container_width=True)

            if st.button("🚀 Analyze with Hybrid AI", use_container_width=True):
                res, prov = get_hybrid_analysis(pair, {'price': curr_p}, sigs, [], atr, user_info, tf)
                st.session_state.ai_parsed_data = parse_ai_response(res)
                st.session_state.ai_result, st.session_state.active_provider = res, prov
                st.rerun()

            if "ai_result" in st.session_state:
                p = st.session_state.ai_parsed_data
                c = st.columns(3)
                c[0].markdown(f"<div class='trade-metric'><h4>ENTRY</h4><h2 style='color:#00d4ff;'>{p['ENTRY']}</h2></div>", unsafe_allow_html=True)
                c[1].markdown(f"<div class='trade-metric'><h4>SL</h4><h2 style='color:#ff4b4b;'>{p['SL']}</h2></div>", unsafe_allow_html=True)
                c[2].markdown(f"<div class='trade-metric'><h4>TP</h4><h2 style='color:#00ff00;'>{p['TP']}</h2></div>", unsafe_allow_html=True)
                st.markdown(f"**🤖 Provider:** `{st.session_state.active_provider}`")
                st.markdown(f"<div class='entry-box'>{st.session_state.ai_result}</div>", unsafe_allow_html=True)

    elif app_mode == "Market Scanner":
        st.title("📡 Global Market Scanner")
        if st.button("Start Scan", type="primary"):
            with st.spinner("Scanning Global Markets (Forex, Crypto, Metals)..."):
                all_scan_assets = assets["Forex"] + assets["Crypto"] + assets["Metals"]
                found = scan_market(all_scan_assets)
                if found: st.success(f"Signal Found: {found['pair']}")
                else: st.warning("No High Prob trades.")
            st.rerun()

    elif app_mode == "Trader Chat":
        st.title("💬 Global Trader Room")
        for m in st.session_state.chat_history:
            st.markdown(f"<div class='chat-msg'><span class='chat-user'>{m['user']}</span>: {m['text']}</div>", unsafe_allow_html=True)
        with st.form("chat"):
            msg = st.text_input("Message")
            if st.form_submit_button("Send") and msg:
                st.session_state.chat_history.append({"user": user_info['Username'], "text": msg})
                st.rerun()

    # --- ADMIN PANEL (UPDATED WITH MOBILE) ---
    elif app_mode == "Admin Panel":
        if user_info.get("Role") == "Admin":
            st.title("🛡️ Admin Center")
            sheet, _ = get_user_sheet()
            if sheet:
                all_records = sheet.get_all_records()
                df_users = pd.DataFrame(all_records)
                st.dataframe(df_users, use_container_width=True)
                
                st.markdown("---")
                with st.expander("➕ Create New User", expanded=False):
                    with st.form("create_user_form"):
                        new_u_name = st.text_input("Username")
                        new_u_pass = st.text_input("Password")
                        new_u_limit = st.number_input("Initial Hybrid Limit", value=10, min_value=1)
                        # Added Mobile Number Input (From New Code)
                        new_u_mobile = st.text_input("Mobile Number (with Country Code)", placeholder="+947xxxxxxxx")
                        
                        if st.form_submit_button("Create User"):
                            if new_u_name and new_u_pass and new_u_mobile:
                                success, msg = add_new_user_to_db(new_u_name, new_u_pass, new_u_limit, new_u_mobile)
                                if success: 
                                    st.success(msg)
                                    time.sleep(1)
                                    st.rerun()
                                else: st.error(msg)
                            else: st.warning("Please fill all fields (Username, Password, Mobile)")

                st.markdown("### ✏️ Manage User Credits")
                user_list = [r['Username'] for r in all_records if str(r.get('Username')) != 'Admin']
                target_user = st.selectbox("Select User to Update", user_list)
                
                if target_user:
                    curr_user_data = next((u for u in all_records if u['Username'] == target_user), {})
                    st.info(f"User: **{target_user}** | Current Limit: **{curr_user_data.get('HybridLimit', 'N/A')}** | Used: **{curr_user_data.get('UsageCount', 'N/A')}**")
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        st.subheader("Update Limit")
                        new_limit_val = st.number_input("New Hybrid Limit", min_value=0, value=int(curr_user_data.get('HybridLimit', 10)))
                        if st.button("💾 Save Limit"):
                            update_user_limit_in_db(target_user, new_limit_val)
                            st.success(f"Limit updated to {new_limit_val}")
                            time.sleep(1)
                            st.rerun()
                    with c2:
                        st.subheader("Reset Usage")
                        new_usage_val = st.number_input("Set Usage Count", min_value=0, value=0)
                        if st.button("🔄 Update Usage"):
                            update_usage_in_db(target_user, new_usage_val)
                            st.success(f"Usage count set to {new_usage_val}")
                            time.sleep(1)
                            st.rerun()
            else: st.error("Database Connection Failed")
        else: st.error("Access Denied.")

    if auto_refresh:
        time.sleep(60)
        st.rerun()
