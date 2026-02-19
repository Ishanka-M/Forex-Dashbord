import streamlit as st
import yfinance as yf
import pandas as pd
import puter  # Puter AI for Fallback
import google.generativeai as genai # Gemini AI
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import time
import re
import numpy as np
import requests
import xml.etree.ElementTree as ET
import pytz # For Timezone handling

# Import Combine Engine functions
from combine_engine import ai_verify_trade, get_deep_hybrid_analysis

# --- 1. SETUP & STYLE (UPDATED ANIMATIONS & UI) ---
st.set_page_config(page_title="♾️ INFINITE AI TERMINAL", layout="wide", page_icon="⚡")

st.markdown("""
<style>
    /* ... (same CSS as before) ... */
</style>
""", unsafe_allow_html=True)

# --- Initialize Session State ---
if "logged_in" not in st.session_state: st.session_state.logged_in = False
if "active_provider" not in st.session_state: st.session_state.active_provider = "Waiting for analysis..."
if "ai_parsed_data" not in st.session_state: st.session_state.ai_parsed_data = {"ENTRY": "N/A", "SL": "N/A", "TP": "N/A"}
if "scan_results" not in st.session_state: st.session_state.scan_results = {"swing": [], "scalp": []}
if "forecast_chart" not in st.session_state: st.session_state.forecast_chart = None
if "selected_trade" not in st.session_state: st.session_state.selected_trade = None
if "deep_analysis_result" not in st.session_state: st.session_state.deep_analysis_result = None
if "deep_analysis_provider" not in st.session_state: st.session_state.deep_analysis_provider = None
if "deep_forecast_chart" not in st.session_state: st.session_state.deep_forecast_chart = None

# Cache for live prices (to avoid rate limits)
if "price_cache" not in st.session_state:
    st.session_state.price_cache = {}  # clean_pair -> (price, timestamp)

# ==================== HELPER FUNCTIONS (unchanged) ====================

def get_yf_symbol(display_symbol):
    # ... same as before ...
    pass

def clean_pair_to_yf_symbol(clean_pair):
    # ... same as before ...
    pass

def get_live_price(clean_pair):
    # ... same as before ...
    pass

def get_user_sheet():
    # ... same as before ...
    pass

def get_ongoing_sheet():
    # ... same as before ...
    pass

def save_trade_to_ongoing(trade, username):
    # ... same as before ...
    pass

def load_user_trades(username, status=None):
    # ... same as before ...
    pass

def update_trade_status_by_row(row_index, new_status, closed_date=""):
    # ... same as before ...
    pass

def delete_trade_by_row_number(row_number):
    # ... same as before ...
    pass

def check_and_update_trades(username):
    # ... same as before ...
    pass

def is_trade_tracked(scan_trade, active_trades):
    # ... same as before ...
    pass

def get_current_date_str():
    # ... same as before ...
    pass

def check_login(username, password):
    # ... same as before ...
    pass

def update_usage_in_db(username, new_usage):
    # ... same as before ...
    pass

def update_user_limit_in_db(username, new_limit):
    # ... same as before ...
    pass

def add_new_user_to_db(username, password, limit):
    # ... same as before ...
    pass

def get_sentiment_class(title):
    # ... same as before ...
    pass

def get_market_news(symbol):
    # ... same as before ...
    pass

def calculate_news_impact(news_list):
    # ... same as before ...
    pass

def get_data_period(tf):
    # ... same as before ...
    pass

def calculate_advanced_signals(df, tf):
    # ... same as before ...
    pass

def infinite_algorithmic_engine(pair, curr_p, sigs, news_items, atr, tf):
    # ... same as before ...
    pass

def get_hybrid_analysis(pair, asset_data, sigs, news_items, atr, user_info, tf):
    # ... same as before (this function remains for the Terminal page) ...
    # Note: This one still uses internal Gemini calls; we keep it as is.
    pass

def parse_ai_response(text):
    # ... same as before ...
    pass

def create_forecast_chart(historical_df, entry_price, sl, tp, forecast_text):
    # ... same as before ...
    pass

# ==================== SCAN FUNCTION (unchanged) ====================
def scan_market(assets_list, active_trades=None):
    # ... same as before (returns raw candidates) ...
    pass

# --- 7. MAIN APPLICATION ---
if not st.session_state.logged_in:
    st.markdown("<h1 style='text-align: center; color: #00d4ff; animation: fadeIn 1s;'>♾️ INFINITE AI TERMINAL | v17.0</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1,2,1])
    with c2:
        with st.form("login_form"):
            u, p = st.text_input("Username"), st.text_input("Password", type="password")
            if st.form_submit_button("Access Terminal"):
                user = check_login(u, p)
                if user:
                    st.session_state.logged_in, st.session_state.user = True, user
                    st.rerun()
                else: st.error("Invalid Credentials")
else:
    user_info = st.session_state.get('user', {})
    st.sidebar.title(f"👤 {user_info.get('Username', 'Trader')}")
    st.sidebar.caption(f"Credits: {user_info.get('UsageCount', 0)}/{user_info.get('HybridLimit', 10)}")
    
    auto_refresh = st.sidebar.checkbox("🔄 Auto-Monitor (60s)", value=False)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    nav_options = ["Terminal", "Market Scanner", "Ongoing Trades"]
    if user_info.get("Role") == "Admin": nav_options.append("Admin Panel")
    app_mode = st.sidebar.radio("Navigation", nav_options)
    
    assets = {
        "Forex": [ ... ],  # same as before
        "Crypto": [ ... ],
        "Metals": [ ... ]
    }

    # Collect Gemini API keys from secrets
    gemini_keys = []
    for i in range(1, 8):
        k = st.secrets.get(f"GEMINI_API_KEY_{i}")
        if k: gemini_keys.append(k)

    if app_mode == "Terminal":
        # ... (Terminal page unchanged) ...
        pass

    elif app_mode == "Market Scanner":
        st.title("📡 Global Market Scanner (Multi-Timeframe)")
        
        enable_ai_verification = st.checkbox("🤖 Enable AI Verification (slower, uses credits)", value=True,
                                             help="If enabled, each candidate trade will be checked by AI and only profitable ones shown.")
        
        if st.button("Start Global Scan (All Pairs)", type="primary"):
            with st.spinner("Scanning markets for High Probability Setups (>30%)..."):
                all_scan_assets = assets["Forex"] + assets["Crypto"] + assets["Metals"]
                active_trades = load_user_trades(user_info['Username'], status='Active')
                results = scan_market(all_scan_assets, active_trades)
                
                if enable_ai_verification and (results['swing'] or results['scalp']):
                    verified_swing = []
                    verified_scalp = []
                    total_trades = len(results['swing']) + len(results['scalp'])
                    progress_bar = st.progress(0, text="AI Verifying trades...")
                    status_text = st.empty()
                    
                    # Helper to process a trade
                    def verify_trade(trade):
                        # Fetch news and live price
                        orig_sym = trade['symbol_orig']
                        news_items = get_market_news(orig_sym)
                        news_str = "\n".join([f"- {n['title']}" for n in news_items])
                        live_price = trade['live_price']
                        
                        # Call AI verification (no usage counting inside)
                        is_profitable, msg, provider = ai_verify_trade(
                            trade, news_str, live_price, gemini_keys
                        )
                        return is_profitable, msg, provider
                    
                    # Verify swing trades
                    for i, trade in enumerate(results['swing']):
                        status_text.text(f"Verifying Swing {i+1}/{len(results['swing'])}: {trade['pair']}")
                        is_profitable, msg, provider = verify_trade(trade)
                        if is_profitable:
                            trade['verification_msg'] = msg
                            trade['verification_provider'] = provider
                            verified_swing.append(trade)
                            # Increment usage if successful
                            new_usage = user_info.get("UsageCount", 0) + 1
                            user_info["UsageCount"] = new_usage
                            st.session_state.user = user_info
                            if user_info["Username"] != "Admin":
                                update_usage_in_db(user_info["Username"], new_usage)
                        progress_bar.progress((i+1)/total_trades)
                    
                    # Verify scalp trades
                    for i, trade in enumerate(results['scalp']):
                        status_text.text(f"Verifying Scalp {i+1}/{len(results['scalp'])}: {trade['pair']}")
                        is_profitable, msg, provider = verify_trade(trade)
                        if is_profitable:
                            trade['verification_msg'] = msg
                            trade['verification_provider'] = provider
                            verified_scalp.append(trade)
                            new_usage = user_info.get("UsageCount", 0) + 1
                            user_info["UsageCount"] = new_usage
                            st.session_state.user = user_info
                            if user_info["Username"] != "Admin":
                                update_usage_in_db(user_info["Username"], new_usage)
                        progress_bar.progress((len(results['swing'])+i+1)/total_trades)
                    
                    progress_bar.empty()
                    status_text.empty()
                    results['swing'] = verified_swing
                    results['scalp'] = verified_scalp
                
                st.session_state.scan_results = results
                
                if not results['swing'] and not results['scalp']:
                    st.warning("No signals found above 30% accuracy" + (" after AI verification." if enable_ai_verification else "."))
                else:
                    st.success(f"Scan Complete! Found {len(results['swing'])} Swing & {len(results['scalp'])} Scalp setups.")
        
        # Display results (same as before, but with verification badge)
        res = st.session_state.scan_results
        st.markdown("---")
        
        # Swing section
        st.subheader("🐢 SWING TRADES (4H)")
        if res['swing']:
            for idx, sig in enumerate(res['swing']):
                # ... same display code, but include badge if verification_msg exists ...
                # (unchanged)
                pass
        else:
            st.info("No Swing setups found.")
        
        st.markdown("---")
        
        # Scalp section
        st.subheader("🐇 SCALP TRADES (15M)")
        if res['scalp']:
            for idx, sig in enumerate(res['scalp']):
                # ... same display code ...
                pass
        else:
            st.info("No Scalp setups found.")
        
        # Deep analysis for selected trade (updated to use imported function)
        if st.session_state.selected_trade:
            st.markdown("---")
            st.subheader(f"🔬 Deep Analysis: {st.session_state.selected_trade['pair']} ({st.session_state.selected_trade['tf']})")
            
            if st.session_state.deep_analysis_result is None:
                with st.spinner("Running deep analysis with Gemini + Puter..."):
                    trade = st.session_state.selected_trade
                    # Prepare data
                    orig_sym = trade['symbol_orig']
                    news_items = get_market_news(orig_sym)
                    news_str = "\n".join([f"- {n['title']}" for n in news_items])
                    live_price = trade['live_price']
                    
                    # Call deep analysis
                    result, provider = get_deep_hybrid_analysis(
                        trade, news_str, live_price, gemini_keys
                    )
                    st.session_state.deep_analysis_result = result
                    st.session_state.deep_analysis_provider = provider
                    
                    # Update usage
                    new_usage = user_info.get("UsageCount", 0) + 1
                    user_info["UsageCount"] = new_usage
                    st.session_state.user = user_info
                    if user_info["Username"] != "Admin":
                        update_usage_in_db(user_info["Username"], new_usage)
                    
                    # Parse forecast and create chart (same as before)
                    parsed = parse_ai_response(result)
                    forecast_text = parsed.get('FORECAST', '')
                    # ... rest of chart creation ...
                    pass
            
            # Display results (same as before)
            pass

    elif app_mode == "Ongoing Trades":
        # ... unchanged ...
        pass

    elif app_mode == "Admin Panel":
        # ... unchanged ...
        pass

    if auto_refresh:
        time.sleep(60)
        st.rerun()
