"""
app.py
FX-WavePulse Pro - Main Streamlit Application
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import pytz
import time
import uuid

# ── Page Config (must be first Streamlit call) ──────────────────────────────
st.set_page_config(
    page_title="FX-WavePulse Pro",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Imports ──────────────────────────────────────────────────────────────────
try:
    from modules.database import (
        get_database, get_fresh_spreadsheet, authenticate_user, create_user, delete_user,
        get_users, get_active_trades, add_active_trade, close_trade,
        get_trade_history, update_trade_pnl, auto_capture_signal,
        get_user_settings, save_user_settings,
        get_notifications, mark_all_read, check_sl_tp_hits,
    )
    from modules.market_data import (
        get_all_live_prices, get_ohlcv, get_session_status, get_colombo_time,
        SYMBOL_MAP, MAJOR_PAIRS, SYMBOL_CATEGORIES, get_all_symbols
    )
    from modules.elliott_wave import identify_elliott_waves
    from modules.smc_analysis import analyze_smc
    from modules.signal_engine import generate_all_signals, generate_signal, TradeSignal
    from modules.charts import create_candlestick_chart, create_pnl_chart
    from modules.gemini_ai import (
        get_gemini_confirmation, get_market_sentiment,
        get_key_rotation_status, _get_api_keys, get_news_impact_alert,
    )
except ImportError as e:
    st.error(f"""
    ❌ **Module Import Error:** `{e}`

    **Fix:** Make sure all files in the `modules/` folder are uploaded to GitHub:
    - `modules/__init__.py`
    - `modules/database.py`
    - `modules/market_data.py`
    - `modules/elliott_wave.py`
    - `modules/smc_analysis.py`
    - `modules/signal_engine.py`
    - `modules/charts.py`

    Also verify `requirements.txt` is in the root folder.
    """)
    st.stop()

COLOMBO_TZ = pytz.timezone("Asia/Colombo")

# ══════════════════════════════════════════════════════════════
# CUSTOM CSS
# ══════════════════════════════════════════════════════════════
def inject_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    :root {
        --bg-primary:   #070B14;
        --bg-secondary: #0D1220;
        --bg-card:      #111827;
        --bg-card2:     #161D2E;
        --accent-green: #00D4AA;
        --accent-red:   #FF4B6E;
        --accent-gold:  #F5C518;
        --accent-blue:  #3B82F6;
        --accent-purple:#8B5CF6;
        --text-primary: #E8EDF5;
        --text-muted:   #6B7A99;
        --border:       #1E2A42;
    }

    /* Base */
    html, body, [class*="css"] {
        font-family: 'Space Grotesk', sans-serif !important;
        background-color: var(--bg-primary) !important;
        color: var(--text-primary) !important;
    }

    .main .block-container { padding: 1rem 1.5rem 2rem !important; max-width: 100% !important; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #0A0F1E 0%, #070B14 100%) !important;
        border-right: 1px solid var(--border) !important;
    }
    [data-testid="stSidebar"] .stRadio > div { gap: 4px; }

    /* Headers */
    h1, h2, h3 { font-family: 'Space Grotesk', sans-serif !important; letter-spacing: -0.02em; }

    /* Brand Header */
    .brand-header {
        background: linear-gradient(135deg, #0D1220 0%, #111827 100%);
        border: 1px solid #1E2A42;
        border-radius: 12px;
        padding: 1rem 1.5rem;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .brand-title {
        font-size: 1.8rem;
        font-weight: 700;
        background: linear-gradient(90deg, #00D4AA, #3B82F6, #8B5CF6);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        letter-spacing: -0.03em;
    }
    .brand-subtitle { color: var(--text-muted); font-size: 0.78rem; font-family: 'JetBrains Mono'; }

    /* Metric Cards */
    .metric-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 1rem 1.2rem;
        transition: border-color 0.2s;
    }
    .metric-card:hover { border-color: #2E3D5A; }
    .metric-label { font-size: 0.72rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 4px; }
    .metric-value { font-size: 1.5rem; font-weight: 600; font-family: 'JetBrains Mono'; }
    .metric-change { font-size: 0.8rem; font-family: 'JetBrains Mono'; margin-top: 2px; }
    .up   { color: var(--accent-green); }
    .down { color: var(--accent-red); }
    .neutral { color: var(--text-muted); }

    /* Signal Card */
    .signal-card {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 0.75rem;
        position: relative;
        overflow: hidden;
    }
    .signal-card::before {
        content: '';
        position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
    }
    .signal-card.buy::before  { background: var(--accent-green); }
    .signal-card.sell::before { background: var(--accent-red); }
    .signal-badge {
        display: inline-block; padding: 3px 10px; border-radius: 20px;
        font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em;
    }
    .badge-buy  { background: rgba(0,212,170,0.15); color: var(--accent-green); border: 1px solid rgba(0,212,170,0.3); }
    .badge-sell { background: rgba(255,75,110,0.15); color: var(--accent-red);   border: 1px solid rgba(255,75,110,0.3); }
    .badge-score-high   { background: rgba(0,212,170,0.2); color: var(--accent-green); }
    .badge-score-medium { background: rgba(245,197,24,0.2); color: var(--accent-gold); }
    .badge-score-low    { background: rgba(107,122,153,0.2); color: var(--text-muted); }

    /* Session Pills */
    .session-pill {
        display: inline-block; padding: 4px 12px; border-radius: 20px;
        font-size: 0.75rem; font-weight: 500; margin: 2px;
    }
    .session-active   { background: rgba(0,212,170,0.15); color: var(--accent-green); border: 1px solid rgba(0,212,170,0.3); }
    .session-inactive { background: var(--bg-card2); color: var(--text-muted); border: 1px solid var(--border); }
    .session-overlap  { background: rgba(245,197,24,0.15); color: var(--accent-gold); border: 1px solid rgba(245,197,24,0.3); }

    /* Ticker Strip */
    .ticker-strip {
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 8px;
        padding: 0.5rem 1rem;
        display: flex; gap: 1.5rem; flex-wrap: wrap;
        margin-bottom: 1rem;
    }
    .ticker-item { display: flex; align-items: center; gap: 6px; }
    .ticker-symbol { font-size: 0.78rem; color: var(--text-muted); font-weight: 600; }
    .ticker-price { font-family: 'JetBrains Mono'; font-size: 0.9rem; font-weight: 500; }

    /* Table */
    .styled-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
    .styled-table th {
        background: var(--bg-card2); color: var(--text-muted);
        font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em;
        padding: 8px 12px; border-bottom: 1px solid var(--border); text-align: left;
    }
    .styled-table td { padding: 10px 12px; border-bottom: 1px solid #141E30; }
    .styled-table tr:hover td { background: var(--bg-card2); }

    /* Progress Bar */
    .score-bar-container { background: var(--bg-card2); border-radius: 4px; height: 6px; overflow: hidden; margin-top: 4px; }
    .score-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
    .score-high   { background: linear-gradient(90deg, #00D4AA, #3B82F6); }
    .score-medium { background: linear-gradient(90deg, #F5C518, #F97316); }
    .score-low    { background: #4B5563; }

    /* Login */
    .login-container {
        max-width: 420px; margin: 5vh auto 0;
        background: var(--bg-card);
        border: 1px solid var(--border);
        border-radius: 16px; padding: 2.5rem;
        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
    }

    /* Hide Streamlit default elements */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    [data-testid="stToolbar"] { display: none; }

    /* ── Sidebar Toggle Button (☰) ─────────────────────────── */
    /* Show the native Streamlit collapse button always */
    [data-testid="collapsedControl"] {
        display: flex !important;
        visibility: visible !important;
        opacity: 1 !important;
    }
    /* Style it nicely */
    [data-testid="collapsedControl"] button {
        background: linear-gradient(135deg, #00D4AA22, #3B82F622) !important;
        border: 1px solid #1E2A42 !important;
        border-radius: 8px !important;
        color: #00D4AA !important;
        width: 38px !important;
        height: 38px !important;
        font-size: 1.1rem !important;
    }
    [data-testid="collapsedControl"] button:hover {
        background: linear-gradient(135deg, #00D4AA44, #3B82F644) !important;
        border-color: #00D4AA !important;
    }
    /* Custom floating toggle button for mobile / collapsed state */
    .sidebar-toggle-btn {
        position: fixed;
        top: 0.6rem;
        left: 0.6rem;
        z-index: 999999;
        background: linear-gradient(135deg, #0D1220, #111827);
        border: 1px solid #1E2A42;
        border-radius: 8px;
        width: 38px; height: 38px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer;
        font-size: 1.1rem;
        color: #00D4AA;
        box-shadow: 0 2px 12px rgba(0,0,0,0.4);
        transition: all 0.2s;
    }
    .sidebar-toggle-btn:hover {
        border-color: #00D4AA;
        background: linear-gradient(135deg, #0D1220, #162030);
    }

    /* Input styling */
    .stTextInput input, .stSelectbox select, .stNumberInput input {
        background: var(--bg-card2) !important;
        border-color: var(--border) !important;
        color: var(--text-primary) !important;
        border-radius: 8px !important;
    }
    .stButton > button {
        background: linear-gradient(135deg, #00D4AA, #3B82F6) !important;
        color: white !important; border: none !important;
        border-radius: 8px !important; font-weight: 600 !important;
        padding: 0.5rem 1.5rem !important; width: 100% !important;
        transition: opacity 0.2s !important;
    }
    .stButton > button:hover { opacity: 0.85 !important; }
    .danger-btn > button { background: linear-gradient(135deg, #FF4B6E, #DC2626) !important; }

    /* Divider */
    hr { border-color: var(--border) !important; }

    /* Tab styling */
    .stTabs [data-baseweb="tab-list"] { background: var(--bg-card) !important; border-radius: 8px; }
    .stTabs [data-baseweb="tab"] { color: var(--text-muted) !important; }
    .stTabs [aria-selected="true"] { color: var(--accent-green) !important; }
    </style>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════
def init_session():
    defaults = {
        "authenticated":     False,
        "user":              None,
        "db":                None,
        "db_error":          None,
        "page":              "dashboard",
        "last_refresh":      None,
        "sidebar_open":      True,
        "sl_tp_checked_at":  0,       # timestamp of last SL/TP check
        "notif_count":       0,       # unread notification count
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ══════════════════════════════════════════════════════════════
# LOGIN PAGE
# ══════════════════════════════════════════════════════════════
def render_login():
    st.markdown("""
    <div style="text-align:center; padding: 2rem 0 1rem;">
        <div style="font-size:3rem; margin-bottom:0.5rem;">📈</div>
        <div style="font-size:2rem; font-weight:700; background: linear-gradient(90deg,#00D4AA,#3B82F6,#8B5CF6);
             -webkit-background-clip:text; -webkit-text-fill-color:transparent; letter-spacing:-0.03em;">
            FX-WavePulse Pro
        </div>
        <div style="color:#6B7A99; font-size:0.82rem; font-family:'JetBrains Mono'; margin-top:4px;">
            Elliott Wave · Smart Money Concepts · Multi-Timeframe
        </div>
    </div>
    """, unsafe_allow_html=True)

    col = st.columns([1, 1.2, 1])[1]
    with col:
        with st.container():
            st.markdown('<div class="login-container">', unsafe_allow_html=True)
            st.markdown("#### Sign In")

            if st.session_state.db_error:
                st.warning(f"⚠️ Google Sheets not connected: {st.session_state.db_error}\n\nDemo mode active — no data will be persisted.", icon="⚠️")

            username = st.text_input("Username", placeholder="Enter username", key="login_user")
            password = st.text_input("Password", type="password", placeholder="Enter password", key="login_pass")

            if st.button("Sign In →", key="login_btn"):
                if username and password:
                    user = authenticate_user(st.session_state.db, username, password)
                    if user:
                        st.session_state.authenticated = True
                        st.session_state.user = user if isinstance(user, dict) else {"username": username, "role": "trader"}
                        st.rerun()
                    else:
                        st.error("Invalid credentials. Please try again.")
                else:
                    st.warning("Please enter username and password.")

            st.markdown("""
            <div style="text-align:center; margin-top:1rem; color:#4B5563; font-size:0.75rem;">
                Contact admin to create your account
            </div>
            """, unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════
def render_sidebar():
    user     = st.session_state.user
    is_admin = user.get("role") == "admin"
    username = user.get("username","")
    db       = st.session_state.db

    # ── SL/TP background monitor (every 60s) ──────────────────────────────
    import time as _time
    now_ts = _time.time()
    if db and (now_ts - st.session_state.get("sl_tp_checked_at", 0)) > 60:
        try:
            from modules.market_data import get_live_price
            trades_df = get_active_trades(db, None if is_admin else username)
            if not trades_df.empty:
                symbols = trades_df["symbol"].unique().tolist()
                live_prices = {s: (get_live_price(s).get("price") or 0) for s in symbols}
                closed = check_sl_tp_hits(db, live_prices)
                if closed:
                    for c in closed:
                        icon = "🎉" if c["result"]=="TP" else "🛑"
                        st.toast(f"{icon} {c['symbol']} {c['direction']} → {c['result']} Hit! {c['msg']}", icon=icon[0])
                    # Refresh cached db
                    get_database.clear()
                    st.session_state.db, _ = get_database()
        except Exception as e:
            pass
        st.session_state.sl_tp_checked_at = now_ts

    # ── Unread notification count ─────────────────────────────────────────
    notif_count = 0
    if db:
        try:
            notifs = get_notifications(db, username, unread_only=True)
            notif_count = len(notifs) if not notifs.empty else 0
            st.session_state.notif_count = notif_count
        except Exception:
            pass

    with st.sidebar:
        st.markdown(f"""
        <div style="padding:1rem 0.5rem; border-bottom:1px solid #1E2A42; margin-bottom:1rem;">
            <div style="font-size:1.2rem; font-weight:700; color:#00D4AA;">FX-WavePulse Pro</div>
            <div style="font-size:0.75rem; color:#6B7A99; font-family:'JetBrains Mono';">v3.0 · Elliott + SMC + AI</div>
        </div>
        <div style="background:#111827; border-radius:8px; padding:0.7rem 1rem; margin-bottom:1rem; border:1px solid #1E2A42;">
            <div style="font-size:0.72rem; color:#6B7A99;">Logged in as</div>
            <div style="font-weight:600; color:#E8EDF5;">{username}</div>
            <div style="font-size:0.7rem; background:{'rgba(139,92,246,0.2)' if is_admin else 'rgba(59,130,246,0.2)'};
                 color:{'#8B5CF6' if is_admin else '#3B82F6'};
                 border-radius:10px; padding:1px 8px; display:inline-block; margin-top:2px;">
                {'👑 Admin' if is_admin else '📊 Trader'}
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Notification bell
        if notif_count > 0:
            if st.button(f"🔔 Notifications ({notif_count})", use_container_width=True):
                st.session_state.page = "notifications"
                st.rerun()
        else:
            st.markdown('<div style="color:#6B7A99; font-size:0.78rem; padding:0.3rem 0.5rem;">🔕 No new notifications</div>', unsafe_allow_html=True)

        pages = {
            "dashboard": "📊  Dashboard",
            "signals":   "🎯  Trade Signals",
            "analysis":  "🔬  Chart Analysis",
            "trades":    "💼  Active Trades",
            "history":   "📜  Trade History",
            "settings":  "⚙️  My Settings",
        }
        if is_admin:
            pages["admin"] = "👑  Admin Panel"

        st.markdown("**Navigation**")
        for page_key, label in pages.items():
            btn_type = "primary" if st.session_state.page == page_key else "secondary"
            if st.button(label, key=f"nav_{page_key}", use_container_width=True, type=btn_type):
                st.session_state.page = page_key
                st.rerun()

        st.markdown("---")
        now = datetime.now(COLOMBO_TZ)
        st.markdown(f"""
        <div style="background:#0D1220; border-radius:8px; padding:0.7rem 1rem; border:1px solid #1E2A42;">
            <div style="font-size:0.7rem; color:#6B7A99;">🕐 Asia/Colombo (LKT)</div>
            <div style="font-family:'JetBrains Mono'; font-size:0.9rem; color:#E8EDF5; margin-top:2px;">
                {now.strftime('%H:%M:%S')}
            </div>
            <div style="font-size:0.72rem; color:#6B7A99;">{now.strftime('%a %d %b %Y')}</div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")
        if st.button("🚪 Sign Out", use_container_width=True):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()


# ══════════════════════════════════════════════════════════════
# DASHBOARD PAGE
# ══════════════════════════════════════════════════════════════
def render_dashboard():
    # Sidebar toggle button (floating, always visible)
    st.markdown("""
    <script>
    function toggleSidebar() {
        const btn = window.parent.document.querySelector('[data-testid="collapsedControl"] button');
        if (btn) btn.click();
    }
    </script>
    """, unsafe_allow_html=True)

    # Header
    st.markdown("""
    <div class="brand-header">
        <div>
            <div class="brand-title">📈 FX-WavePulse Pro</div>
            <div class="brand-subtitle">Elliott Wave · Smart Money Concepts · Multi-Timeframe Analysis</div>
        </div>
        <div style="display:flex; gap:8px; align-items:center;">
            <div onclick="toggleSidebar()" class="sidebar-toggle-btn" title="Toggle Menu">☰</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Market Sessions
    sessions = get_session_status()
    session_html = '<div style="margin-bottom:1rem;">'
    for name, info in sessions.items():
        if info["active"]:
            cls = "session-overlap" if info["overlap"] else "session-active"
            icon = "🔥" if info["overlap"] else "🟢"
        else:
            cls = "session-inactive"
            icon = "⚫"
        session_html += f'<span class="session-pill {cls}">{icon} {name}</span>'
    session_html += '</div>'
    st.markdown(session_html, unsafe_allow_html=True)

    # Live Tickers
    with st.spinner("Loading live prices..."):
        prices = get_all_live_prices()
    
    ticker_html = '<div class="ticker-strip">'
    for p in prices:
        if p["price"] is None:
            continue
        chg = p.get("change_pct", 0) or 0
        color = "#00D4AA" if chg >= 0 else "#FF4B6E"
        arrow = "▲" if chg >= 0 else "▼"
        price_str = f"{p['price']:.5f}" if p["price"] < 100 else f"{p['price']:.2f}"
        ticker_html += f"""
        <div class="ticker-item">
            <span class="ticker-symbol">{p['symbol']}</span>
            <span class="ticker-price" style="color:{color}">{price_str}</span>
            <span style="font-size:0.75rem; color:{color}; font-family:'JetBrains Mono'">
                {arrow}{abs(chg):.2f}%
            </span>
        </div>"""
    ticker_html += '</div>'
    st.markdown(ticker_html, unsafe_allow_html=True)

    # Stats Row
    c1, c2, c3, c4 = st.columns(4)
    db = st.session_state.db
    username = st.session_state.user.get("username")
    
    active_trades = get_active_trades(db, username) if db else pd.DataFrame()
    history = get_trade_history(db, username) if db else pd.DataFrame()
    
    n_active = len(active_trades)
    
    total_pnl = 0
    win_rate = 0
    if not history.empty and "pnl" in history.columns:
        history["pnl"] = pd.to_numeric(history["pnl"], errors="coerce").fillna(0)
        total_pnl = history["pnl"].sum()
        wins = (history["pnl"] > 0).sum()
        win_rate = round(wins / len(history) * 100, 1) if len(history) > 0 else 0

    pnl_color = "up" if total_pnl >= 0 else "down"
    
    for col, (label, value, extra, color) in zip(
        [c1, c2, c3, c4],
        [
            ("Active Trades", str(n_active), "Running positions", "neutral"),
            ("Total P&L", f"${total_pnl:+.2f}", "All closed trades", pnl_color),
            ("Win Rate", f"{win_rate}%", f"{len(history)} closed trades", "up" if win_rate > 50 else "down"),
            ("Signals", "Live", "EW + SMC engine", "neutral"),
        ]
    ):
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value {color}">{value}</div>
            <div class="metric-change neutral">{extra}</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("---")

    # Quick Signals
    col_left, col_right = st.columns([1.5, 1])
    
    with col_left:
        st.markdown("### 🎯 Top Signals")
        with st.spinner("Generating signals..."):
            signals = generate_all_signals(MAJOR_PAIRS[:6], "swing", min_score=20)
        
        if not signals:
            st.info("No high-confidence signals at the moment. Market may be ranging.")
        else:
            for sig in signals[:4]:
                _render_signal_card(sig)

    with col_right:
        st.markdown("### 📡 Session Overview")
        for name, info in sessions.items():
            status = "🟢 Active" if info["active"] else "⚫ Closed"
            overlap = " 🔥 Overlap!" if info["overlap"] else ""
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; padding:8px 0; 
                 border-bottom:1px solid #1E2A42; font-size:0.85rem;">
                <span style="color:#6B7A99;">{name}</span>
                <span style="color:{'#00D4AA' if info['active'] else '#4B5563'}">{status}{overlap}</span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("---")
        st.markdown("### 📊 Quick Stats")
        st.markdown(f"""
        <div style="font-size:0.8rem; color:#6B7A99; font-family:'JetBrains Mono';">
            <div style="margin-bottom:6px">🕐 LKT: {datetime.now(COLOMBO_TZ).strftime('%H:%M:%S')}</div>
            <div style="margin-bottom:6px">📈 Pairs tracked: {len(MAJOR_PAIRS)}</div>
            <div style="margin-bottom:6px">🔄 Data refresh: 60s</div>
            <div>⚡ Engine: EW + SMC v2</div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# SIGNAL CARD HELPER
# ══════════════════════════════════════════════════════════════
def _render_signal_card(sig: TradeSignal):
    """Manual-trader optimized card — MT4/MT5 copy-paste ready."""
    score     = sig.probability_score
    score_cls = "badge-score-high" if score >= 70 else ("badge-score-medium" if score >= 50 else "badge-score-low")
    bar_cls   = "score-high" if score >= 70 else ("score-medium" if score >= 50 else "score-low")
    dir_badge = "badge-buy" if sig.direction == "BUY" else "badge-sell"
    is_buy    = sig.direction == "BUY"

    def fmt(v):
        if v is None: return "—"
        try:
            fv = float(v)
            return f"{fv:.5f}" if fv < 100 else f"{fv:.3f}"
        except Exception:
            return "—"

    entry     = float(sig.entry_price)   # = market price (cp)
    sl        = float(sig.sl_price)
    tp1       = float(sig.tp_price)
    tp2       = float(sig.tp2_price) if sig.tp2_price else None
    tp3       = float(sig.tp3_price) if sig.tp3_price else None
    risk_pips = abs(entry - sl) * 10000

    entry_note = str(getattr(sig, "entry_note",    "") or "")
    ez_top     = float(getattr(sig, "entry_zone_top", 0) or 0)
    ez_bot     = float(getattr(sig, "entry_zone_bot", 0) or 0)
    sl_struct  = str(getattr(sig, "sl_structure",   "") or "")
    rsi_val    = float(getattr(sig, "momentum_rsi",   0) or 0)
    mom_ok     = bool(getattr(sig, "momentum_ok",    False))
    candle_pat = str(getattr(sig, "candle_pattern", "") or "")
    at_zone    = ez_top > 0 and ez_bot > 0   # True = price is AT an OB/FVG

    border_c   = "#00D4AA" if is_buy else "#FF4B6E"

    # Zone info badge (shown in header)
    if at_zone:
        zone_badge = (f'<span style="font-size:0.72rem;background:#00D4AA1A;color:#00D4AA;'
                      f'border:1px solid #00D4AA44;border-radius:6px;padding:2px 8px;">✅ AT OB/FVG</span>')
    else:
        zone_badge = (f'<span style="font-size:0.72rem;background:#F5C5181A;color:#F5C518;'
                      f'border:1px solid #F5C51844;border-radius:6px;padding:2px 8px;">⚡ MARKET</span>')

    # Entry note — truncate cleanly
    note_display = (entry_note[:55] + "…") if len(entry_note) > 55 else entry_note

    # OB/FVG zone reference box (shown below table if at zone)
    zone_html = ""
    if at_zone:
        zone_html = (
            f'<div style="margin:5px 0;padding:5px 10px;background:#00D4AA0A;'
            f'border-left:2px solid #00D4AA55;border-radius:0 6px 6px 0;font-size:0.75rem;">'
            f'<span style="color:#00D4AA;font-weight:700;">📍 Zone:</span> '
            f'<span style="color:#E8EDF5;font-family:monospace;">{fmt(ez_bot)} – {fmt(ez_top)}</span>'
            f'<span style="color:#6B7A99;margin-left:8px;">{note_display}</span></div>'
        )

    def tp_row(label, price, label_color, action_text):
        if not price: return ""
        pips = abs(price - entry) * 10000
        rr   = round(abs(price - entry) / abs(entry - sl), 1) if abs(entry - sl) > 0 else 0
        return (
            f'<tr style="border-bottom:1px solid #1E2A4215;">'
            f'<td style="color:{label_color};padding:5px 8px;font-weight:700;">{label}</td>'
            f'<td style="font-family:monospace;color:{label_color};padding:5px 8px;'
            f'font-weight:800;font-size:1rem;">{fmt(price)}</td>'
            f'<td style="color:#6B7A99;font-size:0.78rem;padding:5px 8px;">'
            f'+{pips:.0f} pips &nbsp;·&nbsp; {rr}R</td>'
            f'<td style="color:{label_color};font-size:0.72rem;padding:5px 8px;'
            f'opacity:0.85;">{action_text}</td></tr>'
        )

    rsi_c        = "#00D4AA" if mom_ok else "#F5C518"
    mom_color    = "#00D4AA" if mom_ok else "#F5C518"
    mom_text     = "✅ Aligned" if mom_ok else "⚠️ Weak"
    candle_html  = f'<span style="color:#F5C518;font-size:0.78rem;">{candle_pat}</span>' if candle_pat else ""
    sl_struct_display = (sl_struct[:40] + "…") if len(sl_struct) > 40 else sl_struct

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,#0D1117,#0f1923);
         border:1px solid {border_c}33;border-left:3px solid {border_c};
         border-radius:12px;padding:1rem 1.2rem;margin:0.4rem 0;">

        <!-- Header -->
        <div style="display:flex;justify-content:space-between;align-items:center;
             margin-bottom:10px;flex-wrap:wrap;gap:6px;">
            <div>
                <span style="font-weight:800;font-size:1.1rem;color:#E8EDF5;">{sig.symbol}</span>
                <span class="signal-badge {dir_badge}" style="margin-left:8px;">{sig.direction}</span>
                <span style="font-size:0.72rem;color:#6B7A99;margin-left:6px;">
                    {sig.timeframe} · {sig.strategy.upper()}
                </span>
            </div>
            <div style="display:flex;gap:8px;align-items:center;">
                {zone_badge}
                <span class="signal-badge {score_cls}">{score}%</span>
            </div>
        </div>

        <!-- Price table -->
        <table style="width:100%;border-collapse:collapse;margin-bottom:4px;">
            <tr style="border-bottom:1px solid #1E2A42;">
                <td style="color:#6B7A99;padding:5px 8px;">Entry</td>
                <td style="font-family:monospace;color:#E8EDF5;padding:5px 8px;
                    font-weight:800;font-size:1.05rem;">{fmt(entry)}</td>
                <td colspan="2" style="color:#6B7A99;font-size:0.76rem;padding:5px 8px;">
                    Enter at market price now</td>
            </tr>
            <tr style="border-bottom:1px solid #1E2A42;">
                <td style="color:#FF4B6E;padding:5px 8px;font-weight:700;">SL</td>
                <td style="font-family:monospace;color:#FF4B6E;padding:5px 8px;
                    font-weight:800;font-size:1.05rem;">{fmt(sl)}</td>
                <td style="color:#6B7A99;font-size:0.78rem;padding:5px 8px;">
                    -{risk_pips:.0f} pips &nbsp;·&nbsp; 1R</td>
                <td style="color:#6B7A99;font-size:0.72rem;padding:5px 8px;max-width:160px;
                    overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                    {sl_struct_display}</td>
            </tr>
            {tp_row("TP1 ⭐", tp1, "#00D4AA", "Close 50% → Move SL to BE")}
            {tp_row("TP2",    tp2, "#3B82F6", "Close 30% → Trail SL")}
            {tp_row("TP3",    tp3, "#8B5CF6", "Let it run")}
        </table>

        {zone_html}

        <!-- Momentum -->
        <div style="display:flex;gap:1.2rem;font-size:0.78rem;margin-top:6px;
             flex-wrap:wrap;align-items:center;">
            <span style="color:#6B7A99;">RSI: <b style="color:{rsi_c};">{rsi_val:.0f}</b></span>
            <span style="color:#6B7A99;">Momentum:
                <b style="color:{mom_color};">{mom_text}</b></span>
            {candle_html}
        </div>

        <!-- Score bar -->
        <div class="score-bar-container" style="margin-top:8px;">
            <div class="score-bar {bar_cls}" style="width:{score}%;"></div>
        </div>

        <!-- TP strategy -->
        <div style="margin-top:8px;padding:6px 10px;background:#00D4AA06;
             border-left:2px solid #00D4AA33;border-radius:0 6px 6px 0;
             font-size:0.75rem;color:#6B7A99;line-height:1.6;">
            💡 <b style="color:#00D4AA;">TP Strategy:</b>
            TP1 hit → Close 50% →
            Move SL to <b style="color:#E8EDF5;">Breakeven ({fmt(entry)})</b> →
            TP2/TP3 runs <b style="color:#00D4AA;">risk-free</b>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# GEMINI VERDICT CARD
# ══════════════════════════════════════════════════════════════
def _render_gemini_verdict(gemini: dict):
    """Rich Gemini v4 verdict card."""
    verdict      = str(gemini.get("verdict") or "CAUTION")
    confidence   = int(gemini.get("confidence") or 50)
    reason       = str(gemini.get("reason") or "")
    risk_note    = str(gemini.get("risk_note") or "")
    best_entry   = str(gemini.get("best_entry") or "").replace("_", " ")
    sl_quality   = str(gemini.get("sl_quality") or "")
    tp1_prob     = int(gemini.get("tp1_probability") or 0)
    pos_size     = str(gemini.get("position_size") or "FULL")
    close_plan   = str(gemini.get("partial_close") or "")
    news_impact  = bool(gemini.get("news_impact") or False)
    news_sinhala = str(gemini.get("news_sinhala") or "")
    sl_adjust    = gemini.get("sl_adjust")
    ai_powered   = bool(gemini.get("ai_powered") or True)
    pre_filtered = bool(gemini.get("pre_filtered") or False)

    color = {"CONFIRM":"#00D4AA","REJECT":"#FF4B6E","CAUTION":"#F5C518"}.get(verdict,"#6B7A99")
    icon  = {"CONFIRM":"✅","REJECT":"❌","CAUTION":"⚠️"}.get(verdict,"🤖")
    badge = "🤖 Gemini AI" if ai_powered else "📊 Rule-based"
    if pre_filtered: badge += " · Pre-filtered"

    # SL quality badge
    slq_colors = {"GOOD":"#00D4AA","TOO_TIGHT":"#F5C518","TOO_WIDE":"#FF4B6E","MISPLACED":"#FF4B6E"}
    slq_c = slq_colors.get(sl_quality, "#6B7A99")
    slq_html = (f'<span style="font-size:0.72rem;background:{slq_c}22;color:{slq_c};'
                f'border:1px solid {slq_c}44;border-radius:6px;padding:1px 8px;margin-left:8px;">'
                f'SL: {sl_quality.replace("_"," ")}</span>') if sl_quality else ""

    # TP1 probability bar
    tp_c = "#00D4AA" if tp1_prob >= 60 else ("#F5C518" if tp1_prob >= 40 else "#FF4B6E")
    tp_bar = (f'<div style="margin:6px 0 4px;">'
              f'<span style="font-size:0.72rem;color:#6B7A99;">TP1 Probability: </span>'
              f'<span style="font-size:0.72rem;color:{tp_c};font-weight:700;">{tp1_prob}%</span>'
              f'<div style="background:#1E2A42;border-radius:4px;height:5px;margin-top:3px;">'
              f'<div style="background:{tp_c};width:{min(tp1_prob,100)}%;height:5px;border-radius:4px;"></div>'
              f'</div></div>') if tp1_prob else ""

    # Position size badge
    ps_c = {"FULL":"#00D4AA","HALF":"#F5C518","QUARTER":"#8B5CF6","SKIP":"#FF4B6E"}.get(pos_size,"#6B7A99")
    pos_html = (f'<span style="font-size:0.72rem;background:{ps_c}22;color:{ps_c};'
                f'border:1px solid {ps_c}44;border-radius:6px;padding:1px 8px;">'
                f'📊 {pos_size} size</span>')

    # News alert
    news_html = ""
    if news_impact and news_sinhala:
        news_html = (f'<div style="margin-top:8px;padding:8px 12px;'
                     f'background:rgba(245,197,24,0.08);border-left:3px solid #F5C518;'
                     f'border-radius:0 6px 6px 0;font-size:0.82rem;">'
                     f'<b style="color:#F5C518;">📰 News Alert — </b>'
                     f'<span style="color:#E8EDF5;">{news_sinhala}</span></div>')

    # SL adjust suggestion
    sl_adj_html = ""
    if sl_adjust and isinstance(sl_adjust, dict):
        sl_adj_html = (f'<div style="margin-top:6px;padding:6px 10px;'
                       f'background:rgba(139,92,246,0.08);border-left:3px solid #8B5CF6;'
                       f'border-radius:0 6px 6px 0;font-size:0.8rem;">'
                       f'<b style="color:#8B5CF6;">🎯 SL Adjust: </b>'
                       f'<code>{sl_adjust.get("price","")}</code>'
                       f' — {sl_adjust.get("reason","")}</div>')

    st.markdown(f"""
    <div style="background:linear-gradient(135deg,{color}0D,{color}04);
         border:1px solid {color}33;border-radius:12px;
         padding:1rem 1.2rem;margin:0.6rem 0;">
        <div style="display:flex;justify-content:space-between;align-items:center;
             margin-bottom:8px;flex-wrap:wrap;gap:6px;">
            <span style="font-weight:700;color:{color};font-size:1.05rem;">
                {icon} {verdict}{slq_html}
            </span>
            <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
                {pos_html}
                <span style="font-size:0.72rem;color:#6B7A99;font-family:monospace;">
                    {badge} · conf {confidence}%
                </span>
            </div>
        </div>
        <div style="font-size:0.85rem;color:#E8EDF5;margin-bottom:4px;line-height:1.5;">
            {reason}
        </div>
        {tp_bar}
        <div style="display:flex;gap:1.5rem;font-size:0.78rem;margin-top:4px;flex-wrap:wrap;">
            <span style="color:#6B7A99;">⚡ Entry: <b style="color:#E8EDF5">{best_entry}</b></span>
            <span style="color:#6B7A99;">📋 <span style="color:#8B5CF6">{close_plan}</span></span>
        </div>
        <div style="font-size:0.78rem;color:#F5C518;margin-top:5px;">⚠️ {risk_note}</div>
        {news_html}{sl_adj_html}
    </div>
    """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# SIGNALS PAGE
# ══════════════════════════════════════════════════════════════
def render_signals():
    st.markdown("## 🎯 Trade Signals")

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        strategy = st.selectbox("Strategy", ["swing", "short"],
                                format_func=lambda x: "📈 Swing (H4/D1)" if x == "swing" else "⚡ Short-Term (M15/H1)")
    with col2:
        category = st.selectbox("Category", list(SYMBOL_CATEGORIES.keys()))
        cat_symbols = SYMBOL_CATEGORIES[category]
    with col3:
        min_score = st.slider("Min Score (%)", 0, 100, 20, 5)

    selected_symbols = st.multiselect(
        "Select Symbols", cat_symbols,
        default=cat_symbols[:6],
        help="Select up to 10 pairs for analysis"
    )
    if len(selected_symbols) > 10:
        st.warning("⚠️ Maximum 10 symbols at a time to avoid timeouts.")
        selected_symbols = selected_symbols[:10]

    if st.button("🔄 Refresh Signals", use_container_width=False):
        st.cache_data.clear()

    if not selected_symbols:
        st.info("Please select at least one symbol.")
        return

    with st.spinner(f"Analysing {len(selected_symbols)} pairs with EW + SMC…"):
        signals = generate_all_signals(selected_symbols, strategy, min_score=min_score)

    if not signals:
        st.info(
            f"No signals found for the selected pairs at **{min_score}%** threshold.\n\n"
            f"Try: lowering Min Score → 20%, or selecting different pairs / strategy."
        )
        # Show raw trend table as fallback
        st.markdown("#### 📊 Trend Overview (fallback)")
        rows = []
        for sym in selected_symbols[:8]:
            try:
                tf = "D1" if strategy == "swing" else "H1"
                df = get_ohlcv(sym, tf)
                if df is not None and not df.empty:
                    c = df["close"]
                    trend = "🟢 Bullish" if c.iloc[-1] > c.iloc[-20] else "🔴 Bearish"
                    chg = (c.iloc[-1] - c.iloc[-20]) / c.iloc[-20] * 100
                    rows.append({"Symbol": sym, "Trend": trend, "20-bar Chg %": f"{chg:+.2f}%",
                                 "Price": f"{c.iloc[-1]:.5f}"})
            except Exception:
                pass
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        return

    # Gemini available check
    gemini_keys_available = len(_get_api_keys()) > 0

    # ── Auto-capture summary ──────────────────────────────────────────────
    db       = st.session_state.db
    username = st.session_state.user.get("username","")
    cfg      = get_user_settings(db, username) if db else {}
    auto_on  = str(cfg.get("auto_capture","true")).lower() == "true"
    min_sc   = int(cfg.get("min_score", 40) or 40)

    auto_col, manual_col = st.columns([2,1])
    with auto_col:
        if auto_on:
            st.success(f"🤖 Auto-capture ON — signals ≥{min_sc}% score saved automatically")
        else:
            st.warning("⚙️ Auto-capture OFF — enable in ⚙️ My Settings")
    with manual_col:
        if st.button("⚙️ Capture Settings", use_container_width=True):
            st.session_state.page = "settings"; st.rerun()

    st.markdown(
        f"**{len(signals)} signal(s) found** "
        f"{'🤖 Gemini AI — CONFIRM-only auto-capture' if gemini_keys_available else '⚠️ Add Gemini keys for AI analysis'}"
    )

    if not gemini_keys_available:
        st.warning(
            "⚠️ **Gemini API keys නෑ.** Admin Panel → Gemini section → keys add කරන්න.\n\n"
            "**Secrets format:**\n```toml\ngemini_api_keys = \"AIzaSy...key1,AIzaSy...key2\"\n```\n"
            "Keys නැතිව signals generate වේ, Gemini verdict නෑ, auto-capture off."
        )
    else:
        # Quick connection check (cached 60s)
        keys_list = _get_api_keys()
        st.caption(f"🤖 {len(keys_list)} Gemini key(s) loaded · CONFIRM-only auto-capture · "
                   f"Admin Panel → test connection if AI not working")

    # ── Per-signal loop ─────────────────────────────────────────────────────
    for sig in signals:
        tp2 = sig.tp2_price
        tp3 = sig.tp3_price

        # ── Call Gemini with ALL new v4 fields ──────────────────────────
        gemini = None
        if gemini_keys_available:
            try:
                gemini = get_gemini_confirmation(
                    symbol            = sig.symbol,
                    direction         = sig.direction,
                    entry_price       = sig.entry_price,
                    sl_price          = sig.sl_price,
                    tp_price          = sig.tp_price,
                    tp2               = tp2 or 0.0,
                    tp3               = tp3 or 0.0,
                    risk_reward       = sig.risk_reward,
                    probability_score = sig.probability_score,
                    strategy          = sig.strategy,
                    timeframe         = sig.timeframe,
                    ew_pattern        = sig.ew_pattern,
                    smc_bias          = sig.smc_bias,
                    confluences_str   = "|".join(sig.confluences),
                    ew_trend          = getattr(sig, "ew_trend", ""),
                    current_wave      = getattr(sig, "current_wave", ""),
                    ew_confidence     = getattr(sig, "ew_confidence", 0.0),
                    wave3_extended    = getattr(sig, "wave3_extended", False),
                    last_bos          = getattr(sig, "last_bos", "None"),
                    last_choch        = getattr(sig, "last_choch", "None"),
                    current_ob        = getattr(sig, "current_ob_str", "None"),
                    nearest_fvg       = getattr(sig, "nearest_fvg_str", "None"),
                    price_zone        = getattr(sig, "price_zone", "?"),
                    liq_sweeps        = getattr(sig, "liq_sweeps_str", "None"),
                )
            except Exception:
                gemini = None

        gemini_verdict = gemini.get("verdict", "CAUTION") if gemini else "CAUTION"
        tp1_prob       = gemini.get("tp1_probability", 0) if gemini else 0
        ai_powered     = gemini.get("ai_powered", False) if gemini else False

        # ── Auto-capture: CONFIRM only ─────────────────────────────────
        auto_captured = False
        auto_msg      = ""
        if auto_on and db and gemini_verdict == "CONFIRM":
            ok, msg = auto_capture_signal(db, sig, username, gemini_verdict)
            if ok:
                auto_captured = True
                auto_msg      = msg

        # ── Expander title ─────────────────────────────────────────────
        v_icon = {"CONFIRM":"✅","REJECT":"❌","CAUTION":"⚠️"}.get(gemini_verdict,"🤖")
        ai_tag = f" {v_icon}" if gemini else ""
        news_tag = " 📰" if (gemini and gemini.get("news_impact")) else ""
        capture_tag = " 💾" if auto_captured else ""
        prob_tag = f" TP:{tp1_prob}%" if tp1_prob else ""
        qf = getattr(sig, "quality_flags", [])
        w3_tag = " ⚡" if any("Wave 3" in f for f in qf) else ""

        expander_label = (
            f"{'🟢' if sig.direction=='BUY' else '🔴'} "
            f"{sig.symbol} {sig.direction}"
            f" — Score: {sig.probability_score}%"
            f"{ai_tag}{prob_tag}{w3_tag}{news_tag}{capture_tag}"
        )

        with st.expander(expander_label, expanded=(sig.probability_score >= 65
                                                    or gemini_verdict == "CONFIRM")):

            # ── Quality flags row ──────────────────────────────────────
            if qf:
                flags_html = " &nbsp;".join(
                    f'<span style="font-size:0.72rem;background:#1E2A42;'
                    f'color:#E8EDF5;border-radius:6px;padding:2px 8px;">{f}</span>'
                    for f in qf[:6]
                )
                st.markdown(f'<div style="margin-bottom:8px;">{flags_html}</div>',
                            unsafe_allow_html=True)

            # ── Signal card ────────────────────────────────────────────
            _render_signal_card(sig)

            # SL structure label
            sl_struct = getattr(sig, "sl_structure", "")
            if sl_struct:
                st.markdown(
                    f'<div style="font-size:0.75rem;color:#8B5CF6;margin:4px 0 8px;">'
                    f'🛡️ SL behind: {sl_struct}</div>',
                    unsafe_allow_html=True
                )

            # ── Gemini verdict card ────────────────────────────────────
            if gemini:
                _render_gemini_verdict(gemini)

            # Auto-capture success banner
            if auto_captured:
                st.success(f"🤖 Auto-captured → Active Trades ✅ {auto_msg}")

            # ── Confluence + EW/SMC details ────────────────────────────
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**📊 Confluences:**")
                for c in sig.confluences:
                    clr = "#00D4AA" if "✅" in c else ("#F5C518" if "⚠️" in c else "#E8EDF5")
                    st.markdown(
                        f'<div style="font-size:0.82rem;color:{clr};margin:2px 0;">{c}</div>',
                        unsafe_allow_html=True
                    )
            with col_b:
                zone   = getattr(sig, "price_zone", "?")
                wave   = getattr(sig, "current_wave", "?")
                ew_cf  = getattr(sig, "ew_confidence", 0)
                zc     = {"DISCOUNT":"#00D4AA","PREMIUM":"#FF4B6E"}.get(zone,"#F5C518")
                st.markdown(f"""
                <div style="font-size:0.82rem;line-height:1.9;">
                    <div><b>EW Pattern:</b> <code>{sig.ew_pattern}</code> · Wave <code>{wave}</code></div>
                    <div><b>EW Conf:</b> {ew_cf*100:.0f}%</div>
                    <div><b>Zone:</b> <span style="color:{zc};font-weight:600">{zone}</span></div>
                    <div><b>BOS:</b> {getattr(sig,"last_bos","?")}</div>
                    <div><b>CHoCH:</b> {getattr(sig,"last_choch","?")}</div>
                    <div style="font-size:0.72rem;color:#6B7A99;margin-top:4px;">{sig.generated_at} LKT</div>
                </div>
                """, unsafe_allow_html=True)

            # ── Manual add button (for REJECT / CAUTION) ──────────────
            if gemini_verdict == "REJECT":
                st.error("❌ Gemini REJECT — do NOT trade this setup.")
            else:
                col_btn, col_warn = st.columns([1, 2])
                with col_btn:
                    btn_lbl = (f"{'💾 Re-add' if auto_captured else '➕ Add'} to Active Trades")
                    if st.button(btn_lbl,
                                 key=f"add_{sig.trade_id}",
                                 use_container_width=True):
                        ss_w, err = get_fresh_spreadsheet()
                        if err:
                            st.error(f"❌ {err}")
                        else:
                            trade = {
                                "trade_id":          sig.trade_id,
                                "username":          username,
                                "symbol":            sig.symbol,
                                "direction":         sig.direction,
                                "entry_price":       str(sig.entry_price),
                                "sl_price":          str(sig.sl_price),
                                "tp_price":          str(sig.tp_price),
                                "tp2_price":         str(tp2 or ""),
                                "tp3_price":         str(tp3 or ""),
                                "lot_size":          str(sig.lot_size),
                                "open_time":         sig.generated_at,
                                "strategy":          sig.strategy,
                                "timeframe":         sig.timeframe,
                                "probability_score": str(sig.probability_score),
                                "ew_pattern":        sig.ew_pattern,
                                "smc_bias":          sig.smc_bias[:120],
                                "status":            "open",
                                "current_price":     str(sig.entry_price),
                                "pnl":               "0",
                                "gemini_verdict":    gemini_verdict,
                            }
                            ok, msg = add_active_trade(ss_w, trade)
                            if ok: st.success(f"✅ {msg}")
                            else:  st.error(f"❌ {msg}")
                with col_warn:
                    if gemini_verdict == "CAUTION":
                        if gemini is not None:
                            sl_q       = str(gemini.get("sl_quality") or "")
                            reason_txt = str(gemini.get("reason") or "Moderate confluence.")[:80]
                        else:
                            sl_q, reason_txt = "", "Moderate confluence — verify manually."
                        st.warning(
                            f"⚠️ CAUTION — {reason_txt}"
                            + (f" · SL: {sl_q}" if sl_q else "")
                        )


# ══════════════════════════════════════════════════════════════
# CHART ANALYSIS PAGE
# ══════════════════════════════════════════════════════════════


# TradingView symbol conversion
_TV_SYMBOL_MAP = {
    # Forex Majors
    "EURUSD":"FX:EURUSD","GBPUSD":"FX:GBPUSD","USDJPY":"FX:USDJPY",
    "USDCHF":"FX:USDCHF","AUDUSD":"FX:AUDUSD","NZDUSD":"FX:NZDUSD",
    "USDCAD":"FX:USDCAD",
    # Cross Pairs
    "EURGBP":"FX:EURGBP","EURJPY":"FX:EURJPY","GBPJPY":"FX:GBPJPY",
    "AUDJPY":"FX:AUDJPY","CADJPY":"FX:CADJPY","CHFJPY":"FX:CHFJPY",
    "EURCHF":"FX:EURCHF","EURAUD":"FX:EURAUD","EURCAD":"FX:EURCAD",
    "GBPCHF":"FX:GBPCHF","GBPAUD":"FX:GBPAUD","GBPCAD":"FX:GBPCAD",
    "AUDCAD":"FX:AUDCAD","AUDCHF":"FX:AUDCHF","AUDNZD":"FX:AUDNZD",
    "NZDJPY":"FX:NZDJPY","NZDCAD":"FX:NZDCAD","NZDCHF":"FX:NZDCHF",
    "CADCHF":"FX:CADCHF",
    # Exotic
    "USDSEK":"FX:USDSEK","USDNOK":"FX:USDNOK","USDSGD":"FX:USDSGD",
    "USDMXN":"FX:USDMXN","USDZAR":"FX:USDZAR","USDTRY":"FX:USDTRY",
    # Metals
    "XAUUSD":"TVC:GOLD","XAGUSD":"TVC:SILVER","XPTUSD":"TVC:PLATINUM",
    # Oil
    "USOIL":"TVC:USOIL","UKOIL":"TVC:UKOIL",
    # Crypto
    "BTCUSD":"BINANCE:BTCUSDT","ETHUSD":"BINANCE:ETHUSDT",
    "BNBUSD":"BINANCE:BNBUSDT","SOLUSD":"BINANCE:SOLUSDT",
    "XRPUSD":"BINANCE:XRPUSDT",
    # Indices
    "US30":"TVC:DJI","NAS100":"NASDAQ:NDX","SPX500":"SP:SPX",
    "UK100":"TVC:UKX","GER40":"XETR:DAX","JPN225":"TVC:NI225",
}

_TV_TF_MAP = {
    "M1":"1","M5":"5","M15":"15","M30":"30",
    "H1":"60","H4":"240","D1":"D","W1":"W",
}


def _tv_ticker_widget(symbols: list) -> str:
    """TradingView Ticker Tape widget HTML — live scrolling prices."""
    syms_json = ",".join(
        f'{{"proName":"{_TV_SYMBOL_MAP.get(s, "FX:"+s)}","title":"{s}"}}'
        for s in symbols[:12]
    )
    return f"""
<div class="tradingview-widget-container" style="margin-bottom:12px;">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-ticker-tape.js"
    async>
  {{
    "symbols": [{syms_json}],
    "showSymbolLogo": true,
    "isTransparent": true,
    "displayMode": "adaptive",
    "colorTheme": "dark",
    "locale": "en"
  }}
  </script>
</div>"""


def _tv_chart_widget(tv_symbol: str, timeframe: str,
                     height: int = 520, studies: list = None) -> str:
    """TradingView Advanced Chart widget — full live interactive chart."""
    tf   = _TV_TF_MAP.get(timeframe, "60")
    stud = studies or []
    stud_json = ",".join(f'"{s}"' for s in stud)
    return f"""
<div class="tradingview-widget-container" style="height:{height}px;width:100%;">
  <div id="tradingview_chart" style="height:100%;width:100%;"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget({{
    "autosize": true,
    "symbol": "{tv_symbol}",
    "interval": "{tf}",
    "timezone": "Asia/Colombo",
    "theme": "dark",
    "style": "1",
    "locale": "en",
    "toolbar_bg": "#0D1117",
    "enable_publishing": false,
    "hide_top_toolbar": false,
    "hide_legend": false,
    "save_image": true,
    "container_id": "tradingview_chart",
    "studies": [{stud_json}],
    "overrides": {{
      "mainSeriesProperties.candleStyle.upColor":       "#00D4AA",
      "mainSeriesProperties.candleStyle.downColor":     "#FF4B6E",
      "mainSeriesProperties.candleStyle.borderUpColor": "#00D4AA",
      "mainSeriesProperties.candleStyle.borderDownColor":"#FF4B6E",
      "mainSeriesProperties.candleStyle.wickUpColor":   "#00D4AA",
      "mainSeriesProperties.candleStyle.wickDownColor": "#FF4B6E",
      "paneProperties.background":                      "#0D1117",
      "paneProperties.backgroundType":                  "solid",
      "paneProperties.gridLinesMode":                   "Both",
      "paneProperties.vertGridProperties.color":        "#1E2A4222",
      "paneProperties.horzGridProperties.color":        "#1E2A4222",
      "scalesProperties.textColor":                     "#6B7A99"
    }}
  }});
  </script>
</div>"""


def _tv_mini_widget(tv_symbol: str, height: int = 220) -> str:
    """TradingView Mini Symbol Overview — compact live price + sparkline."""
    return f"""
<div class="tradingview-widget-container" style="height:{height}px;">
  <div class="tradingview-widget-container__widget" style="height:100%;"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-mini-symbol-overview.js"
    async>
  {{
    "symbol": "{tv_symbol}",
    "width": "100%",
    "height": {height},
    "locale": "en",
    "dateRange": "1D",
    "colorTheme": "dark",
    "isTransparent": true,
    "autosize": false,
    "largeChartUrl": ""
  }}
  </script>
</div>"""


def _tv_technical_analysis_widget(tv_symbol: str, timeframe: str) -> str:
    """TradingView Technical Analysis widget — buy/sell/neutral gauge."""
    tf_map = {"M5":"5m","M15":"15m","H1":"1h","H4":"4h","D1":"1D"}
    tf = tf_map.get(timeframe, "1h")
    return f"""
<div class="tradingview-widget-container">
  <div class="tradingview-widget-container__widget"></div>
  <script type="text/javascript"
    src="https://s3.tradingview.com/external-embedding/embed-widget-technical-analysis.js"
    async>
  {{
    "interval": "{tf}",
    "width": "100%",
    "isTransparent": true,
    "height": 400,
    "symbol": "{tv_symbol}",
    "showIntervalTabs": true,
    "displayMode": "single",
    "locale": "en",
    "colorTheme": "dark"
  }}
  </script>
</div>"""


def render_analysis():
    st.markdown("## 🔬 Live Chart Analysis")

    from modules.market_data import inject_live_price

    # ── Controls row ──────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([1.2, 1.2, 1, 0.8])
    with col1:
        category = st.selectbox("Category", list(SYMBOL_CATEGORIES.keys()), key="analysis_cat")
        symbol   = st.selectbox("Symbol", SYMBOL_CATEGORIES[category], key="analysis_sym")
    with col2:
        timeframe = st.selectbox("Timeframe",
                                 ["M1","M5","M15","M30","H1","H4","D1","W1"],
                                 index=4, key="analysis_tf")
        col2a, col2b = st.columns(2)
        with col2a:
            show_ew  = st.checkbox("Elliott Wave", value=True,  key="analysis_ew")
        with col2b:
            show_smc = st.checkbox("SMC Zones",    value=True,  key="analysis_smc")
    with col3:
        show_rsi  = st.checkbox("RSI",  value=True,  key="analysis_rsi")
        show_macd = st.checkbox("MACD", value=False, key="analysis_macd")
        show_bb   = st.checkbox("BB",   value=False, key="analysis_bb")
    with col4:
        st.markdown("<div style='margin-top:0.3rem;'></div>", unsafe_allow_html=True)
        if st.button("🔄 Refresh", use_container_width=True, key="analysis_refresh"):
            st.cache_data.clear()
            st.rerun()
        auto_ref = st.checkbox("⏱ Auto 30s", value=False, key="analysis_auto")

    # Auto-refresh
    if auto_ref:
        import time as _time
        last = st.session_state.get("_analysis_last_ref", 0)
        if _time.time() - last > 30:
            st.session_state["_analysis_last_ref"] = _time.time()
            st.cache_data.clear()
            st.rerun()

    tv_sym = _TV_SYMBOL_MAP.get(symbol, f"FX:{symbol}")

    # ── Live Ticker Tape — top of page ────────────────────────
    ticker_syms = SYMBOL_CATEGORIES.get("⭐ Major Pairs", [])[:8] + [symbol]
    ticker_syms = list(dict.fromkeys(ticker_syms))   # deduplicate, preserve order
    st.components.v1.html(_tv_ticker_widget(ticker_syms), height=72, scrolling=False)

    # ── Tab layout: Live Chart | Technical Analysis | EW/SMC ──
    tab_chart, tab_ta, tab_ewsmc = st.tabs([
        "📈 Live TradingView Chart",
        "🎯 Technical Analysis",
        "🌊 EW + SMC Analysis",
    ])

    with tab_chart:
        # Build studies list
        studies = []
        if show_rsi:  studies.append("RSI@tv-basicstudies")
        if show_macd: studies.append("MACD@tv-basicstudies")
        if show_bb:   studies.append("BB@tv-basicstudies")

        st.components.v1.html(
            _tv_chart_widget(tv_sym, timeframe, height=580, studies=studies),
            height=590, scrolling=False
        )
        st.caption(
            f"📡 Live TradingView chart — {symbol} {timeframe} · "
            f"Timezone: Colombo (LKT) · Candles: 🟢 Bullish #00D4AA · 🔴 Bearish #FF4B6E"
        )

    with tab_ta:
        col_mini, col_gauge = st.columns([1, 1])
        with col_mini:
            st.markdown(f"**{symbol} — Live Price**")
            st.components.v1.html(
                _tv_mini_widget(tv_sym, height=220),
                height=230, scrolling=False
            )
        with col_gauge:
            st.markdown(f"**Technical Rating — {timeframe}**")
            st.components.v1.html(
                _tv_technical_analysis_widget(tv_sym, timeframe),
                height=420, scrolling=False
            )

    with tab_ewsmc:
        # Fetch + inject live price for EW/SMC
        with st.spinner(f"Fetching {symbol} {timeframe} OHLCV..."):
            df_raw = get_ohlcv(symbol, timeframe)

        if df_raw is None or df_raw.empty:
            st.error(f"⚠️ OHLCV data unavailable for **{symbol} {timeframe}**.")
            st.info("💡 Try H1 or D1 timeframe. Live TradingView chart above still works.")
        else:
            df, live_price, fetch_time = inject_live_price(df_raw, symbol)
            if not live_price:
                df = df_raw

            # Live price banner
            if live_price and fetch_time:
                diff       = live_price - float(df_raw.iloc[-1]["close"])
                diff_pips  = abs(diff) * 10000
                diff_c     = "#00D4AA" if diff >= 0 else "#FF4B6E"
                diff_arrow = "▲" if diff >= 0 else "▼"
                st.markdown(
                    f'<div style="background:#0D1117;border:1px solid #00D4AA33;'
                    f'border-radius:8px;padding:6px 14px;margin-bottom:8px;'
                    f'display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                    f'<span style="font-size:0.8rem;color:#6B7A99;">📡 Live injected</span>'
                    f'<span style="font-family:monospace;">'
                    f'<b style="color:#E8EDF5;">{symbol}</b>&nbsp;'
                    f'<span style="color:{diff_c};font-weight:700;">{live_price:.5f}</span>'
                    f'&nbsp;<span style="font-size:0.75rem;color:{diff_c};">'
                    f'{diff_arrow} {diff_pips:.1f} pips</span></span>'
                    f'<span style="font-size:0.75rem;color:#6B7A99;">🕐 {fetch_time}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            # EW/SMC analysis
            with st.spinner("Running EW + SMC analysis on live data..."):
                ew_result  = identify_elliott_waves(df) if show_ew  else None
                smc_result = analyze_smc(df)            if show_smc else None

            # Plotly overlay chart (EW+SMC annotations)
            fig = create_candlestick_chart(df, symbol, timeframe,
                                           ew_result  if show_ew  else None,
                                           smc_result if show_smc else None)
            st.plotly_chart(fig, use_container_width=True)

            # EW + SMC side-by-side summary
            col_ew, col_smc = st.columns(2)

            if ew_result and show_ew:
                with col_ew:
                    st.markdown("### 🌊 Elliott Wave")
                    w3x = '<span style="background:#F5C51822;color:#F5C518;border:1px solid #F5C51844;border-radius:6px;padding:1px 6px;font-size:0.7rem;">⚡ Wave 3 Extended</span>' if getattr(ew_result,"wave3_extended",False) else ""
                    def fmtp(v):
                        if not v: return "—"
                        return f"{float(v):.5f}" if abs(float(v)) < 100 else f"{float(v):.3f}"
                    tp1e = ew_result.projected_target
                    tp2e = getattr(ew_result, "projected_tp2", None)
                    tp3e = getattr(ew_result, "projected_tp3", None)
                    st.markdown(f"""
                    <div class="metric-card">
                        <div style="font-size:0.84rem;line-height:2.0;">
                            <div><b>Pattern:</b> <code>{ew_result.pattern_type}</code> {w3x}</div>
                            <div><b>Trend:</b> <span class="{'up' if ew_result.trend=='bullish' else 'down'}">{ew_result.trend.upper()}</span> <span style="font-size:0.7rem;color:#00D4AA;">📡 live</span></div>
                            <div><b>Wave:</b> <code>{ew_result.current_wave}</code> &nbsp; <b>Conf:</b> {ew_result.confidence*100:.0f}%</div>
                            <div><b>TP1:</b> <code style="color:#00D4AA">{fmtp(tp1e)}</code></div>
                            <div><b>TP2:</b> <code style="color:#3B82F6">{fmtp(tp2e)}</code></div>
                            <div><b>TP3:</b> <code style="color:#8B5CF6">{fmtp(tp3e)}</code></div>
                            <div><b>SL:</b> <code style="color:#FF4B6E">{fmtp(ew_result.projected_sl)}</code></div>
                            <div style="color:#6B7A99;font-size:0.76rem;margin-top:4px;">{ew_result.description}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)

            if smc_result and show_smc:
                with col_smc:
                    st.markdown("### 💡 SMC Zones")
                    ob_t   = f"✅ {smc_result.current_ob.ob_type.upper()} @ {smc_result.current_ob.mid:.5f} (×{getattr(smc_result.current_ob,'touch_count',0)})" if smc_result.current_ob else "None"
                    fvg_t  = f"✅ {smc_result.nearest_fvg.fvg_type.upper()} — {smc_result.nearest_fvg.fill_pct:.0f}% filled" if smc_result.nearest_fvg else "None"
                    bos_t  = f"✅ {smc_result.last_bos.direction.upper()}" if smc_result.last_bos else "None"
                    choch_t= f"✅ {smc_result.last_choch.direction.upper()}" if smc_result.last_choch else "None"
                    sw_t   = f"⚡ {smc_result.liquidity_sweeps[-1].sweep_type.replace('_',' ').title()}" if getattr(smc_result,'liquidity_sweeps',[]) else "None"
                    cp_now = float(df["close"].iloc[-1])
                    prem   = getattr(smc_result,"premium_zone",None)
                    disc   = getattr(smc_result,"discount_zone",None)
                    if prem and cp_now >= prem:     zone_lbl,zone_c = "PREMIUM","#FF4B6E"
                    elif disc and cp_now <= disc:   zone_lbl,zone_c = "DISCOUNT","#00D4AA"
                    else:                           zone_lbl,zone_c = "EQUILIBRIUM","#F5C518"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div style="font-size:0.84rem;line-height:2.0;">
                            <div><b>Trend:</b>
                                <span class="{'up' if smc_result.trend=='bullish' else 'down'}">{smc_result.trend.upper()}</span>
                                &nbsp;<span style="font-size:0.72rem;color:{zone_c};background:{zone_c}22;border-radius:6px;padding:1px 7px;">{zone_lbl}</span>
                            </div>
                            <div><b>CHoCH:</b> <code>{choch_t}</code></div>
                            <div><b>BOS:</b>   <code>{bos_t}</code></div>
                            <div><b>OB:</b>    <code>{ob_t}</code></div>
                            <div><b>FVG:</b>   <code>{fvg_t}</code></div>
                            <div><b>Sweep:</b> <code>{sw_t}</code></div>
                            <div><b>Conf:</b>  {smc_result.confidence*100:.0f}%</div>
                            <div style="color:#6B7A99;font-size:0.76rem;margin-top:4px;">{str(smc_result.bias)[:120]}</div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)




# ══════════════════════════════════════════════════════════════
# ACTIVE TRADES PAGE
# ══════════════════════════════════════════════════════════════
def render_active_trades():
    st.markdown("## 💼 Active Trades")

    db       = st.session_state.db
    username = st.session_state.user.get("username", "")
    is_admin = st.session_state.user.get("role") == "admin"

    if not db:
        st.warning("⚠️ Database not connected.")
        return

    from modules.market_data import get_live_price

    # ── Header controls ───────────────────────────────────────
    hcol1, hcol2 = st.columns([3, 1])
    with hcol2:
        if st.button("🔄 Refresh", use_container_width=True, key="at_refresh_btn"):
            st.rerun()

    # ── Load trades ───────────────────────────────────────────
    trades_df = get_active_trades(db, None if is_admin else username)

    if trades_df.empty:
        st.info("No active trades. Go to 🎯 Trade Signals to generate and capture trades.")
        return

    # ── Fetch all live prices at once (avoid duplicate imports) ──
    symbols    = trades_df["symbol"].dropna().unique().tolist()
    live_cache = {}
    for sym in symbols:
        try:
            lp = get_live_price(sym)
            live_cache[sym] = float(lp.get("price") or 0)
        except Exception:
            live_cache[sym] = 0.0

    # ── Auto SL/TP monitor: close any hits immediately ────────
    auto_hit_count = 0
    for sym, price in live_cache.items():
        if price <= 0:
            continue
        subset = trades_df[trades_df["symbol"] == sym]
        for _, row in subset.iterrows():
            tid  = str(row.get("trade_id", ""))
            dirn = str(row.get("direction", "BUY"))
            try:
                sl_v = float(row.get("sl_price") or 0)
                tp_v = float(row.get("tp_price") or 0)
            except Exception:
                continue

            hit = None
            if dirn == "BUY":
                if tp_v > 0 and price >= tp_v: hit = "TP"
                elif sl_v > 0 and price <= sl_v: hit = "SL"
            else:
                if tp_v > 0 and price <= tp_v: hit = "TP"
                elif sl_v > 0 and price >= sl_v: hit = "SL"

            if hit and tid:
                ss_w, err = get_fresh_spreadsheet()
                if not err:
                    ok, msg = close_trade(ss_w, tid, price, hit)
                    if ok:
                        auto_hit_count += 1
                        icon = "🎉" if hit == "TP" else "🛑"
                        st.toast(f"{icon} {sym} {dirn} — {hit} Hit! {msg}", icon=icon)

    # Reload after any auto-closes
    if auto_hit_count > 0:
        get_database.clear()
        st.session_state.db, _ = get_database()
        db = st.session_state.db
        trades_df = get_active_trades(db, None if is_admin else username)
        st.success(f"✅ {auto_hit_count} trade(s) auto-closed (SL/TP hit). Moved to History.")

    if trades_df.empty:
        st.success("✅ All trades closed! See Trade History.")
        return

    st.markdown(f"**{len(trades_df)} active trade(s)**")

    # ── Per-trade cards ───────────────────────────────────────
    for row_i, (_, trade) in enumerate(trades_df.iterrows()):
        # Use row index as key suffix — prevents duplicate key even if trade_id is empty
        trade_id  = str(trade.get("trade_id", f"tid_{row_i}") or f"tid_{row_i}")
        uid       = f"{row_i}_{trade_id}"          # guaranteed unique

        symbol    = str(trade.get("symbol", ""))
        direction = str(trade.get("direction", "BUY"))
        owner     = str(trade.get("username", ""))
        strategy  = str(trade.get("strategy", ""))
        tf        = str(trade.get("timeframe", ""))
        g_verdict = str(trade.get("gemini_verdict", ""))
        opened    = str(trade.get("open_time", ""))
        score     = str(trade.get("probability_score", ""))
        ew_pat    = str(trade.get("ew_pattern", ""))

        def _fv(key, d=0.0):
            try: return float(trade.get(key) or d)
            except: return d

        entry = _fv("entry_price")
        sl    = _fv("sl_price")
        tp    = _fv("tp_price")
        tp2   = _fv("tp2_price")
        tp3   = _fv("tp3_price")
        lot   = _fv("lot_size", 0.01) or 0.01

        live_price = live_cache.get(symbol, entry) or entry
        if live_price <= 0:
            live_price = entry

        pnl        = (live_price - entry) * (1 if direction == "BUY" else -1) * lot * 100000
        pnl_color  = "#00D4AA" if pnl >= 0 else "#FF4B6E"

        # ── SL/TP proximity bars ──────────────────────────────
        def _prox(target, current, is_buy):
            """Return % progress toward target (0=entry, 100=hit)."""
            if target <= 0 or entry <= 0: return 0.0
            full = abs(target - entry)
            done = abs(current - entry)
            if full == 0: return 0.0
            pct = min(100.0, done / full * 100)
            # Correct direction
            if is_buy:
                if target > entry and current > entry: return pct
                if target < entry and current < entry: return pct
            else:
                if target < entry and current < entry: return pct
                if target > entry and current > entry: return pct
            return 0.0

        is_buy  = direction == "BUY"
        tp_pct  = _prox(tp, live_price, is_buy)
        sl_pct  = _prox(sl, live_price, not is_buy)   # SL is opposite direction

        def _bar(pct, color, label):
            w    = int(min(100, max(0, pct)))
            warn = " 🚨" if pct >= 85 else (" ⚠️" if pct >= 65 else "")
            return (
                f'<div style="margin:3px 0;">'
                f'<span style="font-size:0.72rem;color:{color};">{label}{warn} {pct:.0f}%</span>'
                f'<div style="background:#1E2A42;border-radius:4px;height:5px;margin-top:2px;">'
                f'<div style="background:{color};width:{w}%;height:5px;border-radius:4px;'
                f'transition:width 0.3s;"></div></div></div>'
            )

        tp_bar = _bar(tp_pct, "#00D4AA", "TP")
        sl_bar = _bar(sl_pct, "#FF4B6E", "SL")

        def fmt(v): return (f"{v:.5f}" if 0 < abs(v) < 100 else f"{v:.3f}") if v else "—"

        # Alert level for expander
        alert = ""
        if tp_pct >= 85: alert = " 🚨TP Near!"
        elif sl_pct >= 85: alert = " 🛑SL Near!"
        elif tp_pct >= 65: alert = " ⚠️"

        verdict_colors = {"CONFIRM":"#00D4AA","CAUTION":"#F5C518","REJECT":"#FF4B6E"}
        vc = verdict_colors.get(g_verdict, "#6B7A99")

        header = (
            f"{'🟢' if is_buy else '🔴'} {symbol} {direction}"
            f"  |  Live: {fmt(live_price)}"
            f"  |  P&L: ${pnl:+.2f}{alert}"
            + (f"  |  👤{owner}" if is_admin else "")
        )

        with st.expander(header, expanded=(tp_pct >= 65 or sl_pct >= 65)):
            col1, col2, col3 = st.columns([1.3, 1.1, 1.2])

            with col1:
                tp2_row = f'<div><b>TP2:</b> <code style="color:#3B82F6">{fmt(tp2)}</code></div>' if tp2 else ""
                tp3_row = f'<div><b>TP3:</b> <code style="color:#8B5CF6">{fmt(tp3)}</code></div>' if tp3 else ""
                st.markdown(
                    f'<div style="font-size:0.84rem;line-height:1.9;">'
                    f'<div><b>Entry:</b> <code>{fmt(entry)}</code></div>'
                    f'<div><b>Live:</b> <code style="color:#E8EDF5;font-weight:700">{fmt(live_price)}</code></div>'
                    f'<div><b>SL:</b> <code style="color:#FF4B6E">{fmt(sl)}</code></div>'
                    f'<div><b>TP1:</b> <code style="color:#00D4AA">{fmt(tp)}</code></div>'
                    f'{tp2_row}{tp3_row}</div>'
                    f'{tp_bar}{sl_bar}',
                    unsafe_allow_html=True
                )

            with col2:
                st.markdown(
                    f'<div style="font-size:0.84rem;line-height:1.9;">'
                    f'<div><b>P&L:</b> <span style="color:{pnl_color};font-family:monospace;font-weight:700">${pnl:+.2f}</span></div>'
                    f'<div><b>Score:</b> {score}%</div>'
                    f'<div><b>EW:</b> <span style="font-size:0.75rem;color:#6B7A99">{ew_pat}</span></div>'
                    f'<div><b>Strategy:</b> {strategy.upper()} {tf}</div>'
                    f'<div style="margin-top:4px;">'
                    f'<span style="font-size:0.72rem;background:{vc}22;color:{vc};'
                    f'border:1px solid {vc}44;border-radius:8px;padding:1px 8px;">'
                    f'🤖 {g_verdict or "N/A"}</span></div>'
                    f'<div style="font-size:0.72rem;color:#6B7A99;margin-top:4px;">{opened}</div>'
                    f'</div>',
                    unsafe_allow_html=True
                )

            with col3:
                # KEY FIX: use uid (row_index + trade_id) — guaranteed unique across all renders
                close_val = st.number_input(
                    "Close at",
                    value=float(round(live_price, 5)),
                    key=f"cp_{uid}",
                    format="%.5f",
                    step=0.00001,
                    label_visibility="visible",
                )
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("🎯 TP Hit", key=f"tp_{uid}", use_container_width=True):
                        ss_w, err = get_fresh_spreadsheet()
                        if err:
                            st.error(f"❌ {err}")
                        else:
                            ok, msg = close_trade(ss_w, trade_id, close_val, "TP")
                            if ok: st.toast(f"🎉 {symbol} TP Hit! {msg}"); st.rerun()
                            else: st.error(msg)
                with c2:
                    if st.button("🛑 SL Hit", key=f"sl_{uid}", use_container_width=True):
                        ss_w, err = get_fresh_spreadsheet()
                        if err:
                            st.error(f"❌ {err}")
                        else:
                            ok, msg = close_trade(ss_w, trade_id, close_val, "SL")
                            if ok: st.toast(f"🛑 {symbol} SL Hit! {msg}"); st.rerun()
                            else: st.error(msg)

                if st.button("🔒 Manual Close", key=f"mc_{uid}", use_container_width=True):
                    ss_w, err = get_fresh_spreadsheet()
                    if err:
                        st.error(f"❌ {err}")
                    else:
                        ok, msg = close_trade(ss_w, trade_id, close_val, "MANUAL")
                        if ok: st.toast(f"🔒 {symbol} closed. {msg}"); st.rerun()
                        else: st.error(msg)


# ══════════════════════════════════════════════════════════════
# TRADE HISTORY PAGE
# ══════════════════════════════════════════════════════════════
def render_history():
    st.markdown("## 📜 Trade History")
    
    db = st.session_state.db
    username = st.session_state.user.get("username")
    is_admin = st.session_state.user.get("role") == "admin"

    history_df = get_trade_history(db, None if is_admin else username) if db else pd.DataFrame()

    if history_df.empty:
        st.info("No trade history yet.")
        return

    # Performance chart
    st.plotly_chart(create_pnl_chart(history_df), use_container_width=True)

    # Stats
    history_df["pnl"] = pd.to_numeric(history_df["pnl"], errors="coerce").fillna(0)
    c1, c2, c3, c4 = st.columns(4)
    total_pnl = history_df["pnl"].sum()
    wins = (history_df["pnl"] > 0).sum()
    losses = (history_df["pnl"] <= 0).sum()
    win_rate = wins / len(history_df) * 100 if len(history_df) > 0 else 0
    avg_win = history_df[history_df["pnl"] > 0]["pnl"].mean() if wins > 0 else 0
    avg_loss = history_df[history_df["pnl"] <= 0]["pnl"].mean() if losses > 0 else 0

    for col, (label, val, clr) in zip([c1, c2, c3, c4], [
        ("Total P&L", f"${total_pnl:+.2f}", "up" if total_pnl >= 0 else "down"),
        ("Win Rate", f"{win_rate:.1f}%", "up" if win_rate > 50 else "down"),
        ("Avg Win", f"${avg_win:+.2f}", "up"),
        ("Avg Loss", f"${avg_loss:.2f}", "down"),
    ]):
        col.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">{label}</div>
            <div class="metric-value {clr}">{val}</div>
        </div>""", unsafe_allow_html=True)

    # Table
    st.markdown("### All Trades")
    display_cols = ["trade_id", "symbol", "direction", "entry_price", "close_price", "pnl", "result", "close_time"]
    show_cols = [c for c in display_cols if c in history_df.columns]
    st.dataframe(
        history_df[show_cols].sort_values("close_time", ascending=False) if "close_time" in show_cols else history_df[show_cols],
        use_container_width=True, hide_index=True
    )


# ══════════════════════════════════════════════════════════════
# SETTINGS PAGE
# ══════════════════════════════════════════════════════════════
def render_settings():
    st.markdown("## ⚙️ My Settings")
    db       = st.session_state.db
    username = st.session_state.user.get("username","")

    if not db:
        st.warning("Database not connected."); return

    cfg = get_user_settings(db, username)

    st.markdown("### 🤖 Auto-Capture")
    st.markdown("Signals page ස්කෑන් කළ විට qualifying signals **automatically** Active Trades වලට save වෙනවා.")

    col1, col2 = st.columns(2)
    with col1:
        auto_on   = st.toggle("Auto-Capture Enabled",
                              value=str(cfg.get("auto_capture","true")).lower()=="true",
                              key="s_auto")
        min_score = st.slider("Min Score Threshold (%)", 20, 90,
                              int(cfg.get("min_score",40) or 40), 5,
                              key="s_minscore",
                              help="Only signals above this score are auto-captured")
    with col2:
        st.markdown(f"""
        <div class="metric-card" style="margin-top:1.5rem;">
            <div style="font-size:0.8rem; color:#6B7A99;">Auto-capture status</div>
            <div style="font-size:1.2rem; font-weight:700; color:{'#00D4AA' if auto_on else '#FF4B6E'};">
                {'🟢 Active' if auto_on else '🔴 Disabled'}
            </div>
            <div style="font-size:0.75rem; color:#6B7A99; margin-top:4px;">
                Min score: {min_score}%
            </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 🔔 Notifications")
    col3, col4, col5 = st.columns(3)
    with col3:
        notify_tp  = st.toggle("TP Hit Alerts",  value=str(cfg.get("notify_tp","true")).lower()=="true",  key="s_ntp")
    with col4:
        notify_sl  = st.toggle("SL Hit Alerts",  value=str(cfg.get("notify_sl","true")).lower()=="true",  key="s_nsl")
    with col5:
        notify_sig = st.toggle("Signal Alerts",  value=str(cfg.get("notify_signal","true")).lower()=="true", key="s_nsig")

    st.markdown("---")
    if st.button("💾 Save Settings", use_container_width=False):
        ok, msg = save_user_settings(db, username, {
            "auto_capture":  "true" if auto_on  else "false",
            "min_score":     str(min_score),
            "notify_tp":     "true" if notify_tp  else "false",
            "notify_sl":     "true" if notify_sl  else "false",
            "notify_signal": "true" if notify_sig else "false",
        })
        if ok: st.success(f"✅ {msg}")
        else:  st.error(f"❌ {msg}")

    # Show current settings summary
    st.markdown("### 📋 Current Config")
    st.json({
        "username":       username,
        "auto_capture":   cfg.get("auto_capture","true"),
        "min_score":      cfg.get("min_score","40"),
        "notify_tp":      cfg.get("notify_tp","true"),
        "notify_sl":      cfg.get("notify_sl","true"),
        "notify_signal":  cfg.get("notify_signal","true"),
        "updated_at":     cfg.get("updated_at","—"),
    })


# ══════════════════════════════════════════════════════════════
# NOTIFICATIONS PAGE
# ══════════════════════════════════════════════════════════════
def render_notifications():
    st.markdown("## 🔔 Notifications")
    db       = st.session_state.db
    username = st.session_state.user.get("username","")

    if not db:
        st.warning("Database not connected."); return

    col1, col2 = st.columns([3,1])
    with col2:
        if st.button("✅ Mark All Read", use_container_width=True):
            mark_all_read(db, username)
            st.session_state.notif_count = 0
            st.rerun()

    notifs = get_notifications(db, username, unread_only=False)
    if notifs.empty:
        st.info("No notifications yet."); return

    for _, n in notifs.iterrows():
        ntype    = str(n.get("type",""))
        is_read  = str(n.get("is_read","false")).lower() == "true"
        msg      = str(n.get("message",""))
        created  = str(n.get("created_at",""))
        symbol   = str(n.get("symbol",""))
        direction= str(n.get("direction",""))

        icon  = {"TP":"🎉","SL":"🛑","SIGNAL":"📊","CLOSE":"🔒"}.get(ntype,"🔔")
        color = {"TP":"#00D4AA","SL":"#FF4B6E","SIGNAL":"#3B82F6","CLOSE":"#8B5CF6"}.get(ntype,"#6B7A99")
        bg    = "#111827" if is_read else "#0D1A2D"
        border= "#1E2A42" if is_read else color+"44"
        opacity = "0.6" if is_read else "1.0"

        st.markdown(f"""
        <div style="background:{bg}; border:1px solid {border}; border-left:3px solid {color};
             border-radius:8px; padding:0.8rem 1rem; margin-bottom:0.5rem; opacity:{opacity};">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <span style="font-weight:600; color:{color};">{icon} {ntype}</span>
                <span style="font-size:0.72rem; color:#6B7A99; font-family:'JetBrains Mono';">{created}</span>
            </div>
            <div style="font-size:0.85rem; color:#E8EDF5; margin-top:4px;">{msg}</div>
        </div>
        """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ADMIN PAGE
# ══════════════════════════════════════════════════════════════
def render_admin():
    st.markdown("## 👑 Admin Panel")
    
    if st.session_state.user.get("role") != "admin":
        st.error("Access denied.")
        return

    db = st.session_state.db
    if not db:
        st.warning("Database not connected.")
        return

    tab1, tab2 = st.tabs(["👥 User Management", "📊 System Overview"])

    with tab1:
        col1, col2 = st.columns([1.5, 1])
        
        with col1:
            st.markdown("#### All Users")
            users_df = get_users(db)
            if not users_df.empty:
                display = users_df[["username", "role", "email", "created_at", "is_active"]].copy() if all(c in users_df.columns for c in ["username", "role", "email"]) else users_df
                st.dataframe(display, use_container_width=True, hide_index=True)
            else:
                st.info("No users found.")

        with col2:
            st.markdown("#### Create User")
            new_user = st.text_input("Username", key="new_user")
            new_email = st.text_input("Email", key="new_email")
            new_pass = st.text_input("Password", type="password", key="new_pass")
            new_role = st.selectbox("Role", ["trader", "admin"], key="new_role")
            
            if st.button("➕ Create User"):
                if new_user and new_pass:
                    ok, msg = create_user(db, new_user, new_pass, new_email, new_role)
                    if ok: st.success(msg)
                    else: st.error(msg)
                else:
                    st.warning("Username and password required.")

            st.markdown("---")
            st.markdown("#### Delete User")
            del_user = st.text_input("Username to delete", key="del_user")
            with st.container():
                st.markdown('<div class="danger-btn">', unsafe_allow_html=True)
                if st.button("🗑️ Delete User", key="del_btn"):
                    if del_user:
                        ok, msg = delete_user(db, del_user)
                        if ok: st.success(msg)
                        else: st.error(msg)
                st.markdown('</div>', unsafe_allow_html=True)

    with tab2:
        st.markdown("#### 🔌 Database Connection Status")

        db   = st.session_state.db
        err  = st.session_state.db_error

        if db:
            st.success("✅ Google Sheets connected — `Forex_User_DB` is active.")
        else:
            st.error(f"❌ Not connected — **{err}**")
            st.markdown("""
            **How to fix:**

            1. Go to [console.cloud.google.com](https://console.cloud.google.com)
            2. Enable **Google Sheets API** + **Google Drive API**
            3. Create a **Service Account** → download JSON key
            4. On Streamlit Cloud → **Settings → Secrets** → paste:

            ```toml
            [gcp_service_account]
            type = "service_account"
            project_id = "your-project-id"
            private_key_id = "..."
            private_key = "-----BEGIN RSA PRIVATE KEY-----\\n...\\n-----END RSA PRIVATE KEY-----\\n"
            client_email = "your-sa@your-project.iam.gserviceaccount.com"
            client_id = "..."
            auth_uri = "https://accounts.google.com/o/oauth2/auth"
            token_uri = "https://oauth2.googleapis.com/token"
            auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
            client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/your-sa%40your-project.iam.gserviceaccount.com"
            ```

            5. Share the `Forex_User_DB` spreadsheet with the `client_email` as **Editor**
            6. Click **Retry Connection** below
            """)
            if st.button("🔄 Retry Connection"):
                st.cache_resource.clear()
                st.session_state.db       = None
                st.session_state.db_error = None
                st.rerun()

        st.markdown("---")
        st.markdown("#### ⚙️ System Status")
        st.markdown(f"""
        <div class="metric-card">
            <div style="font-size:0.85rem; display:grid; grid-template-columns:1fr 1fr; gap:8px;">
                <div>🗄️ <b>Database:</b> {'🟢 Connected' if db else '🔴 Disconnected'}</div>
                <div>📊 <b>Pairs:</b> {len(SYMBOL_MAP)} tracked</div>
                <div>🕐 <b>Server Time:</b> {datetime.now(COLOMBO_TZ).strftime('%H:%M:%S LKT')}</div>
                <div>⚙️ <b>Engine:</b> EW + SMC v2.1 + Gemini AI</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Gemini Key Rotation Status ─────────────────────────────
        st.markdown("#### 🤖 Gemini API Key Rotation")
        try:
            key_status = get_key_rotation_status()
            total  = key_status["total_keys"]
            avail  = key_status["available"]

            if total == 0:
                st.warning("⚠️ No Gemini API keys configured. Add keys to Streamlit Secrets.")
                st.code("""# secrets.toml — Gemini keys add කරන ක්‍රම 2ක්:

# ක්‍රමය 1 — comma separated list
gemini_api_keys = "AIza...key1,AIza...key2,AIza...key3"

# ක්‍රමය 2 — individual keys
gemini_key_1 = "AIzaSy..."
gemini_key_2 = "AIzaSy..."
gemini_key_3 = "AIzaSy..."
# ... up to gemini_key_7""", language="toml")
            else:
                st.markdown(f"**{avail}/{total} keys available**")

                # ── Live connection test ──────────────────────────
                if st.button("🔌 Test Gemini Connection", key="test_gemini_btn"):
                    import requests, json as _json
                    keys_list = _get_api_keys()
                    tested = 0
                    for k in keys_list[:3]:   # test first 3 keys
                        try:
                            r = requests.post(
                                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={k}",
                                json={"contents":[{"parts":[{"text":"Reply with JSON: {\"ok\":true}"}]}],
                                      "generationConfig":{"maxOutputTokens":20,"temperature":0}},
                                timeout=10,
                            )
                            if r.status_code == 200:
                                st.success(f"✅ Key ...{k[-6:]} — Connected OK (HTTP 200)")
                            elif r.status_code == 400:
                                st.error(f"❌ Key ...{k[-6:]} — Bad Request (400). Key invalid or malformed.")
                            elif r.status_code == 403:
                                st.error(f"❌ Key ...{k[-6:]} — Forbidden (403). Key disabled or no permission.")
                            elif r.status_code == 429:
                                st.warning(f"⏳ Key ...{k[-6:]} — Rate limited (429). Try later.")
                            else:
                                try:
                                    err_msg = r.json().get("error",{}).get("message","")
                                except Exception:
                                    err_msg = r.text[:100]
                                st.error(f"❌ Key ...{k[-6:]} — HTTP {r.status_code}: {err_msg}")
                            tested += 1
                        except requests.Timeout:
                            st.error(f"⏰ Key ...{k[-6:]} — Timeout (network issue)")
                        except Exception as ex:
                            st.error(f"❌ Key ...{k[-6:]} — {ex}")
                    if tested == 0:
                        st.error("No keys to test.")

                cols = st.columns(min(total, 7))
                for i, ki in enumerate(key_status["keys"]):
                    with cols[i % len(cols)]:
                        color  = "#00D4AA" if ki["available"] else "#FF4B6E"
                        status = "✅" if ki["available"] else f"⏳ {ki['cooldown']}s"
                        st.markdown(f"""
                        <div style="background:#111827; border:1px solid #1E2A42;
                             border-radius:8px; padding:0.6rem; text-align:center; font-size:0.75rem;">
                            <div style="color:{color}; font-weight:700;">Key {ki['index']}</div>
                            <div style="color:#6B7A99; font-family:'JetBrains Mono';">{ki['key_hint']}</div>
                            <div style="color:{color};">{status}</div>
                            <div style="color:#6B7A99;">Used: {ki['usage']} · Err: {ki['errors']}</div>
                        </div>
                        """, unsafe_allow_html=True)
        except Exception as e:
            st.info(f"Gemini status unavailable: {e}")

        all_active  = get_active_trades(db)  if db else pd.DataFrame()
        all_history = get_trade_history(db)  if db else pd.DataFrame()
        st.markdown(f"**Total Active Trades:** {len(all_active)} &nbsp;|&nbsp; **Total History:** {len(all_history)}")


# ══════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════
def main():
    init_session()
    inject_css()

    # Initialize DB once
    if st.session_state.db is None and st.session_state.db_error is None:
        db, err = get_database()
        st.session_state.db = db
        st.session_state.db_error = err

    if not st.session_state.authenticated:
        render_login()
        return

    render_sidebar()

    page = st.session_state.page
    if page == "dashboard":
        render_dashboard()
    elif page == "signals":
        render_signals()
    elif page == "analysis":
        render_analysis()
    elif page == "trades":
        render_active_trades()
    elif page == "history":
        render_history()
    elif page == "settings":
        render_settings()
    elif page == "notifications":
        render_notifications()
    elif page == "admin":
        render_admin()


if __name__ == "__main__":
    main()
