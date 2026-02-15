import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import feedparser
import urllib.parse

# --- ADMIN පෞද්ගලික තොරතුරු (මෙහි ඔබේ තොරතුරු දාන්න) ---
ADMIN_TELEGRAM_LINK = "https://t.me/YourUsername" # ඔබේ Telegram Link එක
ADMIN_WHATSAPP_LINK = "https://wa.me/947XXXXXXXX" # ඔබේ WhatsApp අංකය

# --- GOOGLE SHEETS සම්බන්ධතාවය ---
def get_user_sheet():
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
    client = gspread.authorize(creds)
    sheet = client.open("Forex_User_DB").sheet1 
    return sheet

# --- GEMINI KEY ROTATION LOGIC ---
def get_ai_analysis(prompt):
    keys = st.secrets["GEMINI_KEYS"]
    if "key_index" not in st.session_state:
        st.session_state.key_index = 0

    for _ in range(len(keys)):
        try:
            genai.configure(api_key=keys[st.session_state.key_index])
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            return response.text
        except:
            st.session_state.key_index = (st.session_state.key_index + 1) % len(keys)
    return "කණගාටුයි, සියලුම AI සේවා මේ මොහොතේ කාර්යබහුලයි."

# --- UI සැකසුම් ---
st.set_page_config(page_title="Forex Pro Sinhala AI", layout="wide")

if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# --- පද්ධතියට ඇතුල් වීමේ තිරය ---
def login_screen():
    st.title("🔐 Forex Pro පද්ධතියට ඇතුල් වන්න")
    user_input = st.text_input("පරිශීලක නාමය (Username)")
    pass_input = st.text_input("මුරපදය (Password)", type="password")
    
    if st.button("Log In"):
        try:
            sheet = get_user_sheet()
            records = sheet.get_all_records()
            user_data = next((item for item in records if item["Username"] == user_input), None)
            
            if user_data and str(user_data["Password"]) == pass_input:
                expiry_date = datetime.strptime(user_data["Expiry_Date"], "%Y-%m-%d")
                if expiry_date > datetime.now():
                    st.session_state.logged_in = True
                    st.session_state.user_data = user_data
                    st.rerun()
                else:
                    st.error("❌ ඔබේ පැකේජය අවසන් වී ඇත! කරුණාකර පහත Support මගින් Admin සම්බන්ධ කරගන්න.")
            else:
                st.error("❌ වැරදි තොරතුරු ඇතුළත් කළා!")
        except Exception as e:
            st.error("Database සම්බන්ධතාවයේ දෝෂයකි. කරුණාකර පසුව උත්සාහ කරන්න.")

    st.divider()
    st.info("පැකේජ මිලදී ගැනීමට හෝ ගැටළු සඳහා Admin සම්බන්ධ කරගන්න:")
    st.write(f"💬 [Telegram]({ADMIN_TELEGRAM_LINK}) | [WhatsApp]({ADMIN_WHATSAPP_LINK})")

if not st.session_state.logged_in:
    login_screen()
else:
    # --- ප්‍රධාන පද්ධතිය ---
    user = st.session_state.user_data
    expiry_date = datetime.strptime(user["Expiry_Date"], "%Y-%m-%d")
    days_left = (expiry_date - datetime.now()).days

    # Sidebar
    st.sidebar.title(f"ආයුබෝවන්, {user['Username']}!")
    if days_left <= 5:
        st.sidebar.warning(f"⚠️ ඔබේ කාලය තව දින {days_left} කින් අවසන් වේ!")
    
    # --- SUPPORT BUTTONS IN SIDEBAR ---
    st.sidebar.divider()
    st.sidebar.subheader("🆘 උදව් සහ සහාය")
    st.sidebar.write("ඔබට ගැටලුවක් තිබේද?")
    st.sidebar.link_button("Telegram සහාය", ADMIN_TELEGRAM_LINK)
    st.sidebar.link_button("WhatsApp සහාය", ADMIN_WHATSAPP_LINK)
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # --- ADMIN PANEL ---
    if user["Role"] == "admin":
        with st.expander("🛠️ Admin පාලක පැනලය (ඔබට පමණක් පෙනේ)"):
            new_u = st.text_input("නව පාරිභෝගිකයාගේ නම")
            new_p = st.text_input("මුරපදය")
            sub_days = st.number_input("කාලය (දින ගණන)", value=30)
            if st.button("පාරිභෝගිකයා එකතු කරන්න"):
                sheet = get_user_sheet()
                exp = (datetime.now() + timedelta(days=sub_days)).strftime("%Y-%m-%d")
                sheet.append_row([new_u, new_p, "user", exp])
                st.success(f"{new_u} සාර්ථකව එකතු කළා!")

    # --- TRADING SYSTEM ---
    st.title("📊 SMC + SK AI Trading Dashboard")
    
    pair = st.sidebar.selectbox("මුදල් යුගලය", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X"])
    tf = st.sidebar.selectbox("කාලරාමුව", ["15m", "1h", "4h"])

    df = yf.download(pair, period="60d", interval=tf)
    
    # Structure Logic
    last_c = df['Close'].iloc[-1]
    prev_h = df['High'].iloc[-20:-1].max()
    prev_l = df['Low'].iloc[-20:-1].min()
    struct = "Bullish (ඉහළට) 🟢" if last_c > prev_h else "Bearish (පහළට) 🔴" if last_c < prev_l else "Ranging ↔️"

    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader(f"📈 {pair} සජීවී ප්‍රස්ථාරය")
        fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False)
        st.plotly_chart(fig, use_container_width=True)
        st.write(f"වෙළඳපල ප්‍රවණතාවය: **{struct}**")
        

    with col2:
        st.subheader("🤖 AI පුවත් විග්‍රහය")
        if st.button("පුවත් Analyze කරන්න"):
            with st.spinner("AI පුවත් සහ ප්‍රස්ථාරය අධ්‍යයනය කරමින් පවතියි..."):
                feed = feedparser.parse("https://www.forexfactory.com/ff_calendar_thisweek.xml")
                news_summary = "\n".join([e.title for e in feed.entries[:5]])
                prompt = f"Analyze Forex news: {news_summary}. Current Price: {last_c}. Trend: {struct}. Provide a detailed trading recommendation in Sinhala."
                st.info(get_ai_analysis(prompt))
        
        st.divider()
        st.subheader("🎯 SK Strategy Levels")
        high_p, low_p = df['High'].max(), df['Low'].min()
        fib_618 = low_p + (high_p - low_p) * 0.618
        st.write(f"Discount Zone (0.618): **{fib_618:.5f}**")
