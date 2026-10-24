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
except Exception as _mod_err:
    st.error(f"❌ Backend Engine Initialization Error: {_mod_err}")
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

st.set_page_config(
    page_title="CoinDCX Box Theory Terminal",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
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
            <h2 style="margin: 0; color: #0f172a; font-weight: 800; font-size: 24px; letter-spacing: -0.5px;">CoinDCX Terminal</h2>
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
            unlock_clicked = st.form_submit_button("🔓 Unlock Terminal", use_container_width=True)
            if unlock_clicked:
                if entered_pin.strip() == required_pin:
                    st.session_state.authenticated = True
                    st.success("✅ Access Granted! Opening Terminal...")
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

# ----------------- SESSION STATE INITIALIZATION -----------------
if "executed_trades" not in st.session_state:
    st.session_state.executed_trades = []

if "active_position" not in st.session_state:
    st.session_state.active_position = None

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
</style>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR CONTROLS -----------------
st.sidebar.markdown("### 💰 Account Margin Overview")
wallet_data = get_cached_balance()
st.sidebar.metric("Futures Balance", f"₹{wallet_data['total_inr']:,.2f}", wallet_data["source"])

default_margin = float(os.getenv("MARGIN_PER_TRADE_INR", 100000))
margin_inr = st.sidebar.number_input("Margin per Trade (INR)", value=int(default_margin), step=10000)

default_lev = int(os.getenv("LEVERAGE", 5))
leverage = st.sidebar.slider("Leverage Multiplier", min_value=1, max_value=20, value=default_lev)

live_crypto_rate = get_coindcx_live_usdt_inr_rate()
usd_inr = st.sidebar.number_input("USDT / INR Rate (Live CoinDCX)", value=float(live_crypto_rate), step=0.5)
st.sidebar.caption(f"🟢 CoinDCX Live Spot USDT: **₹{live_crypto_rate:,.2f} INR**")

st.sidebar.markdown("---")
st.sidebar.markdown("### 📧 Email Alerts & Server Link")
alert_enabled = os.getenv("ALERT_EMAIL_ENABLED", "True").lower() in ["true", "1", "yes"]
st.sidebar.caption(f"Status: **{'🟢 Active' if alert_enabled else '🔴 Disabled'}** | Cooldown: 15 mins")
cfg_receiver = os.getenv("RECEIVER_EMAIL", "jwalashiva@gmail.com")
cfg_app_url = os.getenv("APP_WEB_URL", "http://localhost:8501")
custom_url = st.sidebar.text_input("Server Web App URL (Included in Alerts):", value=cfg_app_url, key="input_app_web_url")
if custom_url != os.getenv("APP_WEB_URL", ""):
    os.environ["APP_WEB_URL"] = custom_url
st.sidebar.caption(f"Receiver: `{cfg_receiver}`")

if st.sidebar.button("📩 Send Test Alert Email", key="btn_send_test_email", use_container_width=True):
    with st.sidebar:
        with st.spinner("Dispatching test alert email..."):
            test_ticker = get_cached_ticker(st.session_state.selected_pair)
            test_lp = test_ticker.get("last_price", 100.0)
            ok, msg = send_sweep_alert(
                pair=st.session_state.selected_pair,
                signal_type="BUY",
                session_name="🏛️ London Open (01:30 PM IST)",
                live_price=test_lp,
                entry=test_lp,
                stop_loss=round(test_lp * 0.985, 2),
                tp1=round(test_lp * 1.025, 2),
                tp2=round(test_lp * 1.045, 2),
                roe_tp1=12.5,
                force=True
            )
            if ok:
                st.success(f"✅ {msg}")
            else:
                st.error(f"❌ {msg}")

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
    st.title("⚡ CoinDCX Box Terminal")
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

        if pos and pos.get("pair") == pair and cur_p > 0:
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
tabs = st.tabs([
    "📈 Live Chart & Trade Setups",
    "⚡ Live Trade Execution & Risk",
    "📐 Key Box Levels Breakdown",
    "📋 Google Sheet Logger",
    "📊 Strategy Backtest"
])

# ==============================================================================
# TAB 0: INTERACTIVE CHART (DARK/LIGHT + TIMEFRAME + BOLD HIGHLIGHTS)
# ==============================================================================
with tabs[0]:
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

    render_chart_fragment(selected_pair, levels, is_light_theme, margin_inr, leverage, usd_inr)

# ==============================================================================
# TAB 1: LIVE TRADE EXECUTION, FEES & CAPITAL PRESERVATION (REQUIREMENTS 2, 3, 4, 5)
# ==============================================================================
with tabs[1]:
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

        # LIVE COINDCX POSITIONS
        live_positions = get_cached_positions()
        if live_positions:
            col_pos_head, col_pos_close_all = st.columns([2.2, 1.8])
            with col_pos_head:
                st.markdown("#### 🔥 Active CoinDCX Futures Positions")
                st.caption(f"{len(live_positions)} active position(s) streaming live from CoinDCX")
            with col_pos_close_all:
                st.write("")
                if st.button("🚨 CLOSE ALL POSITIONS & CANCEL ORDERS", key="btn_close_all_positions", type="primary", use_container_width=True):
                    with st.spinner("Executing Emergency Close All on CoinDCX..."):
                        closed, total, msg = exit_all_coindcx_positions()
                        log_entry = {
                            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                            "pair": "ALL",
                            "action": "EMERGENCY_CLOSE_ALL",
                            "status": "SUCCESS" if closed == total else ("WARNING" if closed > 0 else "ERROR"),
                            "message": msg,
                            "details": {"closed": closed, "total": total}
                        }
                        st.session_state.api_error_logs.insert(0, log_entry)
                        st.session_state.last_order_status = {
                            "type": "success" if closed == total else "error",
                            "msg": msg,
                            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                            "pair": "ALL"
                        }
                        st.rerun()

            for p in live_positions:
                pos_id = p["id"]
                pair_name = p["pair"]
                direction = p["direction"]
                qty = p["quantity"]
                entry_p = p["entry_price"]
                mark_p = p["mark_price"]
                pnl_inr = p["pnl_inr"]
                pnl_usd = p["pnl_usd"]
                roe_pct = p["roe_pct"]
                liq_p = p["liquidation_price"]
                lev = p["leverage"]
                cur_tp = p.get("take_profit")
                cur_sl = p.get("stop_loss")
                pnl_col = "#16a34a" if pnl_inr >= 0 else "#dc2626"
                pnl_sgn = "+" if pnl_inr >= 0 else ""

                with st.container(border=True):
                    c_title, c_metrics, c_actions = st.columns([1.5, 2.0, 1.5])
                    with c_title:
                        dir_badge = f"<span class='badge-buy'>{direction} {pair_name}</span>" if direction == "LONG" else f"<span class='badge-sell'>{direction} {pair_name}</span>"
                        st.markdown(f"{dir_badge} **{qty}** @ ${entry_p:,.2f} ({lev}x)", unsafe_allow_html=True)
                        st.caption(f"Mark: ${mark_p:,.2f} | Liq: ${liq_p:,.2f} | Mode: {p.get('margin_type', 'isolated').upper()}")
                    with c_metrics:
                        st.markdown(f"<div style='font-size:1.15rem; font-weight:800; color:{pnl_col};'>{pnl_sgn}₹{pnl_inr:,.2f} ({pnl_sgn}{roe_pct:.2f}% ROE)</div>", unsafe_allow_html=True)
                        st.caption(f"Margin: ₹{p.get('locked_margin_inr', 0.0):,.2f} | Size: ₹{p.get('notional_inr', 0.0):,.2f} | Rate: ₹{p.get('settlement_rate', 100.0):.2f}/USDT")
                    with c_actions:
                        if st.button(f"❌ Close {pair_name}", key=f"btn_close_one_{pos_id}", use_container_width=True):
                            with st.spinner(f"Closing {pair_name} on CoinDCX..."):
                                ok, msg = exit_coindcx_position(pos_id)
                                log_entry = {
                                    "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                                    "pair": pair_name,
                                    "action": "CLOSE_POSITION",
                                    "status": "SUCCESS" if ok else "ERROR",
                                    "message": msg,
                                    "details": {"pos_id": pos_id}
                                }
                                st.session_state.api_error_logs.insert(0, log_entry)
                                if ok:
                                    st.session_state.last_order_status = {
                                        "type": "success",
                                        "msg": f"✅ Closed {pair_name} position!",
                                        "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                                        "pair": pair_name
                                    }
                                    st.rerun()
                                else:
                                    st.session_state.last_order_status = {
                                        "type": "error",
                                        "msg": f"❌ Failed to close {pair_name}: {msg}",
                                        "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                                        "pair": pair_name
                                    }
                                    st.error(f"❌ {msg}")

                    # In-position adjustment of Take Profit & Stop Loss
                    with st.expander(f"⚙️ Adjust TP / SL for {pair_name}", expanded=False):
                        t_col1, t_col2, t_col3 = st.columns([1.5, 1.5, 1.2])
                        with t_col1:
                            new_tp_val = st.number_input(
                                "New Take Profit ($):",
                                value=float(cur_tp) if cur_tp else float(round_asset_price(mark_p * (1.02 if direction == "LONG" else 0.98), mark_p)),
                                step=0.5 if mark_p > 1.0 else 0.0001,
                                format="%.4f" if mark_p < 1.0 else "%.2f",
                                key=f"input_tp_{pos_id}"
                            )
                        with t_col2:
                            new_sl_val = st.number_input(
                                "New Stop Loss ($):",
                                value=float(cur_sl) if cur_sl else float(round_asset_price(mark_p * (0.98 if direction == "LONG" else 1.02), mark_p)),
                                step=0.5 if mark_p > 1.0 else 0.0001,
                                format="%.4f" if mark_p < 1.0 else "%.2f",
                                key=f"input_sl_{pos_id}"
                            )
                        with t_col3:
                            st.write("")
                            if st.button("💾 Save TP/SL", key=f"btn_update_tpsl_{pos_id}", use_container_width=True):
                                with st.spinner("Updating triggers on CoinDCX..."):
                                    ok, msg = update_coindcx_position_tpsl(pos_id, new_tp_val, new_sl_val, pair=pair_name)
                                    log_entry = {
                                        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                                        "pair": pair_name,
                                        "action": "UPDATE_TPSL",
                                        "status": "SUCCESS" if ok else "ERROR",
                                        "message": msg,
                                        "details": {"tp": new_tp_val, "sl": new_sl_val, "pos_id": pos_id}
                                    }
                                    st.session_state.api_error_logs.insert(0, log_entry)
                                    if ok:
                                        st.session_state.last_order_status = {
                                            "type": "success",
                                            "msg": f"✅ TP and SL updated for {pair_name} on CoinDCX!",
                                            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                                            "pair": pair_name
                                        }
                                        st.rerun()
                                    else:
                                        st.session_state.last_order_status = {
                                            "type": "error",
                                            "msg": f"❌ Failed to update TP/SL for {pair_name}: {msg}",
                                            "timestamp": datetime.now(IST).strftime("%H:%M:%S IST"),
                                            "pair": pair_name
                                        }
                                        st.error(f"❌ {msg}")

        st.markdown("---")

        # REQUIREMENT 2: ALLOW USERS TO INPUT MARGIN & LEVERAGE BEFORE EXECUTION
        st.markdown("#### 🎛️ Configure Order Margin & Leverage")
        inp_col1, inp_col2, inp_col3 = st.columns([1.5, 1.5, 1])

        with inp_col1:
            avail_margin_int = max(1000, int(wallet["available_inr"]))
            trade_margin_inr = st.number_input(
                "Margin Allocation for this Trade (INR):",
                min_value=500,
                max_value=max(avail_margin_int, 500000),
                value=min(100000, avail_margin_int),
                step=1000,
                key=f"exec_margin_inr_{pair}"
            )
            # Preset percentage chips
            c1, c2, c3, c4 = st.columns(4)
            if c1.button("25%", key=f"pct_25_{pair}"):
                trade_margin_inr = int(wallet["available_inr"] * 0.25)
            if c2.button("50%", key=f"pct_50_{pair}"):
                trade_margin_inr = int(wallet["available_inr"] * 0.50)
            if c3.button("75%", key=f"pct_75_{pair}"):
                trade_margin_inr = int(wallet["available_inr"] * 0.75)
            if c4.button("100%", key=f"pct_100_{pair}"):
                trade_margin_inr = int(wallet["available_inr"])

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

        # Compute Setups and Costs based on dynamic margin & leverage
        b_setup = calculate_trade_setup_details("BUY", box_levels, cur_price, trade_margin_inr, trade_leverage, trade_usd_inr, pair=pair)
        s_setup = calculate_trade_setup_details("SELL", box_levels, cur_price, trade_margin_inr, trade_leverage, trade_usd_inr, pair=pair)
        sig_data = evaluate_tri_session_signal(pair, box_levels, trade_margin_inr, trade_leverage, trade_usd_inr, trigger_alert=False)

        exec_left, exec_right = st.columns([1.1, 1.1])

        with exec_left:
            st.markdown("#### Choose Order Setup")
            trade_choice = st.radio(
                "Execution Mode:",
                [
                    f"🟢 BUY / LONG Setup (Entry at Range Low: {fmt(b_setup['entry'])})",
                    f"🔴 SELL / SHORT Setup (Entry at Range High: {fmt(s_setup['entry'])})",
                    f"⚡ {sig_data['session_name']} Signal ({sig_data['signal']}: {sig_data['setup']})"
                ],
                index=0,
                key=f"trade_choice_exec_{pair}"
            )

            if "BUY" in trade_choice:
                active_trade = b_setup
                trade_dir = "BUY"
                setup_tag = "BUY"
                color_class = "badge-buy"
            elif "SELL" in trade_choice:
                active_trade = s_setup
                trade_dir = "SELL"
                setup_tag = "SELL"
                color_class = "badge-sell"
            else:
                trade_dir = "BUY" if sig_data["signal"] in ["BUY", "LONG"] else ("SELL" if sig_data["signal"] in ["SELL", "SHORT"] else "BUY")
                active_trade = b_setup if trade_dir == "BUY" else s_setup
                setup_tag = "SIGNAL"
                color_class = "badge-buy" if trade_dir == "BUY" else "badge-sell"

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
                        "Take Profit 1 (MID) ($):",
                        value=float(st.session_state.get(tp1_key, active_trade["tp1"])),
                        step=step_val,
                        format=fmt_str,
                        key=tp1_key
                    )
                    custom_tp2 = st.number_input(
                        "Take Profit 2 (Extreme) ($):",
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
                        <td style="padding:6px 0;"><b>Take Profit 1 (MID):</b></td>
                        <td style="text-align:right; color:#0284c7; font-weight:700;">{fmt(active_trade['tp1'])} (+{active_trade['roe_tp1']}%)</td>
                    </tr>
                    <tr style="border-bottom:1px solid {card_border};">
                        <td style="padding:6px 0;"><b>Take Profit 2 (Extreme):</b></td>
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
                    else:
                        with st.spinner("Submitting order to CoinDCX Futures API..."):
                            ok, api_msg, api_extra = place_coindcx_futures_order(
                                pair=pair,
                                side=trade_dir,
                                quantity=active_trade["crypto_qty"],
                                leverage=trade_leverage,
                                order_type="market_order",
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
                    order_record = {
                        "timestamp": exec_time,
                        "pair": pair,
                        "signal": trade_dir,
                        "direction": trade_dir,
                        "setup": active_trade.get("setup", "Box Setup"),
                        "entry": active_trade["entry"],
                        "stop_loss": active_trade["stop_loss"],
                        "tp1": active_trade["tp1"],
                        "tp2": active_trade["tp2"],
                        "crypto_qty": active_trade["crypto_qty"],
                        "margin_inr": trade_margin_inr,
                        "leverage": trade_leverage,
                        "usd_inr": trade_usd_inr,
                        "profit_tp1_inr": active_trade["profit_tp1_inr"],
                        "loss_sl_inr": active_trade["loss_sl_inr"],
                        "status": "LIVE_FILLED" if "Live" in exec_mode else "PAPER_EXECUTED"
                    }

                    # Save active position for tracking
                    st.session_state.active_position = order_record
                    st.session_state.executed_trades.insert(0, order_record)

                    sheet_success, sheet_msg = log_trade_to_google_sheet(order_record, return_details=True)

                    status_headline = "LIVE COINDCX ORDER EXECUTED!" if "Live" in exec_mode else "PAPER ORDER RECORDED!"
                    success_text = f"✅ **{status_headline}** {trade_dir} {active_trade['crypto_qty']} {cur_asset} @ {fmt(active_trade['entry'])} | {live_api_msg or 'Paper Simulation Active'} | Google Sheets: {sheet_msg}"

                    st.session_state.last_order_status = {
                        "type": "success",
                        "msg": success_text,
                        "timestamp": exec_time,
                        "pair": pair
                    }
                    if "Live" not in exec_mode:
                        st.session_state.api_error_logs.insert(0, {
                            "timestamp": exec_time,
                            "pair": pair,
                            "action": f"PAPER_{trade_dir}",
                            "status": "SUCCESS",
                            "message": f"Paper trade recorded: {trade_dir} {active_trade['crypto_qty']} {cur_asset}",
                            "details": order_record
                        })
                    st.rerun()

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
# TAB 2: KEY BOX LEVELS BREAKDOWN
# ==============================================================================
with tabs[2]:
    st.subheader(f"📐 Calculated Key Box Levels for {selected_pair}")
    st.caption("Derived from completed Previous Day Daily (1D) Candle and Multi-Day Swing Extrema")

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
with tabs[3]:
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
# TAB 4: REAL-TIME STRATEGY BACKTEST & PERFORMANCE ANALYTICS
# ==============================================================================
with tabs[4]:
    st.subheader("📊 Real-Time Strategy Backtest & Execution Simulator")
    st.caption("Simulate the institutional Box Theory & Liquidity Sweep strategy on real historical exchange candles with exact CoinDCX Futures fee schedules, leverage, and Indian GST accounting.")

    # 1. Backtest Configuration Controls
    with st.container():
        st.markdown(f"""
            <div style="background:{card_bg}; border:1px solid {card_border}; border-radius:10px; padding:14px 18px; margin-bottom:15px;">
                <span style="font-weight:700; color:{text_color}; font-size:1.05rem;">⚙️ Backtest Simulation Parameters</span>
            </div>
        """, unsafe_allow_html=True)

        c_pair, c_dur, c_tf, c_margin, c_lev, c_target = st.columns([1.5, 1.4, 1.0, 1.4, 1.0, 1.5])

        # Current pair default index
        cur_pair = st.session_state.selected_pair
        default_pair_idx = GLOBAL_FUTURES_PAIRS.index(cur_pair) if cur_pair in GLOBAL_FUTURES_PAIRS else 0

        with c_pair:
            bt_pair = st.selectbox("Futures Asset", GLOBAL_FUTURES_PAIRS, index=default_pair_idx, key="bt_pair_select")

        with c_dur:
            duration_options = {
                "1 Week (7 Days)": 7,
                "1 Month (30 Days)": 30,
                "3 Months (90 Days)": 90,
                "6 Months (180 Days)": 180,
                "12 Months / 1 Year (365 Days)": 365
            }
            bt_dur_label = st.selectbox("Duration", list(duration_options.keys()), index=4, key="bt_dur_select", help="Simulation lookback period")
            bt_days = duration_options[bt_dur_label]

        with c_tf:
            timeframe_options = ["15m", "1h", "4h", "1d"]
            bt_interval = st.selectbox("Timeframe", timeframe_options, index=0, key="bt_interval_select", help="Standard candlestick intervals: 15m (Institutional sweep), 1h (Hourly swing), 4h (Macro trend), 1d (Daily swing)")

        with c_margin:
            bt_margin = st.number_input(
                "Trade Margin (₹ INR)",
                min_value=2500,
                max_value=2000000,
                value=int(margin_inr) if margin_inr >= 2500 else 50000,
                step=5000,
                key="bt_margin_input",
                help="Margin allocation per simulated trade in Indian Rupees."
            )

        with c_lev:
            bt_leverage = st.slider("Leverage", min_value=1, max_value=25, value=int(leverage), key="bt_lev_slider")

        with c_target:
            bt_target_mode = st.selectbox(
                "Take Profit Rule",
                ["TP1 Midpoint", "TP2 Full Rotation", "50/50 Split"],
                index=0,
                key="bt_target_select",
                help="TP1 Midpoint: 50% retracement. TP2 Full Rotation: opposite range boundary. 50/50: scale out half at TP1 & move SL to breakeven."
            )

        col_run, col_info = st.columns([1.5, 4.5])
        with col_run:
            run_btn = st.button("🚀 Run Real-Time Backtest", use_container_width=True, type="primary", key="btn_run_backtest")
        with col_info:
            if bt_days >= 365 and bt_interval == "15m":
                st.caption("⚡ **1 Year on 15m Candles:** Simulating ~35,000 candles with multi-batch pagination and instant in-memory caching.")
            else:
                st.caption(f"Pulls live {bt_interval} candles for {bt_days} days directly from CoinDCX / Binance public data APIs, establishes rolling daily boxes, and simulates execution.")

    # Manage backtest session execution
    if "backtest_result" not in st.session_state:
        st.session_state.backtest_result = None

    if run_btn or st.session_state.backtest_result is None:
        if run_strategy_backtest:
            with st.spinner(f"⏳ Simulating Box Theory sweeps for {bt_pair} across historical candles ({bt_days} days on {bt_interval})..."):
                try:
                    bt_res = run_strategy_backtest(
                        pair=bt_pair,
                        duration_days=bt_days,
                        interval=bt_interval,
                        margin_inr=float(bt_margin),
                        leverage=int(bt_leverage),
                        target_mode=bt_target_mode,
                        usd_inr=usd_inr
                    )
                    st.session_state.backtest_result = bt_res
                except Exception as _bt_err:
                    st.error(f"❌ Backtest simulation failed: {_bt_err}")
                    st.session_state.backtest_result = {"error": str(_bt_err)}

    bt_res = st.session_state.backtest_result

    if bt_res:
        if bt_res.get("error"):
            st.warning(f"⚠️ {bt_res['error']}")
        else:
            # 2. Performance Summary Headline
            roi_color = "#16a34a" if bt_res['net_profit_inr'] >= 0 else "#dc2626"
            roi_sign = "+" if bt_res['net_profit_inr'] >= 0 else ""

            st.markdown(f"""
                <div style="background:{card_bg}; border:1px solid {card_border}; border-left:4px solid {roi_color}; border-radius:8px; padding:12px 16px; margin: 12px 0 16px 0;">
                    <span style="font-weight:700; color:{text_color}; font-size:1.05rem;">
                        Backtest Results: {bt_res['pair']} | {bt_res['duration_days']} Days ({bt_res['candle_interval']} Candles) | ₹{bt_res['margin_inr']:,.0f} Margin @ {bt_res['leverage']}x Leverage
                    </span><br>
                    <span style="font-size:0.85rem; color:{subtext_color};">
                        Strategy: Daily Box Liquidity Sweeps • Exit Target: {bt_res['target_mode']} • Fee Model: 0.05% Taker + 18% GST
                    </span>
                </div>
            """, unsafe_allow_html=True)

            # 3. Key Performance Metric Cards (Row 1)
            k1, k2, k3, k4, k5 = st.columns(5)
            with k1:
                st.metric(
                    "Net Profit (INR)",
                    f"₹{bt_res['net_profit_inr']:,.2f}",
                    f"{roi_sign}{bt_res['total_roi_pct']:.1f}% ROI",
                    delta_color="normal"
                )
            with k2:
                st.metric(
                    "Win Rate",
                    f"{bt_res['win_rate_pct']:.1f}%",
                    f"{bt_res['win_count']}W / {bt_res['loss_count']}L"
                )
            with k3:
                pf_str = f"{bt_res['profit_factor']:.2f}" if bt_res['profit_factor'] < 90 else "∞"
                st.metric(
                    "Profit Factor",
                    pf_str,
                    f"Gross: ₹{bt_res['total_gross_profit']:,.0f}"
                )
            with k4:
                st.metric(
                    "Max Drawdown",
                    f"-{bt_res['max_drawdown_pct']:.1f}%",
                    "Equity peak-to-trough"
                )
            with k5:
                st.metric(
                    "Total Trades",
                    f"{bt_res['total_trades']}",
                    f"Avg: {bt_res['avg_duration_candles']} candles"
                )

            # 4. Secondary Edge & Execution Statistics (Row 2)
            st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
            e1, e2, e3, e4 = st.columns(4)
            with e1:
                st.metric(
                    "Long Win Rate",
                    f"{bt_res['long_win_rate_pct']:.1f}%",
                    f"{bt_res['long_trades']} Long Trades"
                )
            with e2:
                st.metric(
                    "Short Win Rate",
                    f"{bt_res['short_win_rate_pct']:.1f}%",
                    f"{bt_res['short_trades']} Short Trades"
                )
            with e3:
                st.metric(
                    "CoinDCX Fees Paid",
                    f"₹{bt_res['total_fees_paid_inr']:,.2f}",
                    "Taker + 18% GST"
                )
            with e4:
                st.metric(
                    "Avg Win vs Avg Loss",
                    f"₹{bt_res['avg_win_inr']:,.0f}",
                    f"Avg Loss: ₹{bt_res['avg_loss_inr']:,.0f}"
                )

            # 5. Interactive Cumulative Equity Growth Curve (Plotly Chart)
            st.markdown("---")
            st.markdown("#### 📈 Cumulative Portfolio Equity Curve (₹ INR)")

            eq_data = bt_res.get("equity_curve", [])
            if eq_data and len(eq_data) > 1:
                eq_df = pd.DataFrame(eq_data)
                fig_eq = go.Figure()

                is_profitable = bt_res['net_profit_inr'] >= 0
                line_col = "#10b981" if is_profitable else "#ef4444"
                fill_col = "rgba(16, 185, 129, 0.12)" if is_profitable else "rgba(239, 68, 68, 0.12)"

                fig_eq.add_trace(go.Scatter(
                    x=eq_df['timestamp'],
                    y=eq_df['equity_inr'],
                    mode='lines+markers',
                    line=dict(color=line_col, width=2.5),
                    marker=dict(size=4, color=line_col),
                    fill='tozeroy',
                    fillcolor=fill_col,
                    name='Account Equity',
                    hovertemplate="<b>Date:</b> %{x}<br><b>Portfolio Equity:</b> ₹%{y:,.2f}<extra></extra>"
                ))

                fig_eq.add_hline(
                    y=bt_res['margin_inr'],
                    line_dash="dash",
                    line_color="#94a3b8",
                    annotation_text=f"Starting Margin: ₹{bt_res['margin_inr']:,.0f}",
                    annotation_position="bottom right"
                )

                fig_eq.update_layout(
                    xaxis_title="Trade Timeline",
                    yaxis_title="Equity (₹ INR)",
                    template="plotly_white" if is_light_theme else "plotly_dark",
                    margin=dict(l=20, r=20, t=30, b=20),
                    height=340,
                    hovermode="x unified"
                )
                st.plotly_chart(fig_eq, use_container_width=True)

            # 6. Dynamic Performance Breakdowns
            st.markdown("---")
            col_tbl_m, col_tbl_s = st.columns([1.1, 1.0])

            with col_tbl_m:
                st.markdown("#### 📅 Monthly Performance Breakdown")
                monthly_df = bt_res.get("monthly_df", pd.DataFrame())
                if not monthly_df.empty:
                    st.dataframe(monthly_df, use_container_width=True, hide_index=True)
                else:
                    st.info("No completed monthly intervals in this duration window.")

            with col_tbl_s:
                st.markdown("#### 🏛️ Institutional Session Breakdown")
                session_df = bt_res.get("session_df", pd.DataFrame())
                if not session_df.empty:
                    st.dataframe(session_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Session analytics will appear here once trades are executed.")

            # 7. Detailed Trade-by-Trade Execution Log & CSV Export
            st.markdown("---")
            st.markdown(f"#### 📋 Complete Simulated Trade Log ({bt_res['total_trades']} Trades)")

            trades_df = bt_res.get("trades_df", pd.DataFrame())
            if not trades_df.empty:
                display_cols = [
                    "trade_id", "entry_time", "exit_time", "direction", "session",
                    "entry_price", "exit_price", "exit_reason", "gross_pnl_inr",
                    "fees_inr", "net_pnl_inr", "roe_pct"
                ]
                avail_cols = [c for c in display_cols if c in trades_df.columns]

                # Download CSV button
                csv_bytes = trades_df.to_csv(index=False).encode('utf-8')
                col_btn, col_exp_info = st.columns([1.5, 4.5])
                with col_btn:
                    st.download_button(
                        label="📥 Export Trade Log (CSV)",
                        data=csv_bytes,
                        file_name=f"box_backtest_{bt_res['pair']}_{bt_res['duration_days']}d_{bt_res.get('candle_interval', '15m')}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )
                with col_exp_info:
                    st.caption(f"Download complete trade-by-trade audit logs with exact entries, stops, take profits, and fee deductions.")

                rename_map = {
                    "trade_id": "Trade #",
                    "entry_time": "Entry Time",
                    "exit_time": "Exit Time",
                    "direction": "Side",
                    "session": "Session",
                    "entry_price": "Entry ($)",
                    "exit_price": "Exit ($)",
                    "exit_reason": "Outcome",
                    "gross_pnl_inr": "Gross (₹)",
                    "fees_inr": "Fees (₹)",
                    "net_pnl_inr": "Net PnL (₹)",
                    "roe_pct": "ROE %"
                }

                pretty_df = trades_df[avail_cols].rename(columns=rename_map)
                st.dataframe(pretty_df, use_container_width=True, hide_index=True)
            else:
                st.info(f"No liquidity sweep trade setups were triggered for {bt_res['pair']} during the selected {bt_res['duration_days']}-day period.")
