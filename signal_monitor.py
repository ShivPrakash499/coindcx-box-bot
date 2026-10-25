"""
Signal monitor: scans the watchlist for zone-reversal / tower-continuation confirmations on the last
CLOSED 15m candle and e-mails each NEW signal once. Used by the app (while it is open) and by
signal_scanner.py (standalone terminal loop). It never places orders.
"""
from __future__ import annotations

import json
import os
import time

import coindcx_engine as eng
import email_notifier

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "alert_state.json")
DEFAULT_WATCHLIST = ["B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT"]
COOLDOWN_MIN = 60   # per pair + direction, on top of once-per-candle de-duplication


def _load() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f)


def scan_pair(pair: str, margin_inr: float, leverage: int, usd_inr: float):
    levels = eng.calculate_daily_box_levels(pair)
    if not levels:
        return None
    return eng.evaluate_tri_session_signal(pair, levels, margin_inr, leverage, usd_inr, trigger_alert=False)


def scan_and_alert(pairs, margin_inr: float, leverage: int, usd_inr: float, send: bool = True) -> list:
    """Returns one dict per pair: {pair, signal(dict|None), emailed(bool), message}."""
    state = _load()
    results = []
    for pair in pairs:
        try:
            sig = scan_pair(pair, margin_inr, leverage, usd_inr)
        except Exception as e:
            results.append({"pair": pair, "signal": None, "emailed": False, "message": f"scan error: {e}"})
            continue
        if not sig or sig["signal"] == "NEUTRAL":
            results.append({"pair": pair, "signal": sig, "emailed": False, "message": "no signal"})
            continue

        key = f"{pair}|{sig['signal_kind']}|{sig['signal']}"
        last = state.get(key, {})
        is_new_candle = last.get("candle_ts") != sig["candle_ts"]
        cooled = (time.time() - last.get("sent_at", 0)) >= COOLDOWN_MIN * 60
        emailed, msg = False, "already alerted for this candle" if not is_new_candle else "on cooldown"
        if send and is_new_candle and cooled:
            note = ("Rejection confirmed on the last closed 15m candle." if sig["signal_kind"] == "REVERSAL"
                    else "Solid tower candle closed beyond the boundary (continuation idea - untested).")
            emailed, msg = email_notifier.send_trade_email(
                pair=pair, direction=sig["signal"], entry=sig["entry"], stop_loss=sig["stop_loss"],
                tp1=sig["tp1"], tp2=sig["tp2"], margin_inr=sig["margin_inr"], leverage=sig["leverage"],
                zone=sig["trigger_zone"], kind="SIGNAL", note=note)
            if emailed:
                state[key] = {"candle_ts": sig["candle_ts"], "sent_at": time.time()}
                _save(state)
        results.append({"pair": pair, "signal": sig, "emailed": emailed, "message": msg})
    return results
