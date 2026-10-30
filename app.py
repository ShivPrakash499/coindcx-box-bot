from __future__ import annotations
import os
import sys
import importlib
import traceback
import threading
import time
from datetime import datetime

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
    try:
        importlib.reload(email_notifier)
        importlib.reload(signal_monitor)
    except Exception:
        pass
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
    page_title="Crypto Trade Pro Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed"
)

IST = pytz.timezone("Asia/Kolkata")

def _safe_scan_and_alert(pairs, margin_inr, leverage, usd_inr, send=True, strategy_ids=None, autotrade=False):
    """Calls signal_monitor.scan_and_alert safely even across hot-reloads on Streamlit Cloud."""
    if not signal_monitor:
        return []
    try:
        return signal_monitor.scan_and_alert(
            pairs=pairs,
            margin_inr=margin_inr,
            leverage=leverage,
            usd_inr=usd_inr,
            send=send,
            strategy_ids=strategy_ids,
            autotrade=autotrade,
        )
    except TypeError:
        try:
            importlib.reload(signal_monitor)
            return signal_monitor.scan_and_alert(
                pairs=pairs,
                margin_inr=margin_inr,
                leverage=leverage,
                usd_inr=usd_inr,
                send=send,
                strategy_ids=strategy_ids,
                autotrade=autotrade,
            )
        except TypeError:
            return signal_monitor.scan_and_alert(
                pairs, margin_inr, leverage, usd_inr, send=send, strategy_ids=strategy_ids
            )

# ----------------- 24/7 BACKGROUND SIGNAL MONITOR DAEMON (STARTS BEFORE PIN GATE) -----------------
@st.cache_resource
def _ensure_background_monitor():
    """Starts the 24/7 background monitor daemon exactly once per Streamlit server process,
    BEFORE check_authentication() so alerts and AutoTrade run 24/7 even when no browser session is logged in."""
    def _monitor_worker():
        while True:
            try:
                if signal_monitor:
                    auto_cfg = coindcx_engine.get_autotrade_config()
                    rot = coindcx_engine.get_rotational_margin_inr(leverage=10)
                    m_inr = float(auto_cfg.get("single_trade_margin_inr") or rot.get("margin_inr", 100000.0))
                    lev = int(auto_cfg.get("leverage") or int(os.getenv("LEVERAGE", 10)))
                    u_inr = float(coindcx_engine.get_coindcx_live_usdt_inr_rate())
                    watch_pairs = coindcx_engine.get_high_volatility_watchlist(top_n=12)
                    _safe_scan_and_alert(
                        pairs=watch_pairs,
                        margin_inr=m_inr,
                        leverage=lev,
                        usd_inr=u_inr,
                        send=True,
                        autotrade=bool(auto_cfg.get("enabled", False)),
                    )
            except Exception as e:
                print(f"[Crypto Trade Assistant Background Monitor Error]: {e}")
            time.sleep(60)

    th = threading.Thread(target=_monitor_worker, daemon=True, name="CryptoTradeAssistantDaemon")
    th.start()
    return True

_ensure_background_monitor()

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
        <div style="max-width: 400px; margin: 48px auto 16px auto; padding: 28px 24px; background: #0f172a; border-radius: 16px; box-shadow: 0 12px 32px rgba(0,0,0,0.25); text-align: center; border: 1px solid #1e293b; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
            <div style="font-size: 38px; margin-bottom: 8px;">⚡</div>
            <h2 style="margin: 0; color: #f8fafc; font-weight: 800; font-size: 22px; letter-spacing: -0.4px;">Crypto Trade Pro</h2>
            <div style="display: inline-block; background: rgba(59,130,246,0.15); color: #60a5fa; font-size: 11px; font-weight: 700; padding: 3px 10px; border-radius: 20px; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px;">24/7 Daemon Active</div>
            <p style="color: #94a3b8; font-size: 12.5px; margin-top: 10px; margin-bottom: 0px;">Enter your PIN to unlock execution & position controls.</p>
        </div>
        """,
        unsafe_allow_html=True
    )

    _, col_center, _ = st.columns([1, 1.4, 1])
    with col_center:
        with st.form("pin_security_form", clear_on_submit=False):
            entered_pin = st.text_input(
                "Access PIN",
                type="password",
                placeholder="Enter PIN",
                label_visibility="collapsed"
            )
            unlock_clicked = st.form_submit_button("🔓 Unlock Terminal", use_container_width=True, type="primary")
            if unlock_clicked:
                if entered_pin.strip() == required_pin:
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error("❌ Incorrect PIN.")

    st.stop()

check_authentication()

# ----------------- DATA CACHING -----------------
@st.cache_data(ttl=300)
def get_cached_box_levels(pair):
    return calculate_daily_box_levels(pair)

@st.cache_data(ttl=4)
def get_cached_ticker(pair):
    return fetch_live_ticker(pair)

@st.cache_data(ttl=15)
def get_cached_funding(pair):
    return fetch_futures_funding_rate(pair)

@st.cache_data(ttl=6)
def get_cached_balance():
    return fetch_coindcx_futures_balance()

@st.cache_data(ttl=5)
def get_cached_positions():
    return fetch_coindcx_active_positions()

@st.cache_data(ttl=15)
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
    lp = float(live_px) if strategy_registry.get_strategy(strategy_id).uses_live_price else 0.0
    return _cached_strategy_plan(strategy_id, pair, lp, m_inr, lev, u_inr)

@st.cache_data(ttl=45)
def get_cached_top_movers(watch_tuple: tuple, top_n: int = 6):
    return coindcx_engine.fetch_top_volatility_movers(list(watch_tuple), top_n=top_n)

@st.cache_data(ttl=45)
def get_cached_signals_scan(watch_tuple: tuple, m_inr: float, lev: int, u_inr: float, strat_tuple: tuple, auto_send: bool, auto_trade: bool):
    return _safe_scan_and_alert(
        list(watch_tuple), m_inr, lev, u_inr,
        send=auto_send, strategy_ids=list(strat_tuple), autotrade=auto_trade
    )

def fmt_px(p):
    if p is None:
        return "$0.00"
    p_f = float(p)
    if p_f == 0:
        return "$0.00"
    return f"${p_f:,.4f}" if abs(p_f) < 1.0 else f"${p_f:,.2f}"

def clean_sym(pair: str) -> str:
    return str(pair).replace("B-", "").replace("_USDT", "")

NAV_SECTIONS = [
    "⚡ Signals",
    "🎯 Execute",
    "📊 Positions",
    "📈 Chart & Levels",
    "🧪 Backtest",
]

# ----------------- SESSION STATE & AUTO-SYNC ACTIVE ASSET ON LOAD -----------------
if "executed_trades" not in st.session_state:
    st.session_state.executed_trades = []

if "active_position" not in st.session_state:
    st.session_state.active_position = None

if "paper_pending_orders" not in st.session_state:
    st.session_state.paper_pending_orders = []

if "realized_pnl_inr" not in st.session_state:
    st.session_state.realized_pnl_inr = 0.0

if "favorite_pairs" not in st.session_state:
    st.session_state.favorite_pairs = ["B-ETH_USDT", "B-BTC_USDT", "B-SOL_USDT", "B-INJ_USDT", "B-DOGE_USDT", "B-XRP_USDT"]

if "chart_timeframe" not in st.session_state:
    st.session_state.chart_timeframe = "15m"

if "api_error_logs" not in st.session_state:
    st.session_state.api_error_logs = []

if "last_order_status" not in st.session_state:
    st.session_state.last_order_status = None

if "active_nav_section" not in st.session_state:
    st.session_state.active_nav_section = NAV_SECTIONS[0]

def _detect_active_trade_pair() -> str | None:
    """Returns the pair of the currently active live position, App/API lock, or paper position."""
    try:
        live_pos = get_cached_positions() or []
        if live_pos:
            first_pair = live_pos[0].get("pair")
            if first_pair in GLOBAL_FUTURES_PAIRS:
                return first_pair
    except Exception:
        pass
    try:
        slot = coindcx_engine.get_active_portfolio_trade_status()
        if slot.get("is_occupied") and slot.get("active_pair") in GLOBAL_FUTURES_PAIRS:
            return slot.get("active_pair")
    except Exception:
        pass
    pos = st.session_state.get("active_position")
    if pos and pos.get("pair") in GLOBAL_FUTURES_PAIRS:
        return pos.get("pair")
    return None

# Process URL query parameters first (e.g. from trade alert email action button)
_qp = st.query_params
_url_pair = _qp.get("pair")
if _url_pair and _url_pair in GLOBAL_FUTURES_PAIRS:
    st.session_state.selected_pair = _url_pair
    st.session_state.pair_selector_widget = _url_pair
    st.session_state["_pair_auto_synced"] = True
elif "selected_pair" not in st.session_state or not st.session_state.get("_pair_auto_synced"):
    _active_trade_pair = _detect_active_trade_pair()
    _init_pair = _active_trade_pair if _active_trade_pair else "B-ETH_USDT"
    st.session_state.selected_pair = _init_pair
    st.session_state.pair_selector_widget = _init_pair
    st.session_state["_pair_auto_synced"] = True

_url_tab = _qp.get("tab", "").lower()
is_execution_link = _url_tab in ("execute", "execution", "trade")

_url_sig = str(sorted(_qp.to_dict().items())) if is_execution_link else ""
if is_execution_link and st.session_state.get("_url_applied") != _url_sig:
    st.session_state["_url_applied"] = _url_sig
    st.session_state.active_nav_section = "🎯 Execute"
    _p = st.session_state.selected_pair
    if "margin" in _qp:
        try:
            st.session_state[f"exec_margin_inr_{_p}"] = int(float(_qp["margin"]))
        except Exception:
            pass
    if "lev" in _qp:
        try:
            st.session_state[f"exec_leverage_{_p}"] = int(_qp["lev"])
        except Exception:
            pass
    _url_sid = _qp.get("strategy", strategy_registry.DEFAULT_STRATEGY_ID)
    if _url_sid not in strategy_registry.STRATEGY_REGISTRY:
        _url_sid = strategy_registry.DEFAULT_STRATEGY_ID
    st.session_state["exec_strategy_mode"] = f"{strategy_registry.get_strategy(_url_sid).name} Only"
    try:
        if "entry" in _qp and "sl" in _qp:
            _dir = str(_qp.get("direction", "LONG")).upper()
            st.session_state["url_prefill"] = {
                "pair": _p,
                "strategy_id": _url_sid,
                "direction": "BUY" if _dir in ("LONG", "BUY") else "SELL",
                "entry": float(_qp["entry"]),
                "stop_loss": float(_qp["sl"]),
                "tp1": float(_qp.get("tp1", _qp["entry"])),
                "tp2": float(_qp.get("tp2", _qp["entry"])),
            }
    except Exception:
        pass

def _switch_pair_and_nav(target_pair: str, nav_section: str | None = None, strategy_name: str | None = None):
    """Single-click callback that updates both selected_pair and dropdown widget key in sync."""
    if target_pair in GLOBAL_FUTURES_PAIRS:
        st.session_state.selected_pair = target_pair
        st.session_state.pair_selector_widget = target_pair
    if strategy_name:
        st.session_state["exec_strategy_mode"] = f"{strategy_name} Only"
    if nav_section in NAV_SECTIONS:
        st.session_state.active_nav_section = nav_section

def _on_pair_dropdown_change():
    picked = st.session_state.get("pair_selector_widget")
    if picked in GLOBAL_FUTURES_PAIRS:
        st.session_state.selected_pair = picked

def check_and_update_paper_orders():
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

        is_filled = (px <= entry_lvl) if is_buy else (px >= entry_lvl)
        if is_filled:
            ord_item["status"] = "PAPER_FILLED"
            ord_item["fill_price"] = px
            ord_item["filled_at"] = datetime.now(IST).strftime("%H:%M:%S IST")
            st.session_state.active_position = ord_item
            st.session_state.executed_trades.insert(0, ord_item)
            log_trade_to_google_sheet(ord_item, return_details=False)
            send_trade_email(
                pair=p_pair, direction=p_dir, entry=entry_lvl,
                stop_loss=ord_item.get("stop_loss", 0), tp1=ord_item.get("tp1", 0), tp2=ord_item.get("tp2", 0),
                margin_inr=ord_item.get("margin_inr", 10000), leverage=ord_item.get("leverage", 5),
                kind="EXECUTED", note=f"Resting Paper Limit order filled at ${entry_lvl:,.2f}.",
                strategy_name=ord_item.get("strategy_name", ""), strategy_id=ord_item.get("strategy_id", ""),
                trigger_reason=ord_item.get("trigger_reason", "")
            )
            st.toast(f"🎯 Paper Limit Filled: {p_dir} {clean_sym(p_pair)} @ {fmt_px(entry_lvl)}", icon="✅")
        else:
            still_pending.append(ord_item)

    st.session_state.paper_pending_orders = still_pending

check_and_update_paper_orders()

# ----------------- SIDEBAR: COMPACT PRO CONTROLS -----------------
st.sidebar.markdown("### ⚡ Pro Terminal Setup")

wallet_data = dict(get_cached_balance() or {})
_auto_cfg = coindcx_engine.get_autotrade_config()

# Allow live sync or manual override of Futures Wallet Balance (defaults to ₹40,569.80 if API is offline/expired)
_init_wallet_inr = float(wallet_data.get("total_inr", 40569.80) or 40569.80)
if _init_wallet_inr in (30000.0, 250000.0):
    _init_wallet_inr = 40569.80
wallet_data["total_inr"] = _init_wallet_inr
if float(wallet_data.get("available_inr", 0.0) or 0.0) in (0.0, 30000.0, 250000.0):
    wallet_data["available_inr"] = _init_wallet_inr

st.sidebar.metric(
    "Futures Wallet",
    f"₹{wallet_data['total_inr']:,.2f}",
    f"Free: ₹{wallet_data['available_inr']:,.2f}"
)

if not wallet_data.get("is_live_api"):
    _manual_wallet_inr = st.sidebar.number_input(
        "Sync Wallet Balance (INR)",
        min_value=500.0,
        max_value=10000000.0,
        value=float(wallet_data["total_inr"]),
        step=100.0,
        format="%.2f",
        help="Your total CoinDCX Futures Wallet balance in INR (auto-synced when CoinDCX API key is active)."
    )
    if round(_manual_wallet_inr, 2) != round(float(wallet_data["total_inr"]), 2):
        wallet_data["total_inr"] = round(_manual_wallet_inr, 2)
        wallet_data["available_inr"] = round(_manual_wallet_inr, 2)
        _auto_cfg = coindcx_engine.save_autotrade_config({"wallet_balance_inr": round(_manual_wallet_inr, 2)})
        get_cached_balance.clear()
        st.rerun()

_rot = get_rotational_margin_inr(leverage=10)
_saved_margin = float(_auto_cfg.get("single_trade_margin_inr") or 0.0)
if _saved_margin <= 0 or _saved_margin in (30000.0, 250000.0):
    default_margin = float(wallet_data["total_inr"])
else:
    default_margin = _saved_margin

margin_inr = st.sidebar.number_input(
    "Single-Trade Margin (INR)",
    min_value=500.0,
    max_value=max(float(wallet_data["total_inr"]) * 2.0, 1000000.0),
    value=float(default_margin),
    step=500.0,
    format="%.2f",
    help="50% used on Entry 1 and 50% reserved for Entry 2 @ Sweep."
)
default_lev = int(_auto_cfg.get("leverage") or int(os.getenv("LEVERAGE", 10)))
leverage = st.sidebar.slider("Leverage (x)", min_value=1, max_value=20, value=default_lev)
st.sidebar.caption(f"Split: **₹{margin_inr*0.5:,.2f}** Entry 1 + **₹{margin_inr*0.5:,.2f}** Entry 2 @ {leverage}x")

live_crypto_rate = get_coindcx_live_usdt_inr_rate()
usd_inr = float(live_crypto_rate)

st.sidebar.markdown("---")
st.sidebar.markdown("### 🤖 AutoTrade (1-Slot)")
autotrade_on = st.sidebar.toggle(
    "Enable AutoTrade (10x 2-Entry)",
    value=bool(_auto_cfg.get("enabled", False)),
    key="sidebar_autotrade_toggle",
)
if (
    autotrade_on != bool(_auto_cfg.get("enabled", False))
    or round(float(margin_inr), 2) != round(float(_auto_cfg.get("single_trade_margin_inr", 0.0)), 2)
    or int(leverage) != int(_auto_cfg.get("leverage", 10))
):
    _auto_cfg = coindcx_engine.save_autotrade_config({
        "enabled": bool(autotrade_on),
        "single_trade_margin_inr": round(float(margin_inr), 2),
        "wallet_balance_inr": round(float(wallet_data["total_inr"]), 2),
        "leverage": int(leverage),
    })

_slot_status = coindcx_engine.get_active_portfolio_trade_status()
if _slot_status.get("is_occupied"):
    _act_p = _slot_status.get("active_pair", "")
    _act_d = _slot_status.get("active_direction", "")
    st.sidebar.warning(f"🔒 **App Lock:** `{clean_sym(_act_p)}` ({_act_d})")
    if st.sidebar.button("🔓 Release App Trade Lock", key="btn_clear_autotrade_lock", use_container_width=True):
        coindcx_engine.clear_autotrade_active_lock()
        st.rerun()
else:
    st.sidebar.caption(f"🟢 **App Slot Free (0/1)** • AutoTrade: **{'ON' if autotrade_on else 'OFF'}**")

with st.sidebar.expander("⚙️ Watchlist, Theme & Tools", expanded=False):
    chart_theme = st.radio(
        "Theme",
        ["🌙 Dark Pro Terminal", "☀️ Crisp Light Theme"],
        index=0
    )
    monitor_on = st.toggle("24/7 Email Alerts", value=True, key="monitor_on")
    _strategy_names = [s.name for s in strategy_registry.list_strategies()]
    monitor_strategy_names = st.multiselect("Active Strategies", _strategy_names, default=_strategy_names, key="monitor_strategies")
    monitor_strategy_ids = [s.id for s in strategy_registry.list_strategies() if s.name in monitor_strategy_names]
    _default_watch = list(coindcx_engine.HIGH_VOL_FUTURES_UNIVERSE)
    monitor_pairs = st.multiselect(
        "High-Vol Watchlist",
        GLOBAL_FUTURES_PAIRS,
        default=[p for p in _default_watch if p in GLOBAL_FUTURES_PAIRS],
        key="monitor_pairs"
    )
    if st.button("📧 Send Test Email", key="btn_send_test_email", use_container_width=True):
        test_ticker = get_cached_ticker(st.session_state.selected_pair)
        ok, msg = send_test_trade_email(st.session_state.selected_pair, test_ticker.get("last_price", 100.0), margin_inr)
        (st.success if ok else st.error)(msg)
    if st.button("📋 Test Google Sheet Log", key="btn_test_sheet_sidebar", use_container_width=True):
        ok, msg = log_trade_to_google_sheet({
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "pair": st.session_state.selected_pair,
            "signal": "BUY", "entry": 100.0, "stop_loss": 95.0, "tp1": 105.0, "tp2": 110.0,
            "crypto_qty": 1.0, "margin_inr": margin_inr, "leverage": leverage,
            "profit_tp1_inr": 500.0, "loss_sl_inr": 500.0
        }, return_details=True)
        (st.success if ok else st.error)(msg)
    if st.button("🔒 Lock Session", use_container_width=True):
        st.session_state.authenticated = False
        st.rerun()

is_light_theme = "Light" in chart_theme

if is_light_theme:
    bg_main = "#f8fafc"
    card_bg = "#ffffff"
    card_border = "#cbd5e1"
    text_color = "#0f172a"
    subtext_color = "#475569"
    banner_bg = "#f1f5f9"
    plot_paper = "#ffffff"
    plot_bg = "#fafbfd"
    plot_grid = "#edf2f7"
    axis_font = "#334155"
    candle_up = "#089981"
    candle_down = "#f23645"
    nav_bg = "#ffffff"
    nav_active_bg = "#2563eb"
    nav_active_txt = "#ffffff"
else:
    bg_main = "#0b0f17"
    card_bg = "#111827"
    card_border = "#263244"
    text_color = "#f8fafc"
    subtext_color = "#94a3b8"
    banner_bg = "#1e293b"
    plot_paper = "#111827"
    plot_bg = "#0b0f17"
    plot_grid = "#1e293b"
    axis_font = "#94a3b8"
    candle_up = "#10b981"
    candle_down = "#ef4444"
    nav_bg = "#161f30"
    nav_active_bg = "#2563eb"
    nav_active_txt = "#ffffff"

# ----------------- RESPONSIVE CSS (DESKTOP HORIZONTAL NAV / IPHONE VERTICAL NAV) -----------------
st.markdown(f"""
<style>
    /* Global anti-horizontal-scroll enforcement */
    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {{
        overflow-x: hidden !important;
        max-width: 100vw !important;
        background-color: {bg_main};
        color: {text_color};
    }}
    .block-container {{
        padding-top: 1.4rem !important;
        padding-bottom: 2.5rem !important;
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 1420px !important;
        overflow-x: hidden !important;
    }}

    /* =========================================================================
       SECTION NAVIGATION: HORIZONTAL ON DESKTOP, VERTICAL ON MOBILE / IPHONE
       ========================================================================= */
    .st-key-active_nav_section div[role="radiogroup"] {{
        display: flex !important;
        flex-direction: row !important;
        flex-wrap: nowrap !important;
        gap: 8px !important;
        width: 100% !important;
        background: {card_bg};
        padding: 6px;
        border-radius: 12px;
        border: 1px solid {card_border};
        box-sizing: border-box;
    }}
    .st-key-active_nav_section div[role="radiogroup"] > label {{
        flex: 1 1 0% !important;
        background: {nav_bg} !important;
        border: 1px solid {card_border} !important;
        border-radius: 8px !important;
        padding: 9px 12px !important;
        margin: 0 !important;
        cursor: pointer !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.15s ease !important;
        min-height: 40px !important;
        box-sizing: border-box !important;
    }}
    /* Hide the default circular radio dot inside the main section navigator */
    .st-key-active_nav_section div[role="radiogroup"] > label > div:first-child,
    .st-key-active_nav_section div[data-baseweb="radio"] > div:first-child {{
        display: none !important;
    }}
    .st-key-active_nav_section div[role="radiogroup"] > label p {{
        font-weight: 700 !important;
        font-size: 0.9rem !important;
        color: {text_color} !important;
        margin: 0 !important;
        white-space: nowrap !important;
    }}
    .st-key-active_nav_section div[role="radiogroup"] > label:has(input:checked) {{
        background: {nav_active_bg} !important;
        border-color: {nav_active_bg} !important;
        box-shadow: 0 3px 10px rgba(37, 99, 235, 0.35) !important;
    }}
    .st-key-active_nav_section div[role="radiogroup"] > label:has(input:checked) p {{
        color: {nav_active_txt} !important;
    }}

    /* High-contrast Secondary & Primary Buttons across Desktop & Mobile */
    .stButton > button[kind="secondary"],
    .stButton > button:not([kind="primary"]) {{
        background-color: {nav_bg} !important;
        color: {text_color} !important;
        border: 1px solid {card_border} !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
    }}
    .stButton > button[kind="secondary"] p,
    .stButton > button:not([kind="primary"]) p {{
        color: {text_color} !important;
        font-weight: 700 !important;
    }}
    .stButton > button[kind="secondary"]:hover,
    .stButton > button:not([kind="primary"]):hover {{
        border-color: #3b82f6 !important;
        background-color: {banner_bg} !important;
    }}
    .stButton > button[kind="primary"] {{
        background-color: #2563eb !important;
        color: #ffffff !important;
        border: 1px solid #3b82f6 !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
    }}
    .stButton > button[kind="primary"] p {{
        color: #ffffff !important;
        font-weight: 700 !important;
    }}

    /* Pro Terminal Cards & Badges */
    .pro-card {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 10px;
        padding: 10px 14px;
        box-sizing: border-box;
        width: 100%;
    }}
    .badge-live {{
        background-color: {'#dcfce7' if is_light_theme else 'rgba(16,185,129,0.15)'};
        color: {'#15803d' if is_light_theme else '#34d399'};
        border: 1px solid {'#86efac' if is_light_theme else 'rgba(16,185,129,0.35)'};
        font-weight: 700;
        padding: 2px 8px;
        border-radius: 12px;
        font-size: 0.72rem;
        display: inline-flex;
        align-items: center;
        gap: 4px;
    }}
    .badge-funding-pos {{
        background-color: {'#ecfdf5' if is_light_theme else 'rgba(16,185,129,0.12)'};
        color: {'#059669' if is_light_theme else '#34d399'};
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 6px;
        font-size: 0.72rem;
    }}
    .badge-funding-neg {{
        background-color: {'#fff1f2' if is_light_theme else 'rgba(244,63,94,0.15)'};
        color: {'#e11d48' if is_light_theme else '#fb7185'};
        font-weight: 600;
        padding: 2px 6px;
        border-radius: 6px;
        font-size: 0.72rem;
    }}
    .badge-buy {{
        background-color: {'#dcfce7' if is_light_theme else 'rgba(16,185,129,0.18)'};
        color: {'#16a34a' if is_light_theme else '#34d399'};
        border: 1px solid {'#86efac' if is_light_theme else '#059669'};
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.82rem;
    }}
    .badge-sell {{
        background-color: {'#fee2e2' if is_light_theme else 'rgba(239,68,68,0.18)'};
        color: {'#dc2626' if is_light_theme else '#f87171'};
        border: 1px solid {'#fca5a5' if is_light_theme else '#dc2626'};
        font-weight: 700;
        padding: 3px 10px;
        border-radius: 6px;
        font-size: 0.82rem;
    }}
    /* Responsive Grid for Movers */
    .movers-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
        gap: 8px;
        width: 100%;
        margin-bottom: 10px;
    }}
    .mover-pill {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 8px;
        padding: 8px 10px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }}
    div[data-testid="stMetric"] {{
        background: {card_bg};
        border: 1px solid {card_border};
        border-radius: 8px;
        padding: 8px 10px !important;
    }}
    div[data-testid="stMetricLabel"] > div {{
        font-size: 0.76rem !important;
        color: {subtext_color} !important;
    }}
    div[data-testid="stMetricValue"] > div {{
        font-size: 1.05rem !important;
        font-weight: 700 !important;
    }}

    /* =========================================================================
       MOBILE & IPHONE AIR RESPONSIVE RULES (<= 768px)
       - Vertical Section Selector on iPhone/Mobile
       - 3-per-row Quick-Tap Asset Switcher Buttons
       ========================================================================= */
    @media only screen and (max-width: 768px) {{
        .block-container {{
            padding: 0.8rem 0.55rem 2rem 0.55rem !important;
        }}
        /* Vertical section selection on Mobile & iPhone */
        .st-key-active_nav_section div[role="radiogroup"] {{
            flex-direction: column !important;
            gap: 6px !important;
            padding: 8px !important;
        }}
        .st-key-active_nav_section div[role="radiogroup"] > label {{
            width: 100% !important;
            flex: 1 1 100% !important;
            justify-content: flex-start !important;
            padding: 11px 14px !important;
            min-height: 44px !important;
        }}
        .st-key-active_nav_section div[role="radiogroup"] > label p {{
            font-size: 0.95rem !important;
            width: 100% !important;
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
        }}
        .st-key-active_nav_section div[role="radiogroup"] > label p::after {{
            content: "›";
            font-size: 1.2rem;
            opacity: 0.75;
        }}
        /* Keep Quick-Switch Asset buttons in a compact 3-column grid on iPhone */
        .st-key-quick_asset_bar div[data-testid="stHorizontalBlock"] {{
            display: flex !important;
            flex-direction: row !important;
            flex-wrap: wrap !important;
            gap: 6px !important;
        }}
        .st-key-quick_asset_bar div[data-testid="stHorizontalBlock"] > div[data-testid="stColumn"],
        .st-key-quick_asset_bar div[data-testid="stHorizontalBlock"] > div[data-testid="column"] {{
            min-width: calc(33.33% - 6px) !important;
            flex: 1 1 calc(33.33% - 6px) !important;
        }}
        input, select, textarea {{
            font-size: 16px !important;
        }}
    }}
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 1. PROMINENT ASSET SWITCHER + LIVE PRICE & MATCHED PNL HEADER
# ==============================================================================
# Ensure dropdown widget state is always synced with st.session_state.selected_pair
if st.session_state.get("pair_selector_widget") != st.session_state.selected_pair:
    st.session_state.pair_selector_widget = st.session_state.selected_pair

selected_pair = st.session_state.selected_pair
asset_name = clean_sym(selected_pair)

# Check if any active live position or App/API lock exists
_all_live_pos = get_cached_positions() or []
_slot_info = coindcx_engine.get_active_portfolio_trade_status()
_active_pos_pairs = [p["pair"] for p in _all_live_pos if p.get("pair") in GLOBAL_FUTURES_PAIRS]
if _slot_info.get("is_occupied") and _slot_info.get("active_pair") in GLOBAL_FUTURES_PAIRS:
    if _slot_info["active_pair"] not in _active_pos_pairs:
        _active_pos_pairs.append(_slot_info["active_pair"])

# Top Quick-Switch Asset Bar (Always visible on iPhone Air & Desktop!)
with st.container(key="quick_asset_bar"):
    sw_col_drop, sw_col_btns = st.columns([1.2, 2.2])
    with sw_col_drop:
        st.selectbox(
            "🪙 Switch Crypto Asset (All 25+ Futures)",
            GLOBAL_FUTURES_PAIRS,
            format_func=lambda p: f"🪙 {clean_sym(p)} / USDT  ({'🟢 OPEN TRADE' if p in _active_pos_pairs else p})",
            key="pair_selector_widget",
            on_change=_on_pair_dropdown_change,
        )
    with sw_col_btns:
        st.markdown(
            f"<div style='font-size:0.78rem; font-weight:700; color:{subtext_color}; margin-bottom:4px;'>"
            f"⚡ 1-TAP SWITCH ASSET (Active: <b style='color:#3b82f6;'>{asset_name}/USDT</b>)</div>",
            unsafe_allow_html=True,
        )
        # Build 6 quick-switch asset buttons: prioritize any active trade coin + current coin + top favorites
        quick_coins = []
        for ap in _active_pos_pairs:
            if ap not in quick_coins:
                quick_coins.append(ap)
        for fp in ["B-ETH_USDT", "B-BTC_USDT", "B-SOL_USDT", "B-INJ_USDT", "B-DOGE_USDT", "B-XRP_USDT"]:
            if fp not in quick_coins and len(quick_coins) < 6:
                quick_coins.append(fp)
        if selected_pair not in quick_coins:
            quick_coins[-1] = selected_pair

        q_cols = st.columns(len(quick_coins))
        for idx_qc, qc_pair in enumerate(quick_coins):
            qc_sym = clean_sym(qc_pair)
            is_cur = (qc_pair == selected_pair)
            is_open_tr = (qc_pair in _active_pos_pairs)
            btn_prefix = "🟢 " if is_open_tr else ("✅ " if is_cur else "")
            q_cols[idx_qc].button(
                f"{btn_prefix}{qc_sym}",
                key=f"top_qswitch_{qc_pair}",
                on_click=_switch_pair_and_nav,
                args=(qc_pair, None, None),
                type="primary" if is_cur else "secondary",
                use_container_width=True,
            )

# Single Unified Live Header Fragment (Live Price + Selected Asset PnL side-by-side)
@st.fragment(run_every="10s")
def render_unified_live_header(pair: str):
    sym = clean_sym(pair)
    tick = get_cached_ticker(pair)
    fund = get_cached_funding(pair)
    lp = float(tick.get("last_price", 0.0))
    chg = float(tick.get("change_24h", 0.0))
    chg_col = "#10b981" if chg >= 0 else "#ef4444"
    chg_sgn = "+" if chg >= 0 else ""
    fund_badge_class = "badge-funding-pos" if fund["is_positive"] else "badge-funding-neg"

    live_positions = get_cached_positions() or []
    matching_live = next((p for p in live_positions if p["pair"] == pair), None)
    other_live = [p for p in live_positions if p["pair"] != pair]

    h_price_col, h_pnl_col = st.columns(2)
    with h_price_col:
        st.html(f"""
            <div class="pro-card">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                    <span class="badge-live">● {sym}/USDT LIVE PRICE</span>
                    <span class="{fund_badge_class}">Fund: {fund['funding_rate_str']} ({fund['countdown']})</span>
                </div>
                <div style="margin-top:4px; display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
                    <span style="font-size:1.35rem; font-weight:800; color:{text_color};">{fmt_px(lp)}</span>
                    <span style="font-size:0.88rem; font-weight:700; color:{chg_col};">{chg_sgn}{chg:.2f}% (24h)</span>
                </div>
            </div>
        """)

    with h_pnl_col:
        if matching_live:
            pnl_inr = float(matching_live["pnl_inr"])
            roe_pct = float(matching_live["roe_pct"])
            entry_p = float(matching_live["entry_price"])
            dir_str = matching_live["direction"]
            pnl_col = "#10b981" if pnl_inr >= 0 else "#ef4444"
            pnl_sgn = "+" if pnl_inr >= 0 else ""
            st.html(f"""
                <div class="pro-card" style="border-color:{pnl_col};">
                    <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                        <span style="font-weight:700; color:{pnl_col}; font-size:0.76rem;">● {sym} ACTIVE TRADE ({dir_str} {matching_live['leverage']}x)</span>
                        <span style="font-size:0.74rem; color:{subtext_color};">Entry: {fmt_px(entry_p)}</span>
                    </div>
                    <div style="margin-top:4px; display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
                        <span style="font-size:1.35rem; font-weight:800; color:{pnl_col};">{pnl_sgn}₹{pnl_inr:,.2f}</span>
                        <span style="font-size:0.88rem; font-weight:700; color:{pnl_col};">({pnl_sgn}{roe_pct:.2f}% ROE)</span>
                    </div>
                </div>
            """)
        else:
            pos = st.session_state.active_position
            if pos and pos.get("pair") == pair and lp > 0 and pos.get("status") in ("LIVE_FILLED", "PAPER_FILLED"):
                entry_p = float(pos.get("entry", 0.0))
                qty = float(pos.get("crypto_qty", 0.0))
                pos_dir = pos.get("direction") or pos.get("signal", "BUY")
                is_buy = str(pos_dir).upper() in ["BUY", "LONG"]
                u_inr = float(pos.get("usd_inr", 85.0))
                m_inr = float(pos.get("margin_inr", 100000))
                price_diff = (lp - entry_p) if is_buy else (entry_p - lp)
                pnl_usd = price_diff * qty
                pnl_inr = pnl_usd * u_inr
                roe_pct = (pnl_usd / (m_inr / u_inr)) * 100.0 if m_inr > 0 else 0.0
                pnl_col = "#10b981" if pnl_inr >= 0 else "#ef4444"
                pnl_sgn = "+" if pnl_inr >= 0 else ""
                st.html(f"""
                    <div class="pro-card" style="border-color:{pnl_col};">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                            <span style="font-weight:700; color:{pnl_col}; font-size:0.76rem;">● {sym} PAPER ({pos_dir})</span>
                            <span style="font-size:0.74rem; color:{subtext_color};">Entry: {fmt_px(entry_p)}</span>
                        </div>
                        <div style="margin-top:4px; display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
                            <span style="font-size:1.35rem; font-weight:800; color:{pnl_col};">{pnl_sgn}₹{pnl_inr:,.2f}</span>
                            <span style="font-size:0.88rem; font-weight:700; color:{pnl_col};">({pnl_sgn}{roe_pct:.2f}% ROE)</span>
                        </div>
                    </div>
                """)
            else:
                other_note = (
                    f"Active on {clean_sym(other_live[0]['pair'])}: {'+' if other_live[0]['pnl_inr'] >= 0 else ''}₹{other_live[0]['pnl_inr']:,.2f}"
                    if other_live
                    else f"Wallet: ₹{wallet_data['total_inr']:,.2f} • AutoTrade: {'ON 🚀' if autotrade_on else 'OFF'}"
                )
                st.html(f"""
                    <div class="pro-card">
                        <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:4px;">
                            <span style="font-weight:700; color:{subtext_color}; font-size:0.76rem;">● {sym}/USDT POSITION</span>
                            <span style="font-size:0.74rem; color:{subtext_color};">{other_note}</span>
                        </div>
                        <div style="margin-top:4px; display:flex; align-items:baseline; gap:8px; flex-wrap:wrap;">
                            <span style="font-size:1.25rem; font-weight:800; color:{subtext_color};">FLAT (No {sym} Position)</span>
                        </div>
                    </div>
                """)

render_unified_live_header(selected_pair)

levels = get_cached_box_levels(selected_pair)
ticker = get_cached_ticker(selected_pair)
live_price = float(ticker.get("last_price", 0.0))

# ==============================================================================
# 2. RESPONSIVE SECTION SELECTOR (VERTICAL ON MOBILE/IPHONE, HORIZONTAL ON DESKTOP)
# ==============================================================================
if st.session_state.get("active_nav_section") not in NAV_SECTIONS:
    st.session_state.active_nav_section = NAV_SECTIONS[0]

active_section = st.radio(
    "Navigate Section",
    NAV_SECTIONS,
    horizontal=True,
    label_visibility="collapsed",
    key="active_nav_section",
)

# ==============================================================================
# SECTION 1: HIGH-VOLATILITY SIGNALS & WATCHLIST MATRIX
# ==============================================================================
if active_section == "⚡ Signals":
    if not monitor_pairs or not monitor_strategy_ids:
        st.info("Select at least one derivative and strategy in the sidebar settings.")
    else:
        hdr_s1, hdr_s2 = st.columns([3.2, 1.0])
        with hdr_s1:
            slot_now = coindcx_engine.get_active_portfolio_trade_status()
            if slot_now.get("is_occupied"):
                st.warning(
                    f"🔒 **App/API Trade Lock Active:** `{clean_sym(slot_now.get('active_pair'))}` ({slot_now.get('active_direction')}) • "
                    f"50% margin reserved for Entry 2 @ Sweep."
                )
            else:
                st.caption(
                    f"🟢 **App Slot Free (0/1)** • Wallet: **₹{wallet_data['total_inr']:,.2f}** • Single-Trade Margin: **₹{margin_inr:,.2f}** (`{leverage}x`) • "
                    f"AutoTrade: **{'ON 🚀' if autotrade_on else 'OFF'}**"
                )
        with hdr_s2:
            if st.button("🔄 Scan Now", key="btn_force_rescan_signals", use_container_width=True):
                get_cached_top_movers.clear()
                get_cached_signals_scan.clear()
                st.rerun()

        # Top 6 High-Volatility Movers Grid
        top_movers = get_cached_top_movers(tuple(monitor_pairs), top_n=min(6, len(monitor_pairs)))
        if top_movers:
            cards_html = []
            for idx_m, mv in enumerate(top_movers):
                chg_c = "#10b981" if mv["change_24h_pct"] >= 0 else "#ef4444"
                cards_html.append(
                    f"<div class='mover-pill'>"
                    f"<div style='display:flex;justify-content:space-between;font-size:0.75rem;color:{subtext_color};font-weight:700;'>"
                    f"<span>#{idx_m+1} {mv['symbol']}</span><span style='color:{chg_c};'>{mv['change_24h_pct']:+.1f}%</span></div>"
                    f"<div style='font-size:0.98rem;font-weight:800;color:{text_color};margin:2px 0;'>{fmt_px(mv['last_price'])}</div>"
                    f"<div style='font-size:0.72rem;color:#3b82f6;font-weight:700;'>24h Range: {mv['range_24h_pct']:.1f}%</div>"
                    f"</div>"
                )
            st.html(f"<div class='movers-grid'>{''.join(cards_html)}</div>")

        results = get_cached_signals_scan(
            tuple(monitor_pairs), float(margin_inr), int(leverage), float(usd_inr),
            tuple(monitor_strategy_ids), bool(monitor_on), bool(autotrade_on)
        )
        active_signals = [r for r in results if r.get("signal") and r["signal"].get("signal") not in (None, "NEUTRAL")]

        if active_signals:
            st.markdown(f"#### 🔥 Active Confirmed Signals ({len(active_signals)})")
            for r in active_signals:
                pair_r = r["pair"]
                name_r = clean_sym(pair_r)
                sig = r["signal"]
                is_l = sig["signal"] == "LONG"
                badge = "badge-buy" if is_l else "badge-sell"
                with st.container(border=True):
                    st.markdown(
                        f"<span class='{badge}'>{sig['signal']} {name_r}/USDT</span> &nbsp; "
                        f"**{r['strategy_name']}** • {sig.get('trigger_reason') or sig.get('trigger_zone') or ''}",
                        unsafe_allow_html=True
                    )
                    m1, m2, m3, m4, m5 = st.columns(5)
                    m1.metric("Entry 1 (50%)", fmt_px(sig["entry"]))
                    m2.metric("Entry 2 @ Sweep", fmt_px(sig.get("entry2_sweep", sig["entry"])))
                    m3.metric("TP1 (50% -> BE)", fmt_px(sig["tp1"]), f"+{sig['roe_tp1']}% ROE")
                    m4.metric("TP2 (50% Runner)", fmt_px(sig["tp2"]), f"+{sig['roe_tp2']}% ROE")
                    m5.metric("Catastrophe SL", fmt_px(sig["stop_loss"]), f"-{sig['roe_sl']}% ROE")

                    b1, b2 = st.columns(2)
                    b1.button(
                        f"🎯 Load {name_r} into Execute",
                        key=f"btn_load_sig_{r['strategy_id']}_{pair_r}",
                        use_container_width=True,
                        on_click=_switch_pair_and_nav,
                        args=(pair_r, "🎯 Execute", r["strategy_name"]),
                    )
                    if b2.button(
                        f"🤖 Auto-Execute {name_r} (₹{margin_inr:,.0f} @ {leverage}x)",
                        key=f"btn_auto_exec_{r['strategy_id']}_{pair_r}",
                        type="primary",
                        use_container_width=True,
                    ):
                        ok_a, msg_a, _ = coindcx_engine.execute_autotrade_two_entry_signal(
                            pair=pair_r, sig=sig, single_trade_margin_inr=margin_inr, leverage=leverage, usd_inr=usd_inr
                        )
                        (st.success if ok_a else st.error)(msg_a)

        st.markdown("#### 📡 High-Volatility Watchlist Matrix")
        matrix_rows = []
        for pair_w in monitor_pairs:
            sym_w = clean_sym(pair_w)
            lv = get_cached_box_levels(pair_w)
            px = float(get_cached_ticker(pair_w).get("last_price", 0.0))
            pair_res = [r for r in results if r["pair"] == pair_w]
            active_r = next((r for r in pair_res if r.get("signal") and r["signal"].get("signal") not in (None, "NEUTRAL")), None)

            if lv and px > 0:
                if px >= lv["RH"]:
                    zone = "🔴 Sell Zone" if px <= lv["SH"] else "🔴 Above SH"
                elif px <= lv["RL"]:
                    zone = "🟢 Buy Zone" if px >= lv["SL"] else "🟢 Below SL"
                else:
                    zone = "⚪ Mid-Range"
                tb = lv.get("trend_bias", "RANGE")
                bias_lbl = "🟢 BULL" if tb == "BULLISH" else ("🔴 BEAR" if tb == "BEARISH" else "🟡 RANGE")
                sh_s, rh_s, mid_s, rl_s, sl_s = fmt_px(lv["SH"]), fmt_px(lv["RH"]), fmt_px(lv["MID"]), fmt_px(lv["RL"]), fmt_px(lv["SL"])
            else:
                zone, bias_lbl = "—", "—"
                sh_s = rh_s = mid_s = rl_s = sl_s = "—"

            sig_status = f"🔥 {active_r['signal']['signal']}" if active_r else "⏳ Watching"
            matrix_rows.append({
                "Asset": sym_w,
                "Price": fmt_px(px),
                "Bias": bias_lbl,
                "Zone": zone,
                "Status": sig_status,
                "SH": sh_s,
                "RH": rh_s,
                "MID": mid_s,
                "RL": rl_s,
                "SL": sl_s,
            })

        if matrix_rows:
            st.dataframe(pd.DataFrame(matrix_rows), use_container_width=True, hide_index=True)

# ==============================================================================
# SECTION 2: STREAMLINED ORDER EXECUTION STATION
# ==============================================================================
elif active_section == "🎯 Execute":
    cur_asset = clean_sym(selected_pair)
    cur_price = live_price
    wallet = get_cached_balance()
    live_positions = get_cached_positions() or []

    if st.session_state.last_order_status:
        los = st.session_state.last_order_status
        c_b, c_d = st.columns([0.92, 0.08])
        with c_b:
            msg_txt = f"**[{los.get('timestamp', '')}] ({clean_sym(los.get('pair', ''))}):** {los.get('msg', '')}"
            if los.get("type") == "error":
                st.error(msg_txt)
            elif los.get("type") == "success":
                st.success(msg_txt)
            else:
                st.info(msg_txt)
        with c_d:
            if st.button("✕", key="btn_dismiss_banner"):
                st.session_state.last_order_status = None
                st.rerun()

    exec_left, exec_right = st.columns([1.05, 1.05])

    with exec_left:
        st.markdown(f"#### 🎛️ Order Setup — {cur_asset}/USDT")
        avail_margin_int = max(1000, int(wallet["available_inr"]))
        margin_key = f"exec_margin_inr_{selected_pair}"
        if margin_key not in st.session_state:
            st.session_state[margin_key] = int(margin_inr)

        m_col1, m_col2 = st.columns(2)
        with m_col1:
            trade_margin_inr = st.number_input(
                "Total Trade Margin (INR)",
                min_value=500,
                max_value=max(avail_margin_int, 1000000),
                step=1000,
                key=margin_key
            )
        with m_col2:
            matching_active_pos = next((p for p in live_positions if p["pair"] == selected_pair), None)
            active_pos_leverage = int(round(float(matching_active_pos["leverage"]))) if matching_active_pos else None
            default_slider_leverage = active_pos_leverage if active_pos_leverage else int(leverage)
            trade_leverage = st.slider(
                "Leverage (x)",
                min_value=1,
                max_value=20,
                value=default_slider_leverage,
                key=f"exec_leverage_{selected_pair}"
            )

        trade_usd_inr = float(usd_inr)

        _all_label = "All Strategies (Auto-Detect)"
        _mode_opts = [_all_label] + [f"{s.name} Only" for s in strategy_registry.list_strategies()]
        if st.session_state.get("exec_strategy_mode") not in _mode_opts:
            st.session_state["exec_strategy_mode"] = _mode_opts[0]
        exec_strategy_mode = st.selectbox("Strategy", _mode_opts, key="exec_strategy_mode", label_visibility="collapsed")
        armed_strats = (
            strategy_registry.list_strategies()
            if exec_strategy_mode == _all_label
            else [s for s in strategy_registry.list_strategies() if f"{s.name} Only" == exec_strategy_mode]
        )

        choices = []
        _pref = st.session_state.get("url_prefill")
        if _pref and _pref.get("pair") == selected_pair:
            _ps = strategy_registry.get_strategy(_pref["strategy_id"])
            if _ps.id in [s.id for s in armed_strats]:
                _pm = strategy_registry.position_metrics(
                    selected_pair, _pref["entry"], _pref["stop_loss"], _pref["tp1"], _pref["tp2"],
                    trade_margin_inr, trade_leverage, trade_usd_inr
                )
                _pset = {
                    "direction": _pref["direction"], "setup": f"{_ps.name}: Alert Ticket",
                    "entry": _pref["entry"], "stop_loss": _pref["stop_loss"],
                    "tp1": _pref["tp1"], "tp2": _pref["tp2"], **_pm,
                    "strategy_id": _ps.id, "strategy_name": _ps.name, "trigger_reason": "Email Alert Link"
                }
                choices.append((f"📧 Alert {_pref['direction']} ({fmt_px(_pref['entry'])})", _pset, strategy_registry.setup_tag(_ps.id, "EMAIL"), _ps))

        for _s in armed_strats:
            _sig = get_cached_strategy_signal(_s.id, selected_pair, trade_margin_inr, trade_leverage, trade_usd_inr)
            _sig_live = bool(_sig and _sig.get("signal") in ("LONG", "SHORT"))
            if _sig_live:
                _sd = "BUY" if _sig["signal"] == "LONG" else "SELL"
                choices.append((
                    f"⚡ LIVE {_sig['signal']} ({fmt_px(_sig['entry'])})",
                    {**_sig, "direction": _sd},
                    strategy_registry.setup_tag(_s.id, "SIGNAL"),
                    _s
                ))
            _plan = get_cached_strategy_plan(_s.id, selected_pair, float(cur_price), trade_margin_inr, trade_leverage, trade_usd_inr)
            for _d, _ico in (("BUY", "🟢"), ("SELL", "🔴")):
                _st = _plan.get(_d)
                if not _st or _st.get("signal_kind"):
                    continue
                choices.append((
                    f"{_ico} {_d} Plan ({fmt_px(_st['entry'])})",
                    _st,
                    strategy_registry.setup_tag(_s.id, _d),
                    _s
                ))

        if choices:
            _labels = [c[0] for c in choices]
            _def = next(
                (i for i, c in enumerate(choices) if c[2].endswith("EMAIL")),
                next((i for i, c in enumerate(choices) if c[2].endswith("SIGNAL")), 0)
            )
            trade_choice = st.radio("Select Ticket", _labels, index=_def, horizontal=True, key=f"trade_choice_exec_{selected_pair}_{exec_strategy_mode}")
            _, active_trade, setup_tag, active_strategy = choices[_labels.index(trade_choice)]
            trade_dir = "BUY" if str(active_trade.get("direction", "BUY")).upper() in ("BUY", "LONG") else "SELL"
            color_class = "badge-buy" if trade_dir == "BUY" else "badge-sell"

            entry_key = f"custom_entry_{selected_pair}_{setup_tag}"
            sl_key = f"custom_sl_{selected_pair}_{setup_tag}"
            tp1_key = f"custom_tp1_{selected_pair}_{setup_tag}"
            tp2_key = f"custom_tp2_{selected_pair}_{setup_tag}"
            choice_tracker_key = f"last_setup_tag_{selected_pair}"
            levels_tracker_key = f"last_formula_entry_{selected_pair}_{setup_tag}"

            if st.session_state.get(choice_tracker_key) != setup_tag or st.session_state.get(levels_tracker_key) != float(active_trade["entry"]):
                st.session_state[choice_tracker_key] = setup_tag
                st.session_state[levels_tracker_key] = float(active_trade["entry"])
                st.session_state[entry_key] = float(active_trade["entry"])
                st.session_state[sl_key] = float(active_trade["stop_loss"])
                st.session_state[tp1_key] = float(active_trade["tp1"])
                st.session_state[tp2_key] = float(active_trade["tp2"])

            p_ref = float(active_trade["entry"])
            step_val = 0.5 if p_ref > 1.0 else (0.0001 if p_ref > 0.001 else 0.000001)
            fmt_str = "%.2f" if p_ref > 1.0 else ("%.4f" if p_ref > 0.001 else "%.6f")

            adj_col1, adj_col2 = st.columns(2)
            with adj_col1:
                custom_entry = st.number_input("Entry 1 ($)", value=float(st.session_state.get(entry_key, active_trade["entry"])), step=step_val, format=fmt_str, key=entry_key)
                custom_sl = st.number_input("Catastrophe SL ($)", value=float(st.session_state.get(sl_key, active_trade["stop_loss"])), step=step_val, format=fmt_str, key=sl_key)
            with adj_col2:
                custom_tp1 = st.number_input("TP1 (50% Book -> BE) ($)", value=float(st.session_state.get(tp1_key, active_trade["tp1"])), step=step_val, format=fmt_str, key=tp1_key)
                custom_tp2 = st.number_input("TP2 (50% Runner) ($)", value=float(st.session_state.get(tp2_key, active_trade["tp2"])), step=step_val, format=fmt_str, key=tp2_key)

            pos_usd = (trade_margin_inr * trade_leverage) / trade_usd_inr
            c_qty = format_order_quantity(selected_pair, pos_usd / custom_entry) if custom_entry > 0 else 0
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
                "entry": custom_entry, "stop_loss": custom_sl, "tp1": custom_tp1, "tp2": custom_tp2,
                "crypto_qty": c_qty, "roe_tp1": c_roe_tp1, "roe_tp2": c_roe_tp2, "roe_sl": c_roe_sl,
                "profit_tp1_inr": c_profit_tp1_inr, "profit_tp2_inr": c_profit_tp2_inr, "loss_sl_inr": c_loss_sl_inr
            }
            cost_details = calculate_trade_costs_and_safe_tp(
                direction=trade_dir, entry_price=active_trade["entry"],
                margin_inr=trade_margin_inr, leverage=trade_leverage, usd_inr=trade_usd_inr
            )
        else:
            active_trade = None
            cost_details = None
            st.info("No setup available for this pair right now.")

    with exec_right:
        if active_trade:
            st.markdown("#### 🎫 2-Entry + 50/50 Runner Ticket")
            _e2_lvl = active_trade.get("entry2_sweep") or (
                (levels["SL"] if trade_dir == "BUY" else levels["SH"]) if levels else active_trade["entry"]
            )
            _avg_2x = (active_trade["entry"] + float(_e2_lvl)) / 2.0
            _tranche_m = trade_margin_inr * 0.5
            _tranche_q = format_order_quantity(selected_pair, active_trade["crypto_qty"] * 0.5)
            _blended_profit = 0.5 * active_trade["profit_tp1_inr"] + 0.5 * active_trade["profit_tp2_inr"]
            _blended_roe = round(0.5 * active_trade["roe_tp1"] + 0.5 * active_trade["roe_tp2"], 2)
            _fee_inr = cost_details["total_cost_inr"] if cost_details else 0.0
            _be_px = cost_details["breakeven_price"] if cost_details else active_trade["entry"]

            st.html(f"""
            <div class="pro-card" style="padding:14px;">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:6px;">
                    <span class="{color_class}">{trade_dir} {cur_asset}/USDT ({trade_leverage}x)</span>
                    <span style="font-weight:700; color:{text_color}; font-size:0.95rem;">Live: {fmt_px(cur_price)}</span>
                </div>
                <div style="display:grid; grid-template-columns:1fr auto; row-gap:6px; font-size:0.86rem; color:{text_color};">
                    <span style="color:{subtext_color};">Entry 1 (50% Zone):</span>
                    <span style="text-align:right; font-weight:700;">{fmt_px(active_trade['entry'])} (₹{_tranche_m:,.0f} / {_tranche_q} {cur_asset})</span>

                    <span style="color:{subtext_color};">Entry 2 (50% @ {'SL' if trade_dir == 'BUY' else 'SH'} Sweep):</span>
                    <span style="text-align:right; color:#8b5cf6; font-weight:700;">{fmt_px(_e2_lvl)} (Avg: {fmt_px(_avg_2x)})</span>

                    <span style="color:{subtext_color};">TP1 (50% Book -> SL to BE):</span>
                    <span style="text-align:right; color:#38bdf8; font-weight:700;">{fmt_px(active_trade['tp1'])} (+{active_trade['roe_tp1']}% ROE)</span>

                    <span style="color:{subtext_color};">TP2 (50% Runner):</span>
                    <span style="text-align:right; color:#10b981; font-weight:700;">{fmt_px(active_trade['tp2'])} (+{active_trade['roe_tp2']}% ROE)</span>

                    <span style="color:{subtext_color};">Catastrophe Stop Loss:</span>
                    <span style="text-align:right; color:#ef4444; font-weight:700;">{fmt_px(active_trade['stop_loss'])} (-{active_trade['roe_sl']}%)</span>

                    <span style="color:{subtext_color};">Est. Fee (incl. GST) / Breakeven:</span>
                    <span style="text-align:right; color:{subtext_color}; font-weight:600;">₹{_fee_inr:,.0f} • BE {fmt_px(_be_px)}</span>
                </div>
                <div style="margin-top:10px; padding-top:8px; border-top:1px solid {card_border}; display:flex; justify-content:space-between; align-items:center;">
                    <span style="font-size:0.85rem; font-weight:700; color:{subtext_color};">Projected Runner Profit:</span>
                    <span style="font-size:1.05rem; font-weight:800; color:#10b981;">+₹{_blended_profit:,.0f} (+{_blended_roe}% ROE)</span>
                </div>
            </div>
            """)

            trade_notional_inr = active_trade["crypto_qty"] * active_trade["entry"] * trade_usd_inr
            is_below_min_val = trade_notional_inr < 2448.0
            if is_below_min_val:
                st.warning(f"⚠️ Notional (₹{trade_notional_inr:,.0f}) is below CoinDCX ₹2,448 minimum.")

            ctl1, ctl2 = st.columns([1.3, 1])
            with ctl1:
                exec_mode = st.radio(
                    "Target",
                    ["⚡ Live CoinDCX Order", "📝 Paper Trade"],
                    index=0 if wallet["is_live_api"] else 1,
                    horizontal=True,
                    key=f"exec_mode_choice_{selected_pair}",
                    label_visibility="collapsed"
                )
            with ctl2:
                price_shield_pct = st.number_input(
                    "Max Slippage %",
                    min_value=0.05, max_value=2.0, value=0.25, step=0.05,
                    key=f"price_shield_{selected_pair}"
                )

            btn_label = f"🚀 EXECUTE {trade_dir} {cur_asset} ({'LIVE' if 'Live' in exec_mode else 'PAPER'})"
            if st.button(btn_label, key=f"btn_exec_{selected_pair}", type="primary", use_container_width=True):
                exec_time = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
                live_api_msg = ""
                order_placed_ok = True

                shield_blocked, shield_live_px, shield_dev = False, 0.0, 0.0
                if "Live" in exec_mode and wallet["is_live_api"]:
                    shield_live_px = float(fetch_live_ticker(selected_pair).get("last_price", 0.0) or 0.0)
                    _ent = float(active_trade["entry"])
                    shield_dev = abs(shield_live_px - _ent) / _ent * 100.0 if (_ent > 0 and shield_live_px > 0) else 999.0
                    shield_blocked = shield_dev > price_shield_pct

                if "Live" in exec_mode:
                    if not wallet["is_live_api"]:
                        st.error("❌ CoinDCX API credentials not configured in .env.")
                        order_placed_ok = False
                    elif is_below_min_val:
                        st.error(f"❌ Order value (₹{trade_notional_inr:,.0f}) is below CoinDCX minimum ₹2,448.")
                        order_placed_ok = False
                    elif shield_blocked:
                        st.error(f"🛡️ Price Shield blocked order: Live {fmt_px(shield_live_px)} is {shield_dev:.2f}% from entry {fmt_px(active_trade['entry'])}.")
                        order_placed_ok = False
                    else:
                        _maker_px = round_asset_price(
                            min(float(active_trade["entry"]), shield_live_px) if trade_dir == "BUY" else max(float(active_trade["entry"]), shield_live_px),
                            float(active_trade["entry"])
                        )
                        with st.spinner("Submitting Limit Maker order to CoinDCX..."):
                            ok, api_msg, api_extra = place_coindcx_futures_order(
                                pair=selected_pair, side=trade_dir, quantity=active_trade["crypto_qty"],
                                leverage=trade_leverage, order_type="limit_order", price=_maker_px,
                                post_only=True, margin_currency="INR",
                                tp_price=active_trade["tp1"], sl_price=active_trade["stop_loss"]
                            )
                            order_placed_ok = ok
                            live_api_msg = api_msg
                            st.session_state.api_error_logs.insert(0, {
                                "timestamp": exec_time, "pair": selected_pair, "action": f"LIVE_{trade_dir}",
                                "status": "SUCCESS" if ok else "ERROR", "message": api_msg,
                                "details": api_extra or {}
                            })
                            if not ok:
                                st.error(f"❌ CoinDCX Execution Failed: {api_msg}")

                if order_placed_ok:
                    is_live = "Live" in exec_mode
                    cur_market_px = float(get_cached_ticker(selected_pair).get("last_price", 0.0))
                    is_buy_dir = (trade_dir == "BUY")
                    limit_entry_px = float(active_trade["entry"])
                    already_reached = (cur_market_px <= limit_entry_px) if is_buy_dir else (cur_market_px >= limit_entry_px) if cur_market_px > 0 else True
                    order_status = "LIVE_FILLED" if is_live else ("PAPER_FILLED" if already_reached else "PAPER_PENDING")

                    coindcx_engine.register_app_trade_lock(
                        pair=selected_pair, direction=trade_dir, entry=limit_entry_px,
                        stop_loss=active_trade["stop_loss"], tp1=active_trade["tp1"], tp2=active_trade["tp2"],
                        entry2_sweep=active_trade.get("entry2_sweep", limit_entry_px),
                        margin_inr=trade_margin_inr, leverage=trade_leverage, qty1=active_trade["crypto_qty"],
                        mode="App/API Live Execution" if is_live else "App/API Paper Execution",
                        is_live_exchange=is_live,
                    )

                    order_record = {
                        "timestamp": exec_time, "pair": selected_pair, "signal": trade_dir, "direction": trade_dir,
                        "setup": active_trade.get("setup", "Box Setup"), "entry": limit_entry_px,
                        "stop_loss": active_trade["stop_loss"], "tp1": active_trade["tp1"], "tp2": active_trade["tp2"],
                        "crypto_qty": active_trade["crypto_qty"], "margin_inr": trade_margin_inr,
                        "leverage": trade_leverage, "usd_inr": trade_usd_inr,
                        "profit_tp1_inr": active_trade["profit_tp1_inr"], "loss_sl_inr": active_trade["loss_sl_inr"],
                        "status": order_status, "strategy_id": active_strategy.id,
                        "strategy_name": active_strategy.name, "trigger_reason": active_trade.get("trigger_reason", "")
                    }

                    if is_live or already_reached:
                        st.session_state.active_position = order_record
                        st.session_state.executed_trades.insert(0, order_record)
                        log_trade_to_google_sheet(order_record, return_details=True)
                        send_trade_email(
                            pair=selected_pair, direction=trade_dir, entry=limit_entry_px, stop_loss=active_trade["stop_loss"],
                            tp1=active_trade["tp1"], tp2=active_trade["tp2"], margin_inr=trade_margin_inr,
                            leverage=trade_leverage, kind="EXECUTED",
                            note="Live order submitted." if is_live else "Paper order filled.",
                            strategy_name=active_strategy.name, strategy_id=active_strategy.id,
                            trigger_reason=active_trade.get("trigger_reason", "")
                        )
                        msg_out = f"✅ {trade_dir} {active_trade['crypto_qty']} {cur_asset} @ {fmt_px(limit_entry_px)} ({live_api_msg or 'Filled'})"
                    else:
                        st.session_state.setdefault("paper_pending_orders", []).insert(0, order_record)
                        msg_out = f"⏳ Resting Paper Limit {trade_dir} {cur_asset} @ {fmt_px(limit_entry_px)} queued."

                    st.session_state.setdefault("trade_plans", {})[selected_pair] = {
                        "direction": "LONG" if trade_dir == "BUY" else "SHORT", "entry": limit_entry_px,
                        "sl": active_trade["stop_loss"], "tp1": active_trade["tp1"], "tp2": active_trade["tp2"],
                        "applied": False, "margin_inr": trade_margin_inr, "leverage": trade_leverage
                    }
                    st.session_state.last_order_status = {
                        "type": "success" if (is_live or already_reached) else "info",
                        "msg": msg_out, "timestamp": exec_time, "pair": selected_pair
                    }
                    st.rerun()

    if st.session_state.executed_trades or st.session_state.api_error_logs:
        with st.expander(f"📜 Session Orders ({len(st.session_state.executed_trades)}) & API Logs ({len(st.session_state.api_error_logs)})", expanded=False):
            if st.session_state.executed_trades:
                st.dataframe(pd.DataFrame([
                    {
                        "Time": t["timestamp"].split()[1], "Asset": clean_sym(t.get("pair", selected_pair)),
                        "Side": t["signal"], "Entry": fmt_px(t["entry"]), "TP1": fmt_px(t["tp1"]),
                        "SL": fmt_px(t["stop_loss"]), "Margin": f"₹{t.get('margin_inr', 0):,.0f}"
                    }
                    for t in st.session_state.executed_trades[:8]
                ]), use_container_width=True, hide_index=True)
            if st.session_state.api_error_logs:
                for entry in st.session_state.api_error_logs[:5]:
                    st.caption(f"`{entry.get('timestamp')}` • **{entry.get('status')}** ({entry.get('pair')}): {entry.get('message')}")

# ==============================================================================
# SECTION 3: LIVE POSITIONS & ORDER MANAGER
# ==============================================================================
elif active_section == "📊 Positions":
    def _lt_finish_close(pos, pnl_inr, reason_label):
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
            stop_loss=float(plan.get("sl") or pos.get("stop_loss") or 0),
            tp1=float(plan.get("tp1") or pos.get("take_profit") or 0),
            tp2=float(plan.get("tp2") or 0), margin_inr=float(pos.get("locked_margin_inr", 0)),
            leverage=int(pos.get("leverage", 10) or 10),
            kind="CLOSED", note=f"Closed at ~{fmt_px(pos['mark_price'])} | Final PnL: {'+' if pnl_inr >= 0 else ''}₹{pnl_inr:,.2f}"
        )

    check_and_update_paper_orders()
    live_positions = get_cached_positions() or []
    paper = st.session_state.active_position
    plans = st.session_state.get("trade_plans", {})
    pending_paper = st.session_state.get("paper_pending_orders", [])

    total_margin = sum(float(p.get("locked_margin_inr", 0) or 0) for p in live_positions)
    total_unreal = sum(float(p.get("pnl_inr", 0) or 0) for p in live_positions)
    unreal_pct = (total_unreal / total_margin * 100.0) if total_margin > 0 else 0.0
    realized = st.session_state.realized_pnl_inr
    n_open = len(live_positions) + (1 if paper else 0)

    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Open Positions", n_open)
    s2.metric("Margin Deployed", f"₹{total_margin:,.0f}")
    s3.metric("Unrealized PnL", f"{'+' if total_unreal >= 0 else ''}₹{total_unreal:,.2f}", f"{unreal_pct:+.2f}%")
    s4.metric("Session Realized", f"{'+' if realized >= 0 else ''}₹{realized:,.2f}")

    if live_positions and st.button("🚨 Emergency Close All Positions", key="lt_close_all", type="primary", use_container_width=True):
        snapshot = list(live_positions)
        with st.spinner("Closing all positions on CoinDCX..."):
            closed, total, msg = exit_all_coindcx_positions()
        if closed:
            for pos in snapshot:
                _lt_finish_close(pos, float(pos.get("pnl_inr", 0) or 0), "Manual Close All")
            coindcx_engine.clear_autotrade_active_lock()
        st.session_state.last_order_status = {"type": "success" if closed == total else "error", "msg": msg, "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"), "pair": "ALL"}
        st.rerun()

    if not live_positions and not paper and not pending_paper:
        st.info("No open positions or resting paper orders right now.")

    for p in live_positions:
        pid, pr = p["id"], p["pair"]
        sym_p = clean_sym(pr)
        is_long = p["direction"] == "LONG"
        entry_p, mark_p = float(p["entry_price"]), float(p["mark_price"])
        plan = plans.get(pr, {})
        cur_sl, cur_tp = p.get("stop_loss"), p.get("take_profit")
        tp1 = float(plan.get("tp1") or cur_tp or 0)
        tp2 = float(plan.get("tp2") or 0)

        if plan and not plan.get("applied") and not cur_sl:
            ok, m = update_coindcx_position_tpsl(pid, plan.get("tp1"), plan.get("sl"), pair=pr)
            plan["applied"] = True
            cur_sl, cur_tp = plan.get("sl"), plan.get("tp1")

        ratchet, target_sl = "⏳ Waiting for TP1", None
        if tp1 and tp2:
            half = (tp1 + tp2) / 2.0
            reached = (lambda lvl: mark_p >= lvl) if is_long else (lambda lvl: mark_p <= lvl)
            if reached(half):
                ratchet, target_sl = "🔒 ≥50% to TP2: Ratchet SL to TP1", tp1
            elif reached(tp1):
                ratchet, target_sl = "✅ TP1 reached: Move SL to Breakeven", entry_p

        pnl_inr, roe = float(p["pnl_inr"]), float(p["roe_pct"])
        col = "#10b981" if pnl_inr >= 0 else "#ef4444"

        with st.container(border=True):
            badge = "badge-buy" if is_long else "badge-sell"
            st.markdown(
                f"<div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:6px;'>"
                f"<div><span class='{badge}'>{p['direction']} {sym_p}/USDT</span> &nbsp; <b>{p['quantity']}</b> @ {fmt_px(entry_p)} ({p['leverage']}x)</div>"
                f"<div style='font-size:1.15rem;font-weight:800;color:{col};'>{'+' if pnl_inr >= 0 else ''}₹{pnl_inr:,.2f} ({roe:+.2f}% ROE)</div>"
                f"</div>",
                unsafe_allow_html=True
            )
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Entry", fmt_px(entry_p))
            m2.metric("Mark Price", fmt_px(mark_p))
            m3.metric("Current SL", fmt_px(float(cur_sl)) if cur_sl else "Not set")
            m4.metric("TP1 / TP2", f"{fmt_px(tp1) if tp1 else '—'} / {fmt_px(tp2) if tp2 else '—'}")
            st.caption(f"{ratchet} • Liq: {fmt_px(float(p.get('liquidation_price', 0) or 0))} • Margin: ₹{float(p.get('locked_margin_inr', 0) or 0):,.0f}")

            b1, b2, b3 = st.columns(3)
            b1.button(
                f"📈 View {sym_p} Chart",
                key=f"lt_focus_{pid}",
                use_container_width=True,
                on_click=_switch_pair_and_nav,
                args=(pr, "📈 Chart & Levels", None),
            )
            if target_sl is not None:
                better = (cur_sl is None) or ((target_sl > float(cur_sl)) if is_long else (target_sl < float(cur_sl)))
                if better and b2.button("🔒 Ratchet SL", key=f"lt_ratchet_{pid}", use_container_width=True):
                    ok, m = update_coindcx_position_tpsl(pid, cur_tp, target_sl, pair=pr)
                    (st.success if ok else st.error)(m)
            if b3.button(f"❌ Close {sym_p}", key=f"lt_close_{pid}", use_container_width=True):
                with st.spinner(f"Closing {sym_p}..."):
                    ok, m = exit_coindcx_position(pid)
                if ok:
                    _lt_finish_close(p, pnl_inr, "Manual close")
                    coindcx_engine.clear_autotrade_active_lock()
                    st.rerun()
                else:
                    st.error(m)

            with st.expander(f"⚙️ Edit TP / SL — {sym_p}"):
                step = 0.5 if mark_p > 1.0 else 0.0001
                fmt_s = "%.2f" if mark_p > 1.0 else "%.4f"
                e1, e2, e3 = st.columns([1.5, 1.5, 1])
                new_tp = e1.number_input("Take Profit ($)", value=float(cur_tp) if cur_tp else float(tp1 or mark_p), step=step, format=fmt_s, key=f"lt_tp_{pid}")
                new_sl = e2.number_input("Stop Loss ($)", value=float(cur_sl) if cur_sl else float(mark_p), step=step, format=fmt_s, key=f"lt_sl_{pid}")
                if e3.button("💾 Save", key=f"lt_save_{pid}", use_container_width=True):
                    ok, m = update_coindcx_position_tpsl(pid, new_tp, new_sl, pair=pr)
                    (st.success if ok else st.error)(m)

    if paper:
        pr = paper.get("pair", "")
        px = float(get_cached_ticker(pr).get("last_price", 0.0)) if pr else 0.0
        is_b = str(paper.get("direction") or paper.get("signal", "BUY")).upper() in ("BUY", "LONG")
        e_px, qty = float(paper.get("entry", 0)), float(paper.get("crypto_qty", 0))
        diff = (px - e_px) if is_b else (e_px - px)
        p_inr = diff * qty * float(paper.get("usd_inr", 85.0)) if px else 0.0
        with st.container(border=True):
            st.markdown(f"📝 **Paper Position** — {'LONG' if is_b else 'SHORT'} {clean_sym(pr)} ({qty} @ {fmt_px(e_px)})")
            q1, q2, q3 = st.columns(3)
            q1.metric("Mark Price", fmt_px(px) if px else "—")
            q2.metric("SL / TP1", f"{fmt_px(float(paper.get('stop_loss', 0)))} / {fmt_px(float(paper.get('tp1', 0)))}")
            q3.metric("Unrealized PnL", f"{'+' if p_inr >= 0 else ''}₹{p_inr:,.2f}")
            if st.button("❌ Close Paper Position", key="lt_close_paper", use_container_width=True):
                st.session_state.realized_pnl_inr += p_inr
                st.session_state.active_position = None
                coindcx_engine.clear_autotrade_active_lock()
                st.rerun()

    if pending_paper:
        st.markdown("#### ⏳ Resting Paper Limit Orders")
        for idx, p_ord in enumerate(list(pending_paper)):
            p_pair = p_ord.get("pair", "")
            p_entry = float(p_ord.get("entry", 0.0))
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                c1.markdown(f"**{p_ord.get('direction', 'BUY')} LIMIT {clean_sym(p_pair)}** • Qty `{p_ord['crypto_qty']}` @ `{fmt_px(p_entry)}`")
                if c2.button("❌ Cancel", key=f"lt_cancel_pending_{idx}", use_container_width=True):
                    st.session_state.paper_pending_orders.remove(p_ord)
                    st.rerun()

# ==============================================================================
# SECTION 4: INTERACTIVE CHART & KEY BOX LEVELS
# ==============================================================================
elif active_section == "📈 Chart & Levels":
    if levels:
        _bias = get_cached_bias(selected_pair)
        _bias_name = _bias["bias"]
        _bias_icon = "🟢" if _bias_name == "BULLISH" else ("🔴" if _bias_name == "BEARISH" else "🟡")

        k1, k2, k3, k4, k5 = st.columns(5)
        k1.metric("Swing High (SH)", fmt_px(levels["SH"]))
        k2.metric("Range High (RH)", fmt_px(levels["RH"]))
        k3.metric("Midpoint (MID)", fmt_px(levels["MID"]))
        k4.metric("Range Low (RL)", fmt_px(levels["RL"]))
        k5.metric("Swing Low (SL)", fmt_px(levels["SL"]))

        st.caption(f"**Daily Trend Bias ({asset_name}):** {_bias_icon} **{_bias_name}** — " + " • ".join(_bias["reasons"]))

        b_setup = calculate_trade_setup_details("BUY", levels, live_price, margin_inr, leverage, usd_inr, pair=selected_pair)
        s_setup = calculate_trade_setup_details("SELL", levels, live_price, margin_inr, leverage, usd_inr, pair=selected_pair)

        tf_col, overlay_col, slider_col, reload_col = st.columns([1.8, 1.8, 1.4, 0.9])
        with tf_col:
            tf_options = ["1m", "5m", "15m", "1h", "4h", "1d"]
            cur_tf_idx = tf_options.index(st.session_state.chart_timeframe) if st.session_state.chart_timeframe in tf_options else 2
            selected_tf = st.radio("Timeframe", tf_options, index=cur_tf_idx, horizontal=True, label_visibility="collapsed", key=f"tf_radio_{selected_pair}")
            if selected_tf != st.session_state.chart_timeframe:
                st.session_state.chart_timeframe = selected_tf
                st.rerun()
        with overlay_col:
            overlay_mode = st.selectbox(
                "Overlay Mode",
                ["Price & Box Levels Only", "Both BUY & SELL Setups", "BUY Setup Only", "SELL Setup Only"],
                index=0, label_visibility="collapsed", key=f"overlay_mode_{selected_pair}"
            )
        with slider_col:
            candle_count = st.slider("Bars", min_value=30, max_value=150, value=75, step=15, label_visibility="collapsed", key=f"bars_{selected_pair}")
        with reload_col:
            if st.button("🔄 Refresh Chart", key=f"btn_chart_refresh_{selected_pair}", use_container_width=True):
                st.rerun()

        active_tf = st.session_state.chart_timeframe
        df_chart = fetch_coindcx_candles(selected_pair, interval=active_tf, limit=candle_count, sync_live_price=True)

        if not df_chart.empty:
            ts_series = pd.to_datetime(df_chart["timestamp"], unit="ms")
            fig = go.Figure()

            fig.add_hrect(y0=levels["RH"], y1=levels["SH"], fillcolor="rgba(239,68,68,0.12)", line_width=0, layer="below")
            fig.add_hrect(y0=levels["SL"], y1=levels["RL"], fillcolor="rgba(16,185,129,0.12)", line_width=0, layer="below")

            fig.add_trace(go.Candlestick(
                x=ts_series, open=df_chart["open"], high=df_chart["high"], low=df_chart["low"], close=df_chart["close"],
                name=f"{asset_name} ({active_tf})",
                increasing_line_color=candle_up, increasing_fillcolor=candle_up,
                decreasing_line_color=candle_down, decreasing_fillcolor=candle_down
            ))

            ema50_curve = df_chart["close"].ewm(span=50, adjust=False).mean()
            ema200_curve = df_chart["close"].ewm(span=200, adjust=False).mean()
            fig.add_trace(go.Scatter(x=ts_series, y=ema50_curve, mode="lines", name="50 EMA", line=dict(color="#8b5cf6", width=1.8)))
            fig.add_trace(go.Scatter(x=ts_series, y=ema200_curve, mode="lines", name="200 EMA", line=dict(color="#f59e0b", width=1.8, dash="dot")))

            for lbl, key_l, col_l, dsh in [
                ("SH", "SH", "#ef4444", "dash"),
                ("RH", "RH", "#f97316", "solid"),
                ("MID", "MID", "#0284c7", "dot"),
                ("RL", "RL", "#10b981", "solid"),
                ("SL", "SL", "#059669", "dash"),
            ]:
                fig.add_hline(
                    y=levels[key_l], line_dash=dsh, line_color=col_l, line_width=1.8,
                    annotation_text=f"<b>{lbl}: {fmt_px(levels[key_l])}</b>",
                    annotation_position="top left" if key_l in ("SH", "RH", "MID") else "bottom left",
                    annotation_bgcolor=col_l, annotation_font=dict(size=10, color="#ffffff")
                )

            if live_price > 0:
                fig.add_hline(
                    y=live_price, line_dash="dashdot", line_color="#3b82f6", line_width=2,
                    annotation_text=f"<b>LIVE: {fmt_px(live_price)}</b>",
                    annotation_position="top right", annotation_bgcolor="#2563eb",
                    annotation_font=dict(size=11, color="#ffffff")
                )

            if "BUY" in overlay_mode or "Both" in overlay_mode:
                fig.add_hline(y=b_setup["entry"], line_color="#10b981", line_width=1.5, annotation_text=f"BUY E1: {fmt_px(b_setup['entry'])}", annotation_position="bottom right")
                fig.add_hline(y=b_setup["stop_loss"], line_dash="dash", line_color="#ef4444", line_width=1.5, annotation_text=f"BUY SL: {fmt_px(b_setup['stop_loss'])}", annotation_position="bottom right")
            if "SELL" in overlay_mode or "Both" in overlay_mode:
                fig.add_hline(y=s_setup["entry"], line_color="#f43f5e", line_width=1.5, annotation_text=f"SELL E1: {fmt_px(s_setup['entry'])}", annotation_position="top right")
                fig.add_hline(y=s_setup["stop_loss"], line_dash="dash", line_color="#f97316", line_width=1.5, annotation_text=f"SELL SL: {fmt_px(s_setup['stop_loss'])}", annotation_position="top right")

            fig.update_layout(
                height=480,
                template="plotly_dark" if not is_light_theme else "plotly_white",
                paper_bgcolor=plot_paper, plot_bgcolor=plot_bg, showlegend=False,
                xaxis=dict(rangeslider=dict(visible=False), gridcolor=plot_grid, tickfont=dict(color=axis_font, size=10)),
                yaxis=dict(gridcolor=plot_grid, side="right", tickfont=dict(color=axis_font, size=10)),
                margin=dict(l=10, r=10, t=15, b=15),
                hovermode="x unified"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.error(f"Could not load {active_tf} candles for {selected_pair}.")
    else:
        st.warning(f"Key levels unavailable for {selected_pair}.")

# ==============================================================================
# SECTION 5: 1-CRYPTO-AT-A-TIME HIGH-VOLATILITY BACKTEST
# ==============================================================================
elif active_section == "🧪 Backtest":
    st.markdown("#### 🧪 1-Crypto-at-a-Time High-Volatility Backtest (10x Leverage)")
    bc1, bc2, bc3 = st.columns(3)
    bt_dur_label = bc1.selectbox("Duration", ["30 Days", "60 Days", "90 Days", "180 Days"], index=0, key="bt_multi_dur")
    bt_capital = bc2.number_input("Single-Trade Margin (₹)", min_value=5000, value=int(margin_inr), step=5000, key="bt_multi_cap")
    bt_lev = bc3.slider("Leverage (x)", 1, 20, 10, key="bt_multi_lev")

    if st.button("🏆 Run 1-Crypto-at-a-Time Portfolio Backtest (All 12 High-Vol Movers)", key="btn_run_portfolio_1slot", type="primary", use_container_width=True):
        days_p = int(bt_dur_label.split()[0])
        with st.spinner(f"Simulating 1-Crypto-at-a-Time across 12 High-Vol pairs ({bt_dur_label} @ {bt_lev}x)..."):
            port_res = coindcx_engine.run_portfolio_single_slot_backtest(
                pairs=list(coindcx_engine.HIGH_VOL_FUTURES_UNIVERSE),
                duration_days=days_p,
                margin_inr=float(bt_capital),
                leverage=bt_lev,
                usd_inr=usd_inr,
                strategy_id=strategy_registry.DEFAULT_STRATEGY_ID,
            )
            st.session_state["bt_portfolio_1slot"] = port_res

    port_out = st.session_state.get("bt_portfolio_1slot")
    if port_out and port_out.get("total_trades", 0) > 0:
        pk1, pk2, pk3, pk4 = st.columns(4)
        pk1.metric("Net Portfolio Profit", f"₹{port_out['net_profit_inr']:,.0f}", f"{port_out['total_roi_pct']:+.1f}% ROI")
        pk2.metric("Total Trades (1 Slot)", port_out["total_trades"])
        pk3.metric("Win Rate", f"{port_out['win_rate_pct']}%", f"{port_out['win_count']}W / {port_out['loss_count']}L")
        pk4.metric("Profit Factor", f"{port_out['profit_factor']}")
        st.dataframe(port_out["coin_summary_df"], use_container_width=True, hide_index=True)
        with st.expander("📜 View Individual Portfolio Trades"):
            st.dataframe(
                port_out["trades_df"][["entry_time", "exit_time", "pair", "direction", "entry_price", "exit_price", "roe_pct", "net_pnl_inr", "trigger", "exit_reason"]],
                use_container_width=True,
                hide_index=True
            )
