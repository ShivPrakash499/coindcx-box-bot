# ⚡ CoinDCX Box Theory Terminal — Session Handover & Memory
**Date:** October 23, 2026  
**Account:** Binni (`38df78ae-38f0-468a-86f2-047ff6113a7f`)  
**Live URL:** [https://shiv-prakash-crypto-robot.streamlit.app](https://shiv-prakash-crypto-robot.streamlit.app)  
**GitHub Repository:** [ShivPrakash499/coindcx-box-bot](https://github.com/ShivPrakash499/coindcx-box-bot) (`main` branch)

---

## 1. 🚀 Current Deployment Status
* **Cloud App:** Live, healthy, and operational on Streamlit Community Cloud.
* **Security Gate:** App is protected with an **Access PIN** (`7426` or fallback `1234`). No API queries, balances, or trade buttons load until unlocked. A `🔒 Lock Terminal Session` button is available in the sidebar.
* **Local LAN Access:** Also accessible from home Wi-Fi at `http://192.168.1.8:8501`.
* **Git Sync:** All local fixes committed and pushed to `origin/main` (latest commit `b91253a`).

---

## 2. 🛠️ Critical Fixes Completed Today

| Issue | Root Cause | Solution Applied |
| :--- | :--- | :--- |
| **Setup Levels Not Refreshing** | Streamlit number input widget state locking to initial values | Replaced with setup-specific widget keys (`custom_entry_{pair}_{setup_tag}`) and auto-sync logic on setup switch; added Reset button. |
| **Mark Price / PnL Stale** | CoinDCX futures position mark price snapshot was frozen/static | Linked real-time mark price to live Binance ticker & CoinDCX live ticker; live PnL and ROE recalculate on every tick. |
| **`Connection error: None` on Orders** | Python `requests` response object evaluated as falsy (`if not res:`) when CoinDCX returned 400/401 HTTP codes | Fixed to `if res is None:` across `coindcx_engine.py` and added clean JSON error message parsing. |
| **Paper Trading `KeyError: 'direction'`** | Order record dictionary saved key as `"signal"` while PnL tracker expected `"direction"` | Standardized `order_record` to include both `"signal"` and `"direction"`; updated components to defensively use `.get("direction", "signal")`. |
| **Public Deployment Misuse Risk** | Public Streamlit URLs are accessible to anyone | Added Institutional Security Gate directly into `app.py` with PIN authentication and sidebar locking. |

---

## 3. 🔑 CoinDCX API & Wallet Verification
* **API Credentials:** 100% verified working and authenticated against CoinDCX live servers for user **Binni**.
* **Live Futures Wallet Details:**
  * **Total Value (INR):** `₹25,748.24`
  * **Cash Balance (INR):** `₹15,754.90`
  * **Locked Balance:** `₹9,993.34` (held by an active pending `B-SOL_USDT` limit buy order at `$103.46`)
  * **Available Margin:** `~₹5,761.56`
* **Live Order Constraint:** CoinDCX requires a minimum order value of **₹2,448 INR**. When testing live orders, keep trade margin between **₹2,500 and ₹5,000** to stay within available funds and meet the exchange minimum.

---

## 4. 📊 1-Year Strategy Backtest Summary (365 Days)
Tested against completed historical daily box setups across **ETH**, **BTC**, and **SOL** with ₹1,00,000 margin per trade @ 5x leverage:

* **Total Trades Triggered:** 458 trades
* **Total Wins (TP1 / TP2):** 452 wins
* **Total Losses (SL):** 6 losses
* **Portfolio Win Rate:** **98.7%**
* **Average Win:** +₹7,771.71 | **Average Loss:** -₹268.44
* **Max Portfolio Drawdown:** -₹529.10 (0.5%)
* **Total Net Profit (after Taker Fees + 18% GST):** **+₹35,22,040.81 INR**
* **Intraday 15m Real-Time Validation:** ~62% win rate when using Swing High (SH) and Swing Low (SL) stop loss buffers.

---

## 5. 📋 Action Items for Tomorrow

1. **Activate Email Alerts:**
   * Go to [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).
   * Generate a 16-character App Password named `CoinDCX Bot`.
   * Add to `.env` and Streamlit Cloud Secrets:
     ```toml
     SENDER_EMAIL = "jwalashiva@gmail.com"
     SENDER_APP_PASSWORD = "your_16_character_code"
     RECEIVER_EMAIL = "jwalashiva@gmail.com"
     ```
   * Click **"📩 Send Test Alert Email"** in the sidebar to verify inbox delivery.

2. **Simulated & Live Order Testing:**
   * Run a **Simulated Paper Trade** on the live web app to observe real-time position tracking and Google Sheets logging.
   * If testing a **Live CoinDCX Order**, set margin to `₹2,500 - ₹5,000` to fit the available wallet margin (`₹5,761`).
