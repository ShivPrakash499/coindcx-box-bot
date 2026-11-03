"""
Signal monitor: scans the watchlist with EVERY registered strategy (see strategies.py) on the last
CLOSED candle and e-mails each NEW signal once, tagged with the strategy name. Used by the app
(while it is open, plus its 24/7 background thread) and by signal_scanner.py (standalone loop).
It never places orders unless AutoTrade is explicitly enabled.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time

from datetime import datetime

import coindcx_engine as eng
import email_notifier
import strategies as strat_registry

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".cache", "alert_state.json")
DEFAULT_WATCHLIST = list(eng.HIGH_VOL_FUTURES_UNIVERSE)
COOLDOWN_MIN = 60          # per strategy + pair + direction, plus pair-level anti-spam guard
SAME_SETUP_LOCK_MIN = 240  # 4h deduplication lock for the same setup / price zone in the same direction
MAX_DAILY_ALERTS_PER_PAIR = 3
MAX_DAILY_PORTFOLIO_TRADES = 6
_STATE_SCHEMA_VERSION = 3
_SCAN_LOCK = sys.__dict__.setdefault("_signal_monitor_scan_lock", threading.Lock())
_LAST_SCAN_CACHE = sys.__dict__.setdefault("_signal_monitor_last_scan", {"ts": 0.0, "results": []})


def _load() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                if data.get("_schema_version") != _STATE_SCHEMA_VERSION:
                    fresh = {"_schema_version": _STATE_SCHEMA_VERSION}
                    _save(fresh)
                    return fresh
                return data
    except Exception:
        pass
    return {"_schema_version": _STATE_SCHEMA_VERSION}


def _save(state: dict) -> None:
    state["_schema_version"] = _STATE_SCHEMA_VERSION
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
    e1 = sig.get("entry", 0.0)
    e2 = sig.get("entry2_sweep", 0.0)
    tp1 = sig.get("tp1", 0.0)
    tp2 = sig.get("tp2", 0.0)
    return (
        f"2-Entry + Runner Plan: Enter 50% (Tranche 1) at ${e1:,.2f} and place an equal 50% Limit Order (Tranche 2) "
        f"at the Sweep Level (${e2:,.2f}). Book 50% early profit at TP1 (${tp1:,.2f}) & move SL to Breakeven; "
        f"hold the remaining 50% risk-free Runner to TP2 (${tp2:,.2f}) to capture the big drop/move!"
    )


def scan_and_alert(pairs=None, margin_inr: float = None, leverage: int = 10, usd_inr: float = 85.0,
                   send: bool = True, strategy_ids=None, autotrade: bool = None) -> list:
    """
    Scans high-volatility crypto futures pairs (ordered by live 24h volatility) at 10x leverage:
      1. Suppresses alerts and trades for any asset ALREADY in an active Live CoinDCX trade (`open_live_pairs`).
      2. Enforces '1 Crypto at a Time' so 50% of the single-trade margin is always reserved for Entry 2 @ Sweep.
      3. Sends email alert for the highest-priority confirmed signal when the portfolio slot is free.
      4. When AutoTrade is toggled ON in the Sidebar, automatically executes the 2-Entry + Runner setup
         using the user's configured Single-Trade Margin out of the Futures Wallet.
    """
    auto_cfg = eng.get_autotrade_config()
    if margin_inr is None or margin_inr <= 0:
        margin_inr = float(auto_cfg.get("single_trade_margin_inr", 100000.0))
    if leverage is None or leverage <= 0:
        leverage = int(auto_cfg.get("leverage", 10))
    if autotrade is None:
        autotrade = bool(auto_cfg.get("enabled", False))

    if not pairs:
        pairs = eng.get_high_volatility_watchlist(top_n=12)
    else:
        # Rank user-supplied pairs by live 24h volatility so highest-volatility movers get first priority
        vol_order = {m["pair"]: idx for idx, m in enumerate(eng.fetch_top_volatility_movers(pairs, top_n=len(pairs)))}
        pairs = sorted(list(pairs), key=lambda p: vol_order.get(p, 999))

    strategy_ids = strategy_ids or enabled_strategy_ids()
    today_ist = datetime.now(eng.IST).strftime("%Y-%m-%d")
    is_daemon_thread = threading.current_thread().name.startswith("CryptoTradeAssistantDaemon")

    # Fast-path for UI threads: if _SCAN_LOCK is busy or last scan was < 50s ago, return cached results in 0ms!
    if not is_daemon_thread and _LAST_SCAN_CACHE.get("results"):
        cache_age = time.time() - float(_LAST_SCAN_CACHE.get("ts", 0.0))
        if cache_age < 50.0 or _SCAN_LOCK.locked():
            return list(_LAST_SCAN_CACHE["results"])

    with _SCAN_LOCK:
        state = _load()
        results = []
        slot_status = eng.get_active_portfolio_trade_status(manage_exchange=is_daemon_thread)
        portfolio_occupied = bool(slot_status.get("is_occupied", False))
        active_Slot_pair = slot_status.get("active_pair")
        autotrade_daily_key = f"AUTOTRADE_DAILY_COUNT|{today_ist}"
        autotrade_daily_count = int(state.get(autotrade_daily_key, 0))

        # Collect all pairs currently in a Live CoinDCX position or active App Trade Lock
        open_live_pairs = set()
        if portfolio_occupied and active_Slot_pair:
            open_live_pairs.add(active_Slot_pair)
        try:
            for pos in (eng.fetch_coindcx_active_positions() or []):
                if isinstance(pos, dict) and pos.get("pair"):
                    open_live_pairs.add(pos["pair"])
        except Exception:
            pass

        for pair in pairs:
            pair_lock_key = f"PAIR_LOCK|{pair}"
            pair_last = state.get(pair_lock_key, {})
            email_daily_key = f"EMAIL_COUNT|{pair}|{today_ist}"
            email_daily_count = int(state.get(email_daily_key, 0))

            for sid in strategy_ids:
                s = strat_registry.get_strategy(sid)
                row = {
                    "pair": pair, "strategy_id": s.id, "strategy_name": s.name,
                    "signal": None, "emailed": False, "autotraded": False, "autotrade_error": ""
                }
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

                # Skip sending duplicate setup alerts or opening trades on assets ALREADY in a Live Trade
                if pair in open_live_pairs:
                    results.append({
                        **row,
                        "message": f"skipped: {pair} is already in an active Live Trade"
                    })
                    continue

                # 1-Crypto-at-a-Time Guard: If another crypto is already active, do not alert/open a 2nd crypto
                if portfolio_occupied and active_Slot_pair and active_Slot_pair != pair:
                    results.append({
                        **row,
                        "message": f"1-crypto-at-a-time guard: {active_Slot_pair} is currently active (50% reserved for Entry 2)"
                    })
                    continue

                key = _state_key(s.id, pair, sig)
                last = state.get(key, {})
                now_ts = time.time()
                is_new_candle = last.get("candle_ts") != sig["candle_ts"]
                cooled = (now_ts - last.get("sent_at", 0)) >= COOLDOWN_MIN * 60
                pair_cooled = (now_ts - pair_last.get("sent_at", 0)) >= COOLDOWN_MIN * 60

                # Same-setup deduplication: if same direction & entry within 0.8%, suppress duplicate email for 4 hours
                last_entry = float(last.get("entry", 0.0) or 0.0)
                cur_entry = float(sig.get("entry", 0.0) or 0.0)
                same_price_zone = (
                    last.get("direction") == sig["signal"]
                    and last_entry > 0
                    and cur_entry > 0
                    and (abs(cur_entry - last_entry) / cur_entry) < 0.008
                )
                same_setup_locked = same_price_zone and ((now_ts - last.get("sent_at", 0)) < SAME_SETUP_LOCK_MIN * 60)

                if not is_new_candle:
                    msg = "already alerted for this candle"
                elif same_setup_locked:
                    msg = "already alerted for this setup zone"
                elif not (cooled and pair_cooled):
                    msg = "on cooldown"
                else:
                    msg = "ready"

                emailed = False
                autotraded = False
                autotrade_error = ""
                already_autotraded_candle = (
                    last.get("candle_ts") == sig["candle_ts"] and bool(last.get("autotraded", False))
                )
                last_autotraded_at = float(last.get("autotraded_at", 0.0) or 0.0)
                already_autotraded_setup = (
                    bool(last.get("autotraded", False))
                    and same_price_zone
                    and ((now_ts - last_autotraded_at) < COOLDOWN_MIN * 60)
                )

                if (
                    send
                    and is_new_candle
                    and cooled
                    and pair_cooled
                    and not same_setup_locked
                    and email_daily_count < MAX_DAILY_ALERTS_PER_PAIR
                ):
                    emailed, msg = email_notifier.send_trade_email(
                        pair=pair, direction=sig["signal"], entry=sig["entry"], stop_loss=sig["stop_loss"],
                        tp1=sig["tp1"], tp2=sig["tp2"], margin_inr=sig["margin_inr"], leverage=sig["leverage"],
                        zone=sig.get("trigger_zone") or "", kind="SIGNAL", note=_note(s.id, sig),
                        strategy_name=s.name, strategy_id=s.id, trigger_reason=sig.get("trigger_reason", ""),
                        levels=sig.get("levels"), entry2_sweep=sig.get("entry2_sweep", 0.0))
                    if emailed:
                        now_sent = time.time()
                        state[key] = {
                            "candle_ts": sig["candle_ts"],
                            "sent_at": now_sent,
                            "direction": sig["signal"],
                            "entry": cur_entry,
                            "tp1": float(sig.get("tp1", 0.0) or 0.0),
                            "autotraded": already_autotraded_candle,
                            "autotraded_at": last_autotraded_at,
                        }
                        pair_last = {
                            "candle_ts": sig["candle_ts"],
                            "sent_at": now_sent,
                            "direction": sig["signal"],
                            "entry": cur_entry,
                            "strategy_id": s.id,
                        }
                        state[pair_lock_key] = pair_last
                        email_daily_count += 1
                        state[email_daily_key] = email_daily_count
                        _save(state)

                # If AutoTrade is toggled ON in Sidebar and no other coin is active, place the 2-Entry + Runner trade!
                # Even if a SIGNAL email was already sent earlier while AutoTrade was OFF, execute immediately
                # as long as this confirmed signal has not already been autotraded!
                if (
                    autotrade
                    and not portfolio_occupied
                    and not already_autotraded_candle
                    and not already_autotraded_setup
                    and autotrade_daily_count < MAX_DAILY_PORTFOLIO_TRADES
                ):
                    ok_auto, auto_msg, _ = eng.execute_autotrade_two_entry_signal(
                        pair=pair, sig=sig, single_trade_margin_inr=margin_inr, leverage=leverage, usd_inr=usd_inr
                    )
                    autotraded = ok_auto
                    msg = f"{msg} | 🤖 {auto_msg}"
                    now_exec = time.time()
                    if ok_auto:
                        portfolio_occupied = True
                        active_Slot_pair = pair
                        open_live_pairs.add(pair)
                        state[key] = {
                            "candle_ts": sig["candle_ts"],
                            "sent_at": state.get(key, {}).get("sent_at", now_exec),
                            "direction": sig["signal"],
                            "entry": cur_entry,
                            "tp1": float(sig.get("tp1", 0.0) or 0.0),
                            "autotraded": True,
                            "autotraded_at": now_exec,
                        }
                        autotrade_daily_count += 1
                        state[autotrade_daily_key] = autotrade_daily_count
                        _save(state)
                        email_notifier.send_trade_email(
                            pair=pair, direction=sig["signal"], entry=sig["entry"], stop_loss=sig["stop_loss"],
                            tp1=sig["tp1"], tp2=sig["tp2"], margin_inr=margin_inr, leverage=leverage,
                            zone=sig.get("trigger_zone") or "", kind="EXECUTED", note=auto_msg,
                            strategy_name=s.name, strategy_id=s.id, trigger_reason=sig.get("trigger_reason", ""),
                            levels=sig.get("levels"), entry2_sweep=sig.get("entry2_sweep", 0.0)
                        )
                    else:
                        autotrade_error = auto_msg
                results.append({**row, "emailed": emailed, "autotraded": autotraded, "autotrade_error": autotrade_error, "message": msg})
        _LAST_SCAN_CACHE["results"] = list(results)
        _LAST_SCAN_CACHE["ts"] = time.time()
        return results
