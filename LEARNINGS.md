# CoinDCX Box Bot — Deployment & Regression Learnings (`GEMINI.md` / `LEARNINGS.md`)

> **CRITICAL RULE FOR ALL AGENTS**: Read and obey every rule in this file before modifying [`app.py`](file:///C:/coindcx_box_bot/app.py), [`coindcx_engine.py`](file:///C:/coindcx_box_bot/coindcx_engine.py), [`signal_monitor.py`](file:///C:/coindcx_box_bot/signal_monitor.py), [`strategies.py`](file:///C:/coindcx_box_bot/strategies.py), or [`requirements.txt`](file:///C:/coindcx_box_bot/requirements.txt), and before pushing to `staging` or `main`.

---

## 1. Never Touch `requirements.txt` Unnecessarily (Prevents Container Restarts & Static JS Chunk Failures)
- **What Happened**: Adding or changing lines in [`requirements.txt`](file:///C:/coindcx_box_bot/requirements.txt) caused Streamlit Cloud (`uv`) to reinstall packages (`pip`, `certifi`, `pyarrow`) and restart the Uvicorn/Tornado server mid-flight while the browser was fetching dynamically imported UI chunks (`Selectbox.*.js`, `Metric.*.js`, `TextInput.*.js`). It also wiped the in-memory pinned Cloud NAT session (`_PERSIST["session"]`).
- **Mandatory Rule**:
  - **NEVER** modify [`requirements.txt`](file:///C:/coindcx_box_bot/requirements.txt) unless a genuinely new third-party library is required and requested by the user.

---

## 2. Never Spawn `ThreadPoolExecutor` Inside `_send_coindcx_signed_request()` (Prevents GIL & Socket Starvation)
- **What Happened**: Spawning `ThreadPoolExecutor(max_workers=10)` with 20 parallel sockets inside [`_send_coindcx_signed_request()`](file:///C:/coindcx_box_bot/coindcx_engine.py) caused multiple concurrent callers (wallet refresh, positions refresh, open orders, background daemon) to open 80–120 TLS sockets simultaneously, starving Streamlit's single-process Tornado server and causing `TypeError: Failed to fetch dynamically imported module`.
- **However, Sequential Close-Before-Open Loops Also Fail on Cloud NAT**:
  - Doing `for _ in range(5): cand = requests.Session(); ...; cand.close()` sequentially causes Google Cloud NAT to recycle the exact same non-allowlisted NAT IP instead of rotating across the NAT pool to reach the allowlisted IP (`34.83.176.217`), resulting in `0` visible positions after a container restart.
- **Mandatory Rule**:
  - Always use the single-flight [`_pin_coindcx_nat_session()`](file:///C:/coindcx_box_bot/coindcx_engine.py) guarded by `_NAT_PIN_LOCK.acquire(blocking=False)` so at most **1** NAT pin scan can ever run across the entire process.
  - Inside `_pin_coindcx_nat_session()`, keep candidate `requests.Session()` sockets open simultaneously in `cand_pool = []` (with a `0.03s` `time.sleep` between probes to yield the GIL) so Google Cloud NAT is forced to allocate distinct egress IPs across its pool until `34.83.176.217` responds `200 OK`, then close all unused sockets in `finally:`.

---

## 3. Streamlit Hot-Reload vs. Background Threads & Stale Modules (`sys.modules`)
- **What Happened**: When pushing code to `staging` or `main` without a container restart, Streamlit Cloud only re-executes [`app.py`](file:///C:/coindcx_box_bot/app.py) when a browser tab reruns. Meanwhile:
  1. Cached modules in `sys.modules` (`coindcx_engine`, `strategies`, `signal_monitor`) are **not** automatically reloaded by Python `import` statements.
  2. Already-running background daemon threads (`CryptoTradeAssistantDaemon`) keep executing the old `while True:` loop and old function objects in memory.
- **Mandatory Rule**:
  - Keep the top-of-file `importlib.reload(coindcx_engine)`, `importlib.reload(strategies)`, and `importlib.reload(signal_monitor)` in [`app.py`](file:///C:/coindcx_box_bot/app.py), AND keep [`_upgrade_all_in_memory_functions_and_disarm()`](file:///C:/coindcx_box_bot/coindcx_engine.py) at the bottom of [`coindcx_engine.py`](file:///C:/coindcx_box_bot/coindcx_engine.py).
  - Whenever changing background daemon logic or safety guards, increment `_REQUIRED_DAEMON_VERSION` in both [`coindcx_engine.py`](file:///C:/coindcx_box_bot/coindcx_engine.py) and [`app.py`](file:///C:/coindcx_box_bot/app.py).
  - **NEVER** raise `SystemExit` inside `_check_and_kill_obsolete_daemon()` (if called on a Streamlit thread, `SystemExit` kills Uvicorn and logs `Unclean server shutdown : 8501`). Always raise the custom `_ObsoleteDaemonStop(BaseException)` only when `threading.current_thread().name` is an older `CryptoTradeAssistantDaemon`.

---

## 4. Prevent Open Browser Tabs from Overwriting Config State on Rerun (`st.sidebar.toggle`)
- **What Happened**: An already-open browser tab on `main` had `st.session_state["sidebar_autotrade_toggle"] = True`. Even after `autotrade_config.json` was disarmed (`"enabled": False`) on disk, `st.sidebar.toggle(..., value=False, key="sidebar_autotrade_toggle")` returned the tab's stale `st.session_state` value (`True`), and `if autotrade_on != _auto_cfg["enabled"]:` immediately overwrote `autotrade_config.json` back to `"enabled": True`, causing unwanted `RENDER` trades to keep firing.
- **Mandatory Rule**:
  - Never auto-save `enabled` inside the main render body by comparing `autotrade_on != _auto_cfg["enabled"]`.
  - Always mutate `"enabled"` **only** inside the explicit `on_change=_on_sidebar_autotrade_toggle_change` widget callback (which only fires when the user physically clicks the toggle), and sync `st.session_state["sidebar_autotrade_toggle"]` when the disarm version increments.

---

## 5. Never Use `st.markdown(..., unsafe_allow_html=True)` for Large `<style>` or `<div>` Blocks
- **What Happened**: During transient chunk-loading retries or when indentation/newlines were present inside `st.markdown("""<style>...""", unsafe_allow_html=True)`, CommonMark parsed parts of the CSS/HTML as a code block and dumped raw `<style>/* Global anti-horizontal-scroll...` text onto the screen.
- **Mandatory Rule**:
  - Always use `st.html("""<style>...</style>""")` for CSS stylesheets and multi-line HTML cards (including the PIN gate card and main responsive stylesheet).

---

## 6. Prevent Email Alert Spam Across Concurrent Threads (`signal_monitor.py`)
- **What Happened**: When an old daemon thread (`_SCHEMA_VERSION = 2`) and a new daemon thread (`_SCHEMA_VERSION = 3`) ran concurrently during a branch merge, `_load()` in [`signal_monitor.py`](file:///C:/coindcx_box_bot/signal_monitor.py) wiped `alert_state.json` to `{}` every time `_schema_version != _SCHEMA_VERSION`, erasing cooldown timestamps every 45 seconds and sending 50+ duplicate emails.
- **Mandatory Rule**:
  - `_load()` in [`signal_monitor.py`](file:///C:/coindcx_box_bot/signal_monitor.py) must **NEVER** wipe existing cooldown entries when `_schema_version` changes — it must preserve all existing pair/direction cooldown timestamps, merge with `sys.__dict__["_signal_monitor_state_mem"]`, and upgrade `_schema_version` using `max()`.

---

## 7. Strict Trading & Execution Invariants (Never Regress)
1. **1-Crypto-at-a-Time Live Exchange Guard**:
   - Before placing any AutoTrade entry in [`execute_autotrade_two_entry_signal()`](file:///C:/coindcx_box_bot/coindcx_engine.py), always check both the local lock AND live exchange positions via `_fetch_coindcx_active_positions_sync(return_none_on_error=True)`. If the live API call returns `None` (transient error/401) or returns any open position on another pair, **fail closed** and block the new trade.
2. **Daily 50 & 200 EMA Bias Guard (Locked to Completed Daily Candle)**:
   - [`calculate_daily_box_levels()`](file:///C:/coindcx_box_bot/coindcx_engine.py) must compute `EMA50`, `EMA200`, `daily_close`, and `trend_bias` strictly from `completed_df = df.iloc[:-1]` (completed daily candles prior to today), so intraday wicks never flip Daily Bias mid-day.
   - `BEARISH` -> `SHORT` only (`LONG` strictly blocked).
   - `BULLISH` -> `LONG` only (`SHORT` strictly blocked).
   - `NEUTRAL` / `RANGE` -> Both confirmed Buy-zone (`RL–SL`) and Sell-zone (`RH–SH`) box setups allowed.
3. **Zero Recursion Between Wallet Fetch and `save_autotrade_config()`**:
   - `_fetch_coindcx_futures_balance_sync()` must populate `_WALLET_BALANCE_CACHE["data"]` **before** calling `save_autotrade_config()`, and `get_autotrade_config()` / `save_autotrade_config()` must read `_get_saved_wallet_balance_default()` instead of calling `fetch_coindcx_futures_balance()`.

---

## 8. Never Store Any Secret in Code — Always Read Strictly From Streamlit Server (`st.secrets`)
- **Mandatory Rule**:
  - **NEVER** hardcode or store any API key, API secret, Gmail password, or Google Service Account credential in source code (neither plaintext nor base64/encoded fallback).
  - Always read credentials dynamically from the Streamlit Server (`st.secrets`, synced into `os.environ` at the top of [`app.py`](file:///C:/coindcx_box_bot/app.py) for background threads) or local untracked `.env` / `credentials.json`.

---

## 9. Mandatory Pre-Push Verification Gate (`test_smoke.py`)
- Before pushing any commit to `staging` or merging to `main`, always run:
  ```powershell
  C:\coindcx_box_bot\.venv\Scripts\python.exe C:\coindcx_box_bot\test_smoke.py
  ```
- All checks in [`test_smoke.py`](file:///C:/coindcx_box_bot/test_smoke.py) must pass with `0` errors.
