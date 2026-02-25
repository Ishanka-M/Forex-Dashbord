"""
modules/database.py
Google Sheets Database Layer for FX-WavePulse Pro
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
import json
import os
from datetime import datetime
import pytz

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

SPREADSHEET_NAME = "Forex_User_DB"
COLOMBO_TZ = pytz.timezone("Asia/Colombo")

SHEET_SCHEMAS = {
    "Users": ["username", "password_hash", "role", "email", "created_at", "is_active"],
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
    "role": "admin",
    "email": "admin@fxwavepulse.com",
}


def get_gspread_client():
    """Initialize gspread client from Streamlit secrets or service account file."""
    if not GSPREAD_AVAILABLE:
        return None, "gspread / google-auth not installed. Check requirements.txt."
    try:
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=SCOPES
            )
        elif os.path.exists("service_account.json"):
            creds = Credentials.from_service_account_file(
                "service_account.json", scopes=SCOPES
            )
        else:
            return None, "No Google credentials found. Please configure service account."
        client = gspread.authorize(creds)
        return client, None
    except Exception as e:
        return None, str(e)


@st.cache_resource(ttl=300)
def get_database():
    """Get or create the Google Sheets database."""
    client, error = get_gspread_client()
    if error:
        return None, error

    try:
        try:
            spreadsheet = client.open(SPREADSHEET_NAME)
        except gspread.SpreadsheetNotFound:
            spreadsheet = client.create(SPREADSHEET_NAME)
            spreadsheet.share(None, perm_type="anyone", role="writer")

        existing_sheets = [ws.title for ws in spreadsheet.worksheets()]

        for sheet_name, headers in SHEET_SCHEMAS.items():
            if sheet_name not in existing_sheets:
                ws = spreadsheet.add_worksheet(title=sheet_name, rows=1000, cols=len(headers))
                ws.append_row(headers)
            
        # Remove default Sheet1 if exists
        if "Sheet1" in existing_sheets:
            try:
                spreadsheet.del_worksheet(spreadsheet.worksheet("Sheet1"))
            except:
                pass

        # Initialize admin user if not exists
        _ensure_admin_exists(spreadsheet)

        return spreadsheet, None
    except Exception as e:
        return None, str(e)


def _ensure_admin_exists(spreadsheet):
    """Make sure admin user exists in Users sheet."""
    try:
        import hashlib
        ws = spreadsheet.worksheet("Users")
        records = ws.get_all_records()
        usernames = [r.get("username") for r in records]
        if ADMIN_USER["username"] not in usernames:
            pwd_hash = hashlib.sha256(ADMIN_USER["password"].encode()).hexdigest()
            now = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
            ws.append_row([
                ADMIN_USER["username"], pwd_hash, ADMIN_USER["role"],
                ADMIN_USER["email"], now, "true"
            ])
    except Exception as e:
        print(f"Admin init error: {e}")


def get_users(spreadsheet) -> pd.DataFrame:
    try:
        ws = spreadsheet.worksheet("Users")
        records = ws.get_all_records()
        return pd.DataFrame(records) if records else pd.DataFrame(columns=SHEET_SCHEMAS["Users"])
    except:
        return pd.DataFrame(columns=SHEET_SCHEMAS["Users"])


def authenticate_user(spreadsheet, username: str, password: str) -> dict | None:
    """Authenticate user. Returns user dict or None."""
    import hashlib
    pwd_hash = hashlib.sha256(password.encode()).hexdigest()
    
    # Check admin hardcoded
    if username == ADMIN_USER["username"] and password == ADMIN_USER["password"]:
        return {"username": username, "role": "admin", "email": ADMIN_USER["email"]}

    if spreadsheet is None:
        return None
    
    try:
        users_df = get_users(spreadsheet)
        if users_df.empty:
            return None
        user_row = users_df[
            (users_df["username"] == username) &
            (users_df["password_hash"] == pwd_hash) &
            (users_df["is_active"].astype(str).str.lower() == "true")
        ]
        if not user_row.empty:
            return user_row.iloc[0].to_dict()
        return None
    except:
        return None


def create_user(spreadsheet, username, password, email, role="trader") -> tuple[bool, str]:
    """Create a new user in Users sheet."""
    import hashlib
    try:
        users_df = get_users(spreadsheet)
        if username in users_df["username"].values:
            return False, f"Username '{username}' already exists."
        pwd_hash = hashlib.sha256(password.encode()).hexdigest()
        now = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
        ws = spreadsheet.worksheet("Users")
        ws.append_row([username, pwd_hash, role, email, now, "true"])
        return True, "User created successfully."
    except Exception as e:
        return False, str(e)


def delete_user(spreadsheet, username) -> tuple[bool, str]:
    """Delete a user from Users sheet."""
    try:
        if username == "admin":
            return False, "Cannot delete admin user."
        ws = spreadsheet.worksheet("Users")
        records = ws.get_all_records()
        for i, record in enumerate(records):
            if record.get("username") == username:
                ws.delete_rows(i + 2)  # +2 for header and 0-index
                return True, f"User '{username}' deleted."
        return False, "User not found."
    except Exception as e:
        return False, str(e)


def get_active_trades(spreadsheet, username=None) -> pd.DataFrame:
    try:
        ws = spreadsheet.worksheet("ActiveTrades")
        records = ws.get_all_records()
        df = pd.DataFrame(records) if records else pd.DataFrame(columns=SHEET_SCHEMAS["ActiveTrades"])
        if username and not df.empty:
            df = df[df["username"] == username]
        return df
    except:
        return pd.DataFrame(columns=SHEET_SCHEMAS["ActiveTrades"])


def add_active_trade(spreadsheet, trade: dict) -> tuple[bool, str]:
    try:
        ws = spreadsheet.worksheet("ActiveTrades")
        row = [trade.get(col, "") for col in SHEET_SCHEMAS["ActiveTrades"]]
        ws.append_row(row)
        return True, "Trade added."
    except Exception as e:
        return False, str(e)


def close_trade(spreadsheet, trade_id, close_price, result) -> tuple[bool, str]:
    """Move trade from ActiveTrades to TradeHistory."""
    try:
        active_ws = spreadsheet.worksheet("ActiveTrades")
        history_ws = spreadsheet.worksheet("TradeHistory")
        
        records = active_ws.get_all_records()
        for i, record in enumerate(records):
            if str(record.get("trade_id")) == str(trade_id):
                now = datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
                entry = float(record.get("entry_price", 0))
                direction = record.get("direction", "BUY")
                lot = float(record.get("lot_size", 0.01))
                pnl = (close_price - entry) * (1 if direction == "BUY" else -1) * lot * 100000
                
                history_row = [
                    record.get("trade_id"), record.get("username"), record.get("symbol"),
                    record.get("direction"), record.get("entry_price"),
                    record.get("sl_price"), record.get("tp_price"), record.get("lot_size"),
                    record.get("open_time"), now, close_price, round(pnl, 2), result,
                    record.get("strategy"), record.get("probability_score")
                ]
                history_ws.append_row(history_row)
                active_ws.delete_rows(i + 2)
                return True, f"Trade closed with {result}. P&L: ${round(pnl, 2)}"
        return False, "Trade not found."
    except Exception as e:
        return False, str(e)


def get_trade_history(spreadsheet, username=None) -> pd.DataFrame:
    try:
        ws = spreadsheet.worksheet("TradeHistory")
        records = ws.get_all_records()
        df = pd.DataFrame(records) if records else pd.DataFrame(columns=SHEET_SCHEMAS["TradeHistory"])
        if username and not df.empty and "username" in df.columns:
            df = df[df["username"] == username]
        return df
    except:
        return pd.DataFrame(columns=SHEET_SCHEMAS["TradeHistory"])
