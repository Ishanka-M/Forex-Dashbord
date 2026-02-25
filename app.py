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
        get_database, authenticate_user, create_user, delete_user,
        get_users, get_active_trades, add_active_trade, close_trade, get_trade_history
    )
    from modules.market_data import (
        get_all_live_prices, get_ohlcv, get_session_status, get_colombo_time,
        SYMBOL_MAP, MAJOR_PAIRS, SYMBOL_CATEGORIES, get_all_symbols
    )
    from modules.elliott_wave import identify_elliott_waves
    from modules.smc_analysis import analyze_smc
    from modules.signal_engine import generate_all_signals, generate_signal, TradeSignal
    from modules.charts import create_candlestick_chart, create_pnl_chart
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
        "authenticated": False,
        "user":          None,
        "db":            None,
        "db_error":      None,
        "page":          "dashboard",
        "last_refresh":  None,
        "sidebar_open":  True,
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
    user = st.session_state.user
    is_admin = user.get("role") == "admin"

    with st.sidebar:
        st.markdown(f"""
        <div style="padding:1rem 0.5rem; border-bottom:1px solid #1E2A42; margin-bottom:1rem;">
            <div style="font-size:1.2rem; font-weight:700; color:#00D4AA;">FX-WavePulse Pro</div>
            <div style="font-size:0.75rem; color:#6B7A99; font-family:'JetBrains Mono';">v2.0 · Elliott + SMC</div>
        </div>
        <div style="background:#111827; border-radius:8px; padding:0.7rem 1rem; margin-bottom:1rem; border:1px solid #1E2A42;">
            <div style="font-size:0.72rem; color:#6B7A99;">Logged in as</div>
            <div style="font-weight:600; color:#E8EDF5;">{user.get('username', 'User')}</div>
            <div style="font-size:0.7rem; background:{'rgba(139,92,246,0.2)' if is_admin else 'rgba(59,130,246,0.2)'}; 
                 color:{'#8B5CF6' if is_admin else '#3B82F6'}; 
                 border-radius:10px; padding:1px 8px; display:inline-block; margin-top:2px;">
                {'👑 Admin' if is_admin else '📊 Trader'}
            </div>
        </div>
        """, unsafe_allow_html=True)

        pages = {
            "dashboard": "📊  Dashboard",
            "signals":   "🎯  Trade Signals",
            "analysis":  "🔬  Chart Analysis",
            "trades":    "💼  Active Trades",
            "history":   "📜  Trade History",
        }
        if is_admin:
            pages["admin"] = "👑  Admin Panel"

        st.markdown("**Navigation**")
        for page_key, label in pages.items():
            btn_style = "primary" if st.session_state.page == page_key else "secondary"
            if st.button(label, key=f"nav_{page_key}", use_container_width=True, type=btn_style):
                st.session_state.page = page_key
                st.rerun()

        st.markdown("---")

        # Colombo time
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
    score = sig.probability_score
    score_cls = "badge-score-high" if score >= 70 else ("badge-score-medium" if score >= 50 else "badge-score-low")
    bar_cls = "score-high" if score >= 70 else ("score-medium" if score >= 50 else "score-low")
    dir_class = "buy" if sig.direction == "BUY" else "sell"
    dir_badge = "badge-buy" if sig.direction == "BUY" else "badge-sell"

    confluence_str = " · ".join(sig.confluences[:3]) if sig.confluences else "—"

    entry_fmt = f"{sig.entry_price:.5f}" if sig.entry_price < 100 else f"{sig.entry_price:.2f}"
    sl_fmt    = f"{sig.sl_price:.5f}" if sig.sl_price < 100 else f"{sig.sl_price:.2f}"
    tp_fmt    = f"{sig.tp_price:.5f}" if sig.tp_price < 100 else f"{sig.tp_price:.2f}"

    st.markdown(f"""
    <div class="signal-card {dir_class}">
        <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:8px;">
            <div>
                <span style="font-weight:700; font-size:1.05rem;">{sig.symbol}</span>
                <span class="signal-badge {dir_badge}" style="margin-left:8px;">{sig.direction}</span>
                <span style="font-size:0.72rem; color:#6B7A99; margin-left:6px;">{sig.timeframe} · {sig.strategy.upper()}</span>
            </div>
            <span class="signal-badge {score_cls}">{score}%</span>
        </div>
        <div style="font-size:0.8rem; color:#6B7A99; margin-bottom:8px; font-family:'JetBrains Mono';">
            {confluence_str}
        </div>
        <div style="display:flex; gap:1.5rem; font-family:'JetBrains Mono'; font-size:0.82rem;">
            <div><span style="color:#6B7A99">Entry</span> <span style="color:#E8EDF5; font-weight:500">{entry_fmt}</span></div>
            <div><span style="color:#6B7A99">SL</span> <span style="color:#FF4B6E">{sl_fmt}</span></div>
            <div><span style="color:#6B7A99">TP</span> <span style="color:#00D4AA">{tp_fmt}</span></div>
            <div><span style="color:#6B7A99">RR</span> <span style="color:#8B5CF6">1:{sig.risk_reward}</span></div>
        </div>
        <div class="score-bar-container" style="margin-top:8px;">
            <div class="score-bar {bar_cls}" style="width:{score}%;"></div>
        </div>
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

    st.markdown(f"**{len(signals)} signal(s) found**")

    for sig in signals:
        with st.expander(
            f"{'🟢' if sig.direction=='BUY' else '🔴'} {sig.symbol} "
            f"{sig.direction} — Score: {sig.probability_score}%",
            expanded=sig.probability_score >= 60
        ):
            _render_signal_card(sig)

            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"""
                **EW Pattern:** `{sig.ew_pattern}`
                **SMC Bias:** `{sig.smc_bias[:60]}`
                **Generated:** `{sig.generated_at} LKT`
                """)
            with col_b:
                st.markdown("**Confluences:**")
                for c in sig.confluences:
                    st.markdown(f"- ✅ {c}")

            # ── Add to Active Trades ─────────────────────────────
            db = st.session_state.get("db")
            if db:
                col_btn, col_status = st.columns([1, 2])
                with col_btn:
                    if st.button(f"➕ Add to Active Trades", key=f"add_{sig.trade_id}",
                                 use_container_width=True):
                        trade = {
                            "trade_id":          sig.trade_id,
                            "username":          st.session_state.user.get("username"),
                            "symbol":            sig.symbol,
                            "direction":         sig.direction,
                            "entry_price":       str(sig.entry_price),
                            "sl_price":          str(sig.sl_price),
                            "tp_price":          str(sig.tp_price),
                            "lot_size":          str(sig.lot_size),
                            "open_time":         sig.generated_at,
                            "strategy":          sig.strategy,
                            "probability_score": str(sig.probability_score),
                            "status":            "open",
                            "current_price":     str(sig.entry_price),
                            "pnl":               "0",
                        }
                        try:
                            ok, msg = add_active_trade(db, trade)
                            if ok:
                                st.cache_resource.clear()
                                st.success(f"✅ Trade saved! → Go to **Active Trades**")
                            else:
                                st.error(f"❌ Save failed: {msg}")
                        except Exception as ex:
                            st.error(f"❌ Error: {ex}")
            else:
                st.warning("⚠️ Database not connected — trades cannot be saved. Configure Google Sheets secrets.")


# ══════════════════════════════════════════════════════════════
# CHART ANALYSIS PAGE
# ══════════════════════════════════════════════════════════════
def render_analysis():
    st.markdown("## 🔬 Chart Analysis")

    col1, col2 = st.columns([1, 1])
    with col1:
        category = st.selectbox("Category", list(SYMBOL_CATEGORIES.keys()), key="analysis_cat")
        symbol   = st.selectbox("Symbol", SYMBOL_CATEGORIES[category], key="analysis_sym")
    with col2:
        timeframe = st.selectbox("Timeframe", ["M5","M15","H1","H4","D1"], index=2)

    col3, col4 = st.columns([1, 1])
    with col3:
        show_ew  = st.checkbox("Elliott Wave", value=True)
    with col4:
        show_smc = st.checkbox("SMC Zones (OB / FVG / BOS)", value=True)

    with st.spinner(f"Fetching {symbol} {timeframe} data..."):
        df = get_ohlcv(symbol, timeframe)

    if df is None or df.empty:
        st.error(f"⚠️ Could not fetch data for **{symbol}** on **{timeframe}**.")
        with st.expander("🔧 Troubleshooting"):
            st.markdown(f"""
            **Possible reasons:**
            - `{symbol}` may not have data at `{timeframe}` granularity on Yahoo Finance
            - Intraday data (M5/M15) is only available for the **last 60 days**
            - Some exotic pairs have limited history — try **H1** or **D1**
            - Yahoo Finance rate limit — wait 30 seconds and retry

            **Try these instead:**
            - Change timeframe to `H1` or `D1`
            - Switch to a Major pair: EURUSD, GBPUSD, XAUUSD
            - Click **Refresh** below to clear the cache
            """)
            if st.button("🔄 Clear Cache & Retry"):
                st.cache_data.clear()
                st.rerun()
        return

    ew_result = identify_elliott_waves(df) if show_ew else None
    smc_result = analyze_smc(df) if show_smc else None

    # Chart
    fig = create_candlestick_chart(df, symbol, timeframe, 
                                    ew_result if show_ew else None,
                                    smc_result if show_smc else None)
    st.plotly_chart(fig, use_container_width=True)

    # Analysis summary
    col_ew, col_smc = st.columns(2)

    if ew_result and show_ew:
        with col_ew:
            st.markdown("### 🌊 Elliott Wave Summary")
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size:0.85rem;">
                    <div style="margin-bottom:6px"><b>Pattern:</b> <code>{ew_result.pattern_type}</code></div>
                    <div style="margin-bottom:6px"><b>Trend:</b> <span class="{'up' if ew_result.trend=='bullish' else 'down'}">{ew_result.trend.upper()}</span></div>
                    <div style="margin-bottom:6px"><b>Current Wave:</b> <code>{ew_result.current_wave}</code></div>
                    <div style="margin-bottom:6px"><b>Confidence:</b> {ew_result.confidence*100:.0f}%</div>
                    <div style="margin-bottom:6px"><b>Target:</b> <code>{ew_result.projected_target or 'N/A'}</code></div>
                    <div style="color:#6B7A99; font-size:0.8rem;">{ew_result.description}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    if smc_result and show_smc:
        with col_smc:
            st.markdown("### 💡 SMC Summary")
            st.markdown(f"""
            <div class="metric-card">
                <div style="font-size:0.85rem;">
                    <div style="margin-bottom:6px"><b>Trend:</b> <span class="{'up' if smc_result.trend=='bullish' else 'down'}">{smc_result.trend.upper()}</span></div>
                    <div style="margin-bottom:6px"><b>Last CHoCH:</b> <code>{'✅ '+smc_result.last_choch.direction.upper() if smc_result.last_choch else 'None'}</code></div>
                    <div style="margin-bottom:6px"><b>Last BOS:</b> <code>{'✅ '+smc_result.last_bos.direction.upper() if smc_result.last_bos else 'None'}</code></div>
                    <div style="margin-bottom:6px"><b>Nearest OB:</b> <code>{'✅ '+smc_result.current_ob.ob_type.upper() if smc_result.current_ob else 'None'}</code></div>
                    <div style="margin-bottom:6px"><b>Nearest FVG:</b> <code>{'✅ Unfilled' if smc_result.nearest_fvg else 'None'}</code></div>
                    <div style="margin-bottom:6px"><b>Confidence:</b> {smc_result.confidence*100:.0f}%</div>
                    <div style="color:#6B7A99; font-size:0.8rem;">{smc_result.bias}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# ACTIVE TRADES PAGE
# ══════════════════════════════════════════════════════════════
def render_active_trades():
    st.markdown("## 💼 Active Trades")
    
    db = st.session_state.db
    username = st.session_state.user.get("username")
    is_admin = st.session_state.user.get("role") == "admin"

    if not db:
        st.warning("Database not connected. Trades cannot be persisted.")
        return

    trades_df = get_active_trades(db, None if is_admin else username)
    
    if trades_df.empty:
        st.info("No active trades. Go to Signals to find and add trades.")
        return

    st.markdown(f"**{len(trades_df)} active trade(s)**")

    for _, trade in trades_df.iterrows():
        trade_id = str(trade.get("trade_id", ""))
        symbol = trade.get("symbol", "")
        direction = trade.get("direction", "")
        entry = float(trade.get("entry_price", 0) or 0)
        sl = float(trade.get("sl_price", 0) or 0)
        tp = float(trade.get("tp_price", 0) or 0)
        score = trade.get("probability_score", 0)

        # Get live price
        from modules.market_data import get_live_price
        live = get_live_price(symbol) if symbol else {}
        live_price = live.get("price") or entry
        pnl = (live_price - entry) * (1 if direction == "BUY" else -1) * float(trade.get("lot_size", 0.01) or 0.01) * 100000
        pnl_color = "#00D4AA" if pnl >= 0 else "#FF4B6E"

        with st.expander(f"{'🟢' if direction=='BUY' else '🔴'} {symbol} {direction} | P&L: ${pnl:+.2f}", expanded=True):
            col1, col2, col3 = st.columns(3)
            col1.markdown(f"""
            <div style="font-size:0.85rem;">
                <div><b>Entry:</b> <code>{entry:.5f}</code></div>
                <div><b>Live:</b> <code style="color:#E8EDF5">{live_price:.5f}</code></div>
                <div><b>SL:</b> <code style="color:#FF4B6E">{sl:.5f}</code></div>
                <div><b>TP:</b> <code style="color:#00D4AA">{tp:.5f}</code></div>
            </div>
            """, unsafe_allow_html=True)
            col2.markdown(f"""
            <div style="font-size:0.85rem;">
                <div><b>P&L:</b> <span style="color:{pnl_color}; font-family:'JetBrains Mono';">${pnl:+.2f}</span></div>
                <div><b>Score:</b> {score}%</div>
                <div><b>Opened:</b> {trade.get('open_time', 'N/A')}</div>
            </div>
            """, unsafe_allow_html=True)
            
            with col3:
                close_price = st.number_input(f"Close Price", value=float(live_price), key=f"cp_{trade_id}", format="%.5f")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("✅ TP Hit", key=f"tp_{trade_id}"):
                        ok, msg = close_trade(db, trade_id, close_price, "TP")
                        if ok: st.success(msg); st.rerun()
                        else: st.error(msg)
                with c2:
                    if st.button("❌ SL Hit", key=f"sl_{trade_id}"):
                        ok, msg = close_trade(db, trade_id, close_price, "SL")
                        if ok: st.success(msg); st.rerun()
                        else: st.error(msg)
                if st.button("🔒 Manual Close", key=f"mc_{trade_id}"):
                    ok, msg = close_trade(db, trade_id, close_price, "MANUAL")
                    if ok: st.success(msg); st.rerun()
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
                <div>⚙️ <b>Engine:</b> EW + SMC v2.1</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

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
    elif page == "admin":
        render_admin()


if __name__ == "__main__":
    main()
