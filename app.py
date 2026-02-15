import streamlit as st
import yfinance as yf
import pandas as pd
import google.generativeai as genai
import plotly.graph_objects as go
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
import feedparser

# --- 1. GOOGLE SHEETS සම්බන්ධතාවය ---
def get_user_sheet():
    try:
        scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        # Streamlit Secrets වල 'gcp_service_account' ලෙස JSON එක තිබිය යුතුය
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scope)
        client = gspread.authorize(creds)
        # ඔබගේ Google Sheet එකේ නම මෙහි නිවැරදිව ඇතුළත් කරන්න
        sheet = client.open("Forex_User_DB").sheet1 
        return sheet
    except Exception as e:
        st.error(f"Database දෝෂය: {e}")
        return None

# --- 2. GEMINI KEY ROTATION LOGIC ---
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
        except Exception:
            st.session_state.key_index = (st.session_state.key_index + 1) % len(keys)
    return "කණගාටුයි, සියලුම AI සේවා මේ මොහොතේ කාර්යබහුලයි. පසුව උත්සාහ කරන්න."

# --- 3. UI සැකසුම් (PAGE CONFIG) ---
st.set_page_config(page_title="Forex Pro Sinhala AI", layout="wide")

# Session State මගින් Login තත්ත්වය පවත්වා ගැනීම
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

# --- 4. LOGIN තිරය ---
def login_screen():
    st.title("🔐 Forex Pro පද්ධතියට ඇතුල් වන්න")
    user_input = st.text_input("පරිශීලක නාමය (Username)")
    pass_input = st.text_input("මුරපදය (Password)", type="password")
    
    if st.button("Log In"):
        sheet = get_user_sheet()
        if sheet:
            records = sheet.get_all_records()
            user_data = next((item for item in records if item["Username"] == user_input), None)
            
            if user_data and str(user_data["Password"]) == pass_input:
                expiry_date = datetime.strptime(user_data["Expiry_Date"], "%Y-%m-%d")
                if expiry_date > datetime.now():
                    st.session_state.logged_in = True
                    st.session_state.user_data = user_data
                    st.rerun()
                else:
                    st.error("❌ ඔබේ පැකේජය අවසන් වී ඇත! කරුණාකර Admin සම්බන්ධ කරගන්න.")
            else:
                st.error("❌ වැරදි Username හෝ Password එකක්!")

    st.divider()
    st.info("පැකේජ ලබා ගැනීමට හෝ සහාය සඳහා: [WhatsApp](https://wa.me/947XXXXXXXX) | [Telegram](https://t.me/YourUsername)")

# --- 5. පද්ධතියට ලොග් වූ පසු පෙනෙන කොටස ---
if not st.session_state.logged_in:
    login_screen()
else:
    user = st.session_state.user_data
    expiry_date = datetime.strptime(user["Expiry_Date"], "%Y-%m-%d")
    days_left = (expiry_date - datetime.now()).days

    # Sidebar තොරතුරු
    st.sidebar.title(f"ආයුබෝවන්, {user['Username']}!")
    if days_left <= 5:
        st.sidebar.warning(f"⚠️ ඔබේ කාලය තව දින {days_left} කින් අවසන් වේ!")
    
    st.sidebar.subheader("🆘 උදව් සහ සහාය")
    st.sidebar.link_button("Contact Admin", "https://t.me/YourUsername")
    
    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # Admin Panel (Admin ට පමණක් පෙනේ)
    if user["Role"] == "admin":
        with st.expander("🛠️ Admin Panel - නව පාරිභෝගිකයන් එකතු කිරීම"):
            new_u = st.text_input("New Username")
            new_p = st.text_input("New Password")
            sub_days = st.number_input("දින ගණන", value=30)
            if st.button("පාරිභෝගිකයා එකතු කරන්න"):
                sheet = get_user_sheet()
                if sheet:
                    exp = (datetime.now() + timedelta(days=sub_days)).strftime("%Y-%m-%d")
                    sheet.append_row([new_u, new_p, "user", exp])
                    st.success(f"{new_u} සාර්ථකව එකතු කළා!")

    # Trading Dashboard
    st.title("📊 SMC + SK AI Trading Dashboard")
    
    pair = st.sidebar.selectbox("මුදල් යුගලය", ["EURUSD=X", "GBPUSD=X", "XAUUSD=X", "USDJPY=X"])
    tf = st.sidebar.selectbox("කාලරාමුව", ["15m", "1h", "4h"])

    # Data Fetching
    df = yf.download(pair, period="60d", interval=tf)
    
    if not df.empty:
        # --- නිවැරදි කරන ලද SMC LOGIC (ValueError Fix) ---
        last_c = float(df['Close'].iloc[-1])
        prev_h = float(df['High'].iloc[-20:-1].max())
        prev_l = float(df['Low'].iloc[-20:-1].min())
        
        if last_c > prev_h:
            struct = "Bullish (ඉහළට) 🟢"
        elif last_c < prev_l:
            struct = "Bearish (පහළට) 🔴"
        else:
            struct = "Ranging ↔️"

        col1, col2 = st.columns([2, 1])
        
        with col1:
            st.subheader(f"📈 {pair} සජීවී ප්‍රස්ථාරය")
            fig = go.Figure(data=[go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'])])
            fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, height=500)
            st.plotly_chart(fig, use_container_width=True)
            st.write(f"වෙළඳපල ප්‍රවණතාවය (Market Structure): **{struct}**")
            

        with col2:
            st.subheader("🤖 AI පුවත් විශ්ලේෂණය")
            if st.button("AI Analyze කරන්න"):
                with st.spinner("පුවත් සහ ප්‍රස්ථාරය අධ්‍යයනය කරමින්..."):
                    feed = feedparser.parse("https://www.forexfactory.com/ff_calendar_thisweek.xml")
                    news_summary = "\n".join([e.title for e in feed.entries[:5]])
                    prompt = f"Analyze Forex news: {news_summary}. Trend: {struct}. Pair: {pair}. Give trading advice in SINHALA."
                    st.info(get_ai_analysis(prompt))
            
            st.divider()
            st.subheader("🎯 SK Strategy Zones")
            high_p, low_p = float(df['High'].max()), float(df['Low'].min())
            fib_618 = low_p + (high_p - low_p) * 0.618
            st.write(f"Discount Zone (0.618): **{fib_618:.5f}**")
            
    else:
        st.error("දත්ත ලබා ගැනීමට නොහැකි විය. කරුණාකර පසුව උත්සාහ කරන්න.")
