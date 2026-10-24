# ⚡ CoinDCX Box Theory Terminal — Session Handover & Memory
**Date:** October 24, 2026  
**Account:** Binni (`38df78ae-38f0-468a-86f2-047ff6113a7f`)  
**Live URL:** [https://shiv-prakash-crypto-robot.streamlit.app](https://shiv-prakash-crypto-robot.streamlit.app)  
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
| **CoinDCX Order Placement 400 Bad Request** | CoinDCX Futures strictly enforces instrument step sizes (e.g. `Quantity should be divisible by 0.01` for SOL, `0.001` for ETH/BTC). Code previously rounded all quantities to arbitrary 4 decimals. | Added `FUTURES_PAIR_SPECS` and `format_order_quantity` across all 30 futures pairs to automatically quantize quantities strictly to exchange lot size rules before submission. |
| **Order Error Disappearing in 1 Second** | The Trade Execution Station in Tab 1 had `@st.fragment(run_every=5)`, which refreshed all inputs and cleared `st.button` click state every 5 seconds. | Removed `run_every=5` from the execution station. Isolated only the 4 wallet metric cards into a self-contained 5s live fragment so trade inputs and messages never reset. |
| **Order Replacement Error Disappearing** | In `update_coindcx_position_tpsl` (TP/SL trigger adjustment), `st.rerun()` was called unconditionally right after `st.error(...)`, erasing the error message instantly. | Only trigger `st.rerun()` on successful updates (`ok=True`). On errors, maintain error on screen and log to session state. |
| **Order Leverage Mismatch (422 Error)** | When an active position already exists for a coin on CoinDCX (e.g. SOL 10x), CoinDCX rejects orders with a different leverage (`Order leverage must be equal to position leverage`). | Added automatic position leverage detection in both `place_coindcx_futures_order` and the UI slider, ensuring orders always match active position leverage. |
| **App Refreshing Every 30s** | Sidebar `chart_refresh_rate` defaulted to `index=2` ("Every 30s"). | Changed default to `index=0` ("Manual Only (Zero Interruption - Recommended)") and added a dedicated `🔄 Refresh Terminal & Market Data` button. |
| **Maintain Error Log on Streamlit** | User requested persistent error logs on Streamlit. | Implemented a persistent **"📋 CoinDCX Execution & API Error Console"** in `st.session_state.api_error_logs` (with expandable raw JSON technical payloads and Clear Logs button), plus a sticky dismissible alert banner. |

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
   - Added `FUTURES_PAIR_SPECS` and `format_order_quantity` for all 30 pairs.
   - Updated `place_coindcx_futures_order` with quantity step size formatting, pre-flight ₹2,448 INR value check, position leverage auto-alignment, millisecond timestamps (`int(round(time.time() * 1000))`), and structured JSON error reporting.
   - Updated `calculate_trade_setup_details` and `evaluate_tri_session_signal` to use `format_order_quantity`.
   - Updated `update_coindcx_position_tpsl` and `exit_coindcx_position` with clean JSON error parsing.
2. [app.py](file:///c:/coindcx_box_bot/app.py):
   - Initialized `api_error_logs` and `last_order_status` in `st.session_state`.
   - Changed auto-refresh default to "Manual Only" with explicit refresh button.
   - Removed `run_every=5` from `render_trade_execution_fragment`, isolating wallet metrics in `render_wallet_live_strip`.
   - Added sticky Notification Banner and dedicated **CoinDCX Execution & API Error Console**.
   - Auto-locked leverage slider when an active position exists on that pair.
   - Quantized all user-customized order quantities with `format_order_quantity`.

