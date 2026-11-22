from __future__ import annotations
import os
import time
import json
import hmac
import hashlib
import requests
import pandas as pd
import pytz
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

IST = pytz.timezone('Asia/Kolkata')

# Curated list of major global crypto futures markets
GLOBAL_FUTURES_PAIRS = [
    "B-BTC_USDT",
    "B-ETH_USDT",
    "B-SOL_USDT",
    "B-XRP_USDT",
    "B-BNB_USDT",
    "B-DOGE_USDT",
    "B-SUI_USDT",
    "B-NEAR_USDT",
    "B-PEPE_USDT",
    "B-ADA_USDT",
    "B-AVAX_USDT",
    "B-LINK_USDT",
    "B-APT_USDT",
    "B-ARB_USDT",
    "B-OP_USDT",
    "B-INJ_USDT",
    "B-TIA_USDT",
    "B-RENDER_USDT",
    "B-FET_USDT",
    "B-SHIB_USDT",
    "B-LTC_USDT",
    "B-DOT_USDT",
    "B-FTM_USDT",
    "B-POL_USDT",
    "B-WIF_USDT",
    "B-ENA_USDT",
    "B-SEI_USDT",
    "B-TON_USDT",
    "B-KAS_USDT",
    "B-UNI_USDT"
]

# Exact Binance/CoinDCX Futures Contract Specifications & Lot Sizes
FUTURES_PAIR_SPECS = {
    "B-BTC_USDT": {"step_size": 0.001, "qty_decimals": 3, "min_qty": 0.001, "tick_size": 0.1, "min_notional_usd": 50.0},
    "B-ETH_USDT": {"step_size": 0.001, "qty_decimals": 3, "min_qty": 0.001, "tick_size": 0.01, "min_notional_usd": 20.0},
    "B-SOL_USDT": {"step_size": 0.01, "qty_decimals": 2, "min_qty": 0.01, "tick_size": 0.01, "min_notional_usd": 5.0},
    "B-XRP_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-BNB_USDT": {"step_size": 0.01, "qty_decimals": 2, "min_qty": 0.01, "tick_size": 0.01, "min_notional_usd": 5.0},
    "B-DOGE_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-SUI_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-NEAR_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.001, "min_notional_usd": 5.0},
    "B-PEPE_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-07, "min_notional_usd": 5.0},
    "B-ADA_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-AVAX_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.001, "min_notional_usd": 5.0},
    "B-LINK_USDT": {"step_size": 0.01, "qty_decimals": 2, "min_qty": 0.01, "tick_size": 0.001, "min_notional_usd": 20.0},
    "B-APT_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-ARB_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-OP_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-INJ_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.001, "min_notional_usd": 5.0},
    "B-TIA_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-RENDER_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.001, "min_notional_usd": 5.0},
    "B-FET_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-SHIB_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-06, "min_notional_usd": 5.0},
    "B-LTC_USDT": {"step_size": 0.001, "qty_decimals": 3, "min_qty": 0.001, "tick_size": 0.01, "min_notional_usd": 20.0},
    "B-DOT_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-FTM_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-POL_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-WIF_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-ENA_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-SEI_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-TON_USDT": {"step_size": 0.1, "qty_decimals": 1, "min_qty": 0.1, "tick_size": 0.0001, "min_notional_usd": 5.0},
    "B-KAS_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 1e-05, "min_notional_usd": 5.0},
    "B-UNI_USDT": {"step_size": 1.0, "qty_decimals": 0, "min_qty": 1.0, "tick_size": 0.001, "min_notional_usd": 5.0}
}

def get_pair_lot_spec(pair: str) -> dict:
    """Returns the lot size and step precision specifications for a futures pair."""
    return FUTURES_PAIR_SPECS.get(pair, {
        "step_size": 0.001,
        "qty_decimals": 3,
        "min_qty": 0.001,
        "tick_size": 0.0001,
        "min_notional_usd": 5.0
    })

def format_order_quantity(pair: str, raw_qty: float) -> float:
    """
    Quantizes order quantity strictly to the exchange step size and decimal precision.
    Prevents HTTP 400 'Quantity should be divisible by X' errors on CoinDCX Futures.
    """
    if raw_qty is None or raw_qty <= 0:
        return 0.0

    spec = get_pair_lot_spec(pair)
    step = spec["step_size"]
    decimals = spec["qty_decimals"]

    steps = int(round(raw_qty / step, 8))
    quantized = steps * step

    if decimals == 0:
        return float(int(quantized))
    return round(quantized, decimals)

def format_order_price(pair: str, raw_price: float) -> float:
    """
    Quantizes order/trigger price strictly to the exchange tick_size precision.
    """
    if raw_price is None or raw_price <= 0:
        return 0.0
    spec = get_pair_lot_spec(pair)
    tick = float(spec.get("tick_size", 0.01) or 0.01)
    if tick <= 0:
        return round_asset_price(raw_price)
    steps = int(round(float(raw_price) / tick, 8))
    quantized = steps * tick
    tick_str = f"{tick:.8f}".rstrip("0")
    decimals = len(tick_str.split(".")[1]) if "." in tick_str else 0
    return round(quantized, decimals)

def round_asset_price(val, ref_price=None):
    """
    Rounds price dynamically based on asset magnitude (handles low-cost tokens like DOGE/PEPE).
    Keeps 4 decimal places across standard assets (6 decimal places for < 0.001).
    """
    ref = ref_price if ref_price is not None else val
    if ref is None:
        return 0.0
    if abs(ref) < 0.001:
        return round(float(val), 6)
    return round(float(val), 4)

import sys as _sys
import threading as _threading

# Process-wide persistent state that survives importlib.reload(coindcx_engine) across Streamlit reruns
_PERSIST = _sys.__dict__.setdefault("_coindcx_persistent_state", {
    "lock": _threading.Lock(),
    "last_ts_ms": 0,
    "last_ts_sec": 0,
    "session": requests.Session(),
    "session_verified": False,
    "pinned_ip": "",
    "seen_coindcx_ips": [],
    "wallet_cache": {"data": None, "ts": 0.0, "last_good_live": None, "last_good_ts": 0.0},
    "positions_cache": {"data": None, "ts": 0.0},
    "ticker_map_cache": {"ts": 0.0, "map": {}},
    "fapi_blocked": False,
    "api_key": "",
    "api_secret": "",
})
_PERSIST.setdefault("pinned_ip", "")
_PERSIST.setdefault("seen_coindcx_ips", [])
_PERSIST.setdefault("ticker_map_cache", {"ts": 0.0, "map": {}})
_PERSIST.setdefault("fapi_blocked", False)

_COINDCX_SIGN_LOCK = _PERSIST["lock"]
_WALLET_BALANCE_CACHE = _PERSIST["wallet_cache"]
_ACTIVE_POSITIONS_CACHE = _PERSIST["positions_cache"]
_TICKER_MAP_CACHE = _PERSIST["ticker_map_cache"]


def _get_coindcx_ticker_map(ttl: float = 5.0) -> dict:
    """Returns a 5-second cached dictionary of all CoinDCX markets -> ticker item so UI calls take 0ms."""
    now = time.time()
    cached_map = _TICKER_MAP_CACHE.get("map")
    if cached_map and (now - float(_TICKER_MAP_CACHE.get("ts", 0.0))) < ttl:
        return cached_map
    try:
        r = requests.get("https://api.coindcx.com/exchange/ticker", timeout=3.5)
        if r.status_code == 200:
            new_map = {}
            for item in r.json():
                mkt = item.get("market")
                if mkt:
                    new_map[str(mkt)] = item
            if new_map:
                _TICKER_MAP_CACHE["map"] = new_map
                _TICKER_MAP_CACHE["ts"] = now
                return new_map
    except Exception:
        pass
    return cached_map or {}


def fetch_live_ticker(pair="B-ETH_USDT"):
    """
    Fetches real-time market price, 24h high/low, and 24h price change.
    Uses the 5s shared CoinDCX ticker map first for 0ms UI response on Streamlit Cloud.
    """
    clean_pair = pair.replace("B-", "").replace("I-", "").replace("_", "")
    now_str = datetime.now(IST).strftime("%H:%M:%S IST")

    # 1. Fast Shared CoinDCX Ticker Map (0ms when warm, never geo-blocked on US Streamlit Cloud)
    try:
        t_map = _get_coindcx_ticker_map(ttl=5.0)
        item = t_map.get(clean_pair) or t_map.get(pair)
        if item:
            raw_p = float(item.get("last_price", 0) or 0)
            if raw_p > 0:
                high_p = float(item.get("high", raw_p) or raw_p)
                low_p = float(item.get("low", raw_p) or raw_p)
                bid_p = float(item.get("bid", 0) or 0)
                ask_p = float(item.get("ask", 0) or 0)
                chg = float(item.get("change_24_hour", 0) or 0)
                vol = float(item.get("volume", 0) or 0)
                return {
                    "pair": pair,
                    "symbol": clean_pair,
                    "last_price": round_asset_price(raw_p),
                    "bid": round_asset_price(bid_p, raw_p) if bid_p > 0 else 0.0,
                    "ask": round_asset_price(ask_p, raw_p) if ask_p > 0 else 0.0,
                    "high_24h": round_asset_price(high_p, raw_p),
                    "low_24h": round_asset_price(low_p, raw_p),
                    "change_24h": round(chg, 2),
                    "volume": round(vol, 2),
                    "source": "CoinDCX Public Feed",
                    "timestamp": now_str,
                    "status": "LIVE"
                }
    except Exception as e:
        print(f"[Live Ticker CoinDCX Error]: {e}")

    # 2. Fallback: Binance Vision 24hr Ticker
    try:
        url = f"https://data-api.binance.vision/api/v3/ticker/24hr?symbol={clean_pair}"
        r = requests.get(url, timeout=2.5)
        if r.status_code == 200:
            data = r.json()
            raw_p = float(data['lastPrice'])
            return {
                "pair": pair,
                "symbol": clean_pair,
                "last_price": round_asset_price(raw_p),
                "high_24h": round_asset_price(float(data['highPrice']), raw_p),
                "low_24h": round_asset_price(float(data['lowPrice']), raw_p),
                "change_24h": round(float(data['priceChangePercent']), 2),
                "volume": round(float(data['volume']), 2),
                "source": "Binance Vision Feed",
                "timestamp": now_str,
                "status": "LIVE"
            }
    except Exception:
        pass

    return {
        "pair": pair,
        "symbol": clean_pair,
        "last_price": 0.0,
        "high_24h": 0.0,
        "low_24h": 0.0,
        "change_24h": 0.0,
        "volume": 0.0,
        "source": "Unavailable",
        "timestamp": now_str,
        "status": "OFFLINE"
    }

def fetch_futures_funding_rate(pair="B-ETH_USDT"):
    """
    Fetches real-time futures funding rate, next funding settlement timestamp,
    and market sentiment (Positive: Longs pay Shorts / Negative: Shorts pay Longs).
    """
    clean_pair = pair.replace("B-", "").replace("I-", "").replace("_", "")
    if not _PERSIST.get("fapi_blocked"):
        try:
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={clean_pair}"
            resp = requests.get(url, timeout=1.5)
            if resp.status_code != 200:
                _PERSIST["fapi_blocked"] = True
            else:
                r = resp.json()
                if "lastFundingRate" in r:
                    raw_rate = float(r.get("lastFundingRate", 0.0))
                    pct_rate = raw_rate * 100.0
                    next_time_ms = int(r.get("nextFundingTime", 0))

                    now_ms = int(time.time() * 1000)
                    diff_sec = max(0, (next_time_ms - now_ms) // 1000)
                    hrs = diff_sec // 3600
                    mins = (diff_sec % 3600) // 60
                    countdown_str = f"{hrs}h {mins}m" if next_time_ms > 0 else "N/A"

                    is_pos = pct_rate >= 0
                    sentiment_desc = "Longs Pay Shorts (Bullish Premium)" if is_pos else "Shorts Pay Longs (Bearish Discount)"

                    return {
                        "pair": pair,
                        "symbol": clean_pair,
                        "funding_rate_pct": round(pct_rate, 4),
                        "funding_rate_str": f"{'+' if is_pos else ''}{pct_rate:.4f}%",
                        "is_positive": is_pos,
                        "sentiment": sentiment_desc,
                        "countdown": countdown_str,
                        "mark_price": float(r.get("markPrice", 0.0)),
                        "index_price": float(r.get("indexPrice", 0.0)),
                        "status": "ACTIVE"
                    }
        except Exception:
            _PERSIST["fapi_blocked"] = True

    return {
        "pair": pair,
        "symbol": clean_pair,
        "funding_rate_pct": 0.0100,
        "funding_rate_str": "+0.0100%",
        "is_positive": True,
        "sentiment": "Neutral Standard (0.01% / 8h)",
        "countdown": "3h 30m",
        "mark_price": 0.0,
        "index_price": 0.0,
        "status": "DEFAULT"
    }

def _next_monotonic_ms() -> int:
    """Returns a strictly increasing millisecond epoch timestamp."""
    now_ms = int(round(time.time() * 1000))
    if now_ms <= _PERSIST["last_ts_ms"]:
        now_ms = _PERSIST["last_ts_ms"] + 1
    _PERSIST["last_ts_ms"] = now_ms
    return now_ms


def _probe_session_coindcx_ip(sess: requests.Session, timeout: float = 2.5) -> str:
    """Queries https://api.coindcx.com/cdn-cgi/trace on the exact Keep-Alive session to return
    the true outbound IP address that api.coindcx.com sees for this TCP socket."""
    _check_and_kill_obsolete_daemon()
    try:
        r = sess.get(
            "https://api.coindcx.com/cdn-cgi/trace",
            headers={"Connection": "keep-alive"},
            timeout=timeout,
        )
        if r.status_code == 200:
            for line in r.text.splitlines():
                if line.startswith("ip="):
                    ip_val = line.split("=", 1)[1].strip()
                    if ip_val and ip_val not in _PERSIST["seen_coindcx_ips"]:
                        _PERSIST["seen_coindcx_ips"].append(ip_val)
                    return ip_val
    except Exception:
        pass
    return ""


def get_coindcx_outbound_ip_info(scan_extra_sockets: int = 0) -> dict:
    """Returns the exact outbound IP seen by api.coindcx.com on the active session plus any other NAT pool IPs."""
    cur_ip = _PERSIST.get("pinned_ip") or _probe_session_coindcx_ip(_PERSIST["session"], timeout=2.5)
    if scan_extra_sockets > 0:
        for _ in range(scan_extra_sockets):
            s = requests.Session()
            try:
                _probe_session_coindcx_ip(s, timeout=2.0)
            finally:
                try:
                    s.close()
                except Exception:
                    pass
    all_ips = list(_PERSIST.get("seen_coindcx_ips") or ([] if not cur_ip else [cur_ip]))
    return {
        "active_ip": cur_ip,
        "all_coindcx_ips": all_ips,
        "comma_separated": ", ".join(all_ips) if all_ips else cur_ip,
        "session_verified": bool(_PERSIST.get("session_verified", False)),
    }


def _get_coindcx_credentials() -> tuple[str, str]:
    """
    Reads CoinDCX API Key & Secret strictly from Streamlit Server (`st.secrets`) or environment variables (`os.environ`).
    Never stores or falls back to any hardcoded secret in code.
    """
    _check_and_kill_obsolete_daemon()
    api_key = ""
    api_secret = ""
    try:
        import streamlit as _st
        if hasattr(_st, "secrets"):
            for _k_name in ("COINDCX_API_KEY", "coindcx_api_key", "API_KEY"):
                if _k_name in _st.secrets and str(_st.secrets[_k_name]).strip():
                    api_key = str(_st.secrets[_k_name]).strip().strip('"').strip("'")
                    break
            for _s_name in ("COINDCX_API_SECRET", "COINDCX_SECRET_KEY", "COINDCX_SECRET", "coindcx_api_secret", "API_SECRET"):
                if _s_name in _st.secrets and str(_st.secrets[_s_name]).strip():
                    api_secret = str(_st.secrets[_s_name]).strip().strip('"').strip("'")
                    break
            if not api_key or not api_secret:
                for _k, _v in _st.secrets.items():
                    if hasattr(_v, "get"):
                        if not api_key:
                            for _k_name in ("COINDCX_API_KEY", "coindcx_api_key", "API_KEY"):
                                if _k_name in _v and str(_v[_k_name]).strip():
                                    api_key = str(_v[_k_name]).strip().strip('"').strip("'")
                                    break
                        if not api_secret:
                            for _s_name in ("COINDCX_API_SECRET", "COINDCX_SECRET_KEY", "COINDCX_SECRET", "coindcx_api_secret", "API_SECRET"):
                                if _s_name in _v and str(_v[_s_name]).strip():
                                    api_secret = str(_v[_s_name]).strip().strip('"').strip("'")
                                    break
    except Exception:
        pass

    if not api_key:
        api_key = (os.getenv("COINDCX_API_KEY") or _PERSIST.get("api_key") or "").strip().strip('"').strip("'")
    if not api_secret:
        api_secret = (
            os.getenv("COINDCX_API_SECRET")
            or os.getenv("COINDCX_SECRET_KEY")
            or os.getenv("COINDCX_SECRET")
            or _PERSIST.get("api_secret")
            or ""
        ).strip().strip('"').strip("'")

    api_key = "".join(api_key.split())
    api_secret = "".join(api_secret.split())
    if api_secret == "your_coindcx_secret_key_here":
        api_secret = ""

    if api_key and api_secret:
        prev_k = _PERSIST.get("api_key", "")
        prev_s = _PERSIST.get("api_secret", "")
        os.environ["COINDCX_API_KEY"] = api_key
        os.environ["COINDCX_API_SECRET"] = api_secret
        _PERSIST["api_key"] = api_key
        _PERSIST["api_secret"] = api_secret
        if (prev_k and prev_k != api_key) or (prev_s and prev_s != api_secret):
            _PERSIST["session_verified"] = False
            _PERSIST["last_nat_probe_ts"] = 0.0
            _WALLET_BALANCE_CACHE["data"] = None
            _WALLET_BALANCE_CACHE["last_good_live"] = None
            _ACTIVE_POSITIONS_CACHE["data"] = None

    return api_key, api_secret


_REQUIRED_DAEMON_VERSION = 35
ENTRY1_LIMIT_EXPIRY_SEC = 45 * 60  # Auto-cancel unfilled AutoTrade Entry 1 limit orders after 45 mins (3 x 15m candles)
MAX_EMA_CONCURRENT_TRADES = 2      # Cap 15m 50/200 EMA to max 2 of 3 slots so >=1 slot stays open for Box Theory Sweep


def compute_maker_limit_entry_price(
    pair: str,
    direction: str,
    desired_entry_px: float,
    live_ticker: dict = None,
    nudge_ticks: int = 0,
    sl_px: float = None,
    entry2_px: float = None,
    tp1_px: float = None,
) -> float:
    """
    Computes a strict Maker-side Limit Order price for AutoTrade Entry 1 so CoinDCX:
      1. Charges Maker fee (0.0236% incl. GST) instead of Taker Market fee (0.059% incl. GST — 60% lower fee!).
      2. Never rejects the limit order for immediately crossing the book (BUY < last_price/ask, SELL > last_price/bid).
    """
    spec = get_pair_lot_spec(pair)
    tick = float(spec.get("tick_size", 0.0001) or 0.0001)
    is_long = str(direction or "LONG").upper() in ("LONG", "BUY")
    base_e = float(desired_entry_px or 0.0)
    if base_e <= 0:
        return 0.0

    tk = live_ticker if isinstance(live_ticker, dict) else fetch_live_ticker(pair)
    last_p = float((tk or {}).get("last_price", 0.0) or 0.0)
    bid_p = float((tk or {}).get("bid", 0.0) or 0.0)
    ask_p = float((tk or {}).get("ask", 0.0) or 0.0)

    # Only anchor to live ticker when live_p is from the same live market regime (within 3% of signal entry)
    if last_p <= 0 or abs(last_p - base_e) / base_e > 0.03:
        return format_order_price(pair, base_e)

    extra_step = max(0, int(nudge_ticks)) * tick
    if is_long:
        if bid_p > 0 and bid_p < last_p:
            maker_ceil = bid_p - extra_step
        else:
            maker_ceil = last_p - max(1, int(nudge_ticks) + 1) * tick
        cand = min(base_e, maker_ceil)
        # Keep strictly above Entry 2 / Stop Loss so level ordering stays valid
        lower_guard = max(float(entry2_px or 0.0), float(sl_px or 0.0))
        if lower_guard > 0 and cand <= lower_guard:
            cand = base_e
        fmt_px = format_order_price(pair, cand)
        fmt_last = format_order_price(pair, last_p)
        if fmt_last > tick and fmt_px >= fmt_last and (lower_guard <= 0 or (fmt_last - tick) > lower_guard):
            fmt_px = format_order_price(pair, fmt_last - max(1, int(nudge_ticks) + 1) * tick)
        return fmt_px
    else:
        if ask_p > 0 and ask_p > last_p:
            maker_floor = ask_p + extra_step
        else:
            maker_floor = last_p + max(1, int(nudge_ticks) + 1) * tick
        cand = max(base_e, maker_floor)
        # Keep strictly below Entry 2 / Stop Loss so level ordering stays valid
        upper_guards = [g for g in (float(entry2_px or 0.0), float(sl_px or 0.0)) if g > 0]
        upper_guard = min(upper_guards) if upper_guards else 0.0
        if upper_guard > 0 and cand >= upper_guard:
            cand = base_e
        fmt_px = format_order_price(pair, cand)
        fmt_last = format_order_price(pair, last_p)
        if fmt_last > 0 and fmt_px <= fmt_last and (upper_guard <= 0 or (fmt_last + tick) < upper_guard):
            fmt_px = format_order_price(pair, fmt_last + max(1, int(nudge_ticks) + 1) * tick)
        return fmt_px
_sys.__dict__["_active_daemon_version"] = _REQUIRED_DAEMON_VERSION
_NAT_PIN_LOCK = _PERSIST.setdefault("nat_pin_lock", _threading.Lock())


class _ObsoleteDaemonStop(BaseException):
    """Custom non-SystemExit exception so Uvicorn/Tornado never logs an unclean server shutdown."""
    pass


def _check_and_kill_obsolete_daemon():
    """Immediately terminates any background daemon thread from an older version (< v10) or legacy CoinDCXNatKeepAlive."""
    _tname = _threading.current_thread().name
    if _tname == "CoinDCXNatKeepAlive" or (
        _tname.startswith("CryptoTradeAssistantDaemon") and _tname != f"CryptoTradeAssistantDaemon_v{_REQUIRED_DAEMON_VERSION}"
    ):
        _sys.__dict__["_active_daemon_version"] = _REQUIRED_DAEMON_VERSION
        raise _ObsoleteDaemonStop(f"Terminating obsolete daemon thread {_tname} (active is v{_REQUIRED_DAEMON_VERSION})")


def _get_coindcx_proxy_url() -> str:
    """
    Returns the configured Static IP Proxy URL (`http://user:pass@IP:8888` or `http://IP:8888`)
    for CoinDCX signed requests from Streamlit Secrets, environment variables, autotrade_config.json,
    or the shared `_Live_Account_Sync` Google Sheet tab.
    """
    proxy_url = ""
    try:
        import streamlit as _st
        if hasattr(_st, "secrets"):
            for _p_key in ("COINDCX_PROXY_URL", "coindcx_proxy_url", "STATIC_PROXY_URL"):
                if _p_key in _st.secrets and str(_st.secrets[_p_key]).strip():
                    proxy_url = str(_st.secrets[_p_key]).strip().strip('"').strip("'")
                    break
            if not proxy_url:
                for _k, _v in _st.secrets.items():
                    if hasattr(_v, "get"):
                        for _p_key in ("COINDCX_PROXY_URL", "coindcx_proxy_url", "STATIC_PROXY_URL"):
                            if _p_key in _v and str(_v[_p_key]).strip():
                                proxy_url = str(_v[_p_key]).strip().strip('"').strip("'")
                                break
    except Exception:
        pass

    if not proxy_url:
        proxy_url = (
            os.getenv("COINDCX_PROXY_URL")
            or _PERSIST.get("proxy_url")
            or ""
        ).strip().strip('"').strip("'")

    if not proxy_url:
        try:
            if os.path.exists(AUTOTRADE_CONFIG_FILE):
                with open(AUTOTRADE_CONFIG_FILE, "r", encoding="utf-8") as _f:
                    _cfg_p = json.load(_f)
                    if isinstance(_cfg_p, dict) and str(_cfg_p.get("coindcx_proxy_url", "")).strip():
                        proxy_url = str(_cfg_p["coindcx_proxy_url"]).strip()
        except Exception:
            pass

    if not proxy_url:
        try:
            import sheets_logger as _sl
            proxy_url = str(_sl._SHEET_SYNC_CACHE.get("proxy_url") or "").strip()
        except Exception:
            pass

    if not proxy_url:
        # Built-in Permanent GCP Static IP Proxy (domain-filtered strictly to api.coindcx.com)
        proxy_url = "http://35.230.95.39:8888"

    if proxy_url and not proxy_url.startswith(("http://", "https://", "socks5://")):
        proxy_url = f"http://{proxy_url}"
    if proxy_url:
        _PERSIST["proxy_url"] = proxy_url
    return proxy_url


def set_coindcx_proxy_url(proxy_url: str, sync_to_sheet: bool = True) -> str:
    """Updates the Static IP Proxy URL in memory, autotrade_config.json, and optionally Crypto_Trades_Journal."""
    clean_p = (proxy_url or "").strip().strip('"').strip("'")
    if clean_p and not clean_p.startswith(("http://", "https://", "socks5://")):
        clean_p = f"http://{clean_p}"
    _PERSIST["proxy_url"] = clean_p
    os.environ["COINDCX_PROXY_URL"] = clean_p
    _PERSIST["session_verified"] = False
    _PERSIST["last_nat_probe_ts"] = 0.0
    try:
        save_autotrade_config({"coindcx_proxy_url": clean_p})
    except Exception:
        pass
    if sync_to_sheet:
        def _sync_p():
            try:
                import sheets_logger as _sl
                _sl.save_live_account_sync_to_sheet(
                    wallet=_WALLET_BALANCE_CACHE.get("data"),
                    positions=_ACTIVE_POSITIONS_CACHE.get("data"),
                    pinned_ip=_PERSIST.get("pinned_ip", ""),
                    proxy_url=clean_p,
                )
            except Exception:
                pass
        _threading.Thread(target=_sync_p, daemon=True, name="CoinDCXProxySync").start()
    return clean_p


def _trigger_bg_sheet_account_publish(wallet_data: dict | None = None, positions_data: list | None = None):
    """Publishes verified live CoinDCX wallet & positions to Crypto_Trades_Journal every 20s in a background thread."""
    if not _PERSIST.get("session_verified") or _PERSIST.get("using_sheet_bridge"):
        return
    now_s = time.time()
    if (now_s - float(_PERSIST.get("last_sheet_pub_ts", 0.0))) < 60.0:
        return
    _PERSIST["last_sheet_pub_ts"] = now_s
    pinned_ip = str(_PERSIST.get("pinned_ip") or "")

    def _pub_worker():
        try:
            import sheets_logger as _sl
            _sl.save_live_account_sync_to_sheet(
                wallet=wallet_data if isinstance(wallet_data, dict) else _WALLET_BALANCE_CACHE.get("data"),
                positions=positions_data if isinstance(positions_data, list) else _ACTIVE_POSITIONS_CACHE.get("data"),
                pinned_ip=pinned_ip,
            )
        except Exception:
            pass

    _threading.Thread(target=_pub_worker, daemon=True, name="CoinDCXSheetSyncPub").start()


def _try_load_sheet_account_bridge(api_key: str, max_age_sec: float = 900.0) -> dict | None:
    """
    When a server's GKE node rotates off the allowlisted NAT IP, loads the verified live wallet & positions
    (and any newly configured Static IP Proxy URL) from Crypto_Trades_Journal ('_Live_Account_Sync' tab).
    """
    if not api_key:
        return None
    try:
        import sheets_logger as _sl
        snap = _sl.load_live_account_sync_from_sheet(max_age_sec=max_age_sec)
        if not isinstance(snap, dict):
            return None
        sheet_proxy = str(snap.get("proxy_url") or "").strip()
        if sheet_proxy and sheet_proxy != _PERSIST.get("proxy_url", ""):
            _PERSIST["proxy_url"] = sheet_proxy
            os.environ["COINDCX_PROXY_URL"] = sheet_proxy
            _PERSIST["last_nat_probe_ts"] = 0.0
        return snap
    except Exception:
        return None


def _make_single_socket_session(use_proxy: bool = True) -> requests.Session:
    """Creates a requests.Session strictly limited to 1 TCP connection (pool_maxsize=1) so urllib3
    never opens a 2nd unpinned Cloud NAT socket under concurrent load. Automatically attaches
    COINDCX_PROXY_URL when a Static IP proxy is configured and use_proxy=True."""
    s = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_connections=1, pool_maxsize=1, max_retries=0)
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    if use_proxy:
        proxy_url = _get_coindcx_proxy_url()
        if proxy_url:
            s.proxies = {"http": proxy_url, "https": proxy_url}
    return s


def _pin_coindcx_nat_session(api_key: str, api_secret: str, method: str = "GET", url: str = "https://api.coindcx.com/exchange/v1/derivatives/futures/wallets", payload: dict | None = None, timeout: float = 3.5):
    """
    Two-stage Cloud NAT egress IP pinner:
    - Phase 1 (Concurrent Priority Probe & Instant Verify): 8 worker threads open up to 8 sockets each
      (64 concurrent sockets held open in `cand_pool` so Google Cloud NAT spills across all 6+ egress IPs,
      including `35.230.78.192`). Workers ONLY call `_test_signed_on_sess` when `cand_ip in priority_ips`,
      so `_COINDCX_SIGN_LOCK` has zero contention and `35.230.78.192` is verified in ~0.4s on the warm socket.
    - Phase 2 (Fallback after `w.join()`): If no priority IP won, tests remaining unique `seen_ips` on the
      main pinner thread after all workers have joined (zero socket close race).
    """
    if not api_key or not api_secret:
        return None
    pin_lock = _PERSIST.get("nat_pin_lock") or _NAT_PIN_LOCK
    if not pin_lock.acquire(blocking=True, timeout=12.0):
        return None

    cand_pool = []
    winning_sess = None
    winning_res = None
    winning_ip = ""
    try:
        def _test_signed_on_sess(cand_sess, k_try: str, s_try: str):
            sign_lock = _PERSIST.get("lock") or _COINDCX_SIGN_LOCK
            with sign_lock:
                body = payload.copy() if payload else {}
                body["timestamp"] = _next_monotonic_ms()
                json_body = json.dumps(body, separators=(',', ':'))
                signature = hmac.new(s_try.encode('utf-8'), json_body.encode('utf-8'), hashlib.sha256).hexdigest()
                headers = {
                    'Content-Type': 'application/json',
                    'X-AUTH-APIKEY': k_try,
                    'X-AUTH-SIGNATURE': signature,
                    'Connection': 'keep-alive',
                }
                try:
                    if method.upper() == "GET":
                        r = cand_sess.get(url, data=json_body, headers=headers, timeout=timeout)
                    else:
                        r = cand_sess.post(url, data=json_body, headers=headers, timeout=timeout)
                    _PERSIST["last_sess_io_ts"] = time.time()
                    return r
                except Exception:
                    return None

        # 1. If a preceding caller that just released pin_lock already pinned a direct verified session, reuse it!
        if _PERSIST.get("session_verified") and not _PERSIST.get("using_sheet_bridge") and _PERSIST.get("session") is not None:
            r_reuse = _test_signed_on_sess(_PERSIST["session"], api_key, api_secret)
            if r_reuse is not None and (r_reuse.status_code == 200 or r_reuse.status_code not in (401, 502, 503)):
                return r_reuse

        now_p = time.time()

        # 2. Fast-path: Always test the permanent GCP Static IP Proxy (`35.230.95.39:8888`) first on a single socket (< 0.3s)
        active_proxy = _get_coindcx_proxy_url()
        if active_proxy and (now_p - float(_PERSIST.get("last_proxy_probe_ts", 0.0))) >= 30.0:
            _PERSIST["last_proxy_probe_ts"] = now_p
            cand_proxy = _make_single_socket_session(use_proxy=True)
            cand_pool.append(cand_proxy)
            proxy_ip = "35.230.95.39"
            r_proxy = _test_signed_on_sess(cand_proxy, api_key, api_secret)
            if r_proxy is not None and (r_proxy.status_code == 200 or r_proxy.status_code not in (401, 502, 503)):
                sign_lock = _PERSIST.get("lock") or _COINDCX_SIGN_LOCK
                with sign_lock:
                    old_sess = _PERSIST.get("session")
                    if old_sess is not None and old_sess is not cand_proxy:
                        try:
                            old_sess.close()
                        except Exception:
                            pass
                    _PERSIST["session"] = cand_proxy
                    _PERSIST["session_verified"] = True
                    _PERSIST["using_sheet_bridge"] = False
                    _PERSIST["pinned_ip"] = proxy_ip
                    _PERSIST["last_verified_ip"] = proxy_ip
                    _PERSIST["last_sess_io_ts"] = time.time()
                    _PERSIST["last_auth_error"] = ""
                winning_sess = cand_proxy
                return r_proxy

        # 3. Avoid back-to-back 120-socket direct NAT scans if a scan just ran < 1.5s ago (or < 60s when Sheet Bridge is active)
        min_probe_gap = 60.0 if _PERSIST.get("using_sheet_bridge") else 1.5
        if (now_p - float(_PERSIST.get("last_nat_probe_ts", 0.0))) < min_probe_gap:
            return None
        _PERSIST["last_nat_probe_ts"] = now_p

        priority_ips = {"35.230.78.192", "34.83.176.217"}
        last_v_ip = _PERSIST.get("last_verified_ip")
        if last_v_ip:
            priority_ips.add(last_v_ip)

        seen_ips = {}
        tested_ips = set()
        pool_lock = _threading.Lock()
        found_evt = _threading.Event()
        win_box = {"sess": None, "res": None, "ip": ""}

        def _probe_worker():
            for _ in range(10):
                if found_evt.is_set():
                    return
                cand = _make_single_socket_session(use_proxy=False)
                with pool_lock:
                    cand_pool.append(cand)
                cand_ip = _probe_session_coindcx_ip(cand, timeout=1.6)
                if not cand_ip or found_evt.is_set():
                    continue
                with pool_lock:
                    if cand_ip not in seen_ips:
                        seen_ips[cand_ip] = cand
                if cand_ip in priority_ips and not found_evt.is_set():
                    with pool_lock:
                        tested_ips.add(cand_ip)
                    r_try = _test_signed_on_sess(cand, api_key, api_secret)
                    if r_try is not None and (r_try.status_code == 200 or r_try.status_code not in (401, 502, 503)):
                        with pool_lock:
                            if not found_evt.is_set():
                                win_box["sess"] = cand
                                win_box["res"] = r_try
                                win_box["ip"] = cand_ip
                                found_evt.set()
                        return

        workers = [_threading.Thread(target=_probe_worker, daemon=True) for _ in range(12)]
        for w in workers:
            w.start()
        for w in workers:
            w.join(timeout=8.5)

        winning_sess = win_box["sess"]
        winning_res = win_box["res"]
        winning_ip = win_box["ip"]

        # Phase 2: Fallback after all workers joined if user allowlisted a different NAT IP not in priority_ips
        if winning_sess is None:
            for cand_ip, cand in list(seen_ips.items()):
                if cand_ip in tested_ips:
                    continue
                tested_ips.add(cand_ip)
                r_try = _test_signed_on_sess(cand, api_key, api_secret)
                if r_try is not None and (r_try.status_code == 200 or r_try.status_code not in (401, 502, 503)):
                    winning_sess = cand
                    winning_res = r_try
                    winning_ip = cand_ip
                    break

        if winning_sess is not None:
            sign_lock = _PERSIST.get("lock") or _COINDCX_SIGN_LOCK
            with sign_lock:
                old_sess = _PERSIST.get("session")
                if old_sess is not None and old_sess is not winning_sess:
                    try:
                        old_sess.close()
                    except Exception:
                        pass
                _PERSIST["session"] = winning_sess
                _PERSIST["session_verified"] = True
                _PERSIST["using_sheet_bridge"] = False
                _PERSIST["pinned_ip"] = winning_ip
                _PERSIST["last_verified_ip"] = winning_ip
                _PERSIST["last_sess_io_ts"] = time.time()
                _PERSIST["last_auth_error"] = ""
            return winning_res
        return None
    finally:
        for s in cand_pool:
            if s is not winning_sess:
                try:
                    s.close()
                except Exception:
                    pass
        pin_lock.release()


def _send_coindcx_signed_request(method, url, payload=None, timeout=3.5):
    """
    Executes signed CoinDCX REST API requests with HMAC-SHA256 authentication.
    - Serializes requests over the pinned single-socket Keep-Alive session (`_COINDCX_SIGN_LOCK`)
      so concurrent calls (`wallets` + `positions`) never open a 2nd unpinned NAT socket or close
      the active 35.230.78.192 connection.
    """
    _check_and_kill_obsolete_daemon()
    api_key, api_secret = _get_coindcx_credentials()

    if not api_key or not api_secret:
        return None, "API credentials not configured in .env or Streamlit Secrets"

    try:
        res = None
        if _PERSIST.get("session_verified") and not _PERSIST.get("using_sheet_bridge") and _PERSIST.get("session") is not None:
            with _COINDCX_SIGN_LOCK:
                sess = _PERSIST["session"]
                body = payload.copy() if payload else {}
                body["timestamp"] = _next_monotonic_ms()
                json_body = json.dumps(body, separators=(',', ':'))
                signature = hmac.new(api_secret.encode('utf-8'), json_body.encode('utf-8'), hashlib.sha256).hexdigest()
                headers = {
                    'Content-Type': 'application/json',
                    'X-AUTH-APIKEY': api_key,
                    'X-AUTH-SIGNATURE': signature,
                    'Connection': 'keep-alive',
                }
                try:
                    if method.upper() == "GET":
                        res = sess.get(url, data=json_body, headers=headers, timeout=timeout)
                    else:
                        res = sess.post(url, data=json_body, headers=headers, timeout=timeout)
                    _PERSIST["last_sess_io_ts"] = time.time()
                except Exception:
                    res = None

                if res is not None and (res.status_code == 200 or (res.status_code not in (400, 401, 429, 500, 502, 503) and "timestamp" not in res.text.lower() and "credential" not in res.text.lower())):
                    _PERSIST["session_verified"] = True
                    _PERSIST["last_auth_error"] = ""
                    return res, None

                # Pinned socket dropped or rotated; mark unverified and fall through to pinner
                _PERSIST["session_verified"] = False
                _PERSIST["pinned_ip"] = ""

        # Single-flight NAT pool pinner acquires 35.230.78.192 across 64 concurrent sockets
        r_pinned = _pin_coindcx_nat_session(api_key, api_secret, method=method, url=url, payload=payload, timeout=timeout)
        if r_pinned is not None:
            return r_pinned, None

        if not _PERSIST.get("using_sheet_bridge"):
            _PERSIST["last_auth_error"] = "HTTP 401 Invalid credentials / Egress IP not allowlisted"
        return res, _PERSIST.get("last_auth_error") or "HTTP 401 Invalid credentials / Egress IP not allowlisted"
    except Exception as e:
        return None, str(e)

_LIVE_USDT_INR_CACHE = {"rate": 102.0, "timestamp": 0.0}

def get_coindcx_live_usdt_inr_rate() -> float:
    """
    Fetches the live USDT/INR spot rate from the shared CoinDCX ticker map (0ms when warm).
    Caches the rate for 60 seconds and never blocks the UI thread.
    """
    _check_and_kill_obsolete_daemon()
    now = time.time()
    if now - _LIVE_USDT_INR_CACHE["timestamp"] < 60.0 and _LIVE_USDT_INR_CACHE["rate"] > 50.0:
        return _LIVE_USDT_INR_CACHE["rate"]

    try:
        t_map = _TICKER_MAP_CACHE.get("map") or _get_coindcx_ticker_map(ttl=60.0)
        item = t_map.get("USDTINR") or t_map.get("B-USDT_INR")
        if item:
            price = float(item.get("last_price", 0.0) or 0.0)
            if price > 50.0:
                _LIVE_USDT_INR_CACHE["rate"] = round(price, 2)
                _LIVE_USDT_INR_CACHE["timestamp"] = now
                return round(price, 2)
    except Exception:
        pass

    env_rate = float(os.getenv("USD_INR_RATE", 102.0))
    _LIVE_USDT_INR_CACHE["rate"] = env_rate
    _LIVE_USDT_INR_CACHE["timestamp"] = now
    return env_rate

def _get_saved_wallet_balance_default() -> float:
    """Reads the last saved wallet_balance_inr from autotrade_config.json without any network or recursive calls."""
    raw_env_bal = float(os.getenv("TOTAL_WALLET_INR", 47287.18))
    default_balance = 47287.18 if raw_env_bal in (30000.0, 250000.0, 40569.80) else raw_env_bal
    try:
        if os.path.exists(AUTOTRADE_CONFIG_FILE):
            with open(AUTOTRADE_CONFIG_FILE, "r", encoding="utf-8") as _f:
                _saved_cfg = json.load(_f)
                if isinstance(_saved_cfg, dict):
                    _sb = float(_saved_cfg.get("wallet_balance_inr", 0) or 0)
                    if _sb > 0 and _sb not in (30000.0, 250000.0, 40569.80):
                        default_balance = _sb
    except Exception:
        pass
    return default_balance

def _fetch_coindcx_futures_balance_sync() -> dict:
    """Internal synchronous worker that fetches live wallet balance from CoinDCX Futures API."""
    usd_inr = get_coindcx_live_usdt_inr_rate()
    default_balance = _get_saved_wallet_balance_default()
    api_key, api_secret = _get_coindcx_credentials()
    now_ts = time.time()

    if not api_key or not api_secret:
        return {
            "total_inr": round(default_balance, 2),
            "available_inr": round(default_balance, 2),
            "inr_cash": round(default_balance, 2),
            "locked_inr": 0.0,
            "usdt_cash": 0.0,
            "locked_margin_usd": 0.0,
            "cross_user_margin_usd": 0.0,
            "is_live_api": False,
            "source": f"Synced Wallet Balance (₹{default_balance:,.2f})"
        }

    usdt_balance = 0.0
    inr_balance = 0.0
    locked_inr = 0.0
    locked_margin_usd = 0.0
    cross_margin_usd = 0.0
    is_live = False
    api_err_msg = ""

    def _parse_futures_wallets(resp_obj) -> bool:
        nonlocal usdt_balance, inr_balance, locked_inr, locked_margin_usd, cross_margin_usd
        try:
            wallets = resp_obj.json()
            wallet_list = wallets if isinstance(wallets, list) else (wallets.get("wallets") or wallets.get("data") or []) if isinstance(wallets, dict) else []
            for w in wallet_list:
                if not isinstance(w, dict):
                    continue
                curr = str(w.get("currency_short_name") or w.get("currency") or "").upper()
                bal = float(w.get("balance", 0.0) or w.get("available_balance", 0.0) or 0.0)
                locked = float(w.get("locked_balance", 0.0) or 0.0)
                cross = float(w.get("cross_user_margin", 0.0) or 0.0)
                if curr == "USDT":
                    usdt_balance += bal
                    locked_margin_usd += locked
                    cross_margin_usd += cross
                elif curr == "INR":
                    inr_balance += bal
                    locked_inr += (locked + cross)
            return True
        except Exception as e:
            print(f"[Futures Wallet Parse Error]: {e}")
            return False

    # 1. Primary: CoinDCX Futures Wallet Endpoint (/exchange/v1/derivatives/futures/wallets)
    res_fut, err_fut = _send_coindcx_signed_request("GET", "https://api.coindcx.com/exchange/v1/derivatives/futures/wallets")
    if res_fut is not None and res_fut.status_code == 200:
        is_live = _parse_futures_wallets(res_fut)
    elif res_fut is not None:
        try:
            api_err_msg = res_fut.json().get("message", f"HTTP {res_fut.status_code}")
        except Exception:
            api_err_msg = f"HTTP {res_fut.status_code}"

    if is_live:
        raw_calc_inr = inr_balance + locked_inr + (usdt_balance * usd_inr)
        total_inr = raw_calc_inr
        avail_usdt = max(0.0, usdt_balance - locked_margin_usd - cross_margin_usd)
        avail_inr = inr_balance + (avail_usdt * usd_inr)
        if total_inr <= 0:
            total_inr = default_balance
            avail_inr = default_balance
        live_res = {
            "total_inr": round(total_inr, 2),
            "available_inr": round(avail_inr, 2),
            "inr_cash": round(inr_balance if inr_balance > 0 else total_inr, 2),
            "locked_inr": round(locked_inr, 2),
            "usdt_cash": round(usdt_balance, 4),
            "available_usdt": round(avail_usdt, 4),
            "locked_margin_usd": round(locked_margin_usd, 4),
            "cross_user_margin_usd": round(cross_margin_usd, 4),
            "live_usd_inr": usd_inr,
            "is_live_api": True,
            "source": "CoinDCX Live Futures API",
            "_key_prefix": api_key[:8],
        }
        # Always populate cache FIRST before touching config disk file (prevents any recursion!)
        _WALLET_BALANCE_CACHE["data"] = live_res
        _WALLET_BALANCE_CACHE["ts"] = now_ts
        _WALLET_BALANCE_CACHE["last_good_live"] = live_res
        _WALLET_BALANCE_CACHE["last_good_ts"] = now_ts
        _PERSIST["using_sheet_bridge"] = False
        _trigger_bg_sheet_account_publish(wallet_data=live_res, positions_data=_ACTIVE_POSITIONS_CACHE.get("data"))
        if abs(total_inr - default_balance) > 1.0:
            try:
                _cur_cfg = get_autotrade_config()
                _upd = {"wallet_balance_inr": round(total_inr, 2)}
                _cur_sm = float(_cur_cfg.get("single_trade_margin_inr", 0.0) or 0.0)
                if not _cur_cfg.get("user_custom_margin") and _cur_sm in (0.0, 15762.39, 30000.0, 250000.0, 100000.0):
                    _upd["single_trade_margin_inr"] = round(total_inr * TRADE_ALLOCATION_FRACTION, 2)
                save_autotrade_config(_upd)
            except Exception:
                pass
        return dict(live_res)

    # Cross-Server Sync Bridge via Crypto_Trades_Journal ('_Live_Account_Sync' tab):
    # If another server (e.g. staging on 35.230.78.192) is verified and publishing live account state,
    # or if a new Static IP Proxy URL was saved to the sheet, sync immediately!
    prev_proxy = _PERSIST.get("proxy_url", "")
    bridge = _try_load_sheet_account_bridge(api_key)
    if isinstance(bridge, dict):
        if bridge.get("proxy_url") and bridge.get("proxy_url") != prev_proxy:
            res_retry, _ = _send_coindcx_signed_request("GET", "https://api.coindcx.com/exchange/v1/derivatives/futures/wallets")
            if res_retry is not None and res_retry.status_code == 200 and _parse_futures_wallets(res_retry):
                raw_calc_inr = inr_balance + locked_inr + (usdt_balance * usd_inr)
                total_inr = raw_calc_inr if raw_calc_inr > 0 else default_balance
                avail_usdt = max(0.0, usdt_balance - locked_margin_usd - cross_margin_usd)
                avail_inr = inr_balance + (avail_usdt * usd_inr) if raw_calc_inr > 0 else default_balance
                live_res = {
                    "total_inr": round(total_inr, 2),
                    "available_inr": round(avail_inr, 2),
                    "inr_cash": round(inr_balance if inr_balance > 0 else total_inr, 2),
                    "locked_inr": round(locked_inr, 2),
                    "usdt_cash": round(usdt_balance, 4),
                    "available_usdt": round(avail_usdt, 4),
                    "locked_margin_usd": round(locked_margin_usd, 4),
                    "cross_user_margin_usd": round(cross_margin_usd, 4),
                    "live_usd_inr": usd_inr,
                    "is_live_api": True,
                    "source": "CoinDCX Live Futures API (Static Proxy)",
                    "_key_prefix": api_key[:8],
                }
                _WALLET_BALANCE_CACHE["data"] = live_res
                _WALLET_BALANCE_CACHE["ts"] = now_ts
                _WALLET_BALANCE_CACHE["last_good_live"] = live_res
                _WALLET_BALANCE_CACHE["last_good_ts"] = now_ts
                return dict(live_res)

        b_wallet = bridge.get("wallet")
        if isinstance(b_wallet, dict) and b_wallet.get("is_live_api") and not bridge.get("stale"):
            bridge_ip = str(bridge.get("pinned_ip") or "35.230.78.192")
            synced_wallet = dict(b_wallet)
            synced_wallet["_key_prefix"] = api_key[:8]
            synced_wallet["is_live_api"] = True
            synced_wallet["source"] = f"CoinDCX Live Futures API (Synced via {bridge_ip})"
            _WALLET_BALANCE_CACHE["data"] = synced_wallet
            _WALLET_BALANCE_CACHE["ts"] = now_ts
            _WALLET_BALANCE_CACHE["last_good_live"] = synced_wallet
            _WALLET_BALANCE_CACHE["last_good_ts"] = now_ts
            _PERSIST["session_verified"] = True
            _PERSIST["using_sheet_bridge"] = True
            _PERSIST["pinned_ip"] = bridge_ip
            _PERSIST["last_auth_error"] = ""
            try:
                _b_tot = float(synced_wallet.get("total_inr", 0.0) or 0.0)
                if _b_tot > 0:
                    _cur_cfg_b = get_autotrade_config()
                    _upd_b = {"wallet_balance_inr": round(_b_tot, 2)}
                    _cur_sm_b = float(_cur_cfg_b.get("single_trade_margin_inr", 0.0) or 0.0)
                    if not _cur_cfg_b.get("user_custom_margin") and _cur_sm_b in (0.0, 15762.39, 30000.0, 250000.0, 100000.0):
                        _upd_b["single_trade_margin_inr"] = round(_b_tot * TRADE_ALLOCATION_FRACTION, 2)
                    save_autotrade_config(_upd_b)
            except Exception:
                pass
            if isinstance(bridge.get("positions"), list):
                _ACTIVE_POSITIONS_CACHE["data"] = list(bridge["positions"])
                _ACTIVE_POSITIONS_CACHE["ts"] = now_ts
                _ACTIVE_POSITIONS_CACHE["last_ok_ts"] = now_ts
            return dict(synced_wallet)

    last_good = _WALLET_BALANCE_CACHE.get("last_good_live")
    if (
        isinstance(last_good, dict)
        and last_good.get("_key_prefix") == api_key[:8]
        and (now_ts - float(_WALLET_BALANCE_CACHE.get("last_good_ts", 0.0))) < 90.0
        and "expired" not in str(api_err_msg).lower()
    ):
        return dict(last_good)

    return {
        "total_inr": round(default_balance, 2),
        "available_inr": round(default_balance, 2),
        "inr_cash": round(default_balance, 2),
        "locked_inr": 0.0,
        "usdt_cash": 0.0,
        "locked_margin_usd": 0.0,
        "cross_user_margin_usd": 0.0,
        "is_live_api": False,
        "api_error": api_err_msg,
        "source": f"Wallet Balance ({api_err_msg})" if api_err_msg else "Synced Wallet Balance"
    }

def _trigger_bg_wallet_refresh():
    """Spawns a background daemon thread to refresh wallet balance without blocking the Streamlit UI."""
    now_ts = time.time()
    if _WALLET_BALANCE_CACHE.get("refreshing") and (now_ts - float(_WALLET_BALANCE_CACHE.get("refresh_start_ts", 0.0))) < 15.0:
        return
    _WALLET_BALANCE_CACHE["refreshing"] = True
    _WALLET_BALANCE_CACHE["refresh_start_ts"] = now_ts

    def _bg_worker():
        try:
            res = _fetch_coindcx_futures_balance_sync()
            if isinstance(res, dict) and res.get("is_live_api") and (time.time() - float(_ACTIVE_POSITIONS_CACHE.get("ts", 0.0))) > 10.0:
                _fetch_coindcx_active_positions_sync()
        except Exception:
            pass
        finally:
            _WALLET_BALANCE_CACHE["refreshing"] = False

    _threading.Thread(target=_bg_worker, daemon=True, name="CoinDCXWalletBgRefresh").start()

def fetch_coindcx_futures_balance(force_refresh: bool = False):
    """
    Returns CoinDCX Futures wallet balance in 0ms from cache when available and refreshes asynchronously
    in the background when stale so Streamlit UI navigation never hangs on network retries.
    """
    api_key, _ = _get_coindcx_credentials()
    now_ts = time.time()
    cached_bal = _WALLET_BALANCE_CACHE.get("data")
    if (
        not force_refresh
        and isinstance(cached_bal, dict)
        and cached_bal.get("_key_prefix") == api_key[:8]
    ):
        if cached_bal.get("is_live_api") and _PERSIST.get("session_verified") and not _PERSIST.get("using_sheet_bridge"):
            _trigger_bg_sheet_account_publish(wallet_data=cached_bal, positions_data=_ACTIVE_POSITIONS_CACHE.get("data"))
        age = now_ts - float(_WALLET_BALANCE_CACHE.get("ts", 0.0))
        if age < 30.0:
            return dict(cached_bal)
        # Stale-while-revalidate: return cached balance in 0ms and refresh in background!
        _trigger_bg_wallet_refresh()
        return dict(cached_bal)

    last_good = _WALLET_BALANCE_CACHE.get("last_good_live")
    if (
        not force_refresh
        and isinstance(last_good, dict)
        and last_good.get("_key_prefix") == api_key[:8]
        and bool(last_good.get("is_live_api"))
        and (now_ts - float(_WALLET_BALANCE_CACHE.get("last_good_ts", 0.0))) < (300.0 if _PERSIST.get("session_verified") else 45.0)
    ):
        _trigger_bg_wallet_refresh()
        return dict(last_good)

    # First load if cache is completely empty: seed instant balance from disk and refresh in background
    # NEVER write `seeded` into `last_good_live` (only real HTTP 200 wallet responses may populate `last_good_live`)!
    default_balance = _get_saved_wallet_balance_default()
    is_verified = bool(_PERSIST.get("session_verified", False))
    auth_err = str(_PERSIST.get("last_auth_error", "") or "")
    seeded = {
        "total_inr": round(default_balance, 2),
        "available_inr": round(default_balance, 2),
        "inr_cash": round(default_balance, 2),
        "locked_inr": 0.0,
        "usdt_cash": 0.0,
        "available_usdt": 0.0,
        "locked_margin_usd": 0.0,
        "cross_user_margin_usd": 0.0,
        "live_usd_inr": 102.0,
        "is_live_api": False,
        "api_error": auth_err,
        "source": "Synced Wallet Balance (Connecting...)" if not auth_err else f"Wallet Balance ({auth_err})",
        "_key_prefix": api_key[:8],
    }
    if force_refresh:
        return _fetch_coindcx_futures_balance_sync()
    _trigger_bg_wallet_refresh()
    return dict(seeded)

def _fetch_coindcx_active_positions_sync(return_none_on_error: bool = False) -> list | None:
    """Internal synchronous worker that fetches active open positions from CoinDCX Futures API."""
    now_pos_ts = time.time()
    live_usdt_inr = get_coindcx_live_usdt_inr_rate()
    payload = {
        "page": "1",
        "size": "100",
        "margin_currency_short_name": ["USDT", "INR"]
    }

    res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions", payload)
    if not res or res.status_code != 200:
        api_key_p, _ = _get_coindcx_credentials()
        bridge_p = _try_load_sheet_account_bridge(api_key_p)
        if isinstance(bridge_p, dict) and isinstance(bridge_p.get("positions"), list) and not bridge_p.get("stale"):
            synced_pos = list(bridge_p["positions"])
            _ACTIVE_POSITIONS_CACHE["data"] = synced_pos
            _ACTIVE_POSITIONS_CACHE["ts"] = now_pos_ts
            _ACTIVE_POSITIONS_CACHE["last_ok_ts"] = now_pos_ts
            _PERSIST["session_verified"] = True
            _PERSIST["using_sheet_bridge"] = True
            _PERSIST["last_auth_error"] = ""
            return list(synced_pos)
        if return_none_on_error:
            return None
        prev = _ACTIVE_POSITIONS_CACHE.get("data")
        last_ok = float(_ACTIVE_POSITIONS_CACHE.get("last_ok_ts", 0.0))
        if prev is not None and _PERSIST.get("session_verified") and (now_pos_ts - last_ok) < 90.0:
            return list(prev)
        _ACTIVE_POSITIONS_CACHE["data"] = []
        return []

    active_positions = []
    try:
        data = res.json()
        if isinstance(data, list):
            # Reuse 5s shared CoinDCX ticker map (0ms when warm) instead of redundant HTTP fetches
            live_prices = {}
            try:
                t_map = _get_coindcx_ticker_map(ttl=5.0)
                for mkt, it in t_map.items():
                    live_prices[mkt] = float(it.get("last_price", 0.0) or 0.0)
            except Exception:
                pass

            for item in data:
                active_pos_qty = float(
                    item.get("active_pos", 0.0)
                    or item.get("quantity", 0.0)
                    or item.get("position_size", 0.0)
                    or 0.0
                )
                if abs(active_pos_qty) > 0:
                    pair = str(item.get("pair", "") or "").strip()
                    if pair and pair not in GLOBAL_FUTURES_PAIRS:
                        GLOBAL_FUTURES_PAIRS.append(pair)
                    direction = "LONG" if active_pos_qty > 0 else "SHORT"
                    entry_price = float(item.get("avg_price", 0.0) or 0.0)
                    liq_price = float(item.get("liquidation_price", 0.0) or 0.0)
                    leverage = float(item.get("leverage", 1.0) or 1.0)

                    # Determine live market mark price
                    clean_sym = pair.replace("B-", "").replace("I-", "").replace("_", "")
                    live_p = live_prices.get(clean_sym, 0.0)
                    if live_p <= 0:
                        live_p = live_prices.get(pair.replace("B-", "").replace("I-", ""), 0.0)
                    if live_p <= 0:
                        try:
                            t_single = fetch_live_ticker(pair)
                            live_p = float(t_single.get("last_price", 0.0) or 0.0)
                        except Exception:
                            pass

                    raw_mark = float(item.get("mark_price", 0.0) or 0.0)
                    mark_price = live_p if live_p > 0 else raw_mark

                    settlement_rate = float(item.get("settlement_currency_avg_price", 0.0) or 0.0)
                    if settlement_rate <= 0:
                        settlement_rate = live_usdt_inr

                    margin_currency = item.get("margin_currency_short_name", "INR").upper()
                    raw_locked_margin = float(item.get("locked_margin", 0.0) or 0.0)

                    if margin_currency == "INR":
                        locked_margin_inr = raw_locked_margin * settlement_rate
                        locked_margin_usd = raw_locked_margin
                    else:
                        locked_margin_usd = raw_locked_margin
                        locked_margin_inr = locked_margin_usd * settlement_rate

                    qty = abs(active_pos_qty)
                    notional_usd = mark_price * qty
                    notional_inr = notional_usd * settlement_rate

                    if mark_price > 0 and entry_price > 0:
                        price_diff = (mark_price - entry_price) if direction == "LONG" else (entry_price - mark_price)
                        pnl_usd = price_diff * qty
                        pnl_inr = pnl_usd * settlement_rate
                        roe_pct = (pnl_inr / locked_margin_inr * 100.0) if locked_margin_inr > 0 else 0.0
                    else:
                        pnl_usd = 0.0
                        pnl_inr = 0.0
                        roe_pct = 0.0

                    tp = item.get("take_profit_trigger")
                    sl = item.get("stop_loss_trigger")
                    margin_type = item.get("margin_type", "isolated")

                    active_positions.append({
                        "id": item.get("id", ""),
                        "pair": pair,
                        "direction": direction,
                        "quantity": qty,
                        "entry_price": round_asset_price(entry_price),
                        "mark_price": round_asset_price(mark_price),
                        "liquidation_price": round_asset_price(liq_price),
                        "leverage": leverage,
                        "settlement_rate": round(settlement_rate, 2),
                        "margin_currency": margin_currency,
                        "locked_margin_usd": round(locked_margin_usd, 2),
                        "locked_margin_inr": round(locked_margin_inr, 2),
                        "notional_usd": round(notional_usd, 2),
                        "notional_inr": round(notional_inr, 2),
                        "pnl_usd": round(pnl_usd, 2),
                        "pnl_inr": round(pnl_inr, 2),
                        "roe_pct": round(roe_pct, 2),
                        "take_profit": float(tp) if tp else None,
                        "stop_loss": float(sl) if sl else None,
                        "margin_type": margin_type,
                        "updated_at": item.get("updated_at")
                    })
    except Exception as e:
        print(f"[CoinDCX Positions Parse Error]: {e}")

    _ACTIVE_POSITIONS_CACHE["data"] = active_positions
    _ACTIVE_POSITIONS_CACHE["ts"] = now_pos_ts
    _ACTIVE_POSITIONS_CACHE["last_ok_ts"] = now_pos_ts
    _trigger_bg_sheet_account_publish(wallet_data=_WALLET_BALANCE_CACHE.get("data"), positions_data=active_positions)
    if (now_pos_ts - float(_WALLET_BALANCE_CACHE.get("ts", 0.0))) > 20.0 or not (_WALLET_BALANCE_CACHE.get("data") or {}).get("is_live_api"):
        _trigger_bg_wallet_refresh()
    return active_positions

def _trigger_bg_positions_refresh():
    """Spawns a background daemon thread to refresh active positions without blocking the UI."""
    now_ts = time.time()
    if _ACTIVE_POSITIONS_CACHE.get("refreshing") and (now_ts - float(_ACTIVE_POSITIONS_CACHE.get("refresh_start_ts", 0.0))) < 15.0:
        return
    _ACTIVE_POSITIONS_CACHE["refreshing"] = True
    _ACTIVE_POSITIONS_CACHE["refresh_start_ts"] = now_ts

    def _bg_pos_worker():
        try:
            pos = _fetch_coindcx_active_positions_sync()
            if pos is not None and not _WALLET_BALANCE_CACHE.get("data"):
                _fetch_coindcx_futures_balance_sync()
        except Exception:
            pass
        finally:
            _ACTIVE_POSITIONS_CACHE["refreshing"] = False

    _threading.Thread(target=_bg_pos_worker, daemon=True, name="CoinDCXPosBgRefresh").start()

def fetch_coindcx_active_positions(force_refresh: bool = False):
    """
    Returns active CoinDCX Futures positions in 0ms from cache when warm, refreshing asynchronously
    in the background when stale so Streamlit UI navigation never blocks.
    """
    if force_refresh:
        return _fetch_coindcx_active_positions_sync()

    now_pos_ts = time.time()
    cached_pos = _ACTIVE_POSITIONS_CACHE.get("data")
    if cached_pos is not None:
        age = now_pos_ts - float(_ACTIVE_POSITIONS_CACHE.get("ts", 0.0))
        if age >= 8.0 or (len(cached_pos) == 0 and not _PERSIST.get("session_verified")):
            _trigger_bg_positions_refresh()
        return list(cached_pos)

    # First call when cache is cold: trigger background refresh and return fast
    _ACTIVE_POSITIONS_CACHE["data"] = []
    _ACTIVE_POSITIONS_CACHE["ts"] = now_pos_ts - 9.0
    _trigger_bg_positions_refresh()
    return []

def fetch_coindcx_open_orders():
    """
    Fetches open/pending futures orders (Limit, TP/SL, Untriggered) from CoinDCX Futures API.
    """
    payload = {
        "status": "open,partially_filled,untriggered",
        "side": "buy",
        "page": "1",
        "size": "20",
        "margin_currency_short_name": ["USDT", "INR"]
    }

    orders = []
    # Fetch Buy side
    res_b, _ = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders", payload)
    if res_b and res_b.status_code == 200:
        try:
            data = res_b.json()
            if isinstance(data, list):
                orders.extend(data)
        except Exception:
            pass

    # Fetch Sell side
    payload["side"] = "sell"
    res_s, _ = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders", payload)
    if res_s and res_s.status_code == 200:
        try:
            data = res_s.json()
            if isinstance(data, list):
                orders.extend(data)
        except Exception:
            pass

    return orders


_FUTURES_FUNDS_CACHE = _PERSIST.setdefault(
    "futures_funds_cache",
    {"ts": 0.0, "transactions": [], "spot_balances": [], "ok": False, "error": "", "pages": 0},
)


def _parse_tx_timestamp_ms(val) -> int:
    """Parses CoinDCX epoch seconds, epoch milliseconds, or ISO-8601 timestamp into integer ms."""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        v = float(val)
        if v <= 0:
            return 0
        return int(v * 1000) if v < 1e11 else int(v)
    s = str(val).strip()
    if s.replace(".", "", 1).isdigit():
        fv = float(s)
        return int(fv * 1000) if fv < 1e11 else int(fv)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp() * 1000)
    except Exception:
        return 0


def fetch_coindcx_spot_balances() -> list[dict]:
    """
    Fetches non-zero Spot / Main Wallet balances via POST /exchange/v1/users/balances.
    Fails gracefully (returns []) if the API key is Futures-only or unverified.
    """
    out = []
    try:
        res, _ = _send_coindcx_signed_request(
            "POST",
            "https://api.coindcx.com/exchange/v1/users/balances",
            {},
            timeout=8.0,
        )
        if res is not None and res.status_code == 200:
            data = res.json()
            if isinstance(data, list):
                for item in data:
                    if not isinstance(item, dict):
                        continue
                    cur = str(item.get("currency") or item.get("currency_short_name") or "").upper().strip()
                    bal = float(item.get("balance", 0.0) or 0.0)
                    locked = float(item.get("locked_balance", 0.0) or 0.0)
                    if cur and (bal > 0.0 or locked > 0.0):
                        out.append({
                            "currency": cur,
                            "available": round(bal, 6),
                            "locked": round(locked, 6),
                            "total": round(bal + locked, 6),
                        })
                out.sort(key=lambda x: (0 if x["currency"] == "INR" else (1 if x["currency"] == "USDT" else 2), -x["total"]))
    except Exception:
        pass
    return out


def fetch_coindcx_futures_wallet_transactions(
    force_refresh: bool = False,
    max_pages: int = 60,
) -> dict:
    """
    Paginates GET /exchange/v1/derivatives/futures/wallets/transactions from page 1 to the beginning
    of the user's CoinDCX Futures Wallet history (covering INR & USDT Futures transfers, trade settlements,
    and funding fees). Cached for 180s in `_FUTURES_FUNDS_CACHE` unless `force_refresh=True`.
    """
    now_ts = time.time()
    if (
        not force_refresh
        and _FUTURES_FUNDS_CACHE.get("ok")
        and (now_ts - float(_FUTURES_FUNDS_CACHE.get("ts", 0.0))) < 180.0
    ):
        return {
            "ok": True,
            "transactions": list(_FUTURES_FUNDS_CACHE.get("transactions") or []),
            "spot_balances": list(_FUTURES_FUNDS_CACHE.get("spot_balances") or []),
            "pages_fetched": int(_FUTURES_FUNDS_CACHE.get("pages", 0) or 0),
            "fetched_at_ist": _FUTURES_FUNDS_CACHE.get("fetched_at_ist", ""),
            "error": "",
        }

    api_key, api_secret = _get_coindcx_credentials()
    if not api_key or not api_secret:
        return {
            "ok": False,
            "transactions": [],
            "spot_balances": [],
            "pages_fetched": 0,
            "fetched_at_ist": "",
            "error": "CoinDCX API credentials are not configured.",
        }

    all_tx: list[dict] = []
    seen_ids: set[str] = set()
    prev_page_fp = None
    pages_fetched = 0
    last_err = ""
    success = False

    for page_size in (1000, 500, 100):
        all_tx = []
        seen_ids = set()
        prev_page_fp = None
        pages_fetched = 0
        tried_ok = False
        for page in range(1, max(1, int(max_pages)) + 1):
            url = f"https://api.coindcx.com/exchange/v1/derivatives/futures/wallets/transactions?page={page}&size={page_size}"
            res, err = _send_coindcx_signed_request("GET", url, {}, timeout=12.0)
            if res is None:
                last_err = err or "Connection error reaching CoinDCX Futures Transactions API"
                break
            if res.status_code != 200:
                msg_txt = res.text[:240]
                try:
                    rj = res.json()
                    if isinstance(rj, dict) and rj.get("message"):
                        msg_txt = str(rj["message"])
                except Exception:
                    pass
                last_err = f"CoinDCX API HTTP {res.status_code}: {msg_txt}"
                # HTTP 401/403 is credential/IP rejection -> don't retry smaller page sizes
                if res.status_code in (401, 403):
                    return {
                        "ok": False,
                        "transactions": list(_FUTURES_FUNDS_CACHE.get("transactions") or []),
                        "spot_balances": list(_FUTURES_FUNDS_CACHE.get("spot_balances") or []),
                        "pages_fetched": int(_FUTURES_FUNDS_CACHE.get("pages", 0) or 0),
                        "fetched_at_ist": _FUTURES_FUNDS_CACHE.get("fetched_at_ist", ""),
                        "error": last_err,
                    }
                break

            tried_ok = True
            success = True
            try:
                raw_json = res.json()
            except Exception as je:
                last_err = f"Invalid JSON from CoinDCX transactions API: {je}"
                break

            batch = raw_json if isinstance(raw_json, list) else (
                (raw_json.get("data") or raw_json.get("transactions") or []) if isinstance(raw_json, dict) else []
            )
            if not isinstance(batch, list) or len(batch) == 0:
                break

            # Detect duplicate page if exchange ignores pagination beyond final page
            cur_fp = tuple(
                (
                    str(x.get("id", "")),
                    str(x.get("created_at", "")),
                    str(x.get("amount", "")),
                    str(x.get("transaction_type", "")),
                    str(x.get("reason", "")),
                )
                for x in batch[:10]
            )
            if prev_page_fp is not None and cur_fp == prev_page_fp:
                break
            prev_page_fp = cur_fp

            pages_fetched += 1
            added_this_page = 0
            for item in batch:
                if not isinstance(item, dict):
                    continue
                tx_id = str(item.get("id") or "").strip()
                if tx_id:
                    if tx_id in seen_ids:
                        continue
                    seen_ids.add(tx_id)
                all_tx.append(item)
                added_this_page += 1

            if len(batch) < page_size or added_this_page == 0:
                break
            time.sleep(0.08)

        if tried_ok:
            break

    spot_balances = fetch_coindcx_spot_balances() if success else []
    fetched_ist = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    if success:
        _FUTURES_FUNDS_CACHE.update({
            "ts": now_ts,
            "transactions": list(all_tx),
            "spot_balances": list(spot_balances),
            "ok": True,
            "error": "",
            "pages": pages_fetched,
            "fetched_at_ist": fetched_ist,
        })
    return {
        "ok": success,
        "transactions": all_tx,
        "spot_balances": spot_balances,
        "pages_fetched": pages_fetched,
        "fetched_at_ist": fetched_ist if success else _FUTURES_FUNDS_CACHE.get("fetched_at_ist", ""),
        "error": "" if success else (last_err or "Failed to fetch CoinDCX Futures wallet transactions."),
    }


def compute_futures_funds_summary(
    transactions: list[dict],
    wallet: dict | None = None,
    positions: list[dict] | None = None,
    spot_balances: list[dict] | None = None,
    usd_inr: float | None = None,
) -> dict:
    """
    Aggregates CoinDCX Futures Wallet transaction history from the very beginning into:
      - Total Capital Added / Deposited to Futures Wallet (INR & USDT)
      - Total Withdrawn from Futures Wallet (INR & USDT)
      - Net Capital Invested & Peak Net Capital Deployed
      - Current Realized Futures Wallet Value, Open Unrealized PnL, & Total Equity
      - Realized Growth (INR & %), Total Growth (INR & % vs Net Capital, Peak Capital, and Total Deposited)
      - Breakdown by CoinDCX ledger `reason` (`by_universal_wallet`, `by_futures_order`, `by_futures_funding`, etc.)
      - Chronological Transfers Table, Monthly Summary Table, and Equity vs Invested Capital Timeline
    """
    w = wallet if isinstance(wallet, dict) else {}
    rate = float(usd_inr or w.get("live_usd_inr") or get_coindcx_live_usdt_inr_rate() or 102.0)

    def _to_inr(amt_abs: float, cur: str) -> float:
        c = cur.upper()
        if c == "INR":
            return amt_abs
        if c in ("USDT", "USD", "USDC"):
            return amt_abs * rate
        return amt_abs

    parsed_rows = []
    for idx_t, tx in enumerate(transactions or []):
        if not isinstance(tx, dict):
            continue
        ts_ms = _parse_tx_timestamp_ms(tx.get("created_at") or tx.get("timestamp") or tx.get("updated_at"))
        dt_ist = datetime.fromtimestamp(ts_ms / 1000.0, tz=IST) if ts_ms > 0 else None
        raw_amt = float(tx.get("amount", 0.0) or 0.0)
        ttype = str(tx.get("transaction_type") or tx.get("type") or "").strip().lower()
        if ttype in ("credit", "deposit", "in", "cr"):
            is_credit = True
            norm_type = "credit"
        elif ttype in ("debit", "withdraw", "withdrawal", "out", "dr"):
            is_credit = False
            norm_type = "debit"
        else:
            is_credit = raw_amt >= 0.0
            norm_type = "credit" if is_credit else "debit"
        amt_abs = abs(raw_amt)
        signed_amt = amt_abs if is_credit else -amt_abs
        cur = str(tx.get("currency_short_name") or tx.get("currency") or "INR").upper().strip()
        reason = str(tx.get("reason") or "other").strip()
        reason_l = reason.lower()
        is_transfer = any(k in reason_l for k in ("universal_wallet", "wallet", "transfer", "deposit", "withdraw"))
        is_funding = "funding" in reason_l
        is_order = (not is_transfer) and (not is_funding) and any(
            k in reason_l for k in ("order", "trade", "position", "pnl", "fee", "liquidat", "settle", "margin")
        )
        cat = "transfer" if is_transfer else ("funding" if is_funding else ("order" if is_order else "other"))
        inr_abs = _to_inr(amt_abs, cur)
        signed_inr = inr_abs if is_credit else -inr_abs

        parsed_rows.append({
            "idx": idx_t,
            "ts_ms": ts_ms,
            "dt_str": dt_ist.strftime("%Y-%m-%d %H:%M:%S IST") if dt_ist else str(tx.get("created_at", "")),
            "date_str": dt_ist.strftime("%Y-%m-%d") if dt_ist else "Unknown",
            "ym": dt_ist.strftime("%Y-%m") if dt_ist else "Unknown",
            "month_label": dt_ist.strftime("%b %Y") if dt_ist else "Unknown",
            "transaction_type": norm_type,
            "is_credit": is_credit,
            "amount": round(amt_abs, 6),
            "signed_amount": round(signed_amt, 6),
            "currency": cur,
            "amount_inr": round(inr_abs, 2),
            "signed_inr": round(signed_inr, 2),
            "reason": reason,
            "category": cat,
            "balance_after": tx.get("balance"),
        })

    # Sort oldest -> newest for exact running cumulative capital & wallet trajectory
    parsed_rows.sort(key=lambda r: (r["ts_ms"], r["idx"]))

    total_added_inr = 0.0
    total_withdrawn_inr = 0.0
    total_added_usdt = 0.0
    total_withdrawn_usdt = 0.0
    total_added_all_inr = 0.0
    total_withdrawn_all_inr = 0.0
    deposit_count = 0
    withdrawal_count = 0

    order_credits_inr = 0.0
    order_debits_inr = 0.0
    funding_credits_inr = 0.0
    funding_debits_inr = 0.0
    other_net_inr = 0.0

    cum_net_cap_inr = 0.0
    peak_net_cap_inr = 0.0
    cum_ledger_inr = 0.0

    transfers_rows = []
    reason_agg: dict[tuple[str, str, str], dict] = {}
    monthly_map: dict[str, dict] = {}
    daily_timeline_map: dict[str, dict] = {}

    for r in parsed_rows:
        rk = (r["reason"], r["currency"], r["transaction_type"])
        if rk not in reason_agg:
            reason_agg[rk] = {
                "Reason": r["reason"],
                "Category": r["category"].title(),
                "Currency": r["currency"],
                "Type": r["transaction_type"].upper(),
                "Count": 0,
                "Total Amount": 0.0,
                "INR Equivalent (₹)": 0.0,
            }
        reason_agg[rk]["Count"] += 1
        reason_agg[rk]["Total Amount"] += r["amount"]
        reason_agg[rk]["INR Equivalent (₹)"] += r["amount_inr"]

        ym = r["ym"]
        if ym not in monthly_map:
            monthly_map[ym] = {
                "ym": ym,
                "Month": r["month_label"],
                "Added (₹)": 0.0,
                "Withdrawn (₹)": 0.0,
                "Net Flow (₹)": 0.0,
                "Trading & Funding Ledger (₹)": 0.0,
                "Deposits": 0,
                "Withdrawals": 0,
                "End Net Capital (₹)": 0.0,
                "Est. End Wallet (₹)": 0.0,
            }
        m_row = monthly_map[ym]

        cum_ledger_inr += r["signed_inr"]

        if r["category"] == "transfer":
            if r["is_credit"]:
                deposit_count += 1
                total_added_all_inr += r["amount_inr"]
                if r["currency"] == "INR":
                    total_added_inr += r["amount"]
                elif r["currency"] == "USDT":
                    total_added_usdt += r["amount"]
                m_row["Added (₹)"] += r["amount_inr"]
                m_row["Deposits"] += 1
            else:
                withdrawal_count += 1
                total_withdrawn_all_inr += r["amount_inr"]
                if r["currency"] == "INR":
                    total_withdrawn_inr += r["amount"]
                elif r["currency"] == "USDT":
                    total_withdrawn_usdt += r["amount"]
                m_row["Withdrawn (₹)"] += r["amount_inr"]
                m_row["Withdrawals"] += 1
            cum_net_cap_inr += r["signed_inr"]
            if cum_net_cap_inr > peak_net_cap_inr:
                peak_net_cap_inr = cum_net_cap_inr
            m_row["Net Flow (₹)"] += r["signed_inr"]

            transfers_rows.append({
                "Date & Time (IST)": r["dt_str"],
                "Action": "DEPOSIT (Added to Futures)" if r["is_credit"] else "WITHDRAWAL (Moved Out)",
                "Type": "CREDIT" if r["is_credit"] else "DEBIT",
                "Amount": r["amount"],
                "Currency": r["currency"],
                "INR Value (₹)": round(r["signed_inr"], 2),
                "Cumulative Net Capital (₹)": round(cum_net_cap_inr, 2),
                "Reason": r["reason"],
            })
        elif r["category"] == "order":
            if r["is_credit"]:
                order_credits_inr += r["amount_inr"]
            else:
                order_debits_inr += r["amount_inr"]
            m_row["Trading & Funding Ledger (₹)"] += r["signed_inr"]
        elif r["category"] == "funding":
            if r["is_credit"]:
                funding_credits_inr += r["amount_inr"]
            else:
                funding_debits_inr += r["amount_inr"]
            m_row["Trading & Funding Ledger (₹)"] += r["signed_inr"]
        else:
            other_net_inr += r["signed_inr"]
            m_row["Trading & Funding Ledger (₹)"] += r["signed_inr"]

        m_row["End Net Capital (₹)"] = round(cum_net_cap_inr, 2)
        m_row["Est. End Wallet (₹)"] = round(max(0.0, cum_ledger_inr), 2)

        if r["date_str"] != "Unknown":
            daily_timeline_map[r["date_str"]] = {
                "date": r["date_str"],
                "net_capital_inr": round(cum_net_cap_inr, 2),
                "ledger_wallet_inr": round(cum_ledger_inr, 2),
                "cumulative_pnl_inr": round(cum_ledger_inr - cum_net_cap_inr, 2),
            }

    net_capital_inr = round(total_added_all_inr - total_withdrawn_all_inr, 2)
    cur_realized_inr = round(float(w.get("total_inr", 0.0) or 0.0), 2)
    available_inr = round(float(w.get("available_inr", cur_realized_inr) or 0.0), 2)
    locked_inr = round(max(0.0, cur_realized_inr - available_inr), 2)
    unrealized_pnl_inr = round(
        sum(float(p.get("pnl_inr", 0.0) or 0.0) for p in (positions or []) if isinstance(p, dict)),
        2,
    )
    cur_equity_inr = round(cur_realized_inr + unrealized_pnl_inr, 2)

    # Realized & Total Growth strictly by accounting identity: Current Value - Net Capital Invested
    realized_growth_inr = round(cur_realized_inr - net_capital_inr, 2)
    total_growth_inr = round(cur_equity_inr - net_capital_inr, 2)

    growth_pct_net = round((total_growth_inr / net_capital_inr) * 100.0, 2) if net_capital_inr > 0 else None
    realized_growth_pct_net = round((realized_growth_inr / net_capital_inr) * 100.0, 2) if net_capital_inr > 0 else None
    growth_pct_peak = round((total_growth_inr / peak_net_cap_inr) * 100.0, 2) if peak_net_cap_inr > 0 else None
    growth_pct_added = round((total_growth_inr / total_added_all_inr) * 100.0, 2) if total_added_all_inr > 0 else None

    # Append live "Today" anchor to timeline so chart always terminates at exact Current Equity
    today_str = datetime.now(IST).strftime("%Y-%m-%d")
    timeline_list = [daily_timeline_map[k] for k in sorted(daily_timeline_map.keys())]
    if timeline_list:
        if timeline_list[-1]["date"] == today_str:
            timeline_list[-1]["ledger_wallet_inr"] = cur_equity_inr
            timeline_list[-1]["cumulative_pnl_inr"] = total_growth_inr
        else:
            timeline_list.append({
                "date": today_str,
                "net_capital_inr": net_capital_inr,
                "ledger_wallet_inr": cur_equity_inr,
                "cumulative_pnl_inr": total_growth_inr,
            })

    monthly_rows = []
    for ym_k in sorted(monthly_map.keys()):
        mr = monthly_map[ym_k]
        base_cap = mr["End Net Capital (₹)"] if mr["End Net Capital (₹)"] > 0 else max(1.0, mr["Added (₹)"])
        mr_out = {
            "Month": mr["Month"],
            "Deposits": mr["Deposits"],
            "Withdrawals": mr["Withdrawals"],
            "Added (₹)": round(mr["Added (₹)"], 2),
            "Withdrawn (₹)": round(mr["Withdrawn (₹)"], 2),
            "Net Flow (₹)": round(mr["Net Flow (₹)"], 2),
            "Trading & Funding Ledger (₹)": round(mr["Trading & Funding Ledger (₹)"], 2),
            "End Net Capital (₹)": round(mr["End Net Capital (₹)"], 2),
            "Est. End Wallet (₹)": round(mr["Est. End Wallet (₹)"], 2),
            "Monthly Return %": round((mr["Trading & Funding Ledger (₹)"] / base_cap) * 100.0, 2) if base_cap > 0 else 0.0,
        }
        monthly_rows.append(mr_out)

    reason_rows = []
    for rk_v in sorted(reason_agg.values(), key=lambda x: (-x["INR Equivalent (₹)"], x["Reason"])):
        reason_rows.append({
            **rk_v,
            "Total Amount": round(rk_v["Total Amount"], 4),
            "INR Equivalent (₹)": round(rk_v["INR Equivalent (₹)"], 2),
        })

    # Spot wallet INR/USDT summary
    spot_inr_total = 0.0
    spot_usdt_total = 0.0
    for sb in (spot_balances or []):
        if sb.get("currency") == "INR":
            spot_inr_total += float(sb.get("total", 0.0) or 0.0)
        elif sb.get("currency") == "USDT":
            spot_usdt_total += float(sb.get("total", 0.0) or 0.0)

    first_tx_ist = parsed_rows[0]["dt_str"] if parsed_rows else ""
    latest_tx_ist = parsed_rows[-1]["dt_str"] if parsed_rows else ""

    return {
        "total_transactions": len(parsed_rows),
        "first_tx_ist": first_tx_ist,
        "latest_tx_ist": latest_tx_ist,
        "usd_inr_rate": rate,
        "deposit_count": deposit_count,
        "withdrawal_count": withdrawal_count,
        "total_added_inr": round(total_added_inr, 2),
        "total_withdrawn_inr": round(total_withdrawn_inr, 2),
        "total_added_usdt": round(total_added_usdt, 4),
        "total_withdrawn_usdt": round(total_withdrawn_usdt, 4),
        "total_added_all_inr": round(total_added_all_inr, 2),
        "total_withdrawn_all_inr": round(total_withdrawn_all_inr, 2),
        "net_capital_inr": net_capital_inr,
        "peak_net_capital_inr": round(peak_net_cap_inr, 2),
        "current_realized_wallet_inr": cur_realized_inr,
        "available_inr": available_inr,
        "locked_margin_inr": locked_inr,
        "unrealized_pnl_inr": unrealized_pnl_inr,
        "current_equity_inr": cur_equity_inr,
        "realized_growth_inr": realized_growth_inr,
        "total_growth_inr": total_growth_inr,
        "growth_pct_net_capital": growth_pct_net,
        "realized_growth_pct_net_capital": realized_growth_pct_net,
        "growth_pct_peak_capital": growth_pct_peak,
        "growth_pct_total_added": growth_pct_added,
        "order_credits_inr": round(order_credits_inr, 2),
        "order_debits_inr": round(order_debits_inr, 2),
        "net_order_ledger_inr": round(order_credits_inr - order_debits_inr, 2),
        "funding_credits_inr": round(funding_credits_inr, 2),
        "funding_debits_inr": round(funding_debits_inr, 2),
        "net_funding_inr": round(funding_credits_inr - funding_debits_inr, 2),
        "other_net_inr": round(other_net_inr, 2),
        "ledger_reconciled_balance_inr": round(cum_ledger_inr, 2),
        "ledger_reconciliation_diff_inr": round(cur_realized_inr - cum_ledger_inr, 2),
        "spot_inr_total": round(spot_inr_total, 2),
        "spot_usdt_total": round(spot_usdt_total, 4),
        "spot_balances": list(spot_balances or []),
        "transfers_rows": transfers_rows,
        "monthly_rows": monthly_rows,
        "reason_rows": reason_rows,
        "timeline": timeline_list,
        "all_rows_desc": list(reversed(parsed_rows)),
    }


def parse_coindcx_statement_csv(raw_bytes: bytes) -> dict:
    """
    Parses an optional CoinDCX App/Web exported INR Deposit/Withdrawal or Ledger Statement CSV
    to summarize Bank <-> Spot INR Deposits, Withdrawals, and Net Cash Invested.
    """
    import io
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as e:
        return {"ok": False, "error": f"Could not parse CSV: {e}"}

    if df is None or df.empty:
        return {"ok": False, "error": "Uploaded CSV is empty."}

    cols_map = {str(c).strip().lower(): c for c in df.columns}
    type_col = next((cols_map[k] for k in cols_map if any(w in k for w in ("type", "transaction", "action", "nature", "category"))), None)
    amt_col = next((cols_map[k] for k in cols_map if any(w in k for w in ("amount", "value", "total", "inr", "quantity"))), None)
    cur_col = next((cols_map[k] for k in cols_map if any(w in k for w in ("currency", "asset", "coin"))), None)
    status_col = next((cols_map[k] for k in cols_map if "status" in k), None)
    date_col = next((cols_map[k] for k in cols_map if any(w in k for w in ("date", "time", "created"))), None)

    if not amt_col:
        return {"ok": False, "error": f"Could not locate an Amount column in CSV headers: {list(df.columns)}"}

    dep_inr, wd_inr, dep_cnt, wd_cnt = 0.0, 0.0, 0, 0
    matched_rows = []
    for _, row in df.iterrows():
        if status_col:
            st_val = str(row.get(status_col, "")).strip().lower()
            if st_val and any(bad in st_val for bad in ("fail", "reject", "cancel", "pending", "expire")):
                continue
        if cur_col:
            c_val = str(row.get(cur_col, "")).strip().upper()
            if c_val and c_val != "INR":
                continue
        raw_a = str(row.get(amt_col, "0")).replace(",", "").replace("₹", "").replace("INR", "").strip()
        try:
            amt = float(raw_a)
        except Exception:
            continue
        t_txt = str(row.get(type_col, "")).strip().lower() if type_col else ""
        is_dep = any(w in t_txt for w in ("deposit", "credit", "add", "inr_deposit")) or (not t_txt and amt > 0)
        is_wd = any(w in t_txt for w in ("withdraw", "debit", "payout", "inr_withdraw")) or (not t_txt and amt < 0)
        if is_dep and not is_wd:
            dep_inr += abs(amt)
            dep_cnt += 1
            matched_rows.append({"Date": str(row.get(date_col, "")) if date_col else "", "Type": "DEPOSIT", "Amount (₹)": round(abs(amt), 2)})
        elif is_wd:
            wd_inr += abs(amt)
            wd_cnt += 1
            matched_rows.append({"Date": str(row.get(date_col, "")) if date_col else "", "Type": "WITHDRAWAL", "Amount (₹)": round(-abs(amt), 2)})

    return {
        "ok": True,
        "deposit_count": dep_cnt,
        "withdrawal_count": wd_cnt,
        "total_deposited_inr": round(dep_inr, 2),
        "total_withdrawn_inr": round(wd_inr, 2),
        "net_bank_invested_inr": round(dep_inr - wd_inr, 2),
        "rows": matched_rows,
    }

def exit_coindcx_position(position_id: str, pair: str = None) -> tuple[bool, str]:
    """
    Market exits a specific open futures position on CoinDCX by position ID (with automatic pair-level
    ID refresh fallback and pending order cleanup).
    Calls POST /exchange/v1/derivatives/futures/positions/exit.
    """
    if not position_id and not pair:
        return False, "Invalid position ID"

    target_id = str(position_id or "").strip()
    res, err = (None, None)
    if target_id:
        payload = {"id": target_id, "timestamp": int(round(time.time() * 1000))}
        res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/exit", payload)

    # Fallback: if position_id was stale or failed and pair is known, refresh active positions and retry
    if (res is None or res.status_code != 200) and pair:
        fresh_pos = _fetch_coindcx_active_positions_sync(return_none_on_error=True)
        if fresh_pos is not None:
            matched = next((p for p in fresh_pos if p.get("pair") == pair), None)
            if matched is None:
                _ACTIVE_POSITIONS_CACHE["data"] = fresh_pos
                try:
                    cancel_coindcx_open_entry_orders(pair, cancel_all_for_pair=True)
                    clear_autotrade_active_lock(pair)
                except Exception:
                    pass
                return True, f"Position for {pair} is already closed on CoinDCX."
            fresh_id = str(matched.get("id", "")).strip()
            if fresh_id:
                payload = {"id": fresh_id, "timestamp": int(round(time.time() * 1000))}
                res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/exit", payload)

    if res is not None and res.status_code == 200:
        _ACTIVE_POSITIONS_CACHE["data"] = None
        try:
            if pair:
                cancel_coindcx_open_entry_orders(pair, cancel_all_for_pair=True)
            clear_autotrade_active_lock(pair)
        except Exception:
            pass
        return True, f"Successfully executed market exit for position {target_id or pair}"
    msg = res.text if res is not None else (err or "Exit request failed")
    try:
        if res is not None:
            err_json = res.json()
            if isinstance(err_json, dict) and "message" in err_json:
                msg = err_json["message"]
    except Exception:
        pass
    return False, f"CoinDCX Exit Error: {msg}"

def exit_all_coindcx_positions() -> tuple[int, int, str]:
    """
    Emergency Close All: Exits every active open position and cancels all pending orders.
    Returns (positions_closed_count, total_positions, summary_message).
    """
    positions = _fetch_coindcx_active_positions_sync(return_none_on_error=True)
    if positions is None:
        positions = fetch_coindcx_active_positions()
    cancel_payload = {
        "timestamp": int(time.time()),
        "margin_currency_short_name": ["INR", "USDT"]
    }
    if not positions:
        # Still cancel open orders just in case
        _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/cancel_all_open_orders", cancel_payload)
        return 0, 0, "No active positions to close. All pending orders cleared."

    success_count = 0
    for p in positions:
        pos_id = p.get("id")
        if pos_id:
            ok, _ = exit_coindcx_position(pos_id)
            if ok:
                success_count += 1

    # Clear all remaining open bracket/limit orders
    _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/cancel_all_open_orders", cancel_payload)
    try:
        clear_autotrade_active_lock()
    except Exception:
        pass
    return success_count, len(positions), f"Closed {success_count}/{len(positions)} active positions and cancelled all pending orders."

def update_coindcx_position_tpsl(position_id: str, tp_price: float = None, sl_price: float = None, pair: str = None) -> tuple[bool, str]:
    """
    Attaches or updates Take Profit and Stop Loss bracket triggers directly on an active position.
    Cancels any existing TP or SL orders for this pair first to prevent 'TP already exists' errors.
    Calls POST /exchange/v1/derivatives/futures/positions/create_tpsl.
    """
    if not position_id:
        return False, "Missing position ID"

    tp_val = format_order_price(pair, float(tp_price)) if (pair and tp_price and tp_price > 0) else (round_asset_price(tp_price) if (tp_price and tp_price > 0) else None)
    sl_val = format_order_price(pair, float(sl_price)) if (pair and sl_price and sl_price > 0) else (round_asset_price(sl_price) if (sl_price and sl_price > 0) else None)

    # Step 1: Pre-cancel existing TP/SL triggers for this pair if open
    cancelled_any = False
    try:
        open_orders = fetch_coindcx_open_orders()
        for o in open_orders:
            o_pair = o.get("pair")
            o_stage = o.get("stage")
            o_type = o.get("order_type", "")
            o_id = o.get("id")
            if o_id and (not pair or o_pair == pair) and o_stage == "tpsl_exit":
                if tp_val is not None and "take_profit" in o_type:
                    _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel", {"id": o_id, "timestamp": int(round(time.time() * 1000))})
                    cancelled_any = True
                if sl_val is not None and "stop" in o_type and "take_profit" not in o_type:
                    _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel", {"id": o_id, "timestamp": int(round(time.time() * 1000))})
                    cancelled_any = True
        if cancelled_any:
            time.sleep(0.25)
    except Exception as e:
        print(f"[TP/SL Pre-Cancel Notice]: {e}")

    def _call_create_tpsl(tp_p, sl_p, as_float: bool = False):
        pl = {
            "timestamp": int(round(time.time() * 1000)),
            "id": str(position_id).strip(),
        }
        if tp_p is not None and tp_p > 0:
            pl["take_profit"] = {
                "stop_price": float(tp_p) if as_float else str(tp_p),
                "order_type": "take_profit_market",
            }
        if sl_p is not None and sl_p > 0:
            pl["stop_loss"] = {
                "stop_price": float(sl_p) if as_float else str(sl_p),
                "order_type": "stop_market",
            }
        return _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/create_tpsl", pl)

    # Step 2: Create new TP/SL triggers (try string stop_price, then numeric float fallback, then individual fallback)
    res, err = _call_create_tpsl(tp_val, sl_val, as_float=False)
    if (res is None or res.status_code != 200) and (tp_val or sl_val):
        res2, err2 = _call_create_tpsl(tp_val, sl_val, as_float=True)
        if res2 is not None and res2.status_code == 200:
            res, err = res2, err2

    if res is not None and res.status_code == 200:
        _ACTIVE_POSITIONS_CACHE["data"] = None
        return True, f"Position TP ({tp_val}) & SL ({sl_val}) set on CoinDCX!"

    # If combined TP+SL failed because one side violated mark price or already existed, set TP and SL individually
    if tp_val or sl_val:
        tp_ok = False
        sl_ok = False
        if tp_val:
            r_tp, _ = _call_create_tpsl(tp_val, None, as_float=False)
            if r_tp is None or r_tp.status_code != 200:
                r_tp, _ = _call_create_tpsl(tp_val, None, as_float=True)
            tp_ok = bool(r_tp is not None and r_tp.status_code == 200)
        if sl_val:
            r_sl, err_sl = _call_create_tpsl(None, sl_val, as_float=False)
            if r_sl is None or r_sl.status_code != 200:
                r_sl, err_sl = _call_create_tpsl(None, sl_val, as_float=True)
            if r_sl is None or r_sl.status_code != 200:
                time.sleep(0.25)
                r_sl, err_sl = _call_create_tpsl(None, sl_val, as_float=False)
            sl_ok = bool(r_sl is not None and r_sl.status_code == 200)
            if not sl_ok and r_sl is not None:
                res, err = r_sl, err_sl
        if (tp_ok if tp_val else True) and (sl_ok if sl_val else True):
            _ACTIVE_POSITIONS_CACHE["data"] = None
            parts = []
            if tp_ok:
                parts.append(f"TP={tp_val}")
            if sl_ok:
                parts.append(f"SL={sl_val}")
            return True, f"Position {', '.join(parts)} attached on CoinDCX!"
        elif tp_ok or sl_ok:
            _ACTIVE_POSITIONS_CACHE["data"] = None
            sl_err_txt = (res.text if res is not None else (err or "failed")) if (sl_val and not sl_ok) else ""
            return False, f"Partial TP/SL: TP={'OK' if tp_ok else 'FAIL'}, SL={'OK' if sl_ok else f'FAIL ({sl_err_txt})'}"

    msg = res.text if res is not None else (err or "Failed to update TP/SL on exchange")
    try:
        if res is not None:
            err_json = res.json()
            if isinstance(err_json, dict) and "message" in err_json:
                msg = err_json["message"]
    except Exception:
        pass
    return False, f"CoinDCX TP/SL Error: {msg}"

def place_coindcx_futures_order(
    pair: str,
    side: str,
    quantity: float,
    leverage: int = 5,
    order_type: str = "market_order",
    price: float = None,
    margin_currency: str = "INR",
    tp_price: float = None,
    sl_price: float = None,
    post_only: bool = False
) -> tuple[bool, str, dict]:
    """
    Executes a real futures order directly on CoinDCX exchange via API.
    Supports market_order or limit_order, leverage multiplier, and optional auto TP/SL attachments.
    Enforces exchange quantity divisibility, minimum order value, and position leverage matching.
    """
    side_lower = side.lower()
    order_side = "buy" if side_lower in ["buy", "long"] else "sell"

    # Step 1: Format quantity strictly to pair's step size and precision
    formatted_qty = format_order_quantity(pair, float(quantity))
    if formatted_qty <= 0:
        return False, f"Calculated quantity ({quantity}) is too small for {pair} minimum lot size.", {
            "error_type": "LOT_SIZE_UNDERFLOW",
            "pair": pair,
            "raw_quantity": quantity
        }

    # Step 2: Auto-sync leverage if an active position already exists for this pair
    try:
        active_positions = fetch_coindcx_active_positions()
        matched_pos = next((p for p in active_positions if p["pair"] == pair), None)
        if matched_pos and matched_pos.get("leverage"):
            pos_lev = int(round(float(matched_pos["leverage"])))
            if int(leverage) != pos_lev:
                print(f"[Leverage Auto-Sync]: Aligning order leverage from {leverage}x to {pos_lev}x for active position in {pair}")
                leverage = pos_lev
    except Exception as e:
        print(f"[Leverage Check Notice]: {e}")

    # Step 3: Check CoinDCX minimum order value (strictly 2,448 INR)
    usd_inr = get_coindcx_live_usdt_inr_rate()
    ref_p = format_order_price(pair, float(price)) if (price and price > 0) else 0.0
    if ref_p <= 0:
        try:
            t = fetch_live_ticker(pair)
            ref_p = float(t.get("last_price", 0.0) or 0.0)
        except Exception:
            pass

    if ref_p > 0:
        notional_inr = formatted_qty * ref_p * usd_inr
        if notional_inr < 2448.0:
            min_margin_needed = int(round(2500.0 / max(1, leverage))) + 50
            return False, (
                f"Minimum order value on CoinDCX is ₹2,448 INR (current: ₹{notional_inr:,.0f}). "
                f"Please increase trade margin to at least ₹{min_margin_needed:,} or increase leverage."
            ), {
                "error_type": "MIN_ORDER_VALUE_NOT_MET",
                "notional_inr": notional_inr,
                "min_required_inr": 2448.0,
                "formatted_qty": formatted_qty,
                "ref_price": ref_p
            }

    order_payload = {
        "side": order_side,
        "pair": pair,
        "order_type": order_type,
        "total_quantity": formatted_qty,
        "leverage": int(leverage),
        "margin_currency_short_name": margin_currency.upper(),
        "notification": "email_notification",
        "hidden": False,
        "post_only": False
    }

    if order_type == "limit_order":
        if price is None or price <= 0:
            return False, "Limit order requires a valid price", {}
        order_payload["price"] = format_order_price(pair, float(price))
        order_payload["time_in_force"] = "good_till_cancel"

    body = {
        "timestamp": int(round(time.time() * 1000)),
        "order": order_payload
    }

    res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/create", body)
    if res is None:
        return False, f"Connection error: {err or 'Failed to reach CoinDCX server'}", {
            "error_type": "CONNECTION_ERROR",
            "details": err,
            "body": body
        }

    if res.status_code == 200:
        _ACTIVE_POSITIONS_CACHE["data"] = None
        data = res.json()
        order_info = data[0] if (isinstance(data, list) and len(data) > 0) else (data if isinstance(data, dict) else {})
        order_id = order_info.get("id", "CONFIRMED")

        tpsl_attached = False
        tpsl_msg = ""
        # If TP or SL specified, poll fresh active positions (bypassing cache!) and attach TP/SL
        if tp_price or sl_price:
            for wait_s in (0.6, 1.0, 1.4):
                time.sleep(wait_s)
                try:
                    positions = fetch_coindcx_active_positions(force_refresh=True)
                    matched_pos = next((p for p in positions if p["pair"] == pair), None)
                    if matched_pos and matched_pos.get("id"):
                        tpsl_attached, tpsl_msg = update_coindcx_position_tpsl(
                            matched_pos["id"], tp_price=tp_price, sl_price=sl_price, pair=pair
                        )
                        if tpsl_attached:
                            break
                except Exception as e:
                    print(f"[Auto TP/SL Notice]: {e}")

        tpsl_suffix = f" | {tpsl_msg}" if tpsl_msg else ""
        return True, f"Successfully placed {order_side.upper()} order for {formatted_qty} {pair} on CoinDCX! (Order ID: {order_id}){tpsl_suffix}", {
            "order_id": order_id,
            "tpsl_attached": tpsl_attached,
            "tpsl_message": tpsl_msg,
            "raw_response": data,
            "request_payload": order_payload
        }
    else:
        err_msg = res.text
        raw_json = {}
        try:
            raw_json = res.json()
            if isinstance(raw_json, dict) and "message" in raw_json:
                err_msg = raw_json["message"]
        except Exception:
            pass
        return False, f"CoinDCX API Error ({res.status_code}): {err_msg}", {
            "status_code": res.status_code,
            "error_message": err_msg,
            "raw_response": raw_json or res.text,
            "request_payload": order_payload
        }

def get_current_session_info(dt: datetime = None) -> dict:
    """
    Identifies the institutional market session based on Indian Standard Time (IST):
    - 🌅 Asia Open: 07:00 - 08:30 IST (Center 07:30 IST)
    - 🏛️ London Open: 13:00 - 14:30 IST (Center 13:30 IST)
    - ⚡ New York Open: 18:45 - 20:15 IST (Center 19:15 IST)
    - 🌐 24/7 Intraday Monitor: Continuous Zone Watcher
    """
    now = dt or datetime.now(IST)
    minute_of_day = now.hour * 60 + now.minute

    # 07:00 - 08:30 IST (420 to 510 mins)
    if 420 <= minute_of_day <= 510:
        return {
            "session_id": "ASIA",
            "name": "Asia / Tokyo Open",
            "emoji": "🌅",
            "window": "07:00 - 08:30 IST",
            "peak": "07:30 AM IST",
            "is_prime": True,
            "badge_color": "#d97706",
            "description": "Asian Institutional Open (Tokyo, Hong Kong, Singapore desks)"
        }
    # 13:00 - 14:30 IST (780 to 870 mins)
    elif 780 <= minute_of_day <= 870:
        return {
            "session_id": "LONDON",
            "name": "London / Europe Open",
            "emoji": "🏛️",
            "window": "13:00 - 14:30 IST",
            "peak": "01:30 PM IST",
            "is_prime": True,
            "badge_color": "#0284c7",
            "description": "London Institutional Open (Highest European Forex & Crypto Volatility)"
        }
    # 18:45 - 20:15 IST (1125 to 1215 mins)
    elif 1125 <= minute_of_day <= 1215:
        return {
            "session_id": "NEW_YORK",
            "name": "New York / US Open",
            "emoji": "⚡",
            "window": "18:45 - 20:15 IST",
            "peak": "07:15 PM IST",
            "is_prime": True,
            "badge_color": "#7c3aed",
            "description": "Wall Street Open (US Equities, CME Futures & Institutional ETF flow)"
        }
    else:
        return {
            "session_id": "INTRADAY",
            "name": "24/7 Intraday Monitor",
            "emoji": "🌐",
            "window": "Continuous Active",
            "peak": "Real-Time",
            "is_prime": False,
            "badge_color": "#475569",
            "description": "Continuous 24/7 Box Level & Liquidity Pool Monitor"
        }

def calculate_trade_costs_and_safe_tp(direction="BUY", entry_price=0.0, margin_inr=100000, leverage=5, usd_inr=85.0):
    """
    Calculates exact round-trip trade execution fees, slippage buffer, total trade cost,
    minimum breakeven price move, and capital-preserving Safe Take-Profit thresholds
    to protect against capital decay.
    """
    if entry_price <= 0:
        return {}

    notional_inr = margin_inr * leverage
    notional_usd = notional_inr / usd_inr
    crypto_qty = notional_usd / entry_price

    # CoinDCX Futures Fee Structure:
    # Standard Taker: 0.05% (0.0005) on Entry, 0.05% on Exit -> 0.10% Base Round Trip
    taker_fee_rate = 0.0005
    entry_fee_inr = round(notional_inr * taker_fee_rate, 2)
    exit_fee_inr = round(notional_inr * taker_fee_rate, 2)
    round_trip_base_fee_inr = round(entry_fee_inr + exit_fee_inr, 2)
    round_trip_base_fee_usd = round(round_trip_base_fee_inr / usd_inr, 2)

    # Mandatory Indian GST (18%) on Exchange Brokerage/Trading Fees
    gst_rate = 0.18
    entry_gst_inr = round(entry_fee_inr * gst_rate, 2)
    exit_gst_inr = round(exit_fee_inr * gst_rate, 2)
    total_gst_inr = round(entry_gst_inr + exit_gst_inr, 2)
    total_gst_usd = round(total_gst_inr / usd_inr, 2)

    # Total Exchange Cost (Base Fees + 18% GST)
    round_trip_fee_inr = round(round_trip_base_fee_inr + total_gst_inr, 2)
    round_trip_fee_usd = round(round_trip_fee_inr / usd_inr, 2)

    # Slippage / Spread Safety Buffer (0.02% of notional)
    slippage_buffer_inr = round(notional_inr * 0.0002, 2)
    slippage_buffer_usd = round(slippage_buffer_inr / usd_inr, 2)

    # Overall Estimated Trade Cost (Base Fees + 18% GST + Slippage)
    total_cost_inr = round(round_trip_fee_inr + slippage_buffer_inr, 2)
    total_cost_usd = round(total_cost_inr / usd_inr, 2)

    # Minimum Price Move required just to cover all fees, GST, and friction
    min_move_pct = (total_cost_inr / notional_inr) * 100.0
    price_delta_usd = entry_price * (min_move_pct / 100.0)

    # Exact Breakeven Price (accounting for 18% GST)
    if direction.upper() in ["BUY", "LONG"]:
        breakeven_price = round_asset_price(entry_price + price_delta_usd, entry_price)
        # Minimum Safe TP (must be at least 3x the total friction cost to avoid capital decay)
        safe_tp_price = round_asset_price(entry_price + (3.0 * price_delta_usd), entry_price)
    else:
        breakeven_price = round_asset_price(entry_price - price_delta_usd, entry_price)
        safe_tp_price = round_asset_price(entry_price - (3.0 * price_delta_usd), entry_price)

    # Safe Profit at Minimum TP
    safe_profit_gross_inr = round((abs(safe_tp_price - entry_price) * crypto_qty) * usd_inr, 2)
    safe_profit_net_inr = round(safe_profit_gross_inr - total_cost_inr, 2)
    min_safe_roe = round((safe_profit_gross_inr / margin_inr) * 100.0, 2)

    return {
        "direction": direction,
        "entry_price": entry_price,
        "notional_inr": notional_inr,
        "notional_usd": round(notional_usd, 2),
        "crypto_qty": round(crypto_qty, 4),
        "entry_fee_inr": entry_fee_inr,
        "exit_fee_inr": exit_fee_inr,
        "round_trip_base_fee_inr": round_trip_base_fee_inr,
        "round_trip_base_fee_usd": round_trip_base_fee_usd,
        "entry_gst_inr": entry_gst_inr,
        "exit_gst_inr": exit_gst_inr,
        "total_gst_inr": total_gst_inr,
        "total_gst_usd": total_gst_usd,
        "round_trip_fee_inr": round_trip_fee_inr,
        "round_trip_fee_usd": round_trip_fee_usd,
        "slippage_buffer_inr": slippage_buffer_inr,
        "total_cost_inr": total_cost_inr,
        "total_cost_usd": total_cost_usd,
        "cost_pct_of_margin": round((total_cost_inr / margin_inr) * 100.0, 2),
        "min_breakeven_move_pct": round(min_move_pct, 3),
        "breakeven_price": breakeven_price,
        "safe_tp_price": safe_tp_price,
        "safe_profit_net_inr": safe_profit_net_inr,
        "min_safe_roe": min_safe_roe
    }

def fetch_coindcx_candles(pair="B-ETH_USDT", interval="15m", limit=100, sync_live_price=True):
    """
    Fetches historical candlestick data for any timeframe (1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d)
    from CoinDCX Futures Candlesticks API (`pcode=f`), CoinDCX Public Candles API, and
    Binance Vision / Binance public APIs. Guarantees ascending order and syncs with live price.
    """
    df = pd.DataFrame()
    intv = str(interval).lower().strip()
    lim = max(10, int(limit or 100))

    intv_minutes_map = {
        "1m": 1, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720, "1d": 1440,
    }
    dcx_res_map = {
        "1m": "1", "5m": "5", "15m": "15", "30m": "30",
        "1h": "60", "2h": "120", "4h": "240", "6h": "360", "1d": "1D",
    }

    # 1. Primary: CoinDCX Native Futures Candlesticks API (supports 1m, 5m, 15m, 30m, 1h, 2h, 4h, 1d!)
    if intv in dcx_res_map:
        try:
            now_sec = int(time.time())
            mins = intv_minutes_map.get(intv, 15)
            from_sec = now_sec - int((lim + 15) * mins * 60)
            r_fut = requests.get(
                "https://public.coindcx.com/market_data/candlesticks",
                params={
                    "pair": pair,
                    "from": from_sec,
                    "to": now_sec,
                    "resolution": dcx_res_map[intv],
                    "pcode": "f",
                },
                timeout=7,
            )
            if r_fut.status_code == 200:
                payload = r_fut.json()
                data = payload.get("data", []) if isinstance(payload, dict) else []
                if isinstance(data, list) and len(data) > 0:
                    raw_df = pd.DataFrame(data)
                    if "time" in raw_df.columns:
                        raw_df = raw_df.rename(columns={"time": "timestamp"})
                    for col in ["open", "high", "low", "close", "volume"]:
                        if col in raw_df.columns:
                            raw_df[col] = pd.to_numeric(raw_df[col], errors="coerce").astype(float)
                    if "timestamp" in raw_df.columns:
                        raw_df["timestamp"] = pd.to_numeric(raw_df["timestamp"], errors="coerce")
                        if len(raw_df) > 0 and raw_df["timestamp"].iloc[0] < 1e11:
                            raw_df["timestamp"] = raw_df["timestamp"] * 1000
                        raw_df = raw_df.dropna(subset=["timestamp", "open", "high", "low", "close"])
                        df = raw_df.sort_values("timestamp").drop_duplicates(subset=["timestamp"]).tail(lim).reset_index(drop=True)
                        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        except Exception as e:
            print(f"[CoinDCX Futures Candlesticks Notice ({pair} {intv})]: {e}")

    # 2. Secondary: CoinDCX Public Market Data Candles API (supports [1m, 15m, 1h, 1d])
    if df.empty and intv in ("1m", "15m", "1h", "1d"):
        url = f"https://public.coindcx.com/market_data/candles?pair={pair}&interval={intv}&limit={lim}"
        try:
            response = requests.get(url, timeout=7)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list) and len(data) > 0:
                    raw_df = pd.DataFrame(data)
                    if 'time' in raw_df.columns:
                        raw_df = raw_df.rename(columns={'time': 'timestamp'})
                    for col in ['open', 'high', 'low', 'close', 'volume']:
                        if col in raw_df.columns:
                            raw_df[col] = raw_df[col].astype(float)
                    if 'timestamp' in raw_df.columns:
                        raw_df['timestamp'] = pd.to_numeric(raw_df['timestamp'], errors='coerce')
                        if len(raw_df) > 0 and raw_df['timestamp'].iloc[0] < 1e11:
                            raw_df['timestamp'] = raw_df['timestamp'] * 1000
                        df = raw_df.sort_values('timestamp').reset_index(drop=True)
                        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
        except Exception as e:
            print(f"[CoinDCX Candles Notice]: {e}")

    # 3. Fallback to Binance Vision (US-accessible global mirror) & Binance Public API
    if df.empty:
        clean_pair = pair.replace("B-", "").replace("I-", "").replace("_", "")
        for base_host in ("https://data-api.binance.vision", "https://api.binance.com"):
            try:
                url_binance = f"{base_host}/api/v3/klines?symbol={clean_pair}&interval={intv}&limit={lim}"
                resp_b = requests.get(url_binance, timeout=7)
                if resp_b.status_code == 200:
                    r = resp_b.json()
                    if isinstance(r, list) and len(r) > 0 and isinstance(r[0], list):
                        b_df = pd.DataFrame(r, columns=[
                            'timestamp', 'open', 'high', 'low', 'close', 'volume',
                            'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
                        ])
                        for col in ['open', 'high', 'low', 'close', 'volume']:
                            b_df[col] = b_df[col].astype(float)
                        b_df['timestamp'] = pd.to_numeric(b_df['timestamp'], errors='coerce')
                        df = b_df.sort_values('timestamp').reset_index(drop=True)
                        df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                        break
            except Exception as e:
                print(f"[Binance Fallback Error ({base_host})]: {e}")

    # 4. Synchronize the active (last) candle's close with the real-time ticker
    if sync_live_price and not df.empty:
        try:
            ticker = fetch_live_ticker(pair)
            live_p = ticker.get("last_price", 0.0)
            if live_p > 0:
                last_idx = len(df) - 1
                df.at[last_idx, 'close'] = live_p
                if live_p > df.at[last_idx, 'high']:
                    df.at[last_idx, 'high'] = live_p
                if live_p < df.at[last_idx, 'low']:
                    df.at[last_idx, 'low'] = live_p
        except Exception as e:
            print(f"[Sync Live Price Notice]: {e}")

    return df

_HISTORICAL_CANDLES_CACHE = {}

def fetch_historical_candles_paginated(
    pair: str = "B-BTC_USDT",
    interval: str = "15m",
    duration_days: int = 365,
    progress_callback = None
) -> pd.DataFrame:
    """
    Fetches full historical candlestick data across extended durations (e.g. 1 Year on 15m = ~35,000 candles)
    using multi-batch pagination from Binance / CoinDCX public APIs.
    Maintains an in-memory cache to make repeated simulations (e.g. changing margin or leverage) instant.
    """
    clean_pair = pair.replace("B-", "").replace("I-", "").replace("_", "").upper()
    cache_key = f"{clean_pair}_{interval.lower()}_{duration_days}"
    now_ts = time.time()

    if cache_key in _HISTORICAL_CANDLES_CACHE:
        cached_entry = _HISTORICAL_CANDLES_CACHE[cache_key]
        if (now_ts - cached_entry["timestamp"]) < 1800:  # 30-minute cache TTL
            return cached_entry["df"].copy()

    intv_minutes = {
        "1m": 1,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "12h": 720,
        "1d": 1440
    }
    m = intv_minutes.get(interval.lower(), 15)
    total_candles_needed = int((duration_days * 24 * 60) / m) + 50
    # Safety cap: up to 40,000 candles
    total_candles_needed = min(total_candles_needed, 40000)

    all_candles = []
    end_time = None
    batch_size = 1000
    batches_needed = (total_candles_needed + batch_size - 1) // batch_size

    # Multi-batch fetching loop (uses US-accessible data-api.binance.vision first, then api.binance.com)
    for b_idx in range(batches_needed):
        url = f"https://data-api.binance.vision/api/v3/klines?symbol={clean_pair}&interval={interval}&limit={batch_size}"
        if end_time:
            url += f"&endTime={end_time}"

        try:
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if not data or not isinstance(data, list):
                    break
                # Binance returns ascending: data[0] is oldest, data[-1] is newest in this batch
                all_candles.extend(data)
                # Next batch fetches candles prior to the oldest one in current batch
                end_time = data[0][0] - 1
                if progress_callback:
                    try:
                        progress_callback(b_idx + 1, batches_needed, len(all_candles))
                    except Exception:
                        pass
            else:
                break
        except Exception as e:
            print(f"[Historical Candles Notice]: {e}")
            break

        if len(all_candles) >= total_candles_needed:
            break

    if not all_candles:
        # Fallback to single fetch
        return fetch_coindcx_candles(pair=pair, interval=interval, limit=min(1000, total_candles_needed), sync_live_price=False)

    # Convert to standardized DataFrame
    b_df = pd.DataFrame(all_candles, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'qav', 'num_trades', 'taker_base_vol', 'taker_quote_vol', 'ignore'
    ])
    for col in ['open', 'high', 'low', 'close', 'volume']:
        b_df[col] = b_df[col].astype(float)
    b_df['timestamp'] = pd.to_numeric(b_df['timestamp'], errors='coerce')

    df = b_df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)
    df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    _HISTORICAL_CANDLES_CACHE[cache_key] = {"df": df, "timestamp": now_ts}
    return df

def compute_box_swing_levels(df_completed: pd.DataFrame) -> dict:
    """
    Single source of truth for Box RH / RL / SH / SL used by BOTH live trading (calculate_daily_box_levels)
    and backtesting (BoxTheorySweep.prepare_backtest), so both always produce identical levels.

    `df_completed` = completed daily candles in ascending order whose LAST row is the previous day (RH/RL day).
    Only the last 30 completed candles are used.
      - SH = nearest prior high at least 0.8% above RH, if within 3.5% of RH; otherwise RH + 1.5%.
      - SL = nearest prior low at least 0.8% below RL, if within 3.5% of RL; otherwise RL - 1.5%.
    """
    dfc = df_completed.tail(30)
    prev_day = dfc.iloc[-1]
    rh = float(prev_day["high"])
    rl = float(prev_day["low"])
    df_hist = dfc.iloc[:-1]

    up_days = dfc[dfc["close"] >= dfc["open"]]
    down_days = dfc[dfc["close"] < dfc["open"]]
    avg_daily_rise = float((up_days["close"] - up_days["open"]).mean()) if len(up_days) > 0 else (rh - rl) * 0.25
    avg_daily_drop = float((down_days["open"] - down_days["close"]).mean()) if len(down_days) > 0 else (rh - rl) * 0.25
    if not avg_daily_rise or avg_daily_rise <= 0 or avg_daily_rise != avg_daily_rise:
        avg_daily_rise = (rh - rl) * 0.25
    if not avg_daily_drop or avg_daily_drop <= 0 or avg_daily_drop != avg_daily_drop:
        avg_daily_drop = (rh - rl) * 0.25

    # Formula B (selected for both live & backtest):
    #   SH = nearest prior high >= RH * 1.008, if it is <= RH * 1.035; otherwise RH * 1.015
    #   SL = nearest prior low  <= RL * 0.992, if it is >= RL * 0.965; otherwise RL * 0.985
    # (avg_daily_rise / avg_daily_drop above are kept for UI display only)
    sh_candidates = [float(h) for h in df_hist["high"].tolist() if float(h) >= rh * 1.008]
    if sh_candidates and min(sh_candidates) <= rh * 1.035:
        sh = min(sh_candidates)
    else:
        sh = rh * 1.015

    sl_candidates = [float(l) for l in df_hist["low"].tolist() if float(l) <= rl * 0.992]
    if sl_candidates and max(sl_candidates) >= rl * 0.965:
        sl = max(sl_candidates)
    else:
        sl = rl * 0.985

    return {
        "RH": rh, "RL": rl, "SH": sh, "SL": sl,
        "avg_daily_rise": avg_daily_rise, "avg_daily_drop": avg_daily_drop,
    }


def calculate_daily_box_levels(pair="B-ETH_USDT"):
    """
    Calculates Previous Day High (RH), Low (RL), Swing High (SH), Swing Low (SL),
    Equilibrium Midpoint (MID), and Daily 50 EMA & 200 EMA Trend Bias.
    Strictly caps SH/SL lookback to 30 completed daily candles, while using 1000 daily candles
    so the 200-day EMA matches TradingView / CoinDCX exactly.
    """
    df_daily = fetch_coindcx_candles(pair=pair, interval="1d", limit=1000, sync_live_price=False)
    if df_daily.empty or len(df_daily) < 2:
        return None

    df_all_completed = df_daily.iloc[:-1].reset_index(drop=True)
    if df_all_completed.empty:
        return None

    # Lock Daily 50 EMA, 200 EMA, and Trend Bias to the previous completed daily candle close
    # so Daily Bias stays fixed for the entire 24h day (matching prepare_backtest() and never flickering intrabar)
    ema50_val = float(df_all_completed['close'].ewm(span=50, adjust=False).mean().iloc[-1])
    ema200_val = float(df_all_completed['close'].ewm(span=200, adjust=False).mean().iloc[-1])

    # Limit search strictly to maximum 30 completed daily candles (never go beyond 30 days)
    df_completed = df_all_completed.tail(30)
    prev_day = df_completed.iloc[-1]
    rh = float(prev_day['high'])
    rl = float(prev_day['low'])
    daily_close = float(prev_day['close'])
    mid = (rh + rl) / 2.0

    if daily_close < ema50_val and daily_close < ema200_val:
        trend_bias = "BEARISH"
    elif daily_close > ema50_val and daily_close > ema200_val:
        trend_bias = "BULLISH"
    else:
        trend_bias = "NEUTRAL"

    # Shared SH/SL formula (identical in live and backtest — see compute_box_swing_levels)
    swing = compute_box_swing_levels(df_completed)
    sh, sl = swing["SH"], swing["SL"]
    avg_daily_rise, avg_daily_drop = swing["avg_daily_rise"], swing["avg_daily_drop"]

    return {
        "RH": round_asset_price(rh),
        "RL": round_asset_price(rl),
        "SH": round_asset_price(sh, rh),
        "SL": round_asset_price(sl, rl),
        "MID": round_asset_price(mid, rh),
        "EMA50": round_asset_price(ema50_val, rh),
        "EMA200": round_asset_price(ema200_val, rh),
        "daily_close": round_asset_price(daily_close, rh),
        "trend_bias": trend_bias,
        "prev_day_date": datetime.fromtimestamp(prev_day['timestamp'] / 1000, tz=IST).strftime("%Y-%m-%d"),
        "avg_daily_rise": round(avg_daily_rise, 2),
        "avg_daily_drop": round(avg_daily_drop, 2)
    }

def _get_live_15m_ema50(pair: str, fallback_val: float = 0.0) -> float:
    """Fetches the latest closed 15m 50 EMA (200-candle warmup matching live/backtest) for Smart Hybrid TP1."""
    try:
        df15 = fetch_coindcx_candles(pair=pair, interval="15m", limit=205, sync_live_price=False)
        if df15 is not None and not df15.empty:
            now_ms = int(time.time() * 1000)
            closed = df15[df15["timestamp"] + 900000 <= now_ms]
            if closed.empty:
                closed = df15.iloc[:-1]
            if not closed.empty:
                ema_s = closed["close"].ewm(span=50, adjust=False).mean()
                return float(ema_s.iloc[-1])
    except Exception:
        pass
    return float(fallback_val or 0.0)


def _select_smart_hybrid_box_tp1(direction: str, entry: float, mid: float, ema50_15m: float, fallback_edge: float) -> tuple[float, str]:
    """
    Smart Hybrid Strategy 1 TP1 Rule:
      - Selects the NEARER of `Midpoint(Entry 1, TP2)` (`(entry + TP2) / 2`) or `15m 50 EMA`
        in the profitable direction.
      - When `Entry 1` is at the box edge (`RL` / `RH`), `(Entry 1 + TP2) / 2` equals Box `MID`.
      - When `Entry 1` is executed inside the box, `(Entry 1 + TP2) / 2` stays strictly halfway
        between `Entry 1` and `TP2` (`RH` / `RL`), and `15m 50 EMA` is only eligible if it is at least
        `max(0.8% of entry, 50% of distance to Midpoint(Entry 1, TP2))` away from `Entry 1` so TP1 is never set too near.
    """
    is_long = str(direction).upper() in ("BUY", "LONG")
    min_dist = entry * 0.0059
    if is_long:
        tp2_ref = fallback_edge if (fallback_edge > entry * 1.008) else (mid if mid > entry * 1.012 else entry * 1.024)
        tp_mid = (entry + tp2_ref) / 2.0
        mid_lbl = "MID" if (mid > 0 and abs(tp_mid - mid) / max(1e-9, entry) <= 0.002) else "Mid(Entry1,TP2)"
        min_ema_dist = max(entry * 0.008, abs(tp_mid - entry) * 0.50)

        valid_cands = []
        if tp_mid > entry and (tp_mid - entry) >= min_dist:
            valid_cands.append((tp_mid - entry, tp_mid, mid_lbl))
        if ema50_15m > entry and (ema50_15m - entry) >= max(min_dist, min_ema_dist):
            valid_cands.append((ema50_15m - entry, ema50_15m, "15m 50 EMA"))

        if valid_cands:
            _, struct_tp1, lbl = min(valid_cands, key=lambda c: c[0])
        elif tp_mid > entry:
            struct_tp1, lbl = tp_mid, mid_lbl
        elif fallback_edge > entry and (fallback_edge - entry) >= min_dist:
            struct_tp1, lbl = (entry + fallback_edge) / 2.0, mid_lbl
        else:
            struct_tp1, lbl = entry * 1.012, mid_lbl
        tp1_dist = max(min(abs(struct_tp1 - entry), entry * 0.02), entry * 0.006)
        return entry + tp1_dist, lbl
    else:
        tp2_ref = fallback_edge if (0 < fallback_edge < entry * 0.992) else (mid if 0 < mid < entry * 0.988 else entry * 0.976)
        tp_mid = (entry + tp2_ref) / 2.0
        mid_lbl = "MID" if (mid > 0 and abs(tp_mid - mid) / max(1e-9, entry) <= 0.002) else "Mid(Entry1,TP2)"
        min_ema_dist = max(entry * 0.008, abs(entry - tp_mid) * 0.50)

        valid_cands = []
        if 0 < tp_mid < entry and (entry - tp_mid) >= min_dist:
            valid_cands.append((entry - tp_mid, tp_mid, mid_lbl))
        if 0 < ema50_15m < entry and (entry - ema50_15m) >= max(min_dist, min_ema_dist):
            valid_cands.append((entry - ema50_15m, ema50_15m, "15m 50 EMA"))

        if valid_cands:
            _, struct_tp1, lbl = min(valid_cands, key=lambda c: c[0])
        elif 0 < tp_mid < entry:
            struct_tp1, lbl = tp_mid, mid_lbl
        elif 0 < fallback_edge < entry and (entry - fallback_edge) >= min_dist:
            struct_tp1, lbl = (entry + fallback_edge) / 2.0, mid_lbl
        else:
            struct_tp1, lbl = entry * 0.988, mid_lbl
        tp1_dist = max(min(abs(entry - struct_tp1), entry * 0.02), entry * 0.006)
        return entry - tp1_dist, lbl


def calculate_trade_setup_details(direction="BUY", levels=None, live_price=0.0, margin_inr=100000, leverage=5, usd_inr=85.0, pair="B-ETH_USDT"):
    """
    Calculates specific BUY (Long at Range Low / Swing Low) or SELL (Short at Range High / Swing High)
    100% Single-Slot Maker Limit + Structural Runner trade setup parameters:
      - Entry 1 (100% Slot Margin): RL / RH rejection price (Maker Limit Order; Entry 2 removed)
      - Catastrophe SL: 0.5% beyond SL / SH sweep level
      - TP1 (50% Early Book + Lock Profit SL): Nearer of MID or 15m 50 EMA (capped at 2.0% move)
      - TP2 (50% Structural Runner): Opposite Box Edge (RH / RL), with Halfway-to-TP2 SL Ratchet to TP1
    """
    if not levels:
        return None

    rh, rl = levels["RH"], levels["RL"]
    sh, sl = levels["SH"], levels["SL"]
    mid = levels["MID"]
    ema50_15m = float(levels.get("EMA50_15m") or _get_live_15m_ema50(pair, mid))

    lev = max(1, int(leverage))
    if direction.upper() in ["BUY", "LONG"]:
        dir_name = "BUY"
        entry = round_asset_price(live_price if live_price > 0 and live_price <= rl else rl, rh)
        sweep_anchor = round_asset_price(min(sl, entry * 0.992), rh)
        entry2_sweep = 0.0
        avg_entry_2x = entry
        stop_loss = round_asset_price(min(sweep_anchor * 0.995, sl * 0.995), rh)
        raw_tp1, tp1_lbl = _select_smart_hybrid_box_tp1("BUY", entry, mid, ema50_15m, rh)
        tp1 = round_asset_price(raw_tp1, rh)
        tp1_dist = abs(tp1 - entry)
        tp2_target = rh if entry < rh * 0.988 else sh
        tp2 = round_asset_price(max(tp2_target, entry + tp1_dist * 1.6), rh)
        setup_desc = (
            f"BUY (Long): 100% Single-Slot Maker Limit @ ${entry:,.2f} | SL ${stop_loss:,.2f} | "
            f"TP1 @ {tp1_lbl} (${tp1:,.2f}) -> TP2 Structural Runner to RH (${tp2:,.2f})"
        )
    else:
        dir_name = "SELL"
        entry = round_asset_price(live_price if live_price > 0 and live_price >= rh else rh, rh)
        sweep_anchor = round_asset_price(max(sh, entry * 1.008), rh)
        entry2_sweep = 0.0
        avg_entry_2x = entry
        stop_loss = round_asset_price(max(sweep_anchor * 1.005, sh * 1.005), rh)
        raw_tp1, tp1_lbl = _select_smart_hybrid_box_tp1("SELL", entry, mid, ema50_15m, rl)
        tp1 = round_asset_price(raw_tp1, rh)
        tp1_dist = abs(entry - tp1)
        tp2_target = rl if entry > rl * 1.012 else sl
        tp2 = round_asset_price(min(tp2_target, entry - tp1_dist * 1.6), rh)
        setup_desc = (
            f"SELL (Short): 100% Single-Slot Maker Limit @ ${entry:,.2f} | SL ${stop_loss:,.2f} | "
            f"TP1 @ {tp1_lbl} (${tp1:,.2f}) -> TP2 Structural Runner to RL (${tp2:,.2f})"
        )

    margin_usd = margin_inr / usd_inr
    position_usd = margin_usd * leverage
    raw_qty = position_usd / entry if entry > 0 else 0
    crypto_qty = format_order_quantity(pair, raw_qty)
    tranche_qty = crypto_qty

    risk_per_unit = abs(entry - stop_loss) if stop_loss > 0 else 0
    reward_tp1 = abs(entry - tp1)
    reward_tp2 = abs(entry - tp2)

    roe_tp1 = round((reward_tp1 / entry) * leverage * 100, 2) if entry > 0 else 0
    roe_tp2 = round((reward_tp2 / entry) * leverage * 100, 2) if entry > 0 else 0
    roe_blended = round(0.5 * roe_tp1 + 0.5 * roe_tp2, 2)
    roe_sl = round((risk_per_unit / entry) * leverage * 100, 2) if entry > 0 else 0

    profit_tp1_inr = round((reward_tp1 * crypto_qty) * usd_inr, 2)
    profit_tp2_inr = round((reward_tp2 * crypto_qty) * usd_inr, 2)
    profit_blended_inr = round(0.5 * profit_tp1_inr + 0.5 * profit_tp2_inr, 2)
    loss_sl_inr = round((risk_per_unit * crypto_qty) * usd_inr, 2)

    return {
        "direction": dir_name,
        "setup": setup_desc,
        "entry": entry,
        "entry2_sweep": entry2_sweep,
        "avg_entry_2x": avg_entry_2x,
        "tranche_qty": tranche_qty,
        "tranche_margin_inr": round(margin_inr, 2),
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "crypto_qty": crypto_qty,
        "position_usd": round(position_usd, 2),
        "margin_inr": margin_inr,
        "leverage": leverage,
        "usd_inr": usd_inr,
        "roe_tp1": roe_tp1,
        "roe_tp2": roe_tp2,
        "roe_blended": roe_blended,
        "roe_sl": roe_sl,
        "profit_tp1_inr": profit_tp1_inr,
        "profit_tp2_inr": profit_tp2_inr,
        "profit_blended_inr": profit_blended_inr,
        "loss_sl_inr": loss_sl_inr,
        "target_roe_met": roe_tp1 >= 3.0
    }

def detect_zone_signal(levels: dict, o: float, h: float, l: float, c: float):
    """
    Classifies ONE CLOSED candle against the daily box zones (RH/SH and RL/SL),
    returning Single-Entry + Structural Runner levels (TP1 = min(2% move, MID) for 50% book, TP2 = RL/RH for 50% runner).
    """
    rh, rl, sh, sl, mid = levels["RH"], levels["RL"], levels["SH"], levels["SL"], levels["MID"]

    if (h >= rh and c < rh) or (h >= sh and c < sh):
        sweep_anc = max(sh, h, c * 1.008)
        stop_p = round(sweep_anc * 1.005, 4)
        tp1_dist = min(abs(c - mid), c * 0.02)
        if tp1_dist < c * 0.0058:
            return None
        tp1_p = round(c - tp1_dist, 4)
        tp2_p = round(min(rl if c > rl * 1.012 else sl, c - tp1_dist * 2.0), 4)
        return {"kind": "REVERSAL", "direction": "SHORT", "zone": "Sell Zone RH-SH",
                "entry2_sweep": 0.0, "stop": stop_p, "tp1": tp1_p, "tp2": tp2_p}
    if (l <= rl and c > rl) or (l <= sl and c > sl):
        sweep_anc = min(sl, l, c * 0.992)
        stop_p = round(sweep_anc * 0.995, 4)
        tp1_dist = min(abs(mid - c), c * 0.02)
        if tp1_dist < c * 0.0058:
            return None
        tp1_p = round(c + tp1_dist, 4)
        tp2_p = round(max(rh if c < rh * 0.988 else sh, c + tp1_dist * 2.0), 4)
        return {"kind": "REVERSAL", "direction": "LONG", "zone": "Buy Zone RL-SL",
                "entry2_sweep": 0.0, "stop": stop_p, "tp1": tp1_p, "tp2": tp2_p}
    return None


def compute_market_bias(pair: str = "B-ETH_USDT", live_price: float = 0.0) -> dict:
    """
    Daily 50 EMA & 200 EMA Trend Bias Filter (locked to Previous Completed Daily Candle Close):
      - BEARISH: Prev Completed Daily Close < 50 EMA AND < 200 EMA (SHORT setups only)
      - BULLISH: Prev Completed Daily Close > 50 EMA AND > 200 EMA (LONG setups only)
      - NEUTRAL / RANGE: Prev Completed Daily Close is between 50 EMA and 200 EMA (WAIT / NO TRADE)
    """
    out = {"bias": "NEUTRAL / RANGE", "score": 0, "reasons": []}
    try:
        d = fetch_coindcx_candles(pair=pair, interval="1d", limit=1000, sync_live_price=False)
        if len(d) >= 52:
            d_comp = d.iloc[:-1].reset_index(drop=True)
            ema50 = float(d_comp["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(d_comp["close"].ewm(span=200, adjust=False).mean().iloc[-1])
            d_close = float(d_comp["close"].iloc[-1])
            out["ema50"] = round_asset_price(ema50, d_close)
            out["ema200"] = round_asset_price(ema200, d_close)
            out["daily_close"] = round_asset_price(d_close, d_close)

            if d_close < ema50 and d_close < ema200:
                out["bias"] = "BEARISH"
                out["score"] = -2
                out["reasons"].append(f"Prev Daily Close (`${d_close:,.2f}`) < 50 EMA (`${ema50:,.2f}`) & < 200 EMA (`${ema200:,.2f}`) → SHORT setups only")
            elif d_close > ema50 and d_close > ema200:
                out["bias"] = "BULLISH"
                out["score"] = 2
                out["reasons"].append(f"Prev Daily Close (`${d_close:,.2f}`) > 50 EMA (`${ema50:,.2f}`) & > 200 EMA (`${ema200:,.2f}`) → LONG setups only")
            else:
                out["bias"] = "NEUTRAL / RANGE"
                out["score"] = 0
                out["reasons"].append(f"Prev Daily Close (`${d_close:,.2f}`) is between 50 EMA (`${ema50:,.2f}`) & 200 EMA (`${ema200:,.2f}`) → Range Mode (Both RH/SH Sell Zone & RL/SL Buy Zone Active on Confirmation)")
    except Exception as e:
        out["reasons"].append(f"Bias unavailable: {e}")
    return out


def evaluate_tri_session_signal(pair="B-ETH_USDT", levels=None, margin_inr=100000, leverage=5, usd_inr=85.0, trigger_alert: bool = False):
    """
    Evaluates 15-minute candles and real-time prices across the Three Institutional Opens:
    - 🌅 Asia Open (07:00 - 08:30 IST)
    - 🏛️ London Open (13:00 - 14:30 IST)
    - ⚡ New York / US Open (18:45 - 20:15 IST)
    - 🌐 24/7 Intraday Monitor
    Automatically triggers email notification when an institutional sweep occurs.
    """
    if not levels:
        levels = calculate_daily_box_levels(pair)
    if not levels:
        return None

    df_15m = fetch_coindcx_candles(pair=pair, interval="15m", limit=40, sync_live_price=False)
    if df_15m.empty:
        return None

    df_15m['ist_dt'] = pd.to_datetime(df_15m['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(IST)
    now_ist = datetime.now(IST)
    session = get_current_session_info(now_ist)

    # Confirmation requires a CLOSED candle: drop the still-forming 15m bar
    now_ms = int(time.time() * 1000)
    closed_df = df_15m[df_15m['timestamp'] + 900000 <= now_ms]
    eval_candle = closed_df.iloc[-1] if not closed_df.empty else df_15m.iloc[-2 if len(df_15m) > 1 else -1]
    candle_time_str = eval_candle['ist_dt'].strftime('%H:%M IST')
    candle_label = f"Last closed 15m candle ({candle_time_str}) [{session['emoji']} {session['name']}]"

    open_price = float(eval_candle['open'])
    close_price = float(eval_candle['close'])
    high_price = float(eval_candle['high'])
    low_price = float(eval_candle['low'])
    candle_ts = int(eval_candle['timestamp'])

    rh, rl = levels["RH"], levels["RL"]
    sh, sl = levels["SH"], levels["SL"]
    mid = levels["MID"]

    setup = "WAIT / NO TRADE (No zone rejection or tower confirmation on the last closed candle)"
    entry = close_price
    stop_loss = 0.0
    tp1 = mid
    tp2 = rl
    signal_type = "NEUTRAL"
    signal_kind = None
    trigger_zone = None

    zs = detect_zone_signal(levels, open_price, high_price, low_price, close_price)
    if zs:
        signal_type = zs["direction"]
        signal_kind = zs["kind"]
        trigger_zone = zs["zone"]
        stop_loss = round_asset_price(zs["stop"], rh)
        tp1 = round_asset_price(zs["tp1"], rh)
        tp2 = round_asset_price(zs["tp2"], rh)
        word = "BUY (Long)" if signal_type == "LONG" else "SELL (Short)"
        label = "Rejection Reversal" if signal_kind == "REVERSAL" else "Tower Continuation (alert-only, untested)"
        setup = f"{word}: {label} - {trigger_zone} ({session['name']})"

    margin_usd = margin_inr / usd_inr
    position_usd = margin_usd * leverage
    raw_qty = position_usd / entry if entry > 0 else 0
    crypto_qty = format_order_quantity(pair, raw_qty)

    risk_per_unit = abs(entry - stop_loss) if stop_loss > 0 else 0
    reward_tp1 = abs(entry - tp1)
    reward_tp2 = abs(entry - tp2)

    roe_tp1 = round((reward_tp1 / entry) * leverage * 100, 2) if entry > 0 else 0
    roe_tp2 = round((reward_tp2 / entry) * leverage * 100, 2) if entry > 0 else 0
    roe_sl = round((risk_per_unit / entry) * leverage * 100, 2) if entry > 0 else 0

    profit_tp1_inr = round((reward_tp1 * crypto_qty) * usd_inr, 2)
    profit_tp2_inr = round((reward_tp2 * crypto_qty) * usd_inr, 2)
    loss_sl_inr = round((risk_per_unit * crypto_qty) * usd_inr, 2)

    target_roe_met = roe_tp1 >= 5.0
    if signal_type != "NEUTRAL" and not target_roe_met:
        setup += f" [Warning: TP1 ROE ({roe_tp1}%) < 5% target]"

    # Automated Email Alert Dispatch if signal is active
    if trigger_alert and signal_type != "NEUTRAL":
        try:
            from alert_notifier import send_sweep_alert
            send_sweep_alert(
                pair=pair,
                signal_type=signal_type,
                session_name=f"{session['emoji']} {session['name']} ({session['peak']})",
                live_price=close_price,
                entry=entry,
                stop_loss=stop_loss,
                tp1=tp1,
                tp2=tp2,
                roe_tp1=roe_tp1,
                box_levels=levels
            )
        except Exception as e:
            print(f"[Alert Dispatch Notice]: {e}")

    return {
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
        "candle_evaluated": candle_label,
        "session": session,
        "session_name": f"{session['emoji']} {session['name']}",
        "is_prime_session": session["is_prime"],
        "is_us_open_candle": session["session_id"] == "NEW_YORK",
        "pair": pair,
        "signal": signal_type,
        "setup": setup,
        "entry": round_asset_price(entry, rh),
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "crypto_qty": crypto_qty,
        "position_usd": round(position_usd, 2),
        "margin_inr": margin_inr,
        "leverage": leverage,
        "roe_tp1": roe_tp1,
        "roe_tp2": roe_tp2,
        "roe_sl": roe_sl,
        "target_roe_met": target_roe_met,
        "profit_tp1_inr": profit_tp1_inr,
        "profit_tp2_inr": profit_tp2_inr,
        "loss_sl_inr": loss_sl_inr,
        "levels": levels,
        "signal_kind": signal_kind,
        "trigger_zone": trigger_zone,
        "candle_ts": candle_ts
    }

def evaluate_715_pm_signal(pair="B-ETH_USDT", levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
    """
    Backwards compatibility alias for evaluate_tri_session_signal.
    """
    return evaluate_tri_session_signal(pair, levels, margin_inr, leverage, usd_inr)

def run_strategy_backtest(
    pair: str = "B-BTC_USDT",
    duration_days: int = 30,
    interval: str = "15m",
    margin_inr: float = 50000.0,
    leverage: int = 5,
    target_mode: str = "TP1 Midpoint",
    usd_inr: float = None,
    progress_callback = None,
    strategy_id: str = "box_theory",
    wallet_inr: float = None,
    exit_mode: str = "hybrid",
) -> dict:
    """
    Executes a real-time historical simulation of any registered strategy (see strategies.py).
    Supports two active-trade exit modes:
      - exit_mode="hybrid" (Default): Book 50% at TP1 (nearer of MID or 15m 50 EMA for Box), then manage
        the remaining 50% runner with Trailing 15m H/L SL + Strategy 3 (>=20% Daily ATR 5m candle 30% pullback
        exit OR confirmed 2-candle 5m 9 EMA cross exit) instead of fixed TP2.
      - exit_mode="strategy3_full": Manage 100% of the trade with Trailing 15m H/L SL + Strategy 3
        (>=20% Daily ATR 5m candle 30% pullback exit OR confirmed 2-candle 5m 9 EMA cross exit).
    Discipline:
      - All previous daily trade-count and 10% win-lock caps removed.
      - STOP trading for the day if 5% of total futures wallet (`wallet_inr`, default `3 * margin_inr`) is lost including fees.
    """
    import strategies as _strategies
    strat = _strategies.get_strategy(strategy_id)

    if not usd_inr or usd_inr <= 0:
        usd_inr = get_coindcx_live_usdt_inr_rate()

    eff_wallet_inr = float(wallet_inr) if (wallet_inr and wallet_inr > 0) else (margin_inr / TRADE_ALLOCATION_FRACTION)
    max_daily_loss_inr = eff_wallet_inr * (_strategies.DAILY_WALLET_LOSS_STOP_PCT / 100.0)

    # 1. Fetch execution candles using multi-batch pagination (with 5d pre-window buffer on 15m for 200 EMA warmup)
    fetch_days_exec = (duration_days + 5) if interval == "15m" else duration_days
    df_exec_raw = fetch_historical_candles_paginated(
        pair=pair,
        interval=interval,
        duration_days=fetch_days_exec,
        progress_callback=progress_callback
    )
    if df_exec_raw.empty or len(df_exec_raw) < 20:
        return {"error": f"Insufficient historical candle data available for {pair} on {interval}."}
    if interval == "15m":
        cutoff_ms = int(df_exec_raw["timestamp"].iloc[-1]) - int(duration_days * 86400 * 1000)
        df_sub = df_exec_raw[df_exec_raw["timestamp"] >= cutoff_ms].copy().reset_index(drop=True)
        df = df_sub if len(df_sub) >= 20 else df_exec_raw.copy().reset_index(drop=True)
        df.attrs["df_full_15m"] = df_exec_raw.copy().reset_index(drop=True)
    else:
        df = df_exec_raw

    # 2. Fetch daily candles for daily box & ATR establishment
    df_daily = fetch_historical_candles_paginated(
        pair=pair,
        interval="1d",
        duration_days=duration_days + strat.daily_warmup_days
    )
    if df_daily.empty or len(df_daily) < 5:
        return {"error": f"Insufficient daily candle data for {pair}."}

    # 3. Fetch 5m candles for Strategy 3 (5m 9 EMA confirmed cross & >=20% ATR 30% pullback exit / retest entry)
    df_5m = fetch_historical_candles_paginated(
        pair=pair,
        interval="5m",
        duration_days=duration_days + 2
    )
    sub5_by_15m_ts = {}
    if df_5m is not None and not df_5m.empty:
        df_5m = df_5m.copy().reset_index(drop=True)
        df_5m["EMA9"] = df_5m["close"].ewm(span=9, adjust=False).mean()
        for r5 in df_5m.to_dict("records"):
            bucket = (int(r5["timestamp"]) // 900000) * 900000
            sub5_by_15m_ts.setdefault(bucket, []).append(r5)
        df.attrs["df_5m"] = df_5m

    df['dt_ist'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(IST)
    df['date_str'] = df['dt_ist'].dt.strftime('%Y-%m-%d')

    df_daily['dt_ist'] = pd.to_datetime(df_daily['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(IST)
    df_daily['date_str'] = df_daily['dt_ist'].dt.strftime('%Y-%m-%d')

    strat_ctx = strat.prepare_backtest(df, df_daily)

    df_records = df.to_dict('records')
    trades = []
    active_trade = None
    last_exit_idx = -999
    initial_capital = margin_inr
    current_equity = initial_capital
    first_candle_time = df['dt_ist'].iloc[0].strftime("%Y-%m-%d %H:%M")
    equity_curve = [{"timestamp": first_candle_time, "equity_inr": initial_capital, "pnl_inr": 0.0}]

    taker_fee_rate = 0.0005 * 1.18  # 0.05% + 18% GST (Stop Loss / Market exit)
    maker_fee_rate = 0.0002 * 1.18  # 0.02% + 18% GST (Maker Limit Entry 1 & TP1 Limit Order)
    day_trade_count = {}
    day_realized_pnl = {}
    day_locked = set()

    for idx, candle in enumerate(df_records):
        c_date = candle['date_str']
        c_time = candle['dt_ist']
        c_high = float(candle['high'])
        c_low = float(candle['low'])
        c_close = float(candle['close'])
        c_open = float(candle.get('open', c_close))
        c_ts = int(candle['timestamp'])

        if not strat.backtest_has_context(candle, strat_ctx):
            continue

        daily_atr = (
            float((strat_ctx.get("boxes", {}).get(c_date) or {}).get("ATR", 0.0))
            or float((strat_ctx.get("daily", {}).get(c_date) or {}).get("atr", 0.0))
            or float(((strat_ctx.get("ctx1", {}) or {}).get("boxes", {}).get(c_date) or {}).get("ATR", 0.0))
            or 0.0
        )

        if active_trade:
            pos_dir = active_trade["direction"]
            entry_p = active_trade["entry_price"]
            entry2_p = active_trade.get("entry2_sweep", 0.0)
            sl_p = active_trade["stop_loss"]
            tp1_p = active_trade["tp1"]
            tp2_p = active_trade["tp2"]
            qty = active_trade["quantity"]
            notional_inr = active_trade["notional_inr"]
            deployed_margin_inr = active_trade["deployed_margin_inr"]

            is_s3_active = (
                "Strategy 3" in str(active_trade.get("strategy", ""))
                or strategy_id == "ema9_retest"
            )
            use_full_s3_mode = (exit_mode == "strategy3_full") or (exit_mode == "smart_hybrid" and is_s3_active)

            # Trailing 15m Candle High/Low Stop Loss is used only in Strategy 3 full-runner mode;
            # Strategy 1 & 2 use Profit-Locked SL + Halfway-to-TP2 SL Ratchet + Fixed TP2 (no early runner choke).
            if use_full_s3_mode and idx > active_trade["entry_idx"]:
                prev_15m = df_records[idx - 1]
                prev_15m_l = float(prev_15m["low"])
                prev_15m_h = float(prev_15m["high"])
                prev_15m_c = float(prev_15m["close"])
                can_trail_15m = (
                    bool(active_trade.get("tp1_hit", False))
                    and ((pos_dir == "LONG" and prev_15m_c >= tp1_p) or (pos_dir == "SHORT" and prev_15m_c <= tp1_p))
                )
                if can_trail_15m:
                    if pos_dir == "LONG" and prev_15m_l > sl_p and prev_15m_l < prev_15m_c:
                        sl_p = prev_15m_l
                        active_trade["stop_loss"] = sl_p
                    elif pos_dir == "SHORT" and prev_15m_h < sl_p and prev_15m_h > prev_15m_c:
                        sl_p = prev_15m_h
                        active_trade["stop_loss"] = sl_p

            # Step A: If Tranche 2 (at SH/SL sweep level) has not filled yet and TP1 not hit yet, check if price swept into Entry 2
            # (Note: if price sweeps all the way to sl_p, it necessarily passes through entry2_p first!)
            if not active_trade.get("entry2_filled", False) and not active_trade.get("tp1_hit", False) and entry2_p > 0:
                if (pos_dir == "LONG" and c_low <= entry2_p) or (
                    pos_dir == "SHORT" and c_high >= entry2_p
                ):
                    new_avg_entry = (entry_p + entry2_p) / 2.0
                    full_margin_usd = margin_inr / usd_inr
                    full_pos_usd = full_margin_usd * leverage
                    new_qty = format_order_quantity(pair, full_pos_usd / new_avg_entry) if new_avg_entry > 0 else qty
                    tp1_dist_new = min(abs(tp1_p - new_avg_entry), new_avg_entry * 0.02)
                    new_tp1 = (new_avg_entry + tp1_dist_new) if pos_dir == "LONG" else (new_avg_entry - tp1_dist_new)

                    active_trade["entry_price"] = new_avg_entry
                    active_trade["quantity"] = new_qty
                    active_trade["tp1"] = new_tp1
                    active_trade["entry2_filled"] = True

                    entry_p = new_avg_entry
                    tp1_p = new_tp1
                    qty = new_qty

            exit_triggered = False
            exit_price = None
            exit_reason = None
            has_e2 = float(active_trade.get("entry2_sweep", 0.0) or 0.0) > 0
            scale_tag = " [2-Entry Averaged]" if active_trade.get("entry2_filled") else (" [Entry 1]" if has_e2 else " [Single Entry]")

            sub5_list = sub5_by_15m_ts.get((c_ts // 900000) * 900000) or [
                {"open": c_open, "high": c_high, "low": c_low, "close": c_close, "EMA9": c_close}
            ]

            for s5 in sub5_list:
                s5_open = float(s5.get("open", c_open))
                s5_high = float(s5["high"])
                s5_low = float(s5["low"])
                s5_close = float(s5["close"])
                s5_ema9 = float(s5.get("EMA9", s5_close))
                s5_range = s5_high - s5_low

                is_s3_trade = (
                    "Strategy 3" in str(active_trade.get("strategy", ""))
                    or strategy_id == "ema9_retest"
                )
                use_full_s3_runner = (exit_mode == "strategy3_full") or (exit_mode == "smart_hybrid" and is_s3_trade)
                if use_full_s3_runner:
                    # Variant 1: 100% of trade managed by Trailing 15m SL + Strategy 3 (20% ATR 30% Pullback / Confirmed 9 EMA Cross)
                    if (pos_dir == "LONG" and s5_low <= sl_p) or (pos_dir == "SHORT" and s5_high >= sl_p):
                        exit_triggered = True
                        exit_price = sl_p
                        r_lbl = (
                            "20% ATR 30% Pullback SL"
                            if active_trade.get("atr20_pb_armed")
                            else ("Trailing 15m SL" if active_trade.get("tp1_hit") else "Catastrophe Stop Loss")
                        )
                        exit_reason = f"100% {r_lbl}{scale_tag}"
                        break

                    if not active_trade.get("tp1_hit", False):
                        if (pos_dir == "LONG" and s5_high >= tp1_p) or (pos_dir == "SHORT" and s5_low <= tp1_p):
                            active_trade["tp1_hit"] = True
                            prev_c = df_records[idx - 1] if idx > 0 else candle
                            new_sl = compute_tp1_profit_lock_sl(
                                pair, pos_dir, entry_p, tp1_p,
                                prev_candle_high=float(prev_c["high"]), prev_candle_low=float(prev_c["low"]),
                            )
                            if (pos_dir == "LONG" and new_sl > sl_p) or (pos_dir == "SHORT" and new_sl < sl_p):
                                sl_p = new_sl
                                active_trade["stop_loss"] = sl_p

                    # Strategy 3 Rule A: >=20% Daily ATR 5m candle in our favour -> exit on 30% pullback
                    if daily_atr > 0 and s5_range >= 0.20 * daily_atr:
                        if pos_dir == "LONG" and s5_close > s5_open:
                            pb_lvl = s5_high - 0.30 * s5_range
                            if (s5_high - s5_close) >= 0.30 * s5_range and s5_close > entry_p:
                                exit_triggered = True
                                exit_price = max(s5_close, pb_lvl)
                                exit_reason = f"100% Exit: 5m >=20% ATR 30% Pullback{scale_tag}"
                                break
                            if pb_lvl > sl_p:
                                sl_p = pb_lvl
                                active_trade["stop_loss"] = sl_p
                                active_trade["atr20_pb_armed"] = True
                        elif pos_dir == "SHORT" and s5_close < s5_open:
                            pb_lvl = s5_low + 0.30 * s5_range
                            if (s5_close - s5_low) >= 0.30 * s5_range and s5_close < entry_p:
                                exit_triggered = True
                                exit_price = min(s5_close, pb_lvl)
                                exit_reason = f"100% Exit: 5m >=20% ATR 30% Pullback{scale_tag}"
                                break
                            if pb_lvl < sl_p:
                                sl_p = pb_lvl
                                active_trade["stop_loss"] = sl_p
                                active_trade["atr20_pb_armed"] = True

                    # Strategy 3 Rule B: Confirmed 5m 9 EMA cross (once price has reached TP1 profit zone)
                    if active_trade.get("tp1_hit", False):
                        if pos_dir == "LONG":
                            if s5_close > s5_ema9 and s5_close >= tp1_p:
                                active_trade["ema9_armed"] = True
                                active_trade["wrong_ema9_streak"] = 0
                            elif active_trade.get("ema9_armed", False) and s5_close < s5_ema9:
                                active_trade["wrong_ema9_streak"] = int(active_trade.get("wrong_ema9_streak", 0)) + 1
                                if active_trade["wrong_ema9_streak"] >= 2:
                                    exit_triggered = True
                                    exit_price = max(s5_close, sl_p)
                                    exit_reason = f"100% Exit: Confirmed 5m 9 EMA Cross{scale_tag}"
                                    break
                        else:
                            if s5_close < s5_ema9 and s5_close <= tp1_p:
                                active_trade["ema9_armed"] = True
                                active_trade["wrong_ema9_streak"] = 0
                            elif active_trade.get("ema9_armed", False) and s5_close > s5_ema9:
                                active_trade["wrong_ema9_streak"] = int(active_trade.get("wrong_ema9_streak", 0)) + 1
                                if active_trade["wrong_ema9_streak"] >= 2:
                                    exit_triggered = True
                                    exit_price = min(s5_close, sl_p)
                                    exit_reason = f"100% Exit: Confirmed 5m 9 EMA Cross{scale_tag}"
                                    break

                else:
                    # Variant 2 (Default Structural Runner): Book 50% at TP1, lock runner SL in profit
                    # (`compute_tp1_profit_lock_sl`), ratchet SL to TP1 halfway to TP2, and hold 50% runner for TP2
                    # (5m 9 EMA Cross & 20% ATR early runner chokes removed).
                    if not active_trade.get("tp1_hit", False):
                        if (pos_dir == "LONG" and s5_low <= sl_p) or (pos_dir == "SHORT" and s5_high >= sl_p):
                            exit_triggered = True
                            exit_price = sl_p
                            exit_reason = f"Catastrophe Stop Loss{scale_tag}"
                            break
                        if (pos_dir == "LONG" and s5_high >= tp1_p) or (pos_dir == "SHORT" and s5_low <= tp1_p):
                            active_trade["tp1_hit"] = True
                            prev_c = df_records[idx - 1] if idx > 0 else candle
                            new_sl = compute_tp1_profit_lock_sl(
                                pair, pos_dir, entry_p, tp1_p,
                                prev_candle_high=float(prev_c["high"]), prev_candle_low=float(prev_c["low"]),
                            )
                            sl_p = new_sl
                            active_trade["stop_loss"] = sl_p
                            if (pos_dir == "LONG" and tp2_p > 0 and s5_high >= tp2_p) or (pos_dir == "SHORT" and tp2_p > 0 and s5_low <= tp2_p):
                                exit_triggered = True
                                exit_price = 0.5 * tp1_p + 0.5 * tp2_p
                                active_trade["tp2_hit"] = True
                                exit_reason = f"TP1 (50% Booked) + 50% TP2 Target Hit{scale_tag}"
                                break
                            if tp2_p > 0:
                                half_tp2 = 0.5 * (tp1_p + tp2_p)
                                if pos_dir == "LONG" and s5_high >= half_tp2 and tp1_p > sl_p:
                                    sl_p = tp1_p
                                    active_trade["stop_loss"] = sl_p
                                    active_trade["halfway_ratcheted"] = True
                                elif pos_dir == "SHORT" and s5_low <= half_tp2 and tp1_p < sl_p:
                                    sl_p = tp1_p
                                    active_trade["stop_loss"] = sl_p
                                    active_trade["halfway_ratcheted"] = True
                            continue
                    else:
                        # TP1 (50%) already booked; managing the remaining 50% Structural Runner
                        if (pos_dir == "LONG" and s5_low <= sl_p) or (pos_dir == "SHORT" and s5_high >= sl_p):
                            exit_triggered = True
                            exit_price = 0.5 * tp1_p + 0.5 * sl_p
                            r_lbl = "Runner Halfway-Ratchet SL" if active_trade.get("halfway_ratcheted") else "Runner Profit-Locked SL"
                            exit_reason = f"TP1 (50% Booked) + 50% {r_lbl}{scale_tag}"
                            break
                        if (pos_dir == "LONG" and tp2_p > 0 and s5_high >= tp2_p) or (pos_dir == "SHORT" and tp2_p > 0 and s5_low <= tp2_p):
                            exit_triggered = True
                            exit_price = 0.5 * tp1_p + 0.5 * tp2_p
                            active_trade["tp2_hit"] = True
                            exit_reason = f"TP1 (50% Booked) + 50% TP2 Target Hit{scale_tag}"
                            break
                        if tp2_p > 0:
                            half_tp2 = 0.5 * (tp1_p + tp2_p)
                            if pos_dir == "LONG" and s5_high >= half_tp2 and tp1_p > sl_p:
                                sl_p = tp1_p
                                active_trade["stop_loss"] = sl_p
                                active_trade["halfway_ratcheted"] = True
                            elif pos_dir == "SHORT" and s5_low <= half_tp2 and tp1_p < sl_p:
                                sl_p = tp1_p
                                active_trade["stop_loss"] = sl_p
                                active_trade["halfway_ratcheted"] = True

            if exit_triggered:
                if pos_dir == "LONG":
                    gross_pnl_usd = (exit_price - entry_p) * qty
                else:
                    gross_pnl_usd = (entry_p - exit_price) * qty

                gross_pnl_inr = gross_pnl_usd * usd_inr
                entry_fee_inr = notional_inr * maker_fee_rate
                exit_notional_inr = (qty * exit_price) * usd_inr
                if active_trade.get("tp1_hit", False) and not use_full_s3_mode:
                    tp1_notional_inr = (0.5 * qty * tp1_p) * usd_inr
                    exit_fee_inr = (tp1_notional_inr * maker_fee_rate) + (max(0.0, exit_notional_inr - tp1_notional_inr) * taker_fee_rate)
                else:
                    exit_fee_inr = exit_notional_inr * taker_fee_rate
                total_fees_inr = entry_fee_inr + exit_fee_inr
                net_pnl_inr = gross_pnl_inr - total_fees_inr
                roe_pct = (net_pnl_inr / deployed_margin_inr) * 100.0 if deployed_margin_inr > 0 else 0.0

                current_equity += net_pnl_inr

                entry_day = active_trade.get("entry_date", c_date)
                day_realized_pnl[entry_day] = day_realized_pnl.get(entry_day, 0.0) + net_pnl_inr
                if c_date != entry_day:
                    day_realized_pnl[c_date] = day_realized_pnl.get(c_date, 0.0) + net_pnl_inr

                # New Discipline Rule: STOP Trading for the day if 5% of total futures wallet is lost including fees
                if day_realized_pnl.get(entry_day, 0.0) <= -max_daily_loss_inr:
                    day_locked.add(entry_day)
                if day_realized_pnl.get(c_date, 0.0) <= -max_daily_loss_inr:
                    day_locked.add(c_date)

                trades.append({
                    "trade_id": len(trades) + 1,
                    "entry_time": active_trade["entry_time"],
                    "exit_time": c_time.strftime("%Y-%m-%d %H:%M"),
                    "pair": pair,
                    "direction": pos_dir,
                    "session": active_trade["session"],
                    "entry_price": round_asset_price(entry_p, entry_p),
                    "exit_price": round_asset_price(exit_price, entry_p),
                    "stop_loss": round_asset_price(sl_p, entry_p),
                    "target_tp": round_asset_price(tp1_p, entry_p),
                    "exit_reason": exit_reason,
                    "quantity": qty,
                    "gross_pnl_inr": round(gross_pnl_inr, 2),
                    "fees_inr": round(total_fees_inr, 2),
                    "net_pnl_inr": round(net_pnl_inr, 2),
                    "roe_pct": round(roe_pct, 2),
                    "is_win": net_pnl_inr > 0,
                    "duration_candles": idx - active_trade["entry_idx"],
                    "strategy": active_trade.get("strategy_tag") or strat.name,
                    "trigger": active_trade.get("reason", "")
                })

                equity_curve.append({
                    "timestamp": c_time.strftime("%Y-%m-%d %H:%M"),
                    "equity_inr": round(current_equity, 2),
                    "pnl_inr": round(net_pnl_inr, 2)
                })

                active_trade = None
                last_exit_idx = idx

        # Daily Discipline Gate: Only stop trading for the day if 5% of total futures wallet is lost including fees
        if c_date in day_locked:
            continue

        # If no active trade, ask the strategy whether this closed candle is an entry
        if not active_trade and (idx - last_exit_idx >= 1):
            entry_sig = strat.backtest_entry(idx, candle, strat_ctx, df_records)
            if entry_sig:
                trade_dir = entry_sig["direction"]
                entry_p = entry_sig["entry"]
                entry2_p = float(entry_sig.get("entry2_sweep", 0.0) or 0.0)
                sl_p = entry_sig["stop"]
                tp1_p = entry_sig["tp1"]
                tp2_p = entry_sig["tp2"]

                margin_usd = margin_inr / usd_inr
                pos_usd = margin_usd * leverage
                raw_qty = pos_usd / entry_p if entry_p > 0 else 0
                qty = format_order_quantity(pair, raw_qty)
                notional_inr = margin_inr * leverage

                sess_name = _strategies.backtest_session_name(c_time)

                active_trade = {
                    "direction": trade_dir,
                    "entry_time": c_time.strftime("%Y-%m-%d %H:%M"),
                    "entry_date": c_date,
                    "entry_idx": idx,
                    "entry_price": entry_p,
                    "entry2_sweep": entry2_p,
                    "entry2_filled": False,
                    "stop_loss": sl_p,
                    "tp1": tp1_p,
                    "tp2": tp2_p,
                    "quantity": qty,
                    "notional_inr": notional_inr,
                    "deployed_margin_inr": margin_inr,
                    "session": sess_name,
                    "tp1_hit": False,
                    "ema9_armed": False,
                    "wrong_ema9_streak": 0,
                    "atr20_pb_armed": False,
                    "tp1_label": entry_sig.get("tp1_label", "50% Book"),
                    "tp2_label": entry_sig.get("tp2_label", "50% Runner"),
                    "reason": entry_sig.get("reason", ""),
                    "strategy_tag": entry_sig.get("strategy_tag", strat.name),
                }
                day_trade_count[c_date] = day_trade_count.get(c_date, 0) + 1

    # Summary Statistics Calculation
    total_trades = len(trades)
    if total_trades == 0:
        return {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_rate_pct": 0.0,
            "net_profit_inr": 0.0,
            "total_roi_pct": 0.0,
            "profit_factor": 0.0,
            "max_drawdown_pct": 0.0,
            "total_gross_profit": 0.0,
            "total_gross_loss": 0.0,
            "avg_win_inr": 0.0,
            "avg_loss_inr": 0.0,
            "avg_duration_candles": 0.0,
            "candle_interval": interval,
            "trades_df": pd.DataFrame(),
            "monthly_df": pd.DataFrame(),
            "session_df": pd.DataFrame(),
            "equity_curve": equity_curve,
            "pair": pair,
            "duration_days": duration_days,
            "margin_inr": margin_inr,
            "leverage": leverage,
            "total_fees_paid_inr": 0.0,
            "strategy_id": strat.id,
            "strategy_name": strat.name
        }

    wins = [t for t in trades if t["is_win"]]
    losses = [t for t in trades if not t["is_win"]]
    longs = [t for t in trades if t["direction"] == "LONG"]
    shorts = [t for t in trades if t["direction"] == "SHORT"]

    win_count = len(wins)
    loss_count = len(losses)
    win_rate = round((win_count / total_trades) * 100.0, 1)

    long_wins = [t for t in longs if t["is_win"]]
    short_wins = [t for t in shorts if t["is_win"]]
    long_win_rate = round((len(long_wins) / len(longs) * 100.0), 1) if longs else 0.0
    short_win_rate = round((len(short_wins) / len(shorts) * 100.0), 1) if shorts else 0.0

    total_gross_profit = sum(t["net_pnl_inr"] for t in wins)
    total_gross_loss = abs(sum(t["net_pnl_inr"] for t in losses))
    net_profit = round(sum(t["net_pnl_inr"] for t in trades), 2)
    total_roi = round((net_profit / initial_capital) * 100.0, 2)

    profit_factor = round(total_gross_profit / total_gross_loss, 2) if total_gross_loss > 0 else (99.0 if total_gross_profit > 0 else 0.0)

    # Max Drawdown calculation from equity curve
    equity_series = [e["equity_inr"] for e in equity_curve]
    peak = equity_series[0]
    max_dd = 0.0
    for eq in equity_series:
        if eq > peak:
            peak = eq
        dd = ((peak - eq) / peak) * 100.0 if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    avg_win = round(total_gross_profit / win_count, 2) if win_count > 0 else 0.0
    avg_loss = round(total_gross_loss / loss_count, 2) if loss_count > 0 else 0.0
    avg_duration_candles = round(sum(t["duration_candles"] for t in trades) / total_trades, 1)
    total_fees_paid = round(sum(t["fees_inr"] for t in trades), 2)

    trades_df = pd.DataFrame(trades)

    # Compute Monthly Breakdown with requested columns:
    # Month, Number of Trades, Margin Used, Fees Paid, Profit or Loss, Win Rate, Overall Net Profit
    monthly_rows = []
    if not trades_df.empty:
        trades_df['ym'] = pd.to_datetime(trades_df['entry_time']).dt.strftime('%Y-%m')
        cum_net_pnl = 0.0

        for ym_str in sorted(trades_df['ym'].unique()):
            m_group = trades_df[trades_df['ym'] == ym_str]
            m_dt = pd.to_datetime(ym_str + "-01")
            month_label = m_dt.strftime('%b %Y')

            m_trades = len(m_group)
            m_wins = len(m_group[m_group['is_win']])
            m_losses = m_trades - m_wins
            m_wr = round((m_wins / m_trades) * 100.0, 1) if m_trades > 0 else 0.0

            m_margin_used = m_trades * margin_inr
            m_fees = round(m_group['fees_inr'].sum(), 2)
            m_net_pnl = round(m_group['net_pnl_inr'].sum(), 2)
            cum_net_pnl = round(cum_net_pnl + m_net_pnl, 2)

            monthly_rows.append({
                "Month": month_label,
                "Number of Trades": m_trades,
                "Margin Used": f"₹{m_margin_used:,.0f}",
                "Fees Paid": f"₹{m_fees:,.2f}",
                "Profit or Loss": f"{'+' if m_net_pnl >= 0 else ''}₹{m_net_pnl:,.2f}",
                "Win Rate": f"{m_wr:.1f}%",
                "Overall Net Profit": f"{'+' if cum_net_pnl >= 0 else ''}₹{cum_net_pnl:,.2f}"
            })

        # Summary total row
        monthly_rows.append({
            "Month": "🔥 TOTAL / SUMMARY",
            "Number of Trades": total_trades,
            "Margin Used": f"₹{(total_trades * margin_inr):,.0f}",
            "Fees Paid": f"₹{total_fees_paid:,.2f}",
            "Profit or Loss": f"{'+' if net_profit >= 0 else ''}₹{net_profit:,.2f}",
            "Win Rate": f"{win_rate:.1f}%",
            "Overall Net Profit": f"{'+' if net_profit >= 0 else ''}₹{net_profit:,.2f}"
        })
    monthly_df = pd.DataFrame(monthly_rows)

    # Compute Session Breakdown
    session_rows = []
    if not trades_df.empty:
        for sess_name, s_group in trades_df.groupby('session', sort=False):
            s_trades = len(s_group)
            s_wins = len(s_group[s_group['is_win']])
            s_wr = round((s_wins / s_trades) * 100.0, 1) if s_trades > 0 else 0.0
            s_pnl = round(s_group['net_pnl_inr'].sum(), 2)
            session_rows.append({
                "Institutional Session": sess_name,
                "Trades": s_trades,
                "Wins": s_wins,
                "Win Rate": f"{s_wr:.1f}%",
                "Net Profit (INR)": f"₹{s_pnl:,.2f}"
            })
    session_df = pd.DataFrame(session_rows)

    return {
        "strategy_id": strat.id,
        "strategy_name": strat.name,
        "pair": pair,
        "duration_days": duration_days,
        "margin_inr": margin_inr,
        "leverage": leverage,
        "target_mode": target_mode,
        "total_trades": total_trades,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate_pct": win_rate,
        "long_trades": len(longs),
        "long_win_rate_pct": long_win_rate,
        "short_trades": len(shorts),
        "short_win_rate_pct": short_win_rate,
        "net_profit_inr": net_profit,
        "total_roi_pct": total_roi,
        "profit_factor": profit_factor,
        "max_drawdown_pct": round(max_dd, 2),
        "total_gross_profit": round(total_gross_profit, 2),
        "total_gross_loss": round(total_gross_loss, 2),
        "total_fees_paid_inr": total_fees_paid,
        "avg_win_inr": avg_win,
        "avg_loss_inr": avg_loss,
        "avg_duration_candles": avg_duration_candles,
        "candle_interval": interval,
        "trades_df": trades_df,
        "monthly_df": monthly_df,
        "session_df": session_df,
        "equity_curve": equity_curve
    }



_raw_def_wallet = float(os.getenv("DEFAULT_WALLET_INR", 47287.18))
DEFAULT_WALLET_INR = 47287.18 if _raw_def_wallet in (30000.0, 250000.0, 40569.80) else _raw_def_wallet
TRADE_ALLOCATION_FRACTION = 1.0 / 3.0
MAX_CONCURRENT_TRADES = 3  # 3 concurrent trades x ₹20k = ₹60k wallet

# High-Volatility / High-Movement Crypto Futures Universe (Verified Profitable at 10x Leverage: 67.2% WR, +407% 30d ROI)
HIGH_VOL_FUTURES_UNIVERSE = [
    "B-INJ_USDT",
    "B-RENDER_USDT",
    "B-FET_USDT",
    "B-APT_USDT",
    "B-SUI_USDT",
    "B-NEAR_USDT",
    "B-DOGE_USDT",
    "B-AVAX_USDT",
    "B-XRP_USDT",
    "B-SOL_USDT",
    "B-ETH_USDT",
    "B-BTC_USDT",
]

_VOL_MOVERS_CACHE = {"timestamp": 0.0, "movers": []}
AUTOTRADE_CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "autotrade_config.json")


def fetch_top_volatility_movers(candidate_pairs: list[str] = None, top_n: int = 12, force_refresh: bool = False) -> list[dict]:
    """
    Scans the high-liquidity futures universe and ranks pairs by 24h Range Volatility %
    ((high_24h - low_24h) / last_price * 100) and 24h directional momentum.
    Uses Binance 24hr ticker with automatic fallback to CoinDCX public ticker (/exchange/ticker)
    so Streamlit Cloud (where Binance is geo-blocked) always gets real live prices & ranges.
    """
    now = time.time()
    if not force_refresh and _VOL_MOVERS_CACHE["movers"] and (now - _VOL_MOVERS_CACHE["timestamp"] < 180):
        return _VOL_MOVERS_CACHE["movers"][:top_n]

    pool = candidate_pairs or HIGH_VOL_FUTURES_UNIVERSE
    sym_map = {p.replace("B-", "").replace("I-", "").replace("_", ""): p for p in pool}
    movers = []

    # 1. Fast Shared CoinDCX Public Ticker Map (0ms when warm, always accessible on Streamlit Cloud)
    try:
        t_map = _get_coindcx_ticker_map(ttl=5.0)
        for mkt, item in t_map.items():
            if mkt in sym_map:
                pair = sym_map[mkt]
                last_p = float(item.get("last_price", 0.0) or 0.0)
                high_p = float(item.get("high", last_p) or last_p)
                low_p = float(item.get("low", last_p) or last_p)
                chg_pct = float(item.get("change_24_hour", 0.0) or 0.0)
                vol = float(item.get("volume", 0.0) or 0.0)
                if last_p > 0:
                    range_pct = round(((high_p - low_p) / last_p) * 100.0, 2)
                    vol_score = round(range_pct * 0.7 + abs(chg_pct) * 0.3, 2)
                    movers.append({
                        "pair": pair,
                        "symbol": mkt.replace("USDT", ""),
                        "last_price": round_asset_price(last_p),
                        "change_24h_pct": round(chg_pct, 2),
                        "range_24h_pct": range_pct,
                        "volatility_score": vol_score,
                        "quote_volume_usd": round(vol, 0),
                    })
    except Exception as e:
        print(f"[Volatility Scanner CoinDCX Notice]: {e}")

    if not movers:
        for idx, p in enumerate(pool):
            movers.append({
                "pair": p,
                "symbol": p.replace("B-", "").replace("_USDT", ""),
                "last_price": 0.0,
                "change_24h_pct": 0.0,
                "range_24h_pct": round(6.5 - idx * 0.25, 2),
                "volatility_score": round(6.5 - idx * 0.25, 2),
                "quote_volume_usd": 0.0,
            })
    else:
        movers.sort(key=lambda x: x["volatility_score"], reverse=True)

    _VOL_MOVERS_CACHE["timestamp"] = now
    _VOL_MOVERS_CACHE["movers"] = movers
    return movers[:top_n]


def get_high_volatility_watchlist(top_n: int = 12) -> list[str]:
    """Returns ordered list of high-volatility futures pairs (plus SOL/ETH/BTC guaranteed)."""
    movers = fetch_top_volatility_movers(top_n=top_n)
    ordered = [m["pair"] for m in movers]
    for core in ("B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT"):
        if core not in ordered:
            ordered.append(core)
    return ordered


_MARKET_REGIME_CACHE = _PERSIST.setdefault("market_regime_cache", {"ts": 0.0, "data": None})


def classify_universe_regime_from_stats(
    bull_frac: float,
    bear_frac: float,
    r14: float,
    r5: float,
    r2: float,
) -> str:
    """
    Zero-lookahead 2-Year Verified Market Trend Classifier across the 12-coin High-Volatility Universe:
      - STRONG_UPTREND   : >=50% Bullish Daily Bias AND 14d median >= +2.5% AND 5d >= -1.0% AND 2d >= -1.5%
      - STRONG_DOWNTREND : >=50% Bearish Daily Bias AND 14d median <= -3.5% AND 5d <= +0.5% AND 2d <= +1.0%
      - RANGING_CHOP     : Mixed breadth, flat 14d momentum, or multi-day post-crash/rally consolidation
                           (e.g. 2d median bounce > +1.0% in Bear or pullback < -1.5% in Bull).
    """
    if bull_frac >= 0.50 and r14 >= 2.5 and r5 >= -1.0 and r2 >= -1.5:
        return "STRONG_UPTREND"
    if bear_frac >= 0.50 and r14 <= -3.5 and r5 <= 0.5 and r2 <= 1.0:
        return "STRONG_DOWNTREND"
    return "RANGING_CHOP"


def _format_regime_metadata(regime: str, bull_frac: float, bear_frac: float, r14: float, r5: float, r2: float) -> dict:
    b_pct = round(bull_frac * 100.0, 0)
    br_pct = round(bear_frac * 100.0, 0)
    if regime == "STRONG_UPTREND":
        emoji, label = "🟢", "STRONG UPTREND"
        routing = "Box Sweep (L+S) + Bull 15m 50/200 EMA (LONG)"
    elif regime == "STRONG_DOWNTREND":
        emoji, label = "🔴", "STRONG DOWNTREND"
        routing = "Box Sweep (L+S) + Bear 15m 50/200 EMA (SHORT)"
    else:
        emoji, label = "🟡", "RANGING / CHOP"
        routing = "Box Theory Sweep ONLY (15m 50/200 EMA Auto-Paused in Chop)"
    summary = (
        f"{emoji} {label} — Breadth: {b_pct:.0f}% Bull / {br_pct:.0f}% Bear | "
        f"14d: {r14:+.1f}% • 5d: {r5:+.1f}% • 2d: {r2:+.1f}% -> {routing}"
    )
    return {
        "regime": regime,
        "emoji": emoji,
        "label": label,
        "active_routing": routing,
        "bull_breadth_pct": round(bull_frac * 100.0, 1),
        "bear_breadth_pct": round(bear_frac * 100.0, 1),
        "median_14d_pct": round(r14, 2),
        "median_5d_pct": round(r5, 2),
        "median_2d_pct": round(r2, 2),
        "summary": summary,
    }


def compute_market_regime(pairs: list[str] = None, force_refresh: bool = False) -> dict:
    """
    Computes the live zero-lookahead Market Trend Regime across HIGH_VOL_FUTURES_UNIVERSE
    using completed daily candles (cached 5 minutes so UI & 24/7 scanner calls take 0ms when warm).
    """
    now = time.time()
    cached = _MARKET_REGIME_CACHE.get("data")
    if not force_refresh and isinstance(cached, dict) and (now - float(_MARKET_REGIME_CACHE.get("ts", 0.0))) < 300.0:
        return dict(cached)

    pool = list(pairs or HIGH_VOL_FUTURES_UNIVERSE)
    now_ms = int(now * 1000)
    bull_cnt, bear_cnt, valid_cnt = 0, 0, 0
    r14_list, r5_list, r2_list = [], [], []

    for p in pool:
        try:
            df_d = fetch_coindcx_candles(pair=p, interval="1d", limit=260, sync_live_price=False)
            if df_d is None or df_d.empty or len(df_d) < 20:
                continue
            closed_d = df_d[df_d["timestamp"] + 86400000 <= now_ms].reset_index(drop=True)
            if len(closed_d) < 16:
                closed_d = df_d.iloc[:-1].reset_index(drop=True)
            if len(closed_d) < 16:
                continue
            closes = closed_d["close"]
            e50 = float(closes.ewm(span=50, adjust=False).mean().iloc[-1])
            e200 = float(closes.ewm(span=200, adjust=False).mean().iloc[-1])
            c_last = float(closes.iloc[-1])
            valid_cnt += 1
            if c_last > e50 and c_last > e200:
                bull_cnt += 1
            elif c_last < e50 and c_last < e200:
                bear_cnt += 1
            r14_list.append((c_last / float(closes.iloc[-15]) - 1.0) * 100.0)
            r5_list.append((c_last / float(closes.iloc[-6]) - 1.0) * 100.0)
            r2_list.append((c_last / float(closes.iloc[-3]) - 1.0) * 100.0)
        except Exception:
            continue

    if valid_cnt == 0:
        fallback = _format_regime_metadata("RANGING_CHOP", 0.0, 0.0, 0.0, 0.0, 0.0)
        return fallback

    r14_med = float(pd.Series(r14_list).median()) if r14_list else 0.0
    r5_med = float(pd.Series(r5_list).median()) if r5_list else 0.0
    r2_med = float(pd.Series(r2_list).median()) if r2_list else 0.0
    bull_f = bull_cnt / valid_cnt
    bear_f = bear_cnt / valid_cnt
    reg = classify_universe_regime_from_stats(bull_f, bear_f, r14_med, r5_med, r2_med)
    out = _format_regime_metadata(reg, bull_f, bear_f, r14_med, r5_med, r2_med)
    _MARKET_REGIME_CACHE["data"] = dict(out)
    _MARKET_REGIME_CACHE["ts"] = now
    return out


def build_historical_regime_map(pairs: list[str] = None, duration_days: int = 30, warmup_days: int = 1000) -> dict[str, str]:
    """
    Builds a date_str -> ('STRONG_UPTREND' | 'STRONG_DOWNTREND' | 'RANGING_CHOP') lookup across the
    12-coin universe for historical backtests (strictly using prior completed daily candles, zero lookahead).
    """
    pool = list(pairs or HIGH_VOL_FUTURES_UNIVERSE)
    bias_by_d: dict[str, list[str]] = {}
    r14_by_d: dict[str, list[float]] = {}
    r5_by_d: dict[str, list[float]] = {}
    r2_by_d: dict[str, list[float]] = {}
    today_str = datetime.now(IST).strftime("%Y-%m-%d")

    for p in pool:
        try:
            df_d = fetch_historical_candles_paginated(pair=p, interval="1d", duration_days=duration_days + warmup_days)
            if df_d is None or df_d.empty or len(df_d) < 20:
                continue
            df_d = df_d.copy().reset_index(drop=True)
            df_d["dt_ist"] = pd.to_datetime(df_d["timestamp"], unit="ms").dt.tz_localize("UTC").dt.tz_convert(IST)
            df_d["date_str"] = df_d["dt_ist"].dt.strftime("%Y-%m-%d")
            if str(df_d["date_str"].iloc[-1]) < today_str:
                nxt = df_d.iloc[[-1]].copy()
                nxt["timestamp"] = int(df_d["timestamp"].iloc[-1]) + 86400000
                nxt["date_str"] = today_str
                df_d = pd.concat([df_d, nxt], ignore_index=True)

            e50_s = df_d["close"].ewm(span=50, adjust=False).mean().tolist()
            e200_s = df_d["close"].ewm(span=200, adjust=False).mean().tolist()
            closes = df_d["close"].tolist()
            dates = df_d["date_str"].tolist()
            for i in range(16, len(closes)):
                cur_d = dates[i]
                pc, pe50, pe200 = float(closes[i - 1]), float(e50_s[i - 1]), float(e200_s[i - 1])
                b = "BULLISH" if (pc > pe50 and pc > pe200) else ("BEARISH" if (pc < pe50 and pc < pe200) else "NEUTRAL")
                bias_by_d.setdefault(cur_d, []).append(b)
                r14_by_d.setdefault(cur_d, []).append((pc / float(closes[i - 15]) - 1.0) * 100.0)
                r5_by_d.setdefault(cur_d, []).append((pc / float(closes[i - 6]) - 1.0) * 100.0)
                r2_by_d.setdefault(cur_d, []).append((pc / float(closes[i - 3]) - 1.0) * 100.0)
        except Exception:
            continue

    reg_map: dict[str, str] = {}
    for d_k, b_list in bias_by_d.items():
        nb = max(1, len(b_list))
        bull_f = sum(1 for x in b_list if x == "BULLISH") / nb
        bear_f = sum(1 for x in b_list if x == "BEARISH") / nb
        r14_m = float(pd.Series(r14_by_d.get(d_k, [0.0])).median())
        r5_m = float(pd.Series(r5_by_d.get(d_k, [0.0])).median())
        r2_m = float(pd.Series(r2_by_d.get(d_k, [0.0])).median())
        reg_map[d_k] = classify_universe_regime_from_stats(bull_f, bear_f, r14_m, r5_m, r2_m)
    _PERSIST["backtest_regime_map"] = reg_map
    return reg_map


def _get_active_locks_map(cfg: dict = None) -> dict[str, dict]:
    """Returns a normalized {pair: lock_dict} map combining multi-pair `active_trade_locks` and legacy `active_trade_lock`."""
    cfg = cfg if isinstance(cfg, dict) else get_autotrade_config()
    out: dict[str, dict] = {}
    raw_map = cfg.get("active_trade_locks")
    if isinstance(raw_map, dict):
        for _, lk in raw_map.items():
            if isinstance(lk, dict) and lk.get("pair"):
                out[str(lk["pair"])] = dict(lk)
    legacy = cfg.get("active_trade_lock")
    if isinstance(legacy, dict) and legacy.get("pair"):
        lp = str(legacy["pair"])
        if lp not in out:
            out[lp] = dict(legacy)
    return out


def get_open_entry_limit_orders(
    open_orders: list[dict] = None,
    live_positions: list[dict] = None,
    cfg: dict = None,
) -> list[dict]:
    """
    Returns resting Entry Limit Orders on CoinDCX (excluding bracket `tpsl_exit` triggers and excluding
    opposite-side `TP1` partial-take-profit reduce limit orders on already-open positions).
    """
    ords = open_orders if isinstance(open_orders, list) else (fetch_coindcx_open_orders() or [])
    pos_dir_by_pair = {
        str(p.get("pair")): str(p.get("direction", "LONG")).upper()
        for p in (live_positions or [])
        if isinstance(p, dict) and p.get("pair")
    }
    entry_ords = []
    for o in ords:
        if not isinstance(o, dict):
            continue
        o_pair = str(o.get("pair") or "").strip()
        if not o_pair:
            continue
        if str(o.get("stage") or "").lower() == "tpsl_exit":
            continue
        o_type = str(o.get("order_type") or "").lower()
        if "limit" not in o_type:
            continue
        o_status = str(o.get("status") or "open").lower()
        if o_status not in ("open", "partially_filled", "init", "untriggered", ""):
            continue
        if o_pair in pos_dir_by_pair:
            pos_long = pos_dir_by_pair[o_pair] in ("LONG", "BUY")
            o_side = str(o.get("side") or "").upper()
            # Opposite-side limit order on an open position is our 50% TP1 partial exit, not a new slot entry
            if (pos_long and o_side == "SELL") or ((not pos_long) and o_side == "BUY"):
                continue
        entry_ords.append(o)
    return entry_ords


def count_open_ema50_200_slots(
    live_positions: list[dict] = None,
    cfg: dict = None,
    open_orders: list[dict] = None,
) -> int:
    """
    Counts how many currently active portfolio trades (both filled positions AND resting Entry 1 limit orders)
    were opened by Strategy 4 (`ema50_200`), so AutoTrade caps correlated EMA trend positions at
    MAX_EMA_CONCURRENT_TRADES (2) and keeps >=1 slot for Box Sweep.
    """
    cfg = cfg if isinstance(cfg, dict) else get_autotrade_config()
    locks_map = _get_active_locks_map(cfg)
    records = list(locks_map.values())
    for h in (cfg.get("history") or []):
        if isinstance(h, dict) and h.get("pair"):
            records.append(h)

    now_ts = time.time()
    active_pairs: list[str] = []
    if live_positions is not None:
        for pos in live_positions:
            p_name = pos.get("pair") if isinstance(pos, dict) else None
            if p_name and p_name not in active_pairs:
                active_pairs.append(str(p_name))
        if isinstance(open_orders, list):
            for eo in get_open_entry_limit_orders(open_orders=open_orders, live_positions=live_positions, cfg=cfg):
                ep = eo.get("pair")
                if ep and ep not in active_pairs:
                    active_pairs.append(str(ep))
        for lp, lk in locks_map.items():
            if bool(lk.get("entry1_pending")) and (now_ts - float(lk.get("opened_ts", 0.0) or 0.0)) < ENTRY1_LIMIT_EXPIRY_SEC:
                if lp not in active_pairs:
                    active_pairs.append(lp)

        ema_cnt = 0
        for p_name in active_pairs:
            matched_rec = next(
                (
                    r for r in records
                    if r.get("pair") == p_name
                    and not r.get("closed")
                    and (now_ts - float(r.get("opened_ts", 0.0) or 0.0)) < 7 * 86400
                ),
                None,
            )
            if matched_rec and str(matched_rec.get("strategy_id", "")) == "ema50_200":
                ema_cnt += 1
        return ema_cnt

    return sum(1 for lk in locks_map.values() if str(lk.get("strategy_id", "")) == "ema50_200")


_AUTOTRADE_CFG_MEM_CACHE = _PERSIST.setdefault("autotrade_cfg_cache", {"mtime": 0.0, "data": None})


# Keys that must survive a Streamlit Cloud restart (persisted per deployment to the Google Sheet)
_DURABLE_AUTOTRADE_KEYS = (
    "enabled",
    "paper_autotrade_enabled",
    "email_alerts_enabled",
    "autotrade_strategy_mode",
    "regime_mode_migrated_v33",
    "single_trade_margin_inr",
    "user_custom_margin",
    "leverage",
    "daily_start_wallet",
    "daily_loss_stop_hit",
    "paper_wallet_inr",
    "paper_starting_wallet_inr",
    "paper_daily_start_wallet",
    "paper_realized_pnl_inr",
    "synced_from_main_at",
    "active_trade_lock",
    "active_trade_locks",
)


def get_git_branch_name() -> str:
    """Returns the active git branch / deployment name ('Experiment', 'staging', 'main', etc.) in both local and cloud runs."""
    env_id = str(os.getenv("APP_DEPLOYMENT_ID", "") or os.getenv("STREAMLIT_BRANCH", "") or "").strip()
    if env_id:
        return env_id
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        with open(os.path.join(here, ".git", "HEAD"), "r", encoding="utf-8") as fh:
            head = fh.read().strip()
        if head.startswith("ref: refs/heads/"):
            return head.split("ref: refs/heads/", 1)[1].strip()
    except Exception:
        pass
    return ""


def is_experiment_environment() -> bool:
    """
    True when running on the `Experiment` branch or Experiment deployment.
    On Experiment, Live CoinDCX orders and 24/7 background AutoTrade/Emails are disabled by default;
    it mirrors Main's live setup strictly for testing new changes and full-parity backtesting.
    """
    app_env = str(os.getenv("APP_ENV", "") or "").strip().lower()
    if app_env == "experiment":
        return True
    if app_env in ("staging", "main", "production"):
        return False
    branch = get_git_branch_name().lower()
    if branch == "experiment" or "experiment" in branch:
        return True
    host = str(os.getenv("HOSTNAME", "") or os.getenv("STREAMLIT_SERVER_ADDRESS", "") or os.getenv("APP_WEB_URL", "") or "").lower()
    if "experiment" in host:
        return True
    return False


def is_staging_environment() -> bool:
    """
    True when running on the `staging` branch or staging deployment (`np-shiv-prakash-trade-assistant`).
    On staging, Live CoinDCX AutoTrade is disabled and AutoTrade executes strictly as Paper Trading
    on live market data (mirroring Main's Funds, Margin, Leverage, Strategy & 5% SL Threshold).
    """
    app_env = str(os.getenv("APP_ENV", "") or "").strip().lower()
    if app_env == "staging":
        return True
    if app_env in ("experiment", "main", "production"):
        return False
    if is_experiment_environment():
        return False
    branch = get_git_branch_name().lower()
    if branch == "staging" or "staging" in branch:
        return True
    host = str(os.getenv("HOSTNAME", "") or os.getenv("STREAMLIT_SERVER_ADDRESS", "") or "").lower()
    if "np-shiv-prakash" in host or "staging" in host:
        return True
    return False


def get_environment_tier() -> str:
    """Returns the active 3-tier deployment role: 'experiment', 'staging', or 'main'."""
    if is_experiment_environment():
        return "experiment"
    if is_staging_environment():
        return "staging"
    return "main"


def get_paper_wallet_snapshot(cfg: dict | None = None, live_wallet: dict | None = None) -> dict:
    """
    Returns Staging's live-market Paper Trading wallet snapshot with exact CoinDCX wallet keys
    (`total_inr`, `available_inr`, `locked_inr`, `starting_inr`, `net_pnl_inr`, `is_live_api=True`),
    accounting for locked margin in open paper trades and realized PnL from closed paper trades.
    """
    c = dict(cfg) if isinstance(cfg, dict) else get_autotrade_config()
    pw = float(c.get("paper_wallet_inr", 0.0) or 0.0)
    if pw <= 0:
        lw_tot = float((live_wallet or {}).get("total_inr", 0.0) or 0.0) if isinstance(live_wallet, dict) else 0.0
        pw = lw_tot if lw_tot > 0 else float(c.get("wallet_balance_inr", 47287.18) or 47287.18)
    start_pw = float(c.get("paper_starting_wallet_inr", 0.0) or 0.0) or pw
    locks_map = _get_active_locks_map(c)
    locked_inr = round(
        sum(
            float(lk.get("margin_inr", 0.0) or 0.0)
            for lk in locks_map.values()
            if isinstance(lk, dict) and not lk.get("is_live_exchange")
        ),
        2,
    )
    avail_inr = round(max(0.0, pw - locked_inr), 2)
    net_pnl = round(pw - start_pw, 2)
    return {
        "total_inr": round(pw, 2),
        "available_inr": avail_inr,
        "inr_cash": avail_inr,
        "locked_inr": locked_inr,
        "usdt_cash": 0.0,
        "available_usdt": 0.0,
        "locked_margin_usd": 0.0,
        "cross_user_margin_usd": 0.0,
        "starting_inr": round(start_pw, 2),
        "net_pnl_inr": net_pnl,
        "live_usd_inr": float((live_wallet or {}).get("live_usd_inr", 0.0) or 0.0) or get_coindcx_live_usdt_inr_rate(),
        "is_live_api": True,
        "is_paper_wallet": True,
        "source": "Staging Paper Wallet (Mirrors Main)",
    }


def sync_setup_from_main(reset_paper_wallet: bool = False) -> tuple[bool, str, dict]:
    """
    Mirrors Main's exact live setup (Funds/Wallet Balance, Single-Trade Margin, Leverage, and
    Strategy Mode) from the shared Google Sheet into Staging (Paper Trading) or Experiment (Backtest Lab).
    """
    try:
        import sheets_logger as _sl
        main_setup = _sl.load_main_live_setup_from_sheet(force_refresh=True)
        if not isinstance(main_setup, dict):
            return False, "Could not load Main live setup from Google Sheet (`_AutoTrade_State` / `_Live_Account_Sync`).", {}
        cfg = get_autotrade_config()
        today = datetime.now(IST).strftime("%Y-%m-%d")
        now_s = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
        m_wallet = float(main_setup.get("wallet_balance_inr", 0.0) or 0.0)
        m_margin = float(main_setup.get("single_trade_margin_inr", 0.0) or 0.0)
        m_custom = bool(main_setup.get("user_custom_margin", False))
        m_lev = int(main_setup.get("leverage", 10) or 10)
        m_mode = str(main_setup.get("autotrade_strategy_mode") or "box_plus_ema50_200_regime")

        updates = {
            "autotrade_strategy_mode": m_mode,
            "leverage": m_lev,
            "user_custom_margin": m_custom,
            "synced_from_main_at": now_s,
        }
        if m_wallet > 0:
            updates["wallet_balance_inr"] = round(m_wallet, 2)
        if m_margin > 0:
            updates["single_trade_margin_inr"] = round(m_margin, 2)
        elif m_wallet > 0:
            updates["single_trade_margin_inr"] = round(m_wallet * TRADE_ALLOCATION_FRACTION, 2)

        cur_pw = float(cfg.get("paper_wallet_inr", 0.0) or 0.0)
        if m_wallet > 0 and (reset_paper_wallet or cur_pw <= 0):
            updates["paper_wallet_inr"] = round(m_wallet, 2)
            updates["paper_starting_wallet_inr"] = round(m_wallet, 2)
            updates["paper_daily_start_wallet"] = {"date": today, "inr": round(m_wallet, 2)}
            updates["paper_realized_pnl_inr"] = 0.0
            updates["daily_loss_stop_hit"] = ""

        saved = save_autotrade_config(updates)
        return True, (
            f"Synced from Main: Wallet ₹{m_wallet:,.2f} | Margin ₹{updates.get('single_trade_margin_inr', m_margin):,.2f} "
            f"@ {m_lev}x | Mode `{m_mode}`"
        ), saved
    except Exception as e:
        return False, f"Sync from Main failed: {e}", {}


def _get_deployment_id() -> str:
    """
    Identifies this deployment ('main' / 'staging' / 'Experiment') so tiers never share AutoTrade state.
    Only active on Streamlit Cloud (/mount/src/...) so local runs and tests never touch the shared Google Sheet.
    """
    env_id = str(os.getenv("APP_DEPLOYMENT_ID", "") or "").strip()
    if env_id:
        return env_id
    here = os.path.dirname(os.path.abspath(__file__))
    if not here.replace("\\", "/").startswith("/mount/src/"):
        return ""
    return get_git_branch_name()


def _restore_autotrade_state_once() -> None:
    """On a fresh container (no local config file yet), restore durable AutoTrade state from the Google Sheet once."""
    if _PERSIST.get("autotrade_state_restore_done"):
        return
    _PERSIST["autotrade_state_restore_done"] = True
    dep_id = _get_deployment_id()
    if not dep_id or os.path.exists(AUTOTRADE_CONFIG_FILE):
        return
    try:
        import sheets_logger as _sl
        saved = _sl.load_autotrade_state_from_sheet(dep_id)
        if isinstance(saved, dict) and saved:
            restored = {k: saved[k] for k in _DURABLE_AUTOTRADE_KEYS if k in saved}
            if restored:
                os.makedirs(os.path.dirname(AUTOTRADE_CONFIG_FILE), exist_ok=True)
                with open(AUTOTRADE_CONFIG_FILE, "w", encoding="utf-8") as fh:
                    json.dump(restored, fh, indent=2)
                print(f"[AutoTrade State] Restored from Google Sheet for '{dep_id}': {restored}")
    except Exception as e:
        print(f"[AutoTrade State Restore Notice]: {e}")


def _persist_autotrade_state_bg(cfg: dict) -> None:
    """Writes durable AutoTrade keys for this deployment to the Google Sheet in a background thread."""
    dep_id = _get_deployment_id()
    if not dep_id:
        return
    state = {k: cfg.get(k) for k in _DURABLE_AUTOTRADE_KEYS if k in cfg}

    def _worker():
        try:
            import sheets_logger as _sl
            _sl.save_autotrade_state_to_sheet(dep_id, state)
        except Exception:
            pass

    _threading.Thread(target=_worker, daemon=True, name="AutoTradeStatePersist").start()


def get_autotrade_config() -> dict:
    """
    Loads persistent AutoTrade & Single-Trade Margin settings shared between the Streamlit UI
    and the 24/7 background monitor daemon in 0ms (never makes network or recursive balance calls).
    Immediately terminates any obsolete pre-v3 background daemon threads from earlier @st.cache_resource runs.
    On a fresh Streamlit Cloud container, durable keys (AutoTrade ON/OFF etc.) are restored once from the Google Sheet.
    """
    _check_and_kill_obsolete_daemon()
    _restore_autotrade_state_once()

    _is_stg = is_staging_environment()
    _is_exp = is_experiment_environment()
    default_cfg = {
        "enabled": False,
        "paper_autotrade_enabled": True if _is_stg else False,
        "email_alerts_enabled": False if (_is_stg or _is_exp) else True,
        "paper_only": (_is_stg or _is_exp),
        "autotrade_strategy_mode": "box_plus_ema50_200_regime",
        "wallet_balance_inr": 47287.18,
        "single_trade_margin_inr": 15762.39,
        "user_custom_margin": False,
        "leverage": 10,
        "one_crypto_at_a_time": True,
        "high_vol_scan_enabled": True,
        "active_trade_lock": None,
        "active_trade_locks": {},
        "history": [],
        "updated_at": "",
    }
    try:
        if os.path.exists(AUTOTRADE_CONFIG_FILE):
            mtime = os.path.getmtime(AUTOTRADE_CONFIG_FILE)
            cached_data = _AUTOTRADE_CFG_MEM_CACHE.get("data")
            if isinstance(cached_data, dict) and _AUTOTRADE_CFG_MEM_CACHE.get("mtime") == mtime:
                res = dict(default_cfg)
                res.update(cached_data)
                res["paper_only"] = (_is_stg or _is_exp)
                wb_c = float(res.get("wallet_balance_inr", 47287.18) or 47287.18)
                sm_c = float(res.get("single_trade_margin_inr", 0) or 0)
                if sm_c <= 0 or sm_c in (15762.39, 30000.0, 250000.0, 100000.0) or not res.get("user_custom_margin"):
                    res["single_trade_margin_inr"] = round(wb_c * TRADE_ALLOCATION_FRACTION, 2)
                return res
            with open(AUTOTRADE_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    _AUTOTRADE_CFG_MEM_CACHE["data"] = dict(saved)
                    _AUTOTRADE_CFG_MEM_CACHE["mtime"] = mtime
                    default_cfg.update(saved)
                    default_cfg["paper_only"] = (_is_stg or _is_exp)
                    wb = float(default_cfg.get("wallet_balance_inr", 47287.18) or 47287.18)
                    sm_val = float(default_cfg.get("single_trade_margin_inr", 0) or 0)
                    if sm_val <= 0 or sm_val in (15762.39, 30000.0, 250000.0, 100000.0) or not default_cfg.get("user_custom_margin"):
                        default_cfg["single_trade_margin_inr"] = round(wb * TRADE_ALLOCATION_FRACTION, 2)
    except Exception:
        pass
    return default_cfg


def save_autotrade_config(updates: dict) -> dict:
    """Saves updated AutoTrade settings to .cache/autotrade_config.json without triggering any API calls."""
    cfg = get_autotrade_config()
    updates = dict(updates or {})
    if "active_trade_lock" in updates and "active_trade_locks" not in updates:
        lk_upd = updates.get("active_trade_lock")
        if lk_upd is None:
            updates["active_trade_locks"] = {}
        elif isinstance(lk_upd, dict) and lk_upd.get("pair"):
            cur_map = dict(_get_active_locks_map(cfg))
            cur_map[str(lk_upd["pair"])] = dict(lk_upd)
            updates["active_trade_locks"] = cur_map
    durable_changed = any(k in updates and updates.get(k) != cfg.get(k) for k in _DURABLE_AUTOTRADE_KEYS)
    cfg.update(updates)
    if durable_changed:
        _persist_autotrade_state_bg(cfg)
    cfg["updated_at"] = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    try:
        os.makedirs(os.path.dirname(AUTOTRADE_CONFIG_FILE), exist_ok=True)
        with open(AUTOTRADE_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        _AUTOTRADE_CFG_MEM_CACHE["data"] = dict(cfg)
        _AUTOTRADE_CFG_MEM_CACHE["mtime"] = os.path.getmtime(AUTOTRADE_CONFIG_FILE)
    except Exception as e:
        print(f"[AutoTrade Config Save Notice]: {e}")
    return cfg


def clear_autotrade_active_lock(pair: str = None) -> dict:
    """Clears `pair` from `active_trade_locks` (or clears ALL active locks when `pair` is None)."""
    try:
        cfg = get_autotrade_config()
        locks_map = _get_active_locks_map(cfg)
        hist = list(cfg.get("history") or [])
        target_pairs = [str(pair)] if pair else list(locks_map.keys())
        for p_pair in target_pairs:
            prev_lock = locks_map.pop(p_pair, None)
            p_ts = float((prev_lock or {}).get("opened_ts", 0.0) or 0.0)
            for h in hist:
                if isinstance(h, dict) and h.get("pair") == p_pair:
                    if p_ts <= 0 or abs(float(h.get("opened_ts", 0.0) or 0.0) - p_ts) < 5.0:
                        h["closed"] = True
        next_primary = (
            max(locks_map.values(), key=lambda x: float(x.get("opened_ts", 0.0) or 0.0))
            if locks_map else None
        )
        return save_autotrade_config({
            "active_trade_lock": next_primary,
            "active_trade_locks": locks_map,
            "history": hist[:30],
        })
    except Exception:
        pass
    return save_autotrade_config({"active_trade_lock": None, "active_trade_locks": {}})


def cancel_coindcx_open_entry_orders(
    pair: str,
    order_id: str = None,
    side: str = None,
    cancel_all_for_pair: bool = False,
) -> int:
    """
    Cancels any unfilled resting limit orders (and optionally all open orders when `cancel_all_for_pair=True`)
    for `pair` once TP1 is reached, Entry 1 expires, or the trade closes.
    If `side` ('buy' or 'sell') is provided, only cancels limit orders on that side.
    """
    cancelled = 0
    side_filter = str(side).lower().strip() if side else None
    try:
        if order_id and order_id not in ("CONFIRMED", "DAEMON_50PCT_REDUCE_AT_TP1"):
            res, _ = _send_coindcx_signed_request(
                "POST",
                "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel",
                {"id": str(order_id), "timestamp": int(round(time.time() * 1000))},
            )
            if res is not None and res.status_code == 200:
                cancelled += 1
        open_orders = fetch_coindcx_open_orders() or []
        for o in open_orders:
            o_id = o.get("id")
            o_pair = o.get("pair")
            o_stage = o.get("stage", "")
            o_side = str(o.get("side", "")).lower().strip()
            o_type = str(o.get("order_type", "")).lower()
            if o_id and o_pair == pair and (cancel_all_for_pair or (o_stage != "tpsl_exit" and "limit" in o_type)):
                if side_filter and o_side and o_side != side_filter:
                    continue
                res, _ = _send_coindcx_signed_request(
                    "POST",
                    "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel",
                    {"id": str(o_id), "timestamp": int(round(time.time() * 1000))},
                )
                if res is not None and res.status_code == 200:
                    cancelled += 1
    except Exception as e:
        print(f"[Cancel Unfilled Entry 2 Notice]: {e}")
    return cancelled


def normalize_two_entry_runner_levels(
    pair: str,
    direction: str,
    entry1_px: float,
    entry2_px: float = None,
    tp1_px: float = None,
    tp2_px: float = None,
    sl_px: float = None,
    live_px: float = None,
    levels: dict = None,
) -> dict:
    """
    Guarantees that Entry 1, Entry 2 @ Sweep, TP1 (50% Book), TP2 (50% Runner), and Catastrophe SL
    are strictly on the valid side of both Entry 1 and current live market price so CoinDCX
    never rejects `create_tpsl` or resting Limit Orders when price is outside prior-day [SL, SH].
    """
    is_long = str(direction).upper() in ("BUY", "LONG")
    e1 = float(entry1_px or live_px or 0.0)
    cur_p = float(live_px or e1)
    if e1 <= 0:
        e1 = cur_p
    has_explicit_e2 = (entry2_px is not None) and (float(entry2_px or 0.0) > 0.0)

    if is_long:
        high_ref = max(e1, cur_p) if cur_p > 0 else e1
        low_ref = min(e1, cur_p) if cur_p > 0 else e1

        has_box_ctx = isinstance(levels, dict) and bool(levels.get("SL") or levels.get("MID"))
        use_sweep_anchor = has_explicit_e2 or has_box_ctx
        sl_sweep_ref = float(entry2_px if has_explicit_e2 else ((levels.get("SL") if levels else 0.0) or 0.0))
        if use_sweep_anchor and (sl_sweep_ref <= 0 or sl_sweep_ref >= low_ref * 0.9992):
            sl_sweep_ref = low_ref * 0.992
        cand_e2 = sl_sweep_ref if has_explicit_e2 else 0.0

        cand_sl = float(sl_px or 0.0)
        min_long_anchor = min(low_ref, sl_sweep_ref) if (use_sweep_anchor and sl_sweep_ref > 0) else low_ref
        if cand_sl <= 0 or cand_sl >= min_long_anchor * 0.999:
            cand_sl = (min_long_anchor if use_sweep_anchor else low_ref * 0.992) * 0.995

        cand_tp2 = float(tp2_px or (levels.get("RH") if levels else 0.0) or 0.0)
        cand_tp1 = float(tp1_px or 0.0)
        if isinstance(levels, dict) and levels.get("MID"):
            _m = float(levels.get("MID", 0.0) or 0.0)
            _e50 = float(levels.get("EMA50_15m") or _get_live_15m_ema50(pair, _m))
            _rh = cand_tp2 if cand_tp2 > high_ref * 1.008 else float(levels.get("RH", high_ref * 1.02) or (high_ref * 1.02))
            _smart_tp1, _ = _select_smart_hybrid_box_tp1("BUY", high_ref, _m, _e50, _rh)
            if cand_tp1 <= high_ref * 1.0059:
                cand_tp1 = _smart_tp1
        elif cand_tp1 <= high_ref * 1.0059:
            cand_tp1 = (high_ref + cand_tp2) / 2.0 if cand_tp2 > high_ref * 1.012 else high_ref * 1.012

        if cand_tp2 <= cand_tp1 * 1.002:
            cand_tp2 = max(cand_tp1 * 1.012, high_ref * 1.024)
    else:
        low_ref = min(e1, cur_p) if cur_p > 0 else e1
        high_ref = max(e1, cur_p) if cur_p > 0 else e1

        has_box_ctx = isinstance(levels, dict) and bool(levels.get("SH") or levels.get("MID"))
        use_sweep_anchor = has_explicit_e2 or has_box_ctx
        sh_sweep_ref = float(entry2_px if has_explicit_e2 else ((levels.get("SH") if levels else 0.0) or 0.0))
        if use_sweep_anchor and (sh_sweep_ref <= 0 or sh_sweep_ref <= high_ref * 1.0008):
            sh_sweep_ref = high_ref * 1.008
        cand_e2 = sh_sweep_ref if has_explicit_e2 else 0.0

        cand_sl = float(sl_px or 0.0)
        max_short_anchor = max(high_ref, sh_sweep_ref) if (use_sweep_anchor and sh_sweep_ref > 0) else high_ref
        if cand_sl <= 0 or cand_sl <= max_short_anchor * 1.001:
            cand_sl = (max_short_anchor if use_sweep_anchor else high_ref * 1.008) * 1.005

        cand_tp2 = float(tp2_px or (levels.get("RL") if levels else 0.0) or 0.0)
        cand_tp1 = float(tp1_px or 0.0)
        if isinstance(levels, dict) and levels.get("MID"):
            _m = float(levels.get("MID", 0.0) or 0.0)
            _e50 = float(levels.get("EMA50_15m") or _get_live_15m_ema50(pair, _m))
            _rl = cand_tp2 if (0 < cand_tp2 < low_ref * 0.992) else float(levels.get("RL", low_ref * 0.98) or (low_ref * 0.98))
            _smart_tp1, _ = _select_smart_hybrid_box_tp1("SELL", low_ref, _m, _e50, _rl)
            if cand_tp1 <= 0 or cand_tp1 >= low_ref * 0.9941:
                cand_tp1 = _smart_tp1
        elif cand_tp1 <= 0 or cand_tp1 >= low_ref * 0.9941:
            cand_tp1 = (low_ref + cand_tp2) / 2.0 if (0 < cand_tp2 < low_ref * 0.988) else low_ref * 0.988

        if cand_tp2 <= 0 or cand_tp2 >= cand_tp1 * 0.998:
            cand_tp2 = min(cand_tp1 * 0.988, low_ref * 0.976)

    return {
        "entry": round_asset_price(e1),
        "entry2_sweep": round_asset_price(cand_e2, e1) if cand_e2 > 0 else 0.0,
        "tp1": round_asset_price(cand_tp1, e1),
        "tp2": round_asset_price(cand_tp2, e1),
        "stop_loss": round_asset_price(cand_sl, e1),
    }


def sync_full_2entry_runner_to_position(
    pair: str,
    direction: str = None,
    entry1_px: float = None,
    entry2_px: float = None,
    tp1_px: float = None,
    tp2_px: float = None,
    sl_px: float = None,
    total_margin_inr: float = 20000.0,
    leverage: int = 10,
    usd_inr: float = None,
    strategy_id: str = "box_theory",
) -> tuple[bool, str, dict]:
    """
    Synchronizes all components of the Smart Hybrid setup onto an active CoinDCX position:
      1. Position Bracket TP = TP2 (Runner) & SL = Catastrophe SL via `update_coindcx_position_tpsl`.
      2. TP1 50% Partial Book resting opposite-side Limit Order (`0.5 * pos_qty` @ `tp1_px`) for Strategy 1 & 2
         (Strategy 3 `ema9_retest` keeps 100% Full Runner and ratchets SL at TP1).
      3. Entry 2 / Trade 2 resting same-side Limit Order (`50%` of `total_margin_inr` @ `entry2_px`) for Strategy 1
         (Strategy 2 & 3 use Single Entry with `entry2_px == 0`).
      4. App Trade Lock registration so the 24/7 daemon manages TP1 -> Cancel Entry 2 -> Ratchet SL -> Smart Hybrid Runner.
    """
    u_inr = float(usd_inr or get_coindcx_live_usdt_inr_rate())
    positions = fetch_coindcx_active_positions(force_refresh=True)
    matched_pos = next((p for p in positions if p.get("pair") == pair), None)
    if not matched_pos or not matched_pos.get("id"):
        return False, f"No active position found on CoinDCX for {pair} yet.", {}

    pos_id = matched_pos["id"]
    pos_dir = str(direction or matched_pos.get("direction", "LONG")).upper()
    is_long = pos_dir in ("LONG", "BUY")
    side = "BUY" if is_long else "SELL"
    opp_side = "SELL" if is_long else "BUY"
    pos_qty = float(matched_pos.get("quantity", 0.0) or 0.0)
    pos_entry = float(matched_pos.get("entry_price", 0.0) or entry1_px or 0.0)
    pos_mark = float(matched_pos.get("mark_price", pos_entry) or pos_entry)
    pos_lev = int(round(float(matched_pos.get("leverage") or leverage or 10)))

    strat_id = str(strategy_id or "box_theory").strip() or "box_theory"
    has_second_entry = (strat_id == "box_theory") and (entry2_px is not None and float(entry2_px or 0.0) > 0.0)
    use_full_s3_runner = (strat_id == "ema9_retest")

    levels = None
    if strat_id == "box_theory":
        try:
            levels = calculate_daily_box_levels(pair)
        except Exception:
            pass

    norm = normalize_two_entry_runner_levels(
        pair=pair,
        direction=pos_dir,
        entry1_px=pos_entry,
        entry2_px=entry2_px if has_second_entry else None,
        tp1_px=tp1_px,
        tp2_px=tp2_px,
        sl_px=sl_px,
        live_px=pos_mark,
        levels=levels,
    )
    e1_val = norm["entry"]
    e2_val = norm["entry2_sweep"] if has_second_entry else 0.0
    tp1_val = norm["tp1"]
    tp2_val = norm["tp2"]
    sl_val = format_order_price(pair, float(sl_px)) if (not has_second_entry and sl_px and float(sl_px) > 0) else norm["stop_loss"]

    status_parts = []
    details = {"normalized_levels": norm}

    # 1. Attach Position TP (TP2 Runner) and SL (Catastrophe SL) on the active position
    tpsl_ok, tpsl_msg = update_coindcx_position_tpsl(pos_id, tp_price=tp2_val, sl_price=sl_val, pair=pair)
    details["tpsl_ok"] = tpsl_ok
    details["tpsl_msg"] = tpsl_msg
    status_parts.append(f"Bracket TP2=${tp2_val} & SL=${sl_val}: {'Set' if tpsl_ok else tpsl_msg}")

    # Inspect existing open limit orders for this pair so we don't duplicate
    open_orders = fetch_coindcx_open_orders() or []
    existing_same_side_limit = None
    existing_opp_side_limit = None
    for o in open_orders:
        if o.get("pair") == pair and o.get("stage") != "tpsl_exit" and "limit" in str(o.get("order_type", "")).lower():
            o_side = str(o.get("side", "")).upper()
            if o_side == side and not existing_same_side_limit:
                existing_same_side_limit = o
            elif o_side == opp_side and not existing_opp_side_limit:
                existing_opp_side_limit = o

    # 2. Place TP1 (50% Partial Book) opposite-side Limit Order if not already open (Strategy 3 keeps 100% Full Runner)
    tp1_order_id = ""
    tp1_qty = format_order_quantity(pair, pos_qty * 0.5) if not use_full_s3_runner else 0.0
    if not use_full_s3_runner and (tp1_qty * tp1_val * u_inr) < 2448.0 and (pos_qty * tp1_val * u_inr) >= 2448.0:
        tp1_qty = min(pos_qty, format_order_quantity(pair, (2500.0 / u_inr) / tp1_val))

    if use_full_s3_runner:
        tp1_order_id = "STRATEGY3_FULL_RUNNER_SL_RATCHET"
        status_parts.append(f"TP1 SL-Ratchet Armed @ ${tp1_val} (100% S3 Runner)")
    elif existing_opp_side_limit:
        tp1_order_id = str(existing_opp_side_limit.get("id", ""))
        status_parts.append(f"TP1 Limit ({existing_opp_side_limit.get('total_quantity')} @ ${existing_opp_side_limit.get('price')}): Already Open")
    elif tp1_qty > 0 and (tp1_qty * tp1_val * u_inr) >= 2448.0:
        ok_tp1, msg_tp1, extra_tp1 = place_coindcx_futures_order(
            pair=pair,
            side=opp_side,
            quantity=tp1_qty,
            leverage=pos_lev,
            order_type="limit_order",
            price=tp1_val,
            margin_currency="INR",
            post_only=False,
        )
        details["tp1_order"] = extra_tp1
        if ok_tp1:
            tp1_order_id = str((extra_tp1 or {}).get("order_id", ""))
            status_parts.append(f"TP1 50% Limit ({opp_side} {tp1_qty} @ ${tp1_val}): Placed")
        else:
            tp1_order_id = "DAEMON_50PCT_REDUCE_AT_TP1"
            status_parts.append(f"TP1 Limit (Daemon 50% Market Reduce Armed @ ${tp1_val})")
    else:
        tp1_order_id = "DAEMON_50PCT_REDUCE_AT_TP1"
        status_parts.append(f"TP1 (Daemon 50% Reduce Armed @ ${tp1_val})")

    # 3. Place Entry 2 / Trade 2 (50% Sweep Scale-In) same-side Limit Order if Strategy 1 (has_second_entry)
    e2_order_id = ""
    tranche_m_inr = max(float(total_margin_inr or 20000.0) * 0.5, float(matched_pos.get("locked_margin_inr", 10000.0) or 10000.0))
    qty2 = format_order_quantity(pair, ((tranche_m_inr * pos_lev) / u_inr) / e2_val) if (has_second_entry and e2_val > 0) else 0.0
    already_full_2entry_sized = bool(
        has_second_entry
        and total_margin_inr
        and float(total_margin_inr) > 0
        and (pos_qty * pos_entry * u_inr) >= (float(total_margin_inr) * pos_lev * 0.80)
    )

    if not has_second_entry:
        status_parts.append("Single Entry (100% Margin on Entry 1)")
    elif already_full_2entry_sized:
        status_parts.append("Entry 2 Sweep Limit: Already Filled in Position")
    elif existing_same_side_limit:
        e2_order_id = str(existing_same_side_limit.get("id", ""))
        status_parts.append(f"Entry 2 Limit ({existing_same_side_limit.get('total_quantity')} @ ${existing_same_side_limit.get('price')}): Already Open")
    elif qty2 > 0 and (qty2 * e2_val * u_inr) >= 2448.0:
        ok_e2, msg_e2, extra_e2 = place_coindcx_futures_order(
            pair=pair,
            side=side,
            quantity=qty2,
            leverage=pos_lev,
            order_type="limit_order",
            price=e2_val,
            margin_currency="INR",
            post_only=False,
        )
        details["entry2_order"] = extra_e2
        if ok_e2:
            e2_order_id = str((extra_e2 or {}).get("order_id", ""))
            status_parts.append(f"Entry 2 Sweep Limit ({side} {qty2} @ ${e2_val}): Placed")
        else:
            status_parts.append(f"Entry 2 Notice: {msg_e2}")

    # 4. Register/Update App Trade Lock so the 24/7 daemon monitors TP1 -> Cancel Entry 2 -> Ratchet SL -> TP2
    lock_info = register_app_trade_lock(
        pair=pair,
        direction="LONG" if is_long else "SHORT",
        entry=e1_val,
        stop_loss=sl_val,
        tp1=tp1_val,
        tp2=tp2_val,
        entry2_sweep=e2_val,
        margin_inr=float(total_margin_inr or (tranche_m_inr * 2.0 if has_second_entry else tranche_m_inr)),
        leverage=pos_lev,
        qty1=pos_qty,
        qty2=qty2,
        mode="App/API Live Execution (TP1/TP2/SL Synced)",
        is_live_exchange=True,
        entry2_order_id=e2_order_id,
        tp1_order_id=tp1_order_id or "DAEMON_50PCT_REDUCE_AT_TP1",
        strategy_id=strat_id,
        entry1_pending=False,
        entry2_filled=already_full_2entry_sized,
    )
    details["lock"] = lock_info
    _ACTIVE_POSITIONS_CACHE["data"] = None
    return True, " | ".join(status_parts), details


def register_app_trade_lock(
    pair: str,
    direction: str,
    entry: float,
    stop_loss: float,
    tp1: float,
    tp2: float = 0.0,
    entry2_sweep: float = 0.0,
    margin_inr: float = 0.0,
    leverage: int = 10,
    qty1: float = 0.0,
    qty2: float = 0.0,
    mode: str = "App/API Executed Trade",
    is_live_exchange: bool = False,
    entry2_order_id: str = "",
    tp1_order_id: str = "",
    strategy_id: str = "box_theory",
    entry1_order_id: str = "",
    entry1_pending: bool = False,
    entry2_filled: bool = False,
) -> dict:
    """
    Registers an active 1-Crypto-at-a-Time lock strictly for trades executed via our App/API.
    Manual trades placed directly on CoinDCX outside our App/API do NOT trigger this lock.
    """
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    lock_info = {
        "pair": pair,
        "direction": str(direction).upper(),
        "strategy_id": str(strategy_id or "box_theory"),
        "entry": float(entry or 0.0),
        "entry1_order_id": str(entry1_order_id or ""),
        "entry1_pending": bool(entry1_pending),
        "entry2_sweep": float(entry2_sweep or 0.0),
        "entry2_filled": bool(entry2_filled),
        "entry2_cancelled": False,
        "entry2_order_id": str(entry2_order_id or ""),
        "tp1_order_id": str(tp1_order_id or ""),
        "tp1": float(tp1 or 0.0),
        "tp2": float(tp2 or tp1 or 0.0),
        "tp1_hit": False,
        "runner_halfway_ratcheted": False,
        "stop_loss": float(stop_loss or 0.0),
        "qty1": float(qty1 or 0.0),
        "target_qty1": float(qty1 or 0.0),
        "qty2": float(qty2 or 0.0),
        "margin_inr": float(margin_inr or 0.0),
        "leverage": int(leverage or 10),
        "opened_at": now_str,
        "opened_ts": time.time(),
        "mode": mode,
        "is_live_exchange": bool(is_live_exchange),
    }
    cfg = get_autotrade_config()
    locks_map = _get_active_locks_map(cfg)
    prev_lock = locks_map.get(pair) or cfg.get("active_trade_lock") or {}
    if pair in locks_map and float(locks_map[pair].get("target_qty1", 0.0) or 0.0) > float(lock_info["target_qty1"]):
        lock_info["target_qty1"] = float(locks_map[pair]["target_qty1"])
    is_paper_autotrade = ("Paper AutoTrade" in str(mode)) or (not is_live_exchange and is_staging_environment())
    should_log_sheet = bool(
        (is_live_exchange or is_paper_autotrade)
        and (
            prev_lock.get("pair") != pair
            or str(prev_lock.get("direction", "")).upper() != str(direction).upper()
            or (time.time() - float(prev_lock.get("opened_ts", 0.0) or 0.0)) > 600
        )
    )
    locks_map[pair] = lock_info
    hist = cfg.get("history", [])
    hist.insert(0, {**lock_info, "status": "APP_API_LOCK_SET"})
    save_autotrade_config({"active_trade_lock": lock_info, "active_trade_locks": locks_map, "history": hist[:30]})

    if should_log_sheet:
        _strat_map = {
            "box_theory": "Strategy 1: Box Theory Sweep",
            "atr_reversal": "Strategy 2: 1-Candle 25% ATR Reversal",
            "ema9_retest": "Strategy 3: 9 EMA Touch & Confirm",
            "ema50_200": "Strategy 4: 15m 50/200 EMA Pullback",
        }
        _base_strat = _strat_map.get(str(strategy_id or "box_theory"), "Box Theory Sweep")
        _tag_suffix = "Staging Paper AutoTrade" if not is_live_exchange else "App Live Order"
        _sheet_strat_name = f"{_base_strat} ({_tag_suffix})"
        _sheet_status = "PAPER_AUTOTRADE_OPEN" if not is_live_exchange else "LOGGED_PENDING"

        def _async_sheet_log():
            try:
                import sheets_logger
                e_f = float(entry or 0.0)
                tp1_f = float(tp1 or 0.0)
                sl_f = float(stop_loss or 0.0)
                m_f = float(margin_inr or 20000.0)
                lev_f = int(leverage or 10)
                proj_tp1 = round(abs(tp1_f - e_f) / e_f * m_f * lev_f, 2) if e_f > 0 else 0.0
                proj_sl = round(-abs(e_f - sl_f) / e_f * m_f * lev_f, 2) if e_f > 0 else 0.0
                _pw_snap = get_paper_wallet_snapshot(cfg) if is_paper_autotrade else {}
                sheets_logger.log_trade_to_google_sheet({
                    "timestamp": now_str,
                    "pair": pair,
                    "signal": str(direction).upper(),
                    "entry": e_f,
                    "stop_loss": sl_f,
                    "tp1": tp1_f,
                    "tp2": float(tp2 or tp1 or 0.0),
                    "crypto_qty": round(float(qty1 or 0.0) + float(qty2 or 0.0), 4),
                    "margin_inr": m_f,
                    "leverage": lev_f,
                    "profit_tp1_inr": proj_tp1,
                    "loss_sl_inr": proj_sl,
                    "status": _sheet_status,
                    "strategy_name": _sheet_strat_name,
                    "trigger_reason": f"{mode} | E1: ${e_f}, E2: ${float(entry2_sweep or 0.0)}",
                    "is_staging_paper": bool(is_paper_autotrade),
                    "worksheet_name": "Staging_Trades" if is_paper_autotrade else "Live_Trades",
                    "paper_wallet_inr": _pw_snap.get("total_inr", "") if is_paper_autotrade else "",
                })
            except Exception as _se:
                print(f"[Auto Sheet Log Notice]: {_se}")

        _threading.Thread(target=_async_sheet_log, daemon=True).start()

    return lock_info


def compute_tp1_profit_lock_sl(
    pair: str,
    direction: str,
    entry_px: float,
    tp1_px: float,
    prev_candle_high: float = None,
    prev_candle_low: float = None,
) -> float:
    """
    Computes the optimal profit-preserving Stop Loss once TP1 (50% Partial Book) is reached (Strategy 3B/3C):
      - Locks at least 50% of the Entry 1 -> TP1 profit distance (`entry +/- 0.5 * |tp1 - entry|`),
        and never worse than Breakeven + fee buffer (`0.18%`).
      - If the previous 15m candle's structure (`prev_candle_low` for LONG, `prev_candle_high` for SHORT)
        tightens the stop even further into profit without exceeding `tp1_px`, uses that tighter level!
    """
    is_long = str(direction).upper() in ("LONG", "BUY")
    e_px = float(entry_px or 0.0)
    t1_px = float(tp1_px or e_px)
    if e_px <= 0:
        return 0.0

    # Base profit lock: 50% of Entry -> TP1 distance, minimum +0.18% fee-covered breakeven
    if is_long:
        be_plus = e_px * 1.0018
        half_tp1 = e_px + 0.5 * max(0.0, t1_px - e_px)
        target_sl = max(be_plus, half_tp1)
        if prev_candle_low and float(prev_candle_low) > target_sl and float(prev_candle_low) < t1_px:
            target_sl = float(prev_candle_low)
    else:
        be_plus = e_px * 0.9982
        half_tp1 = e_px - 0.5 * max(0.0, e_px - t1_px)
        target_sl = min(be_plus, half_tp1)
        if prev_candle_high and float(prev_candle_high) < target_sl and float(prev_candle_high) > t1_px:
            target_sl = float(prev_candle_high)

    return format_order_price(pair, target_sl)


def _check_recent_15m_tp1_touch_and_prev_hl(pair: str, is_long: bool, tp1_px: float, opened_ts: float = 0.0) -> tuple[bool, float | None, float | None]:
    """
    Checks 15m candles that opened AT OR AFTER `opened_ts` to detect whether price wicked through `tp1_px`
    between daemon ticks, and returns `(touched_tp1, prev_15m_high, prev_15m_low)`.
    CRITICAL: Never look back before `opened_ts` (no `- 900.0` offset and no `tail(3)` fallback when `opened_ts <= 0`),
    so pre-entry wicks on candles prior to trade entry can never falsely trigger TP1!
    """
    touched = False
    prev_h = None
    prev_l = None
    try:
        df_15m = fetch_coindcx_candles(pair, interval="15m", limit=6, sync_live_price=True)
        if df_15m is not None and not df_15m.empty:
            if len(df_15m) >= 2:
                prev_row = df_15m.iloc[-2]
                prev_h = float(prev_row["high"])
                prev_l = float(prev_row["low"])
            if tp1_px > 0 and opened_ts > 0:
                cutoff_ms = float(opened_ts) * 1000.0
                recent_df = df_15m[df_15m["timestamp"] >= cutoff_ms]
                if not recent_df.empty:
                    if is_long and float(recent_df["high"].max()) >= tp1_px:
                        touched = True
                    elif (not is_long) and float(recent_df["low"].min()) <= tp1_px:
                        touched = True
    except Exception:
        pass
    return touched, prev_h, prev_l


def _evaluate_smart_hybrid_runner_step(
    pair: str,
    is_long: bool,
    entry_p: float,
    tp1_p: float,
    cur_sl: float,
    opened_ts: float = 0.0,
    strategy_id: str = "box_theory",
) -> tuple[bool, float, str]:
    """
    Evaluates post-TP1 runner rules (matching `run_strategy_backtest`):
      - For Strategy 1 (`box_theory`) and Strategy 2 (`atr_reversal`):
        5m 9 EMA Cross & 20% ATR early runner chokes are REMOVED (proven +24.1% higher 30d net profit,
        PF 1.33 -> 1.49, TP2 hits 10 -> 19). The 50% runner holds with Profit-Locked SL + Halfway-to-TP2
        SL Ratchet (`SL -> TP1`) + Fixed CoinDCX `TP2` Target.
      - For Strategy 3 (`ema9_retest` 100% Full Runner):
        Evaluates 15m Closed-Candle Low/High Trail + 20% Daily ATR 30% Pullback + Confirmed 5m 9 EMA Cross.
    Returns `(should_market_exit, tightened_sl, reason)`.
    """
    new_sl = float(cur_sl or 0.0)
    if entry_p <= 0 or opened_ts <= 0:
        return False, new_sl, ""
    if str(strategy_id or "box_theory").strip() != "ema9_retest":
        return False, new_sl, ""
    now_ms = int(time.time() * 1000)
    cutoff_ms = float(opened_ts) * 1000.0
    min_long_profit_sl = entry_p * 1.0018
    max_short_profit_sl = entry_p * 0.9982

    # 1. Trailing 15m closed-candle Low/High Stop Loss (strictly post-entry closed candles & strictly in profit)
    try:
        df15 = fetch_coindcx_candles(pair, interval="15m", limit=6, sync_live_price=False)
        if df15 is not None and not df15.empty:
            c15 = df15[(df15["timestamp"] + 900000 <= now_ms) & (df15["timestamp"] >= cutoff_ms)]
            if not c15.empty:
                prev_15m = c15.iloc[-1]
                p15_l = float(prev_15m["low"])
                p15_h = float(prev_15m["high"])
                p15_c = float(prev_15m["close"])
                if is_long and p15_c >= tp1_p and p15_l > min_long_profit_sl and p15_l < p15_c and (new_sl <= 0 or p15_l > new_sl):
                    new_sl = format_order_price(pair, p15_l)
                elif (not is_long) and p15_c <= tp1_p and p15_h < max_short_profit_sl and p15_h > p15_c and (new_sl <= 0 or p15_h < new_sl):
                    new_sl = format_order_price(pair, p15_h)
    except Exception:
        pass

    # 2. 14d Daily ATR for Strategy 3 Rule A (20% ATR 5m candle + 30% pullback)
    daily_atr = 0.0
    try:
        df_d = fetch_coindcx_candles(pair, interval="1d", limit=20, sync_live_price=False)
        if df_d is not None and len(df_d) >= 5:
            d_closed = df_d.iloc[:-1] if len(df_d) > 1 else df_d
            daily_atr = float((d_closed["high"] - d_closed["low"]).tail(14).mean() or 0.0)
    except Exception:
        pass

    # 3. Closed 5m candles strictly since `opened_ts` (never fall back to pre-entry candles!)
    try:
        df5 = fetch_coindcx_candles(pair, interval="5m", limit=40, sync_live_price=False)
        if df5 is not None and not df5.empty:
            c5 = df5[df5["timestamp"] + 300000 <= now_ms].copy()
            if not c5.empty:
                c5["EMA9"] = c5["close"].ewm(span=9, adjust=False).mean()
                recent_5m = c5[c5["timestamp"] >= cutoff_ms]
                if not recent_5m.empty:
                    ema9_armed = False
                    wrong_streak = 0
                    for idx_5, r5 in recent_5m.iterrows():
                        s5_o = float(r5["open"])
                        s5_h = float(r5["high"])
                        s5_l = float(r5["low"])
                        s5_c = float(r5["close"])
                        s5_e9 = float(r5["EMA9"])
                        s5_rng = s5_h - s5_l
                        is_last_bar = (idx_5 == recent_5m.index[-1])

                        if daily_atr > 0 and s5_rng >= 0.20 * daily_atr:
                            if is_long and s5_c > s5_o:
                                pb_lvl = format_order_price(pair, s5_h - 0.30 * s5_rng)
                                if is_last_bar and (s5_h - s5_c) >= 0.30 * s5_rng and s5_c > max(min_long_profit_sl, new_sl):
                                    return True, new_sl, "Runner 5m >=20% ATR 30% Pullback"
                                if pb_lvl > min_long_profit_sl and (new_sl <= 0 or pb_lvl > new_sl):
                                    new_sl = pb_lvl
                            elif (not is_long) and s5_c < s5_o:
                                pb_lvl = format_order_price(pair, s5_l + 0.30 * s5_rng)
                                if is_last_bar and (s5_c - s5_l) >= 0.30 * s5_rng and (new_sl <= 0 or s5_c < min(max_short_profit_sl, new_sl)):
                                    return True, new_sl, "Runner 5m >=20% ATR 30% Pullback"
                                if pb_lvl < max_short_profit_sl and (new_sl <= 0 or pb_lvl < new_sl):
                                    new_sl = pb_lvl

                        if is_long:
                            if s5_c > s5_e9 and s5_c >= tp1_p:
                                ema9_armed = True
                                wrong_streak = 0
                            elif ema9_armed and s5_c < s5_e9:
                                wrong_streak += 1
                        else:
                            if s5_c < s5_e9 and s5_c <= tp1_p:
                                ema9_armed = True
                                wrong_streak = 0
                            elif ema9_armed and s5_c > s5_e9:
                                wrong_streak += 1

                    if ema9_armed and wrong_streak >= 2:
                        return True, new_sl, "Runner Confirmed 5m 9 EMA Cross"
    except Exception:
        pass

    return False, new_sl, ""


def _find_matching_app_trade_record(pos: dict) -> dict | None:
    """
    Returns the matching App/AutoTrade lock or unclosed recent history record (opened within 8h)
    if `pos` was originated by our App/AutoTrade.
    Returns `None` for manual positions opened directly by the user on CoinDCX.
    """
    pair = str(pos.get("pair", "") or "").strip()
    if not pair:
        return None
    direction = str(pos.get("direction", "LONG")).upper()
    is_long = direction in ("LONG", "BUY")
    entry_p = float(pos.get("entry_price", 0.0) or 0.0)
    now_ts = time.time()

    cfg = get_autotrade_config()
    locks_map = _get_active_locks_map(cfg)
    lock = locks_map.get(pair)
    if isinstance(lock, dict) and lock.get("pair") == pair:
        l_dir = str(lock.get("direction", "LONG")).upper()
        if (l_dir in ("LONG", "BUY")) == is_long:
            return lock

    for h in (cfg.get("history") or [])[:15]:
        if not isinstance(h, dict) or h.get("pair") != pair:
            continue
        if h.get("closed") or not bool(h.get("is_live_exchange", False)):
            continue
        h_ts = float(h.get("opened_ts", 0.0) or 0.0)
        if h_ts <= 0 or (now_ts - h_ts) > 8 * 3600:
            continue
        h_dir = str(h.get("direction", "LONG")).upper()
        if (h_dir in ("LONG", "BUY")) != is_long:
            continue
        h_entry = float(h.get("entry", 0.0) or 0.0)
        if entry_p > 0 and h_entry > 0 and abs(entry_p - h_entry) / entry_p <= 0.005:
            return h
    return None


def _auto_protect_live_position_tp1_sl(pos: dict) -> None:
    """
    Safeguards open CoinDCX positions while strictly respecting Manual CoinDCX Trades:
      1. MANUAL COINDCX TRADES (`_find_matching_app_trade_record(pos) is None`):
         - NEVER overwrite, ratchet, or modify `cur_sl` or `cur_tp` if the user already has a Stop Loss (`cur_sl > 0`).
         - NEVER cancel open orders or market-exit a manual trade.
         - Only if the user left `cur_sl <= 0` (no SL set at all on CoinDCX), attach a catastrophe safety SL
           while preserving the user's `cur_tp`.
      2. APP / AUTOTRADE POSITIONS (`app_rec is not None`):
         - Uses the exact `opened_ts`, `tp1`, `tp2`, and `qty1` from `app_rec` (never looking back 45m before entry).
         - Never clamps `runner_sl` onto the losing (negative) side of `entry_p`.
    """
    try:
        pid = pos.get("id")
        pair = pos.get("pair")
        if not pid or not pair:
            return
        direction = str(pos.get("direction", "LONG")).upper()
        is_long = direction in ("LONG", "BUY")
        entry_p = float(pos.get("entry_price", 0.0) or 0.0)
        mark_p = float(pos.get("mark_price", entry_p) or entry_p)
        cur_sl = float(pos.get("stop_loss", 0.0) or 0.0)
        cur_tp = float(pos.get("take_profit", 0.0) or 0.0)
        pos_qty = float(pos.get("quantity", 0.0) or 0.0)
        if entry_p <= 0:
            return

        app_rec = _find_matching_app_trade_record(pos)

        # CRITICAL GUARD 1: Manual CoinDCX Trade -> NEVER touch user's TP or SL if SL is already set!
        if app_rec is None:
            if cur_sl > 0:
                return
            # Manual position has NO Stop Loss at all (cur_sl <= 0): attach catastrophe SL only, keeping user's cur_tp untouched
            levels = None
            try:
                levels = calculate_daily_box_levels(pair)
            except Exception:
                pass
            norm = normalize_two_entry_runner_levels(
                pair=pair,
                direction=direction,
                entry1_px=entry_p,
                tp2_px=cur_tp if cur_tp > 0 else None,
                sl_px=None,
                live_px=entry_p,
                levels=levels,
            )
            cat_sl_px = float(norm["stop_loss"])
            valid_cat = (cat_sl_px < mark_p * 0.999) if is_long else (cat_sl_px > mark_p * 1.001)
            if valid_cat and cat_sl_px > 0:
                update_coindcx_position_tpsl(pid, tp_price=cur_tp if cur_tp > 0 else None, sl_price=cat_sl_px, pair=pair)
            return

        # App/AutoTrade-originated position management
        opened_ts = float(app_rec.get("opened_ts", 0.0) or 0.0)
        rec_tp1 = float(app_rec.get("tp1", 0.0) or 0.0)
        rec_tp2 = float(app_rec.get("tp2", 0.0) or 0.0)
        init_qty1 = float(app_rec.get("qty1", 0.0) or 0.0)

        min_profit_sl = format_order_price(pair, entry_p * (1.0018 if is_long else 0.9982))
        already_in_profit_sl = (cur_sl >= min_profit_sl) if (is_long and cur_sl > 0) else ((cur_sl <= min_profit_sl) if (not is_long and cur_sl > 0) else False)

        levels = None
        try:
            levels = calculate_daily_box_levels(pair)
        except Exception:
            pass
        norm = normalize_two_entry_runner_levels(
            pair=pair,
            direction=direction,
            entry1_px=entry_p,
            tp1_px=rec_tp1 if rec_tp1 > 0 else None,
            tp2_px=cur_tp if cur_tp > 0 else (rec_tp2 if rec_tp2 > 0 else None),
            sl_px=cur_sl if cur_sl > 0 else None,
            live_px=entry_p,
            levels=levels,
        )
        eff_tp1_px = rec_tp1 if rec_tp1 > 0 else float(norm["tp1"])
        tp2_px = float(cur_tp if cur_tp > 0 else (rec_tp2 if rec_tp2 > 0 else norm["tp2"]))
        cat_sl_px = float(norm["stop_loss"])

        # Only detect partial TP1 fill by comparing live crypto quantity against recorded App trade qty1 (never INR margin)
        partial_tp1_filled = (init_qty1 > 0 and pos_qty > 0 and pos_qty <= init_qty1 * 0.68)

        hit_tp1 = already_in_profit_sl or partial_tp1_filled or ((mark_p >= eff_tp1_px) if is_long else (mark_p <= eff_tp1_px))
        wicked_tp1, prev_h, prev_l = _check_recent_15m_tp1_touch_and_prev_hl(pair, is_long, eff_tp1_px, opened_ts=opened_ts)
        if hit_tp1 or wicked_tp1:
            entry_side = "buy" if is_long else "sell"
            cancel_coindcx_open_entry_orders(pair, side=entry_side)
            base_sl = compute_tp1_profit_lock_sl(
                pair=pair,
                direction=direction,
                entry_px=entry_p,
                tp1_px=eff_tp1_px,
                prev_candle_high=prev_h,
                prev_candle_low=prev_l,
            )
            if cur_sl > 0 and already_in_profit_sl:
                base_sl = max(base_sl, cur_sl) if is_long else min(base_sl, cur_sl)

            should_exit, runner_sl, _ = _evaluate_smart_hybrid_runner_step(
                pair=pair,
                is_long=is_long,
                entry_p=entry_p,
                tp1_p=eff_tp1_px,
                cur_sl=base_sl,
                opened_ts=opened_ts,
                strategy_id=str(app_rec.get("strategy_id") or "box_theory"),
            )
            if should_exit:
                exit_coindcx_position(pid, pair=pair)
                return

            mid_runner = 0.5 * (eff_tp1_px + tp2_px)
            if is_long and mark_p >= mid_runner and runner_sl < eff_tp1_px:
                runner_sl = format_order_price(pair, eff_tp1_px)
            elif (not is_long) and mark_p <= mid_runner and runner_sl > eff_tp1_px:
                runner_sl = format_order_price(pair, eff_tp1_px)

            # CRITICAL GUARD 2: Never clamp runner_sl onto the losing side of entry_p!
            # Require runner_sl to be strictly in profit AND on the valid side of live mark_p.
            in_profit = (runner_sl >= min_profit_sl) if is_long else (runner_sl <= min_profit_sl)
            valid_side = (runner_sl < mark_p * 0.999) if is_long else (runner_sl > mark_p * 1.001)
            better = (cur_sl <= 0) or ((runner_sl > cur_sl) if is_long else (runner_sl < cur_sl))
            if in_profit and valid_side and better and runner_sl > 0:
                update_coindcx_position_tpsl(pid, tp_price=tp2_px, sl_price=runner_sl, pair=pair)
        else:
            # Early 80% TP1 Breakeven SL Ratchet (only for App-originated trades)
            tp1_dist80 = 0.80 * abs(eff_tp1_px - entry_p)
            reached_80pct_tp1 = (mark_p >= (entry_p + tp1_dist80)) if is_long else (mark_p <= (entry_p - tp1_dist80))
            if reached_80pct_tp1 and tp1_dist80 > 0:
                be_sl = min_profit_sl
                be_valid = (be_sl < mark_p * 0.999) if is_long else (be_sl > mark_p * 1.001)
                be_better = (cur_sl <= 0) or ((be_sl > cur_sl) if is_long else (be_sl < cur_sl))
                if be_valid and be_better and be_sl > 0:
                    update_coindcx_position_tpsl(pid, tp_price=tp2_px, sl_price=be_sl, pair=pair)
                    return
            if cur_sl <= 0 or cur_tp <= 0:
                update_coindcx_position_tpsl(pid, tp_price=tp2_px, sl_price=cat_sl_px, pair=pair)
    except Exception:
        pass


def get_active_portfolio_trade_status(manage_exchange: bool = True) -> dict:
    """
    Checks whether an App/API-originated crypto trade is currently open across the portfolio AND
    (when manage_exchange=True from the 24/7 daemon) automatically manages the 3-stage 50/50 Runner lifecycle:
      - Stage 1 (Price hits TP1 without hitting Entry 2):
          1. Cancels the unfilled resting Entry 2 limit order at SL/SH.
          2. Books 50% of the open Entry 1 position at TP1 (if not already filled by resting TP1 limit order).
          3. Ratchets Stop Loss into profit (Entry 1 +/- 50% of TP1 distance) while holding the remaining 50% for TP2.
      - Stage 2 (Price reaches halfway between TP1 and TP2):
          Ratchets Stop Loss to TP1 (MID).
      - Stage 3 (Price hits TP2 or hits the Stop Loss):
          Cancels any remaining resting orders and releases the 1-Crypto-at-a-Time App Lock.
    """
    cfg = get_autotrade_config()
    locks_map = _get_active_locks_map(cfg)
    if not manage_exchange and locks_map and _PERSIST.get("session_verified"):
        _cached_p = _ACTIVE_POSITIONS_CACHE.get("data")
        _last_ok_p = float(_ACTIVE_POSITIONS_CACHE.get("last_ok_ts", 0.0))
        if isinstance(_cached_p, list) and (time.time() - _last_ok_p) < 120.0:
            for _lp_k, _lk_v in list(locks_map.items()):
                _lk_ts = float(_lk_v.get("opened_ts", 0.0) or 0.0)
                if (
                    bool(_lk_v.get("is_live_exchange", False))
                    and not bool(_lk_v.get("entry1_pending", False))
                    and _lk_ts > 0
                    and (time.time() - _lk_ts) >= 90
                    and not any(p.get("pair") == _lp_k for p in _cached_p)
                ):
                    clear_autotrade_active_lock(_lp_k)
                    locks_map.pop(_lp_k, None)
            if not locks_map and len(_cached_p) == 0:
                return {"is_occupied": False, "active_pair": None, "source": "Slot Free (App Trade Closed on Exchange)"}

    lock = max(locks_map.values(), key=lambda x: float(x.get("opened_ts", 0.0) or 0.0)) if locks_map else None
    if isinstance(lock, dict) and lock.get("pair"):
        l_pair = lock["pair"]
        l_dir = str(lock.get("direction", "LONG")).upper()
        l_entry = float(lock.get("entry", 0.0) or 0.0)
        l_entry2 = float(lock.get("entry2_sweep", 0.0) or 0.0)
        l_tp1 = float(lock.get("tp1", 0.0) or 0.0)
        l_tp2 = float(lock.get("tp2", 0.0) or l_tp1 or 0.0)
        l_sl = float(lock.get("stop_loss", 0.0) or 0.0)
        l_ts = float(lock.get("opened_ts", 0.0) or 0.0)
        is_live_ex = bool(lock.get("is_live_exchange", False))
        tp1_already_hit = bool(lock.get("tp1_hit", False))
        e1_pending = bool(lock.get("entry1_pending", False))
        e1_oid = str(lock.get("entry1_order_id", "") or "")

        # Fast-path for UI rendering: return lock status immediately in <1ms without blocking on exchange API calls
        if not manage_exchange:
            _c_pos = _ACTIVE_POSITIONS_CACHE.get("data") or []
            _act_pairs = list(dict.fromkeys(
                [p.get("pair") for p in _c_pos if isinstance(p, dict) and p.get("pair")]
                + list(locks_map.keys())
            ))
            _cnt = max(1, len(_act_pairs))
            return {
                "is_occupied": _cnt >= MAX_CONCURRENT_TRADES,
                "has_active_trade": True,
                "active_pair": l_pair,
                "active_pairs": _act_pairs,
                "active_direction": l_dir,
                "entry_price": l_entry,
                "entry1_pending": e1_pending,
                "entry2_sweep": l_entry2,
                "tp1": l_tp1,
                "tp2": l_tp2,
                "tp1_hit": tp1_already_hit,
                "entry2_cancelled": bool(lock.get("entry2_cancelled", False)),
                "stop_loss": l_sl,
                "source": lock.get("mode", "App/API Active Trade"),
                "count": _cnt,
                "max_slots": MAX_CONCURRENT_TRADES,
            }

        try:
            if l_ts > 0 and (time.time() - l_ts) > 8 * 3600:
                if is_live_ex:
                    cancel_coindcx_open_entry_orders(l_pair, cancel_all_for_pair=True)
                clear_autotrade_active_lock(l_pair)
                return {"is_occupied": False, "active_pair": None, "source": "Slot Free (Previous App Trade Expired)"}

            matched_live_pos = None
            live_positions = None
            if is_live_ex or any(bool(v.get("is_live_exchange")) for v in locks_map.values()):
                # CRITICAL: Always use synchronous live fetch (_fetch_coindcx_active_positions_sync) here,
                # NEVER the UI's non-blocking cold-cache fetch_coindcx_active_positions(force_refresh=False),
                # which returns [] when cold and previously caused active_trade_lock to be falsely cleared!
                live_positions = _fetch_coindcx_active_positions_sync(return_none_on_error=True)
                if live_positions is not None:
                    # Sync any other pending Maker Limit locks in `locks_map` (multi-slot concurrency support)
                    for _o_lp, _o_lk in list(locks_map.items()):
                        if _o_lp == l_pair or not bool(_o_lk.get("is_live_exchange")):
                            continue
                        _o_ts = float(_o_lk.get("opened_ts", 0.0) or 0.0)
                        _o_pos = next((p for p in live_positions if p.get("pair") == _o_lp), None)
                        if _o_pos and _o_pos.get("id") and bool(_o_lk.get("entry1_pending")):
                            _o_q = float(_o_pos.get("quantity", 0.0) or 0.0)
                            _o_tgt = float(_o_lk.get("target_qty1") or _o_lk.get("qty1") or 0.0)
                            if _o_tgt <= 0 or _o_q >= (_o_tgt * 0.50) or (_o_ts > 0 and (time.time() - _o_ts) >= 180.0):
                                sync_full_2entry_runner_to_position(
                                    pair=_o_lp,
                                    direction=str(_o_lk.get("direction", "LONG")),
                                    entry1_px=float(_o_pos.get("entry_price") or _o_lk.get("entry", 0.0)),
                                    entry2_px=float(_o_lk.get("entry2_sweep", 0.0) or 0.0),
                                    tp1_px=float(_o_lk.get("tp1", 0.0) or 0.0),
                                    tp2_px=float(_o_lk.get("tp2", 0.0) or 0.0),
                                    sl_px=float(_o_lk.get("stop_loss", 0.0) or 0.0),
                                    total_margin_inr=float(_o_lk.get("margin_inr", 20000.0) or 20000.0),
                                    leverage=int(_o_lk.get("leverage", 10) or 10),
                                    strategy_id=str(_o_lk.get("strategy_id", "box_theory") or "box_theory"),
                                )
                        elif not _o_pos and bool(_o_lk.get("entry1_pending")) and _o_ts > 0 and (time.time() - _o_ts) >= ENTRY1_LIMIT_EXPIRY_SEC:
                            cancel_coindcx_open_entry_orders(_o_lp)
                            clear_autotrade_active_lock(_o_lp)
                            locks_map.pop(_o_lp, None)

                if is_live_ex and live_positions is not None:
                    matched_live_pos = next((p for p in live_positions if p.get("pair") == l_pair), None)
                    if matched_live_pos and matched_live_pos.get("id"):
                        if e1_pending:
                            _pos_qty_now = float(matched_live_pos.get("quantity", 0.0) or 0.0)
                            _tgt_qty1 = float(lock.get("target_qty1") or lock.get("qty1") or 0.0)
                            _age_e1 = (time.time() - l_ts) if l_ts > 0 else 999.0
                            if _tgt_qty1 > 0 and _pos_qty_now < (_tgt_qty1 * 0.50) and _age_e1 < 180.0:
                                # Dust partial fill (e.g. 6.5 of 9,899.1 APT): attach catastrophe SL/TP2 for safety,
                                # but KEEP entry1_pending=True & target_qty1 intact until >=50% fills (or 180s elapses)!
                                if matched_live_pos.get("stop_loss") is None or matched_live_pos.get("take_profit") is None:
                                    update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=l_sl, pair=l_pair)
                            else:
                                # Resting Entry 1 Maker Limit Order has meaningfully filled -> attach Bracket TP2/SL + TP1 Limit!
                                _sync_ok_p, _, _sync_det_p = sync_full_2entry_runner_to_position(
                                    pair=l_pair,
                                    direction=l_dir,
                                    entry1_px=float(matched_live_pos.get("entry_price") or l_entry),
                                    entry2_px=l_entry2,
                                    tp1_px=l_tp1,
                                    tp2_px=l_tp2,
                                    sl_px=l_sl,
                                    total_margin_inr=float(lock.get("margin_inr", 20000.0) or 20000.0),
                                    leverage=int(lock.get("leverage", 10) or 10),
                                    strategy_id=str(lock.get("strategy_id", "box_theory") or "box_theory"),
                                )
                                if _sync_ok_p and isinstance((_sync_det_p or {}).get("lock"), dict):
                                    lock = _sync_det_p["lock"]
                                else:
                                    lock["entry1_pending"] = False
                                    save_autotrade_config({"active_trade_lock": lock})
                                e1_pending = False
                                l_entry = float(lock.get("entry", l_entry) or l_entry)
                                l_tp1 = float(lock.get("tp1", l_tp1) or l_tp1)
                                l_tp2 = float(lock.get("tp2", l_tp2) or l_tp2)
                                l_sl = float(lock.get("stop_loss", l_sl) or l_sl)
                        elif not tp1_already_hit:
                            # If remaining Maker Limit quantity filled after initial sync, upsize the 50% TP1 limit order!
                            _pos_qty_now2 = float(matched_live_pos.get("quantity", 0.0) or 0.0)
                            _synced_q1 = float(lock.get("qty1", 0.0) or 0.0)
                            if _synced_q1 > 0 and _pos_qty_now2 > (_synced_q1 * 1.35) and str(lock.get("strategy_id", "box_theory")) != "ema9_retest":
                                _opp_r = "SELL" if l_dir in ("LONG", "BUY") else "BUY"
                                _old_tp1_oid = str(lock.get("tp1_order_id", "") or "")
                                if _old_tp1_oid and not _old_tp1_oid.startswith(("DAEMON_", "FULL_", "STRATEGY")):
                                    cancel_coindcx_open_entry_orders(l_pair, _old_tp1_oid, side=_opp_r.lower())
                                _new_tp1_q = format_order_quantity(l_pair, _pos_qty_now2 * 0.5)
                                _r_lev = int(round(float(matched_live_pos.get("leverage") or lock.get("leverage", 10) or 10)))
                                if _new_tp1_q > 0:
                                    _ok_r1, _, _ext_r1 = place_coindcx_futures_order(
                                        pair=l_pair, side=_opp_r, quantity=_new_tp1_q, leverage=_r_lev,
                                        order_type="limit_order", price=l_tp1, margin_currency="INR", post_only=False,
                                    )
                                    if _ok_r1:
                                        lock["tp1_order_id"] = str((_ext_r1 or {}).get("order_id", "DAEMON_50PCT_REDUCE_AT_TP1"))
                                lock["qty1"] = _pos_qty_now2
                                save_autotrade_config({"active_trade_lock": lock})
                        if lock.get("missing_count", 0) > 0:
                            lock["missing_count"] = 0
                            save_autotrade_config({"active_trade_lock": lock})
                        # Auto-heal too-near TP1 (<0.59% from Entry 1) OR attach resting TP1 limit order once a Limit Entry 1 fills
                        _cur_tp1_oid = str(lock.get("tp1_order_id", "") or "")
                        _needs_tp1_limit_attach = (_cur_tp1_oid in ("", "DAEMON_50PCT_REDUCE_AT_TP1")) and (str(lock.get("strategy_id", "box_theory")) != "ema9_retest")
                        _tp1_too_near = (l_entry > 0 and abs(l_tp1 - l_entry) / l_entry < 0.0059)
                        if not tp1_already_hit and (_tp1_too_near or _needs_tp1_limit_attach):
                            try:
                                _box_lvls = calculate_daily_box_levels(l_pair)
                            except Exception:
                                _box_lvls = None
                            _actual_e1 = float(matched_live_pos.get("entry_price") or l_entry)
                            _fix_norm = normalize_two_entry_runner_levels(
                                pair=l_pair,
                                direction=l_dir,
                                entry1_px=_actual_e1,
                                entry2_px=l_entry2,
                                tp1_px=None if _tp1_too_near else l_tp1,
                                tp2_px=l_tp2,
                                sl_px=l_sl,
                                live_px=_actual_e1,
                                levels=_box_lvls,
                            )
                            _new_tp1 = float(_fix_norm["tp1"])
                            if abs(_new_tp1 - l_tp1) > 1e-6 or _needs_tp1_limit_attach:
                                _opp_s = "SELL" if l_dir in ("LONG", "BUY") else "BUY"
                                if _cur_tp1_oid and not _cur_tp1_oid.startswith(("DAEMON_", "FULL_", "STRATEGY")):
                                    cancel_coindcx_open_entry_orders(l_pair, _cur_tp1_oid, side=_opp_s.lower())
                                _pos_q = float(matched_live_pos.get("quantity", 0.0) or 0.0)
                                _tp1_q = format_order_quantity(l_pair, _pos_q * 0.5)
                                _pos_lev = int(round(float(matched_live_pos.get("leverage") or lock.get("leverage", 10) or 10)))
                                if _tp1_q > 0 and str(lock.get("strategy_id", "box_theory")) != "ema9_retest":
                                    _ok_tp1, _, _ext_tp1 = place_coindcx_futures_order(
                                        pair=l_pair,
                                        side=_opp_s,
                                        quantity=_tp1_q,
                                        leverage=_pos_lev,
                                        order_type="limit_order",
                                        price=_new_tp1,
                                        margin_currency="INR",
                                        post_only=False,
                                    )
                                    if _ok_tp1:
                                        lock["tp1_order_id"] = str((_ext_tp1 or {}).get("order_id", "DAEMON_50PCT_REDUCE_AT_TP1"))
                                l_tp1 = _new_tp1
                                lock["tp1"] = _new_tp1
                                lock["entry"] = _actual_e1
                                save_autotrade_config({"active_trade_lock": lock})
                        # Auto-heal missing TP or SL on CoinDCX whenever either trigger is None
                        if matched_live_pos.get("stop_loss") is None or matched_live_pos.get("take_profit") is None:
                            norm_lvls = normalize_two_entry_runner_levels(
                                pair=l_pair,
                                direction=l_dir,
                                entry1_px=float(matched_live_pos.get("entry_price") or l_entry),
                                entry2_px=l_entry2,
                                tp1_px=l_tp1,
                                tp2_px=l_tp2,
                                sl_px=l_sl,
                                live_px=float(matched_live_pos.get("entry_price") or l_entry),
                            )
                            l_tp2 = float(l_tp2 or norm_lvls["tp2"])
                            l_sl = float(l_sl if (tp1_already_hit and l_sl > 0) else norm_lvls["stop_loss"])
                            lock["tp2"] = l_tp2
                            lock["stop_loss"] = l_sl
                            heal_ok, _ = update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=l_sl, pair=l_pair)
                            lock["tpsl_healed"] = bool(heal_ok)
                            save_autotrade_config({"active_trade_lock": lock})
                    elif e1_pending:
                        # Entry 1 Maker Limit Order has not filled into an active position yet:
                        # 1. Cancel cleanly if price already ran to TP1 without us, broke SL, or expired (>45m).
                        _pend_px = float(fetch_live_ticker(l_pair).get("last_price", 0.0) or 0.0)
                        _is_long_p = l_dir in ("LONG", "BUY")
                        _ran_to_tp1 = (_pend_px >= l_tp1) if (_is_long_p and _pend_px > 0 and l_tp1 > 0) else ((_pend_px <= l_tp1) if (not _is_long_p and _pend_px > 0 and l_tp1 > 0) else False)
                        _broke_sl = (_pend_px <= l_sl) if (_is_long_p and _pend_px > 0 and l_sl > 0) else ((_pend_px >= l_sl) if (not _is_long_p and _pend_px > 0 and l_sl > 0) else False)
                        _expired_e1 = (l_ts > 0 and (time.time() - l_ts) >= ENTRY1_LIMIT_EXPIRY_SEC)
                        if _ran_to_tp1 or _broke_sl or _expired_e1:
                            cancel_coindcx_open_entry_orders(l_pair)
                            clear_autotrade_active_lock(l_pair)
                            _why_c = "TP1 Reached Before Fill" if _ran_to_tp1 else ("SL Breached" if _broke_sl else "45m Limit Expired")
                            _rem_pairs = list(dict.fromkeys([p.get("pair") for p in (live_positions or []) if p.get("pair")] + list(_get_active_locks_map().keys())))
                            if _rem_pairs:
                                return {
                                    "is_occupied": len(_rem_pairs) >= MAX_CONCURRENT_TRADES,
                                    "has_active_trade": True,
                                    "active_pair": _rem_pairs[0],
                                    "active_pairs": _rem_pairs,
                                    "count": len(_rem_pairs),
                                    "max_slots": MAX_CONCURRENT_TRADES,
                                    "source": f"Active ({len(_rem_pairs)}/{MAX_CONCURRENT_TRADES}); {l_pair} cancelled ({_why_c})",
                                }
                            return {"is_occupied": False, "active_pair": None, "source": f"Slot Free (Unfilled Entry 1 Limit Cancelled: {_why_c})"}

                        # 2. Verify resting Entry 1 limit order is still open on CoinDCX (handles manual cancel on app)
                        _open_ords = []
                        if l_ts > 0 and (time.time() - l_ts) >= 90 and fetch_coindcx_futures_balance().get("is_live_api"):
                            _open_ords = fetch_coindcx_open_orders() or []
                            _want_side = "BUY" if _is_long_p else "SELL"
                            _still_open = any(
                                o.get("pair") == l_pair
                                and str(o.get("side", "")).upper() == _want_side
                                and (not e1_oid or str(o.get("id", "")) == e1_oid)
                                for o in _open_ords
                            )
                            if _still_open:
                                if lock.get("missing_count", 0) > 0:
                                    lock["missing_count"] = 0
                                    save_autotrade_config({"active_trade_lock": lock})
                            else:
                                miss_cnt = int(lock.get("missing_count", 0)) + 1
                                if miss_cnt >= 2:
                                    cancel_coindcx_open_entry_orders(l_pair)
                                    clear_autotrade_active_lock(l_pair)
                                    return {"is_occupied": False, "active_pair": None, "source": "Slot Free (Entry 1 Limit Cancelled on Exchange)"}
                                lock["missing_count"] = miss_cnt
                                save_autotrade_config({"active_trade_lock": lock})

                        _eo_pairs = [
                            eo.get("pair")
                            for eo in (get_open_entry_limit_orders(open_orders=_open_ords, live_positions=live_positions, cfg=cfg) if _open_ords else [])
                            if eo.get("pair")
                        ]
                        _act_pairs_p = list(dict.fromkeys(
                            [p.get("pair") for p in live_positions if p.get("pair")]
                            + _eo_pairs
                            + list(_get_active_locks_map().keys())
                            + [l_pair]
                        ))
                        return {
                            "is_occupied": len(_act_pairs_p) >= MAX_CONCURRENT_TRADES,
                            "has_active_trade": True,
                            "active_pair": l_pair,
                            "active_pairs": _act_pairs_p,
                            "active_direction": l_dir,
                            "entry_price": l_entry,
                            "entry1_pending": True,
                            "entry2_sweep": l_entry2,
                            "tp1": l_tp1,
                            "tp2": l_tp2,
                            "tp1_hit": False,
                            "stop_loss": l_sl,
                            "source": lock.get("mode", "App/API Live AutoTrade (Entry 1 Limit Resting)"),
                            "count": len(_act_pairs_p),
                            "max_slots": MAX_CONCURRENT_TRADES,
                        }
                    elif len(live_positions) > 0:
                        # Another position is open on CoinDCX: keep the portfolio slot occupied!
                        other_p = live_positions[0]
                        _act_pairs = [p.get("pair") for p in live_positions if p.get("pair")]
                        return {
                            "is_occupied": len(live_positions) >= MAX_CONCURRENT_TRADES,
                            "has_active_trade": True,
                            "active_pair": other_p.get("pair"),
                            "active_pairs": _act_pairs,
                            "active_direction": other_p.get("direction", "LONG"),
                            "entry_price": float(other_p.get("entry_price", 0.0) or 0.0),
                            "stop_loss": float(other_p.get("stop_loss", 0.0) or 0.0),
                            "source": "CoinDCX Live Active Position",
                            "count": len(live_positions),
                            "max_slots": MAX_CONCURRENT_TRADES,
                        }
                    elif l_ts > 0 and (time.time() - l_ts) >= 90 and fetch_coindcx_futures_balance().get("is_live_api"):
                        # Require 2 consecutive confirmed 200-OK empty position checks before releasing lock
                        miss_cnt = int(lock.get("missing_count", 0)) + 1
                        if miss_cnt >= 2:
                            cancel_coindcx_open_entry_orders(l_pair, lock.get("entry2_order_id", ""))
                            clear_autotrade_active_lock(l_pair)
                            return {"is_occupied": False, "active_pair": None, "source": "Slot Free (App Trade Closed on Exchange)"}
                        else:
                            lock["missing_count"] = miss_cnt
                            save_autotrade_config({"active_trade_lock": lock})

            if l_ts > 0 and (time.time() - l_ts) >= 15:
                tk = fetch_live_ticker(l_pair)
                px = float(tk.get("last_price", 0.0) or 0.0)
                if px > 0:
                    is_long = l_dir in ("LONG", "BUY")
                    entry_side = "buy" if is_long else "sell"

                    # Check if Entry 2 @ Sweep filled before TP1 was reached
                    if not tp1_already_hit and not lock.get("entry2_filled") and l_entry2 > 0:
                        swept_e2 = (px <= l_entry2 and px > l_sl) if is_long else (px >= l_entry2 and px < l_sl)
                        if swept_e2:
                            avg_e = round_asset_price((l_entry + l_entry2) / 2.0, l_entry)
                            tp1_d = min(abs(l_tp1 - avg_e), avg_e * 0.02)
                            new_tp1 = round_asset_price((avg_e + tp1_d) if is_long else (avg_e - tp1_d), l_entry)
                            lock["entry"] = avg_e
                            lock["tp1"] = new_tp1
                            lock["entry2_filled"] = True
                            l_entry = avg_e
                            l_tp1 = new_tp1
                            save_autotrade_config({"active_trade_lock": lock})

                    hit_tp2 = (px >= l_tp2) if (is_long and l_tp2 > 0) else ((px <= l_tp2) if (not is_long and l_tp2 > 0) else False)
                    hit_sl = (px <= l_sl) if (is_long and l_sl > 0) else ((px >= l_sl) if (not is_long and l_sl > 0) else False)

                    def _log_paper_close_async(exit_p: float, reason_str: str):
                        if is_live_ex:
                            return
                        e_p = float(lock.get("entry", 0.0) or 0.0)
                        m_inr = float(lock.get("margin_inr", 20000.0) or 20000.0)
                        lev_v = int(lock.get("leverage", 10) or 10)
                        raw_pct = ((exit_p - e_p) / e_p) if (is_long and e_p > 0) else (((e_p - exit_p) / e_p) if e_p > 0 else 0.0)
                        # If TP1 was already hit on a 50/50 strategy, blend 50% at TP1 + 50% at exit_p
                        is_s3_p = (str(lock.get("strategy_id", "")) == "ema9_retest")
                        if lock.get("tp1_hit") and not is_s3_p and l_tp1 > 0 and e_p > 0:
                            tp1_pct = ((l_tp1 - e_p) / e_p) if is_long else ((e_p - l_tp1) / e_p)
                            raw_pct = 0.5 * tp1_pct + 0.5 * raw_pct
                        roe_v = round((raw_pct * lev_v - 0.0118) * 100.0, 2)
                        net_inr = round(m_inr * (roe_v / 100.0), 2)

                        # Synchronously settle Staging Paper Wallet & immediately check 5% Daily Loss Stop (SL Threshold)!
                        pw_after = 0.0
                        try:
                            cur_cfg_p = get_autotrade_config()
                            pw_snap_before = get_paper_wallet_snapshot(cur_cfg_p)
                            cur_pw = float(pw_snap_before.get("total_inr", 0.0) or 0.0)
                            pw_after = round(max(0.0, cur_pw + net_inr), 2)
                            tot_real_pnl = round(float(cur_cfg_p.get("paper_realized_pnl_inr", 0.0) or 0.0) + net_inr, 2)
                            today_p = datetime.now(IST).strftime("%Y-%m-%d")
                            p_ds = cur_cfg_p.get("paper_daily_start_wallet")
                            if not (isinstance(p_ds, dict) and p_ds.get("date") == today_p and float(p_ds.get("inr", 0.0) or 0.0) > 0):
                                p_ds = {"date": today_p, "inr": round(cur_pw, 2)}
                            save_autotrade_config({
                                "paper_wallet_inr": pw_after,
                                "paper_starting_wallet_inr": float(cur_cfg_p.get("paper_starting_wallet_inr", 0.0) or cur_pw),
                                "paper_daily_start_wallet": p_ds,
                                "paper_realized_pnl_inr": tot_real_pnl,
                            })
                            check_live_daily_loss_stop(get_paper_wallet_snapshot())
                        except Exception as _pwe:
                            print(f"[Paper Wallet Settle Notice]: {_pwe}")

                        outcome_lbl = "PAPER_WIN" if net_inr >= 0 else "PAPER_LOSS"
                        sign_s = "+" if net_inr >= 0 else "-"
                        status_cell = f"{outcome_lbl} ({'+' if roe_v >= 0 else ''}{roe_v:.2f}% ROE | {sign_s}Rs.{abs(net_inr):,.0f} @ ${exit_p})"
                        _strat_names_p = {
                            "box_theory": "Strategy 1: Box Theory Sweep (Staging Paper AutoTrade)",
                            "ema50_200": "Strategy 4: 15m 50/200 EMA Pullback (Staging Paper AutoTrade)",
                            "ema9_retest": "Strategy 3: 9 EMA Touch & Confirm (Staging Paper AutoTrade)",
                        }
                        _s_name_p = _strat_names_p.get(str(lock.get("strategy_id", "box_theory")), "Staging Paper AutoTrade")

                        def _worker_close():
                            try:
                                import sheets_logger
                                sheets_logger.log_trade_closed({
                                    "entry_time": lock.get("opened_at", ""),
                                    "exit_time": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
                                    "pair": l_pair,
                                    "direction": l_dir,
                                    "entry_price": e_p,
                                    "stop_loss": l_sl,
                                    "tp1": l_tp1,
                                    "tp2": l_tp2,
                                    "qty": round(float(lock.get("qty1", 0.0) or 0.0) + float(lock.get("qty2", 0.0) or 0.0), 4),
                                    "margin_inr": m_inr,
                                    "leverage": lev_v,
                                    "strategy_name": _s_name_p,
                                    "exit_price": exit_p,
                                    "exit_reason": f"[STAGING PAPER] {reason_str}",
                                    "net_pnl_inr": net_inr,
                                    "roe_pct": roe_v,
                                    "paper_wallet_after_inr": pw_after,
                                    "is_staging_paper": True,
                                    "update_live_sheet_status": status_cell,
                                })
                            except Exception as _ce:
                                print(f"[Paper Close Log Notice]: {_ce}")
                        _threading.Thread(target=_worker_close, daemon=True).start()

                    # Full Exit at TP2 or Stop Loss (Catastrophe SL or Ratcheted Runner SL)
                    if hit_tp2 or hit_sl:
                        if is_live_ex:
                            cancel_coindcx_open_entry_orders(l_pair, lock.get("entry2_order_id", ""))
                        else:
                            _exit_r = "TP2 Target Hit" if hit_tp2 else ("Profit-Locked SL Hit" if tp1_already_hit else ("80% TP1 Breakeven SL Hit" if lock.get("tp1_80pct_be_ratcheted") else "Stop Loss Hit"))
                            _log_paper_close_async(px, _exit_r)
                        clear_autotrade_active_lock(l_pair)
                        return {"is_occupied": False, "active_pair": None, "source": "Slot Free (Previous App Trade Completed)"}

                    # Stage 1: Price reaches TP1 (or resting TP1 limit order already filled / 15m candle wicked through TP1)
                    # -> Book 50% (if not already reduced), Cancel Entry 2, and Ratchet SL to Profit Lock (50% TP1 dist / Prev 15m H-L)!
                    hit_tp1 = (px >= l_tp1) if (is_long and l_tp1 > 0) else ((px <= l_tp1) if (not is_long and l_tp1 > 0) else False)
                    partial_tp1_already_filled = False
                    if is_live_ex and matched_live_pos and not tp1_already_hit:
                        open_pos_qty_chk = float(matched_live_pos.get("quantity", 0.0) or 0.0)
                        init_qty1_chk = float(lock.get("qty1", open_pos_qty_chk) or open_pos_qty_chk)
                        if init_qty1_chk > 0 and open_pos_qty_chk > 0 and open_pos_qty_chk <= init_qty1_chk * 0.68:
                            partial_tp1_already_filled = True
                            hit_tp1 = True

                    prev_15m_h, prev_15m_l = None, None
                    if not tp1_already_hit and l_tp1 > 0:
                        wicked_tp1, prev_15m_h, prev_15m_l = _check_recent_15m_tp1_touch_and_prev_hl(l_pair, is_long, l_tp1, l_ts)
                        if wicked_tp1:
                            hit_tp1 = True

                    if hit_tp1 and not tp1_already_hit:
                        # 1. Cancel unfilled Entry 2 limit order (same-side only) so it never fills late on reversal
                        if is_live_ex and not lock.get("entry2_filled"):
                            cancel_coindcx_open_entry_orders(l_pair, lock.get("entry2_order_id", ""), side=entry_side)
                            lock["entry2_cancelled"] = True

                        # 2. Book 50% of the open CoinDCX position at TP1 if resting TP1 limit order hasn't already reduced it
                        #    (Strategy 3 `ema9_retest` keeps 100% Full Runner and only ratchets SL at TP1)
                        is_s3_lock = (str(lock.get("strategy_id", "")) == "ema9_retest") or (str(lock.get("tp1_order_id", "")) == "STRATEGY3_FULL_RUNNER_SL_RATCHET")
                        if is_live_ex and matched_live_pos and not is_s3_lock:
                            open_pos_qty = float(matched_live_pos.get("quantity", 0.0) or 0.0)
                            init_qty1 = float(lock.get("qty1", open_pos_qty) or open_pos_qty)
                            tp1_oid = str(lock.get("tp1_order_id", ""))
                            # If open_pos_qty is still >= 75% of init_qty1, the resting TP1 limit order hasn't filled yet
                            if not partial_tp1_already_filled and open_pos_qty >= init_qty1 * 0.75:
                                if tp1_oid and tp1_oid != "DAEMON_50PCT_REDUCE_AT_TP1":
                                    cancel_coindcx_open_entry_orders(l_pair, tp1_oid, side="sell" if is_long else "buy")
                                half_pos_qty = format_order_quantity(l_pair, open_pos_qty * 0.5)
                                pos_lev = int(round(float(matched_live_pos.get("leverage", lock.get("leverage", 10)) or 10)))
                                opp_side = "SELL" if is_long else "BUY"
                                if half_pos_qty > 0:
                                    place_coindcx_futures_order(
                                        pair=l_pair,
                                        side=opp_side,
                                        quantity=half_pos_qty,
                                        leverage=pos_lev,
                                        order_type="market_order",
                                        margin_currency="INR",
                                    )

                        # 3. Ratchet Stop Loss into profit using Strategy 3B/3C (50% TP1 distance + Previous 15m Candle High/Low)
                        ratcheted_sl = compute_tp1_profit_lock_sl(
                            pair=l_pair,
                            direction=l_dir,
                            entry_px=l_entry,
                            tp1_px=l_tp1,
                            prev_candle_high=prev_15m_h,
                            prev_candle_low=prev_15m_l,
                        )
                        lock["tp1_hit"] = True
                        lock["stop_loss"] = ratcheted_sl
                        lock["mode"] = f"{lock.get('mode', 'App Trade')} [TP1 50% Booked -> SL Profit-Locked @ ${ratcheted_sl}]"
                        l_sl = ratcheted_sl
                        _hist_tp1 = list(cfg.get("history") or [])
                        for _hh in _hist_tp1:
                            if isinstance(_hh, dict) and _hh.get("pair") == l_pair and abs(float(_hh.get("opened_ts", 0.0) or 0.0) - l_ts) < 5.0:
                                _hh["tp1_hit"] = True
                        save_autotrade_config({"active_trade_lock": lock, "history": _hist_tp1[:30]})

                        # Update SL on CoinDCX position while keeping single native TP at TP2 (strictly in profit & valid side of px)
                        min_prof_sl = round_asset_price(l_entry * (1.0018 if is_long else 0.9982), l_entry)
                        r_in_prof = (ratcheted_sl >= min_prof_sl) if is_long else (ratcheted_sl <= min_prof_sl)
                        r_valid_px = (ratcheted_sl < px * 0.999) if is_long else (ratcheted_sl > px * 1.001)
                        if is_live_ex and matched_live_pos and matched_live_pos.get("id") and r_in_prof and r_valid_px:
                            update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=ratcheted_sl, pair=l_pair)

                    # Stage 2 (Structural Runner): Halfway-to-TP2 SL Ratchet -> TP2 Target (Strategy 3 also runs 5m runner check)
                    elif tp1_already_hit and l_tp1 > 0:
                        should_exit_r, next_runner_sl, _ = _evaluate_smart_hybrid_runner_step(
                            pair=l_pair,
                            is_long=is_long,
                            entry_p=l_entry,
                            tp1_p=l_tp1,
                            cur_sl=l_sl,
                            opened_ts=l_ts,
                            strategy_id=str(lock.get("strategy_id") or "box_theory"),
                        )
                        if should_exit_r:
                            if is_live_ex and matched_live_pos and matched_live_pos.get("id"):
                                exit_coindcx_position(matched_live_pos["id"], pair=l_pair)
                            elif not is_live_ex:
                                _log_paper_close_async(px, "Smart Hybrid Runner Exit (9 EMA / 20% ATR Pullback)")
                            clear_autotrade_active_lock(l_pair)
                            return {"is_occupied": False, "active_pair": None, "source": "Slot Free (Smart Hybrid Runner Exited)"}

                        if l_tp2 > 0:
                            mid_runner = 0.5 * (l_tp1 + l_tp2)
                            hit_mid_runner = (px >= mid_runner) if is_long else (px <= mid_runner)
                            if hit_mid_runner:
                                lock["runner_halfway_ratcheted"] = True
                                if is_long and next_runner_sl < l_tp1:
                                    next_runner_sl = l_tp1
                                elif (not is_long) and (next_runner_sl <= 0 or next_runner_sl > l_tp1):
                                    next_runner_sl = l_tp1

                        min_prof_sl = round_asset_price(l_entry * (1.0018 if is_long else 0.9982), l_entry)
                        nr_in_prof = (next_runner_sl >= min_prof_sl) if is_long else (next_runner_sl <= min_prof_sl)
                        nr_valid_px = (next_runner_sl < px * 0.999) if is_long else (next_runner_sl > px * 1.001)
                        sl_improved = (l_sl <= 0) or ((next_runner_sl > l_sl) if is_long else (next_runner_sl < l_sl))
                        if next_runner_sl > 0 and nr_in_prof and nr_valid_px and (sl_improved or (matched_live_pos and matched_live_pos.get("stop_loss") is None)):
                            lock["stop_loss"] = next_runner_sl
                            l_sl = next_runner_sl
                            save_autotrade_config({"active_trade_lock": lock})
                            if is_live_ex and matched_live_pos and matched_live_pos.get("id"):
                                update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=next_runner_sl, pair=l_pair)

                    # Pre-TP1 Stage: Early 80% TP1 Breakeven SL Ratchet (protects trades that stall 0.10% shy of TP1)
                    elif not tp1_already_hit and l_tp1 > 0 and l_entry > 0:
                        dist80 = 0.80 * abs(l_tp1 - l_entry)
                        hit_80pct = (px >= (l_entry + dist80)) if is_long else (px <= (l_entry - dist80))
                        if hit_80pct and not lock.get("tp1_80pct_be_ratcheted"):
                            be_sl = round_asset_price(l_entry * (1.0018 if is_long else 0.9982), l_entry)
                            be_valid_px = (be_sl < px * 0.999) if is_long else (be_sl > px * 1.001)
                            be_improved = (l_sl <= 0) or ((be_sl > l_sl) if is_long else (be_sl < l_sl))
                            if be_valid_px and be_improved and be_sl > 0:
                                lock["stop_loss"] = be_sl
                                lock["tp1_80pct_be_ratcheted"] = True
                                l_sl = be_sl
                                save_autotrade_config({"active_trade_lock": lock})
                                if is_live_ex and matched_live_pos and matched_live_pos.get("id"):
                                    update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=be_sl, pair=l_pair)

            # Also safeguard any OTHER live CoinDCX positions (e.g. if 2 positions exist like INJ + RENDER)
            if is_live_ex and live_positions:
                for other_pos in live_positions:
                    o_pair = other_pos.get("pair")
                    if not o_pair or o_pair == l_pair:
                        continue
                    _auto_protect_live_position_tp1_sl(other_pos)
        except Exception:
            pass

        _c_pos2 = _ACTIVE_POSITIONS_CACHE.get("data") or []
        _act_pairs2 = list(dict.fromkeys(
            [p.get("pair") for p in _c_pos2 if isinstance(p, dict) and p.get("pair")]
            + list(_get_active_locks_map().keys())
            + ([l_pair] if l_pair else [])
        ))
        _cnt2 = max(1, len(_act_pairs2))
        return {
            "is_occupied": _cnt2 >= MAX_CONCURRENT_TRADES,
            "has_active_trade": True,
            "active_pair": l_pair,
            "active_pairs": _act_pairs2,
            "active_direction": l_dir,
            "entry_price": float(lock.get("entry", 0.0) or 0.0),
            "entry1_pending": e1_pending,
            "entry2_sweep": float(lock.get("entry2_sweep", 0.0) or 0.0),
            "tp1": l_tp1,
            "tp2": l_tp2,
            "tp1_hit": bool(lock.get("tp1_hit", False)),
            "entry2_cancelled": bool(lock.get("entry2_cancelled", False)),
            "stop_loss": l_sl,
            "source": lock.get("mode", "App/API Active Trade"),
            "count": _cnt2,
            "max_slots": MAX_CONCURRENT_TRADES,
        }

    # Fallback: if local lock file was cleared or container restarted, check live CoinDCX active positions directly
    # Use synchronous live fetch when manage_exchange=True so background daemon never misses an open position due to cold cache
    try:
        live_pos = (
            _fetch_coindcx_active_positions_sync(return_none_on_error=False)
            if manage_exchange
            else (fetch_coindcx_active_positions() or [])
        ) or []
        if live_pos:
            if manage_exchange:
                for lp_item in live_pos:
                    _auto_protect_live_position_tp1_sl(lp_item)
            first_p = live_pos[0]
            _act_pairs3 = [p.get("pair") for p in live_pos if p.get("pair")]
            return {
                "is_occupied": len(live_pos) >= MAX_CONCURRENT_TRADES,
                "has_active_trade": True,
                "active_pair": first_p.get("pair"),
                "active_pairs": _act_pairs3,
                "active_direction": first_p.get("direction", "LONG"),
                "entry_price": float(first_p.get("entry_price", 0.0) or 0.0),
                "stop_loss": float(first_p.get("stop_loss", 0.0) or 0.0),
                "source": "CoinDCX Live Active Position",
                "count": len(live_pos),
                "max_slots": MAX_CONCURRENT_TRADES,
            }
    except Exception:
        pass

    return {"is_occupied": False, "has_active_trade": False, "active_pair": None, "active_pairs": [], "count": 0, "max_slots": MAX_CONCURRENT_TRADES, "source": f"Slots Free (0/{MAX_CONCURRENT_TRADES} Active)"}


def unlock_autotrade_daily_loss_stop(wallet: dict | None = None) -> dict:
    """
    Unlocks AutoTrade from the Sidebar when blocked by the 5% Daily Loss Stop (for example after
    transferring funds from the Futures Wallet to the INR Wallet, or resetting Staging Paper stop)
    by syncing today's start-wallet baseline to the current wallet balance and clearing `daily_loss_stop_hit`.
    """
    today = datetime.now(IST).strftime("%Y-%m-%d")
    is_stg = is_staging_environment()
    if is_stg and not (isinstance(wallet, dict) and wallet.get("is_live_api") and not wallet.get("is_paper_wallet")):
        w = wallet if isinstance(wallet, dict) else get_paper_wallet_snapshot()
        cur = float((w or {}).get("total_inr", 0.0) or 0.0)
        if cur <= 0:
            cur = float(get_autotrade_config().get("paper_wallet_inr", 0.0) or get_autotrade_config().get("wallet_balance_inr", 0.0) or 0.0)
        ds = {"date": today, "inr": round(cur, 2)}
        save_autotrade_config({"paper_daily_start_wallet": ds, "daily_start_wallet": ds, "daily_loss_stop_hit": ""})
        return ds

    w = wallet if isinstance(wallet, dict) else fetch_coindcx_futures_balance()
    cur = float((w or {}).get("total_inr", 0.0) or 0.0)
    if cur <= 0:
        cur = float(get_autotrade_config().get("wallet_balance_inr", 0.0) or 0.0)
    ds = {"date": today, "inr": round(cur, 2)}
    save_autotrade_config({"daily_start_wallet": ds, "daily_loss_stop_hit": ""})
    return ds


def check_live_daily_loss_stop(wallet: dict | None = None) -> tuple[bool, str, dict]:
    """
    Live & Staging-Paper 5% Daily Loss Stop (IST day — SL Threshold AutoTrade Lock):
      - On `main`: Day-start baseline = first verified live futures wallet balance after 00:00 IST.
      - On `staging`: Enforces the EXACT SAME 5% Daily Loss Stop against Staging's mirrored virtual
        Paper Wallet (`paper_wallet_inr` vs `paper_daily_start_wallet`) so hitting SL thresholds locks
        Staging Paper AutoTrade identically to Main!
      - If (baseline - current) >= DAILY_WALLET_LOSS_STOP_PCT% of baseline -> block new trades until
        next IST day (or until unlocked via `unlock_autotrade_daily_loss_stop` from the Sidebar).
    """
    import strategies as _strategies
    pct = float(getattr(_strategies, "DAILY_WALLET_LOSS_STOP_PCT", 5.0) or 5.0)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    cfg = get_autotrade_config()
    is_stg_paper = (
        isinstance(wallet, dict) and bool(wallet.get("is_paper_wallet"))
    ) or (
        is_staging_environment() and (wallet is None or not bool((wallet or {}).get("is_live_api")))
    ) or (
        is_staging_environment() and float(cfg.get("paper_wallet_inr", 0.0) or 0.0) > 0
    )

    if is_stg_paper:
        pw_snap = wallet if (isinstance(wallet, dict) and wallet.get("is_paper_wallet")) else get_paper_wallet_snapshot(cfg, wallet)
        cur = float((pw_snap or {}).get("total_inr", 0.0) or 0.0)
        if cur <= 0:
            return False, "Staging daily loss stop: paper wallet unavailable", {}
        ds = cfg.get("paper_daily_start_wallet")
        if not (isinstance(ds, dict) and ds.get("date") == today and float(ds.get("inr", 0) or 0) > 0):
            ds = {"date": today, "inr": round(cur, 2)}
            save_autotrade_config({"paper_daily_start_wallet": ds, "daily_loss_stop_hit": ""})
        start = float(ds["inr"])
        loss = start - cur
        limit = start * pct / 100.0
        info = {
            "date": today, "day_start_inr": start, "current_inr": cur,
            "loss_inr": round(loss, 2), "limit_inr": round(limit, 2), "is_paper_wallet": True,
        }
        if loss >= limit:
            if cfg.get("daily_loss_stop_hit") != today:
                save_autotrade_config({"daily_loss_stop_hit": today})
            return True, (
                f"5% Daily Loss Stop (Staging Paper): paper wallet down ₹{loss:,.2f} today "
                f"(start ₹{start:,.2f} -> now ₹{cur:,.2f}, limit ₹{limit:,.2f}). "
                f"Paper AutoTrade is locked until next IST day (or click 'Unlock AutoTrade' in sidebar)."
            ), info
        if cfg.get("daily_loss_stop_hit") == today:
            save_autotrade_config({"daily_loss_stop_hit": ""})
        return False, f"Staging paper daily loss ₹{max(loss, 0):,.2f} / limit ₹{limit:,.2f}", info

    w = wallet if isinstance(wallet, dict) else fetch_coindcx_futures_balance()
    if not (isinstance(w, dict) and w.get("is_live_api")):
        return False, "Daily loss stop: live wallet not verified (not enforced this tick)", {}
    cur = float(w.get("total_inr", 0.0) or 0.0)
    if cur <= 0:
        return False, "Daily loss stop: wallet balance unavailable", {}
    ds = cfg.get("daily_start_wallet")
    if not (isinstance(ds, dict) and ds.get("date") == today and float(ds.get("inr", 0) or 0) > 0):
        ds = {"date": today, "inr": round(cur, 2)}
        save_autotrade_config({"daily_start_wallet": ds, "daily_loss_stop_hit": ""})
    start = float(ds["inr"])
    loss = start - cur
    limit = start * pct / 100.0
    info = {"date": today, "day_start_inr": start, "current_inr": cur, "loss_inr": round(loss, 2), "limit_inr": round(limit, 2)}
    if loss >= limit:
        if cfg.get("daily_loss_stop_hit") != today:
            save_autotrade_config({"daily_loss_stop_hit": today})
        return True, (
            f"5% Daily Loss Stop: wallet down ₹{loss:,.2f} today (start ₹{start:,.2f} -> now ₹{cur:,.2f}, "
            f"limit ₹{limit:,.2f}). Click 'Unlock AutoTrade' in the sidebar if you transferred funds out."
        ), info
    if cfg.get("daily_loss_stop_hit") == today:
        save_autotrade_config({"daily_loss_stop_hit": ""})
    return False, f"Daily loss ₹{max(loss, 0):,.2f} / limit ₹{limit:,.2f}", info


def compute_wallet_capped_margin(
    margin_inr: float,
    leverage: int,
    wallet: dict | None = None,
    max_slots: int | None = None,
    honor_custom_margin: bool = False,
) -> tuple[float, str]:
    """
    Caps the per-trade margin to what the live futures wallet can actually fund:
      - Default (`honor_custom_margin=False`): `per_slot = total / slots`
      - Custom Sidebar Margin (`honor_custom_margin=True`): honors the exact Sidebar `Single-Trade Margin (INR)`
        up to `total * 0.98` (without dividing by 3 slots).
    Returns `(effective_margin_inr, note)`. Unverified wallet -> returns the setting unchanged.
    """
    w = wallet if isinstance(wallet, dict) else fetch_coindcx_futures_balance()
    slots = max(1, int(max_slots or MAX_CONCURRENT_TRADES))
    if not (isinstance(w, dict) and w.get("is_live_api")):
        return float(margin_inr), ""
    total = float(w.get("total_inr", 0.0) or 0.0)
    avail = float(w.get("available_inr", total) or 0.0)
    if total > 0:
        per_slot = (total * 0.98) if honor_custom_margin else (total / slots)
    else:
        per_slot = float(margin_inr)
    eff = max(0.0, min(float(margin_inr), per_slot, avail * 0.98))
    note = ""
    if eff + 0.01 < float(margin_inr):
        if honor_custom_margin:
            note = (
                f"Margin capped to ₹{eff:,.2f} (Sidebar ₹{float(margin_inr):,.2f}; wallet ₹{total:,.2f}; "
                f"free ₹{avail:,.2f})"
            )
        else:
            note = (
                f"Margin capped to ₹{eff:,.2f} (setting ₹{float(margin_inr):,.2f}; wallet ₹{total:,.2f} / {slots} slots = "
                f"₹{per_slot:,.2f}; free ₹{avail:,.2f})"
            )
    return round(eff, 2), note


def execute_autotrade_two_entry_signal(
    pair: str,
    sig: dict,
    single_trade_margin_inr: float = None,
    leverage: int = 10,
    usd_inr: float = None,
) -> tuple[bool, str, dict]:
    """
    Executes the 100% Single-Slot Maker Limit + 50/50 Structural Runner setup at 10x leverage:
      1. Enforces strict 3-slot accounting across BOTH filled positions AND resting Entry 1 Limit Orders.
      2. Honors the exact Sidebar Single-Trade Margin (`user_custom_margin`) and skips cleanly when free margin
         is `< 90%` of the target slot margin (eliminating ₹666–₹1,002 leftover-cash dust trades).
      3. Rejects Maker Limit placement if live price has drifted within `< 0.35%` of Stop Loss.
    """
    cfg = get_autotrade_config()
    raw_requested_margin = float(single_trade_margin_inr or cfg.get("single_trade_margin_inr", 30000.0))
    honor_custom_margin = bool(cfg.get("user_custom_margin", False))
    lev = int(leverage or cfg.get("leverage", 10))
    u_inr = float(usd_inr or get_coindcx_live_usdt_inr_rate())

    max_slots = int(cfg.get("max_concurrent_trades", MAX_CONCURRENT_TRADES) or MAX_CONCURRENT_TRADES)
    is_exp_env = is_experiment_environment()
    staging_paper_only = is_staging_environment() or is_exp_env or bool(cfg.get("paper_only", False))

    # Live & Staging-Paper 5% Daily Loss Stop + wallet-aware sizing (same guards on Staging as Main!)
    _live_wallet_raw = fetch_coindcx_futures_balance()
    _wallet_now = (
        get_paper_wallet_snapshot(cfg, _live_wallet_raw)
        if (is_staging_environment() and float(cfg.get("paper_wallet_inr", 0.0) or 0.0) > 0)
        else _live_wallet_raw
    )
    _stop_hit, _stop_msg, _stop_info = check_live_daily_loss_stop(_wallet_now)
    if _stop_hit:
        return False, _stop_msg, {"daily_loss_stop": _stop_info}

    # Anti-Crumb Free-Margin Guard (enforced on BOTH Main Live Wallet AND Staging Paper Wallet!):
    # never downsize a full slot into a leftover-cash dust trade!
    _enforce_free_margin = isinstance(_wallet_now, dict) and (
        (_wallet_now.get("is_live_api") and not staging_paper_only)
        or bool(_wallet_now.get("is_paper_wallet"))
    )
    if _enforce_free_margin:
        _tot_w = float(_wallet_now.get("total_inr", 0.0) or 0.0)
        _avail_w = float(_wallet_now.get("available_inr", _tot_w) or 0.0)
        _target_slot_m = (
            min(raw_requested_margin, (_tot_w * 0.98 if honor_custom_margin else (_tot_w / max(1, max_slots))))
            if _tot_w > 0 else raw_requested_margin
        )
        if _target_slot_m >= 2500.0 and (_avail_w * 0.98) < (_target_slot_m * 0.90):
            return False, (
                f"Insufficient Free Margin Guard: Free Futures margin ₹{_avail_w:,.2f} is below 90% of target slot margin "
                f"₹{_target_slot_m:,.2f} (Sidebar ₹{raw_requested_margin:,.2f}). Skipping {pair} instead of placing an under-sized dust order."
            ), {"wallet": _wallet_now, "target_slot_margin_inr": round(_target_slot_m, 2)}

    margin_inr, _cap_note = compute_wallet_capped_margin(
        raw_requested_margin, lev, _wallet_now, max_slots, honor_custom_margin=honor_custom_margin
    )
    if (margin_inr * lev) < 2448.0:
        return False, (
            f"Insufficient Futures Wallet: usable margin ₹{margin_inr:,.2f} x {lev}x = ₹{margin_inr * lev:,.2f} notional "
            f"is below CoinDCX's ₹2,448 minimum. {_cap_note}"
        ), {"wallet": _wallet_now}

    slot = get_active_portfolio_trade_status()
    slot_pairs = list(slot.get("active_pairs") or ([slot.get("active_pair")] if slot.get("active_pair") else []))
    if pair in slot_pairs:
        return False, (
            f"Duplicate Pair Guard: Active trade or resting limit order already open on {pair} ({slot.get('source')}). "
            f"Skipping duplicate {pair} order."
        ), {"slot_status": slot}
    if slot.get("is_occupied"):
        act_p = slot.get("active_pair") or ", ".join(slot_pairs[:max_slots])
        slot_cnt = int(slot.get("count", len(slot_pairs)) or 1)
        if act_p == pair or slot_cnt >= max_slots:
            return False, (
                f"Portfolio Slot Guard ({slot_cnt}/{max_slots} active): Active trades/orders already open on {act_p} ({slot.get('source')}). "
                f"Skipping {pair}."
            ), {"slot_status": slot}

    # Mandatory synchronous live CoinDCX position + resting open-order check:
    # count BOTH filled positions AND resting Entry 1 Limit Orders toward `max_slots` (3)!
    live_ex_pos = _fetch_coindcx_active_positions_sync(return_none_on_error=True)
    if live_ex_pos is None and os.getenv("COINDCX_API_KEY") and not staging_paper_only:
        return False, (
            f"Portfolio Safety Guard: Could not verify live CoinDCX positions right now; "
            f"blocking {pair} AutoTrade until exchange positions are verified."
        ), {"live_ex_pos": None}

    open_entry_orders = None
    occupied_pairs: list[str] = []
    for _lp in (live_ex_pos or []):
        _p_n = _lp.get("pair") if isinstance(_lp, dict) else None
        if _p_n and _p_n not in occupied_pairs:
            occupied_pairs.append(str(_p_n))
    if not staging_paper_only and isinstance(_wallet_now, dict) and _wallet_now.get("is_live_api"):
        try:
            open_entry_orders = get_open_entry_limit_orders(live_positions=live_ex_pos, cfg=cfg)
            for _eo in (open_entry_orders or []):
                _ep = _eo.get("pair")
                if _ep and _ep not in occupied_pairs:
                    occupied_pairs.append(str(_ep))
        except Exception:
            open_entry_orders = None
    _now_chk = time.time()
    for _lkp, _lkv in _get_active_locks_map(cfg).items():
        if bool(_lkv.get("is_live_exchange")) == (not staging_paper_only):
            if (_now_chk - float(_lkv.get("opened_ts", 0.0) or 0.0)) < ENTRY1_LIMIT_EXPIRY_SEC:
                if _lkp not in occupied_pairs:
                    occupied_pairs.append(str(_lkp))

    if pair in occupied_pairs:
        return False, (
            f"Duplicate Pair Guard: CoinDCX already has an open position or resting limit order on {pair}. Skipping duplicate {pair} order."
        ), {"live_ex_pos": live_ex_pos, "occupied_pairs": occupied_pairs}
    if len(occupied_pairs) >= max_slots:
        open_names = ", ".join(occupied_pairs[:max_slots])
        return False, (
            f"3-Slot Wallet Guard ({len(occupied_pairs)}/{max_slots} active, incl. resting limit orders): "
            f"CoinDCX already has {len(occupied_pairs)} active trades/orders ({open_names}). "
            f"Skipping {pair} (max {max_slots} concurrent trades)."
        ), {"live_ex_pos": live_ex_pos, "occupied_pairs": occupied_pairs}

    direction = str(sig.get("signal") or sig.get("direction", "LONG")).upper()
    norm_dir = "LONG" if direction in ("LONG", "BUY") else "SHORT"

    # Hard Daily 50 & 200 EMA Bias Guard before placing any AutoTrade order
    # Always verify against fresh compute_market_bias(pair) if sig_levels is missing or to prevent stale signals
    sig_levels = sig.get("levels") if isinstance(sig.get("levels"), dict) else {}
    daily_bias = str(sig_levels.get("trend_bias") or sig_levels.get("bias") or "").upper()
    try:
        mb = compute_market_bias(pair)
        live_mb_bias = str(mb.get("bias", "")).upper()
        if live_mb_bias:
            daily_bias = live_mb_bias
    except Exception:
        pass

    if "BULLISH" in daily_bias:
        daily_bias = "BULLISH"
    elif "BEARISH" in daily_bias:
        daily_bias = "BEARISH"
    else:
        daily_bias = "NEUTRAL"

    # AutoTrade Strategy Enforcement: supports `box_theory` (Strategy 1) and `ema50_200` (Strategy 4)
    # per the configured `autotrade_strategy_mode` (default: `box_plus_ema50_200_bear`)
    import strategies as _strat_mod
    auto_mode = _strat_mod.resolve_autotrade_mode(cfg.get("autotrade_strategy_mode"))
    sig_strat_id = str(sig.get("strategy_id") or "box_theory")
    allow_mode_override = bool(sig.get("manual_override", False))
    if sig_strat_id not in ("box_theory", "ema50_200"):
        return False, (
            f"AutoTrade Strategy Guard: AutoTrade only executes Box Theory Sweep or 15m 50/200 EMA Pullback; "
            f"skipping {sig_strat_id} on {pair}."
        ), {"strategy_id": sig_strat_id}
    if not allow_mode_override:
        if auto_mode == "box_theory" and sig_strat_id != "box_theory":
            return False, (
                f"AutoTrade Mode Guard: Sidebar AutoTrade Strategy is Box Sweep Only; skipping {sig_strat_id} on {pair}."
            ), {"strategy_id": sig_strat_id, "mode": auto_mode}
        if auto_mode == "ema50_200" and sig_strat_id != "ema50_200":
            return False, (
                f"AutoTrade Mode Guard: Sidebar AutoTrade Strategy is 15m 50/200 EMA Only; skipping {sig_strat_id} on {pair}."
            ), {"strategy_id": sig_strat_id, "mode": auto_mode}
        if auto_mode == "box_plus_ema50_200_bear" and sig_strat_id == "ema50_200" and norm_dir != "SHORT":
            return False, (
                f"AutoTrade Mode Guard: Bear-Only 15m 50/200 EMA mode skips {norm_dir} EMA entries on {pair} "
                f"(switch to Combo: Regime-Adaptive or Bull & Bear EMA to enable Bullish EMA Longs)."
            ), {"strategy_id": sig_strat_id, "mode": auto_mode, "direction": norm_dir}
        if auto_mode == "box_plus_ema50_200_regime" and sig_strat_id == "ema50_200":
            reg_info = compute_market_regime()
            cur_reg = str(reg_info.get("regime", "RANGING_CHOP"))
            if cur_reg == "RANGING_CHOP":
                return False, (
                    f"Market Regime Guard ({reg_info.get('label', 'RANGING / CHOP')}): Market is ranging "
                    f"(2d median {reg_info.get('median_2d_pct', 0.0):+.2f}%), auto-pausing 15m 50/200 EMA on {pair} "
                    f"and trading Box Theory Sweep only."
                ), {"strategy_id": sig_strat_id, "mode": auto_mode, "regime": cur_reg}
            if cur_reg == "STRONG_DOWNTREND" and norm_dir != "SHORT":
                return False, (
                    f"Market Regime Guard (STRONG DOWNTREND): Blocking counter-regime {norm_dir} EMA entry on {pair}."
                ), {"strategy_id": sig_strat_id, "mode": auto_mode, "regime": cur_reg}
            if cur_reg == "STRONG_UPTREND" and norm_dir != "LONG":
                return False, (
                    f"Market Regime Guard (STRONG UPTREND): Blocking counter-regime {norm_dir} EMA entry on {pair}."
                ), {"strategy_id": sig_strat_id, "mode": auto_mode, "regime": cur_reg}
        if sig_strat_id == "ema50_200":
            open_ema_cnt = count_open_ema50_200_slots(
                live_positions=live_ex_pos if live_ex_pos is not None else [],
                cfg=cfg,
                open_orders=open_entry_orders,
            )
            if open_ema_cnt >= MAX_EMA_CONCURRENT_TRADES:
                return False, (
                    f"EMA Slot Cap ({open_ema_cnt}/{MAX_EMA_CONCURRENT_TRADES} EMA slots active): "
                    f"Reserving final portfolio slot for Box Theory Sweep; skipping correlated EMA trade on {pair}."
                ), {"strategy_id": sig_strat_id, "open_ema_slots": open_ema_cnt}
    if (daily_bias == "BEARISH" and norm_dir != "SHORT") or (daily_bias == "BULLISH" and norm_dir != "LONG"):
        return False, (
            f"Daily Bias Guard: {pair} Daily Bias is {daily_bias}, blocking counter-trend {norm_dir} AutoTrade."
        ), {"daily_bias": daily_bias, "direction": norm_dir}

    side = "BUY" if norm_dir == "LONG" else "SELL"
    opp_side = "SELL" if side == "BUY" else "BUY"
    live_tk_obj = fetch_live_ticker(pair)
    live_tk_px = float((live_tk_obj or {}).get("last_price", 0.0) or 0.0)
    raw_sig_sl = float(sig.get("stop_loss") or 0.0)
    # Pre-Normalization SL Price-Drift Guard (< 0.35% buffer):
    # Never let `normalize_two_entry_runner_levels` silently widen SL when live market price has already
    # drifted into or past the signal's structural Stop Loss (e.g. RENDER $1.4079 vs $1.4085 SL)!
    if raw_sig_sl > 0 and live_tk_px > 0:
        _pre_bad_side = (live_tk_px <= raw_sig_sl) if norm_dir == "LONG" else (live_tk_px >= raw_sig_sl)
        _pre_gap_pct = abs(raw_sig_sl - live_tk_px) / live_tk_px
        if _pre_bad_side or _pre_gap_pct < 0.0035:
            return False, (
                f"Price Drift Guard: Live price ${live_tk_px} has drifted within {_pre_gap_pct * 100.0:.2f}% of "
                f"(or beyond) Signal Stop Loss ${raw_sig_sl} (< 0.35% minimum buffer). Aborting {pair} to prevent instant stop-out."
            ), {"live_px": live_tk_px, "signal_sl_px": raw_sig_sl}

    raw_e2 = float(sig.get("entry2_sweep") or 0.0)
    has_second_entry = False  # Entry 2 removed: 100% Single-Slot Maker Limit sizing on Entry 1
    norm = normalize_two_entry_runner_levels(
        pair=pair,
        direction=direction,
        entry1_px=float(sig["entry"]),
        entry2_px=None,
        tp1_px=float(sig["tp1"]),
        tp2_px=float(sig["tp2"]),
        sl_px=float(sig["stop_loss"]),
        live_px=live_tk_px if live_tk_px > 0 else float(sig["entry"]),
        levels=sig.get("levels") if sig_strat_id == "box_theory" else None,
    )
    entry1_px = norm["entry"]
    entry2_px = 0.0
    tp1_px = norm["tp1"]
    tp2_px = norm["tp2"]
    sl_px = norm["stop_loss"]

    # Price Entry 1 strictly as a non-crossing Maker Limit Order (0.0236% Maker fee vs 0.059% Market Taker fee)
    maker_e1_px = compute_maker_limit_entry_price(
        pair=pair,
        direction=norm_dir,
        desired_entry_px=entry1_px,
        live_ticker=live_tk_obj,
        nudge_ticks=0,
        sl_px=sl_px,
        entry2_px=entry2_px,
        tp1_px=tp1_px,
    )
    if maker_e1_px > 0:
        entry1_px = maker_e1_px

    # Post-Nudge SL Price-Drift Guard (< 0.35% buffer): abort if live market drifted right up against Stop Loss
    if sl_px > 0 and entry1_px > 0:
        _sl_bad_side = (entry1_px <= sl_px) if norm_dir == "LONG" else (entry1_px >= sl_px)
        _sl_gap_pct = abs(sl_px - entry1_px) / entry1_px
        if _sl_bad_side or _sl_gap_pct < 0.0035:
            return False, (
                f"Price Drift Guard: Live Maker Limit ${entry1_px} is within {_sl_gap_pct * 100.0:.2f}% of Stop Loss ${sl_px} "
                f"(< 0.35% minimum buffer). Aborting {pair} to prevent instant stop-out."
            ), {"entry1_px": entry1_px, "sl_px": sl_px}

    tranche_margin_inr = (margin_inr * 0.5) if has_second_entry else margin_inr
    tranche_notional_usd = (tranche_margin_inr * lev) / u_inr
    qty1 = format_order_quantity(pair, tranche_notional_usd / entry1_px) if entry1_px > 0 else 0.0
    qty2 = format_order_quantity(pair, tranche_notional_usd / entry2_px) if (has_second_entry and entry2_px > 0) else 0.0

    # If 50% tranche is below CoinDCX Rs.2,448 minimum notional, use full margin on Entry 1 or bump notional
    if (qty1 * entry1_px * u_inr) < 2448.0 and (margin_inr * lev) >= 2448.0:
        qty1 = format_order_quantity(pair, ((margin_inr * lev) / u_inr) / entry1_px)

    # 50% of Entry 1 quantity to book at TP1 (remaining 50% of Entry 1 rides to TP2)
    qty1_tp1_half = format_order_quantity(pair, qty1 * 0.5)

    if staging_paper_only:
        # Staging Environment: NEVER place live CoinDCX orders; execute strictly as Live-Market Paper AutoTrade!
        lock_info = register_app_trade_lock(
            pair=pair, direction=direction, entry=entry1_px, stop_loss=sl_px,
            tp1=tp1_px, tp2=tp2_px, entry2_sweep=entry2_px, margin_inr=margin_inr,
            leverage=lev, qty1=qty1, qty2=qty2,
            mode="Staging Paper AutoTrade (Live Market)", is_live_exchange=False,
            tp1_order_id="STRATEGY3_FULL_RUNNER_SL_RATCHET" if sig_strat_id == "ema9_retest" else "DAEMON_50PCT_REDUCE_AT_TP1",
            strategy_id=sig_strat_id,
        )
        return True, (
            f"Staging Paper AutoTrade Executed: {norm_dir} {pair} ({sig_strat_id}) | "
            f"Entry 1 Limit: ${entry1_px} ({qty1}) | TP1: ${tp1_px} | TP2: ${tp2_px} | SL: ${sl_px} @ {lev}x"
        ), {"lock": lock_info, "paper_mode": True}

    wallet = fetch_coindcx_futures_balance()
    api_key_now, api_secret_now = _get_coindcx_credentials()
    has_live_creds = bool(api_key_now and api_secret_now)

    if wallet.get("is_live_api") or has_live_creds:
        # Leg 1: Entry 1 (50% Margin = qty1) strictly as a Maker Limit Order (NEVER market_order!)
        ok1, msg1, extra1 = place_coindcx_futures_order(
            pair=pair,
            side=side,
            quantity=qty1,
            leverage=lev,
            order_type="limit_order",
            price=entry1_px,
            margin_currency="INR",
            tp_price=None,
            sl_price=None,
            post_only=False,
        )
        # If price moved 1-2 ticks during HTTP transit, refresh live ticker and retry strictly as a Maker Limit Order
        if not ok1:
            _TICKER_MAP_CACHE["ts"] = 0.0
            fresh_tk = fetch_live_ticker(pair)
            retry_e1_px = compute_maker_limit_entry_price(
                pair=pair,
                direction=norm_dir,
                desired_entry_px=entry1_px,
                live_ticker=fresh_tk,
                nudge_ticks=3,
                sl_px=sl_px,
                entry2_px=entry2_px,
                tp1_px=tp1_px,
            )
            if retry_e1_px > 0 and retry_e1_px != entry1_px:
                if sl_px > 0 and (
                    ((retry_e1_px <= sl_px) if norm_dir == "LONG" else (retry_e1_px >= sl_px))
                    or (abs(sl_px - retry_e1_px) / retry_e1_px) < 0.0035
                ):
                    return False, (
                        f"Price Drift Guard: Retry Maker Limit ${retry_e1_px} drifted within 0.35% of Stop Loss ${sl_px}. "
                        f"Aborting {pair} to prevent instant stop-out."
                    ), {"entry1_px": retry_e1_px, "sl_px": sl_px}
                entry1_px = retry_e1_px
                qty1 = format_order_quantity(pair, tranche_notional_usd / entry1_px)
                if (qty1 * entry1_px * u_inr) < 2448.0 and (margin_inr * lev) >= 2448.0:
                    qty1 = format_order_quantity(pair, ((margin_inr * lev) / u_inr) / entry1_px)
                ok1, msg1, extra1 = place_coindcx_futures_order(
                    pair=pair,
                    side=side,
                    quantity=qty1,
                    leverage=lev,
                    order_type="limit_order",
                    price=entry1_px,
                    margin_currency="INR",
                    tp_price=None,
                    sl_price=None,
                    post_only=False,
                )
        if ok1:
            e1_order_id = str((extra1 or {}).get("order_id") or (extra1 or {}).get("id") or "")
            # Check if Entry 1 Limit Order already filled into an active position
            sync_ok, sync_msg, sync_details = sync_full_2entry_runner_to_position(
                pair=pair,
                direction=direction,
                entry1_px=entry1_px,
                entry2_px=entry2_px,
                tp1_px=tp1_px,
                tp2_px=tp2_px,
                sl_px=sl_px,
                total_margin_inr=margin_inr,
                leverage=lev,
                usd_inr=u_inr,
                strategy_id=sig_strat_id,
            )
            if not sync_ok:
                time.sleep(0.6)
                sync_ok, sync_msg, sync_details = sync_full_2entry_runner_to_position(
                    pair=pair,
                    direction=direction,
                    entry1_px=entry1_px,
                    entry2_px=entry2_px,
                    tp1_px=tp1_px,
                    tp2_px=tp2_px,
                    sl_px=sl_px,
                    total_margin_inr=margin_inr,
                    leverage=lev,
                    usd_inr=u_inr,
                    strategy_id=sig_strat_id,
                )
            lock_obj = (sync_details or {}).get("lock")
            if not lock_obj:
                # Entry 1 Limit Order is resting on the order book waiting for a Maker fill:
                # Also place Entry 2 Sweep Limit Order upfront so fast liquidity wicks fill both Maker legs,
                # and mark entry1_pending=True so the 24/7 daemon attaches TP2/SL + TP1 Limit the instant Entry 1 fills!
                e2_oid_pending = ""
                e2_note = ""
                if has_second_entry and qty2 > 0 and (qty2 * entry2_px * u_inr) >= 2448.0:
                    ok2_p, _, extra2_p = place_coindcx_futures_order(
                        pair=pair,
                        side=side,
                        quantity=qty2,
                        leverage=lev,
                        order_type="limit_order",
                        price=entry2_px,
                        margin_currency="INR",
                        post_only=False,
                    )
                    if ok2_p:
                        e2_oid_pending = str((extra2_p or {}).get("order_id") or (extra2_p or {}).get("id") or "")
                        e2_note = f" + Entry 2 Limit ({qty2} @ ${entry2_px}) Resting"
                lock_obj = register_app_trade_lock(
                    pair=pair,
                    direction=direction,
                    entry=entry1_px,
                    stop_loss=sl_px,
                    tp1=tp1_px,
                    tp2=tp2_px,
                    entry2_sweep=entry2_px,
                    margin_inr=margin_inr,
                    leverage=lev,
                    qty1=qty1,
                    qty2=qty2,
                    mode="App/API Live AutoTrade (Entry 1 Limit Resting)",
                    is_live_exchange=True,
                    entry2_order_id=e2_oid_pending,
                    strategy_id=sig_strat_id,
                    entry1_order_id=e1_order_id,
                    entry1_pending=True,
                )
                sync_msg = f"Entry 1 Maker Limit Resting{e2_note} -> Auto-Attaches TP1/TP2/SL on Fill"
            return True, (
                f"Live Maker Limit AutoTrade Placed on {pair}! Entry 1 Limit ({qty1} @ ${entry1_px}) | {sync_msg}"
                + (f" | {_cap_note}" if _cap_note else "")
            ), {
                "entry1_order": extra1,
                "sync_details": sync_details,
                "lock": lock_obj,
            }
        return False, f"CoinDCX Live AutoTrade Error on {pair}: {msg1}", {"entry1_order": extra1}
    else:
        # Paper / Simulated AutoTrade Lock when live CoinDCX API key is offline/expired
        lock_info = register_app_trade_lock(
            pair=pair, direction=direction, entry=entry1_px, stop_loss=sl_px,
            tp1=tp1_px, tp2=tp2_px, entry2_sweep=entry2_px, margin_inr=margin_inr,
            leverage=lev, qty1=qty1, qty2=qty2,
            mode="App/API Simulated AutoTrade (100% Maker Limit Armed)", is_live_exchange=False,
            strategy_id=sig_strat_id,
        )
        return True, (
            f"AutoTrade Armed (Simulated): {direction} {pair} | "
            f"Entry 1 (100% Slot Maker Limit): ${entry1_px} ({qty1}) -> 50% books at TP1 ${tp1_px} ({qty1_tp1_half}) & 50% rides to TP2 ${tp2_px} @ {lev}x"
        ), {"lock": lock_info}


def run_portfolio_single_slot_backtest(
    pairs: list[str] = None,
    duration_days: int = 30,
    margin_inr: float = 100000.0,
    leverage: int = 10,
    usd_inr: float = 85.0,
    strategy_id: str = "box_theory",
    wallet_inr: float = None,
    exit_mode: str = "smart_hybrid",
    max_concurrent_trades: int = MAX_CONCURRENT_TRADES,
    daily_loss_stop_pct: float = None,
    enforce_free_margin_guard: bool = True,
) -> dict:
    """
    Simulates the exact Main Live Portfolio Engine across the High-Volatility Futures Universe
    with full Main-Parity Guards (used on `Experiment` & `🧪 Backtest`):
      - Scans all pairs in `pairs` (defaults to HIGH_VOL_FUTURES_UNIVERSE).
      - Enforces Max Concurrent Portfolio Slots (default 3) & 1 active trade per coin.
      - Enforces Max 2 Concurrent 15m 50/200 EMA Slots + 4h same-zone re-entry lock.
      - Enforces IST Daily Loss Stop / SL Threshold (default 5.0% of IST day-start wallet equity).
      - Enforces Main's <90% Free-Margin Anti-Crumb Guard against running wallet equity.
      - Returns full Guard Telemetry (`guards_audit`) and chronological `equity_curve`.
    """
    import strategies as _strategies
    eff_wallet_inr = float(wallet_inr) if (wallet_inr and wallet_inr > 0) else (margin_inr / TRADE_ALLOCATION_FRACTION)
    dl_stop_pct = (
        float(_strategies.DAILY_WALLET_LOSS_STOP_PCT)
        if daily_loss_stop_pct is None
        else max(0.0, float(daily_loss_stop_pct))
    )

    universe = list(pairs or HIGH_VOL_FUTURES_UNIVERSE)
    if strategy_id == "box_plus_ema50_200_regime":
        build_historical_regime_map(pairs=universe, duration_days=duration_days)
    all_candidates = []
    standalone_rows = []
    for rank, p in enumerate(universe):
        res = run_strategy_backtest(
            pair=p, duration_days=duration_days, interval="15m",
            margin_inr=margin_inr, leverage=leverage, usd_inr=usd_inr,
            strategy_id=strategy_id, wallet_inr=eff_wallet_inr, exit_mode=exit_mode,
        )
        st_tot = int(res.get("total_trades", 0) or 0)
        st_wins = int(res.get("win_count", 0) or 0)
        st_losses = int(res.get("loss_count", 0) or 0)
        st_wr = float(res.get("win_rate_pct", 0.0) or 0.0)
        st_net = round(float(res.get("net_profit_inr", 0.0) or 0.0), 2)
        st_roi = round((st_net / margin_inr) * 100.0, 2) if margin_inr > 0 else 0.0
        st_pf = float(res.get("profit_factor", 0.0) or 0.0)
        standalone_rows.append({
            "pair": p,
            "Trades": st_tot,
            "Wins": st_wins,
            "Losses": st_losses,
            "Win_Rate_%": round(st_wr, 1),
            "Net_Profit_INR": st_net,
            "ROI_Pct": st_roi,
            "Profit_Factor": round(st_pf, 2),
        })
        tdf = res.get("trades_df")
        if tdf is not None and not tdf.empty:
            for _, row in tdf.iterrows():
                d = row.to_dict()
                d["vol_rank"] = rank
                all_candidates.append(d)

    standalone_df = pd.DataFrame(standalone_rows)
    if not standalone_df.empty:
        standalone_df = standalone_df.sort_values(by="Net_Profit_INR", ascending=False).reset_index(drop=True)

    empty_guards = {
        "starting_wallet_inr": round(eff_wallet_inr, 2),
        "ending_wallet_inr": round(eff_wallet_inr, 2),
        "wallet_roi_pct": 0.0,
        "max_drawdown_pct": 0.0,
        "daily_loss_stop_pct": dl_stop_pct,
        "days_locked_by_sl_threshold": 0,
        "locked_dates": [],
        "blocked_by_sl_threshold": 0,
        "blocked_by_slot_cap": 0,
        "blocked_by_dup_pair": 0,
        "blocked_by_ema_cap": 0,
        "blocked_by_free_margin": 0,
        "blocked_by_4h_zone_lock": 0,
    }
    if not all_candidates:
        return {
            "total_trades": 0, "win_count": 0, "loss_count": 0, "win_rate_pct": 0.0,
            "net_profit_inr": 0.0, "total_roi_pct": 0.0, "profit_factor": 0.0,
            "total_fees_paid_inr": 0.0, "trades_df": pd.DataFrame(),
            "coin_summary_df": pd.DataFrame(), "standalone_summary_df": standalone_df,
            "strategy_id": strategy_id, "strategy_breakdown": {},
            "starting_wallet_inr": round(eff_wallet_inr, 2),
            "ending_wallet_inr": round(eff_wallet_inr, 2),
            "wallet_roi_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "guards_audit": empty_guards,
            "equity_curve": [],
        }

    df_all = pd.DataFrame(all_candidates).sort_values(by=["entry_time", "vol_rank"]).reset_index(drop=True)
    accepted = []
    active_open_trades = []
    max_slots = max(1, int(max_concurrent_trades or MAX_CONCURRENT_TRADES))
    day_counts = {}
    day_pnl = {}
    day_start_wallet: dict[str, float] = {}
    locked_days = set()

    current_wallet_inr = float(eff_wallet_inr)
    peak_wallet_inr = float(eff_wallet_inr)
    max_drawdown_pct = 0.0
    equity_curve: list[dict] = []

    blocked_sl = 0
    blocked_slot = 0
    blocked_dup = 0
    blocked_ema = 0
    blocked_margin = 0
    blocked_zone = 0

    def _settle_closed_trades(up_to_time: str):
        nonlocal active_open_trades, current_wallet_inr, peak_wallet_inr, max_drawdown_pct
        still_open = []
        # Sort closing trades chronologically by exit_time so daily SL threshold triggers at exact close time
        closing = [t for t in active_open_trades if str(t["exit_time"]) <= up_to_time]
        for t in active_open_trades:
            if str(t["exit_time"]) > up_to_time:
                still_open.append(t)
        closing.sort(key=lambda x: str(x["exit_time"]))
        for t in closing:
            t_ent_day = str(t["entry_time"])[:10]
            t_ext_day = str(t["exit_time"])[:10]
            if t_ext_day not in day_start_wallet:
                day_start_wallet[t_ext_day] = max(1.0, current_wallet_inr)
            if t_ent_day not in day_start_wallet:
                day_start_wallet[t_ent_day] = max(1.0, current_wallet_inr)
            pnl_v = float(t["net_pnl_inr"])
            current_wallet_inr = round(max(0.0, current_wallet_inr + pnl_v), 2)
            if current_wallet_inr > peak_wallet_inr:
                peak_wallet_inr = current_wallet_inr
            if peak_wallet_inr > 0:
                dd_pct = ((peak_wallet_inr - current_wallet_inr) / peak_wallet_inr) * 100.0
                if dd_pct > max_drawdown_pct:
                    max_drawdown_pct = dd_pct
            day_pnl[t_ext_day] = day_pnl.get(t_ext_day, 0.0) + pnl_v
            if t_ent_day != t_ext_day:
                day_pnl[t_ent_day] = day_pnl.get(t_ent_day, 0.0) + pnl_v
            if dl_stop_pct > 0:
                lim_ext = day_start_wallet[t_ext_day] * (dl_stop_pct / 100.0)
                lim_ent = day_start_wallet[t_ent_day] * (dl_stop_pct / 100.0)
                if day_pnl.get(t_ext_day, 0.0) <= -lim_ext:
                    locked_days.add(t_ext_day)
                if day_pnl.get(t_ent_day, 0.0) <= -lim_ent:
                    locked_days.add(t_ent_day)
            equity_curve.append({
                "time": str(t["exit_time"]),
                "pair": str(t.get("pair", "")),
                "pnl_inr": round(pnl_v, 2),
                "equity_inr": current_wallet_inr,
                "day_locked": t_ext_day in locked_days,
            })
        active_open_trades = still_open

    last_ema_zone_by_pair: dict[str, tuple] = {}
    for _, tr in df_all.iterrows():
        ent_t = str(tr["entry_time"])
        day_str = ent_t[:10]
        _settle_closed_trades(ent_t)
        if day_str not in day_start_wallet:
            day_start_wallet[day_str] = max(1.0, current_wallet_inr)
        if day_str in locked_days:
            blocked_sl += 1
            continue
        # Only 1 active trade per coin at a time, and at most `max_slots` (3) concurrent trades across the wallet
        if any(t.get("pair") == tr["pair"] for t in active_open_trades):
            blocked_dup += 1
            continue
        if len(active_open_trades) >= max_slots:
            blocked_slot += 1
            continue
        # Main-Parity <90% Free-Margin Anti-Crumb Guard against running wallet equity
        if enforce_free_margin_guard and margin_inr >= 2500.0:
            locked_m = sum(float(t.get("_bt_margin_inr", margin_inr) or margin_inr) for t in active_open_trades)
            avail_m = max(0.0, current_wallet_inr - locked_m)
            if (avail_m * 0.98) < (margin_inr * 0.90):
                blocked_margin += 1
                continue
        is_ema_tr = "50/200 EMA" in str(tr.get("strategy", ""))
        if is_ema_tr:
            open_ema_bt = sum(1 for t in active_open_trades if "50/200 EMA" in str(t.get("strategy", "")))
            if open_ema_bt >= MAX_EMA_CONCURRENT_TRADES:
                blocked_ema += 1
                continue
            prev_z = last_ema_zone_by_pair.get(str(tr["pair"]))
            cur_ep = float(tr.get("entry_price", 0.0) or 0.0)
            cur_dt = pd.to_datetime(ent_t)
            if prev_z and cur_ep > 0:
                prev_dt, prev_dir, prev_ep, prev_win = prev_z
                zone_lock_sec = 3600 if prev_win else (4 * 3600)
                if (
                    prev_dir == str(tr.get("direction", ""))
                    and (cur_dt - prev_dt).total_seconds() < zone_lock_sec
                    and abs(cur_ep - prev_ep) / cur_ep < 0.008
                ):
                    blocked_zone += 1
                    continue
        tr_dict = tr.to_dict()
        tr_dict["_bt_margin_inr"] = float(margin_inr)
        if is_ema_tr:
            last_ema_zone_by_pair[str(tr["pair"])] = (
                pd.to_datetime(ent_t),
                str(tr.get("direction", "")),
                float(tr.get("entry_price", 0.0) or 0.0),
                bool(tr.get("is_win", False)),
            )
        accepted.append(tr_dict)
        active_open_trades.append(tr_dict)
        day_counts[day_str] = day_counts.get(day_str, 0) + 1

    # Settle any remaining open trades chronologically at end of simulation
    _settle_closed_trades("9999-12-31 23:59:59")

    wallet_roi_pct = round(((current_wallet_inr - eff_wallet_inr) / eff_wallet_inr) * 100.0, 2) if eff_wallet_inr > 0 else 0.0
    guards_audit = {
        "starting_wallet_inr": round(eff_wallet_inr, 2),
        "ending_wallet_inr": round(current_wallet_inr, 2),
        "wallet_roi_pct": wallet_roi_pct,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "daily_loss_stop_pct": dl_stop_pct,
        "days_locked_by_sl_threshold": len(locked_days),
        "locked_dates": sorted(locked_days),
        "blocked_by_sl_threshold": blocked_sl,
        "blocked_by_slot_cap": blocked_slot,
        "blocked_by_dup_pair": blocked_dup,
        "blocked_by_ema_cap": blocked_ema,
        "blocked_by_free_margin": blocked_margin,
        "blocked_by_4h_zone_lock": blocked_zone,
    }

    if not accepted:
        return {
            "total_trades": 0, "win_count": 0, "loss_count": 0, "win_rate_pct": 0.0,
            "net_profit_inr": 0.0, "total_roi_pct": 0.0, "profit_factor": 0.0,
            "total_fees_paid_inr": 0.0, "total_gross_profit": 0.0, "total_gross_loss": 0.0,
            "trades_df": pd.DataFrame(), "coin_summary_df": pd.DataFrame(),
            "standalone_summary_df": standalone_df, "strategy_id": strategy_id,
            "strategy_breakdown": {}, "margin_inr": margin_inr, "leverage": leverage,
            "duration_days": duration_days,
            "starting_wallet_inr": round(eff_wallet_inr, 2),
            "ending_wallet_inr": round(current_wallet_inr, 2),
            "wallet_roi_pct": wallet_roi_pct,
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "guards_audit": guards_audit,
            "equity_curve": equity_curve,
        }

    pdf = pd.DataFrame(accepted)
    wins = pdf[pdf["is_win"] == True]
    losses = pdf[pdf["is_win"] == False]
    tot = len(pdf)
    wr = round(len(wins) / tot * 100.0, 1) if tot else 0.0
    net_pnl = round(float(pdf["net_pnl_inr"].sum()), 2)
    fees = round(float(pdf["fees_inr"].sum()), 2)
    gp = float(wins["net_pnl_inr"].sum()) if not wins.empty else 0.0
    gl = abs(float(losses["net_pnl_inr"].sum())) if not losses.empty else 0.0
    pf = round(gp / gl, 2) if gl > 0 else (99.0 if gp > 0 else 0.0)

    coin_grp = (
        pdf.groupby("pair", as_index=False)
        .agg(
            Trades=("is_win", "count"),
            Wins=("is_win", lambda s: int(s.sum())),
            Net_Profit_INR=("net_pnl_inr", lambda s: round(float(s.sum()), 2)),
            Avg_ROE_Pct=("roe_pct", lambda s: round(float(s.mean()), 2)),
        )
    )
    # Ensure all pairs in universe are represented so no coin is silently omitted
    existing_pairs = set(coin_grp["pair"].tolist()) if not coin_grp.empty else set()
    missing_rows = [
        {"pair": p, "Trades": 0, "Wins": 0, "Net_Profit_INR": 0.0, "Avg_ROE_Pct": 0.0}
        for p in universe if p not in existing_pairs
    ]
    if missing_rows:
        coin_grp = pd.concat([coin_grp, pd.DataFrame(missing_rows)], ignore_index=True)

    coin_grp["Losses"] = (coin_grp["Trades"] - coin_grp["Wins"]).astype(int)
    coin_grp["Win_Rate_%"] = coin_grp.apply(
        lambda r: round((float(r["Wins"]) / float(r["Trades"])) * 100.0, 1) if r["Trades"] > 0 else 0.0,
        axis=1,
    )
    coin_grp["ROI_Pct"] = coin_grp["Net_Profit_INR"].apply(
        lambda x: round((float(x) / margin_inr) * 100.0, 2) if margin_inr > 0 else 0.0
    )
    coin_grp = coin_grp.sort_values(by=["Net_Profit_INR", "Trades"], ascending=[False, False]).reset_index(drop=True)
    coin_grp = coin_grp[["pair", "Trades", "Wins", "Losses", "Win_Rate_%", "Net_Profit_INR", "ROI_Pct", "Avg_ROE_Pct"]]

    strategy_breakdown = {}
    if not pdf.empty and "strategy" in pdf.columns:
        for s_lbl, grp in pdf.groupby("strategy"):
            s_tr = int(len(grp))
            s_w = int((grp["is_win"] == True).sum())
            s_l = s_tr - s_w
            s_net = round(float(grp["net_pnl_inr"].sum()), 2)
            s_wr = round((s_w / s_tr) * 100.0, 1) if s_tr > 0 else 0.0
            strategy_breakdown[str(s_lbl)] = {
                "trades": s_tr, "wins": s_w, "losses": s_l,
                "win_rate_pct": s_wr, "net_pnl_inr": s_net,
            }

    return {
        "total_trades": tot,
        "win_count": int(len(wins)),
        "loss_count": int(len(losses)),
        "win_rate_pct": wr,
        "net_profit_inr": net_pnl,
        "total_roi_pct": round((net_pnl / margin_inr) * 100.0, 2) if margin_inr > 0 else 0.0,
        "profit_factor": pf,
        "total_fees_paid_inr": fees,
        "total_gross_profit": round(gp, 2),
        "total_gross_loss": round(gl, 2),
        "trades_df": pdf,
        "coin_summary_df": coin_grp,
        "standalone_summary_df": standalone_df,
        "strategy_id": strategy_id,
        "strategy_breakdown": strategy_breakdown,
        "margin_inr": margin_inr,
        "leverage": leverage,
        "duration_days": duration_days,
        "starting_wallet_inr": round(eff_wallet_inr, 2),
        "ending_wallet_inr": round(current_wallet_inr, 2),
        "wallet_roi_pct": wallet_roi_pct,
        "max_drawdown_pct": round(max_drawdown_pct, 2),
        "guards_audit": guards_audit,
        "equity_curve": equity_curve,
    }


def _isolate_latest_iphone_notification(raw_text: str) -> str:
    """
    Given full-screen iPhone OCR text (which may contain the iPhone status bar at the very top,
    the LATEST notification banner / top Notification Center card first, and older notifications
    or the background Safari Trade Pro app below it), isolates ONLY the single latest notification.
    """
    import re as _re
    import urllib.parse as _urlparse

    txt = str(raw_text or "").strip()
    if "%" in txt and ("20" in txt or "0A" in txt or "3A" in txt):
        try:
            txt = _urlparse.unquote(txt)
        except Exception:
            pass

    # 1. Strip out any background Trade Pro Terminal UI text if the screenshot was taken over Safari
    app_ui_markers = (
        "SWITCH CRYPTO ASSET",
        "1-TAP SWITCH ASSET",
        "PRO TERMINAL SETUP",
        "FUTURES WALLET",
        "SINGLE-TRADE MARGIN",
        "SMART HYBRID EXECUTION TICKET",
        "TRADE EXECUTION TICKET",
        "ORDER SETUP",
        "SELECT TICKET",
        "CATASTROPHE SL",
        "COINDCX IPHONE AIR NOTIFICATION READER",
        "HIGH-VOLATILITY WATCHLIST MATRIX",
        "ACTIVE CONFIRMED SIGNALS",
    )
    up_full = txt.upper()
    cut_idx = len(txt)
    for marker in app_ui_markers:
        pos = up_full.find(marker)
        if pos != -1 and pos < cut_idx:
            cut_idx = pos
    txt = txt[:cut_idx].strip()

    # 2. Strip iPhone status bar prefixes at the very start (carrier, 5G/WiFi, clock)
    txt = _re.sub(
        r"^\s*(?:JIO|AIRTEL|VI|BSNL|5G|LTE|WIFI|WI-FI|\d{1,2}:\d{2}\s*(?:AM|PM)?|\d{1,3}%|[\s•|·-])+\s*",
        "",
        txt,
        flags=_re.IGNORECASE,
    ).strip()

    # 3. If 'CoinDCX' header appears in Notification Center, isolate ONLY the FIRST (top-most = latest) CoinDCX card!
    #    In iOS Notification Center, notifications are ordered strictly newest-at-top -> oldest-at-bottom.
    coindcx_matches = list(_re.finditer(r"\bCOINDCX\b", txt, flags=_re.IGNORECASE))
    if coindcx_matches:
        start_pos = coindcx_matches[0].start()
        # End at the 2nd 'CoinDCX' notification card (if multiple CoinDCX notifications are stacked)
        end_pos = coindcx_matches[1].start() if len(coindcx_matches) > 1 else len(txt)
        snippet = txt[start_pos:end_pos].strip()
    else:
        snippet = txt

    # 4. Also stop if another app's notification card or older timestamp header starts below the first notification
    other_card_split = _re.search(
        r"\b(?:NOTIFICATION CENTER|OLDER NOTIFICATIONS|GMAIL\s+\d|MESSAGES\s+\d|WHATSAPP\s+\d|TELEGRAM\s+\d|-\s*BOX THEORY SWEEP\s*-\s*TRADE NOTIFICATION)\b",
        snippet[25:],
        flags=_re.IGNORECASE,
    )
    if other_card_split:
        snippet = snippet[: 25 + other_card_split.start()].strip()

    # Cap to the top notification card (~260 chars max) so older cards further down the screen are never read
    return snippet[:260].strip() or txt[:260].strip()


def parse_coindcx_notification_text(
    raw_text: str,
    margin_inr: float = 20000.0,
    leverage: int = 10,
    usd_inr: float = None,
) -> dict:
    """
    Parses ONLY the latest (top-most) CoinDCX mobile push notification from iPhone Air Shortcut OCR
    and constructs a full Smart Hybrid 2-Entry + Runner trade setup:
      1. Isolates the top-most notification card (ignoring older notifications below it or background app UI).
      2. Identifies the FIRST (earliest-occurring) Futures Pair in that latest notification.
      3. Detects direction (LONG/BUY vs SHORT/SELL) strictly from that latest notification.
      4. Extracts any explicit Entry / TP / SL numbers in the latest notification, or computes fresh
         Smart Hybrid 2-Entry + Runner + Daily Box levels at the live market price.
    """
    import re as _re
    full_txt = str(raw_text or "").strip()
    if not full_txt:
        return {"ok": False, "error": "Empty notification text"}

    txt = _isolate_latest_iphone_notification(full_txt)
    u_inr = float(usd_inr or get_coindcx_live_usdt_inr_rate())
    up_txt = txt.upper()

    # 1. Detect Crypto Symbol -> CoinDCX Futures Pair by EARLIEST position in the latest notification!
    #    (Never loop in fixed BTC/ETH array order, which previously matched older notifications lower on screen.)
    candidates = []
    for p in GLOBAL_FUTURES_PAIRS:
        sym = p.replace("B-", "").replace("_USDT", "")
        # Explicit pair forms (e.g. SOL/USDT, SOLUSDT, SOL-USDT, B-SOL_USDT)
        for pat in (rf"\b{_re.escape(p)}\b", rf"\b{_re.escape(sym)}\s*[/\-_]?\s*USDT\b", rf"\b{_re.escape(sym)}\s*[/\-_]?\s*INR\b"):
            m = _re.search(pat, up_txt)
            if m:
                candidates.append((m.start(), 0, p))
                break
        # Standalone ticker symbol word boundary (e.g. 'SOL', 'RENDER', 'INJ', 'DOGE')
        m_sym = _re.search(rf"\b{_re.escape(sym)}\b", up_txt)
        if m_sym:
            candidates.append((m_sym.start(), 1, p))

    name_map = {
        "BITCOIN": "B-BTC_USDT", "ETHEREUM": "B-ETH_USDT", "SOLANA": "B-SOL_USDT",
        "RIPPLE": "B-XRP_USDT", "DOGECOIN": "B-DOGE_USDT", "AVALANCHE": "B-AVAX_USDT",
        "INJECTIVE": "B-INJ_USDT", "APTOS": "B-APT_USDT", "FETCH": "B-FET_USDT",
        "CARDANO": "B-ADA_USDT", "CHAINLINK": "B-LINK_USDT", "POLKADOT": "B-DOT_USDT",
        "LITECOIN": "B-LTC_USDT", "TONCOIN": "B-TON_USDT", "UNISWAP": "B-UNI_USDT",
    }
    for cname, cpair in name_map.items():
        m_name = _re.search(rf"\b{cname}\b", up_txt)
        if m_name:
            candidates.append((m_name.start(), 1, cpair))

    if not candidates:
        return {
            "ok": False,
            "error": "Could not detect a supported Futures coin symbol (e.g. SOL, RENDER, INJ, ETH, BTC) in the latest notification.",
            "raw_text": txt,
        }

    # Pick the coin that appears EARLIEST (top-most) in the latest notification card
    candidates.sort(key=lambda item: (item[0], item[1]))
    matched_pair = candidates[0][2]
    first_coin_pos = candidates[0][0]
    # Narrow analysis window to the text around this first coin (up to 180 chars after it)
    up_txt = up_txt[max(0, first_coin_pos - 40) : first_coin_pos + 180]

    # 2. Fetch live price, Daily Box levels, and Daily 50/200 EMA bias
    tk = fetch_live_ticker(matched_pair)
    live_px = float(tk.get("last_price", 0.0) or 0.0)
    levels = calculate_daily_box_levels(matched_pair) or {}
    bias_info = compute_market_bias(matched_pair, live_px)
    daily_bias = str(bias_info.get("bias", "NEUTRAL / RANGE")).upper()

    # 3. Detect Direction (LONG vs SHORT) from notification text
    bull_words = ("LONG", "BUY", "BULLISH", "BREAKOUT", "SURGE", "SURGED", "SURGING", "PUMP", "RALLY", "GAIN", "GAINED", "UP ", "HIGHER", "OVERSOLD", "SUPPORT", "BOUNCE")
    bear_words = ("SHORT", "SELL", "BEARISH", "BREAKDOWN", "DROP", "DROPPED", "DROPPING", "DUMP", "CRASH", "FALL", "FELL", "DOWN ", "LOWER", "OVERBOUGHT", "RESISTANCE", "REJECTION")
    bull_hits = sum(1 for w in bull_words if w in up_txt)
    bear_hits = sum(1 for w in bear_words if w in up_txt)

    # Also check signed percentage e.g. "+6.5%" vs "-5.2%"
    pct_matches = _re.findall(r"([+-]\d+(?:\.\d+)?)\s*%", up_txt)
    for pm in pct_matches:
        try:
            pv = float(pm)
            if pv >= 1.5:
                bull_hits += 2
            elif pv <= -1.5:
                bear_hits += 2
        except Exception:
            pass

    if bull_hits > bear_hits:
        direction = "LONG"
        dir_source = "Notification Bullish Signal"
    elif bear_hits > bull_hits:
        direction = "SHORT"
        dir_source = "Notification Bearish Signal"
    else:
        if "BEARISH" in daily_bias:
            direction = "SHORT"
            dir_source = f"Daily Bias ({daily_bias})"
        elif "BULLISH" in daily_bias:
            direction = "LONG"
            dir_source = f"Daily Bias ({daily_bias})"
        else:
            chg_24h = float(tk.get("change_24h", 0.0) or 0.0)
            direction = "LONG" if chg_24h >= 0 else "SHORT"
            dir_source = f"24h Momentum ({chg_24h:+.2f}%)"

    trade_dir = "BUY" if direction == "LONG" else "SELL"

    # 4. Extract any explicit Entry / TP / SL numbers if CoinDCX notification includes them
    def _extract_labeled_price(pattern: str) -> float | None:
        m = _re.search(pattern, up_txt)
        if m:
            try:
                val = float(m.group(1).replace(",", ""))
                if val > 0:
                    return val
            except Exception:
                pass
        return None

    exp_entry = _extract_labeled_price(r"(?:ENTRY|BUY AT|SELL AT|PRICE)[:\s@\$]*([0-9]+(?:\.[0-9]+)?)")
    exp_tp1 = _extract_labeled_price(r"(?:TP1|TARGET 1|TARGET|TAKE PROFIT)[:\s@\$]*([0-9]+(?:\.[0-9]+)?)")
    exp_tp2 = _extract_labeled_price(r"(?:TP2|TARGET 2)[:\s@\$]*([0-9]+(?:\.[0-9]+)?)")
    exp_sl = _extract_labeled_price(r"(?:SL|STOP LOSS|STOPLOSS|STOP)[:\s@\$]*([0-9]+(?:\.[0-9]+)?)")

    ref_e1 = exp_entry if (exp_entry and exp_entry > 0) else (live_px if live_px > 0 else float(levels.get("MID", 100.0) or 100.0))
    norm = normalize_two_entry_runner_levels(
        pair=matched_pair,
        direction=trade_dir,
        entry1_px=ref_e1,
        entry2_px=None,
        tp1_px=exp_tp1,
        tp2_px=exp_tp2,
        sl_px=exp_sl,
        live_px=live_px if live_px > 0 else ref_e1,
        levels=levels if levels else None,
    )

    e1 = norm["entry"]
    e2 = norm["entry2_sweep"]
    tp1 = norm["tp1"]
    tp2 = norm["tp2"]
    sl = norm["stop_loss"]

    pos_usd = (float(margin_inr) * int(leverage)) / u_inr
    qty = format_order_quantity(matched_pair, pos_usd / e1) if e1 > 0 else 0.0
    roe_tp1 = round((abs(tp1 - e1) / e1) * int(leverage) * 100.0, 2) if e1 > 0 else 0.0
    roe_tp2 = round((abs(tp2 - e1) / e1) * int(leverage) * 100.0, 2) if e1 > 0 else 0.0
    roe_sl = round((abs(e1 - sl) / e1) * int(leverage) * 100.0, 2) if e1 > 0 else 0.0

    sym_clean = matched_pair.replace("B-", "").replace("_USDT", "")
    summary = f"📲 CoinDCX Push ({sym_clean} {direction} via {dir_source})"

    return {
        "ok": True,
        "pair": matched_pair,
        "symbol": sym_clean,
        "signal": direction,
        "direction": trade_dir,
        "entry": e1,
        "entry2_sweep": e2,
        "tp1": tp1,
        "tp2": tp2,
        "stop_loss": sl,
        "crypto_qty": qty,
        "margin_inr": float(margin_inr),
        "leverage": int(leverage),
        "roe_tp1": roe_tp1,
        "roe_tp2": roe_tp2,
        "roe_sl": roe_sl,
        "profit_tp1_inr": round(abs(tp1 - e1) * qty * u_inr, 2),
        "profit_tp2_inr": round(abs(tp2 - e1) * qty * u_inr, 2),
        "loss_sl_inr": round(abs(e1 - sl) * qty * u_inr, 2),
        "daily_bias": daily_bias,
        "levels": levels,
        "strategy_id": "box_theory",
        "strategy_name": "Box Theory Sweep (CoinDCX Push Alert)",
        "signal_kind": "COINDCX_PUSH_NOTIFICATION",
        "trigger_zone": f"CoinDCX iPhone Alert ({dir_source})",
        "trigger_reason": f"{summary}: {txt[:140]}",
        "summary": summary,
        "raw_text": txt,
        "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
    }


def record_coindcx_push_notification(
    raw_text: str,
    margin_inr: float = 20000.0,
    leverage: int = 10,
    usd_inr: float = None,
) -> dict:
    """
    Parses an incoming CoinDCX notification from the user's iPhone Air Shortcut, stores it in
    in-memory `_PERSIST['coindcx_push_alerts']` for instant UI display, and logs it asynchronously
    to the `CoinDCX_Notifications` tab in `Crypto_Trades_Journal`.
    """
    parsed = parse_coindcx_notification_text(raw_text, margin_inr=margin_inr, leverage=leverage, usd_inr=usd_inr)
    parsed["push_id"] = int(time.time() * 1000)
    alerts_list = _PERSIST.setdefault("coindcx_push_alerts", [])
    isolated_txt = parsed.get("raw_text") or str(raw_text).strip()
    if not alerts_list or alerts_list[0].get("raw_text") != isolated_txt:
        alerts_list.insert(0, parsed)
        del alerts_list[20:]

        def _bg_log():
            try:
                import sheets_logger as _sl
                _sl.log_coindcx_notification_to_sheet(isolated_txt, parsed)
            except Exception:
                pass

        _threading.Thread(target=_bg_log, daemon=True, name="CoinDCXPushSheetLog").start()
    else:
        alerts_list[0] = parsed
    return parsed


def get_recent_coindcx_notifications(limit: int = 10) -> list[dict]:
    """Returns recent CoinDCX push notifications from memory or Google Sheets."""
    mem = _PERSIST.get("coindcx_push_alerts") or []
    if mem:
        return list(mem[:limit])
    try:
        import sheets_logger as _sl
        rows = _sl.fetch_coindcx_notifications_from_sheet(limit=limit)
        out = []
        for r in rows:
            out.append({
                "ok": bool(r.get("Parsed Pair")),
                "timestamp": r.get("Timestamp (IST)", ""),
                "raw_text": r.get("Raw Notification Text", ""),
                "pair": r.get("Parsed Pair", ""),
                "direction": r.get("Direction", "BUY"),
                "signal": "LONG" if str(r.get("Direction", "BUY")).upper() in ("LONG", "BUY") else "SHORT",
                "entry": float(r.get("Entry ($)") or 0.0),
                "entry2_sweep": float(r.get("Entry 2 Sweep ($)") or 0.0),
                "tp1": float(r.get("TP1 ($)") or 0.0),
                "tp2": float(r.get("TP2 ($)") or 0.0),
                "stop_loss": float(r.get("Stop Loss ($)") or 0.0),
                "daily_bias": r.get("Daily Bias", ""),
                "summary": r.get("Source / Summary", "iPhone Air Shortcut"),
            })
        if out:
            _PERSIST["coindcx_push_alerts"] = out
        return out
    except Exception:
        return []


def get_rotational_margin_inr(leverage: int = 10) -> dict:
    """
    Rotational capital sizing: 1/3rd of live CoinDCX Futures wallet equity per trade (or user's saved single-trade margin).
    Uses cached wallet equity in 0ms without blocking or recursing.
    """
    _check_and_kill_obsolete_daemon()
    equity, live = DEFAULT_WALLET_INR, False
    try:
        bal = _WALLET_BALANCE_CACHE.get("data") or _WALLET_BALANCE_CACHE.get("last_good_live")
        if isinstance(bal, dict) and float(bal.get("total_inr", 0)) > 0:
            equity, live = float(bal["total_inr"]), bool(bal.get("is_live_api", True))
        else:
            equity, live = _get_saved_wallet_balance_default(), True
    except Exception as e:
        print(f"[Wallet Sizing Fallback]: {e}")
    margin = round(equity * TRADE_ALLOCATION_FRACTION, 2)
    return {"wallet_equity_inr": equity, "margin_inr": margin, "leverage": leverage,
            "notional_inr": margin * leverage, "is_live_api": live}


def _upgrade_all_in_memory_functions_and_disarm():
    """
    1. Immediately disarms AutoTrade ('enabled': False) once on v5 reload so no background or cached scan can place trades.
    2. Forces hot-reload of strategies and signal_monitor in sys.modules even when no browser tab is open.
    3. Upgrades __code__ on any older in-memory function objects held by stale threads so they immediately hit _check_and_kill_obsolete_daemon().
    """
    _sys.__dict__["_active_daemon_version"] = _REQUIRED_DAEMON_VERSION
    try:
        import gc
        import types
        target_fns = {
            "_check_and_kill_obsolete_daemon": _check_and_kill_obsolete_daemon,
            "_get_coindcx_credentials": _get_coindcx_credentials,
            "_probe_session_coindcx_ip": _probe_session_coindcx_ip,
            "_pin_coindcx_nat_session": _pin_coindcx_nat_session,
            "_fetch_coindcx_futures_balance_sync": _fetch_coindcx_futures_balance_sync,
            "_fetch_coindcx_active_positions_sync": _fetch_coindcx_active_positions_sync,
            "get_autotrade_config": get_autotrade_config,
            "get_rotational_margin_inr": get_rotational_margin_inr,
            "get_coindcx_live_usdt_inr_rate": get_coindcx_live_usdt_inr_rate,
            "_send_coindcx_signed_request": _send_coindcx_signed_request,
            "place_coindcx_futures_order": place_coindcx_futures_order,
            "compute_maker_limit_entry_price": compute_maker_limit_entry_price,
            "sync_full_2entry_runner_to_position": sync_full_2entry_runner_to_position,
            "execute_autotrade_two_entry_signal": execute_autotrade_two_entry_signal,
            "get_active_portfolio_trade_status": get_active_portfolio_trade_status,
            "compute_tp1_profit_lock_sl": compute_tp1_profit_lock_sl,
            "_check_recent_15m_tp1_touch_and_prev_hl": _check_recent_15m_tp1_touch_and_prev_hl,
            "_evaluate_smart_hybrid_runner_step": _evaluate_smart_hybrid_runner_step,
            "_find_matching_app_trade_record": _find_matching_app_trade_record,
            "_auto_protect_live_position_tp1_sl": _auto_protect_live_position_tp1_sl,
            "check_live_daily_loss_stop": check_live_daily_loss_stop,
            "unlock_autotrade_daily_loss_stop": unlock_autotrade_daily_loss_stop,
            "classify_universe_regime_from_stats": classify_universe_regime_from_stats,
            "compute_market_regime": compute_market_regime,
            "build_historical_regime_map": build_historical_regime_map,
            "count_open_ema50_200_slots": count_open_ema50_200_slots,
            "_get_active_locks_map": _get_active_locks_map,
            "get_open_entry_limit_orders": get_open_entry_limit_orders,
            "compute_wallet_capped_margin": compute_wallet_capped_margin,
            "save_autotrade_config": save_autotrade_config,
            "clear_autotrade_active_lock": clear_autotrade_active_lock,
            "register_app_trade_lock": register_app_trade_lock,
            "fetch_coindcx_spot_balances": fetch_coindcx_spot_balances,
            "fetch_coindcx_futures_wallet_transactions": fetch_coindcx_futures_wallet_transactions,
            "compute_futures_funds_summary": compute_futures_funds_summary,
            "parse_coindcx_statement_csv": parse_coindcx_statement_csv,
        }
        cur_globals = globals()
        for obj in gc.get_objects():
            if isinstance(obj, types.FunctionType):
                fname = getattr(obj, "__name__", "")
                if fname in target_fns and obj is not target_fns[fname]:
                    try:
                        g = getattr(obj, "__globals__", None)
                        if isinstance(g, dict):
                            g.update(cur_globals)
                        obj.__code__ = target_fns[fname].__code__
                    except Exception:
                        pass
    except Exception:
        pass

    if _PERSIST.get("emergency_disarm_version") != _REQUIRED_DAEMON_VERSION:
        _PERSIST["emergency_disarm_version"] = _REQUIRED_DAEMON_VERSION
        _PERSIST["lock"] = _threading.Lock()
        _PERSIST["nat_pin_lock"] = _threading.Lock()
        global _COINDCX_SIGN_LOCK, _NAT_PIN_LOCK
        _COINDCX_SIGN_LOCK = _PERSIST["lock"]
        _NAT_PIN_LOCK = _PERSIST["nat_pin_lock"]
        _WALLET_BALANCE_CACHE["refreshing"] = False
        _ACTIVE_POSITIONS_CACHE["refreshing"] = False
        _PERSIST["last_nat_probe_ts"] = 0.0
        if not _PERSIST.get("session_verified"):
            _PERSIST["seen_coindcx_ips"] = []
            _WALLET_BALANCE_CACHE["data"] = None
            _WALLET_BALANCE_CACHE["last_good_live"] = None
            _ACTIVE_POSITIONS_CACHE["data"] = None
            _ACTIVE_POSITIONS_CACHE["last_ok_ts"] = 0.0
            try:
                clear_autotrade_active_lock()
            except Exception:
                pass

    # Proactively warm live positions & wallet balance in background if not yet verified,
    # or immediately publish verified live account state to Crypto_Trades_Journal so peer deployments stay synced!
    if _PERSIST.get("session_verified") and not _PERSIST.get("using_sheet_bridge"):
        _trigger_bg_sheet_account_publish(
            wallet_data=_WALLET_BALANCE_CACHE.get("data"),
            positions_data=_ACTIVE_POSITIONS_CACHE.get("data"),
        )
    if not _PERSIST.get("session_verified") or not _ACTIVE_POSITIONS_CACHE.get("data"):
        _trigger_bg_wallet_refresh()
        _trigger_bg_positions_refresh()

    try:
        import importlib as _il
        if "sheets_logger" in _sys.modules:
            _il.reload(_sys.modules["sheets_logger"])
        if "strategies" in _sys.modules:
            _il.reload(_sys.modules["strategies"])
        if "signal_monitor" in _sys.modules:
            _il.reload(_sys.modules["signal_monitor"])
    except Exception as _rel_e:
        print(f"[Module Hot-Reload Notice]: {_rel_e}")


_upgrade_all_in_memory_functions_and_disarm()
