from __future__ import annotations
import os
import sys
import importlib
import traceback

# Guarantee repository root directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

import streamlit as st

# Sync Streamlit Cloud secrets into os.environ BEFORE backend modules initialize
try:
    if hasattr(st, "secrets"):
        for _sec_k, _sec_v in st.secrets.items():
            if isinstance(_sec_v, (str, int, float, bool)):
                os.environ[str(_sec_k)] = str(_sec_v)
except Exception:
    pass

import pandas as pd
import pytz
from datetime import datetime
import plotly.graph_objects as go
from dotenv import load_dotenv

load_dotenv()

# Safe, hot-reloadable module imports with graceful fallbacks
try:
    import coindcx_engine
    try:
        importlib.reload(coindcx_engine)
    except Exception:
        pass

    GLOBAL_FUTURES_PAIRS = coindcx_engine.GLOBAL_FUTURES_PAIRS
    calculate_daily_box_levels = coindcx_engine.calculate_daily_box_levels
    evaluate_715_pm_signal = coindcx_engine.evaluate_715_pm_signal
    evaluate_tri_session_signal = coindcx_engine.evaluate_tri_session_signal
    get_current_session_info = coindcx_engine.get_current_session_info
    fetch_coindcx_candles = coindcx_engine.fetch_coindcx_candles
    fetch_live_ticker = coindcx_engine.fetch_live_ticker
    calculate_trade_setup_details = coindcx_engine.calculate_trade_setup_details
    fetch_futures_funding_rate = coindcx_engine.fetch_futures_funding_rate
    fetch_coindcx_futures_balance = coindcx_engine.fetch_coindcx_futures_balance
    fetch_coindcx_active_positions = coindcx_engine.fetch_coindcx_active_positions
    fetch_coindcx_open_orders = coindcx_engine.fetch_coindcx_open_orders
    exit_coindcx_position = coindcx_engine.exit_coindcx_position
    exit_all_coindcx_positions = coindcx_engine.exit_all_coindcx_positions
    update_coindcx_position_tpsl = coindcx_engine.update_coindcx_position_tpsl
    place_coindcx_futures_order = coindcx_engine.place_coindcx_futures_order
    calculate_trade_costs_and_safe_tp = coindcx_engine.calculate_trade_costs_and_safe_tp
    round_asset_price = coindcx_engine.round_asset_price
    get_coindcx_live_usdt_inr_rate = coindcx_engine.get_coindcx_live_usdt_inr_rate
    format_order_quantity = getattr(coindcx_engine, "format_order_quantity", lambda pair, qty: round(float(qty), 4))
    get_pair_lot_spec = getattr(coindcx_engine, "get_pair_lot_spec", lambda pair: {})
    run_strategy_backtest = getattr(coindcx_engine, "run_strategy_backtest", None)
    compute_market_bias = coindcx_engine.compute_market_bias
    get_rotational_margin_inr = coindcx_engine.get_rotational_margin_inr
except Exception as _mod_err:
    st.error(f"❌ Backend Engine Initialization Error: {_mod_err}")
    st.code(traceback.format_exc())
    st.stop()

try:
    import strategies as strategy_registry
    try:
        importlib.reload(strategy_registry)
    except Exception:
        pass
except Exception as _strat_err:
    st.error(f"❌ Strategy Registry Initialization Error: {_strat_err}")
    st.code(traceback.format_exc())
    st.stop()

try:
    import sheets_logger
    try:
        importlib.reload(sheets_logger)
    except Exception:
        pass
    log_trade_to_google_sheet = sheets_logger.log_trade_to_google_sheet
except Exception as _sheet_err:
    def log_trade_to_google_sheet(*args, **kwargs):
        return (False, f"Google Sheets integration offline: {_sheet_err}") if kwargs.get("return_details") else False

try:
    import alert_notifier
    try:
        importlib.reload(alert_notifier)
    except Exception:
        pass
    send_sweep_alert = alert_notifier.send_sweep_alert
    send_email_notification = alert_notifier.send_email_notification
except Exception as _alert_err:
    def send_sweep_alert(*args, **kwargs):
        pass
    def send_email_notification(*args, **kwargs):
        return False, f"Email notifier offline: {_alert_err}"

try:
    import email_notifier
    import signal_monitor
    from email_notifier import send_trade_email, send_test_trade_email, get_email_config
except Exception as _em_err:
    _EMAIL_ERR = str(_em_err)
    email_notifier = signal_monitor = None
    def send_trade_email(*args, **kwargs):
        return False, f"Email module offline: {_EMAIL_ERR}"
    def send_test_trade_email(*args, **kwargs):
        return False, f"Email module offline: {_EMAIL_ERR}"
    def get_email_config():
        return {"sender": "", "receiver": "", "configured": False}

try:
    from sheets_logger import log_trade_closed, log_failed_trade_diagnostic
except Exception:
    def log_trade_closed(*args, **kwargs):
        return False
    def log_failed_trade_diagnostic(*args, **kwargs):
        return False

st.set_page_config(
    page_title="Crypto Trade Assistant",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ----------------- SECURITY & AUTHENTICATION GATE -----------------
def get_security_pin():
    try:
        if hasattr(st, "secrets") and "APP_PIN" in st.secrets:
            return str(st.secrets["APP_PIN"]).strip()
    except Exception:
        pass
    return os.getenv("APP_PIN", "1234").strip()

def check_authentication():
    if st.session_state.get("authenticated", False):
        return True

    required_pin = get_security_pin()

    st.markdown(
        """
        <div style="max-width: 440px; margin: 60px auto 20px auto; padding: 32px; background: #ffffff; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.08); text-align: center; border: 1px solid #e2e8f0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <div style="font-size: 46px; margin-bottom: 10px;">🔐</div>
            <h2 style="margin: 0; color: #0f172a; font-weight: 800; font-size: 24px; letter-spacing: -0.5px;">Crypto Trade Assistant</h2>
            <div style="display: inline-block; background: #eff6ff; color: #2563eb; font-size: 11px; font-weight: 700; padding: 4px 12px; border-radius: 20px; margin-top: 8px; text-transform: uppercase; letter-spacing: 0.5px;">Institutional Security Gate</div>
            <p style="color: #64748b; font-size: 13px; margin-top: 12px; margin-bottom: 0px; line-height: 1.5;">Enter your secret Access PIN to unlock live balances, analytics, and execution stations.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    _, col_center, _ = st.columns([1, 1.3, 1])
    with col_center:
        with st.form("pin_security_form", clear_on_submit=False):
            entered_pin = st.text_input(
                "Access PIN",
                type="password",
                placeholder="Enter PIN (Default: 1234)",
                help="Configure your personal PIN via APP_PIN in .env or Streamlit Secrets"
            )
            unlock_clicked = st.form_submit_button("🔓 Unlock Assistant", use_container_width=True)
            if unlock_clicked:
                if entered_pin.strip() == required_pin:
                    st.session_state.authenticated = True
                    st.success("✅ Access Granted! Opening Assistant...")
                    st.rerun()
                else:
                    st.error("❌ Incorrect PIN. Access Denied.")

        st.markdown(
            "<p style='text-align: center; color: #94a3b8; font-size: 11px; margin-top: 16px;'>🔒 Private Session • All live API operations gated behind authentication</p>",
            unsafe_allow_html=True
        )

    st.stop()

check_authentication()

IST = pytz.timezone('Asia/Kolkata')

# ----------------- 24/7 BACKGROUND SIGNAL MONITOR DAEMON -----------------
import threading
import time

@st.cache_resource
def _ensure_background_monitor():
    """Starts the 24/7 background monitor daemon exactly once per Streamlit server process.
    Scans every registered strategy (or ENABLED_STRATEGIES) on the default watchlist."""
    def _monitor_worker():
        while True:
            try:
                if signal_monitor:
                    rot = coindcx_engine.get_rotational_margin_inr()
                    m_inr = float(rot.get("margin_inr", 100000.0))
                    lev = int(os.getenv("LEVERAGE", 5))
                    u_inr = float(coindcx_engine.get_coindcx_live_usdt_inr_rate())
                    signal_monitor.scan_and_alert(
                        pairs=["B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT"],
                        margin_inr=m_inr,
                        leverage=lev,
                        usd_inr=u_inr,
                        send=True
                    )
            except Exception as e:
                print(f"[Crypto Trade Assistant Background Monitor Error]: {e}")
            time.sleep(60)

    th = threading.Thread(target=_monitor_worker, daemon=True, name="CryptoTradeAssistantDaemon")
    th.start()
    return True

_ensure_background_monitor()

# ----------------- SESSION STATE & QUERY PARAMS INITIALIZATION -----------------
if "executed_trades" not in st.session_state:
    st.session_state.executed_trades = []

if "active_position" not in st.session_state:
    st.session_state.active_position = None

if "paper_pending_orders" not in st.session_state:
    st.session_state.paper_pending_orders = []

if "realized_pnl_inr" not in st.session_state:
    st.session_state.realized_pnl_inr = 0.0

if "favorite_pairs" not in st.session_state:
    st.session_state.favorite_pairs = ["B-ETH_USDT", "B-BTC_USDT", "B-SOL_USDT", "B-XRP_USDT", "B-DOGE_USDT"]

if "selected_pair" not in st.session_state:
    st.session_state.selected_pair = "B-ETH_USDT"

if "chart_timeframe" not in st.session_state:
    st.session_state.chart_timeframe = "15m"

if "api_error_logs" not in st.session_state:
    st.session_state.api_error_logs = []

if "last_order_status" not in st.session_state:
    st.session_state.last_order_status = None

# Process URL query parameters (e.g. from trade alert email action button)
_qp = st.query_params
_url_pair = _qp.get("pair")
if _url_pair and _url_pair in GLOBAL_FUTURES_PAIRS:
    st.session_state.selected_pair = _url_pair

_url_tab = _qp.get("tab", "").lower()
is_execution_link = _url_tab in ("execute", "execution", "trade")

# Apply an e-mail action link once per distinct link (query params persist across reruns)
_url_sig = str(sorted(_qp.to_dict().items())) if is_execution_link else ""
if is_execution_link and st.session_state.get("_url_applied") != _url_sig:
    st.session_state["_url_applied"] = _url_sig
    _p = st.session_state.selected_pair
    if "margin" in _qp:
        try: st.session_state[f"exec_margin_inr_{_p}"] = int(float(_qp["margin"]))
        except Exception: pass
    if "lev" in _qp:
        try: st.session_state[f"exec_leverage_{_p}"] = int(_qp["lev"])
        except Exception: pass
    _url_sid = _qp.get("strategy", strategy_registry.DEFAULT_STRATEGY_ID)
    if _url_sid not in strategy_registry.STRATEGY_REGISTRY:
        _url_sid = strategy_registry.DEFAULT_STRATEGY_ID
    st.session_state["exec_strategy_mode"] = f"{strategy_registry.get_strategy(_url_sid).name} Only"
    try:
        if "entry" in _qp and "sl" in _qp:
            _dir = str(_qp.get("direction", "LONG")).upper()
            st.session_state["url_prefill"] = {
                "pair": _p, "strategy_id": _url_sid, "direction": "BUY" if _dir in ("LONG", "BUY") else "SELL",
                "entry": float(_qp["entry"]), "stop_loss": float(_qp["sl"]),
                "tp1": float(_qp.get("tp1", _qp["entry"])), "tp2": float(_qp.get("tp2", _qp["entry"]))}
    except Exception:
        pass

def check_and_update_paper_orders():
    """
    Checks resting paper limit orders. Fills them only when live market price
    touches or crosses the limit entry price:
      - BUY limit: fills when last_price <= entry
      - SELL limit: fills when last_price >= entry
    """
    pending = st.session_state.get("paper_pending_orders", [])
    if not pending:
        return
    still_pending = []
    for ord_item in pending:
        p_pair = ord_item.get("pair")
        tick = fetch_live_ticker(p_pair)
        px = float(tick.get("last_price", 0.0))
        if px <= 0:
            still_pending.append(ord_item)
            continue

        p_dir = str(ord_item.get("direction", "BUY")).upper()
        is_buy = p_dir in ("BUY", "LONG")
        entry_lvl = float(ord_item.get("entry", 0.0))

        # Check limit order fill condition
        is_filled = (px <= entry_lvl) if is_buy else (px >= entry_lvl)
        if is_filled:
            ord_item["status"] = "PAPER_FILLED"
            ord_item["fill_price"] = px
            ord_item["filled_at"] = datetime.now(IST).strftime("%H:%M:%S IST")
            st.session_state.active_position = ord_item
            st.session_state.executed_trades.insert(0, ord_item)
            # Log to Google Sheets & send filled email notification
            log_trade_to_google_sheet(ord_item, return_details=False)
            send_trade_email(
                pair=p_pair, direction=p_dir, entry=entry_lvl,
                stop_loss=ord_item.get("stop_loss", 0), tp1=ord_item.get("tp1", 0), tp2=ord_item.get("tp2", 0),
                margin_inr=ord_item.get("margin_inr", 10000), leverage=ord_item.get("leverage", 5),
                kind="EXECUTED", note=f"Resting Paper Limit order filled at ${entry_lvl:,.2f}.",
                strategy_name=ord_item.get("strategy_name", ""), strategy_id=ord_item.get("strategy_id", ""),
                trigger_reason=ord_item.get("trigger_reason", "")
            )
            st.toast(f"🎯 Paper Limit Order Filled! {p_dir} {p_pair} @ ${entry_lvl:,.2f}", icon="✅")
        else:
            still_pending.append(ord_item)

    st.session_state.paper_pending_orders = still_pending

# Execute fill checks for pending paper orders
check_and_update_paper_orders()

# ----------------- DATA CACHING -----------------
@st.cache_data(ttl=300)
def get_cached_box_levels(pair):
    return calculate_daily_box_levels(pair)

@st.cache_data(ttl=3)
def get_cached_ticker(pair):
    return fetch_live_ticker(pair)

@st.cache_data(ttl=10)
def get_cached_funding(pair):
    return fetch_futures_funding_rate(pair)

@st.cache_data(ttl=5)
def get_cached_balance():
    return fetch_coindcx_futures_balance()

@st.cache_data(ttl=4)
def get_cached_positions():
    return fetch_coindcx_active_positions()

@st.cache_data(ttl=10)
def get_cached_open_orders():
    return fetch_coindcx_open_orders()

@st.cache_data(ttl=300)
def get_cached_bias(pair):
    return compute_market_bias(pair)

@st.cache_data(ttl=300)
def get_cached_strategy_levels(strategy_id, pair):
    return strategy_registry.get_strategy(strategy_id).compute_levels(pair)

@st.cache_data(ttl=30)
def get_cached_strategy_signal(strategy_id, pair, m_inr, lev, u_inr):
    s = strategy_registry.get_strategy(strategy_id)
    return s.evaluate_signal(pair, get_cached_strategy_levels(strategy_id, pair), m_inr, lev, u_inr)

@st.cache_data(ttl=30)
def _cached_strategy_plan(strategy_id, pair, live_px, m_inr, lev, u_inr):
    s = strategy_registry.get_strategy(strategy_id)
    return s.plan_setups(pair, get_cached_strategy_levels(strategy_id, pair), live_px, m_inr, lev, u_inr)

def get_cached_strategy_plan(strategy_id, pair, live_px, m_inr, lev, u_inr):
    """Only strategies whose plan depends on the live price get it in the cache key (avoids refetching per tick)."""
    lp = float(live_px) if strategy_registry.get_strategy(strategy_id).uses_live_price else 0.0
    return _cached_strategy_plan(strategy_id, pair, lp, m_inr, lev, u_inr)

# ----------------- THEME & STYLING -----------------
st.sidebar.image("https://img.icons8.com/color/96/000000/bitcoin--v1.png", width=50)
st.sidebar.title("⚡ Terminal Controls")

if st.sidebar.button("🔒 Lock Terminal Session", use_container_width=True, help="Lock the terminal and require PIN"):
    st.session_state.authenticated = False
    st.rerun()

chart_theme = st.sidebar.radio(
    "🎨 Dashboard & Chart Theme",
    ["☀️ Crisp Light Theme", "🌙 Dark Terminal Theme"],
    index=0
)
is_light_theme = "Light" in chart_theme

if is_light_theme:
    bg_main = "#f8fafc"
    card_bg = "#ffffff"
    card_border = "#e2e8f0"
    text_color = "#0f172a"
    subtext_color = "#475569"
    banner_bg = "#f1f5f9"
    plot_paper = "#ffffff"
    plot_bg = "#fafbfd"
    plot_grid = "#edf2f7"
    axis_font = "#334155"
    candle_up = "#089981"
    candle_down = "#f23645"
else:
    bg_main = "#0d1117"
    card_bg = "#161b22"
    card_border = "#30363d"
    text_color = "#f0f6fc"
    subtext_color = "#8b949e"
    banner_bg = "#1f2937"
    plot_paper = "#161b22"
    plot_bg = "#0d1117"
    plot_grid = "#21262d"
    axis_font = "#94a3b8"
    candle_up = "#26a69a"
    candle_down = "#ef5350"

st.markdown(f"""
<style>
    .metric-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 10px;
        padding: 14px;
    }}
    .badge-live {{
        background-color: {'#dcfce7' if is_light_theme else '#064e3b'};
        color: {'#15803d' if is_light_theme else '#34d399'};
        border: 1px solid {'#86efac' if is_light_theme else '#059669'};
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 16px;
        font-size: 0.8rem;
        display: inline-flex;
        align-items: center;
        gap: 5px;
    }}
    .badge-funding-pos {{
        background-color: {'#ecfdf5' if is_light_theme else '#064e3b'};
        color: {'#059669' if is_light_theme else '#34d399'};
        border: 1px solid {'#a7f3d0' if is_light_theme else '#059669'};
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
    }}
    .badge-funding-neg {{
        background-color: {'#fff1f2' if is_light_theme else '#881337'};
        color: {'#e11d48' if is_light_theme else '#fda4af'};
        border: 1px solid {'#fecdd3' if is_light_theme else '#be123c'};
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.8rem;
    }}
    .badge-buy {{
        background-color: {'#dcfce7' if is_light_theme else '#064e3b'};
        color: {'#16a34a' if is_light_theme else '#34d399'};
        border: 1px solid {'#86efac' if is_light_theme else '#059669'};
        font-weight: 700;
        padding: 4px 14px;
        border-radius: 6px;
        font-size: 0.95rem;
    }}
    .badge-sell {{
        background-color: {'#fee2e2' if is_light_theme else '#7f1d1d'};
        color: {'#dc2626' if is_light_theme else '#f87171'};
        border: 1px solid {'#fca5a5' if is_light_theme else '#dc2626'};
        font-weight: 700;
        padding: 4px 14px;
        border-radius: 6px;
        font-size: 0.95rem;
    }}
    /* ---------- iPad / iPhone responsive layer ---------- */
    @media only screen and (max-width: 1024px) {{
        .block-container {{ padding: 1rem 1rem 3rem 1rem !important; }}
        div[data-testid="stTabs"] [role="tablist"] {{ overflow-x: auto; flex-wrap: nowrap; -webkit-overflow-scrolling: touch; scrollbar-width: none; }}
        div[data-testid="stTabs"] button[role="tab"] {{ white-space: nowrap; min-height: 48px; }}
    }}
    @media only screen and (max-width: 768px) {{
        .block-container {{ padding: 0.6rem 0.6rem 3rem 0.6rem !important; }}
        .stButton > button, .stDownloadButton > button, div[data-testid="stFormSubmitButton"] button {{ min-height: 48px; font-size: 1rem; }}
        div[data-testid="stHorizontalBlock"] {{ flex-wrap: wrap !important; gap: 0.5rem !important; }}
        div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
        div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{ min-width: calc(50% - 0.5rem) !important; flex: 1 1 calc(50% - 0.5rem) !important; }}
        div[data-testid="stMetric"] {{ background: {card_bg}; border: 1px solid {card_border}; border-radius: 10px; padding: 10px; }}
        h1 {{ font-size: 1.5rem !important; }}
        h2, h3 {{ font-size: 1.2rem !important; }}
        div[data-testid="stDataFrame"], div[data-testid="stTable"] {{ overflow-x: auto; }}
        input, select, textarea {{ font-size: 16px !important; }}
    }}
</style>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR CONTROLS -----------------
st.sidebar.markdown("### 💰 Account Margin Overview")
wallet_data = get_cached_balance()
st.sidebar.metric("Futures Balance", f"₹{wallet_data['total_inr']:,.2f}", wallet_data["source"])

_rot = get_rotational_margin_inr()
default_margin = float(_rot["margin_inr"])
margin_inr = st.sidebar.number_input("Margin per Trade (INR)", value=int(default_margin), step=500)
st.sidebar.caption(f"Rotational sizing: 1/3 of {'live' if _rot['is_live_api'] else 'configured'} wallet ₹{_rot['wallet_equity_inr']:,.0f} = ₹{_rot['margin_inr']:,.0f}")

default_lev = int(os.getenv("LEVERAGE", 5))
leverage = st.sidebar.slider("Leverage Multiplier", min_value=1, max_value=20, value=default_lev)

live_crypto_rate = get_coindcx_live_usdt_inr_rate()
usd_inr = st.sidebar.number_input("USDT / INR Rate (Live CoinDCX)", value=float(live_crypto_rate), step=0.5)
st.sidebar.caption(f"🟢 CoinDCX Live Spot USDT: **₹{live_crypto_rate:,.2f} INR**")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📧 Gmail Trade Alerts")
_mail_cfg = get_email_config()
st.sidebar.markdown("**Mail Server:** `smtp.gmail.com:587` (Default)")
st.sidebar.caption(f"Status: **{'🟢 Configured' if _mail_cfg['configured'] else '🔴 Incomplete'}** | Receiver: `{_mail_cfg['receiver'] or 'Not set'}`")
if not _mail_cfg.get("is_app_password", False):
    st.sidebar.warning(
        "⚠️ **Google App Password Required:**\n\n"
        "Google requires a 16-character **Google App Password** (not your regular account password):\n"
        "1. Open [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)\n"
        "2. Create a 16-char password for 'Mail'\n"
        "3. Paste into `GMAIL_APP_PASSWORD` in `.env`"
    )

if st.sidebar.button("📧 Send Test Trade Alert Email", key="btn_send_test_email", use_container_width=True):
    with st.sidebar:
        with st.spinner("Dispatching test trade alert..."):
            test_ticker = get_cached_ticker(st.session_state.selected_pair)
            ok, msg = send_test_trade_email(st.session_state.selected_pair, test_ticker.get("last_price", 100.0), margin_inr)
            (st.success if ok else st.error)(("✅ " if ok else "❌ ") + msg)

st.sidebar.markdown("### 📡 24/7 Signal Monitor")
st.sidebar.caption("🟢 Background Daemon Active: Scans 15m candles 24/7 with every registered strategy and sends strategy-tagged emails even if this tab is closed.")
monitor_on = st.sidebar.toggle("Auto-Email Alert Notifications", value=True, key="monitor_on")
_strategy_names = [s.name for s in strategy_registry.list_strategies()]
monitor_strategy_names = st.sidebar.multiselect("Strategies on the Signals tab", _strategy_names, default=_strategy_names,
                                                key="monitor_strategies")
monitor_strategy_ids = [s.id for s in strategy_registry.list_strategies() if s.name in monitor_strategy_names]
_default_watch = ["B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT"]
monitor_pairs = st.sidebar.multiselect(
    "Watchlist", GLOBAL_FUTURES_PAIRS,
    default=[p for p in _default_watch if p in GLOBAL_FUTURES_PAIRS], key="monitor_pairs")
st.sidebar.caption("Standalone terminal scanner: `python signal_scanner.py`.")

st.sidebar.markdown("---")
st.sidebar.markdown("### ⚡ Live Refresh Settings")
chart_refresh_rate = st.sidebar.selectbox(
    "Terminal Auto-Update",
    ["Manual Only (Zero Interruption - Recommended)", "Every 15s", "Every 30s", "Every 60s"],
    index=0
)
if st.sidebar.button("🔄 Refresh Terminal & Market Data", use_container_width=True, help="Force refresh balances, positions, and candlestick charts"):
    st.rerun()

# ==============================================================================
# TOP BAR: LIVE PRICE + LIVE PNL + GLOBAL FUTURES DROPDOWN & FAVORITES
# ==============================================================================
top_col1, top_col2, top_col3, top_col4 = st.columns([1.8, 1.4, 1.6, 2.0])

with top_col1:
    cur_session = get_current_session_info()
    st.title("⚡ Crypto Trade Assistant")
    st.caption(f"Asset: **`{st.session_state.selected_pair}`** | **{cur_session['emoji']} {cur_session['name']}** ({cur_session['window']})")

# REQUIREMENT 1: LIVE PRICE + FUNDING RATE
with top_col2:
    @st.fragment(run_every="5s")
    def render_live_price_ticker(pair):
        tick = get_cached_ticker(pair)
        fund = get_cached_funding(pair)
        lp = tick.get("last_price", 0.0)
        chg = tick.get("change_24h", 0.0)
        chg_col = "#16a34a" if chg >= 0 else "#dc2626"
        chg_sgn = "+" if chg >= 0 else ""
        fmt_price = f"${lp:,.4f}" if lp < 1.0 else f"${lp:,.2f}"
        fund_badge_class = "badge-funding-pos" if fund["is_positive"] else "badge-funding-neg"

        st.html(f"""
            <div style="background:{card_bg}; border:1px solid {card_border}; border-radius:10px; padding:8px 12px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span class="badge-live">● LIVE PRICE</span>
                    <span class="{fund_badge_class}">{fund['funding_rate_str']} ({fund['countdown']})</span>
                </div>
                <div style="margin-top:4px;">
                    <span style="font-size:1.5rem; font-weight:800; color:{text_color};">{fmt_price}</span>
                    <span style="font-size:0.95rem; font-weight:700; color:{chg_col}; margin-left:6px;">{chg_sgn}{chg:.2f}%</span>
                </div>
            </div>
        """)

    render_live_price_ticker(st.session_state.selected_pair)

# REQUIREMENT 1: LIVE PnL AT TOP LIKE LIVE PRICE
with top_col3:
    @st.fragment(run_every="5s")
    def render_live_pnl_header(pair):
        live_positions = get_cached_positions()
        matching_live = next((p for p in live_positions if p["pair"] == pair), None)
        if matching_live:
            pnl_inr = matching_live["pnl_inr"]
            pnl_usd = matching_live["pnl_usd"]
            roe_pct = matching_live["roe_pct"]
            entry_p = matching_live["entry_price"]
            dir_str = matching_live["direction"]
            p_name = matching_live["pair"]
            pnl_col = "#16a34a" if pnl_inr >= 0 else "#dc2626"
            pnl_sgn = "+" if pnl_inr >= 0 else ""

            st.html(f"""
                <div style="background:{card_bg}; border:1px solid {pnl_col}; border-radius:10px; padding:8px 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:{pnl_col}; font-size:0.8rem;">● LIVE PnL ({dir_str} {p_name})</span>
                        <span style="font-size:0.75rem; color:{subtext_color};">Entry: ${entry_p:,.2f}</span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="font-size:1.5rem; font-weight:800; color:{pnl_col};">{pnl_sgn}₹{pnl_inr:,.2f}</span>
                        <span style="font-size:0.95rem; font-weight:700; color:{pnl_col}; margin-left:6px;">{pnl_sgn}{roe_pct:.2f}% ROE (${pnl_usd:,.2f})</span>
                    </div>
                </div>
            """)
            return
        elif len(live_positions) > 0:
            total_pnl_inr = sum(p["pnl_inr"] for p in live_positions)
            total_pnl_usd = sum(p["pnl_usd"] for p in live_positions)
            pnl_col = "#16a34a" if total_pnl_inr >= 0 else "#dc2626"
            pnl_sgn = "+" if total_pnl_inr >= 0 else ""
            pos_labels = ", ".join(p["pair"].replace("B-", "").replace("_USDT", "") for p in live_positions)

            st.html(f"""
                <div style="background:{card_bg}; border:1px solid {pnl_col}; border-radius:10px; padding:8px 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:{pnl_col}; font-size:0.8rem;">● PORTFOLIO PnL ({len(live_positions)} Open: {pos_labels})</span>
                        <span style="font-size:0.75rem; color:{subtext_color};">FLAT on {pair.replace('B-', '').replace('_USDT', '')}</span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="font-size:1.5rem; font-weight:800; color:{pnl_col};">{pnl_sgn}₹{total_pnl_inr:,.2f}</span>
                        <span style="font-size:0.95rem; font-weight:700; color:{pnl_col}; margin-left:6px;">({pnl_sgn}${total_pnl_usd:,.2f} USD)</span>
                    </div>
                </div>
            """)
            return

        pos = st.session_state.active_position
        tick = get_cached_ticker(pair)
        cur_p = tick.get("last_price", 0.0)

        # Check if there is a pending resting limit order for this pair
        pending_list = st.session_state.get("paper_pending_orders", [])
        pair_pending = next((o for o in pending_list if o.get("pair") == pair), None)

        if pos and pos.get("pair") == pair and cur_p > 0 and pos.get("status") in ("LIVE_FILLED", "PAPER_FILLED"):
            entry_p = pos.get("entry", 0.0)
            qty = pos.get("crypto_qty", 0.0)
            pos_dir = pos.get("direction") or pos.get("signal", "BUY")
            is_buy = str(pos_dir).upper() in ["BUY", "LONG"]
            u_inr = pos.get("usd_inr", 85.0)
            m_inr = pos.get("margin_inr", 100000)

            price_diff = (cur_p - entry_p) if is_buy else (entry_p - cur_p)
            pnl_usd = price_diff * qty
            pnl_inr = pnl_usd * u_inr
            roe_pct = (pnl_usd / (m_inr / u_inr)) * 100.0 if m_inr > 0 else 0.0

            pnl_col = "#16a34a" if pnl_inr >= 0 else "#dc2626"
            pnl_sgn = "+" if pnl_inr >= 0 else ""

            st.html(f"""
                <div style="background:{card_bg}; border:1px solid {pnl_col}; border-radius:10px; padding:8px 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:{pnl_col}; font-size:0.8rem;">● LIVE PnL ({pos_dir})</span>
                        <span style="font-size:0.75rem; color:{subtext_color};">Entry: ${entry_p:,.2f}</span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="font-size:1.5rem; font-weight:800; color:{pnl_col};">{pnl_sgn}₹{pnl_inr:,.2f}</span>
                        <span style="font-size:0.95rem; font-weight:700; color:{pnl_col}; margin-left:6px;">{pnl_sgn}{roe_pct:.2f}% ROE</span>
                    </div>
                </div>
            """)
        elif pair_pending:
            p_dir = pair_pending.get("direction", "ORDER")
            p_entry = pair_pending.get("entry", 0.0)
            dist_pct = abs(cur_p - p_entry) / p_entry * 100 if p_entry > 0 else 0.0
            st.html(f"""
                <div style="background:{card_bg}; border:1px solid #3b82f6; border-radius:10px; padding:8px 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:#3b82f6; font-size:0.8rem;">⏳ PENDING LIMIT ({p_dir})</span>
                        <span style="font-size:0.75rem; color:{subtext_color};">Target: ${p_entry:,.2f}</span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="font-size:1.5rem; font-weight:800; color:#94a3b8;">₹0.00</span>
                        <span style="font-size:0.85rem; font-weight:600; color:#3b82f6; margin-left:6px;">Waiting for fill ({dist_pct:.2f}% away)</span>
                    </div>
                </div>
            """)
        else:
            real_pnl = st.session_state.realized_pnl_inr
            real_col = "#16a34a" if real_pnl >= 0 else "#dc2626"
            real_sgn = "+" if real_pnl >= 0 else ""
            st.html(f"""
                <div style="background:{card_bg}; border:1px solid {card_border}; border-radius:10px; padding:8px 12px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <span style="font-weight:700; color:{subtext_color}; font-size:0.8rem;">● LIVE PnL (FLAT)</span>
                        <span style="font-size:0.75rem; color:{subtext_color};">No Open Position</span>
                    </div>
                    <div style="margin-top:4px;">
                        <span style="font-size:1.5rem; font-weight:800; color:{text_color};">₹0.00</span>
                        <span style="font-size:0.85rem; color:{real_col}; margin-left:6px; font-weight:600;">Realized: {real_sgn}₹{real_pnl:,.0f}</span>
                    </div>
                </div>
            """)

    render_live_pnl_header(st.session_state.selected_pair)

# RIGHT DROPDOWN: GLOBAL FUTURES + FAVORITES
with top_col4:
    st.markdown(f"<div style='font-size:0.85rem; font-weight:700; color:{text_color}; margin-bottom:2px;'>🌐 GLOBAL FUTURES SELECTOR</div>", unsafe_allow_html=True)
    fav_filter_col, dropdown_col = st.columns([1.1, 2])
    with fav_filter_col:
        show_favs_only = st.checkbox("⭐ Favorites Only", value=False, key="filter_favs_checkbox")

    if show_favs_only and len(st.session_state.favorite_pairs) > 0:
        available_pairs = [p for p in GLOBAL_FUTURES_PAIRS if p in st.session_state.favorite_pairs]
        if not available_pairs:
            available_pairs = GLOBAL_FUTURES_PAIRS
    else:
        available_pairs = GLOBAL_FUTURES_PAIRS

    cur_idx = available_pairs.index(st.session_state.selected_pair) if st.session_state.selected_pair in available_pairs else 0

    with dropdown_col:
        new_pair = st.selectbox(
            "Select Global Future",
            available_pairs,
            index=cur_idx,
            label_visibility="collapsed",
            key="global_futures_select"
        )
        if new_pair != st.session_state.selected_pair:
            st.session_state.selected_pair = new_pair
            st.rerun()

    fav_btn_col, fav_stat_col = st.columns([1.2, 1.8])
    with fav_btn_col:
        is_cur_fav = st.session_state.selected_pair in st.session_state.favorite_pairs
        if is_cur_fav:
            if st.button("⭐ Favorited", key="btn_toggle_fav"):
                st.session_state.favorite_pairs.remove(st.session_state.selected_pair)
                st.rerun()
        else:
            if st.button("☆ Add to ⭐", key="btn_toggle_fav"):
                st.session_state.favorite_pairs.append(st.session_state.selected_pair)
                st.rerun()
    with fav_stat_col:
        st.caption(f"⭐ {len(st.session_state.favorite_pairs)} Favorites saved")

st.markdown("---")

selected_pair = st.session_state.selected_pair
asset_name = selected_pair.split('_')[0].replace('B-', '')
levels = get_cached_box_levels(selected_pair)
ticker = get_cached_ticker(selected_pair)
live_price = ticker.get("last_price", 0.0)
funding_info = get_cached_funding(selected_pair)

chart_sec = None
if "15" in chart_refresh_rate:
    chart_sec = 15
elif "30" in chart_refresh_rate:
    chart_sec = 30
elif "60" in chart_refresh_rate:
    chart_sec = 60

# Main Tabs
if is_execution_link:
    t_exec, t_signals, t_live, t_levels, t_sheets, t_backtest = st.tabs([
        "🛡️ Trade Execution",
        "🎯 Signals",
        "📊 Live Trades",
        "📐 Key Levels & Predefined Setup",
        "📋 Google Sheet Logger",
        "📊 Multi-Derivative Backtest"
    ])
    st.info(f"⚡ **Alert Action Link Loaded:** Trade Execution station prefilled for **{selected_pair}**. Review levels below and click Execute.")
else:
    t_signals, t_exec, t_live, t_levels, t_sheets, t_backtest = st.tabs([
        "🎯 Signals",
        "🛡️ Trade Execution",
        "📊 Live Trades",
        "📐 Key Levels & Predefined Setup",
        "📋 Google Sheet Logger",
        "📊 Multi-Derivative Backtest"
    ])

# ==============================================================================
# TAB 0: INTERACTIVE CHART (DARK/LIGHT + TIMEFRAME + BOLD HIGHLIGHTS)
# ==============================================================================
with t_signals:
    @st.fragment(run_every=chart_sec)
    def render_chart_fragment(pair, box_levels, is_light, m_inr, lev, u_inr):
        cur_ticker = get_cached_ticker(pair)
        cur_live_price = cur_ticker.get("last_price", 0.0)

        b_setup = calculate_trade_setup_details("BUY", box_levels, cur_live_price, m_inr, lev, u_inr, pair=pair)
        s_setup = calculate_trade_setup_details("SELL", box_levels, cur_live_price, m_inr, lev, u_inr, pair=pair)

        tf_col, overlay_col, slider_col, reload_col = st.columns([1.8, 2.4, 1.8, 1.2])

        with tf_col:
            st.markdown(f"<b>⏱️ Candle Timeframe:</b>", unsafe_allow_html=True)
            tf_options = ["1m", "5m", "15m", "1h", "4h", "1d"]
            cur_tf_idx = tf_options.index(st.session_state.chart_timeframe) if st.session_state.chart_timeframe in tf_options else 2
            selected_tf = st.radio(
                "Timeframe",
                tf_options,
                index=cur_tf_idx,
                horizontal=True,
                label_visibility="collapsed",
                key=f"tf_radio_{pair}"
            )
            if selected_tf != st.session_state.chart_timeframe:
                st.session_state.chart_timeframe = selected_tf
                st.rerun(scope="fragment")

        with overlay_col:
            st.markdown(f"<b>👁️ Strategy Overlays:</b>", unsafe_allow_html=True)
            overlay_mode = st.selectbox(
                "Overlay Mode",
                ["Show Both BUY & SELL Setups", "BUY Setup Only (Long at RL)", "SELL Setup Only (Short at RH)", "Price Action & Key Levels Only"],
                index=0,
                label_visibility="collapsed",
                key=f"overlay_mode_{pair}"
            )

        with slider_col:
            st.markdown(f"<b>Bars to Display:</b>", unsafe_allow_html=True)
            candle_count = st.slider(
                "Bars",
                min_value=30, max_value=150, value=75, step=5,
                label_visibility="collapsed",
                key=f"bars_{pair}"
            )

        with reload_col:
            st.write("")
            if st.button("🔄 Refresh Data", key=f"btn_chart_refresh_{pair}", use_container_width=True):
                st.rerun(scope="fragment")

        active_tf = st.session_state.chart_timeframe
        df_chart = fetch_coindcx_candles(pair, interval=active_tf, limit=candle_count, sync_live_price=True)

        if not df_chart.empty and box_levels:
            ts_series = pd.to_datetime(df_chart['timestamp'], unit='ms')

            fig = go.Figure()

            fig.add_hrect(y0=box_levels['RH'], y1=box_levels['SH'], fillcolor="rgba(220,38,38,0.10)", line_width=0,
                          layer="below", annotation_text="Sell Zone (RH → SH)", annotation_position="top left")
            fig.add_hrect(y0=box_levels['SL'], y1=box_levels['RL'], fillcolor="rgba(22,163,74,0.10)", line_width=0,
                          layer="below", annotation_text="Buy Zone (RL → SL)", annotation_position="bottom left")

            fig.add_trace(go.Candlestick(
                x=ts_series,
                open=df_chart['open'],
                high=df_chart['high'],
                low=df_chart['low'],
                close=df_chart['close'],
                name=f"{pair} ({active_tf})",
                increasing_line_color=candle_up,
                increasing_fillcolor=candle_up,
                decreasing_line_color=candle_down,
                decreasing_fillcolor=candle_down
            ))

            # Overlay 50 EMA and 200 EMA curves on the active timeframe
            ema50_curve = df_chart['close'].ewm(span=50, adjust=False).mean()
            ema200_curve = df_chart['close'].ewm(span=200, adjust=False).mean()
            fig.add_trace(go.Scatter(
                x=ts_series, y=ema50_curve, mode="lines",
                name=f"50 EMA ({active_tf})",
                line=dict(color="#8b5cf6", width=2)
            ))
            fig.add_trace(go.Scatter(
                x=ts_series, y=ema200_curve, mode="lines",
                name=f"200 EMA ({active_tf})",
                line=dict(color="#f59e0b", width=2, dash="dot")
            ))

            def fmt(p):
                if p is None:
                    return "0.00"
                return f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"

            # Bold Highlight Badges for Levels
            fig.add_hline(
                y=box_levels['SH'], line_dash="dash", line_color="#ef4444", line_width=2,
                annotation_text=f"<b>▲ SH (Swing High): {fmt(box_levels['SH'])}</b>",
                annotation_position="top left",
                annotation_bgcolor="#991b1b" if not is_light else "#dc2626",
                annotation_bordercolor="#ffffff",
                annotation_borderwidth=1.5,
                annotation_borderpad=5,
                annotation_font=dict(size=12, color="#ffffff", family="Arial Black, Arial, sans-serif")
            )
            fig.add_hline(
                y=box_levels['RH'], line_color="#ea580c", line_width=2.5,
                annotation_text=f"<b>▲ RH / PDH (Range High): {fmt(box_levels['RH'])}</b>",
                annotation_position="top left",
                annotation_bgcolor="#c2410c" if not is_light else "#ea580c",
                annotation_bordercolor="#ffffff",
                annotation_borderwidth=1.5,
                annotation_borderpad=5,
                annotation_font=dict(size=12, color="#ffffff", family="Arial Black, Arial, sans-serif")
            )
            fig.add_hline(
                y=box_levels['MID'], line_dash="dot", line_color="#0284c7", line_width=2.5,
                annotation_text=f"<b>◆ MID (Equilibrium 50%): {fmt(box_levels['MID'])}</b>",
                annotation_position="top left",
                annotation_bgcolor="#0369a1" if not is_light else "#0284c7",
                annotation_bordercolor="#ffffff",
                annotation_borderwidth=1.5,
                annotation_borderpad=5,
                annotation_font=dict(size=12, color="#ffffff", family="Arial Black, Arial, sans-serif")
            )
            fig.add_hline(
                y=box_levels['RL'], line_color="#16a34a", line_width=2.5,
                annotation_text=f"<b>▼ RL / PDL (Range Low): {fmt(box_levels['RL'])}</b>",
                annotation_position="bottom left",
                annotation_bgcolor="#15803d" if not is_light else "#16a34a",
                annotation_bordercolor="#ffffff",
                annotation_borderwidth=1.5,
                annotation_borderpad=5,
                annotation_font=dict(size=12, color="#ffffff", family="Arial Black, Arial, sans-serif")
            )
            fig.add_hline(
                y=box_levels['SL'], line_dash="dash", line_color="#10b981", line_width=2,
                annotation_text=f"<b>▼ SL (Swing Low): {fmt(box_levels['SL'])}</b>",
                annotation_position="bottom left",
                annotation_bgcolor="#166534" if not is_light else "#15803d",
                annotation_bordercolor="#ffffff",
                annotation_borderwidth=1.5,
                annotation_borderpad=5,
                annotation_font=dict(size=12, color="#ffffff", family="Arial Black, Arial, sans-serif")
            )

            # Live Price (LTP) Line
            if cur_live_price > 0:
                fig.add_hline(
                    y=cur_live_price,
                    line_dash="dashdot",
                    line_color="#3b82f6",
                    line_width=2.5,
                    annotation_text=f"<b>● LIVE PRICE: {fmt(cur_live_price)}</b>",
                    annotation_position="top right",
                    annotation_bgcolor="#2563eb",
                    annotation_bordercolor="#93c5fd",
                    annotation_borderwidth=2,
                    annotation_borderpad=6,
                    annotation_font=dict(size=13, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )

            # Shaded Liquidity Zones
            fig.add_hrect(
                y0=box_levels['RH'], y1=box_levels['SH'],
                fillcolor="rgba(239, 68, 68, 0.15)" if not is_light else "rgba(239, 68, 68, 0.10)",
                line_width=0,
                annotation_text="<b>▲ Top Liquidity Pool (Bearish Sweep Zone)</b>",
                annotation_position="inside top right",
                annotation_font=dict(size=11, color="#f87171" if not is_light else "#dc2626")
            )
            fig.add_hrect(
                y0=box_levels['SL'], y1=box_levels['RL'],
                fillcolor="rgba(34, 197, 94, 0.15)" if not is_light else "rgba(34, 197, 94, 0.10)",
                line_width=0,
                annotation_text="<b>▼ Bottom Liquidity Pool (Bullish Sweep Zone)</b>",
                annotation_position="inside bottom right",
                annotation_font=dict(size=11, color="#4ade80" if not is_light else "#16a34a")
            )

            # BUY Setup Overlays
            if "BUY" in overlay_mode or "Both" in overlay_mode:
                fig.add_hline(
                    y=b_setup['entry'], line_dash="solid", line_color="#10b981", line_width=2,
                    annotation_text=f"<b>🟢 BUY ENTRY: {fmt(b_setup['entry'])}</b>",
                    annotation_position="bottom right",
                    annotation_bgcolor="#059669",
                    annotation_bordercolor="#a7f3d0",
                    annotation_borderwidth=1.5,
                    annotation_borderpad=5,
                    annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )
                fig.add_hline(
                    y=b_setup['stop_loss'], line_dash="dash", line_color="#ef4444", line_width=2,
                    annotation_text=f"<b>🛑 BUY SL: {fmt(b_setup['stop_loss'])} (-{b_setup['roe_sl']}%)</b>",
                    annotation_position="bottom right",
                    annotation_bgcolor="#dc2626",
                    annotation_bordercolor="#fca5a5",
                    annotation_borderwidth=1.5,
                    annotation_borderpad=5,
                    annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )
                fig.add_hline(
                    y=b_setup['tp1'], line_dash="dot", line_color="#06b6d4", line_width=2,
                    annotation_text=f"<b>🎯 BUY TP1 (MID): {fmt(b_setup['tp1'])} (+{b_setup['roe_tp1']}%)</b>",
                    annotation_position="top right",
                    annotation_bgcolor="#0891b2",
                    annotation_bordercolor="#a5f3fc",
                    annotation_borderwidth=1.5,
                    annotation_borderpad=5,
                    annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )

            # SELL Setup Overlays
            if "SELL" in overlay_mode or "Both" in overlay_mode:
                fig.add_hline(
                    y=s_setup['entry'], line_dash="solid", line_color="#f43f5e", line_width=2,
                    annotation_text=f"<b>🔴 SELL ENTRY: {fmt(s_setup['entry'])}</b>",
                    annotation_position="top right",
                    annotation_bgcolor="#e11d48",
                    annotation_bordercolor="#fecdd3",
                    annotation_borderwidth=1.5,
                    annotation_borderpad=5,
                    annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )
                fig.add_hline(
                    y=s_setup['stop_loss'], line_dash="dash", line_color="#ea580c", line_width=2,
                    annotation_text=f"<b>🛑 SELL SL: {fmt(s_setup['stop_loss'])} (-{s_setup['roe_sl']}%)</b>",
                    annotation_position="top right",
                    annotation_bgcolor="#ea580c",
                    annotation_bordercolor="#fed7aa",
                    annotation_borderwidth=1.5,
                    annotation_borderpad=5,
                    annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )
                fig.add_hline(
                    y=s_setup['tp1'], line_dash="dot", line_color="#0284c7", line_width=2,
                    annotation_text=f"<b>🎯 SELL TP1 (MID): {fmt(s_setup['tp1'])} (+{s_setup['roe_tp1']}%)</b>",
                    annotation_position="bottom right",
                    annotation_bgcolor="#0284c7",
                    annotation_bordercolor="#bae6fd",
                    annotation_borderwidth=1.5,
                    annotation_borderpad=5,
                    annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif")
                )

            fig.update_layout(
                title=dict(
                    text=f"<b>{pair} — {active_tf.upper()} Candles</b> | Box Framework | Live: {fmt(cur_live_price)}",
                    font=dict(size=16, color=text_color, family="Arial Black, Arial, sans-serif")
                ),
                height=630,
                template="plotly_dark" if not is_light else "plotly_white",
                paper_bgcolor=plot_paper,
                plot_bgcolor=plot_bg,
                xaxis=dict(
                    rangeslider=dict(visible=False),
                    gridcolor=plot_grid,
                    showgrid=True,
                    tickfont=dict(color=axis_font, size=11),
                    zeroline=False
                ),
                yaxis=dict(
                    gridcolor=plot_grid,
                    showgrid=True,
                    side="right",
                    tickfont=dict(color=axis_font, size=11),
                    zeroline=False
                ),
                margin=dict(l=25, r=30, t=55, b=25),
                hovermode="x unified"
            )

            st.plotly_chart(fig, use_container_width=True)

            st.markdown(f"""
            <div style="background:{banner_bg}; border:1px solid {card_border}; border-radius:8px; padding:10px 16px; margin-top:-10px; display:flex; flex-wrap:wrap; justify-content:space-between; font-size:0.9rem; color:{text_color}; font-weight:700;">
                <div><span style="color:#ef4444;">● SH:</span> {fmt(box_levels['SH'])}</div>
                <div><span style="color:#ea580c;">● RH:</span> {fmt(box_levels['RH'])}</div>
                <div><span style="color:#0284c7;">● MID:</span> {fmt(box_levels['MID'])}</div>
                <div><span style="color:#16a34a;">● RL:</span> {fmt(box_levels['RL'])}</div>
                <div><span style="color:#10b981;">● SL:</span> {fmt(box_levels['SL'])}</div>
                <div><span style="color:#3b82f6;">● LIVE:</span> {fmt(cur_live_price)}</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.error(f"Could not load {active_tf} candles for {pair}.")

    def _load_signal_into_exec(p, strategy_name):
        st.session_state.selected_pair = p
        st.session_state["exec_strategy_mode"] = f"{strategy_name} Only"

    @st.fragment(run_every="60s")
    def render_signals_panel(watch, auto_send, m_inr, lev, u_inr, strat_ids):
        st.subheader("🎯 Strategy Signals — every registered strategy, every watchlist pair")
        st.caption("Evaluated on the last CLOSED 15m candle. Each new confirmation is e-mailed once, tagged with its strategy "
                   "(60-min cooldown per strategy/pair/direction). Open the **🛡️ Trade Execution** tab to review the pre-filled ticket.")
        if not watch:
            st.info("Pick at least one derivative in the sidebar **Signal Monitor** watchlist.")
            return
        if not strat_ids:
            st.info("Pick at least one strategy in the sidebar **Strategies on the Signals tab** selector.")
            return
        results = signal_monitor.scan_and_alert(watch, m_inr, lev, u_inr, send=auto_send, strategy_ids=strat_ids) if signal_monitor else []
        st.caption(f"Last scan: {datetime.now(IST).strftime('%I:%M:%S %p IST')} • auto e-mail {'ON' if auto_send else 'OFF'}")

        by_pair = {}
        for r in results:
            by_pair.setdefault(r["pair"], []).append(r)

        for pair_r, rs in by_pair.items():
            name_r = pair_r.replace("B-", "").replace("_USDT", "")
            lv = get_cached_box_levels(pair_r)
            px = get_cached_ticker(pair_r).get("last_price", 0.0)
            if lv and px:
                if px >= lv["RH"]:
                    zone_txt = "🔴 Inside **Sell Zone** (RH–SH)" if px <= lv["SH"] else "🔴 Above Swing High"
                elif px <= lv["RL"]:
                    zone_txt = "🟢 Inside **Buy Zone** (RL–SL)" if px >= lv["SL"] else "🟢 Below Swing Low"
                else:
                    zone_txt = "⚪ Mid-range (no zone touched)"
            else:
                zone_txt = "levels unavailable"

            with st.container(border=True):
                h1, h2 = st.columns([2, 3])
                h1.markdown(f"### {name_r}  \n`${px:,.4f}`" if px < 1 else f"### {name_r}  \n`${px:,.2f}`")
                h2.markdown(f"Box zone: {zone_txt}")
                for r in rs:
                    sig = r["signal"]
                    if sig and sig["signal"] != "NEUTRAL":
                        is_l = sig["signal"] == "LONG"
                        badge = "badge-buy" if is_l else "badge-sell"
                        st.markdown(f"<span class='{badge}'>{r['strategy_name']} — {sig['signal']} ({sig['signal_kind']})</span> "
                                    f"&nbsp; {sig.get('trigger_reason') or sig.get('trigger_zone') or ''}", unsafe_allow_html=True)
                        m1, m2, m3, m4 = st.columns(4)
                        m1.metric("Entry", f"${sig['entry']:,.4f}")
                        m2.metric("Stop Loss", f"${sig['stop_loss']:,.4f}")
                        m3.metric("TP1", f"${sig['tp1']:,.4f}")
                        m4.metric("TP2", f"${sig['tp2']:,.4f}")
                        st.caption(f"Margin ₹{sig['margin_inr']:,.0f} @ {sig['leverage']}x • TP1 ≈ +₹{sig['profit_tp1_inr']:,.0f} • SL ≈ -₹{sig['loss_sl_inr']:,.0f} • "
                                   f"📧 {'sent' if r['emailed'] else r['message']}")
                        if sig["signal_kind"] == "CONTINUATION":
                            st.caption("⚠️ Continuation (tower) signals are alert-only ideas and have not been backtested.")
                        if st.button(f"➡️ Load {name_r} ({r['strategy_name']}) into Execution tab", key=f"btn_load_sig_{r['strategy_id']}_{pair_r}",
                                     use_container_width=True, on_click=_load_signal_into_exec, args=(pair_r, r["strategy_name"])):
                            st.rerun()
                    else:
                        st.caption(f"**{r['strategy_name']}** — no confirmation on the last closed 15m candle • {r['message']}")

    render_signals_panel(monitor_pairs, monitor_on, margin_inr, leverage, usd_inr, monitor_strategy_ids)

# ==============================================================================
# TAB 1: LIVE TRADE EXECUTION, FEES & CAPITAL PRESERVATION (REQUIREMENTS 2, 3, 4, 5)
# ==============================================================================
with t_exec:
    def render_trade_execution_fragment(pair, box_levels):
        st.subheader(f"⚡ Live Trade Execution Station — {pair}")

        # Persistent Notification Banner for Orders & API Errors
        if st.session_state.last_order_status:
            los = st.session_state.last_order_status
            los_type = los.get("type", "info")
            los_msg = los.get("msg", "")
            los_time = los.get("timestamp", "")
            los_pair = los.get("pair", "")

            c_banner, c_dismiss = st.columns([0.92, 0.08])
            with c_banner:
                banner_title = f"**CoinDCX Order Notice [{los_time}] ({los_pair}):**" if los_pair else f"**CoinDCX Order Notice [{los_time}]:**"
                if los_type == "error":
                    st.error(f"{banner_title} {los_msg}")
                elif los_type == "success":
                    st.success(f"{banner_title} {los_msg}")
                else:
                    st.info(f"{banner_title} {los_msg}")
            with c_dismiss:
                if st.button("✕", key="btn_dismiss_banner", help="Dismiss this alert notice"):
                    st.session_state.last_order_status = None
                    st.rerun()

        cur_ticker = get_cached_ticker(pair)
        cur_price = cur_ticker.get("last_price", 0.0)
        wallet = get_cached_balance()
        cur_asset = pair.split('_')[0].replace('B-', '')

        def fmt(p):
            if p is None:
                return "0.00"
            return f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"

        # REQUIREMENT 2: FETCH USER'S FUTURES WALLET BALANCE (Isolated Live Fragment)
        st.markdown("#### 💰 Futures Wallet & Margin Balance")
        if not wallet["is_live_api"]:
            st.info("ℹ️ **CoinDCX Live API Notice:** Your `COINDCX_API_SECRET` in `.env` is currently set to placeholder. Enter your real API Secret in `.env` to stream your live CoinDCX Futures wallet and active positions.")

        @st.fragment(run_every="5s")
        def render_wallet_live_strip(target_pair):
            cur_ticker_live = get_cached_ticker(target_pair)
            fund_live = get_cached_funding(target_pair)
            wallet_live = get_cached_balance()
            cur_asset_live = target_pair.split('_')[0].replace('B-', '')

            w1, w2, w3, w4 = st.columns(4)
            with w1:
                st.metric("Total Futures Balance", f"₹{wallet_live['total_inr']:,.2f}")
                st.caption(f"Locked Margin: ₹{wallet_live.get('locked_inr', 0.0):,.2f}")
            with w2:
                st.metric("Available Free Margin", f"₹{wallet_live['available_inr']:,.2f}")
                st.caption(f"Rate: ₹{wallet_live.get('live_usd_inr', 100.0):,.2f}/USDT")
            with w3:
                fund_sign = "+" if fund_live["is_positive"] else ""
                st.metric(
                    "8h Funding Rate",
                    f"{fund_live['funding_rate_str']}",
                    f"{'Positive' if fund_live['is_positive'] else 'Negative'} ({fund_live['countdown']})"
                )
                st.caption(fund_live["sentiment"])
            with w4:
                live_pos = get_cached_positions()
                act_p = st.session_state.active_position
                m_pos = next((p for p in live_pos if p["pair"] == target_pair), None) if live_pos else None

                if m_pos:
                    mpnl = m_pos["pnl_inr"]
                    mroe = m_pos["roe_pct"]
                    psgn = "+" if mpnl >= 0 else ""
                    st.metric("Live Position", f"{m_pos['direction']} {m_pos['quantity']} {cur_asset_live}")
                    st.caption(f"PnL: {psgn}₹{mpnl:,.2f} ({psgn}{mroe:.2f}% ROE)")
                elif live_pos:
                    tpnl = sum(p['pnl_inr'] for p in live_pos)
                    psgn = "+" if tpnl >= 0 else ""
                    st.metric("CoinDCX Positions", f"{len(live_pos)} Live Open")
                    st.caption(f"Total Unrealized: {psgn}₹{tpnl:,.2f}")
                elif act_p:
                    pdir = act_p.get("direction") or act_p.get("signal", "BUY")
                    pqty = act_p.get("crypto_qty", 0.0)
                    st.metric("Simulated Position", f"{pdir} {pqty} {cur_asset_live}")
                else:
                    st.metric("Active Position", "FLAT (0 Open)")
                    st.caption("No open exposure")

        render_wallet_live_strip(pair)

        # Simulated active position close bar
        if st.session_state.active_position:
            act_p = st.session_state.active_position
            pdir = act_p.get("direction") or act_p.get("signal", "BUY")
            pqty = act_p.get("crypto_qty", 0.0)
            col_sim1, col_sim2 = st.columns([3, 1])
            with col_sim1:
                st.info(f"📝 **Simulated Position Active:** {pdir} {pqty} {cur_asset} (Entry: ${act_p.get('entry', cur_price):,.2f})")
            with col_sim2:
                if st.button("Close Simulated Position", key=f"btn_close_pos_{pair}", use_container_width=True):
                    is_b = str(pdir).upper() in ["BUY", "LONG"]
                    entry_price = act_p.get("entry", cur_price)
                    diff = (cur_price - entry_price) if is_b else (entry_price - cur_price)
                    real_inr = diff * pqty * act_p.get("usd_inr", 85.0)
                    st.session_state.realized_pnl_inr += real_inr
                    st.session_state.active_position = None
                    st.session_state.last_order_status = {
                        "type": "success",
                        "msg": f"Simulated position closed! Realized PnL: ₹{real_inr:,.2f}",
                        "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                        "pair": pair
                    }
                    st.rerun()

        live_positions = get_cached_positions()
        st.caption("📊 Open positions, TP/SL edits and Close / Close-All live in the **Live Trades** tab.")

        st.markdown("---")

        # REQUIREMENT 2: ALLOW USERS TO INPUT MARGIN & LEVERAGE BEFORE EXECUTION
        st.markdown("#### 🎛️ Configure Order Margin & Leverage")
        inp_col1, inp_col2, inp_col3 = st.columns([1.5, 1.5, 1])

        with inp_col1:
            avail_margin_int = max(1000, int(wallet["available_inr"]))
            margin_key = f"exec_margin_inr_{pair}"
            if margin_key not in st.session_state:
                st.session_state[margin_key] = int(max(500, min(coindcx_engine.get_rotational_margin_inr()["margin_inr"], avail_margin_int if wallet["is_live_api"] else 10**9)))

            def _apply_margin_pct(pct_ratio):
                calc_val = max(500, int(wallet["available_inr"] * pct_ratio))
                st.session_state[margin_key] = min(calc_val, max(avail_margin_int, 500000))

            trade_margin_inr = st.number_input(
                "Margin Allocation for this Trade (INR):",
                min_value=500,
                max_value=max(avail_margin_int, 500000),
                step=1000,
                key=margin_key
            )
            # Preset percentage chips with on_click callbacks that update the input widget before rerun
            c1, c2, c3, c4 = st.columns(4)
            c1.button("25%", key=f"pct_25_{pair}", on_click=_apply_margin_pct, args=(0.25,), use_container_width=True)
            c2.button("50%", key=f"pct_50_{pair}", on_click=_apply_margin_pct, args=(0.50,), use_container_width=True)
            c3.button("75%", key=f"pct_75_{pair}", on_click=_apply_margin_pct, args=(0.75,), use_container_width=True)
            c4.button("100%", key=f"pct_100_{pair}", on_click=_apply_margin_pct, args=(1.00,), use_container_width=True)

        with inp_col2:
            # Check if active position exists for this pair to auto-match leverage
            matching_active_pos = next((p for p in live_positions if p["pair"] == pair), None) if live_positions else None
            active_pos_leverage = int(round(float(matching_active_pos["leverage"]))) if matching_active_pos else None
            default_slider_leverage = active_pos_leverage if active_pos_leverage else 5

            trade_leverage = st.slider(
                "Leverage Multiplier:",
                min_value=1,
                max_value=20,
                value=default_slider_leverage,
                key=f"exec_leverage_{pair}"
            )
            if active_pos_leverage:
                st.caption(f"🔒 **Position Leverage Locked:** CoinDCX requires order leverage to match active {pair} position ({active_pos_leverage}x).")
            else:
                st.caption(f"Position Notional Value: ₹{(trade_margin_inr * trade_leverage):,.0f} (~${(trade_margin_inr * trade_leverage / usd_inr):,.2f} USD)")

        with inp_col3:
            trade_usd_inr = st.number_input(
                "USD/INR Rate:",
                value=float(usd_inr),
                step=0.5,
                key=f"exec_usd_inr_{pair}"
            )

        # ---------------- Strategy arming & order-ticket selection ----------------
        _all_label = "All Active Strategies (Auto-Detect Triggers)"
        _mode_opts = [_all_label] + [f"{s.name} Only" for s in strategy_registry.list_strategies()]
        if st.session_state.get("exec_strategy_mode") not in _mode_opts:
            st.session_state["exec_strategy_mode"] = _mode_opts[0]
        exec_strategy_mode = st.selectbox("🧠 Strategy armed for execution:", _mode_opts, key="exec_strategy_mode",
                                          help="Which strategies may feed order tickets into this station.")
        armed_strats = (strategy_registry.list_strategies() if exec_strategy_mode == _all_label
                        else [s for s in strategy_registry.list_strategies() if f"{s.name} Only" == exec_strategy_mode])

        choices, waiting_notes = [], []   # (label, setup dict, session tag, strategy)
        _pref = st.session_state.get("url_prefill")
        if _pref and _pref.get("pair") == pair:
            _ps = strategy_registry.get_strategy(_pref["strategy_id"])
            if _ps.id in [s.id for s in armed_strats]:
                _pm = strategy_registry.position_metrics(pair, _pref["entry"], _pref["stop_loss"], _pref["tp1"], _pref["tp2"],
                                                         trade_margin_inr, trade_leverage, trade_usd_inr)
                _pset = {"direction": _pref["direction"], "setup": f"{_ps.name}: e-mail alert ticket", "entry": _pref["entry"],
                         "stop_loss": _pref["stop_loss"], "tp1": _pref["tp1"], "tp2": _pref["tp2"], **_pm,
                         "strategy_id": _ps.id, "strategy_name": _ps.name, "trigger_reason": "Loaded from e-mail alert link"}
                choices.append((f"📧 {_ps.name} — e-mail alert {_pref['direction']} (Entry {fmt(_pref['entry'])})", _pset,
                                strategy_registry.setup_tag(_ps.id, "EMAIL"), _ps))
        for _s in armed_strats:
            _sig = get_cached_strategy_signal(_s.id, pair, trade_margin_inr, trade_leverage, trade_usd_inr)
            _sig_live = bool(_sig and _sig.get("signal") in ("LONG", "SHORT"))
            if _sig_live:
                _sd = "BUY" if _sig["signal"] == "LONG" else "SELL"
                choices.append((f"⚡ {_s.name} — LIVE SIGNAL {_sig['signal']}: {_sig.get('trigger_reason') or _sig.get('setup', '')}",
                                {**_sig, "direction": _sd}, strategy_registry.setup_tag(_s.id, "SIGNAL"), _s))
            _plan = get_cached_strategy_plan(_s.id, pair, float(cur_price), trade_margin_inr, trade_leverage, trade_usd_inr)
            _added = False
            for _d, _ico, _word in (("BUY", "🟢", "BUY / LONG"), ("SELL", "🔴", "SELL / SHORT")):
                _st = _plan.get(_d)
                if not _st or _st.get("signal_kind"):   # plan identical to the live signal above
                    continue
                choices.append((f"{_ico} {_s.name} — {_word} plan (Entry {fmt(_st['entry'])})", _st,
                                strategy_registry.setup_tag(_s.id, _d), _s))
                _added = True
            if not _added and not _sig_live and _plan.get("note"):
                waiting_notes.append(f"**{_s.name}:** {_plan['note']}")

        cost_details = None
        exec_left, exec_right = st.columns([1.1, 1.1])

        with exec_left:
            st.markdown("#### Choose Order Setup")
            for _n in waiting_notes:
                st.caption(f"⏳ {_n}")
            if choices:
                _labels = [c[0] for c in choices]
                _def = next((i for i, c in enumerate(choices) if c[2].endswith("EMAIL")),
                            next((i for i, c in enumerate(choices) if c[2].endswith("SIGNAL")), 0))
                trade_choice = st.radio("Execution Mode:", _labels, index=_def, key=f"trade_choice_exec_{pair}_{exec_strategy_mode}")
                _, active_trade, setup_tag, active_strategy = choices[_labels.index(trade_choice)]
                trade_dir = "BUY" if str(active_trade.get("direction", "BUY")).upper() in ("BUY", "LONG") else "SELL"
                color_class = "badge-buy" if trade_dir == "BUY" else "badge-sell"
                _tp1n, _tp2n = active_strategy.tp1_name, active_strategy.tp2_name
                st.caption(f"🧠 Strategy: **{active_strategy.name}**"
                           + (f" • {active_trade.get('trigger_reason')}" if active_trade.get("trigger_reason") else ""))

                # Dynamically track and synchronize inputs when switching setups
                entry_key = f"custom_entry_{pair}_{setup_tag}"
                sl_key = f"custom_sl_{pair}_{setup_tag}"
                tp1_key = f"custom_tp1_{pair}_{setup_tag}"
                tp2_key = f"custom_tp2_{pair}_{setup_tag}"
                choice_tracker_key = f"last_setup_tag_{pair}"
                levels_tracker_key = f"last_formula_entry_{pair}_{setup_tag}"

                # Whenever the setup choice changes or underlying formula levels change, update session state values
                if st.session_state.get(choice_tracker_key) != setup_tag or st.session_state.get(levels_tracker_key) != float(active_trade["entry"]):
                    st.session_state[choice_tracker_key] = setup_tag
                    st.session_state[levels_tracker_key] = float(active_trade["entry"])
                    st.session_state[entry_key] = float(active_trade["entry"])
                    st.session_state[sl_key] = float(active_trade["stop_loss"])
                    st.session_state[tp1_key] = float(active_trade["tp1"])
                    st.session_state[tp2_key] = float(active_trade["tp2"])

                # REQUIREMENT 3: MANUAL ADJUSTMENT OF TP1, TP2, AND SL BEFORE EXECUTION
                with st.expander(f"✏️ Customize Order Levels ({trade_dir}: Entry, SL, TP1, TP2)", expanded=True):
                    exp_h1, exp_h2 = st.columns([3, 1.2])
                    with exp_h1:
                        st.caption(f"Prefilled with **{trade_dir}** formula values. Adjust any level manually before placing your trade:")
                    with exp_h2:
                        if st.button("↺ Reset to Formula", key=f"btn_reset_levels_{pair}_{setup_tag}", use_container_width=True, help="Reset levels back to calculated box values"):
                            st.session_state[entry_key] = float(active_trade["entry"])
                            st.session_state[sl_key] = float(active_trade["stop_loss"])
                            st.session_state[tp1_key] = float(active_trade["tp1"])
                            st.session_state[tp2_key] = float(active_trade["tp2"])
                            st.rerun(scope="fragment")

                    adj_col1, adj_col2 = st.columns(2)
                    p_ref = active_trade["entry"]
                    step_val = 0.5 if p_ref > 1.0 else (0.0001 if p_ref > 0.001 else 0.000001)
                    fmt_str = "%.2f" if p_ref > 1.0 else ("%.4f" if p_ref > 0.001 else "%.6f")

                    with adj_col1:
                        custom_entry = st.number_input(
                            "Planned Entry Price ($):",
                            value=float(st.session_state.get(entry_key, active_trade["entry"])),
                            step=step_val,
                            format=fmt_str,
                            key=entry_key
                        )
                        custom_sl = st.number_input(
                            "Stop Loss SL ($):",
                            value=float(st.session_state.get(sl_key, active_trade["stop_loss"])),
                            step=step_val,
                            format=fmt_str,
                            key=sl_key
                        )
                    with adj_col2:
                        custom_tp1 = st.number_input(
                            "Take Profit 1 ({_tp1n}) ($):".format(_tp1n=_tp1n),
                            value=float(st.session_state.get(tp1_key, active_trade["tp1"])),
                            step=step_val,
                            format=fmt_str,
                            key=tp1_key
                        )
                        custom_tp2 = st.number_input(
                            "Take Profit 2 ({_tp2n}) ($):".format(_tp2n=_tp2n),
                            value=float(st.session_state.get(tp2_key, active_trade["tp2"])),
                            step=step_val,
                            format=fmt_str,
                            key=tp2_key
                        )

                # Recalculate metrics dynamically based on custom user inputs
                pos_usd = (trade_margin_inr * trade_leverage) / trade_usd_inr
                c_qty = format_order_quantity(pair, pos_usd / custom_entry) if custom_entry > 0 else 0
                rew_tp1 = abs(custom_tp1 - custom_entry)
                rew_tp2 = abs(custom_tp2 - custom_entry)
                r_sl = abs(custom_entry - custom_sl)

                c_roe_tp1 = round((rew_tp1 / custom_entry) * trade_leverage * 100, 2) if custom_entry > 0 else 0
                c_roe_tp2 = round((rew_tp2 / custom_entry) * trade_leverage * 100, 2) if custom_entry > 0 else 0
                c_roe_sl = round((r_sl / custom_entry) * trade_leverage * 100, 2) if custom_entry > 0 else 0

                c_profit_tp1_inr = round((rew_tp1 * c_qty) * trade_usd_inr, 2)
                c_profit_tp2_inr = round((rew_tp2 * c_qty) * trade_usd_inr, 2)
                c_loss_sl_inr = round((r_sl * c_qty) * trade_usd_inr, 2)

                active_trade = {
                    **active_trade,
                    "entry": custom_entry,
                    "stop_loss": custom_sl,
                    "tp1": custom_tp1,
                    "tp2": custom_tp2,
                    "crypto_qty": c_qty,
                    "roe_tp1": c_roe_tp1,
                    "roe_tp2": c_roe_tp2,
                    "roe_sl": c_roe_sl,
                    "profit_tp1_inr": c_profit_tp1_inr,
                    "profit_tp2_inr": c_profit_tp2_inr,
                    "loss_sl_inr": c_loss_sl_inr
                }

                # Compute detailed costs and capital-preservation safe TP
                cost_details = calculate_trade_costs_and_safe_tp(
                    direction=trade_dir,
                    entry_price=active_trade["entry"],
                    margin_inr=trade_margin_inr,
                    leverage=trade_leverage,
                    usd_inr=trade_usd_inr
                )

                # Order Ticket Card
                ticket_html = f"""
                <div style="background:{card_bg}; border:2px solid {card_border}; border-radius:12px; padding:18px; margin-top:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
                        <span class="{color_class}">ORDER TICKET: {trade_dir} {cur_asset}</span>
                        <span style="font-weight:700; color:{text_color}; font-size:1.05rem;">LTP: {fmt(cur_price)}</span>
                    </div>
                    <table style="width:100%; border-collapse:collapse; font-size:0.92rem; color:{text_color};">
                        <tr style="border-bottom:1px solid {card_border};">
                            <td style="padding:6px 0;"><b>Planned Entry:</b></td>
                            <td style="text-align:right; font-weight:700;">{fmt(active_trade['entry'])}</td>
                        </tr>
                        <tr style="border-bottom:1px solid {card_border};">
                            <td style="padding:6px 0;"><b>Stop Loss:</b></td>
                            <td style="text-align:right; color:#dc2626; font-weight:700;">{fmt(active_trade['stop_loss'])} (-{active_trade['roe_sl']}%)</td>
                        </tr>
                        <tr style="border-bottom:1px solid {card_border};">
                            <td style="padding:6px 0;"><b>Take Profit 1 ({_tp1n}):</b></td>
                            <td style="text-align:right; color:#0284c7; font-weight:700;">{fmt(active_trade['tp1'])} (+{active_trade['roe_tp1']}%)</td>
                        </tr>
                        <tr style="border-bottom:1px solid {card_border};">
                            <td style="padding:6px 0;"><b>Take Profit 2 ({_tp2n}):</b></td>
                            <td style="text-align:right; color:#16a34a; font-weight:700;">{fmt(active_trade['tp2'])} (+{active_trade['roe_tp2']}%)</td>
                        </tr>
                        <tr style="border-bottom:1px solid {card_border};">
                            <td style="padding:6px 0;"><b>Order Quantity:</b></td>
                            <td style="text-align:right; font-weight:700;">{active_trade['crypto_qty']} {cur_asset}</td>
                        </tr>
                        <tr style="border-bottom:1px solid {card_border};">
                            <td style="padding:6px 0;"><b>Effective Margin:</b></td>
                            <td style="text-align:right;">₹{trade_margin_inr:,.0f} @ {trade_leverage}x Leverage</td>
                        </tr>
                        <tr>
                            <td style="padding:6px 0;"><b>Projected Profit (TP1):</b></td>
                            <td style="text-align:right; color:#16a34a; font-weight:800; font-size:1.05rem;">+₹{active_trade['profit_tp1_inr']:,.2f}</td>
                        </tr>
                    </table>
                </div>
                """
                st.html(ticket_html)

                # Check if order meets CoinDCX minimum required order value (₹2,448 INR)
                trade_notional_inr = active_trade['crypto_qty'] * active_trade['entry'] * trade_usd_inr
                is_below_min_val = trade_notional_inr < 2448.0

                if is_below_min_val:
                    st.warning(f"⚠️ **CoinDCX Minimum Order Constraint:** Current order value is **₹{trade_notional_inr:,.0f} INR**. CoinDCX exchange strictly requires a minimum order value of **₹2,448 INR**. Please increase margin or leverage.")

                st.write("")
                price_shield_pct = st.slider(
                    "🛡️ Price Shield — max deviation of live price from entry (%)",
                    min_value=0.05, max_value=1.0, value=0.15, step=0.05, key=f"price_shield_{pair}",
                    help="Live orders are blocked if the live price has moved further than this from the planned entry."
                )
                st.caption(f"🛡️ Price Shield armed for **{active_strategy.name}** • Live orders are sent as **Limit Maker (post_only)** so they can never pay taker slippage.")
                exec_mode = st.radio(
                    "Execution Target:",
                    ["⚡ Live CoinDCX Exchange Order (Real Funds API)", "📝 Simulated Paper Trade (Track in App & Google Sheet)"],
                    index=0 if wallet["is_live_api"] else 1,
                    key=f"exec_mode_choice_{pair}"
                )

                btn_label = f"🚀 EXECUTE {trade_dir} ORDER ({'COINDCX LIVE' if 'Live' in exec_mode else 'PAPER SIM'})"
                if st.button(btn_label, key=f"btn_exec_{pair}", type="primary", use_container_width=True):
                    exec_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
                    live_api_msg = ""
                    order_placed_ok = True
                    api_extra = {}

                    shield_blocked, shield_live_px, shield_dev = False, 0.0, 0.0
                    if "Live" in exec_mode and wallet["is_live_api"]:
                        shield_live_px = float(fetch_live_ticker(pair).get("last_price", 0.0) or 0.0)
                        _ent = float(active_trade["entry"])
                        shield_dev = abs(shield_live_px - _ent) / _ent * 100.0 if (_ent > 0 and shield_live_px > 0) else 999.0
                        shield_blocked = shield_dev > price_shield_pct

                    if "Live" in exec_mode:
                        if not wallet["is_live_api"]:
                            err_text = "CoinDCX API credentials not configured in .env. Cannot place live exchange order."
                            st.session_state.last_order_status = {
                                "type": "error",
                                "msg": err_text,
                                "timestamp": exec_time,
                                "pair": pair
                            }
                            st.session_state.api_error_logs.insert(0, {
                                "timestamp": exec_time,
                                "pair": pair,
                                "action": f"LIVE_{trade_dir}",
                                "status": "ERROR",
                                "message": err_text,
                                "details": {}
                            })
                            st.error(f"❌ {err_text}")
                            order_placed_ok = False
                        elif is_below_min_val:
                            err_text = f"Order value (₹{trade_notional_inr:,.0f} INR) is below CoinDCX exchange minimum of ₹2,448 INR. Increase margin or leverage."
                            st.session_state.last_order_status = {
                                "type": "error",
                                "msg": err_text,
                                "timestamp": exec_time,
                                "pair": pair
                            }
                            st.session_state.api_error_logs.insert(0, {
                                "timestamp": exec_time,
                                "pair": pair,
                                "action": f"LIVE_{trade_dir}",
                                "status": "ERROR",
                                "message": err_text,
                                "details": {"notional_inr": trade_notional_inr, "min_required_inr": 2448.0}
                            })
                            st.error(f"❌ {err_text}")
                            order_placed_ok = False
                        elif shield_blocked:
                            err_text = (f"🛡️ Price Shield blocked the order: live price {fmt(shield_live_px)} is {shield_dev:.2f}% away from "
                                        f"planned entry {fmt(active_trade['entry'])} (limit {price_shield_pct:.2f}%). Refresh the setup and retry.")
                            st.session_state.last_order_status = {"type": "error", "msg": err_text, "timestamp": exec_time, "pair": pair}
                            st.session_state.api_error_logs.insert(0, {
                                "timestamp": exec_time, "pair": pair, "action": f"LIVE_{trade_dir}", "status": "ERROR",
                                "message": err_text, "details": {"live_price": shield_live_px, "entry": active_trade["entry"], "deviation_pct": round(shield_dev, 3)}
                            })
                            st.error(err_text)
                            order_placed_ok = False
                        else:
                            _maker_px = round_asset_price(
                                min(float(active_trade["entry"]), shield_live_px) if trade_dir == "BUY" else max(float(active_trade["entry"]), shield_live_px),
                                float(active_trade["entry"]))
                            with st.spinner("Submitting Limit Maker (post_only) order to CoinDCX Futures API..."):
                                ok, api_msg, api_extra = place_coindcx_futures_order(
                                    pair=pair,
                                    side=trade_dir,
                                    quantity=active_trade["crypto_qty"],
                                    leverage=trade_leverage,
                                    order_type="limit_order",
                                    price=_maker_px,
                                    post_only=True,
                                    margin_currency="INR",
                                    tp_price=active_trade["tp1"],
                                    sl_price=active_trade["stop_loss"]
                                )
                                order_placed_ok = ok
                                live_api_msg = api_msg

                                log_entry = {
                                    "timestamp": exec_time,
                                    "pair": pair,
                                    "action": f"LIVE_{trade_dir}",
                                    "status": "SUCCESS" if ok else "ERROR",
                                    "message": api_msg,
                                    "details": api_extra or {"quantity": active_trade["crypto_qty"], "entry": active_trade["entry"], "leverage": trade_leverage}
                                }
                                st.session_state.api_error_logs.insert(0, log_entry)

                                if not ok:
                                    st.session_state.last_order_status = {
                                        "type": "error",
                                        "msg": api_msg,
                                        "timestamp": exec_time,
                                        "pair": pair
                                    }
                                    st.error(f"❌ CoinDCX Execution Failed: {api_msg}")

                    if order_placed_ok:
                        is_live = "Live" in exec_mode
                        cur_market_px = float(get_cached_ticker(pair).get("last_price", 0.0))
                        is_buy_dir = (trade_dir == "BUY")
                        limit_entry_px = float(active_trade["entry"])

                        # For paper trades: check if market price has already reached the limit level
                        # A BUY limit order fills only when price <= entry
                        # A SELL limit order fills only when price >= entry
                        already_reached = (cur_market_px <= limit_entry_px) if is_buy_dir else (cur_market_px >= limit_entry_px) if cur_market_px > 0 else True

                        order_status = "LIVE_FILLED" if is_live else ("PAPER_FILLED" if already_reached else "PAPER_PENDING")

                        order_record = {
                            "timestamp": exec_time,
                            "pair": pair,
                            "signal": trade_dir,
                            "direction": trade_dir,
                            "setup": active_trade.get("setup", "Box Setup"),
                            "entry": limit_entry_px,
                            "stop_loss": active_trade["stop_loss"],
                            "tp1": active_trade["tp1"],
                            "tp2": active_trade["tp2"],
                            "crypto_qty": active_trade["crypto_qty"],
                            "margin_inr": trade_margin_inr,
                            "leverage": trade_leverage,
                            "usd_inr": trade_usd_inr,
                            "profit_tp1_inr": active_trade["profit_tp1_inr"],
                            "loss_sl_inr": active_trade["loss_sl_inr"],
                            "status": order_status,
                            "strategy_id": active_strategy.id,
                            "strategy_name": active_strategy.name,
                            "trigger_reason": active_trade.get("trigger_reason", "")
                        }

                        if is_live:
                            st.session_state.active_position = order_record
                            st.session_state.executed_trades.insert(0, order_record)
                            sheet_success, sheet_msg = log_trade_to_google_sheet(order_record, return_details=True)
                            mail_ok, mail_msg = send_trade_email(
                                pair=pair, direction=trade_dir, entry=limit_entry_px, stop_loss=active_trade["stop_loss"],
                                tp1=active_trade["tp1"], tp2=active_trade["tp2"], margin_inr=trade_margin_inr, leverage=trade_leverage,
                                kind="EXECUTED", note="Live Limit Maker order submitted.",
                                strategy_name=active_strategy.name, strategy_id=active_strategy.id,
                                trigger_reason=active_trade.get("trigger_reason", ""))
                            status_headline = "LIVE COINDCX ORDER EXECUTED!"
                            success_text = f"✅ **{status_headline}** {trade_dir} {active_trade['crypto_qty']} {cur_asset} @ {fmt(limit_entry_px)} | {live_api_msg} | Google Sheets: {sheet_msg} | Email: {mail_msg}"
                        elif already_reached:
                            # Paper order filled immediately because price already reached entry
                            st.session_state.active_position = order_record
                            st.session_state.executed_trades.insert(0, order_record)
                            sheet_success, sheet_msg = log_trade_to_google_sheet(order_record, return_details=True)
                            mail_ok, mail_msg = send_trade_email(
                                pair=pair, direction=trade_dir, entry=limit_entry_px, stop_loss=active_trade["stop_loss"],
                                tp1=active_trade["tp1"], tp2=active_trade["tp2"], margin_inr=trade_margin_inr, leverage=trade_leverage,
                                kind="EXECUTED", note="Paper trade filled at limit price.",
                                strategy_name=active_strategy.name, strategy_id=active_strategy.id,
                                trigger_reason=active_trade.get("trigger_reason", ""))
                            status_headline = "PAPER ORDER FILLED!"
                            success_text = f"✅ **{status_headline}** {trade_dir} {active_trade['crypto_qty']} {cur_asset} @ {fmt(limit_entry_px)} | Paper Position Active | Google Sheets: {sheet_msg} | Email: {mail_msg}"
                        else:
                            # Paper limit order resting - NOT FILLED YET
                            st.session_state.setdefault("paper_pending_orders", []).insert(0, order_record)
                            status_headline = "PAPER LIMIT ORDER PLACED (PENDING FILL)!"
                            dist_val = abs(cur_market_px - limit_entry_px)
                            dist_pct = (dist_val / limit_entry_px * 100.0) if limit_entry_px > 0 else 0.0
                            success_text = f"⏳ **{status_headline}** {trade_dir} limit @ {fmt(limit_entry_px)}. Live price is {fmt(cur_market_px)} ({dist_pct:.2f}% away). Order will fill automatically when price reaches entry!"

                        st.session_state.setdefault("trade_plans", {})[pair] = {
                            "direction": "LONG" if trade_dir == "BUY" else "SHORT", "entry": limit_entry_px,
                            "sl": active_trade["stop_loss"], "tp1": active_trade["tp1"], "tp2": active_trade["tp2"],
                            "applied": False, "margin_inr": trade_margin_inr, "leverage": trade_leverage}

                        st.session_state.last_order_status = {
                            "type": "success" if already_reached or is_live else "info",
                            "msg": success_text,
                            "timestamp": exec_time,
                            "pair": pair
                        }
                        if not is_live:
                            st.session_state.api_error_logs.insert(0, {
                                "timestamp": exec_time,
                                "pair": pair,
                                "action": f"PAPER_{trade_dir}",
                                "status": "SUCCESS",
                                "message": f"Paper trade: {trade_dir} {active_trade['crypto_qty']} {cur_asset} ({order_status})",
                                "details": order_record
                            })
                        st.rerun()
            else:
                st.info("No order ticket for the armed strategy right now — see waiting notes above.")

        # REQUIREMENTS 3 & 5: ROUND-TRIP FEES & ANTI-DECAY SAFE TP SHIELD
        with exec_right:
            st.markdown("#### 💸 Round-Trip Execution Fees & Capital Shield")

            if cost_details:
                shield_html = f"""
                <div style="background:{card_bg}; border:2px solid {'#3b82f6' if is_light_theme else '#1d4ed8'}; border-radius:12px; padding:18px; margin-top:10px;">
                    <div style="font-weight:700; color:{text_color}; font-size:1.05rem; margin-bottom:10px; display:flex; justify-content:space-between;">
                        <span>🛡️ Capital Preservation & Cost Shield</span>
                        <span style="color:#0284c7;">CoinDCX Futures</span>
                    </div>

                    <div style="background:{banner_bg}; border-radius:8px; padding:10px 14px; margin-bottom:12px;">
                        <div style="display:flex; justify-content:space-between; font-size:0.9rem; margin-bottom:4px;">
                            <span style="color:{subtext_color};">Position Notional Value:</span>
                            <span style="font-weight:700; color:{text_color};">₹{cost_details['notional_inr']:,.0f} (${cost_details['notional_usd']:,.2f})</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.9rem; margin-bottom:4px;">
                            <span style="color:{subtext_color};">Base Exchange Fees (0.10% Round-Trip):</span>
                            <span style="font-weight:700; color:{text_color};">₹{cost_details['round_trip_base_fee_inr']:,.2f} (${cost_details['round_trip_base_fee_usd']:,.2f})</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.9rem; margin-bottom:4px;">
                            <span style="color:#d97706; font-weight:600;">🇮🇳 Indian GST (18% on Fees):</span>
                            <span style="font-weight:700; color:#d97706;">+₹{cost_details['total_gst_inr']:,.2f} (${cost_details['total_gst_usd']:,.2f})</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.9rem; margin-bottom:4px;">
                            <span style="color:{subtext_color};">Total Statutory Fees (Fee + 18% GST):</span>
                            <span style="font-weight:700; color:#dc2626;">₹{cost_details['round_trip_fee_inr']:,.2f} (${cost_details['round_trip_fee_usd']:,.2f})</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; font-size:0.9rem; margin-bottom:4px;">
                            <span style="color:{subtext_color};">Slippage & Spread Buffer (0.02%):</span>
                            <span style="font-weight:700; color:{subtext_color};">₹{cost_details['slippage_buffer_inr']:,.2f}</span>
                        </div>
                        <hr style="margin:6px 0; border:0; border-top:1px solid {card_border};">
                        <div style="display:flex; justify-content:space-between; font-size:0.95rem; font-weight:800;">
                            <span>Overall Real Cost (Incl. 18% GST):</span>
                            <span style="color:#dc2626;">₹{cost_details['total_cost_inr']:,.2f} ({cost_details['cost_pct_of_margin']}% of margin)</span>
                        </div>
                    </div>

                    <div style="font-size:0.9rem; color:{text_color}; line-height:1.6;">
                        <div style="margin-bottom:8px;">
                            <b>🎯 Breakeven Price:</b> <span style="font-size:1.0rem; font-weight:700; color:#0284c7; background:{banner_bg}; padding:2px 6px; border-radius:4px;">{fmt(cost_details['breakeven_price'])}</span><br>
                            <span style="font-size:0.8rem; color:{subtext_color};">Requires a minimum move of <b>{cost_details['min_breakeven_move_pct']}%</b> just to cover friction fees.</span>
                        </div>

                        <div style="margin-bottom:8px;">
                            <b>🛡️ Minimum Safe TP (Prevents Capital Decay):</b> <span style="font-size:1.0rem; font-weight:700; color:#16a34a; background:{banner_bg}; padding:2px 6px; border-radius:4px;">{fmt(cost_details['safe_tp_price'])}</span><br>
                            <span style="font-size:0.8rem; color:{subtext_color};">Guarantees net profit of <b>+₹{cost_details['safe_profit_net_inr']:,.2f}</b> (≥ 3x fee coverage). Exiting below this level risks long-term capital attrition.</span>
                        </div>

                        <div style="margin-bottom:4px;">
                            <b>⚡ Planned TP1 Margin Coverage:</b> <span style="font-weight:800; color:#16a34a;">{(active_trade['profit_tp1_inr'] / max(1, cost_details['total_cost_inr'])):.1f}x fee coverage</span><br>
                            <span style="font-size:0.8rem; color:{subtext_color};">TP1 target of <b>+₹{active_trade['profit_tp1_inr']:,.2f}</b> safely clears all execution friction!</span>
                        </div>
                    </div>
                </div>
                """
                st.html(shield_html)

            # Session Order History
            st.markdown("#### 📜 Session Executed Orders")
            if st.session_state.executed_trades:
                history_df = pd.DataFrame([
                    {
                        "Time": t["timestamp"].split()[1],
                        "Pair": t.get("pair", pair),
                        "Side": t["signal"],
                        "Margin": f"₹{t.get('margin_inr', trade_margin_inr):,.0f}",
                        "Lev": f"{t.get('leverage', trade_leverage)}x",
                        "Entry": fmt(t['entry']),
                        "TP1": fmt(t['tp1']),
                        "Profit TP1": f"₹{t['profit_tp1_inr']:,.0f}"
                    }
                    for t in st.session_state.executed_trades[:5]
                ])
                st.dataframe(history_df, use_container_width=True, hide_index=True)
            else:
                st.info("No orders executed yet in this session.")

            # Dedicated CoinDCX API & Order Execution Error Console
            st.markdown("---")
            st.markdown("#### 📋 CoinDCX Execution & API Error Console")
            has_error_logs = bool(st.session_state.api_error_logs)
            with st.expander(f"📡 Real-Time CoinDCX API & Error Logs ({len(st.session_state.api_error_logs)} events recorded)", expanded=has_error_logs):
                col_clear, col_log_info = st.columns([1.5, 4.0])
                with col_clear:
                    if st.button("🗑️ Clear Log History", key=f"btn_clear_logs_{pair}", use_container_width=True):
                        st.session_state.api_error_logs = []
                        st.session_state.last_order_status = None
                        st.rerun()
                with col_log_info:
                    st.caption("Maintains persistent history of live order dispatches, bracket adjustments, emergency exits, and exchange error messages. Logs are preserved across reruns.")

                if st.session_state.api_error_logs:
                    for idx, entry in enumerate(st.session_state.api_error_logs[:20]):
                        is_err = entry.get("status") == "ERROR"
                        border_c = "#dc2626" if is_err else "#16a34a"
                        bg_c = "#fef2f2" if is_light_theme and is_err else ("#3b181a" if is_err else ("#f0fdf4" if is_light_theme else "#132b1e"))
                        txt_c = "#991b1b" if is_light_theme and is_err else ("#fca5a5" if is_err else ("#166534" if is_light_theme else "#86efac"))

                        st.markdown(
                            f"""
                            <div style="background:{bg_c}; border-left:4px solid {border_c}; border-radius:6px; padding:10px 14px; margin-bottom:8px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                                    <span style="font-weight:700; color:{txt_c}; font-size:0.95rem;">{'❌ ' + entry.get('status', 'ERROR') if is_err else '✅ SUCCESS'} — {entry.get('action', 'ORDER')} ({entry.get('pair', '')})</span>
                                    <span style="font-size:0.8rem; color:{subtext_color};">{entry.get('timestamp', '')}</span>
                                </div>
                                <div style="font-size:0.9rem; color:{text_color}; font-weight:500;">{entry.get('message', '')}</div>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        if entry.get("details"):
                            with st.expander(f"🔍 Raw Technical Details & Request Payload (Log #{idx + 1})", expanded=False):
                                st.json(entry["details"])
                else:
                    st.info("No API execution errors or orders logged yet in this session.")

    render_trade_execution_fragment(selected_pair, levels)

# ==============================================================================
# TAB 2: LIVE TRADES & POSITION MANAGER
# ==============================================================================
# TAB 2: LIVE TRADES & POSITION MANAGER
# ==============================================================================
with t_live:
    def _lt_fmt(p):
        return f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"

    def _lt_finish_close(pos, pnl_inr, reason_label):
        """Book realised PnL, log the final result to Google Sheets and e-mail the close."""
        st.session_state.realized_pnl_inr += pnl_inr
        plan = st.session_state.get("trade_plans", {}).get(pos["pair"], {})
        record = {
            "entry_time": plan.get("opened", ""), "exit_time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S"),
            "pair": pos["pair"], "direction": pos["direction"], "session": "",
            "entry_price": pos["entry_price"], "stop_loss": plan.get("sl", pos.get("stop_loss") or ""),
            "exit_price": pos["mark_price"], "exit_reason": reason_label, "net_pnl_inr": round(pnl_inr, 2),
            "duration_candles": "",
        }
        log_trade_closed(record)
        if pnl_inr < 0:
            log_failed_trade_diagnostic(record)
        send_trade_email(
            pair=pos["pair"], direction=pos["direction"], entry=pos["entry_price"],
            stop_loss=float(plan.get("sl") or pos.get("stop_loss") or 0), tp1=float(plan.get("tp1") or pos.get("take_profit") or 0),
            tp2=float(plan.get("tp2") or 0), margin_inr=float(pos.get("locked_margin_inr", 0)), leverage=int(pos.get("leverage", 5) or 5),
            kind="CLOSED", note=f"Closed at ~{_lt_fmt(pos['mark_price'])} | Final PnL: {'+' if pnl_inr >= 0 else ''}₹{pnl_inr:,.2f} ({reason_label})")

    @st.fragment(run_every="10s")
    def render_live_trades_manager():
        # Check resting paper orders on each fragment cycle
        check_and_update_paper_orders()

        st.subheader("📊 Live Trades & Position Manager")
        live_positions = get_cached_positions() or []
        paper = st.session_state.active_position
        plans = st.session_state.get("trade_plans", {})
        pending_paper = st.session_state.get("paper_pending_orders", [])

        # Display Pending Paper Limit Orders (Resting)
        if pending_paper:
            st.markdown("#### ⏳ Pending Paper Limit Orders (Resting / Unfilled)")
            for idx, p_ord in enumerate(list(pending_paper)):
                p_pair = p_ord.get("pair", "")
                p_tick = get_cached_ticker(p_pair)
                p_cur_px = float(p_tick.get("last_price", 0.0))
                p_dir = p_ord.get("direction", "BUY")
                p_entry = float(p_ord.get("entry", 0.0))
                p_dist = abs(p_cur_px - p_entry) if p_cur_px else 0.0
                p_dist_pct = (p_dist / p_entry * 100.0) if p_entry > 0 else 0.0
                is_p_buy = p_dir == "BUY"

                with st.container(border=True):
                    badge_cls = "badge-buy" if is_p_buy else "badge-sell"
                    st.markdown(f"<span class='{badge_cls}'>{p_dir} LIMIT {p_pair}</span> &nbsp; **{p_ord['crypto_qty']}** @ {_lt_fmt(p_entry)} ({p_ord.get('leverage', 5)}x)", unsafe_allow_html=True)
                    c_m1, c_m2, c_m3, c_m4 = st.columns(4)
                    c_m1.metric("Planned Entry", _lt_fmt(p_entry))
                    c_m2.metric("Live Mark", _lt_fmt(p_cur_px))
                    c_m3.metric("Distance to Fill", f"{p_dist_pct:.2f}%", f"{'-' if (is_p_buy and p_cur_px > p_entry) else '+'}{_lt_fmt(p_dist)}")
                    c_m4.metric("Allocated Margin", f"₹{p_ord.get('margin_inr', 0):,.0f}")
                    st.caption(f"Status: ⏳ Resting Limit Order • Waiting for live price ({_lt_fmt(p_cur_px)}) to {'drop to' if is_p_buy else 'rise to'} {_lt_fmt(p_entry)}")
                    if st.button(f"❌ Cancel Pending Order ({p_pair})", key=f"lt_cancel_pending_{idx}", use_container_width=True):
                        st.session_state.paper_pending_orders.remove(p_ord)
                        st.session_state.last_order_status = {
                            "type": "info",
                            "msg": f"Cancelled pending paper {p_dir} limit order for {p_pair}.",
                            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                            "pair": p_pair
                        }
                        st.rerun()

        total_margin = sum(float(p.get("locked_margin_inr", 0) or 0) for p in live_positions)
        total_unreal = sum(float(p.get("pnl_inr", 0) or 0) for p in live_positions)
        unreal_pct = (total_unreal / total_margin * 100.0) if total_margin > 0 else 0.0
        realized = st.session_state.realized_pnl_inr
        n_open = len(live_positions) + (1 if paper else 0)

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("Total Open Positions", n_open)
        s2.metric("Margin Deployed", f"₹{total_margin:,.0f}")
        s3.metric("Unrealized PnL", f"{'+' if total_unreal >= 0 else ''}₹{total_unreal:,.2f}", f"{unreal_pct:+.2f}%")
        s4.metric("Realized Session PnL", f"{'+' if realized >= 0 else ''}₹{realized:,.2f}")

        if live_positions and st.button("🚨 Close All Positions", key="lt_close_all", type="primary", use_container_width=True):
            snapshot = list(live_positions)
            with st.spinner("Closing all positions on CoinDCX..."):
                closed, total, msg = exit_all_coindcx_positions()
            if closed:
                for pos in snapshot:
                    _lt_finish_close(pos, float(pos.get("pnl_inr", 0) or 0), "Manual close (Close All)")
            st.session_state.last_order_status = {"type": "success" if closed == total else "error", "msg": msg,
                                                  "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"), "pair": "ALL"}
            st.rerun()

        if not live_positions and not paper:
            st.info("No open positions. Executed trades appear here with live mark price, SL/TPs and PnL.")

        for p in live_positions:
            pid, pr = p["id"], p["pair"]
            is_long = p["direction"] == "LONG"
            entry_p, mark_p = float(p["entry_price"]), float(p["mark_price"])
            plan = plans.get(pr, {})
            cur_sl, cur_tp = p.get("stop_loss"), p.get("take_profit")
            tp1 = float(plan.get("tp1") or cur_tp or 0)
            tp2 = float(plan.get("tp2") or 0)

            # Apply the planned SL/TP once, if the resting limit order has filled and no bracket exists yet
            if plan and not plan.get("applied") and not cur_sl:
                ok, m = update_coindcx_position_tpsl(pid, plan.get("tp1"), plan.get("sl"), pair=pr)
                plan["applied"] = True
                plan["apply_msg"] = ("✅ Planned SL/TP applied on fill" if ok else f"⚠️ Could not apply planned SL/TP: {m}")
                cur_sl, cur_tp = plan.get("sl"), plan.get("tp1")

            # Ratchet trailing status (advisory: exchange holds one TP, so SL moves are applied by button)
            ratchet, target_sl = "—", None
            if tp1 and tp2:
                half = (tp1 + tp2) / 2.0
                reached = (lambda lvl: mark_p >= lvl) if is_long else (lambda lvl: mark_p <= lvl)
                if reached(half):
                    ratchet, target_sl = "🔒 ≥50% of TP1→TP2: ratchet SL to TP1 (MID)", tp1
                elif reached(tp1):
                    ratchet, target_sl = "✅ TP1 (MID) reached: take 50%, SL to breakeven", entry_p
                else:
                    ratchet = "⏳ Waiting for TP1 (MID)"

            pnl_inr, roe = float(p["pnl_inr"]), float(p["roe_pct"])
            col = "#16a34a" if pnl_inr >= 0 else "#dc2626"
            with st.container(border=True):
                badge = "badge-buy" if is_long else "badge-sell"
                st.markdown(f"<span class='{badge}'>{p['direction']} {pr}</span> &nbsp; **{p['quantity']}** @ {_lt_fmt(entry_p)} ({p['leverage']}x)", unsafe_allow_html=True)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Entry", _lt_fmt(entry_p))
                m2.metric("Live Mark", _lt_fmt(mark_p))
                m3.metric("Structural SL", _lt_fmt(float(cur_sl)) if cur_sl else "not set")
                m4.metric("TP1 / TP2", f"{_lt_fmt(tp1) if tp1 else '—'} / {_lt_fmt(tp2) if tp2 else '—'}")
                st.markdown(f"<div style='font-size:1.15rem;font-weight:800;color:{col}'>{'+' if pnl_inr >= 0 else ''}₹{pnl_inr:,.2f} ({roe:+.2f}% ROE)</div>", unsafe_allow_html=True)
                st.caption(f"Ratchet: {ratchet} • Liq {_lt_fmt(float(p.get('liquidation_price', 0) or 0))} • Margin ₹{float(p.get('locked_margin_inr', 0) or 0):,.0f}")
                if plan.get("apply_msg"):
                    st.caption(plan["apply_msg"])

                b1, b2 = st.columns(2)
                if target_sl is not None:
                    better = (cur_sl is None) or ((target_sl > float(cur_sl)) if is_long else (target_sl < float(cur_sl)))
                    if better and b1.button("🔒 Apply ratchet SL", key=f"lt_ratchet_{pid}", use_container_width=True):
                        ok, m = update_coindcx_position_tpsl(pid, cur_tp, target_sl, pair=pr)
                        (st.success if ok else st.error)(("✅ " if ok else "❌ ") + m)
                if b2.button(f"❌ Close Position ({pr})", key=f"lt_close_{pid}", use_container_width=True):
                    with st.spinner(f"Closing {pr}..."):
                        ok, m = exit_coindcx_position(pid)
                    if ok:
                        _lt_finish_close(p, pnl_inr, "Manual close")
                        st.session_state.last_order_status = {"type": "success", "msg": f"✅ Closed {pr}. Final PnL {'+' if pnl_inr >= 0 else ''}₹{pnl_inr:,.2f}",
                                                              "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"), "pair": pr}
                        st.rerun()
                    else:
                        st.error(f"❌ {m}")

                with st.expander(f"⚙️ Adjust TP / SL — {pr}"):
                    step = 0.5 if mark_p > 1.0 else 0.0001
                    fmt_s = "%.2f" if mark_p > 1.0 else "%.4f"
                    e1, e2, e3 = st.columns([1.5, 1.5, 1])
                    new_tp = e1.number_input("Take Profit ($)", value=float(cur_tp) if cur_tp else float(tp1 or mark_p), step=step, format=fmt_s, key=f"lt_tp_{pid}")
                    new_sl = e2.number_input("Stop Loss ($)", value=float(cur_sl) if cur_sl else float(mark_p), step=step, format=fmt_s, key=f"lt_sl_{pid}")
                    if e3.button("💾 Save", key=f"lt_save_{pid}", use_container_width=True):
                        ok, m = update_coindcx_position_tpsl(pid, new_tp, new_sl, pair=pr)
                        (st.success if ok else st.error)(("✅ " if ok else "❌ ") + m)

        if paper:
            pr = paper.get("pair", "")
            px = get_cached_ticker(pr).get("last_price", 0.0) if pr else 0.0
            is_b = str(paper.get("direction") or paper.get("signal", "BUY")).upper() in ("BUY", "LONG")
            e_px, qty = float(paper.get("entry", 0)), float(paper.get("crypto_qty", 0))
            diff = (px - e_px) if is_b else (e_px - px)
            p_inr = diff * qty * float(paper.get("usd_inr", 85.0)) if px else 0.0
            with st.container(border=True):
                st.markdown(f"📝 **Paper position** — {'LONG' if is_b else 'SHORT'} {pr} {qty} @ {_lt_fmt(e_px)}")
                q1, q2, q3 = st.columns(3)
                q1.metric("Live Mark", _lt_fmt(px) if px else "—")
                q2.metric("SL / TP1", f"{_lt_fmt(float(paper.get('stop_loss', 0)))} / {_lt_fmt(float(paper.get('tp1', 0)))}")
                q3.metric("Unrealized PnL", f"{'+' if p_inr >= 0 else ''}₹{p_inr:,.2f}")
                if st.button("❌ Close Paper Position", key="lt_close_paper", use_container_width=True):
                    st.session_state.realized_pnl_inr += p_inr
                    st.session_state.active_position = None
                    st.rerun()

    render_live_trades_manager()


# ==============================================================================
# TAB 2: KEY BOX LEVELS BREAKDOWN
# ==============================================================================
def _fmt_px(p):
    if p is None:
        return "0.00"
    return f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"


@st.fragment(run_every=chart_sec)
def render_strategy_chart_fragment(pair, strategy_id, s_levels, plan):
    """Generic chart for any registered strategy: candles + strategy.chart_lines() + strategy.chart_markers()."""
    strat = strategy_registry.get_strategy(strategy_id)
    cur_live = get_cached_ticker(pair).get("last_price", 0.0)
    c1, c2, c3 = st.columns([2.2, 1.8, 1.0])
    with c1:
        tf = st.radio("Timeframe", ["5m", "15m", "1h", "4h", "1d"], index=1, horizontal=True, key=f"tf_{strategy_id}_{pair}")
    with c2:
        bars = st.slider("Bars", min_value=30, max_value=150, value=75, step=5, key=f"bars_{strategy_id}_{pair}")
    with c3:
        st.write("")
        if st.button("🔄 Refresh", key=f"btn_refresh_{strategy_id}_{pair}", use_container_width=True):
            st.rerun(scope="fragment")

    df_c = fetch_coindcx_candles(pair, interval=tf, limit=bars, sync_live_price=True)
    if df_c.empty:
        st.error(f"Could not load {tf} candles for {pair}.")
        return
    ts = pd.to_datetime(df_c["timestamp"], unit="ms")
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=ts, open=df_c["open"], high=df_c["high"], low=df_c["low"], close=df_c["close"],
                                 name=f"{pair} ({tf})", increasing_line_color=candle_up, increasing_fillcolor=candle_up,
                                 decreasing_line_color=candle_down, decreasing_fillcolor=candle_down))
    for ln in strat.chart_lines(s_levels, plan):
        fig.add_hline(y=ln["price"], line_dash=ln.get("dash", "solid"), line_color=ln["color"], line_width=2,
                      annotation_text=f"<b>{ln['label']}: {_fmt_px(ln['price'])}</b>", annotation_position="top left",
                      annotation_bgcolor=ln["color"], annotation_bordercolor="#ffffff", annotation_borderpad=4,
                      annotation_font=dict(size=11, color="#ffffff", family="Arial Black, Arial, sans-serif"))
    marks = strat.chart_markers(df_c, s_levels, tf)
    if marks:
        fig.add_trace(go.Scatter(
            x=[ts.iloc[m["idx"]] for m in marks], y=[m["price"] for m in marks], mode="markers+text",
            text=[m["text"] for m in marks], textposition=["bottom center" if m["bear"] else "top center" for m in marks],
            marker=dict(symbol=["triangle-up" if m["bear"] else "triangle-down" for m in marks], size=13,
                        color=["#f59e0b" for _ in marks], line=dict(width=1, color="#78350f")),
            textfont=dict(size=10, color="#f59e0b"), name="≥ 25% ATR candle", hoverinfo="text"))
    if cur_live > 0:
        fig.add_hline(y=cur_live, line_dash="dashdot", line_color="#3b82f6", line_width=2,
                      annotation_text=f"<b>● LIVE: {_fmt_px(cur_live)}</b>", annotation_position="top right",
                      annotation_bgcolor="#2563eb", annotation_font=dict(size=12, color="#ffffff"))
    fig.update_layout(
        title=dict(text=f"<b>{pair} — {tf.upper()}</b> | {strat.name} | Live: {_fmt_px(cur_live)}",
                   font=dict(size=15, color=text_color, family="Arial Black, Arial, sans-serif")),
        height=580, template="plotly_dark" if not is_light_theme else "plotly_white",
        paper_bgcolor=plot_paper, plot_bgcolor=plot_bg, showlegend=False, hovermode="x unified",
        xaxis=dict(rangeslider=dict(visible=False), gridcolor=plot_grid, tickfont=dict(color=axis_font, size=11)),
        yaxis=dict(gridcolor=plot_grid, side="right", tickfont=dict(color=axis_font, size=11)),
        margin=dict(l=20, r=25, t=50, b=20))
    st.plotly_chart(fig, use_container_width=True)
    if strat.chart_marker_hint:
        st.caption(strat.chart_marker_hint)


def render_generic_strategy_levels(strat, pair):
    """Key Levels tab for any non-Box strategy, driven entirely by the strategy's UI hooks."""
    st.caption(strat.description)
    s_levels = get_cached_strategy_levels(strat.id, pair)
    if not s_levels:
        st.warning(f"{strat.name} levels are unavailable for {pair} right now (not enough daily history or API error).")
        return
    badges = strat.metric_badges(s_levels)
    if badges:
        for col, (lab, val, dlt) in zip(st.columns(len(badges)), badges):
            col.metric(lab, val, dlt, delta_color="off")

    plan = get_cached_strategy_plan(strat.id, pair, live_price, margin_inr, leverage, usd_inr)
    st.markdown("#### 🎯 Predefined Trade Plan")
    shown = None
    for d in ("BUY", "SELL"):
        stp = plan.get(d)
        if not stp:
            continue
        shown = stp
        with st.container(border=True):
            st.markdown(f"**{'🟢' if d == 'BUY' else '🔴'} {stp.get('setup', strat.name)}**")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Crossover Entry", f"${stp['entry']:,.4f}")
            c2.metric("Stop Loss", f"${stp['stop_loss']:,.4f}", f"-{stp['roe_sl']}% ROE")
            c3.metric(f"TP1 ({strat.tp1_name})", f"${stp['tp1']:,.4f}", f"+{stp['roe_tp1']}% ROE")
            c4.metric(f"TP2 ({strat.tp2_name})", f"${stp['tp2']:,.4f}", f"+{stp['roe_tp2']}% ROE")
            st.caption(f"{stp.get('trigger_reason', '')} • Margin ₹{margin_inr:,.0f} @ {leverage}x • TP1 ≈ +₹{stp['profit_tp1_inr']:,.0f} "
                       f"• TP2 ≈ +₹{stp['profit_tp2_inr']:,.0f} • SL ≈ -₹{stp['loss_sl_inr']:,.0f}")
    if not shown:
        st.info(f"⏳ {plan.get('note') or 'No setup armed right now.'}")

    render_strategy_chart_fragment(pair, strat.id, s_levels, shown)
    st.markdown("---")
    rows = strat.level_rows(s_levels, live_price)
    if rows:
        st.markdown("#### Level Specification")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


with t_levels:
    _lv_opts = [s.name for s in strategy_registry.list_strategies()]
    lv_strategy_name = st.selectbox("🧠 Strategy", _lv_opts, key="levels_strategy_sel")
    lv_strat = strategy_registry.strategy_by_name(lv_strategy_name) or strategy_registry.get_strategy(None)
    st.subheader(f"📐 Key Levels & Predefined Setup — {selected_pair}")
    if lv_strat.id != strategy_registry.DEFAULT_STRATEGY_ID:
        render_generic_strategy_levels(lv_strat, selected_pair)
    else:
        st.caption("Derived from the completed Previous Day candle and multi-day swing extrema. The chart lives only in this tab to keep other tabs fast on mobile.")

        # ---------------- Overall market bias + predefined plan ----------------
        if levels:
            _bias = get_cached_bias(selected_pair)
            _bias_name = _bias["bias"]
            _bias_icon = "🟢" if _bias_name == "BULLISH" else ("🔴" if _bias_name == "BEARISH" else "⚪")
            _buy = calculate_trade_setup_details("BUY", levels, 0.0, margin_inr, leverage, usd_inr, pair=selected_pair)
            _sell = calculate_trade_setup_details("SELL", levels, 0.0, margin_inr, leverage, usd_inr, pair=selected_pair)

            def _plan_card(title, setup, tag):
                with st.container(border=True):
                    st.markdown(f"**{title}**")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Entry", f"${setup['entry']:,.4f}")
                    c2.metric("Structural SL", f"${setup['stop_loss']:,.4f}", f"-{setup['roe_sl']}% ROE")
                    c3.metric("TP1 (MID)", f"${setup['tp1']:,.4f}", f"+{setup['roe_tp1']}% ROE")
                    c4.metric("TP2", f"${setup['tp2']:,.4f}", f"+{setup['roe_tp2']}% ROE")
                    st.caption(f"{tag} • Margin ₹{margin_inr:,.0f} @ {leverage}x • Projected TP1 profit ≈ +₹{setup['profit_tp1_inr']:,.0f} • TP2 ≈ +₹{setup['profit_tp2_inr']:,.0f} • SL loss ≈ -₹{setup['loss_sl_inr']:,.0f}")

            st.markdown("#### 🎯 Predefined Trade Plan (Based on Daily 50 & 200 EMA Trend Bias)")
            st.markdown(f"**Overall Bias: {_bias_icon} {_bias_name}**  \n" + " • ".join(_bias["reasons"]))
            if _bias_name == "BULLISH":
                _plan_card("🟢 LONG in Buy Zone (RL → SL) or 50 EMA Support", _buy, "Primary plan (Daily > 50 & 200 EMA — Short alerts disabled)")
            elif _bias_name == "BEARISH":
                _plan_card("🔴 SHORT in Sell Zone (RH → SH) or 50 EMA Resistance", _sell, "Primary plan (Daily < 50 & 200 EMA — Long alerts disabled)")
            else:
                st.info("⚪ Neutral / Mixed EMA Bias: Daily close is between the 50 EMA and 200 EMA. Trade notifications are paused until price aligns cleanly above or below both EMAs.")

            render_chart_fragment(selected_pair, levels, is_light_theme, margin_inr, leverage, usd_inr)
            st.markdown("---")

        cur_ticker = get_cached_ticker(selected_pair)
        cur_live = cur_ticker.get("last_price", 0.0)

        def fmt(p):
            if p is None:
                return "0.00"
            return f"${p:,.4f}" if p < 1.0 else f"${p:,.2f}"

        if levels:
            k1, k2, k3, k4, k5 = st.columns(5)
            with k1:
                st.metric(
                    "Swing High (SH)",
                    fmt(levels['SH']),
                    f"+{((levels['SH'] - cur_live) / cur_live * 100):.1f}% from LTP" if cur_live > 0 else ""
                )
                st.caption("Upper Liquidity Pool Extremum")
            with k2:
                st.metric(
                    "Range High (RH / PDH)",
                    fmt(levels['RH']),
                    f"+{((levels['RH'] - cur_live) / cur_live * 100):.1f}% from LTP" if cur_live > 0 else ""
                )
                st.caption("Yesterday's Completed High")
            with k3:
                st.metric(
                    "Equilibrium Mid (MID)",
                    fmt(levels['MID']),
                    f"{((levels['MID'] - cur_live) / cur_live * 100):.1f}% from LTP" if cur_live > 0 else ""
                )
                st.caption("50% Range Mean (TP1 Target)")
            with k4:
                st.metric(
                    "Range Low (RL / PDL)",
                    fmt(levels['RL']),
                    f"{((levels['RL'] - cur_live) / cur_live * 100):.1f}% from LTP" if cur_live > 0 else ""
                )
                st.caption("Yesterday's Completed Low")
            with k5:
                st.metric(
                    "Swing Low (SL)",
                    fmt(levels['SL']),
                    f"{((levels['SL'] - cur_live) / cur_live * 100):.1f}% from LTP" if cur_live > 0 else ""
                )
                st.caption("Lower Liquidity Pool Extremum")

            st.markdown("---")
            st.markdown("#### Detailed Box Level Specification")
            levels_table = pd.DataFrame([
                {"Level Name": "Swing High (SH)", "Price": fmt(levels['SH']), "Role in Strategy": "Invalidation Stop Loss for Shorts / Upper Extreme Liquidity", "Distance from Live": f"{((levels['SH'] - cur_live)/cur_live * 100):.2f}%" if cur_live>0 else "N/A"},
                {"Level Name": "Range High (RH / PDH)", "Price": fmt(levels['RH']), "Role in Strategy": "Resistance & Sell Liquidity Sweep Trigger", "Distance from Live": f"{((levels['RH'] - cur_live)/cur_live * 100):.2f}%" if cur_live>0 else "N/A"},
                {"Level Name": "Equilibrium Midpoint (MID)", "Price": fmt(levels['MID']), "Role in Strategy": "Primary Take Profit (TP1) for both Long & Short Trades", "Distance from Live": f"{((levels['MID'] - cur_live)/cur_live * 100):.2f}%" if cur_live>0 else "N/A"},
                {"Level Name": "Range Low (RL / PDL)", "Price": fmt(levels['RL']), "Role in Strategy": "Support & Buy Liquidity Sweep Trigger", "Distance from Live": f"{((levels['RL'] - cur_live)/cur_live * 100):.2f}%" if cur_live>0 else "N/A"},
                {"Level Name": "Swing Low (SL)", "Price": fmt(levels['SL']), "Role in Strategy": "Invalidation Stop Loss for Longs / Lower Extreme Liquidity", "Distance from Live": f"{((levels['SL'] - cur_live)/cur_live * 100):.2f}%" if cur_live>0 else "N/A"},
            ])
            st.dataframe(levels_table, use_container_width=True, hide_index=True)

# ==============================================================================
# TAB 3: GOOGLE SHEET TRADE LOGGER
# ==============================================================================
with t_sheets:
    st.subheader("📋 Google Sheet Automated Trade Logger")
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")
    st.markdown(f"**Target Spreadsheet:** `{sheet_name}`")

    if os.path.exists("credentials.json"):
        st.success("`credentials.json` found in workspace.")
    else:
        st.warning("⚠️ `credentials.json` not found.")

    if st.button("Send Test Row to Google Sheets", key="btn_test_sheet_tab"):
        test_payload = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "pair": selected_pair,
            "signal": "BUY",
            "entry": levels["RL"] if levels else 2400.0,
            "stop_loss": levels["SL"] if levels else 2390.0,
            "tp1": levels["MID"] if levels else 2435.0,
            "tp2": levels["RH"] if levels else 2470.0,
            "crypto_qty": 2.08,
            "margin_inr": margin_inr,
            "leverage": leverage,
            "profit_tp1_inr": 6188.0,
            "loss_sl_inr": 1768.0
        }
        with st.spinner("Logging test record..."):
            success, msg = log_trade_to_google_sheet(test_payload, return_details=True)
            if success:
                st.success(msg)
            else:
                st.error(msg)

    with st.expander("🛠️ Google Service Account Setup Guide", expanded=False):
        st.markdown("""
        1. Create a Google Cloud project & enable **Google Sheets API** and **Google Drive API**.
        2. Create a **Service Account**, generate a JSON key, and save as `credentials.json` in this workspace.
        3. Create a Google Sheet named **`Crypto_Trades_Journal`** and share it with `client_email` as **Editor**.
        """)

# ==============================================================================
# TAB 5: MULTI-DERIVATIVE BACKTEST (max 4 derivatives)
# ==============================================================================
with t_backtest:
    st.subheader("📊 Multi-Derivative Backtest")
    _bt_names = [s.name for s in strategy_registry.list_strategies()]
    _BT_CMP = "Compare All Strategies Side-by-Side"
    bt_strategy_sel = st.selectbox("Select Strategy to Backtest", _bt_names + [_BT_CMP], key="bt_strategy_sel")
    bt_strats = (strategy_registry.list_strategies() if bt_strategy_sel == _BT_CMP
                 else [strategy_registry.strategy_by_name(bt_strategy_sel)])
    for _s in bt_strats:
        st.caption(f"**{_s.name}:** {_s.description}")
    st.caption("Up to 4 derivatives, 15m candles, CoinDCX taker fee 0.05% + 18% GST per side, 1/3 rotational margin per trade.")

    BT_OPTIONS = ["B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT", "B-BNB_USDT", "B-XRP_USDT", "B-DOGE_USDT"]
    bt_pairs = st.multiselect("Derivatives (max 4)", BT_OPTIONS, default=["B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT"],
                              max_selections=4, key="bt_multi_pairs")
    bc1, bc2, bc3 = st.columns(3)
    bt_dur_label = bc1.selectbox("Duration", ["30 Days", "60 Days", "90 Days", "180 Days", "365 Days"], index=4, key="bt_multi_dur")
    bt_capital = bc2.number_input("Starting Capital (₹)", min_value=5000, value=30000, step=5000, key="bt_multi_cap")
    bt_lev = bc3.slider("Leverage", 1, 10, 5, key="bt_multi_lev")

    bt_margin_mode = st.radio("Margin per trade", ["1/3 of capital (rotational)", "Custom margin"], horizontal=True, key="bt_multi_mm")
    if bt_margin_mode.startswith("Custom"):
        bt_margin = st.number_input("Custom margin per trade (₹)", min_value=500, value=int(bt_capital / 3), step=500, key="bt_multi_custom")
    else:
        bt_margin = bt_capital / 3.0
        st.caption(f"Margin per trade = ₹{bt_margin:,.0f}")
    if len(bt_pairs) == 4 and not bt_margin_mode.startswith("Custom"):
        st.warning("4 derivatives with 1/3 margin each can deploy up to 133% of capital if all trade at once. Treat the combined figure as an upper bound.")

    _EXIT_LABELS = {"50/50 Split": "50/50 Split (ratchet SL)", "TP1 Midpoint": "100% at TP1"}
    st.markdown("**Exit mode per derivative** (applies to every selected strategy)")
    bt_modes = {}
    mode_cols = st.columns(max(1, len(bt_pairs)))
    for col, pr in zip(mode_cols, bt_pairs):
        default_idx = 1 if pr == "B-ETH_USDT" else 0
        bt_modes[pr] = col.selectbox(pr.replace("B-", "").replace("_USDT", ""), ["50/50 Split", "TP1 Midpoint"], index=default_idx,
                                     format_func=lambda m: _EXIT_LABELS.get(m, m), key=f"bt_mode_{pr}")

    if st.button("▶️ Run Backtest", key="btn_run_multi_bt", type="primary", use_container_width=True, disabled=not bt_pairs):
        days = int(bt_dur_label.split()[0])
        details, prog = {}, st.progress(0.0, text="Starting...")
        jobs = [(s, pr) for s in bt_strats for pr in bt_pairs]
        for n, (s, pr) in enumerate(jobs):
            prog.progress(n / len(jobs), text=f"Backtesting {s.name} on {pr} ({bt_dur_label})...")
            details[f"{s.id}|{pr}"] = run_strategy_backtest(pair=pr, duration_days=days, interval="15m", margin_inr=bt_margin,
                                                            leverage=bt_lev, target_mode=bt_modes[pr], usd_inr=usd_inr,
                                                            strategy_id=s.id)
        prog.progress(1.0, text="Done")
        st.session_state.bt_multi = {"details": details, "capital": bt_capital, "duration": bt_dur_label,
                                     "modes": dict(bt_modes), "strategies": [s.id for s in bt_strats]}

    out = st.session_state.get("bt_multi")
    if out and "strategies" in out:
        rows, per_strat = [], {}
        for sid in out["strategies"]:
            s_name = strategy_registry.get_strategy(sid).name
            tot = {"trades": 0, "wins": 0, "fees": 0.0, "net": 0.0, "gp": 0.0, "gl": 0.0}
            for key, res in out["details"].items():
                k_sid, pr = key.split("|", 1)
                if k_sid != sid:
                    continue
                name = pr.replace("B-", "").replace("_USDT", "")
                if not res or res.get("error"):
                    rows.append({"Strategy": s_name, "Derivative": name, "Duration": out["duration"], "Trades": 0,
                                 "Fees Taken (₹)": None, "Win Rate %": None, "Net Profit (₹)": None, "ROI %": None,
                                 "Profit Factor": None, "Note": (res or {}).get("error", "error")})
                    continue
                n_tr, net, fees = res["total_trades"], res["net_profit_inr"], res.get("total_fees_paid_inr", 0.0)
                tot["trades"] += n_tr; tot["wins"] += res.get("win_count", 0); tot["fees"] += fees; tot["net"] += net
                tot["gp"] += res.get("total_gross_profit", 0.0); tot["gl"] += res.get("total_gross_loss", 0.0)
                rows.append({"Strategy": s_name, "Derivative": name, "Duration": out["duration"], "Trades": n_tr,
                             "Fees Taken (₹)": round(fees, 2), "Win Rate %": res["win_rate_pct"], "Net Profit (₹)": round(net, 2),
                             "ROI %": round(net / out["capital"] * 100, 2), "Profit Factor": res["profit_factor"],
                             "Note": _EXIT_LABELS.get(out["modes"].get(pr, ""), "")})
            pf = round(tot["gp"] / tot["gl"], 2) if tot["gl"] > 0 else 0.0
            wr = round(tot["wins"] / tot["trades"] * 100, 1) if tot["trades"] else 0.0
            rows.append({"Strategy": s_name, "Derivative": "🔥 COMBINED", "Duration": out["duration"], "Trades": tot["trades"],
                         "Fees Taken (₹)": round(tot["fees"], 2), "Win Rate %": wr, "Net Profit (₹)": round(tot["net"], 2),
                         "ROI %": round(tot["net"] / out["capital"] * 100, 2), "Profit Factor": pf, "Note": ""})
            per_strat[s_name] = {**tot, "pf": pf, "wr": wr}

        for s_name, tot in per_strat.items():
            st.markdown(f"**{s_name}**")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Overall Net Profit", f"{'+' if tot['net'] >= 0 else ''}₹{tot['net']:,.0f}", f"{tot['net'] / out['capital'] * 100:+.1f}% ROI")
            k2.metric("Number of Trades", tot["trades"])
            k3.metric("Fees Taken", f"₹{tot['fees']:,.0f}")
            k4.metric("Win Rate / PF", f"{tot['wr']}% / {tot['pf']}")
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        for key, res in out["details"].items():
            if res and not res.get("error") and res.get("total_trades", 0) > 0:
                k_sid, pr = key.split("|", 1)
                with st.expander(f"📅 Monthly audit — {strategy_registry.get_strategy(k_sid).name} • "
                                 f"{pr.replace('B-', '').replace('_USDT', '')} ({_EXIT_LABELS.get(out['modes'].get(pr, ''), '')})"):
                    st.dataframe(res["monthly_df"], use_container_width=True, hide_index=True)
