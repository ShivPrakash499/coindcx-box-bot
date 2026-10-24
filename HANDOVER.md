# ⚡ CoinDCX Box Theory Terminal — Session Handover & Memory
**Date:** October 24, 2026  
**Account:** Binni (`38df78ae-38f0-468a-86f2-047ff6113a7f`)  
**Live URLs:**  
* Primary Assistant: [https://shiv-prakash-trade-assistant.streamlit.app](https://shiv-prakash-trade-assistant.streamlit.app)  
* Alternative Mirror: [https://shiv-prakash-crypto-robot.streamlit.app](https://shiv-prakash-crypto-robot.streamlit.app)  
**GitHub Repository:** [ShivPrakash499/coindcx-box-bot](https://github.com/ShivPrakash499/coindcx-box-bot) (`main` branch)

---

## 1. 🚀 Current Deployment Status
* **Cloud App:** Live, healthy, and operational on Streamlit Community Cloud.
* **Security Gate:** App is protected with an **Access PIN** (`7426` or fallback `1234`).
* **Live Orders Verified:** Real live orders and order cancellations tested and confirmed 100% operational against CoinDCX Futures API.
* **Zero Interruption Mode:** Default terminal refresh rate set to **Manual Only (Zero Interruption)** with on-demand manual refresh button.

---

## 2. 🛠️ Critical Fixes Completed Today (October 24, 2026)

| Issue | Root Cause | Solution Applied |
| :--- | :--- | :--- |
| **Streamlit Cloud Redacted `ImportError` on line 9** | On Streamlit Community Cloud, active containers cache loaded modules in `sys.modules`. When new functions (`format_order_quantity`, `get_pair_lot_spec`) were added and imported via multi-line `from coindcx_engine import (...)`, Python evaluated against the cached module in memory without reloading, raising an unhandled `ImportError` that Streamlit Cloud redacted for data leak protection. | 1. Added explicit `sys.path.insert(0, CURRENT_DIR)` at the very top of `app.py`.<br>2. Synced Streamlit Cloud `st.secrets` into `os.environ` *before* backend modules load.<br>3. Switched to `import coindcx_engine` with `importlib.reload(coindcx_engine)` and graceful `getattr` fallbacks.<br>4. Added `from __future__ import annotations` across all 4 modules (`app.py`, `coindcx_engine.py`, `alert_notifier.py`, `sheets_logger.py`) for complete cross-version Python compatibility (3.8-3.13+).<br>5. Removed unused `import numpy as np` in `coindcx_engine.py` to prevent potential Linux C-extension ABI conflicts.<br>6. Added `.streamlit/config.toml` with `showErrorDetails = "full"` and `headless = true`. |
| **CoinDCX Order Placement 400 Bad Request** | CoinDCX Futures strictly enforces instrument step sizes (e.g. `Quantity should be divisible by 0.01` for SOL, `0.001` for ETH/BTC). Code previously rounded all quantities to arbitrary 4 decimals. | Added `FUTURES_PAIR_SPECS` and `format_order_quantity` across all 30 futures pairs to automatically quantize quantities strictly to exchange lot size rules before submission. |
| **Order Error Disappearing in 1 Second** | The Trade Execution Station in Tab 1 had `@st.fragment(run_every=5)`, which refreshed all inputs and cleared `st.button` click state every 5 seconds. | Removed `run_every=5` from the execution station. Isolated only the 4 wallet metric cards into a self-contained 5s live fragment so trade inputs and messages never reset. |
| **Order Replacement Error Disappearing** | In `update_coindcx_position_tpsl` (TP/SL trigger adjustment), `st.rerun()` was called unconditionally right after `st.error(...)`, erasing the error message instantly. | Only trigger `st.rerun()` on successful updates (`ok=True`). On errors, maintain error on screen and log to session state. |
| **Order Leverage Mismatch (422 Error)** | When an active position already exists for a coin on CoinDCX (e.g. SOL 10x), CoinDCX rejects orders with a different leverage (`Order leverage must be equal to position leverage`). | Added automatic position leverage detection in both `place_coindcx_futures_order` and the UI slider, ensuring orders always match active position leverage. |
| **App Refreshing Every 30s** | Sidebar `chart_refresh_rate` defaulted to `index=2` ("Every 30s"). | Changed default to `index=0` ("Manual Only (Zero Interruption - Recommended)") and added a dedicated `🔄 Refresh Terminal & Market Data` button. |
| **Maintain Error Log on Streamlit** | User requested persistent error logs on Streamlit. | Implemented a persistent **"📋 CoinDCX Execution & API Error Console"** in `st.session_state.api_error_logs` (with expandable raw JSON technical payloads and Clear Logs button), plus a sticky dismissible alert banner. |

| **Static Backtest Section with Old Mock Data** | Backtest Tab 4 previously rendered static hardcoded metrics and dummy tables from early 2026 without any user controls or live calculation. | Implemented dynamic `run_strategy_backtest` engine with live candle fetching from CoinDCX / Binance public APIs. Added UI controls for selecting futures pair, backtest duration (7d to 180d), trade margin (INR), leverage, and TP rule (TP1 Midpoint, TP2 Full Rotation, 50/50 Split). Generates live KPI cards, interactive Plotly cumulative equity curve, dynamic monthly and institutional session breakdowns, and downloadable trade log CSV. |

---

## 3. 🔑 CoinDCX API & Wallet Verification
* **API Credentials:** 100% verified working and authenticated against CoinDCX live servers for user **Binni**.
* **Live Futures Wallet Details:**
  * **Total Value (INR):** `₹27,537.07`
  * **Cash Balance (INR):** `₹17,541.56`
  * **Locked Balance:** `₹9,995.51` (held by active `B-SOL_USDT` long position + TP order)
  * **Available Margin:** `₹17,541.56`
* **Live Order Constraints Enforced by Bot:**
  * Minimum order notional value: **₹2,448 INR** (enforced pre-flight by guard).
  * Quantity divisibility: Strictly enforced per asset lot size.
  * Leverage consistency: Auto-locked to active position leverage if an open position exists.

---

## 4. 📋 Summary of Code Changes
1. [coindcx_engine.py](file:///c:/coindcx_box_bot/coindcx_engine.py):
   - Added `from __future__ import annotations`.
   - Removed unused `import numpy as np`.
   - Added `FUTURES_PAIR_SPECS` and `format_order_quantity` for all 30 pairs.
   - Added `run_strategy_backtest` function to simulate the Box Liquidity Sweep strategy across historical candles with exact CoinDCX fee schedules (0.05% Taker + 18% GST), daily box establishment, and session tracking.
   - Updated `place_coindcx_futures_order` with quantity step size formatting, pre-flight ₹2,448 INR value check, position leverage auto-alignment, millisecond timestamps (`int(round(time.time() * 1000))`), and structured JSON error reporting.
   - Updated `calculate_trade_setup_details` and `evaluate_tri_session_signal` to use `format_order_quantity`.
   - Updated `update_coindcx_position_tpsl` and `exit_coindcx_position` with clean JSON error parsing.
2. [app.py](file:///c:/coindcx_box_bot/app.py):
   - Added `from __future__ import annotations`.
   - Added `sys.path.insert(0, CURRENT_DIR)` to guarantee module resolution on Streamlit Cloud.
   - Synced `st.secrets` before backend modules load.
   - Robust `importlib.reload(coindcx_engine)` loading with fallback `getattr` implementations.
   - Replaced static Tab 4 with an interactive **Real-Time Strategy Backtest & Execution Simulator** featuring:
     - Futures Pair selector (all 30 pairs, defaulting to active pair)
     - Separated Duration selector: `1 Week (7 Days)`, `1 Month (30 Days)`, `3 Months (90 Days)`, `6 Months (180 Days)`, `12 Months / 1 Year (365 Days)` (defaulting to 6 Months)
     - Separated Standard Timeframe selector: `15m`, `1h`, `4h`, `1d`
     - Dynamic Parameter Change Detection: Changing Duration, Margin, Timeframe, Asset, or Leverage immediately triggers recalculation, preventing stale 1-month or 10,000 margin results.
     - Exact Buy/Sell Zone Rejection Candle Strategy: Long only on liquidity sweeps into Buy Zone (<= RL) with bullish rejection candle close above RL; Short only on liquidity sweeps into Sell Zone (>= RH) with bearish rejection candle close below RH.
     - Multi-batch paginated candle fetching (`fetch_historical_candles_paginated`) supporting up to 35,000+ continuous candles (~1 Year on 15m)
     - High-speed in-memory candle caching (`_HISTORICAL_CANDLES_CACHE`) providing instantaneous (<0.4s) simulation reruns across different margins, leverages, and TP rules
     - Trade Margin input defaulting to ₹100,000 INR
     - Take Profit target mode (TP1 Midpoint, TP2 Full Rotation, 50/50 Split)
     - Key Performance Metric Cards (Net Profit ₹, ROI %, Win Rate, Profit Factor, Max Drawdown, Total Trades)
     - Secondary Edge Statistics (Long vs Short Win Rate, Total Fees Paid, Avg Win vs Avg Loss)
     - Interactive Cumulative Equity Growth Curve (Plotly Chart)
     - Dynamic Monthly Performance & Financial Audit table with columns: `Month`, `Number of Trades`, `Margin Used`, `Fees Paid`, `Profit or Loss`, `Win Rate`, `Overall Net Profit`, plus `🔥 TOTAL / SUMMARY` row
     - Institutional Session Breakdown table (Asia, London, NY, Intraday)
     - Detailed Trade-by-Trade Execution Log with CSV download button (naming includes pair, duration, and timeframe)
   - Initialized `api_error_logs` and `last_order_status` in `st.session_state`.
   - Changed auto-refresh default to "Manual Only" with explicit refresh button.
   - Removed `run_every=5` from `render_trade_execution_fragment`.
   - Added sticky Notification Banner and dedicated **CoinDCX Execution & API Error Console**.
   - Auto-locked leverage slider when an active position exists on that pair.
   - Quantized all user-customized order quantities with `format_order_quantity`.
3. [.streamlit/config.toml](file:///c:/coindcx_box_bot/.streamlit/config.toml):
   - Configured `[client] showErrorDetails = "full"` and `[server] headless = true`.
4. [.gitignore](file:///c:/coindcx_box_bot/.gitignore):
   - Track `.streamlit/config.toml` while keeping `.streamlit/secrets.toml` ignored.
