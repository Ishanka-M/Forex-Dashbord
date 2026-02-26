"""
modules/database.py  — FX-WavePulse Pro v7
Auto-creates ALL sheets, duplicate prevention,
SL/TP auto-monitor, user-level settings, notifications
"""
try:
    import gspread
    from gspread.exceptions import APIError
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    gspread = APIError = Credentials = None

import pandas as pd
import streamlit as st
import hashlib, uuid, os
from datetime import datetime
import pytz

COLOMBO_TZ       = pytz.timezone("Asia/Colombo")
SPREADSHEET_NAME = "Forex_User_DB"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
          "https://www.googleapis.com/auth/drive"]

SHEET_SCHEMAS = {
    "Users":        ["username","password_hash","role","email","created_at","is_active"],
    "ActiveTrades": ["trade_id","username","symbol","direction",
                     "entry_price","sl_price","tp_price","tp2_price","tp3_price",
                     "lot_size","open_time","strategy","timeframe",
                     "probability_score","ew_pattern","smc_bias",
                     "status","current_price","pnl","gemini_verdict"],
    "TradeHistory": ["trade_id","username","symbol","direction",
                     "entry_price","sl_price","tp_price",
                     "lot_size","open_time","close_time",
                     "close_price","pnl","result","strategy",
                     "probability_score","gemini_verdict"],
    "SignalLog":    ["signal_id","username","symbol","direction","timeframe",
                     "entry_price","sl_price","tp_price","tp2_price","tp3_price",
                     "probability_score","ew_pattern","gemini_verdict",
                     "news_sinhala","auto_captured","captured_at"],
    "Notifications":["notif_id","username","type","symbol","direction",
                     "message","created_at","is_read"],
    "Settings":     ["username","auto_capture","min_score","notify_sl",
                     "notify_tp","notify_signal","updated_at"],
}

ADMIN_USER = {"username":"admin","password":"admin@#123",
              "role":"admin","email":"admin@fxwavepulse.com"}
DEFAULT_SETTINGS = {"auto_capture":"true","min_score":"40",
                    "notify_sl":"true","notify_tp":"true","notify_signal":"true"}

def _now(): return datetime.now(COLOMBO_TZ).strftime("%Y-%m-%d %H:%M:%S")
def _sf(v,d=0.0):
    try: return float(v)
    except: return d
def _df_empty(k): return pd.DataFrame(columns=SHEET_SCHEMAS[k])
def _to_df(rec,k): return pd.DataFrame(rec) if rec else _df_empty(k)

# ── Credentials ──────────────────────────────────────────────
def _build_creds():
    if not GSPREAD_AVAILABLE: raise RuntimeError("gspread not installed")
    if "gcp_service_account" in st.secrets:
        info = dict(st.secrets["gcp_service_account"])
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n","\n")
        return Credentials.from_service_account_info(info, scopes=SCOPES)
    if os.path.exists("service_account.json"):
        return Credentials.from_service_account_file("service_account.json", scopes=SCOPES)
    raise RuntimeError("No credentials. Configure [gcp_service_account] in Secrets.")

def _open_ss():
    client = gspread.authorize(_build_creds())
    try: ss = client.open(SPREADSHEET_NAME)
    except:
        ss = client.create(SPREADSHEET_NAME)
        ss.share(None, perm_type="anyone", role="writer")
    existing = {ws.title for ws in ss.worksheets()}
    for name, headers in SHEET_SCHEMAS.items():
        if name not in existing:
            ws = ss.add_worksheet(title=name, rows=5000, cols=len(headers))
            ws.append_row(headers, value_input_option="RAW")
    if "Sheet1" in existing:
        try: ss.del_worksheet(ss.worksheet("Sheet1"))
        except: pass
    return ss

@st.cache_resource(ttl=600, show_spinner=False)
def get_database():
    if not GSPREAD_AVAILABLE: return None,"gspread not installed"
    try:
        ss = _open_ss(); _ensure_admin(ss); return ss,None
    except Exception as e: return None,str(e)

def get_fresh_spreadsheet():
    if not GSPREAD_AVAILABLE: return None,"gspread not installed"
    try: return _open_ss(),None
    except Exception as e: return None,f"Connection: {e}"

# ── Admin ────────────────────────────────────────────────────
def _ensure_admin(ss):
    try:
        ws = ss.worksheet("Users")
        if ADMIN_USER["username"] not in [r.get("username") for r in ws.get_all_records()]:
            ph = hashlib.sha256(ADMIN_USER["password"].encode()).hexdigest()
            ws.append_row([ADMIN_USER["username"],ph,ADMIN_USER["role"],
                           ADMIN_USER["email"],_now(),"true"],value_input_option="RAW")
    except Exception as e: print(f"[admin] {e}")

# ── Users ────────────────────────────────────────────────────
def get_users(ss):
    try: return _to_df(ss.worksheet("Users").get_all_records(),"Users")
    except: return _df_empty("Users")

def authenticate_user(ss, username, password):
    if username==ADMIN_USER["username"] and password==ADMIN_USER["password"]:
        return {"username":username,"role":"admin","email":ADMIN_USER["email"]}
    if ss is None: return None
    try:
        ph  = hashlib.sha256(password.encode()).hexdigest()
        df  = get_users(ss)
        row = df[(df["username"]==username)&(df["password_hash"]==ph)&
                 (df["is_active"].astype(str).str.lower()=="true")]
        return row.iloc[0].to_dict() if not row.empty else None
    except: return None

def create_user(ss, username, password, email, role="trader"):
    try:
        if username in get_users(ss)["username"].values:
            return False,f"'{username}' already exists."
        ss_w,err = get_fresh_spreadsheet()
        if err: return False,err
        ph = hashlib.sha256(password.encode()).hexdigest()
        ss_w.worksheet("Users").append_row([username,ph,role,email,_now(),"true"],
                                            value_input_option="RAW")
        _init_settings(ss_w,username)
        return True,"User created."
    except Exception as e: return False,str(e)

def delete_user(ss, username):
    try:
        if username=="admin": return False,"Cannot delete admin."
        ss_w,err = get_fresh_spreadsheet()
        if err: return False,err
        ws = ss_w.worksheet("Users")
        for i,r in enumerate(ws.get_all_records()):
            if r.get("username")==username:
                ws.delete_rows(i+2); return True,f"'{username}' deleted."
        return False,"Not found."
    except Exception as e: return False,str(e)

# ── Settings ─────────────────────────────────────────────────
def _init_settings(ss, username):
    try:
        ws = ss.worksheet("Settings")
        if not any(r.get("username")==username for r in ws.get_all_records()):
            ws.append_row([username,
                DEFAULT_SETTINGS["auto_capture"],DEFAULT_SETTINGS["min_score"],
                DEFAULT_SETTINGS["notify_sl"],DEFAULT_SETTINGS["notify_tp"],
                DEFAULT_SETTINGS["notify_signal"],_now()],value_input_option="RAW")
    except Exception as e: print(f"[settings] {e}")

def get_user_settings(ss, username) -> dict:
    try:
        _init_settings(ss, username)
        for r in ss.worksheet("Settings").get_all_records():
            if r.get("username")==username: return r
    except: pass
    return {**DEFAULT_SETTINGS,"username":username}

def save_user_settings(ss, username, updates: dict):
    try:
        ss_w,err = get_fresh_spreadsheet()
        if err: return False,err
        ws      = ss_w.worksheet("Settings")
        headers = SHEET_SCHEMAS["Settings"]
        for i,r in enumerate(ws.get_all_records()):
            if r.get("username")==username:
                for col,val in updates.items():
                    if col in headers:
                        ws.update_cell(i+2,headers.index(col)+1,str(val))
                ws.update_cell(i+2,headers.index("updated_at")+1,_now())
                return True,"Saved."
        _init_settings(ss_w,username); return True,"Initialised."
    except Exception as e: return False,str(e)

# ── Notifications ────────────────────────────────────────────
def _add_notif(ss, username, ntype, symbol, direction, message):
    try:
        ss_w,err = get_fresh_spreadsheet()
        if err: return
        ss_w.worksheet("Notifications").append_row([
            str(uuid.uuid4())[:8].upper(),username,ntype,symbol,direction,
            message,_now(),"false"],value_input_option="RAW")
    except Exception as e: print(f"[notif] {e}")

def get_notifications(ss, username, unread_only=True):
    try:
        df = _to_df(ss.worksheet("Notifications").get_all_records(),"Notifications")
        if df.empty: return df
        df = df[df["username"]==username]
        if unread_only:
            df = df[df["is_read"].astype(str).str.lower()=="false"]
        return df.sort_values("created_at",ascending=False) if not df.empty else df
    except: return _df_empty("Notifications")

def mark_all_read(ss, username):
    try:
        ss_w,err = get_fresh_spreadsheet()
        if err: return
        ws      = ss_w.worksheet("Notifications")
        headers = SHEET_SCHEMAS["Notifications"]
        col_idx = headers.index("is_read")+1
        for i,r in enumerate(ws.get_all_records()):
            if r.get("username")==username and str(r.get("is_read","")).lower()=="false":
                ws.update_cell(i+2,col_idx,"true")
    except Exception as e: print(f"[mark read] {e}")

# ── Active Trades ────────────────────────────────────────────
def get_active_trades(ss, username=None):
    try:
        df = _to_df(ss.worksheet("ActiveTrades").get_all_records(),"ActiveTrades")
        if username and not df.empty: df = df[df["username"]==username]
        return df
    except: return _df_empty("ActiveTrades")

def _get_active_ids(ss) -> set:
    try: return set(v for v in ss.worksheet("ActiveTrades").col_values(1)[1:] if v)
    except: return set()

def add_active_trade(ss, trade: dict):
    if ss is None: return False,"Spreadsheet is None"
    try:
        ws = ss.worksheet("ActiveTrades")
        if str(trade.get("trade_id","")) in set(ws.col_values(1)[1:]):
            return False,f"Duplicate: {trade.get('trade_id')} already exists"
        row = [str(trade.get(col,"")) for col in SHEET_SCHEMAS["ActiveTrades"]]
        ws.append_row(row, value_input_option="USER_ENTERED")
        return True,f"Saved {trade.get('trade_id')}"
    except Exception as e: return False,f"{type(e).__name__}: {e}"

def auto_capture_signal(ss, sig, username: str, gemini_verdict: str="") -> tuple:
    cfg       = get_user_settings(ss, username)
    if str(cfg.get("auto_capture","true")).lower()!="true":
        return False,"Auto-capture off"
    min_score = int(cfg.get("min_score",40) or 40)
    if sig.probability_score < min_score:
        return False,f"Score {sig.probability_score}% < threshold {min_score}%"
    ss_w,err = get_fresh_spreadsheet()
    if err: return False,err
    if sig.trade_id in _get_active_ids(ss_w):
        return False,"Already captured"
    trade = {
        "trade_id":          sig.trade_id,
        "username":          username,
        "symbol":            sig.symbol,
        "direction":         sig.direction,
        "entry_price":       str(sig.entry_price),
        "sl_price":          str(sig.sl_price),
        "tp_price":          str(sig.tp_price),
        "tp2_price":         str(getattr(sig,"tp2_price","") or ""),
        "tp3_price":         str(getattr(sig,"tp3_price","") or ""),
        "lot_size":          str(sig.lot_size),
        "open_time":         sig.generated_at,
        "strategy":          sig.strategy,
        "timeframe":         getattr(sig,"timeframe",""),
        "probability_score": str(sig.probability_score),
        "ew_pattern":        sig.ew_pattern,
        "smc_bias":          str(sig.smc_bias)[:120],
        "status":            "open",
        "current_price":     str(sig.entry_price),
        "pnl":               "0",
        "gemini_verdict":    gemini_verdict,
    }
    ok,msg = add_active_trade(ss_w, trade)
    if ok and str(cfg.get("notify_signal","true")).lower()=="true":
        _add_notif(ss_w,username,"SIGNAL",sig.symbol,sig.direction,
            f"📊 Auto-captured {sig.symbol} {sig.direction} @ {sig.entry_price} "
            f"(Score:{sig.probability_score}% Gemini:{gemini_verdict or 'N/A'})")
    return ok,msg

def update_trade_pnl(ss, trade_id, current_price, pnl):
    try:
        ss_w,err = get_fresh_spreadsheet()
        if err: return False,err
        ws      = ss_w.worksheet("ActiveTrades")
        headers = SHEET_SCHEMAS["ActiveTrades"]
        for i,r in enumerate(ws.get_all_records()):
            if str(r.get("trade_id"))==str(trade_id):
                ws.update_cell(i+2,headers.index("current_price")+1,str(round(current_price,5)))
                ws.update_cell(i+2,headers.index("pnl")+1,str(round(pnl,2)))
                return True,"Updated"
        return False,"Not found"
    except Exception as e: return False,str(e)

# ── Close Trade ──────────────────────────────────────────────
def close_trade(ss, trade_id, close_price, result):
    try:
        ss_w,err = get_fresh_spreadsheet()
        if err: return False,f"Connection: {err}"
        active_ws  = ss_w.worksheet("ActiveTrades")
        history_ws = ss_w.worksheet("TradeHistory")
        for i,r in enumerate(active_ws.get_all_records()):
            if str(r.get("trade_id"))!=str(trade_id): continue
            entry     = _sf(r.get("entry_price"))
            direction = r.get("direction","BUY")
            lot       = _sf(r.get("lot_size",0.01),0.01)
            pnl       = (close_price-entry)*(1 if direction=="BUY" else -1)*lot*100000
            username  = r.get("username","")
            symbol    = r.get("symbol","")
            hist = []
            for col in SHEET_SCHEMAS["TradeHistory"]:
                if   col=="close_time":  hist.append(_now())
                elif col=="close_price": hist.append(str(close_price))
                elif col=="pnl":         hist.append(str(round(pnl,2)))
                elif col=="result":      hist.append(result)
                else:                    hist.append(str(r.get(col,"")))
            history_ws.append_row(hist, value_input_option="USER_ENTERED")
            active_ws.delete_rows(i+2)
            pnl_str = f"${pnl:+.2f}"
            cfg = get_user_settings(ss_w, username)
            if result=="TP" and str(cfg.get("notify_tp","true")).lower()=="true":
                _add_notif(ss_w,username,"TP",symbol,direction,
                    f"🎉 {symbol} {direction} — TP Hit! Profit: {pnl_str}")
            elif result=="SL" and str(cfg.get("notify_sl","true")).lower()=="true":
                _add_notif(ss_w,username,"SL",symbol,direction,
                    f"🛑 {symbol} {direction} — SL Hit. Loss: {pnl_str}")
            else:
                _add_notif(ss_w,username,"CLOSE",symbol,direction,
                    f"🔒 {symbol} closed manually. P&L: {pnl_str}")
            return True,f"Closed → {result} | P&L: {pnl_str}"
        return False,f"Trade '{trade_id}' not found."
    except Exception as e: return False,f"{type(e).__name__}: {e}"

# ── SL/TP Auto-Monitor ───────────────────────────────────────
def check_sl_tp_hits(ss, live_prices: dict) -> list:
    closed = []
    try: records = ss.worksheet("ActiveTrades").get_all_records()
    except: return closed
    for r in records:
        trade_id  = str(r.get("trade_id",""))
        symbol    = r.get("symbol","")
        direction = r.get("direction","BUY")
        sl        = _sf(r.get("sl_price"))
        tp        = _sf(r.get("tp_price"))
        if not trade_id or not symbol: continue
        current = live_prices.get(symbol)
        if current is None: continue
        hit = None
        if direction=="BUY":
            if tp>0 and current>=tp: hit="TP"
            elif sl>0 and current<=sl: hit="SL"
        else:
            if tp>0 and current<=tp: hit="TP"
            elif sl>0 and current>=sl: hit="SL"
        if hit:
            ok,msg = close_trade(ss,trade_id,current,hit)
            if ok:
                closed.append({"trade_id":trade_id,"symbol":symbol,
                               "direction":direction,"result":hit,
                               "price":current,"msg":msg})
    return closed

# ── Trade History ────────────────────────────────────────────
def get_trade_history(ss, username=None):
    try:
        df = _to_df(ss.worksheet("TradeHistory").get_all_records(),"TradeHistory")
        if username and not df.empty and "username" in df.columns:
            df = df[df["username"]==username]
        return df
    except: return _df_empty("TradeHistory")
