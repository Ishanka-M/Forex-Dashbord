"""
modules/database.py
Google Sheets Database Layer for FX-WavePulse Pro
- Fresh connection per write operation (fixes cached stale object bug)
- Auto-create missing sheets on every write
- Robust error reporting
"""

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    gspread = None
    Credentials = None

import pandas as pd
import streamlit as st
import os
import hashlib
from datetime import datetime
import pytz

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_NAME = "Forex_User_DB"
COLOMBO_TZ       = pytz.timezone("Asia/Colombo")

SHEET_SCHEMAS = {
    "Users": [
        "username", "password_hash", "role", "email", "created_at", "is_active"
    ],
    "ActiveTrades": [
        "trade_id", "username", "symbol", "direction", "entry_price",
        "sl_price", "tp_price", "lot_size", "open_time", "strategy",
        "probability_score", "status", "current_price", "pnl"
    ],
    "TradeHistory": [
        "trade_id", "username", "symbol", "direction", "entry_price",
        "sl_price", "tp_price", "lot_size", "open_time", "close_time",
        "close_price", "pnl", "result", "strategy", "probability_score"
    ],
    "MarketData": [
        "symbol", "timeframe", "timestamp", "open", "high", "low",
        "close", "volume", "ew_wave", "smc_zone", "signal"
    ],
}

ADMIN_USER = {
    "username": "admin",
    "password": "admin@#123",
    "role":     "admin",
    "email":    "admin@fxwavepulse.com",
}


# ══════════════════════════════════════════════════════
# CONNECTION HELPERS
# ══════════════════════════════════════════════════════

def _build_credentials():
    """Build Google credentials from Streamlit secrets or local file."""
    if not GSPREAD_AVAILABLE:
        raise RuntimeError("gspread not installed — check requirements.txt")

    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        # Streamlit toml sometimes escapes \n — fix private key newlines
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")
        return Credentials.from_service_account_info(info, scopes=SCOPES)

    if os.path.exists("service_account.json"):
        return Credentials.from_service_account_file(
            "service_account.json", scopes=SCOPES
        )

    raise RuntimeError(
        "No Google credentials found.\n"
        "Add [gcp_service_account] to Streamlit Secrets or place service_account.json in root."
    )


def _get_client():
    """Return a fresh authorised gspread client (no caching)."""
    creds = _build_credentials()
    return gspread.authorize(creds)


def _get_spreadsheet():
    """
    Return the Forex_User_DB spreadsheet with all sheets verified.
    Always opens a fresh connection — safe for write operations.
    """
    client = _get_client()
    try:
        ss = client.open(SPREADSHEET_NAME)
    except Exception:
        ss = client.create(SPREADSHEET_NAME)
        ss.share(None, perm_type="anyone", role="writer")

    existing = [ws.title for ws in ss.worksheets()]

    # Create any missing sheets
    for sheet_name, headers in SHEET_SCHEMAS.items():
        if sheet_name not in existing:
            ws = ss.add_worksheet(
                title=sheet_name,
                rows=2000,
                cols=len(headers)
            )
            ws.append_row(headers, value_input_option="RAW")

    # Remove default Sheet1
    if "Sheet1" in existing:
        try:
            ss.del_worksheet(ss.worksheet("Sheet1"))
        except Exception:
            pass

    return ss


# ══════════════════════════════════════════════════════
# CACHED READ CONNECTION  (for dashboard reads only)
# ══════════════════════════════════════════════════════

@st.cache_resource(ttl=600, show_spinner=False)
def get_database():
    """
    Cached spreadsheet for READ operations (dashboard, signals page).
    Returns (spreadsheet, error_string).
    """
    if not GSPREAD_AVAILABLE:
        return None, "gspread not installed — check requirements.txt"
    try:
        ss = _get_spreadsheet()
        _ensure_admin_exists(ss)
        return ss, None
    except Exception as e:
        return None, str(e)


def get_fresh_spreadsheet():
    """
    Fresh (uncached) spreadsheet for WRITE operations.
    Call this instead of session_state.db when writing data.
    Returns (spreadsheet, error_string).
    """
    if not GSPREAD_AVAILABLE:
        return None, "gspread not installed"
    try:
        ss = _get_spreadsheet()
        return ss, None
    except Exception as e:
        return None, str(e)


# ══════════════════════════════════════════════════════
# ADMIN INIT
# ══════════════════════════════════════════════════════

def _ensure_admin_exists(ss):
    try:
        ws       = ss.worksheet("Users")
        records  = ws.get_all_records()
        existing = [r.get("username") for r in records]
        if ADMIN_USER["username"] not in existing:
            pwd_hash = hashlib.sha256(ADMIN_USER["password"].encode()).hexdigest()
            now      = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row(
                [ADMIN_USER["username"], pwd_hash, ADMIN_USER["role"],
                 ADMIN_USER["email"], now, "true"],
                value_input_option="RAW"
            )
    except Exception as e:
        print(f"[Admin init] {e}")


# ══════════════════════════════════════════════════════
# USERS
# ══════════════════════════════════════════════════════

def get_users(ss) -> pd.DataFrame:
    try:
        records = ss.worksheet("Users").get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame(columns=SHEET_SCHEMAS["Users"])
    except Exception:
        return pd.DataFrame(columns=SHEET_SCHEMAS["Users"])


def authenticate_user(ss, username: str, password: str):
    """Returns user dict or None."""
    # Hardcoded admin always works (even if DB down)
    if username == ADMIN_USER["username"] and password == ADMIN_USER["password"]:
        return {"username": username, "role": "admin", "email": ADMIN_USER["email"]}

    if ss is None:
        return None
    try:
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        df       = get_users(ss)
        if df.empty:
            return None
        row = df[
            (df["username"] == username) &
            (df["password_hash"] == pwd_hash) &
            (df["is_active"].astype(str).str.lower() == "true")
        ]
        return row.iloc[0].to_dict() if not row.empty else None
    except Exception:
        return None


def create_user(ss, username, password, email, role="trader"):
    try:
        df = get_users(ss)
        if username in df["username"].values:
            return False, f"Username '{username}' already exists."
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        now      = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
        # Use fresh connection for write
        ss_w, err = get_fresh_spreadsheet()
        if err:
            return False, err
        ss_w.worksheet("Users").append_row(
            [username, pwd_hash, role, email, now, "true"],
            value_input_option="RAW"
        )
        return True, "User created successfully."
    except Exception as e:
        return False, str(e)


def delete_user(ss, username):
    try:
        if username == "admin":
            return False, "Cannot delete admin user."
        ss_w, err = get_fresh_spreadsheet()
        if err:
            return False, err
        ws      = ss_w.worksheet("Users")
        records = ws.get_all_records()
        for i, r in enumerate(records):
            if r.get("username") == username:
                ws.delete_rows(i + 2)
                return True, f"User '{username}' deleted."
        return False, "User not found."
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════
# ACTIVE TRADES
# ══════════════════════════════════════════════════════

def get_active_trades(ss, username=None) -> pd.DataFrame:
    try:
        records = ss.worksheet("ActiveTrades").get_all_records()
        df = pd.DataFrame(records) if records else pd.DataFrame(columns=SHEET_SCHEMAS["ActiveTrades"])
        if username and not df.empty:
            df = df[df["username"] == username]
        return df
    except Exception:
        return pd.DataFrame(columns=SHEET_SCHEMAS["ActiveTrades"])


def add_active_trade(ss, trade: dict):
    """
    Write trade to ActiveTrades sheet.
    Always uses a FRESH connection to avoid stale cached object.
    """
    try:
        ss_w, err = get_fresh_spreadsheet()
        if err:
            return False, f"Connection error: {err}"

        ws  = ss_w.worksheet("ActiveTrades")
        row = [str(trade.get(col, "")) for col in SHEET_SCHEMAS["ActiveTrades"]]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True, "Trade saved to ActiveTrades ✅"
    except Exception as e:
        return False, f"Write error: {str(e)}"


def update_trade_pnl(ss, trade_id: str, current_price: float, pnl: float):
    """Update live P&L on an active trade row."""
    try:
        ss_w, err = get_fresh_spreadsheet()
        if err:
            return False, err
        ws      = ss_w.worksheet("ActiveTrades")
        records = ws.get_all_records()
        headers = SHEET_SCHEMAS["ActiveTrades"]
        for i, r in enumerate(records):
            if str(r.get("trade_id")) == str(trade_id):
                row_num = i + 2
                cp_col  = headers.index("current_price") + 1
                pnl_col = headers.index("pnl") + 1
                ws.update_cell(row_num, cp_col, str(round(current_price, 5)))
                ws.update_cell(row_num, pnl_col, str(round(pnl, 2)))
                return True, "Updated"
        return False, "Trade not found"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════
# CLOSE TRADE  (ActiveTrades → TradeHistory)
# ══════════════════════════════════════════════════════

def close_trade(ss, trade_id, close_price, result):
    """Move trade from ActiveTrades to TradeHistory."""
    try:
        ss_w, err = get_fresh_spreadsheet()
        if err:
            return False, f"Connection error: {err}"

        active_ws  = ss_w.worksheet("ActiveTrades")
        history_ws = ss_w.worksheet("TradeHistory")
        records    = active_ws.get_all_records()

        for i, r in enumerate(records):
            if str(r.get("trade_id")) == str(trade_id):
                now       = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
                entry     = float(r.get("entry_price", 0) or 0)
                direction = r.get("direction", "BUY")
                lot       = float(r.get("lot_size", 0.01) or 0.01)
                pnl       = (close_price - entry) * (1 if direction == "BUY" else -1) * lot * 100000

                history_row = [
                    r.get("trade_id"),   r.get("username"),  r.get("symbol"),
                    r.get("direction"),  r.get("entry_price"),
                    r.get("sl_price"),   r.get("tp_price"),  r.get("lot_size"),
                    r.get("open_time"),  now,                str(close_price),
                    str(round(pnl, 2)), result,
                    r.get("strategy"),  r.get("probability_score"),
                ]
                history_ws.append_row(history_row, value_input_option="USER_ENTERED")
                active_ws.delete_rows(i + 2)
                return True, f"Trade closed → {result}. P&L: ${round(pnl, 2)}"

        return False, "Trade ID not found in ActiveTrades."
    except Exception as e:
        return False, f"Close error: {str(e)}"


# ══════════════════════════════════════════════════════
# TRADE HISTORY
# ══════════════════════════════════════════════════════

def get_trade_history(ss, username=None) -> pd.DataFrame:
    try:
        records = ss.worksheet("TradeHistory").get_all_records()
        df = pd.DataFrame(records) if records else pd.DataFrame(columns=SHEET_SCHEMAS["TradeHistory"])
        if username and not df.empty and "username" in df.columns:
            df = df[df["username"] == username]
        return df
    except Exception:
        return pd.DataFrame(columns=SHEET_SCHEMAS["TradeHistory"])
