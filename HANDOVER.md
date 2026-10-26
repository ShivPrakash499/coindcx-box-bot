# ⚡ CoinDCX Box Theory Terminal — Session Handover & Memory
**Latest Update:** October 25, 2026 (00:30 IST)  
**Account:** Binni  
**Live URL:** [https://shiv-prakash-trade-assistant.streamlit.app](https://shiv-prakash-trade-assistant.streamlit.app)  
**GitHub Repository:** [ShivPrakash499/coindcx-box-bot](https://github.com/ShivPrakash499/coindcx-box-bot) (`main` branch)

---

## 1. 🚀 Current Deployment & Git Status
* **Active Commit on `main`:** **`b91253a`** (`fix: resolve KeyError direction on simulated paper trades and active position PnL`).
* **Preserved Work & Tools Branch:** **`backup-today-oct24`** (commit `ab8f195`).  
  *Contains: full interactive backtester, dynamic wallet capital sizing, `strategy_config.json`, `coindcx_auto_trader.py`, `ai_strategy_optimizer.py`, and multi-mode rotation tools.*
* **Local Terminal App:** Live and operational on `http://localhost:8501`.
* **Security Gate:** Protected with **Access PIN** (configured via `APP_PIN` in environment / secrets).
* **Live Wallet Verification:**
  * **Total Equity (INR):** `~₹28,790.90` (Cash + active margin).
  * **Live Order Guard:** Minimum order value enforced at **₹2,448 INR**.

---

## 1b. 🧠 Oct 25–26, 2026 — Modular Multi-Strategy, Daily 50 & 200 EMA Bias & Dual-Timeframe Engine Upgrade
* New [`strategies.py`](strategies.py) with `STRATEGY_REGISTRY`: **Box Theory Sweep** (`box_theory`) and **1-Candle 25% ATR Reversal** (`atr_reversal`).
* **Daily 50 EMA & 200 EMA Trend Bias Gate (Oct 26 Refinement):**
  * Computed on 1,000 daily candles (`limit=1000`) for exact TradingView/CoinDCX alignment while keeping `SH`/`SL` lookback strictly capped to 30 completed daily candles.
  * **SHORT Only (`BEARISH`):** `Daily Close < 50 EMA AND Daily Close < 200 EMA`
  * **LONG Only (`BULLISH`):** `Daily Close > 50 EMA AND Daily Close > 200 EMA`
  * **NEUTRAL (No Trade):** Price sits between the Daily 50 EMA and Daily 200 EMA.
* **Dual-Timeframe Confirmation Engine (15m Trigger → 5m Confirmation):**
  * **Box Theory Sweep:** 15m candle monitors liquidity sweep into $RH$/$RL$ OR Daily 50 EMA touch; switches to 5m timeframe for rejection confirmation (`close < RH/EMA50` & `< prev_close` for Short, `close > RL/EMA50` & `> prev_close` for Long) with tighter structural stop loss.
  * **1-Candle 25% ATR Reversal:** 15m candle monitors $\ge 25\%$ Daily ATR manipulation flush/spike aligned with Daily 50 & 200 EMA bias; switches to 5m timeframe for 1-candle reversal crossover (`close > prev_5m_red_high` for Long, `close < prev_5m_green_low` for Short).
* **Email Alert Hardening (`signal_monitor.py` & `coindcx_engine.py`):**
  * Removed untested `CONTINUATION` breakdown/breakout alerts from `detect_zone_signal`.
  * Added `_SCAN_LOCK` thread synchronization and per-pair 45m cooldown (`PAIR_LOCK|{pair}`) in `signal_monitor.py` to prevent simultaneous duplicate/conflicting alerts.
* `coindcx_engine.run_strategy_backtest(..., strategy_id=...)` delegates entries to the strategy; exit/fee engine unchanged.
* E-mail subject: `"{SYM} - {Strategy Name} - trade notification"`; Strategy + Trigger Reason in e-mail body and `Live_Trades` sheet.
* UI: strategy selector on Key Levels, strategy arming on Execution ("All Active Strategies (Auto-Detect Triggers)" / "<name> Only"), strategy + "Compare All Strategies Side-by-Side" on Backtest.
* Fixed: background monitor thread was started on every rerun (now `st.cache_resource`).
* Optional env `ENABLED_STRATEGIES` (comma-separated ids). Streamlit Secrets need `GMAIL_*` + `APP_WEB_URL`.

---

## 2. 📅 Session Log: October 24–25, 2026

### A. Strategy Backtesting & Quantitative Discoveries
Tested against 1 full year (365 days) of continuous 15-minute candles (~35,040 candles per instrument) across **SOL**, **ETH**, and **BTC** with ₹1,00,000 margin per trade @ 5x leverage:

#### 1. Core Logic Comparison (`b91253a` Pure Sweep vs. Complex Filters)
* **Finding:** The pure Box Theory sweep-rejection logic from `b91253a` (`low <= RL and close > RL` for Long; `high >= RH and close < RH` for Short) dramatically outperformed complex candle wick-ratio filters and 1H trend gates:
  * **TP1 Midpoint Mode (`b91253a`):** **1,202 trades**, **50.1% Win Rate**, **+₹5,60,730.24 Net Profit** (SOL: +₹3.59L, ETH: +₹2.40L).
  * Adding arbitrary wick-ratio filters (`lower_wick / range >= 0.15`) unnecessarily blocked clean institutional sweeps, reducing net profit by over ₹1,08,000.

#### 2. Target Mode Performance (Midpoint vs. Opposite Extremes)
| Strategy Target Mode | Total Trades | Win Rate (%) | Wins / Losses | Profit Factor | Total Fees (INR) | Portfolio Net Profit (INR) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **TP1 Midpoint** | 1,202 | **50.1%** | 602W / 600L | **1.31** | ₹7,08,312.17 | **+₹5,60,730.24** |
| **50/50 Split (Ratchet SL)** | 1,020 | **49.1%** | 501W / 519L | **1.26** | ₹6,01,160.90 | **+₹3,58,039.29** |
| **TP2 Full Rotation (Opposite Edge $RH$/$RL$)** | 673 | **30.6%** | 206W / 467L | **1.24** | **₹3,96,555.07** | **+₹4,67,283.99** *(All 3 coins profitable!)* |
| **Opposite Swing Extreme ($SH$/$SL$)** | 516 | **28.5%** | 147W / 369L | **1.21** | **₹3,04,052.86** | **+₹6,35,654.66** |

* **Key Takeaway on Opposite Extremes:**
  * Removing midpoint profit and targeting the opposite edge ($RH$/$RL$ or $SH$/$SL$) slashed total fee expense from **₹7.08 Lakhs down to ₹3.04 – ₹3.96 Lakhs** (saving ₹3.1 to ₹4.0 Lakhs in taker fees + GST).
  * In **TP2 Full Rotation**, **ALL THREE COINS WERE GREEN** (SOL: +₹4,47,080, ETH: +₹17,473, BTC: +₹2,730).
  * In **Opposite Swing Extreme**, portfolio net profit reached **+₹6,35,654.66 INR** (+635.7% ROI) due to asymmetric 3.5:1 to 5:1 Risk-to-Reward.

#### 3. Institutional Timezone Audit (Tokyo, London, New York & 24/7 Intraday)
Backtest ran across all 24 hours of every single day:
* **🌅 Tokyo / Asia Open (07:00 – 08:30 IST):** 76 Trades | 34.2% Win Rate | Net: -₹1,68,384.46
* **🏛️ London Open (13:00 – 14:30 IST):** 51 Trades | 31.4% Win Rate | Net: -₹1,07,961.62
* **⚡ New York Open (18:45 – 20:15 IST):** 158 Trades | 47.5% Win Rate | Net: -₹1,08,675.39
* **🌐 24/7 Intraday Cycle (Continuous Monitoring):** **917 Trades** | **52.9% Win Rate** | **+₹9,45,751.81 Net Profit** (Profit Factor: **1.52**)
* **Insight:** The opening 60–90 minutes of major financial centers feature high-momentum volatility expansions that often breach tight boundaries. The true alpha of Box Theory is generated continuously 24/7 across the broader Intraday cycle as price rotates back to daily equilibrium ($MID$).

---

### B. Infrastructure & Tools Developed (Stored in `backup-today-oct24`)
1. **Dynamic CoinDCX Futures Wallet Engine:**
   - Authenticated against `/exchange/v1/derivatives/futures/wallets`.
   - Rotational 1/3rd equity allocation per trade slot (`allocate_rotational_margin`), auto-scaling trade size from ₹10,000 (at ₹30,000 wallet) to ₹1,00,000 (at ₹3,00,000 wallet).
2. **Interactive Real-Time Backtester (Tab 4):**
   - Multi-batch paginated candle fetcher (`fetch_historical_candles_paginated`) pulling up to 35,000+ continuous candles with sub-second in-memory caching.
   - Dynamic parameter detection, Plotly cumulative equity curves, monthly financial audits, and CSV export.
3. **Automated Trading & Audit Modules:**
   - `coindcx_auto_trader.py`: 24/7 background rotational trading engine (paper/live).
   - `ai_strategy_optimizer.py`: Automated Day-15 and Day-30 audit script leveraging Gemini.
   - `sheets_logger.py`: Extended with `Live_Trades` and `Failed_Trade_Diagnostics` logging.

---

### C. Revert Action Completed
* To maintain production stability and adhere to the user's explicit preference, `main` was cleanly reverted to **`b91253a`**.
* All experimental 1H filters, breakout additions, and intermediate code were removed from `main`.
* All newly developed tools and backtest logic are safely archived and directly accessible in branch **`backup-today-oct24`**.

---

## 3. 🛠️ Critical Fixes & Bug Resolutions (Historical Summary)

| Issue | Root Cause | Solution Applied |
| :--- | :--- | :--- |
| **Setup Levels Not Refreshing** | Streamlit number input widget state locking to initial values | Replaced with setup-specific widget keys (`custom_entry_{pair}_{setup_tag}`) and auto-sync logic on setup switch; added Reset button. |
| **Mark Price / PnL Stale** | CoinDCX futures position mark price snapshot was frozen/static | Linked real-time mark price to live Binance ticker & CoinDCX live ticker; live PnL and ROE recalculate on every tick. |
| **`Connection error: None` on Orders** | Python `requests` response object evaluated as falsy (`if not res:`) when CoinDCX returned 400/401 HTTP codes | Fixed to `if res is None:` across `coindcx_engine.py` and added clean JSON error message parsing. |
| **Paper Trading `KeyError: 'direction'`** | Order record dictionary saved key as `"signal"` while PnL tracker expected `"direction"` | Standardized `order_record` to include both `"signal"` and `"direction"`; updated components defensively. |
| **CoinDCX Order Placement 400 Bad Request** | CoinDCX Futures strictly enforces instrument step sizes (e.g. Quantity divisible by 0.01 for SOL, 0.001 for ETH/BTC). | Added `format_order_quantity` across pairs to quantize lot sizes strictly to exchange rules. *(Archived on `backup-today-oct24`)* |
| **Order Error Disappearing in 1 Second** | Trade Execution Station had `@st.fragment(run_every=5)`, resetting button click states. | Isolated only wallet metric cards into 5s live fragment; trade inputs and messages never reset. *(Archived on `backup-today-oct24`)* |
| **Public Deployment Misuse Risk** | Public Streamlit URLs are accessible to anyone | Added Institutional Security Gate directly into `app.py` with PIN authentication. |

---

## 4. 📋 Action Items & Next Steps
1. **Branch Switching Reference:**
   * To inspect or restore the interactive backtester or rotational auto-trader:
     ```bash
     git checkout backup-today-oct24
     ```
   * To return to the clean production baseline:
     ```bash
     git checkout main
     ```
2. **Live Test Order Execution:**
   * Available margin is currently `~₹17,541`. When placing test orders, set margin to `₹2,500 – ₹5,000` to satisfy the ₹2,448 exchange minimum while staying well within available balance.
3. **Email Notification Check:**
   * Verify SMTP credentials in `.env` or Streamlit Cloud Secrets and test via sidebar **"📩 Send Test Alert Email"**.
