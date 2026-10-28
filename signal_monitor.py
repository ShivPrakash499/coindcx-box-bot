"""
Signal monitor: scans the watchlist with EVERY registered strategy (see strategies.py) on the last
CLOSED candle and e-mails each NEW signal once, tagged with the strategy name. Used by the app
(while it is open, plus its 24/7 background thread) and by signal_scanner.py (standalone loop).
It never places orders.
"""
from __future__ import annotations

import json
import os
import threading
import time

from datetime import datetime

import coindcx_engine as eng
import email_notifier
import strategies as strat_registry

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "alert_state.json")
DEFAULT_WATCHLIST = ["B-SOL_USDT", "B-ETH_USDT", "B-BTC_USDT"]
COOLDOWN_MIN = 60   # per strategy + pair + direction, plus pair-level anti-spam guard
MAX_DAILY_ALERTS_PER_PAIR = 2
_SCAN_LOCK = threading.Lock()


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


def enabled_strategy_ids() -> list:
    """All registered strategies, optionally narrowed by ENABLED_STRATEGIES=box_theory,atr_reversal."""
    env = os.getenv("ENABLED_STRATEGIES", "").strip()
    ids = [s.id for s in strat_registry.list_strategies()]
    if env:
        wanted = [x.strip() for x in env.split(",") if x.strip()]
        ids = [i for i in ids if i in wanted] or ids
    return ids


def scan_pair(pair: str, margin_inr: float, leverage: int, usd_inr: float, strategy_id: str = "box_theory"):
    s = strat_registry.get_strategy(strategy_id)
    levels = s.compute_levels(pair)
    if not levels:
        return None
    return s.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)


def _state_key(strategy_id: str, pair: str, sig: dict) -> str:
    base = f"{pair}|{sig['signal_kind']}|{sig['signal']}"
    return base if strategy_id == strat_registry.DEFAULT_STRATEGY_ID else f"{strategy_id}|{base}"


def _note(strategy_id: str, sig: dict) -> str:
    if strategy_id == "box_theory":
        return (
            "Daily 50/200 EMA trend-aligned rejection confirmed. "
            "Single Complete Exit TP = min(20% ROE, MID) | Strict SL = min(5% ROE, Sweep SL). "
            "Max 2 trades/day — if this trade hits >=10% ROE, you are done for the day."
        )
    return (
        "Daily 50/200 EMA trend-aligned 5m crossover confirmed. "
        "Single Complete Exit TP = min(20% ROE, 50% Retrace) | Strict SL = min(5% ROE, Extreme SL). "
        "Max 2 trades/day — if this trade hits >=10% ROE, you are done for the day."
    )


def scan_and_alert(pairs=None, margin_inr: float = 100000.0, leverage: int = 5, usd_inr: float = 85.0,
                   send: bool = True, strategy_ids=None) -> list:
    """Returns one dict per (strategy, pair): {pair, strategy_id, strategy_name, signal(dict|None), emailed, message}."""
    pairs = pairs or DEFAULT_WATCHLIST
    strategy_ids = strategy_ids or enabled_strategy_ids()
    today_ist = datetime.now(eng.IST).strftime("%Y-%m-%d")
    with _SCAN_LOCK:
        state = _load()
        results = []
        for pair in pairs:
            pair_lock_key = f"PAIR_LOCK|{pair}"
            pair_last = state.get(pair_lock_key, {})
            daily_count_key = f"DAILY_COUNT|{pair}|{today_ist}"
            daily_count = int(state.get(daily_count_key, 0))

            for sid in strategy_ids:
                s = strat_registry.get_strategy(sid)
                row = {"pair": pair, "strategy_id": s.id, "strategy_name": s.name, "signal": None, "emailed": False}
                try:
                    sig = scan_pair(pair, margin_inr, leverage, usd_inr, s.id)
                except Exception as e:
                    results.append({**row, "message": f"scan error: {e}"})
                    continue
                row["signal"] = sig
                if not sig or sig["signal"] == "NEUTRAL":
                    results.append({**row, "message": "no signal"})
                    continue

                if float(sig.get("roe_tp1", 0.0)) < 3.0:
                    results.append({**row, "message": f"skipped: TP ROE ({sig.get('roe_tp1')}%) < 3% minimum"})
                    continue

                if daily_count >= MAX_DAILY_ALERTS_PER_PAIR:
                    results.append({**row, "message": f"daily limit reached ({daily_count}/{MAX_DAILY_ALERTS_PER_PAIR} today)"})
                    continue

                key = _state_key(s.id, pair, sig)
                last = state.get(key, {})
                now_ts = time.time()
                is_new_candle = last.get("candle_ts") != sig["candle_ts"]
                cooled = (now_ts - last.get("sent_at", 0)) >= COOLDOWN_MIN * 60
                pair_cooled = (now_ts - pair_last.get("sent_at", 0)) >= COOLDOWN_MIN * 60

                if not is_new_candle:
                    msg = "already alerted for this candle"
                elif not (cooled and pair_cooled):
                    msg = "on cooldown"
                else:
                    msg = "ready"

                emailed = False
                if send and is_new_candle and cooled and pair_cooled:
                    emailed, msg = email_notifier.send_trade_email(
                        pair=pair, direction=sig["signal"], entry=sig["entry"], stop_loss=sig["stop_loss"],
                        tp1=sig["tp1"], tp2=sig["tp2"], margin_inr=sig["margin_inr"], leverage=sig["leverage"],
                        zone=sig.get("trigger_zone") or "", kind="SIGNAL", note=_note(s.id, sig),
                        strategy_name=s.name, strategy_id=s.id, trigger_reason=sig.get("trigger_reason", ""),
                        levels=sig.get("levels"))
                    if emailed:
                        now_sent = time.time()
                        state[key] = {"candle_ts": sig["candle_ts"], "sent_at": now_sent, "direction": sig["signal"]}
                        pair_last = {"candle_ts": sig["candle_ts"], "sent_at": now_sent, "direction": sig["signal"], "strategy_id": s.id}
                        state[pair_lock_key] = pair_last
                        daily_count += 1
                        state[daily_count_key] = daily_count
                        _save(state)
                results.append({**row, "emailed": emailed, "message": msg})
        return results
