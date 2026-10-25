# ⚡ CoinDCX Box Theory Trading System (7:15 PM IST US Open Engine)

A high-performance algorithmic trading terminal and automated trade logger built for the **CoinDCX** crypto market, focused on the **19:00 - 19:15 IST (US Open)** liquidity sweep strategy.

---

## 📁 Project Architecture

```
coindcx_box_bot/
├── .env                  # API keys and trade parameters (Excluded from Git)
├── .gitignore            # Protects keys, credentials, and virtual environment
├── credentials.json      # Google Service Account Key for Sheets API
├── app.py                # Live Streamlit Web Terminal & Real-Time Dashboard
├── coindcx_engine.py     # Live API Data Fetcher (RH, RL, SH, SL + 7:15 PM Signal Engine) & backtester
├── strategies.py         # Pluggable STRATEGY_REGISTRY (Box Theory Sweep, 1-Candle 25% ATR Reversal, ...)
├── signal_monitor.py     # 24/7 multi-strategy scanner + strategy-tagged e-mail alerts
├── email_notifier.py     # Gmail SMTP trade notifications
├── sheets_logger.py      # Google Sheets Automated Trade Logger (gspread)
├── requirements.txt      # Python Dependencies
└── README.md             # Documentation and Execution Guide
```

---

## 🎯 Strategy Overview: Box Liquidity Sweeps

- **Trading Window:** 19:00 – 19:15 IST daily (coinciding with the US Equity / Crypto Open).
- **Box Boundaries:**
  - **RH (Range High):** Previous Day High (PDH).
  - **RL (Range Low):** Previous Day Low (PDL).
  - **MID:** Equilibrium Midpoint `(RH + RL) / 2`.
  - **SH (Swing High):** Highest peak beyond RH from the last 15-30 days.
  - **SL (Swing Low):** Lowest trough beyond RL from the last 15-30 days.
- **Signal Triggers:**
  - **SHORT:** 15m candle sweeps RH/SH (`High >= RH`) and closes back inside (`Close < RH`). Stop Loss placed at `max(High, SH) * 1.002`. Targets: `TP1 = MID`, `TP2 = RL`.
  - **LONG:** 15m candle sweeps RL/SL (`Low <= RL`) and closes back inside (`Close > RL`). Stop Loss placed at `min(Low, SL) * 0.998`. Targets: `TP1 = MID`, `TP2 = RH`.
- **Risk & Capital Management:**
  - **Default Margin:** ₹1,00,000 INR per trade.
  - **Leverage:** 5x multiplier (enforced).
  - **Target ROE:** Minimum 5% ROE on TP1 (Midpoint).

---

## 🧠 Modular Multi-Strategy Architecture (`strategies.py`)

All strategies live in [`strategies.py`](strategies.py) and are registered in `STRATEGY_REGISTRY`.
The Signals, Execution, Key Levels and Backtest tabs, the 24/7 e-mail monitor and the backtester all iterate over the registry, so **a new strategy needs no UI changes**.

| ID | Name | Bias / Trigger | SL | TP1 | TP2 |
|---|---|---|---|---|---|
| `box_theory` | **Box Theory Sweep** (baseline, math unchanged) | Sweep of RH / RL closing back inside | `max(high,SH)*1.002` / `min(low,SL)*0.998` | MID | RL / RH |
| `atr_reversal` | **1-Candle 25% ATR Reversal** | Daily close vs SMA50 → 1–3 candle 15m flush/spike ≥ 25% of Daily ATR14 → close beyond previous opposite candle's high/low | `flush_low*0.9985` / `spike_high*1.0015` | 50% retrace | Origin of move |

Both use the 50/50 ratchet exit in the backtester. ATR guards: one trade per flush, flush must be within the last 8 candles, entry must sit between SL and TP1.

**Adding a strategy:** subclass `Strategy`, set `id`, `name`, `tp1_name`, `tp2_name`, implement `compute_levels`, `evaluate_signal`, `plan_setups`, `prepare_backtest`, `backtest_has_context`, `backtest_entry` (optionally `chart_lines`, `chart_markers`, `metric_badges`, `level_rows`), then add it to `STRATEGY_REGISTRY`.

**Alerts:** e-mail subject is `"{SYM} - {Strategy Name} - trade notification"`; body and the `Live_Trades` sheet include Strategy and Trigger Reason. Restrict the background monitor with `ENABLED_STRATEGIES=box_theory,atr_reversal` (default: all).

**1-year comparison (₹10,000 margin, 5x, 50/50 ratchet, USD/INR 88):**

| Strategy | Pair | Trades | Fees (₹) | Win % | Net (₹) |
|---|---|---|---|---|---|
| Box Theory Sweep | SOL | 369 | 21,763 | 49.6 | **+40,317** |
| Box Theory Sweep | ETH | 330 | 19,450 | 47.3 | **+2,359** |
| Box Theory Sweep | BTC | 312 | 17,804 | 48.7 | **−13,227** |
| 1-Candle 25% ATR Reversal | SOL | 152 | 8,960 | 45.4 | **−5,037** |
| 1-Candle 25% ATR Reversal | ETH | 135 | 7,956 | 36.3 | **−9,172** |
| 1-Candle 25% ATR Reversal | BTC | 152 | 8,656 | 28.9 | **−9,415** |

---

## 🚀 Getting Started

### 1. Clone & Set Up Python Virtual Environment

```bash
# Clone or navigate to the repository
cd c:\coindcx_box_bot

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On Windows (CMD):
.venv\Scripts\activate.bat
# On Linux/macOS:
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure `.env` & Secrets

The `.env` file contains your CoinDCX API keys and trade sizing configuration:

```ini
COINDCX_API_KEY=your_coindcx_api_key_here
COINDCX_API_SECRET=your_coindcx_secret_key_here
GOOGLE_SHEET_NAME=Crypto_Trades_Journal
TOTAL_WALLET_INR=250000
MARGIN_PER_TRADE_INR=100000
LEVERAGE=5
USD_INR_RATE=85.0
```

### 4. Configure Google Sheets Logging (`credentials.json`)

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Enable both **Google Sheets API** and **Google Drive API**.
3. Create a **Service Account** and generate a JSON key.
4. Rename this key file to `credentials.json` and place it in the project root.
5. In Google Drive, create a new spreadsheet named **`Crypto_Trades_Journal`**.
6. Click **Share** on your sheet and give `Editor` access to the `client_email` found inside your `credentials.json`.

---

## 🖥️ Launching the Streamlit Terminal

Run the following command in your terminal:

```bash
streamlit run app.py
```

The live web dashboard will open at `http://localhost:8501`, featuring:
- **📡 Live 7:15 PM Monitor:** Real-time US Open signal evaluation, entry, SL, TP1/TP2, ROE metrics, and one-click Google Sheets logging.
- **📐 Today's Key Levels:** Real-time calculated RH, RL, SH, SL, and Equilibrium MID with Plotly candlestick chart overlay.
- **📋 Google Sheet Trade Logger:** Connection tester and manual trade entry validator.
- **📊 Strategy Backtest & Analytics:** Historical win rate, profit factor, drawdown, and monthly performance.

---

## 📤 Pushing to GitHub

To push this repository to GitHub:

```bash
git init
git add .
git commit -m "feat: complete CoinDCX 7:15 PM box engine with google sheets integration"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/coindcx-box-bot.git
git push -u origin main
```
*(Note: `.env` and `credentials.json` are excluded by `.gitignore` to safeguard your keys.)*
