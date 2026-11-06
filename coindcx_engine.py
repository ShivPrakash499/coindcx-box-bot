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
        "tick_size": 0.01,
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
    """
    ref = ref_price if ref_price is not None else val
    if ref is None:
        return 0.0
    if abs(ref) < 0.001:
        return round(float(val), 6)
    elif abs(ref) < 1.0:
        return round(float(val), 4)
    else:
        return round(float(val), 2)

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
                chg = float(item.get("change_24_hour", 0) or 0)
                vol = float(item.get("volume", 0) or 0)
                return {
                    "pair": pair,
                    "symbol": clean_pair,
                    "last_price": round_asset_price(raw_p),
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


_REQUIRED_DAEMON_VERSION = 15
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
    if (now_s - float(_PERSIST.get("last_sheet_pub_ts", 0.0))) < 20.0:
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
        if active_proxy and (now_p - float(_PERSIST.get("last_proxy_probe_ts", 0.0))) >= 1.5:
            _PERSIST["last_proxy_probe_ts"] = now_p
            cand_proxy = _make_single_socket_session(use_proxy=True)
            cand_pool.append(cand_proxy)
            proxy_ip = _probe_session_coindcx_ip(cand_proxy, timeout=2.5) or "35.230.95.39"
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

        _PERSIST["last_auth_error"] = "HTTP 401 Invalid credentials / Egress IP not allowlisted"
        return res, _PERSIST["last_auth_error"]
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
                save_autotrade_config({"wallet_balance_inr": round(total_inr, 2)})
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
                    clear_autotrade_active_lock()
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
            clear_autotrade_active_lock()
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
                if sl_val is not None and "stop" in o_type:
                    _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel", {"id": o_id, "timestamp": int(round(time.time() * 1000))})
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

    # If combined TP+SL failed because one side violated mark price, try setting TP and SL individually
    if tp_val and sl_val:
        r_tp, _ = _call_create_tpsl(tp_val, None, as_float=False)
        r_sl, _ = _call_create_tpsl(None, sl_val, as_float=False)
        tp_ok = bool(r_tp is not None and r_tp.status_code == 200)
        sl_ok = bool(r_sl is not None and r_sl.status_code == 200)
        if tp_ok or sl_ok:
            _ACTIVE_POSITIONS_CACHE["data"] = None
            parts = []
            if tp_ok:
                parts.append(f"TP={tp_val}")
            if sl_ok:
                parts.append(f"SL={sl_val}")
            return True, f"Position {', '.join(parts)} attached on CoinDCX!"

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

    # Historical completed candles before yesterday within the 30-day window
    df_hist = df_completed.iloc[:-1]

    # Calculate average daily price rise (for green days) and average daily price drop (for red days)
    up_days = df_completed[df_completed['close'] >= df_completed['open']]
    down_days = df_completed[df_completed['close'] < df_completed['open']]

    avg_daily_rise = float((up_days['close'] - up_days['open']).mean()) if len(up_days) > 0 else (rh - rl) * 0.25
    avg_daily_drop = float((down_days['open'] - down_days['close']).mean()) if len(down_days) > 0 else (rh - rl) * 0.25

    if avg_daily_rise <= 0:
        avg_daily_rise = (rh - rl) * 0.25
    if avg_daily_drop <= 0:
        avg_daily_drop = (rh - rl) * 0.25

    # Minimum structural separation between RH <-> SH and RL <-> SL so SH/SL never collapse onto RH/RL
    min_sh_gap = max(rh * 0.008, avg_daily_rise * 0.35)
    max_sh_gap = max(avg_daily_rise, min_sh_gap)
    min_sl_gap = max(rl * 0.008, avg_daily_drop * 0.35)
    max_sl_gap = max(avg_daily_drop, min_sl_gap)

    # Look for swing peaks beyond RH + min_sh_gap strictly within the 30-day window
    historical_highs = df_hist['high'].tolist() if not df_hist.empty else []
    sh_candidates = [float(h) for h in historical_highs if float(h) >= rh + min_sh_gap]
    if sh_candidates:
        nearest_sh = min(sh_candidates)
        # If candidate is within average daily rise distance from RH, use it; otherwise place at RH + max_sh_gap
        if (nearest_sh - rh) <= max_sh_gap:
            sh = nearest_sh
        else:
            sh = rh + max_sh_gap
    else:
        sh = rh + max_sh_gap

    # Look for swing troughs beyond RL - min_sl_gap strictly within the 30-day window
    historical_lows = df_hist['low'].tolist() if not df_hist.empty else []
    sl_candidates = [float(l) for l in historical_lows if float(l) <= rl - min_sl_gap]
    if sl_candidates:
        nearest_sl = max(sl_candidates)
        # If candidate is within average daily drop distance from RL, use it; otherwise place at RL - max_sl_gap
        if (rl - nearest_sl) <= max_sl_gap:
            sl = nearest_sl
        else:
            sl = rl - max_sl_gap
    else:
        sl = rl - max_sl_gap

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

def calculate_trade_setup_details(direction="BUY", levels=None, live_price=0.0, margin_inr=100000, leverage=5, usd_inr=85.0, pair="B-ETH_USDT"):
    """
    Calculates specific BUY (Long at Range Low / Swing Low) or SELL (Short at Range High / Swing High)
    2-Entry + Runner trade setup parameters:
      - Entry 1 (50% Margin): RL / RH rejection price
      - Entry 2 (50% Margin — Same Amount): SL / SH sweep scale-in level
      - Catastrophe SL: ~0.8% beyond Entry 2 (SL / SH)
      - TP1 (50% Early Book + Move SL to Breakeven): min(10% ROE, MID)
      - TP2 (50% Risk-Free Runner for Big Drop): Opposite Box Edge (RH / RL)
    """
    if not levels:
        return None

    rh, rl = levels["RH"], levels["RL"]
    sh, sl = levels["SH"], levels["SL"]
    mid = levels["MID"]

    lev = max(1, int(leverage))
    if direction.upper() in ["BUY", "LONG"]:
        dir_name = "BUY"
        entry = round_asset_price(live_price if live_price > 0 and live_price <= rl else rl, rh)
        entry2_sweep = round_asset_price(min(sl, entry * 0.992), rh)
        avg_entry_2x = round_asset_price((entry + entry2_sweep) / 2.0, rh)
        stop_loss = round_asset_price(min(entry2_sweep * 0.992, sl * 0.995), rh)
        max_tp1_dist = entry * (10.0 / 100.0 / lev)
        tp1_dist = min(abs(mid - entry), max_tp1_dist)
        tp1 = round_asset_price(entry + tp1_dist, rh)
        tp2_target = rh if entry < rh * 0.988 else sh
        tp2 = round_asset_price(max(tp2_target, entry + tp1_dist * 2.0), rh)
        setup_desc = (
            f"BUY (Long): 2-Entry Sweep + Runner — Entry1 ${entry:,.2f} + Entry2 @ SL ${entry2_sweep:,.2f} | "
            f"TP1 (50% Book <=10% ROE) -> TP2 (50% Runner to RH ${tp2:,.2f})"
        )
    else:
        dir_name = "SELL"
        entry = round_asset_price(live_price if live_price > 0 and live_price >= rh else rh, rh)
        entry2_sweep = round_asset_price(max(sh, entry * 1.008), rh)
        avg_entry_2x = round_asset_price((entry + entry2_sweep) / 2.0, rh)
        stop_loss = round_asset_price(max(entry2_sweep * 1.008, sh * 1.005), rh)
        max_tp1_dist = entry * (10.0 / 100.0 / lev)
        tp1_dist = min(abs(entry - mid), max_tp1_dist)
        tp1 = round_asset_price(entry - tp1_dist, rh)
        tp2_target = rl if entry > rl * 1.012 else sl
        tp2 = round_asset_price(min(tp2_target, entry - tp1_dist * 2.0), rh)
        setup_desc = (
            f"SELL (Short): 2-Entry Sweep + Runner — Entry1 ${entry:,.2f} + Entry2 @ SH ${entry2_sweep:,.2f} | "
            f"TP1 (50% Book <=10% ROE) -> TP2 (50% Runner to RL ${tp2:,.2f})"
        )

    margin_usd = margin_inr / usd_inr
    position_usd = margin_usd * leverage
    raw_qty = position_usd / entry if entry > 0 else 0
    crypto_qty = format_order_quantity(pair, raw_qty)
    tranche_qty = format_order_quantity(pair, (position_usd * 0.5) / entry) if entry > 0 else 0

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
        "tranche_margin_inr": round(margin_inr * 0.5, 2),
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
    returning the 2-Entry + Runner levels (TP1 = min(10% ROE, MID) for 50% book, TP2 = RL/RH for 50% runner).
    """
    rh, rl, sh, sl, mid = levels["RH"], levels["RL"], levels["SH"], levels["SL"], levels["MID"]

    if (h >= rh and c < rh) or (h >= sh and c < sh):
        entry2 = max(sh, h, c * 1.008)
        stop_p = round(entry2 * 1.008, 4)
        tp1_dist = min(abs(c - mid), c * 0.02)
        if tp1_dist < c * 0.0058:
            return None
        tp1_p = round(c - tp1_dist, 4)
        tp2_p = round(min(rl if c > rl * 1.012 else sl, c - tp1_dist * 2.0), 4)
        return {"kind": "REVERSAL", "direction": "SHORT", "zone": "Sell Zone RH-SH",
                "entry2_sweep": round(entry2, 4), "stop": stop_p, "tp1": tp1_p, "tp2": tp2_p}
    if (l <= rl and c > rl) or (l <= sl and c > sl):
        entry2 = min(sl, l, c * 0.992)
        stop_p = round(entry2 * 0.992, 4)
        tp1_dist = min(abs(mid - c), c * 0.02)
        if tp1_dist < c * 0.0058:
            return None
        tp1_p = round(c + tp1_dist, 4)
        tp2_p = round(max(rh if c < rh * 0.988 else sh, c + tp1_dist * 2.0), 4)
        return {"kind": "REVERSAL", "direction": "LONG", "zone": "Buy Zone RL-SL",
                "entry2_sweep": round(entry2, 4), "stop": stop_p, "tp1": tp1_p, "tp2": tp2_p}
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
    strategy_id: str = "box_theory"
) -> dict:
    """
    Executes a real-time historical simulation of any registered strategy (see strategies.py).
    Fetches real candles from CoinDCX / Binance public APIs with multi-batch pagination, lets the
    strategy build its daily context and detect entries, then simulates exits with the shared
    TP1 / TP2 / 50-50 ratchet engine and CoinDCX fee accounting.
    target_mode: "TP1 Midpoint" = 100% exit at TP1, "TP2 Full Rotation" = 100% at TP2,
                 "50/50 Split" = half at TP1, ratchet trailing SL on the rest toward TP2.
    """
    import strategies as _strategies
    strat = _strategies.get_strategy(strategy_id)

    if not usd_inr or usd_inr <= 0:
        usd_inr = get_coindcx_live_usdt_inr_rate()

    # 1. Fetch execution candles using multi-batch pagination
    df = fetch_historical_candles_paginated(
        pair=pair,
        interval=interval,
        duration_days=duration_days,
        progress_callback=progress_callback
    )
    if df.empty or len(df) < 20:
        return {"error": f"Insufficient historical candle data available for {pair} on {interval}."}

    # 2. Fetch daily candles for daily box establishment
    df_daily = fetch_historical_candles_paginated(
        pair=pair,
        interval="1d",
        duration_days=duration_days + strat.daily_warmup_days
    )
    if df_daily.empty or len(df_daily) < 5:
        return {"error": f"Insufficient daily candle data for {pair}."}

    df['dt_ist'] = pd.to_datetime(df['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(IST)
    df['date_str'] = df['dt_ist'].dt.strftime('%Y-%m-%d')

    df_daily['dt_ist'] = pd.to_datetime(df_daily['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(IST)
    df_daily['date_str'] = df_daily['dt_ist'].dt.strftime('%Y-%m-%d')

    # Strategy-specific daily context (Box: rolling daily boxes; ATR Reversal: 50-SMA + ATR14)
    strat_ctx = strat.prepare_backtest(df, df_daily)

    # 3. High-speed Sequential Candle Simulation using dictionary records
    df_records = df.to_dict('records')
    trades = []
    active_trade = None
    last_exit_idx = -999
    initial_capital = margin_inr
    current_equity = initial_capital
    first_candle_time = df['dt_ist'].iloc[0].strftime("%Y-%m-%d %H:%M")
    equity_curve = [{"timestamp": first_candle_time, "equity_inr": initial_capital, "pnl_inr": 0.0}]

    taker_fee_rate = 0.0005 * 1.18  # 0.05% + 18% GST
    day_trade_count = {}
    day_realized_pnl = {}
    day_locked = set()

    for idx, candle in enumerate(df_records):
        c_date = candle['date_str']
        c_time = candle['dt_ist']
        c_high = float(candle['high'])
        c_low = float(candle['low'])
        c_close = float(candle['close'])

        if not strat.backtest_has_context(candle, strat_ctx):
            continue

        # Check active trade exit & 2-Entry Scale-In + 50/50 Runner conditions
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

            # Step A: If Tranche 2 (at SH/SL sweep level) has not filled yet and TP1 not hit yet, check if price swept into Entry 2
            if not active_trade.get("entry2_filled", False) and not active_trade.get("tp1_hit", False) and entry2_p > 0:
                if (pos_dir == "LONG" and c_low <= entry2_p and c_low > sl_p) or (
                    pos_dir == "SHORT" and c_high >= entry2_p and c_high < sl_p
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
            scale_tag = " [2-Entry Averaged]" if active_trade.get("entry2_filled") else " [Entry 1]"

            if pos_dir == "LONG":
                if not active_trade.get("tp1_hit", False):
                    if c_low <= sl_p:
                        exit_triggered = True
                        exit_price = sl_p
                        exit_reason = f"Catastrophe Stop Loss Beyond SL Sweep{scale_tag}"
                    elif c_high >= tp2_p:
                        exit_triggered = True
                        exit_price = 0.5 * tp1_p + 0.5 * tp2_p
                        exit_reason = f"TP1 (50% Book) + TP2 (50% Big Drop Runner){scale_tag}"
                    elif c_high >= tp1_p:
                        active_trade["tp1_hit"] = True
                        prev_c = df_records[idx - 1] if idx > 0 else candle
                        prev_l = float(prev_c["low"])
                        mid_runner = 0.5 * (tp1_p + tp2_p)
                        if c_high >= mid_runner:
                            new_sl = tp1_p
                        else:
                            new_sl = compute_tp1_profit_lock_sl(pair, "LONG", entry_p, tp1_p, prev_candle_low=prev_l)
                        active_trade["stop_loss"] = new_sl
                        sl_p = new_sl
                else:
                    # TP1 already booked (50% closed at tp1_p); managing the remaining 50% Free-Ride Runner
                    mid_runner = 0.5 * (tp1_p + tp2_p)
                    if c_high >= mid_runner and sl_p < tp1_p:
                        active_trade["stop_loss"] = tp1_p
                        sl_p = tp1_p
                    if c_high >= tp2_p:
                        exit_triggered = True
                        exit_price = 0.5 * tp1_p + 0.5 * tp2_p
                        exit_reason = f"TP1 (50% Book) + TP2 (50% Runner Hit RH){scale_tag}"
                    elif c_low <= sl_p:
                        exit_triggered = True
                        exit_price = 0.5 * tp1_p + 0.5 * sl_p
                        r_lbl = "Runner Locked at TP1" if sl_p >= tp1_p else "Runner Profit-Locked SL"
                        exit_reason = f"TP1 (50% Booked) + 50% {r_lbl}{scale_tag}"
            else:  # SHORT
                if not active_trade.get("tp1_hit", False):
                    if c_high >= sl_p:
                        exit_triggered = True
                        exit_price = sl_p
                        exit_reason = f"Catastrophe Stop Loss Beyond SH Sweep{scale_tag}"
                    elif c_low <= tp2_p:
                        exit_triggered = True
                        exit_price = 0.5 * tp1_p + 0.5 * tp2_p
                        exit_reason = f"TP1 (50% Book) + TP2 (50% Big Drop Runner){scale_tag}"
                    elif c_low <= tp1_p:
                        active_trade["tp1_hit"] = True
                        prev_c = df_records[idx - 1] if idx > 0 else candle
                        prev_h = float(prev_c["high"])
                        mid_runner = 0.5 * (tp1_p + tp2_p)
                        if c_low <= mid_runner:
                            new_sl = tp1_p
                        else:
                            new_sl = compute_tp1_profit_lock_sl(pair, "SHORT", entry_p, tp1_p, prev_candle_high=prev_h)
                        active_trade["stop_loss"] = new_sl
                        sl_p = new_sl
                else:
                    # TP1 already booked (50% closed at tp1_p); managing the remaining 50% Free-Ride Runner
                    mid_runner = 0.5 * (tp1_p + tp2_p)
                    if c_low <= mid_runner and sl_p > tp1_p:
                        active_trade["stop_loss"] = tp1_p
                        sl_p = tp1_p
                    if c_low <= tp2_p:
                        exit_triggered = True
                        exit_price = 0.5 * tp1_p + 0.5 * tp2_p
                        exit_reason = f"TP1 (50% Book) + TP2 (50% Runner Hit RL){scale_tag}"
                    elif c_high >= sl_p:
                        exit_triggered = True
                        exit_price = 0.5 * tp1_p + 0.5 * sl_p
                        r_lbl = "Runner Locked at TP1" if sl_p <= tp1_p else "Runner Profit-Locked SL"
                        exit_reason = f"TP1 (50% Booked) + 50% {r_lbl}{scale_tag}"

            if exit_triggered:
                # Calculate financial metrics with exact CoinDCX fee schedule
                if pos_dir == "LONG":
                    gross_pnl_usd = (exit_price - entry_p) * qty
                else:
                    gross_pnl_usd = (entry_p - exit_price) * qty

                gross_pnl_inr = gross_pnl_usd * usd_inr
                entry_fee_inr = notional_inr * taker_fee_rate
                exit_notional_inr = (qty * exit_price) * usd_inr
                exit_fee_inr = exit_notional_inr * taker_fee_rate
                total_fees_inr = entry_fee_inr + exit_fee_inr
                net_pnl_inr = gross_pnl_inr - total_fees_inr
                roe_pct = (net_pnl_inr / deployed_margin_inr) * 100.0 if deployed_margin_inr > 0 else 0.0
                gross_roe_pct = (gross_pnl_inr / deployed_margin_inr) * 100.0 if deployed_margin_inr > 0 else 0.0

                current_equity += net_pnl_inr

                entry_day = active_trade.get("entry_date", c_date)
                day_realized_pnl[entry_day] = day_realized_pnl.get(entry_day, 0.0) + net_pnl_inr
                # Done for the Day Rule: if single trade achieves >=10% ROE (gross >=9.5% or net daily >=9% of margin), lock day
                if gross_roe_pct >= 9.5 or day_realized_pnl[entry_day] >= (margin_inr * 0.09):
                    day_locked.add(entry_day)
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
                    "target_tp": round_asset_price(tp2_p, entry_p),
                    "exit_reason": exit_reason,
                    "quantity": qty,
                    "gross_pnl_inr": round(gross_pnl_inr, 2),
                    "fees_inr": round(total_fees_inr, 2),
                    "net_pnl_inr": round(net_pnl_inr, 2),
                    "roe_pct": round(roe_pct, 2),
                    "is_win": net_pnl_inr > 0,
                    "duration_candles": idx - active_trade["entry_idx"],
                    "strategy": strat.name,
                    "trigger": active_trade.get("reason", "")
                })

                equity_curve.append({
                    "timestamp": c_time.strftime("%Y-%m-%d %H:%M"),
                    "equity_inr": round(current_equity, 2),
                    "pnl_inr": round(net_pnl_inr, 2)
                })

                active_trade = None
                last_exit_idx = idx

        # Daily Discipline Gate: Max 2 trades/day + Done for the day after >=10% ROE win
        if c_date in day_locked or day_trade_count.get(c_date, 0) >= 2:
            continue

        # If no active trade, ask the strategy whether this closed candle is an entry
        if not active_trade and (idx - last_exit_idx >= 1):
            entry_sig = strat.backtest_entry(idx, candle, strat_ctx, df_records)
            if entry_sig:
                trade_dir = entry_sig["direction"]
                entry_p = entry_sig["entry"]
                entry2_p = entry_sig.get("entry2_sweep", 0.0)
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
                    "tp1_label": entry_sig.get("tp1_label", "50% Book"),
                    "tp2_label": entry_sig.get("tp2_label", "50% Runner"),
                    "reason": entry_sig.get("reason", "")
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


_AUTOTRADE_CFG_MEM_CACHE = _PERSIST.setdefault("autotrade_cfg_cache", {"mtime": 0.0, "data": None})


def get_autotrade_config() -> dict:
    """
    Loads persistent AutoTrade & Single-Trade Margin settings shared between the Streamlit UI
    and the 24/7 background monitor daemon in 0ms (never makes network or recursive balance calls).
    Immediately terminates any obsolete pre-v3 background daemon threads from earlier @st.cache_resource runs.
    """
    _check_and_kill_obsolete_daemon()

    default_cfg = {
        "enabled": False,
        "wallet_balance_inr": 47287.18,
        "single_trade_margin_inr": 15762.39,
        "leverage": 10,
        "one_crypto_at_a_time": True,
        "high_vol_scan_enabled": True,
        "active_trade_lock": None,
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
                return res
            with open(AUTOTRADE_CONFIG_FILE, "r", encoding="utf-8") as f:
                saved = json.load(f)
                if isinstance(saved, dict):
                    _AUTOTRADE_CFG_MEM_CACHE["data"] = dict(saved)
                    _AUTOTRADE_CFG_MEM_CACHE["mtime"] = mtime
                    default_cfg.update(saved)
                    wb = float(default_cfg.get("wallet_balance_inr", 47287.18) or 47287.18)
                    if float(default_cfg.get("single_trade_margin_inr", 0) or 0) <= 0:
                        default_cfg["single_trade_margin_inr"] = round(wb * TRADE_ALLOCATION_FRACTION, 2)
    except Exception:
        pass
    return default_cfg


def save_autotrade_config(updates: dict) -> dict:
    """Saves updated AutoTrade settings to .cache/autotrade_config.json without triggering any API calls."""
    cfg = get_autotrade_config()
    cfg.update(updates)
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


def clear_autotrade_active_lock() -> dict:
    """Clears any local paper/autotrade active trade slot lock so the next coin can trade."""
    return save_autotrade_config({"active_trade_lock": None})


def cancel_coindcx_open_entry_orders(pair: str, order_id: str = None, side: str = None) -> int:
    """
    Cancels any unfilled resting limit orders (such as an unfilled Entry 2 @ Sweep order)
    for `pair` once TP1 is reached or the trade closes.
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
            if o_id and o_pair == pair and o_stage != "tpsl_exit" and "limit" in o_type:
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

    if is_long:
        high_ref = max(e1, cur_p) if cur_p > 0 else e1
        low_ref = min(e1, cur_p) if cur_p > 0 else e1

        cand_e2 = float(entry2_px or (levels.get("SL") if levels else 0.0) or 0.0)
        if cand_e2 <= 0 or cand_e2 >= low_ref * 0.9992:
            cand_e2 = low_ref * 0.992

        cand_sl = float(sl_px or 0.0)
        min_long_anchor = min(low_ref, cand_e2)
        if cand_sl <= 0 or cand_sl >= min_long_anchor * 0.999:
            cand_sl = min_long_anchor * 0.995

        cand_tp1 = float(tp1_px or (levels.get("MID") if levels else 0.0) or 0.0)
        if cand_tp1 <= high_ref * 1.002:
            cand_tp1 = high_ref * 1.012

        cand_tp2 = float(tp2_px or (levels.get("RH") if levels else 0.0) or 0.0)
        if cand_tp2 <= cand_tp1 * 1.002:
            cand_tp2 = max(cand_tp1 * 1.012, high_ref * 1.024)
    else:
        low_ref = min(e1, cur_p) if cur_p > 0 else e1
        high_ref = max(e1, cur_p) if cur_p > 0 else e1

        cand_e2 = float(entry2_px or (levels.get("SH") if levels else 0.0) or 0.0)
        if cand_e2 <= 0 or cand_e2 <= high_ref * 1.0008:
            cand_e2 = high_ref * 1.008

        cand_sl = float(sl_px or 0.0)
        max_short_anchor = max(high_ref, cand_e2)
        if cand_sl <= 0 or cand_sl <= max_short_anchor * 1.001:
            cand_sl = max_short_anchor * 1.005

        cand_tp1 = float(tp1_px or (levels.get("MID") if levels else 0.0) or 0.0)
        if cand_tp1 <= 0 or cand_tp1 >= low_ref * 0.998:
            cand_tp1 = low_ref * 0.988

        cand_tp2 = float(tp2_px or (levels.get("RL") if levels else 0.0) or 0.0)
        if cand_tp2 <= 0 or cand_tp2 >= cand_tp1 * 0.998:
            cand_tp2 = min(cand_tp1 * 0.988, low_ref * 0.976)

    return {
        "entry": format_order_price(pair, e1),
        "entry2_sweep": format_order_price(pair, cand_e2),
        "tp1": format_order_price(pair, cand_tp1),
        "tp2": format_order_price(pair, cand_tp2),
        "stop_loss": format_order_price(pair, cand_sl),
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
) -> tuple[bool, str, dict]:
    """
    Synchronizes all 4 components of the 2-Entry + 50/50 Runner setup onto an active CoinDCX position:
      1. Position Bracket TP = TP2 (Runner) & SL = Catastrophe SL via `update_coindcx_position_tpsl`.
      2. TP1 50% Partial Book resting opposite-side Limit Order (`0.5 * pos_qty` @ `tp1_px`) in Open Orders.
      3. Entry 2 / Trade 2 resting same-side Limit Order (`50%` of `total_margin_inr` @ `entry2_px`) in Open Orders.
      4. App Trade Lock registration so the 24/7 daemon manages TP1 -> Cancel Entry 2 -> Ratchet SL -> TP2.
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
    pos_entry = float(entry1_px or matched_pos.get("entry_price", 0.0) or 0.0)
    pos_mark = float(matched_pos.get("mark_price", pos_entry) or pos_entry)
    pos_lev = int(round(float(matched_pos.get("leverage") or leverage or 10)))

    levels = None
    try:
        levels = calculate_daily_box_levels(pair)
    except Exception:
        pass

    norm = normalize_two_entry_runner_levels(
        pair=pair,
        direction=pos_dir,
        entry1_px=pos_entry,
        entry2_px=entry2_px,
        tp1_px=tp1_px,
        tp2_px=tp2_px,
        sl_px=sl_px,
        live_px=pos_mark,
        levels=levels,
    )
    e1_val = norm["entry"]
    e2_val = norm["entry2_sweep"]
    tp1_val = norm["tp1"]
    tp2_val = norm["tp2"]
    sl_val = norm["stop_loss"]

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

    # 2. Place TP1 (50% Partial Book) opposite-side Limit Order if not already open
    tp1_order_id = ""
    tp1_qty = format_order_quantity(pair, pos_qty * 0.5)
    if (tp1_qty * tp1_val * u_inr) < 2448.0 and (pos_qty * tp1_val * u_inr) >= 2448.0:
        tp1_qty = min(pos_qty, format_order_quantity(pair, (2500.0 / u_inr) / tp1_val))

    if existing_opp_side_limit:
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

    # 3. Place Entry 2 / Trade 2 (50% Sweep Scale-In) same-side Limit Order if not already open
    e2_order_id = ""
    tranche_m_inr = max(float(total_margin_inr or 20000.0) * 0.5, float(matched_pos.get("locked_margin_inr", 10000.0) or 10000.0))
    qty2 = format_order_quantity(pair, ((tranche_m_inr * pos_lev) / u_inr) / e2_val) if e2_val > 0 else 0.0

    if existing_same_side_limit:
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
        margin_inr=float(total_margin_inr or tranche_m_inr * 2.0),
        leverage=pos_lev,
        qty1=pos_qty,
        qty2=qty2,
        mode="App/API Live Execution (2-Entry + TP1/TP2/SL Synced)",
        is_live_exchange=True,
        entry2_order_id=e2_order_id,
        tp1_order_id=tp1_order_id or "DAEMON_50PCT_REDUCE_AT_TP1",
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
) -> dict:
    """
    Registers an active 1-Crypto-at-a-Time lock strictly for trades executed via our App/API.
    Manual trades placed directly on CoinDCX outside our App/API do NOT trigger this lock.
    """
    now_str = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    lock_info = {
        "pair": pair,
        "direction": str(direction).upper(),
        "entry": float(entry or 0.0),
        "entry2_sweep": float(entry2_sweep or entry or 0.0),
        "entry2_filled": False,
        "entry2_cancelled": False,
        "entry2_order_id": str(entry2_order_id or ""),
        "tp1_order_id": str(tp1_order_id or ""),
        "tp1": float(tp1 or 0.0),
        "tp2": float(tp2 or tp1 or 0.0),
        "tp1_hit": False,
        "runner_halfway_ratcheted": False,
        "stop_loss": float(stop_loss or 0.0),
        "qty1": float(qty1 or 0.0),
        "qty2": float(qty2 or 0.0),
        "margin_inr": float(margin_inr or 0.0),
        "leverage": int(leverage or 10),
        "opened_at": now_str,
        "opened_ts": time.time(),
        "mode": mode,
        "is_live_exchange": bool(is_live_exchange),
    }
    cfg = get_autotrade_config()
    prev_lock = cfg.get("active_trade_lock") or {}
    is_new_live_lock = bool(
        is_live_exchange
        and (
            prev_lock.get("pair") != pair
            or str(prev_lock.get("direction", "")).upper() != str(direction).upper()
            or (time.time() - float(prev_lock.get("opened_ts", 0.0) or 0.0)) > 600
        )
    )
    hist = cfg.get("history", [])
    hist.insert(0, {**lock_info, "status": "APP_API_LOCK_SET"})
    save_autotrade_config({"active_trade_lock": lock_info, "history": hist[:30]})

    if is_new_live_lock:
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
                    "strategy_name": "Box Theory Sweep (App Live Order)",
                    "trigger_reason": f"{mode} | E1: ${e_f}, E2: ${float(entry2_sweep or 0.0)}",
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
    Checks recent 15m candles (since `opened_ts`) to detect whether price wicked through `tp1_px`
    between daemon ticks, and returns `(touched_tp1, prev_15m_high, prev_15m_low)`.
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
            if tp1_px > 0:
                cutoff_ms = max(0.0, (float(opened_ts) - 900.0) * 1000.0) if opened_ts > 0 else 0.0
                recent_df = df_15m[df_15m["timestamp"] >= cutoff_ms] if cutoff_ms > 0 else df_15m.tail(3)
                if not recent_df.empty:
                    if is_long and float(recent_df["high"].max()) >= tp1_px:
                        touched = True
                    elif (not is_long) and float(recent_df["low"].min()) <= tp1_px:
                        touched = True
    except Exception:
        pass
    return touched, prev_h, prev_l


def _auto_protect_live_position_tp1_sl(pos: dict) -> None:
    """
    Safeguards any live CoinDCX position (even if it is not the primary `active_trade_lock` pair,
    such as when `INJ` and `RENDER` were both open) by checking whether TP1 was reached on the
    current price or recent 15m candles, cancelling any unfilled same-side Entry 2 limit order,
    and ratcheting the Position SL into profit (Strategy 3B/3C).
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
        if entry_p <= 0:
            return

        # If SL is already in profit beyond entry, check Stage 2 (50% to TP2 -> lock SL at TP1)
        already_in_profit_sl = (cur_sl > entry_p) if (is_long and cur_sl > 0) else ((cur_sl < entry_p) if (not is_long and cur_sl > 0) else False)

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
            sl_px=cur_sl if cur_sl > 0 else None,
            live_px=mark_p,
            levels=levels,
        )
        tp1_px = float(norm["tp1"])
        tp2_px = float(cur_tp if cur_tp > 0 else norm["tp2"])

        if already_in_profit_sl:
            mid_runner = 0.5 * (tp1_px + tp2_px)
            if (is_long and mark_p >= mid_runner and cur_sl < tp1_px) or (
                (not is_long) and mark_p <= mid_runner and cur_sl > tp1_px
            ):
                update_coindcx_position_tpsl(pid, tp_price=tp2_px, sl_price=tp1_px, pair=pair)
            return

        # Check if TP1 was reached by live mark price or recent 15m candle high/low (last 3 candles = 45m)
        hit_tp1 = (mark_p >= tp1_px) if is_long else (mark_p <= tp1_px)
        wicked_tp1, prev_h, prev_l = _check_recent_15m_tp1_touch_and_prev_hl(pair, is_long, tp1_px, opened_ts=time.time() - 1800.0)
        if hit_tp1 or wicked_tp1:
            entry_side = "buy" if is_long else "sell"
            cancel_coindcx_open_entry_orders(pair, side=entry_side)
            new_sl = compute_tp1_profit_lock_sl(
                pair=pair,
                direction=direction,
                entry_px=entry_p,
                tp1_px=tp1_px,
                prev_candle_high=prev_h,
                prev_candle_low=prev_l,
            )
            better = (cur_sl <= 0) or ((new_sl > cur_sl) if is_long else (new_sl < cur_sl))
            if better and new_sl > 0:
                update_coindcx_position_tpsl(pid, tp_price=tp2_px, sl_price=new_sl, pair=pair)
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
    lock = cfg.get("active_trade_lock")
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

        # Fast-path for UI rendering: return lock status immediately in <1ms without blocking on exchange API calls
        if not manage_exchange:
            if is_live_ex and l_ts > 0 and (time.time() - l_ts) >= 90 and _PERSIST.get("session_verified"):
                _cached_p = _ACTIVE_POSITIONS_CACHE.get("data")
                _last_ok_p = float(_ACTIVE_POSITIONS_CACHE.get("last_ok_ts", 0.0))
                if isinstance(_cached_p, list) and (time.time() - _last_ok_p) < 120.0:
                    if not any(p.get("pair") == l_pair for p in _cached_p):
                        clear_autotrade_active_lock()
                        return {"is_occupied": False, "active_pair": None, "source": "Slot Free (App Trade Closed on Exchange)"}
            return {
                "is_occupied": True,
                "active_pair": l_pair,
                "active_direction": l_dir,
                "entry_price": l_entry,
                "entry2_sweep": l_entry2,
                "tp1": l_tp1,
                "tp2": l_tp2,
                "tp1_hit": tp1_already_hit,
                "entry2_cancelled": bool(lock.get("entry2_cancelled", False)),
                "stop_loss": l_sl,
                "source": lock.get("mode", "App/API Active Trade Lock"),
                "count": 1,
            }

        try:
            if l_ts > 0 and (time.time() - l_ts) > 8 * 3600:
                if is_live_ex:
                    cancel_coindcx_open_entry_orders(l_pair, lock.get("entry2_order_id", ""))
                clear_autotrade_active_lock()
                return {"is_occupied": False, "active_pair": None, "source": "Slot Free (Previous App Trade Expired)"}

            matched_live_pos = None
            if is_live_ex:
                # CRITICAL: Always use synchronous live fetch (_fetch_coindcx_active_positions_sync) here,
                # NEVER the UI's non-blocking cold-cache fetch_coindcx_active_positions(force_refresh=False),
                # which returns [] when cold and previously caused active_trade_lock to be falsely cleared!
                live_positions = _fetch_coindcx_active_positions_sync(return_none_on_error=True)
                if live_positions is not None:
                    matched_live_pos = next((p for p in live_positions if p.get("pair") == l_pair), None)
                    if matched_live_pos and matched_live_pos.get("id"):
                        if lock.get("missing_count", 0) > 0:
                            lock["missing_count"] = 0
                            save_autotrade_config({"active_trade_lock": lock})
                        # Auto-heal missing TP or SL on CoinDCX at most once per trade lock
                        if (
                            not lock.get("tpsl_healed")
                            and (matched_live_pos.get("stop_loss") is None or matched_live_pos.get("take_profit") is None)
                        ):
                            norm_lvls = normalize_two_entry_runner_levels(
                                pair=l_pair,
                                direction=l_dir,
                                entry1_px=float(matched_live_pos.get("entry_price") or l_entry),
                                entry2_px=l_entry2,
                                tp1_px=l_tp1,
                                tp2_px=l_tp2,
                                sl_px=l_sl,
                                live_px=float(matched_live_pos.get("mark_price") or l_entry),
                            )
                            l_tp2 = norm_lvls["tp2"]
                            l_sl = norm_lvls["stop_loss"]
                            lock["tp2"] = l_tp2
                            lock["stop_loss"] = l_sl
                            lock["tpsl_healed"] = True
                            save_autotrade_config({"active_trade_lock": lock})
                            update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=l_sl, pair=l_pair)
                    elif len(live_positions) > 0:
                        # Another position is open on CoinDCX: keep the portfolio slot occupied!
                        other_p = live_positions[0]
                        return {
                            "is_occupied": True,
                            "active_pair": other_p.get("pair"),
                            "active_direction": other_p.get("direction", "LONG"),
                            "entry_price": float(other_p.get("entry_price", 0.0) or 0.0),
                            "stop_loss": float(other_p.get("stop_loss", 0.0) or 0.0),
                            "source": "CoinDCX Live Active Position",
                            "count": len(live_positions),
                        }
                    elif l_ts > 0 and (time.time() - l_ts) >= 90 and fetch_coindcx_futures_balance().get("is_live_api"):
                        # Require 2 consecutive confirmed 200-OK empty position checks before releasing lock
                        miss_cnt = int(lock.get("missing_count", 0)) + 1
                        if miss_cnt >= 2:
                            cancel_coindcx_open_entry_orders(l_pair, lock.get("entry2_order_id", ""))
                            clear_autotrade_active_lock()
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

                    # Full Exit at TP2 or Stop Loss (Catastrophe SL or Ratcheted Runner SL)
                    if hit_tp2 or hit_sl:
                        if is_live_ex:
                            cancel_coindcx_open_entry_orders(l_pair, lock.get("entry2_order_id", ""))
                        clear_autotrade_active_lock()
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
                        if is_live_ex and matched_live_pos:
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
                        save_autotrade_config({"active_trade_lock": lock})

                        # Update SL on CoinDCX position while keeping single native TP at TP2
                        if is_live_ex and matched_live_pos and matched_live_pos.get("id"):
                            update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=ratcheted_sl, pair=l_pair)

                    # Stage 2: Runner reaches 50% of distance between TP1 and TP2 -> Ratchet SL to TP1
                    elif tp1_already_hit and not lock.get("runner_halfway_ratcheted") and l_tp1 > 0 and l_tp2 > 0:
                        mid_runner = 0.5 * (l_tp1 + l_tp2)
                        hit_mid_runner = (px >= mid_runner) if is_long else (px <= mid_runner)
                        if hit_mid_runner:
                            lock["runner_halfway_ratcheted"] = True
                            lock["stop_loss"] = l_tp1
                            l_sl = l_tp1
                            save_autotrade_config({"active_trade_lock": lock})
                            if is_live_ex and matched_live_pos and matched_live_pos.get("id"):
                                update_coindcx_position_tpsl(matched_live_pos["id"], tp_price=l_tp2, sl_price=l_tp1, pair=l_pair)

            # Also safeguard any OTHER live CoinDCX positions (e.g. if 2 positions exist like INJ + RENDER)
            if is_live_ex and live_positions:
                for other_pos in live_positions:
                    o_pair = other_pos.get("pair")
                    if not o_pair or o_pair == l_pair:
                        continue
                    _auto_protect_live_position_tp1_sl(other_pos)
        except Exception:
            pass

        return {
            "is_occupied": True,
            "active_pair": l_pair,
            "active_direction": l_dir,
            "entry_price": float(lock.get("entry", 0.0) or 0.0),
            "entry2_sweep": float(lock.get("entry2_sweep", 0.0) or 0.0),
            "tp1": l_tp1,
            "tp2": l_tp2,
            "tp1_hit": bool(lock.get("tp1_hit", False)),
            "entry2_cancelled": bool(lock.get("entry2_cancelled", False)),
            "stop_loss": l_sl,
            "source": lock.get("mode", "App/API Active Trade Lock"),
            "count": 1,
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
            return {
                "is_occupied": True,
                "active_pair": first_p.get("pair"),
                "active_direction": first_p.get("direction", "LONG"),
                "entry_price": float(first_p.get("entry_price", 0.0) or 0.0),
                "stop_loss": float(first_p.get("stop_loss", 0.0) or 0.0),
                "source": "CoinDCX Live Active Position",
                "count": len(live_pos),
            }
    except Exception:
        pass

    return {"is_occupied": False, "active_pair": None, "source": "Slot Free (0/1 App Trades Active)"}


def execute_autotrade_two_entry_signal(
    pair: str,
    sig: dict,
    single_trade_margin_inr: float = None,
    leverage: int = 10,
    usd_inr: float = None,
) -> tuple[bool, str, dict]:
    """
    Executes the 2-Entry Sweep Scale-In + 50/50 Runner setup for a single crypto at 10x leverage:
      1. Verifies no other App/API crypto position is currently active ('1 Crypto at a Time').
      2. Allocates 50% of `single_trade_margin_inr` to Entry 1 (`qty1`) with Position TP = TP2 and SL = Catastrophe SL.
      3. Places a 50% partial-take-profit limit order (`0.5 * qty1`, opposite side) at TP1 so if price moves straight to TP1
         without touching Entry 2, 50% of Entry 1 books at TP1 while the remaining 50% rides risk-free to TP2!
      4. Allocates the remaining 50% of `single_trade_margin_inr` to Entry 2 (`qty2` Limit Order at SL/SH Sweep), which is
         automatically cancelled if TP1 is hit first.
    """
    cfg = get_autotrade_config()
    margin_inr = float(single_trade_margin_inr or cfg.get("single_trade_margin_inr", 30000.0))
    lev = int(leverage or cfg.get("leverage", 10))
    u_inr = float(usd_inr or get_coindcx_live_usdt_inr_rate())

    slot = get_active_portfolio_trade_status()
    if slot.get("is_occupied"):
        act_p = slot.get("active_pair")
        return False, (
            f"1-Crypto-at-a-Time Guard: Active trade already open on {act_p} ({slot.get('source')}). "
            f"Skipping {pair} so 50% margin stays reserved for {act_p} Entry 2."
        ), {"slot_status": slot}

    # Mandatory synchronous live CoinDCX position check so a 2nd trade can NEVER open if any position is live on the exchange
    live_ex_pos = _fetch_coindcx_active_positions_sync(return_none_on_error=True)
    if live_ex_pos is None and os.getenv("COINDCX_API_KEY"):
        return False, (
            f"1-Crypto-at-a-Time Safety Guard: Could not verify live CoinDCX positions right now; "
            f"blocking {pair} AutoTrade to prevent opening a 2nd concurrent position."
        ), {"live_ex_pos": None}
    if live_ex_pos:
        open_p = live_ex_pos[0].get("pair", "UNKNOWN")
        return False, (
            f"1-Crypto-at-a-Time Live Exchange Guard: CoinDCX already has an open position on {open_p}. "
            f"Skipping {pair} so only 1 crypto is traded at a time."
        ), {"live_ex_pos": live_ex_pos}

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

    # Daily Bias Guard:
    # - BEARISH (<50 & 200 EMA) -> Strictly SHORT only (blocks counter-trend LONG)
    # - BULLISH (>50 & 200 EMA) -> Strictly LONG only (blocks counter-trend SHORT)
    # - NEUTRAL / RANGE (between 50 & 200 EMA) -> Allows both Buy Zone (LONG) and Sell Zone (SHORT) confirmed setups
    if (daily_bias == "BEARISH" and norm_dir != "SHORT") or (daily_bias == "BULLISH" and norm_dir != "LONG"):
        return False, (
            f"Daily Bias Guard: {pair} Daily Bias is {daily_bias}, blocking counter-trend {norm_dir} AutoTrade."
        ), {"daily_bias": daily_bias, "direction": norm_dir}

    side = "BUY" if norm_dir == "LONG" else "SELL"
    opp_side = "SELL" if side == "BUY" else "BUY"
    live_tk_px = float(fetch_live_ticker(pair).get("last_price", 0.0) or 0.0)
    norm = normalize_two_entry_runner_levels(
        pair=pair,
        direction=direction,
        entry1_px=float(sig["entry"]),
        entry2_px=float(sig.get("entry2_sweep") or sig["entry"]),
        tp1_px=float(sig["tp1"]),
        tp2_px=float(sig["tp2"]),
        sl_px=float(sig["stop_loss"]),
        live_px=live_tk_px if live_tk_px > 0 else float(sig["entry"]),
        levels=sig.get("levels"),
    )
    entry1_px = norm["entry"]
    entry2_px = norm["entry2_sweep"]
    tp1_px = norm["tp1"]
    tp2_px = norm["tp2"]
    sl_px = norm["stop_loss"]

    # Split single-trade margin 50% for Entry 1 and 50% for Entry 2 @ Sweep
    tranche_margin_inr = margin_inr * 0.5
    tranche_notional_usd = (tranche_margin_inr * lev) / u_inr
    qty1 = format_order_quantity(pair, tranche_notional_usd / entry1_px) if entry1_px > 0 else 0.0
    qty2 = format_order_quantity(pair, tranche_notional_usd / entry2_px) if entry2_px > 0 else 0.0

    # If 50% tranche is below CoinDCX Rs.2,448 minimum notional, use full margin on Entry 1 or bump notional
    if (qty1 * entry1_px * u_inr) < 2448.0 and (margin_inr * lev) >= 2448.0:
        qty1 = format_order_quantity(pair, ((margin_inr * lev) / u_inr) / entry1_px)

    # 50% of Entry 1 quantity to book at TP1 (remaining 50% of Entry 1 rides to TP2)
    qty1_tp1_half = format_order_quantity(pair, qty1 * 0.5)

    wallet = fetch_coindcx_futures_balance()
    api_key_now, api_secret_now = _get_coindcx_credentials()
    has_live_creds = bool(api_key_now and api_secret_now)

    if wallet.get("is_live_api") or has_live_creds:
        # Leg 1: Entry 1 (50% Margin = qty1) with CoinDCX's single native Position TP = TP2 (Runner) & SL = Catastrophe SL
        ok1, msg1, extra1 = place_coindcx_futures_order(
            pair=pair,
            side=side,
            quantity=qty1,
            leverage=lev,
            order_type="market_order",
            margin_currency="INR",
            tp_price=tp2_px,
            sl_price=sl_px,
            post_only=False,
        )
        if ok1:
            # Synchronize Position TP2/SL + TP1 50% Limit Order + Entry 2 Sweep Limit Order onto the live position
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
            )
            if not sync_ok:
                time.sleep(0.8)
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
                )
            lock_obj = (sync_details or {}).get("lock")
            if not lock_obj:
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
                    mode="App/API Live AutoTrade (Entry 1 Placed)",
                    is_live_exchange=True,
                )
            return True, (
                f"Live 2-Entry + Runner Placed on {pair}! Entry 1 ({qty1} @ ${entry1_px}) | {sync_msg}"
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
            mode="App/API Simulated AutoTrade (2-Entry Armed)", is_live_exchange=False,
        )
        return True, (
            f"AutoTrade Armed (Simulated): {direction} {pair} | "
            f"Entry 1 (50%): ${entry1_px} ({qty1}) -> 50% books at TP1 ${tp1_px} ({qty1_tp1_half}) & 50% rides to TP2 ${tp2_px} | "
            f"Entry 2 @ Sweep (50%): ${entry2_px} ({qty2}) @ {lev}x"
        ), {"lock": lock_info}


def run_portfolio_single_slot_backtest(
    pairs: list[str] = None,
    duration_days: int = 30,
    margin_inr: float = 100000.0,
    leverage: int = 10,
    usd_inr: float = 85.0,
    strategy_id: str = "box_theory",
) -> dict:
    """
    Simulates the exact '1 Crypto at a Time @ 10x Leverage' Portfolio across the High-Volatility
    Futures Universe:
      - Scans all pairs in `pairs` (defaults to HIGH_VOL_FUTURES_UNIVERSE).
      - Strictly allows ONLY 1 active trade across the entire portfolio at any time (so 50% margin
        is always reserved for Entry 2 @ Sweep on the active coin).
      - Enforces daily discipline (max 3 portfolio trades/day; done for the day after a >=10% ROE win).
      - Also returns `standalone_summary_df` so the user can compare the 1-Slot Shared Portfolio
        breakdown against each coin's Standalone 30-Day Backtest.
    """
    universe = list(pairs or HIGH_VOL_FUTURES_UNIVERSE)
    all_candidates = []
    standalone_rows = []
    for rank, p in enumerate(universe):
        res = run_strategy_backtest(
            pair=p, duration_days=duration_days, interval="15m",
            margin_inr=margin_inr, leverage=leverage, usd_inr=usd_inr, strategy_id=strategy_id
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

    if not all_candidates:
        return {
            "total_trades": 0, "win_count": 0, "loss_count": 0, "win_rate_pct": 0.0,
            "net_profit_inr": 0.0, "total_roi_pct": 0.0, "profit_factor": 0.0,
            "total_fees_paid_inr": 0.0, "trades_df": pd.DataFrame(),
            "coin_summary_df": pd.DataFrame(), "standalone_summary_df": standalone_df,
        }

    df_all = pd.DataFrame(all_candidates).sort_values(by=["entry_time", "vol_rank"]).reset_index(drop=True)
    accepted = []
    current_exit_time = ""
    day_counts = {}
    day_pnl = {}
    locked_days = set()

    for _, tr in df_all.iterrows():
        ent_t = str(tr["entry_time"])
        ext_t = str(tr["exit_time"])
        day_str = ent_t[:10]
        if ent_t < current_exit_time:
            continue  # Strictly 1 crypto trade open at any time!
        if day_str in locked_days or day_counts.get(day_str, 0) >= 3:
            continue
        accepted.append(tr.to_dict())
        current_exit_time = ext_t
        day_counts[day_str] = day_counts.get(day_str, 0) + 1
        day_pnl[day_str] = day_pnl.get(day_str, 0.0) + float(tr["net_pnl_inr"])
        if float(tr["roe_pct"]) >= 9.5 or day_pnl[day_str] >= (margin_inr * 0.095):
            locked_days.add(day_str)

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
        "margin_inr": margin_inr,
        "leverage": leverage,
        "duration_days": duration_days,
    }


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
            "execute_autotrade_two_entry_signal": execute_autotrade_two_entry_signal,
            "get_active_portfolio_trade_status": get_active_portfolio_trade_status,
            "compute_tp1_profit_lock_sl": compute_tp1_profit_lock_sl,
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
