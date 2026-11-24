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
POST_SL_LOCK_MIN = 240     # 4h unified cross-strategy lock on (pair, direction) after any SL hit
MAX_DAILY_ALERTS_PER_PAIR = 3
MAX_DAILY_PORTFOLIO_TRADES = 999
MAX_CONCURRENT_PORTFOLIO_TRADES = int(getattr(eng, "MAX_CONCURRENT_TRADES", 3) or 3)  # 3-slot wallet
_STATE_SCHEMA_VERSION = 3
_SCAN_LOCK = sys.__dict__.setdefault("_signal_monitor_scan_lock", threading.Lock())
_LAST_SCAN_CACHE = sys.__dict__.setdefault("_signal_monitor_last_scan", {"ts": 0.0, "results": []})


_MEM_STATE = sys.__dict__.setdefault("_signal_monitor_state_mem", {"_schema_version": _STATE_SCHEMA_VERSION})


def _canon_pair(p: str) -> str:
    """Normalizes any CoinDCX/Binance pair string ('B-INJ_USDT', 'INJUSDT', 'I-INJ_INR') to its base symbol ('INJ')."""
    if not p:
        return ""
    s = str(p).upper().strip()
    for pref in ("B-", "I-"):
        if s.startswith(pref):
            s = s[len(pref):]
    for suf in ("_USDT", "USDT", "_INR", "INR"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[:-len(suf)]
            break
    return s.replace("_", "").replace("-", "")


def _load() -> dict:
    merged = dict(_MEM_STATE)
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                merged.update(data)
    except Exception:
        pass
    merged["_schema_version"] = _STATE_SCHEMA_VERSION
    _MEM_STATE.update(merged)
    return merged


def _save(state: dict) -> None:
    state["_schema_version"] = _STATE_SCHEMA_VERSION
    _MEM_STATE.update(state)
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


def enabled_strategy_ids() -> list:
    """Returns strategy IDs for the active AutoTrade / Scanner mode, optionally overridden by ENABLED_STRATEGIES."""
    env = os.getenv("ENABLED_STRATEGIES", "").strip()
    all_ids = [s.id for s in strat_registry.list_strategies()]
    if env:
        wanted = [x.strip() for x in env.split(",") if x.strip()]
        matched = [i for i in all_ids if i in wanted]
        if matched:
            return matched
    auto_cfg = eng.get_autotrade_config()
    auto_mode = strat_registry.resolve_autotrade_mode(auto_cfg.get("autotrade_strategy_mode"))
    return strat_registry.autotrade_mode_strategy_ids(auto_mode)


def _autotrade_signal_eligible(strategy_id: str, direction: str, auto_mode: str, levels: dict | None = None) -> bool:
    """Checks whether a confirmed signal satisfies the Sidebar AutoTrade Strategy selection."""
    m = strat_registry.resolve_autotrade_mode(auto_mode)
    d = str(direction or "").upper()
    if m == "box_theory":
        return strategy_id == "box_theory"
    if m == "ema50_200":
        return strategy_id == "ema50_200"
    if m == "box_plus_ema50_200_bear":
        return (strategy_id == "box_theory") or (strategy_id == "ema50_200" and d == "SHORT")
    if m == "box_plus_ema50_200_both":
        return strategy_id in ("box_theory", "ema50_200")
    if m == "box_plus_ema50_200_regime":
        reg = str(eng.compute_market_regime().get("regime", "RANGING_CHOP"))
        if strategy_id == "box_theory":
            # Row 9 (v40): Box Sweep runs strictly in RANGING_CHOP (paused in Strong Trends)
            if reg != "RANGING_CHOP":
                return False
            # Row 9 No-Bear-Long Guard: block Box LONG when coin's prior Daily Close <= Daily 50 EMA
            if d == "LONG" and isinstance(levels, dict):
                dc = float(levels.get("daily_close", 0.0) or 0.0)
                de50 = float(levels.get("EMA50", 0.0) or 0.0)
                if dc > 0 and de50 > 0 and dc <= de50:
                    return False
            return True
        if strategy_id == "ema50_200":
            return (reg == "STRONG_DOWNTREND" and d == "SHORT") or (reg == "STRONG_UPTREND" and d == "LONG")
        return False
    return strategy_id == strat_registry.DEFAULT_STRATEGY_ID


def scan_pair(pair: str, margin_inr: float, leverage: int, usd_inr: float, strategy_id: str = "box_theory"):
    s = strat_registry.get_strategy(strategy_id)
    levels = s.compute_levels(pair)
    if not levels:
        return None
    return s.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)


def _state_key(strategy_id: str, pair: str, sig: dict) -> str:
    base = f"{pair}|{sig['signal_kind']}|{sig['signal']}"
    return base if strategy_id == strat_registry.DEFAULT_STRATEGY_ID else f"{strategy_id}|{base}"


def record_post_sl_lock(pair: str, direction: str, reason: str = "SL Hit") -> None:
    """
    Records a 4-hour unified cross-strategy lock on `(pair_base, direction)` whenever any trade
    stops out (Live or Staging Paper). Prevents Box Theory and 15m 50/200 EMA from immediately
    re-entering the exact same losing direction on a coin that just hit SL.
    """
    pair_base = _canon_pair(pair)
    if not pair_base:
        return
    norm_dir = "LONG" if str(direction or "").upper() in ("LONG", "BUY") else "SHORT"
    state = _load()
    state[f"POST_SL_LOCK|{pair_base}|{norm_dir}"] = {
        "locked_at": time.time(),
        "pair": pair,
        "direction": norm_dir,
        "reason": str(reason or "SL Hit"),
    }
    _save(state)


def is_post_sl_locked(pair: str, direction: str, state: dict | None = None) -> tuple[bool, float]:
    """Returns `(is_locked, remaining_minutes)` for a `(pair, direction)` post-SL cooldown."""
    pair_base = _canon_pair(pair)
    if not pair_base:
        return False, 0.0
    norm_dir = "LONG" if str(direction or "").upper() in ("LONG", "BUY") else "SHORT"
    st = state if isinstance(state, dict) else _load()
    rec = st.get(f"POST_SL_LOCK|{pair_base}|{norm_dir}")
    if not isinstance(rec, dict):
        return False, 0.0
    elapsed = time.time() - float(rec.get("locked_at", 0.0) or 0.0)
    limit_sec = POST_SL_LOCK_MIN * 60.0
    if 0.0 <= elapsed < limit_sec:
        return True, round((limit_sec - elapsed) / 60.0, 1)
    return False, 0.0


def _note(strategy_id: str, sig: dict) -> str:
    e1 = sig.get("entry", 0.0)
    e2 = float(sig.get("entry2_sweep", 0.0) or 0.0)
    tp1 = sig.get("tp1", 0.0)
    tp2 = sig.get("tp2", 0.0)
    if e2 > 0:
        return (
            f"2-Entry + Runner Plan: Enter 50% (Tranche 1) at ${e1:,.2f} and place an equal 50% Limit Order (Tranche 2) "
            f"at the Sweep Level (${e2:,.2f}). Book 50% early profit at TP1 (${tp1:,.2f}) & lock SL in profit; "
            f"hold the remaining 50% Runner to TP2 (${tp2:,.2f})!"
        )
    return (
        f"100% Single-Slot Maker Limit + Structural Runner Plan: Place 100% Slot Maker Limit Order at ${e1:,.2f}. "
        f"Book 50% early profit at TP1 (${tp1:,.2f}) & lock SL in profit; "
        f"ratchet SL to TP1 halfway to TP2 and hold the remaining 50% Runner to TP2 (${tp2:,.2f})!"
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
    if hasattr(eng, "_check_and_kill_obsolete_daemon"):
        eng._check_and_kill_obsolete_daemon()
    auto_cfg = eng.get_autotrade_config()
    auto_mode = strat_registry.resolve_autotrade_mode(auto_cfg.get("autotrade_strategy_mode"))
    if margin_inr is None or margin_inr <= 0:
        margin_inr = float(auto_cfg.get("single_trade_margin_inr", 100000.0))
    if leverage is None or leverage <= 0:
        leverage = int(auto_cfg.get("leverage", 10))
    if autotrade is None:
        if eng.is_experiment_environment():
            autotrade = False
        elif eng.is_staging_environment():
            autotrade = bool(auto_cfg.get("paper_autotrade_enabled", True))
        else:
            autotrade = bool(auto_cfg.get("enabled", False))
    # Always honor saved `email_alerts_enabled` setting (defaults to False on staging & Experiment so neither duplicates main emails)
    _non_live_env = eng.is_staging_environment() or eng.is_experiment_environment()
    email_cfg_enabled = bool(auto_cfg.get("email_alerts_enabled", False if _non_live_env else True))
    send = bool(send) and email_cfg_enabled

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

        eff_max_slots = int(eng.get_configured_max_slots(auto_cfg) if hasattr(eng, "get_configured_max_slots") else MAX_CONCURRENT_PORTFOLIO_TRADES)

        # Collect all pairs currently in a Live CoinDCX position, resting Entry Limit order, or active App Trade Lock
        # (normalized by base symbol via `_canon_pair` so `B-INJ_USDT` == `I-INJ_INR` == `INJUSDT`)
        open_live_pairs = set()
        open_live_bases = set()
        for _ap in (slot_status.get("active_pairs") or ([active_Slot_pair] if active_Slot_pair else [])):
            if _ap:
                open_live_pairs.add(_ap)
                open_live_bases.add(_canon_pair(_ap))
        if len(open_live_bases) >= eff_max_slots:
            portfolio_occupied = True
            if not active_Slot_pair:
                active_Slot_pair = next(iter(open_live_pairs), None)

        live_pos_verified = False
        live_pos_list = []
        try:
            if is_daemon_thread or send:
                # Whenever `send=True` (email alerts enabled), ALWAYS perform a synchronous live check
                # (`return_none_on_error=True`) so a cold cache or transient HTTP 401 can NEVER send emails
                # while a live trade is actually open on CoinDCX!
                live_pos_list = eng._fetch_coindcx_active_positions_sync(return_none_on_error=True)
                if live_pos_list is not None:
                    live_pos_verified = True
                else:
                    # Fallback to cached positions if available; if still unverified, fail-closed on email sending
                    live_pos_list = eng._ACTIVE_POSITIONS_CACHE.get("data") or []
            else:
                live_pos_list = eng.fetch_coindcx_active_positions() or []
                live_pos_verified = True

            for pos in (live_pos_list or []):
                if isinstance(pos, dict) and pos.get("pair"):
                    p_raw = pos["pair"]
                    open_live_pairs.add(p_raw)
                    open_live_bases.add(_canon_pair(p_raw))
                    if len(open_live_bases) >= eff_max_slots:
                        portfolio_occupied = True
                        active_Slot_pair = p_raw

            # Also count unfilled resting Entry Limit Orders on CoinDCX toward the slot cap
            if (is_daemon_thread or autotrade) and hasattr(eng, "get_open_entry_limit_orders"):
                _w_chk = eng.fetch_coindcx_futures_balance(force_refresh=False) or {}
                if _w_chk.get("is_live_api"):
                    for _eo in (eng.get_open_entry_limit_orders(live_positions=live_pos_list, cfg=auto_cfg) or []):
                        _ep_pair = _eo.get("pair")
                        if _ep_pair:
                            open_live_pairs.add(_ep_pair)
                            open_live_bases.add(_canon_pair(_ep_pair))
                            if len(open_live_bases) >= eff_max_slots:
                                portfolio_occupied = True
                                active_Slot_pair = _ep_pair
        except Exception:
            pass

        # Live & Staging-Paper 5% Daily Loss Stop + Unrealized PnL Daily SL Pause:
        #   - Realized daily loss >= 5% -> lock AutoTrade for the IST day.
        #   - Open unrealized loss >= 5% Daily SL -> pause new trades until open live positions close!
        daily_stop_hit, daily_stop_msg = False, ""
        if autotrade and not eng.is_experiment_environment():
            try:
                _dl_w = eng.get_paper_wallet_snapshot(auto_cfg) if eng.is_staging_environment() else None
                daily_stop_hit, daily_stop_msg, _ = eng.check_live_daily_loss_stop(_dl_w)
                if not daily_stop_hit and hasattr(eng, "check_unrealized_pnl_daily_sl_pause"):
                    _unr_pos_arg = None if eng.is_staging_environment() else live_pos_list
                    _unr_hit, _unr_msg, _ = eng.check_unrealized_pnl_daily_sl_pause(
                        _dl_w, positions=_unr_pos_arg, allow_live_ticker=True
                    )
                    if _unr_hit:
                        daily_stop_hit, daily_stop_msg = True, _unr_msg
            except Exception as e:
                print(f"[Daily Loss Stop Check Notice]: {e}")

        for pair in pairs:
            if is_daemon_thread:
                time.sleep(0.03)  # Yield GIL so Streamlit Tornado serves static JS assets immediately
            pair_base = _canon_pair(pair)
            pair_lock_key = f"PAIR_LOCK|{pair}"
            pair_last = state.get(pair_lock_key, {})
            email_daily_key = f"EMAIL_COUNT|{pair}|{today_ist}"
            email_daily_count = int(state.get(email_daily_key, 0))

            pair_primary_triggered = False
            for sid in strategy_ids:
                if sid in ("ema9_retest", "ema50_200") and pair_primary_triggered:
                    continue  # Fallback / continuation strategies only run when Box / primary yielded no setup on this pair
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
                if sid in ("box_theory", "atr_reversal"):
                    pair_primary_triggered = True

                if auto_mode == "box_plus_ema50_200_regime" and s.id in ("box_theory", "ema50_200"):
                    if not _autotrade_signal_eligible(s.id, sig.get("signal"), auto_mode, levels=sig.get("levels")):
                        reg_info_sm = eng.compute_market_regime()
                        reg_lbl = reg_info_sm.get("label", "RANGING / CHOP")
                        if s.id == "box_theory" and reg_info_sm.get("regime") == "RANGING_CHOP" and str(sig.get("signal", "")).upper() == "LONG":
                            _p_msg = "blocked by Row-9 No-Bear-Long Guard (Prev Daily Close <= Daily 50 EMA)"
                        else:
                            _p_msg = f"paused by Regime-Adaptive v40 mode ({reg_lbl})"
                        results.append({**row, "signal": None, "message": _p_msg})
                        continue

                if float(sig.get("roe_tp1", 0.0)) < 3.0:
                    results.append({**row, "message": f"skipped: TP ROE ({sig.get('roe_tp1')}%) < 3% minimum"})
                    continue

                # Skip sending duplicate setup alerts or opening trades on assets ALREADY in a Live Trade
                if pair in open_live_pairs or (pair_base and pair_base in open_live_bases):
                    results.append({
                        **row,
                        "message": f"skipped: {pair} is already in an active Live Trade"
                    })
                    continue

                # 1-Crypto-at-a-Time Guard: If any crypto is already active, do not alert/open another crypto
                if portfolio_occupied and active_Slot_pair and _canon_pair(active_Slot_pair) != pair_base:
                    results.append({
                        **row,
                        "message": f"3-slot portfolio guard: {active_Slot_pair} is currently occupying max slots"
                    })
                    continue

                # Fail-Closed Email Guard: If CoinDCX API could not verify live positions on this tick, suppress email alerts
                if send and not live_pos_verified and os.getenv("COINDCX_API_KEY"):
                    results.append({
                        **row,
                        "message": "skipped email: waiting for CoinDCX live position verification"
                    })
                    continue

                key = _state_key(s.id, pair, sig)
                last = state.get(key, {})
                now_ts = time.time()
                norm_sig_dir = "LONG" if str(sig.get("signal", "")).upper() in ("LONG", "BUY") else "SHORT"

                # Unified Cross-Strategy Post-SL 4h Lock: if ANY strategy hit SL on (pair, direction) within 4h, block ALL strategies!
                post_sl_lk, post_sl_rem = is_post_sl_locked(pair, norm_sig_dir, state=state)
                if post_sl_lk:
                    results.append({
                        **row,
                        "message": f"post-SL 4h cross-strategy lock active on {pair_base} {norm_sig_dir} ({post_sl_rem:.0f}m left)"
                    })
                    continue

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

                # Unified Cross-Strategy Re-Entry Lock on (pair_base, direction):
                # Blocks Box <-> EMA flip-flop re-entries on the same breaking coin for 4h (1h only if previous trade won TP1).
                cross_key = f"CROSS_STRAT_LOCK|{pair_base}|{norm_sig_dir}"
                cross_last = state.get(cross_key, {}) if isinstance(state.get(cross_key), dict) else {}
                cross_at = float(cross_last.get("autotraded_at", 0.0) or 0.0)
                _cross_prev_tp1_won = any(
                    isinstance(_h, dict)
                    and _canon_pair(_h.get("pair", "")) == pair_base
                    and str(_h.get("direction", "")).upper() == norm_sig_dir
                    and bool(_h.get("tp1_hit", False))
                    and float(_h.get("opened_ts", 0.0) or 0.0) >= (cross_at - 15.0)
                    for _h in (auto_cfg.get("history") or [])[:15]
                )
                _cross_lock_sec = (COOLDOWN_MIN * 60) if _cross_prev_tp1_won else (SAME_SETUP_LOCK_MIN * 60)
                cross_strat_locked = cross_at > 0 and ((now_ts - cross_at) < _cross_lock_sec)

                if not is_new_candle:
                    msg = "already alerted for this candle"
                elif same_setup_locked:
                    msg = "already alerted for this setup zone"
                elif cross_strat_locked:
                    msg = f"cross-strategy 4h lock on {pair_base} {norm_sig_dir}"
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
                _prev_hist_tp1_won = any(
                    isinstance(_h, dict)
                    and _h.get("pair") == pair
                    and bool(_h.get("tp1_hit", False))
                    and float(_h.get("opened_ts", 0.0) or 0.0) >= (last_autotraded_at - 15.0)
                    for _h in (auto_cfg.get("history") or [])[:15]
                )
                _zone_lock_sec = (COOLDOWN_MIN * 60) if _prev_hist_tp1_won else (SAME_SETUP_LOCK_MIN * 60)
                already_autotraded_setup = (
                    (
                        bool(last.get("autotraded", False))
                        and same_price_zone
                        and ((now_ts - last_autotraded_at) < _zone_lock_sec)
                    )
                    or cross_strat_locked
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
                if autotrade and daily_stop_hit:
                    autotrade_error = daily_stop_msg
                    msg = f"{msg} | 🛑 {daily_stop_msg}"
                elif (
                    autotrade
                    and _autotrade_signal_eligible(str(sig.get("strategy_id") or s.id), sig.get("signal"), auto_mode)
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
                        open_live_pairs.add(pair)
                        open_live_bases.add(pair_base)
                        if len(open_live_bases) >= eff_max_slots:
                            portfolio_occupied = True
                            active_Slot_pair = pair
                        state[key] = {
                            "candle_ts": sig["candle_ts"],
                            "sent_at": state.get(key, {}).get("sent_at", now_exec),
                            "direction": sig["signal"],
                            "entry": cur_entry,
                            "tp1": float(sig.get("tp1", 0.0) or 0.0),
                            "autotraded": True,
                            "autotraded_at": now_exec,
                        }
                        state[cross_key] = {
                            "autotraded_at": now_exec,
                            "strategy_id": s.id,
                            "entry": cur_entry,
                            "direction": norm_sig_dir,
                            "pair": pair,
                        }
                        autotrade_daily_count += 1
                        state[autotrade_daily_key] = autotrade_daily_count
                        _save(state)
                        # Only send an EXECUTED email if `send` (24/7 Email Alerts) is ON and we did NOT already send a SIGNAL email on this tick!
                        if send and not emailed:
                            emailed, _ = email_notifier.send_trade_email(
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


def scan_manual_intraday_signals(
    pairs: list[str],
    margin_inr: float = 10000.0,
    leverage: int = 10,
    usd_inr: float = 85.0,
) -> list[dict]:
    """
    Read-only manual trading scanner powered by `exp-staging-intraday-score-router`:
    Evaluates every watchlist coin with per-coin intraday score (-4..+4) + ADX(14) + Daily risk weighting
    (`1.0x / 0.8x / 0.6x` & `70%` Counter-Daily TP1) and tags whether each setup also passes strict v41
    AutoTrade eligibility. Never places automated orders.
    """
    auto_cfg = eng.get_autotrade_config()
    auto_mode = strat_registry.resolve_autotrade_mode(auto_cfg.get("autotrade_strategy_mode"))
    out = []
    for pair in (pairs or []):
        try:
            info = strat_registry.evaluate_manual_intraday_setup(
                pair=pair,
                margin_inr=float(margin_inr or 10000.0),
                leverage=int(leverage or 10),
                usd_inr=float(usd_inr or 85.0),
            )
            lsig = info.get("live_signal")
            strict_ok = False
            if isinstance(lsig, dict) and lsig.get("signal") in ("LONG", "SHORT"):
                d_b = str(info.get("daily_bias") or "NEUTRAL").upper()
                d_dir = str(lsig["signal"]).upper()
                bias_ok = not ((d_b == "BEARISH" and d_dir != "SHORT") or (d_b == "BULLISH" and d_dir != "LONG"))
                strict_ok = bool(
                    bias_ok
                    and _autotrade_signal_eligible(
                        str(lsig.get("strategy_id") or "box_theory"),
                        d_dir,
                        auto_mode,
                        levels=info.get("levels"),
                    )
                )
            info["strict_v41_autotrade_eligible"] = strict_ok
            out.append(info)
        except Exception as e:
            out.append({"pair": pair, "error": str(e), "policy": {}, "live_signal": None, "prefill_ticket": None, "strict_v41_autotrade_eligible": False})
    return out
