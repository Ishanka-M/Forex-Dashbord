# 📈 FX-WavePulse Pro

**Professional Forex Trading & Management System**  
Built with Streamlit · Elliott Wave Theory · Smart Money Concepts · Google Sheets DB

---

## 🚀 Features

| Feature | Description |
|---|---|
| 🔐 Auth | Login system with hardcoded admin + Google Sheets user DB |
| 🌊 Elliott Wave | Automated 5-wave impulse & ABC corrective detection |
| 💡 SMC Analysis | Order Blocks, BOS, CHoCH, Fair Value Gaps |
| 📊 Multi-Timeframe | Swing (H4/D1) and Short-term (M5/M15/H1) strategies |
| 🎯 Signal Engine | Probability-scored signals combining EW + SMC confluences |
| 📡 Live Data | Real-time prices via yfinance (EURUSD, GBPUSD, GOLD, BTC, etc.) |
| 🕐 Colombo Time | All timestamps in Asia/Colombo (LKT) timezone |
| 💼 Trade Tracker | Active trades with live P&L, close to history |
| 👑 Admin Panel | User create/delete management |

---

## 🏗️ Project Structure

```
fx-wavepulse-pro/
├── app.py                      # Main Streamlit application
├── requirements.txt
├── .gitignore
├── .streamlit/
│   ├── config.toml             # Theme & server config
│   └── secrets.toml.template  # Google credentials template
└── modules/
    ├── __init__.py
    ├── database.py             # Google Sheets CRUD layer
    ├── market_data.py          # yfinance live data fetcher
    ├── elliott_wave.py         # Elliott Wave analysis engine
    ├── smc_analysis.py         # SMC: OB, FVG, BOS, CHoCH
    ├── signal_engine.py        # Trade signal generator
    └── charts.py               # Plotly chart builder
```

---

## ⚡ Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/your-username/fx-wavepulse-pro.git
cd fx-wavepulse-pro
pip install -r requirements.txt
```

### 2. Google Sheets Setup

#### a) Create a Google Cloud Project
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project
3. Enable **Google Sheets API** and **Google Drive API**
4. Create a **Service Account** → download the JSON key

#### b) Configure Credentials
```bash
cp .streamlit/secrets.toml.template .streamlit/secrets.toml
# Edit secrets.toml and paste your service account credentials
```

Or place your service account JSON as `service_account.json` in the root directory.

#### c) Share the Spreadsheet
The app auto-creates `Forex_User_DB` in your Google Drive.  
Make sure the service account email has **Editor** access.

### 3. Run Locally
```bash
streamlit run app.py
```

---

## 🌐 Deploy to Streamlit Cloud

1. Push your code to GitHub (ensure `secrets.toml` is in `.gitignore`)
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. Connect your repo → set `app.py` as the main file
4. In **Secrets**, paste your `secrets.toml` contents

---

## 🔑 Default Login

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin@#123` |

> Admin can create additional trader accounts from the Admin Panel.

---

## 📊 Google Sheets Schema

The app auto-initializes these sheets in `Forex_User_DB`:

| Sheet | Purpose |
|---|---|
| `Users` | User accounts (username, hashed password, role) |
| `ActiveTrades` | Open positions with entry/SL/TP |
| `TradeHistory` | Closed trades with P&L and results |
| `MarketData` | Cached market data (for future extensions) |

---

## 🌊 Strategy Logic

### Elliott Wave Engine
- Uses `scipy.signal.argrelextrema` to detect swing highs/lows
- Validates 3 core EW rules:
  - Wave 2 retraces ≤100% of Wave 1 (ideal: 38.2%–78.6%)
  - Wave 3 is never the shortest among waves 1, 3, 5
  - Wave 4 never overlaps Wave 1's territory
- Projects Wave 5 target using Wave 1 proportions
- Falls back to ABC corrective pattern identification

### SMC Analysis
- **Order Blocks**: Last opposing candle before strong directional move
- **Fair Value Gaps**: Imbalances between candle[i-1] high and candle[i+1] low
- **BOS/CHoCH**: Structural shifts via pivot high/low breaks
- ATR-normalized strength scoring

### Signal Scoring (0–100%)
| Confluence | Points |
|---|---|
| 5-wave impulse confirmed | +25 |
| EW confidence > 70% | +10 |
| CHoCH in direction | +20 |
| BOS confirmation | +15 |
| Unmitigated Order Block | +15 |
| Unfilled FVG | +10 |
| Multi-timeframe alignment | +10 |

---

## ⚠️ Disclaimer

This tool is for **educational and analytical purposes only**.  
Forex and CFD trading involves significant risk of loss.  
Always use proper risk management and consult a licensed financial advisor.

---

## 📄 License

MIT License — Use freely, trade responsibly.
