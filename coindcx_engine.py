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

def fetch_live_ticker(pair="B-ETH_USDT"):
    """
    Fetches real-time market price, 24h high/low, and 24h price change.
    Tries Binance 24hr ticker first for low latency, then falls back to CoinDCX.
    """
    clean_pair = pair.replace("B-", "").replace("I-", "").replace("_", "")
    now_str = datetime.now(IST).strftime("%H:%M:%S IST")

    # 1. Binance 24hr Ticker
    try:
        url = f"https://api.binance.com/api/v3/ticker/24hr?symbol={clean_pair}"
        r = requests.get(url, timeout=4)
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
                "source": "Binance Public Feed",
                "timestamp": now_str,
                "status": "LIVE"
            }
    except Exception as e:
        print(f"[Live Ticker Binance Notice]: {e}. Trying CoinDCX ticker...")

    # 2. CoinDCX Public Ticker Fallback
    try:
        url = "https://api.coindcx.com/exchange/ticker"
        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            items = r.json()
            for item in items:
                market = item.get("market", "")
                if market == clean_pair or market == pair:
                    raw_p = float(item.get("last_price", 0))
                    high_p = float(item.get("high", raw_p))
                    low_p = float(item.get("low", raw_p))
                    chg = float(item.get("change_24_hour", 0))
                    vol = float(item.get("volume", 0))
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
    try:
        url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={clean_pair}"
        r = requests.get(url, timeout=4).json()
        if "lastFundingRate" in r:
            raw_rate = float(r.get("lastFundingRate", 0.0))
            pct_rate = raw_rate * 100.0
            next_time_ms = int(r.get("nextFundingTime", 0))
            
            # Compute countdown
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
    except Exception as e:
        print(f"[Funding Rate Fetch Error]: {e}")

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

def _send_coindcx_signed_request(method, url, payload=None, timeout=6):
    """
    Helper to execute signed CoinDCX REST API requests with HMAC-SHA256 authentication.
    Handles timestamp formatting and secret sanitation.
    """
    api_key = os.getenv("COINDCX_API_KEY", "").strip()
    api_secret = os.getenv("COINDCX_API_SECRET", "").strip()

    if not api_key or not api_secret or api_secret == "your_coindcx_secret_key_here":
        return None, "API credentials not configured in .env"

    try:
        body = payload.copy() if payload else {}
        # CoinDCX Futures endpoints accept and expect standard epoch seconds
        if "timestamp" not in body:
            body["timestamp"] = int(time.time())

        json_body = json.dumps(body, separators=(',', ':'))
        signature = hmac.new(api_secret.encode('utf-8'), json_body.encode('utf-8'), hashlib.sha256).hexdigest()

        headers = {
            'Content-Type': 'application/json',
            'X-AUTH-APIKEY': api_key,
            'X-AUTH-SIGNATURE': signature
        }

        if method.upper() == "GET":
            res = requests.get(url, data=json_body, headers=headers, timeout=timeout)
        else:
            res = requests.post(url, data=json_body, headers=headers, timeout=timeout)

        # If timestamp validation fails with seconds (e.g. legacy endpoint), retry with milliseconds
        if res.status_code == 400 and "timestamp" in res.text.lower():
            body["timestamp"] = int(round(time.time() * 1000))
            json_body = json.dumps(body, separators=(',', ':'))
            signature = hmac.new(api_secret.encode('utf-8'), json_body.encode('utf-8'), hashlib.sha256).hexdigest()
            headers['X-AUTH-SIGNATURE'] = signature
            if method.upper() == "GET":
                res = requests.get(url, data=json_body, headers=headers, timeout=timeout)
            else:
                res = requests.post(url, data=json_body, headers=headers, timeout=timeout)

        return res, None
    except Exception as e:
        return None, str(e)

_LIVE_USDT_INR_CACHE = {"rate": 102.0, "timestamp": 0.0}

def get_coindcx_live_usdt_inr_rate() -> float:
    """
    Fetches the live USDT/INR spot rate directly from CoinDCX ticker (/exchange/ticker).
    Caches the rate for 60 seconds to avoid spamming the public ticker endpoint.
    Falls back gracefully to USD_INR_RATE from .env (or 102.0).
    """
    now = time.time()
    if now - _LIVE_USDT_INR_CACHE["timestamp"] < 60.0:
        return _LIVE_USDT_INR_CACHE["rate"]

    try:
        resp = requests.get("https://api.coindcx.com/exchange/ticker", timeout=5)
        if resp.status_code == 200:
            for item in resp.json():
                if item.get("market") == "USDTINR":
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

def fetch_coindcx_futures_balance():
    """
    Fetches real-time futures wallet balance directly from CoinDCX Futures API.
    Combines USDT Futures Wallet, INR Wallet, locked margin, and calculates total INR equivalent.
    Falls back gracefully to TOTAL_WALLET_INR from .env if credentials are not configured.
    """
    usd_inr = get_coindcx_live_usdt_inr_rate()
    default_balance = float(os.getenv("TOTAL_WALLET_INR", 250000))

    api_key = os.getenv("COINDCX_API_KEY", "").strip()
    api_secret = os.getenv("COINDCX_API_SECRET", "").strip()

    if not api_key or not api_secret or api_secret == "your_coindcx_secret_key_here":
        return {
            "total_inr": default_balance,
            "available_inr": default_balance,
            "inr_cash": default_balance,
            "locked_inr": 0.0,
            "usdt_cash": 0.0,
            "locked_margin_usd": 0.0,
            "cross_user_margin_usd": 0.0,
            "is_live_api": False,
            "source": "Configured in .env (Waiting for API Secret)"
        }

    usdt_balance = 0.0
    inr_balance = 0.0
    locked_inr = 0.0
    locked_margin_usd = 0.0
    cross_margin_usd = 0.0
    is_live = False

    # 1. Primary: CoinDCX Futures Wallet Endpoint (/exchange/v1/derivatives/futures/wallets)
    res_fut, err_fut = _send_coindcx_signed_request("GET", "https://api.coindcx.com/exchange/v1/derivatives/futures/wallets")
    if res_fut and res_fut.status_code == 200:
        try:
            wallets = res_fut.json()
            if isinstance(wallets, list):
                for w in wallets:
                    curr = w.get("currency_short_name", "").upper()
                    bal = float(w.get("balance", 0.0) or 0.0)
                    locked = float(w.get("locked_balance", 0.0) or 0.0)
                    cross = float(w.get("cross_user_margin", 0.0) or 0.0)
                    if curr == "USDT":
                        usdt_balance += bal
                        locked_margin_usd += locked
                        cross_margin_usd += cross
                    elif curr == "INR":
                        inr_balance += bal
                        locked_inr += locked
                is_live = True
        except Exception as e:
            print(f"[Futures Wallet Parse Error]: {e}")

    # 2. Secondary / Fallback: CoinDCX Spot & General Balances (/exchange/v1/users/balances)
    if not is_live or (usdt_balance == 0.0 and inr_balance == 0.0):
        res_spot, err_spot = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/users/balances")
        if res_spot and res_spot.status_code == 200:
            try:
                balances = res_spot.json()
                if isinstance(balances, list):
                    for item in balances:
                        curr = item.get("currency", "").upper()
                        bal = float(item.get("balance", 0.0) or 0.0)
                        if curr == "INR":
                            inr_balance = max(inr_balance, bal)
                        elif curr == "USDT":
                            usdt_balance = max(usdt_balance, bal)
                    is_live = True
            except Exception as e:
                print(f"[Spot Balance Parse Error]: {e}")

    if is_live:
        total_inr = inr_balance + locked_inr + (usdt_balance * usd_inr)
        avail_usdt = max(0.0, usdt_balance - locked_margin_usd - cross_margin_usd)
        avail_inr = inr_balance + (avail_usdt * usd_inr)
        return {
            "total_inr": round(total_inr, 2),
            "available_inr": round(avail_inr, 2),
            "inr_cash": round(inr_balance, 2),
            "locked_inr": round(locked_inr, 2),
            "usdt_cash": round(usdt_balance, 4),
            "available_usdt": round(avail_usdt, 4),
            "locked_margin_usd": round(locked_margin_usd, 4),
            "cross_user_margin_usd": round(cross_margin_usd, 4),
            "live_usd_inr": usd_inr,
            "is_live_api": True,
            "source": "CoinDCX Live Futures API"
        }

    return {
        "total_inr": default_balance,
        "available_inr": default_balance,
        "inr_cash": default_balance,
        "locked_inr": 0.0,
        "usdt_cash": 0.0,
        "locked_margin_usd": 0.0,
        "cross_user_margin_usd": 0.0,
        "is_live_api": False,
        "source": "Configured in .env (API Response Offline)"
    }

def fetch_coindcx_active_positions():
    """
    Fetches real-time active open trades/positions from CoinDCX Futures API.
    Filters positions where active_pos != 0 and computes live PnL and ROE metrics
    using real-time market mark prices and CoinDCX's exact settlement currency
    conversion price (settlement_currency_avg_price).
    """
    live_usdt_inr = get_coindcx_live_usdt_inr_rate()
    payload = {
        "page": "1",
        "size": "20",
        "margin_currency_short_name": ["USDT", "INR"]
    }

    res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions", payload)
    if not res or res.status_code != 200:
        return []

    active_positions = []
    try:
        data = res.json()
        if isinstance(data, list):
            # Fast batch fetch live market prices to guarantee real-time PnL & ROE accuracy
            live_prices = {}
            try:
                r_bin = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=2.5)
                if r_bin.status_code == 200:
                    for it in r_bin.json():
                        live_prices[it["symbol"]] = float(it["price"])
            except Exception:
                pass

            if not live_prices:
                try:
                    r_dcx = requests.get("https://public.coindcx.com/exchange/ticker", timeout=2.5)
                    if r_dcx.status_code == 200:
                        for it in r_dcx.json():
                            live_prices[it.get("market", "")] = float(it.get("last_price", 0.0) or 0.0)
                except Exception:
                    pass

            for item in data:
                active_pos_qty = float(item.get("active_pos", 0.0) or 0.0)
                if abs(active_pos_qty) > 0:
                    pair = item.get("pair", "")
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
                        # Fallback to single pair live ticker
                        try:
                            t_single = fetch_live_ticker(pair)
                            live_p = float(t_single.get("last_price", 0.0) or 0.0)
                        except Exception:
                            pass

                    # If live market price obtained, use it; otherwise fall back to exchange snapshot mark_price
                    raw_mark = float(item.get("mark_price", 0.0) or 0.0)
                    mark_price = live_p if live_p > 0 else raw_mark

                    # Exact CoinDCX settlement conversion rate for this position
                    settlement_rate = float(item.get("settlement_currency_avg_price", 0.0) or 0.0)
                    if settlement_rate <= 0:
                        settlement_rate = live_usdt_inr

                    # Margin currency and locked margin
                    margin_currency = item.get("margin_currency_short_name", "INR").upper()
                    raw_locked_margin = float(item.get("locked_margin", 0.0) or 0.0)

                    # In CoinDCX INR-margined futures:
                    # raw_locked_margin is in USDT; multiplying by settlement_rate yields the exact INR margin (e.g. 511.106 * 102 = ₹52,132.83)
                    if margin_currency == "INR":
                        locked_margin_inr = raw_locked_margin * settlement_rate
                        locked_margin_usd = raw_locked_margin
                    else:
                        locked_margin_usd = raw_locked_margin
                        locked_margin_inr = locked_margin_usd * settlement_rate

                    qty = abs(active_pos_qty)
                    notional_usd = mark_price * qty
                    notional_inr = notional_usd * settlement_rate

                    # Calculate live real-time PnL and ROE matching CoinDCX calculation exactly
                    if mark_price > 0 and entry_price > 0:
                        price_diff = (mark_price - entry_price) if direction == "LONG" else (entry_price - mark_price)
                        pnl_usd = price_diff * qty
                        pnl_inr = pnl_usd * settlement_rate
                        # Exact CoinDCX ROE formula: PnL (INR) / Locked Margin (INR)
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

    return active_positions

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

def exit_coindcx_position(position_id: str) -> tuple[bool, str]:
    """
    Market exits a specific open futures position on CoinDCX by position ID.
    Calls POST /exchange/v1/derivatives/futures/positions/exit.
    """
    if not position_id:
        return False, "Invalid position ID"

    payload = {"id": str(position_id).strip(), "timestamp": int(round(time.time() * 1000))}
    res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/exit", payload)
    if res is not None and res.status_code == 200:
        return True, f"Successfully executed market exit for position {position_id}"
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
    return success_count, len(positions), f"Closed {success_count}/{len(positions)} active positions and cancelled all pending orders."

def update_coindcx_position_tpsl(position_id: str, tp_price: float = None, sl_price: float = None, pair: str = None) -> tuple[bool, str]:
    """
    Attaches or updates Take Profit and Stop Loss bracket triggers directly on an active position.
    Cancels any existing TP or SL orders for this pair first to prevent 'TP already exists' errors.
    Calls POST /exchange/v1/derivatives/futures/positions/create_tpsl.
    """
    if not position_id:
        return False, "Missing position ID"

    # Step 1: Pre-cancel existing TP/SL triggers for this pair if open
    try:
        open_orders = fetch_coindcx_open_orders()
        for o in open_orders:
            o_pair = o.get("pair")
            o_stage = o.get("stage")
            o_type = o.get("order_type", "")
            o_id = o.get("id")
            if o_id and (not pair or o_pair == pair) and o_stage == "tpsl_exit":
                if tp_price is not None and "take_profit" in o_type:
                    _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel", {"id": o_id, "timestamp": int(round(time.time() * 1000))})
                if sl_price is not None and "stop" in o_type:
                    _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/orders/cancel", {"id": o_id, "timestamp": int(round(time.time() * 1000))})
    except Exception as e:
        print(f"[TP/SL Pre-Cancel Notice]: {e}")

    # Step 2: Create new TP/SL triggers
    payload = {
        "timestamp": int(round(time.time() * 1000)),
        "id": str(position_id).strip()
    }
    if tp_price is not None and tp_price > 0:
        payload["take_profit"] = {
            "stop_price": str(tp_price),
            "order_type": "take_profit_market"
        }
    if sl_price is not None and sl_price > 0:
        payload["stop_loss"] = {
            "stop_price": str(sl_price),
            "order_type": "stop_market"
        }

    res, err = _send_coindcx_signed_request("POST", "https://api.coindcx.com/exchange/v1/derivatives/futures/positions/create_tpsl", payload)
    if res is not None and res.status_code == 200:
        return True, "Take Profit and Stop Loss successfully updated on CoinDCX!"

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
    sl_price: float = None
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
    ref_p = float(price) if (price and price > 0) else 0.0
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
        order_payload["price"] = float(price)
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
        data = res.json()
        order_info = data[0] if (isinstance(data, list) and len(data) > 0) else (data if isinstance(data, dict) else {})
        order_id = order_info.get("id", "CONFIRMED")

        # If TP or SL specified, attach them once order is registered
        if tp_price or sl_price:
            time.sleep(1.0)
            try:
                positions = fetch_coindcx_active_positions()
                matched_pos = next((p for p in positions if p["pair"] == pair), None)
                if matched_pos and matched_pos.get("id"):
                    update_coindcx_position_tpsl(matched_pos["id"], tp_price=tp_price, sl_price=sl_price, pair=pair)
            except Exception as e:
                print(f"[Auto TP/SL Notice]: {e}")

        return True, f"Successfully placed {order_side.upper()} order for {formatted_qty} {pair} on CoinDCX! (Order ID: {order_id})", {
            "order_id": order_id,
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
    Fetches historical candlestick data for any timeframe (1m, 5m, 15m, 1h, 4h, 1d)
    from CoinDCX / Binance public APIs. Guarantees ascending order and syncs with live price.
    """
    df = pd.DataFrame()
    intv = interval.lower()

    # 1. Try CoinDCX Public API
    url = f"https://public.coindcx.com/market_data/candles?pair={pair}&interval={intv}&limit={limit}"
    try:
        response = requests.get(url, timeout=8)
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
        print(f"[CoinDCX Candles Notice]: {e}. Attempting Binance fallback...")

    # 2. Fallback to Binance Public API
    if df.empty:
        try:
            clean_pair = pair.replace("B-", "").replace("I-", "").replace("_", "")
            url_binance = f"https://api.binance.com/api/v3/klines?symbol={clean_pair}&interval={intv}&limit={limit}"
            r = requests.get(url_binance, timeout=8).json()
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
        except Exception as e:
            print(f"[Binance Fallback Error]: {e}")

    # 3. Synchronize the active (last) candle's close with the real-time ticker
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

def calculate_daily_box_levels(pair="B-ETH_USDT"):
    """
    Calculates Previous Day High (RH), Low (RL), Swing High (SH), Swing Low (SL),
    and Equilibrium Midpoint (MID) using completed daily candles.
    """
    df_daily = fetch_coindcx_candles(pair=pair, interval="1d", limit=30, sync_live_price=False)
    if df_daily.empty or len(df_daily) < 2:
        return None

    # Completed yesterday candle is iloc[-2]
    prev_day = df_daily.iloc[-2]
    rh = float(prev_day['high'])
    rl = float(prev_day['low'])
    mid = (rh + rl) / 2.0

    # Look back over last 15-28 days for swing peaks/troughs beyond RH/RL
    historical_highs = df_daily['high'].iloc[:-2].tolist()
    historical_lows = df_daily['low'].iloc[:-2].tolist()

    sh_candidates = [h for h in historical_highs if h > rh]
    sh = min(sh_candidates) if sh_candidates else rh * 1.015

    sl_candidates = [l for l in historical_lows if l < rl]
    sl = max(sl_candidates) if sl_candidates else rl * 0.985

    return {
        "RH": round_asset_price(rh),
        "RL": round_asset_price(rl),
        "SH": round_asset_price(sh, rh),
        "SL": round_asset_price(sl, rl),
        "MID": round_asset_price(mid, rh),
        "prev_day_date": datetime.fromtimestamp(prev_day['timestamp'] / 1000, tz=IST).strftime("%Y-%m-%d")
    }

def calculate_trade_setup_details(direction="BUY", levels=None, live_price=0.0, margin_inr=100000, leverage=5, usd_inr=85.0, pair="B-ETH_USDT"):
    """
    Calculates specific BUY (Long at Range Low) or SELL (Short at Range High)
    trade setup parameters including targets, stops, and financial projections.
    Quantizes order quantity to the pair's exchange lot size rules.
    """
    if not levels:
        return None

    rh, rl = levels["RH"], levels["RL"]
    sh, sl = levels["SH"], levels["SL"]
    mid = levels["MID"]

    if direction.upper() in ["BUY", "LONG"]:
        dir_name = "BUY"
        entry = round_asset_price(live_price if live_price > 0 and live_price <= rl else rl, rh)
        stop_loss = round_asset_price(min(rl, sl) * 0.998, rh)
        tp1 = mid
        tp2 = rh
        setup_desc = "BUY (Long): Liquidity Sweep Rejection at Range Low (RL)"
    else:
        dir_name = "SELL"
        entry = round_asset_price(live_price if live_price > 0 and live_price >= rh else rh, rh)
        stop_loss = round_asset_price(max(rh, sh) * 1.002, rh)
        tp1 = mid
        tp2 = rl
        setup_desc = "SELL (Short): Liquidity Sweep Rejection at Range High (RH)"

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

    return {
        "direction": dir_name,
        "setup": setup_desc,
        "entry": entry,
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
        "roe_sl": roe_sl,
        "profit_tp1_inr": profit_tp1_inr,
        "profit_tp2_inr": profit_tp2_inr,
        "loss_sl_inr": loss_sl_inr,
        "target_roe_met": roe_tp1 >= 5.0
    }

def evaluate_tri_session_signal(pair="B-ETH_USDT", levels=None, margin_inr=100000, leverage=5, usd_inr=85.0, trigger_alert: bool = True):
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

    df_15m = fetch_coindcx_candles(pair=pair, interval="15m", limit=30, sync_live_price=True)
    if df_15m.empty:
        return None

    df_15m['ist_dt'] = pd.to_datetime(df_15m['timestamp'], unit='ms').dt.tz_localize('UTC').dt.tz_convert(IST)
    now_ist = datetime.now(IST)
    session = get_current_session_info(now_ist)

    today_date = now_ist.date()

    # Determine whether we are evaluating an institutional session candle or latest active bar
    target_candle_df = df_15m[
        (df_15m['ist_dt'].dt.date == today_date) & 
        (
            ((df_15m['ist_dt'].dt.hour == 7) & (df_15m['ist_dt'].dt.minute >= 15) & (df_15m['ist_dt'].dt.minute <= 45)) |
            ((df_15m['ist_dt'].dt.hour == 13) & (df_15m['ist_dt'].dt.minute >= 15) & (df_15m['ist_dt'].dt.minute <= 45)) |
            ((df_15m['ist_dt'].dt.hour == 19) & (df_15m['ist_dt'].dt.minute == 0))
        )
    ]

    is_prime_session_candle = False
    if not target_candle_df.empty and session["is_prime"]:
        eval_candle = target_candle_df.iloc[-1]
        candle_time_str = eval_candle['ist_dt'].strftime('%H:%M IST')
        candle_label = f"{session['emoji']} {session['name']} Candle ({candle_time_str})"
        is_prime_session_candle = True
    else:
        eval_candle = df_15m.iloc[-1]
        candle_time_str = eval_candle['ist_dt'].strftime('%H:%M IST')
        candle_label = f"Latest Candle ({candle_time_str}) [{session['emoji']} {session['name']}]"

    close_price = float(eval_candle['close'])
    high_price = float(eval_candle['high'])
    low_price = float(eval_candle['low'])

    rh, rl = levels["RH"], levels["RL"]
    sh, sl = levels["SH"], levels["SL"]
    mid = levels["MID"]

    setup = "WAIT / NO TRADE (Price oscillating within Equilibrium)"
    entry = close_price
    stop_loss = 0.0
    tp1 = mid
    tp2 = rl
    signal_type = "NEUTRAL"

    # Top Liquidity Sweep: Swept RH/SH and closed back below RH
    if high_price >= rh and close_price < rh:
        signal_type = "SHORT"
        setup = f"SELL (Short): Liquidity Sweep Rejection at Range High ({session['name']})"
        stop_loss = round_asset_price(max(high_price, sh) * 1.002, rh)
        tp1 = mid
        tp2 = rl

    # Bottom Liquidity Sweep: Swept RL/SL and closed back above RL
    elif low_price <= rl and close_price > rl:
        signal_type = "LONG"
        setup = f"BUY (Long): Liquidity Sweep Rejection at Range Low ({session['name']})"
        stop_loss = round_asset_price(min(low_price, sl) * 0.998, rh)
        tp1 = mid
        tp2 = rh

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
        "levels": levels
    }

def evaluate_715_pm_signal(pair="B-ETH_USDT", levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
    """
    Backwards compatibility alias for evaluate_tri_session_signal.
    """
    return evaluate_tri_session_signal(pair, levels, margin_inr, leverage, usd_inr)

