"""
Pre-merge & post-merge automated verification suite (`test_smoke.py`) for Crypto Trade Pro.
Run this on `staging` before merging and on `main` after merging:
    .venv\\Scripts\\python.exe test_smoke.py
    .venv\\Scripts\\python.exe test_smoke.py --live
"""
from __future__ import annotations

import ast
import base64
import os
import py_compile
import re
import socket
import ssl
import struct
import sys
import tempfile
import time
from unittest.mock import patch

sys.stdout.reconfigure(encoding="utf-8")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

CORE_MODULES = [
    "app.py",
    "coindcx_engine.py",
    "signal_monitor.py",
    "strategies.py",
    "sheets_logger.py",
    "email_notifier.py",
    "gemini_advisor.py",
]


class _MockResponse:
    def __init__(self, status_code: int, json_data):
        self.status_code = status_code
        self._json_data = json_data
        self.text = str(json_data)

    def json(self):
        return self._json_data


def test_1_syntax_and_imports():
    print("[1/10] Checking syntax & compilation across core modules...")
    for fname in CORE_MODULES:
        fpath = os.path.join(ROOT_DIR, fname)
        assert os.path.exists(fpath), f"Missing core file: {fname}"
        py_compile.compile(fpath, doraise=True)
    import coindcx_engine  # noqa: F401
    import signal_monitor  # noqa: F401
    import strategies  # noqa: F401
    import sheets_logger  # noqa: F401
    import email_notifier  # noqa: F401
    import gemini_advisor  # noqa: F401
    print("  -> PASS: All 7 core modules compiled and imported cleanly.")


def test_2_simulated_200_ok_wallet_and_positions_no_recursion():
    print("[2/10] Testing simulated 200 OK CoinDCX Wallet & Positions under strict recursion guard...")
    import coindcx_engine as eng

    def _fake_signed_request(method, url, payload=None, timeout=3.5):
        if "futures/wallets" in url:
            return _MockResponse(200, [
                {
                    "currency_short_name": "INR",
                    "balance": "36138.85",
                    "locked_balance": "11148.33",
                    "cross_user_margin": "0.0",
                }
            ]), None
        if "futures/positions" in url:
            return _MockResponse(200, [
                {
                    "id": "pos-test-near",
                    "pair": "B-NEAR_USDT",
                    "active_pos": 100.0,
                    "avg_price": 3.88,
                    "mark_price": 3.92,
                    "liquidation_price": 3.51,
                    "leverage": 10.0,
                    "settlement_currency_avg_price": 102.0,
                    "margin_currency_short_name": "INR",
                    "locked_margin": 77.26,
                    "take_profit_trigger": 4.35,
                    "stop_loss_trigger": 3.84,
                    "margin_type": "isolated",
                }
            ]), None
        return _MockResponse(200, []), None

    with tempfile.TemporaryDirectory() as tmpdir:
        temp_cfg_file = os.path.join(tmpdir, "autotrade_config.json")
        old_limit = sys.getrecursionlimit()
        try:
            sys.setrecursionlimit(120)
            with patch.object(eng, "AUTOTRADE_CONFIG_FILE", temp_cfg_file), \
                 patch.object(eng, "_get_coindcx_credentials", return_value=("smoke_test_key_123456", "smoke_test_secret_123456")), \
                 patch.object(eng, "_send_coindcx_signed_request", side_effect=_fake_signed_request):
                eng._WALLET_BALANCE_CACHE["data"] = None
                eng._WALLET_BALANCE_CACHE["ts"] = 0.0
                bal = eng._fetch_coindcx_futures_balance_sync()
                assert bal["is_live_api"] is True, f"Expected live wallet, got {bal}"
                assert abs(bal["total_inr"] - 47287.18) < 0.05, f"Unexpected total_inr: {bal['total_inr']}"

                pos = eng._fetch_coindcx_active_positions_sync()
                assert len(pos) == 1 and pos[0]["pair"] == "B-NEAR_USDT", f"Unexpected positions: {pos}"
        finally:
            sys.setrecursionlimit(old_limit)
    print(f"  -> PASS: Simulated 200 OK Wallet (Rs {bal['total_inr']:,.2f}) & Positions parsed with zero recursion.")


def test_3_ui_non_blocking_latency_gate():
    print("[3/10] Checking UI non-blocking latency gate (< 5.0 ms per call)...")
    import coindcx_engine as eng

    # Warm the in-memory caches once
    eng.fetch_coindcx_futures_balance(force_refresh=False)
    eng.fetch_coindcx_active_positions(force_refresh=False)
    eng.get_autotrade_config()
    eng.get_rotational_margin_inr()

    t0 = time.perf_counter()
    _ = eng.fetch_coindcx_futures_balance(force_refresh=False)
    t_bal_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    _ = eng.fetch_coindcx_active_positions(force_refresh=False)
    t_pos_ms = (time.perf_counter() - t1) * 1000.0

    t2 = time.perf_counter()
    _ = eng.get_autotrade_config()
    t_cfg_ms = (time.perf_counter() - t2) * 1000.0

    t3 = time.perf_counter()
    _ = eng.get_rotational_margin_inr()
    t_rot_ms = (time.perf_counter() - t3) * 1000.0

    assert t_bal_ms < 5.0, f"fetch_coindcx_futures_balance too slow: {t_bal_ms:.3f} ms"
    assert t_pos_ms < 5.0, f"fetch_coindcx_active_positions too slow: {t_pos_ms:.3f} ms"
    assert t_cfg_ms < 5.0, f"get_autotrade_config too slow: {t_cfg_ms:.3f} ms"
    assert t_rot_ms < 5.0, f"get_rotational_margin_inr too slow: {t_rot_ms:.3f} ms"
    print(
        f"  -> PASS: UI path latency: Wallet={t_bal_ms:.3f}ms | "
        f"Positions={t_pos_ms:.3f}ms | Config={t_cfg_ms:.3f}ms | Sizing={t_rot_ms:.3f}ms"
    )


def test_4_strategy_and_two_entry_levels():
    print("[4/10] Verifying 2-Entry + Runner level normalization (LONG & SHORT)...")
    import coindcx_engine as eng
    import strategies as strat

    long_lvls = eng.normalize_two_entry_runner_levels(
        pair="B-NEAR_USDT",
        direction="LONG",
        entry1_px=3.88,
        entry2_px=3.85,
        tp1_px=3.96,
        tp2_px=4.35,
        sl_px=3.82,
        live_px=3.88,
    )
    assert long_lvls["stop_loss"] < long_lvls["entry2_sweep"] < long_lvls["entry"] < long_lvls["tp1"] < long_lvls["tp2"], (
        f"Invalid LONG level ordering: {long_lvls}"
    )

    short_lvls = eng.normalize_two_entry_runner_levels(
        pair="B-XRP_USDT",
        direction="SHORT",
        entry1_px=1.26,
        entry2_px=1.27,
        tp1_px=1.24,
        tp2_px=1.21,
        sl_px=1.28,
        live_px=1.26,
    )
    assert short_lvls["tp2"] < short_lvls["tp1"] < short_lvls["entry"] < short_lvls["entry2_sweep"] < short_lvls["stop_loss"], (
        f"Invalid SHORT level ordering: {short_lvls}"
    )

    # Verify 4-decimal precision across round_asset_price and manual Execute level normalization (never rounded to 2 decimals)
    assert eng.round_asset_price(1.1674) == 1.1674, f"Expected 1.1674, got {eng.round_asset_price(1.1674)}"
    manual_4d = eng.normalize_two_entry_runner_levels(
        pair="B-INJ_USDT",
        direction="SHORT",
        entry1_px=8.3245,
        entry2_px=8.5985,
        tp1_px=8.1725,
        tp2_px=8.0315,
        sl_px=8.6415,
        live_px=8.3245,
    )
    assert manual_4d["entry"] == 8.3245 and manual_4d["tp1"] == 8.1725 and manual_4d["tp2"] == 8.0315 and manual_4d["stop_loss"] == 8.6415, (
        f"Expected 4-decimal manual Execute levels preserved without rounding off, got: {manual_4d}"
    )

    # Verify build_two_entry_runner_plan uses 100% Single Entry (entry2_sweep == 0.0) while anchoring Catastrophe SL beyond SH (> $7.43)
    inj_plan = strat.build_two_entry_runner_plan("SHORT", entry=7.30, sweep_level=7.43, struct_tp1=7.10, struct_tp2=6.89, leverage=10)
    assert inj_plan is not None
    assert inj_plan["entry2_sweep"] == 0.0, f"Expected Entry 2 removed (0.0), got {inj_plan['entry2_sweep']}"
    assert inj_plan["stop"] > 7.43, f"Expected Catastrophe SL strictly above SH $7.43, got {inj_plan['stop']}"

    # Verify _nearest_box_tp1 picks nearer of MID or 15m 50 EMA, and Strategy 2 single-entry + 5% wallet loss stop
    tp1_s_px, tp1_s_lbl = strat._nearest_box_tp1("SHORT", entry=7.30, mid=7.00, ema50_15m=7.15, fallback_edge=6.80)
    assert abs(tp1_s_px - 7.15) < 1e-6 and tp1_s_lbl == "15m 50 EMA"
    tp1_l_px, tp1_l_lbl = strat._nearest_box_tp1("LONG", entry=6.90, mid=7.10, ema50_15m=7.02, fallback_edge=7.30)
    assert abs(tp1_l_px - 7.02) < 1e-6 and tp1_l_lbl == "15m 50 EMA"
    s2_plan = strat.build_single_entry_runner_plan("LONG", entry=7.00, struct_stop=6.88, struct_tp1=7.15, struct_tp2=7.30, leverage=10)
    assert s2_plan is not None and s2_plan["entry2_sweep"] == 0.0
    assert strat.DAILY_WALLET_LOSS_STOP_PCT == 5.0
    assert "ema9_retest" in strat.STRATEGY_REGISTRY and "combined" in strat.STRATEGY_REGISTRY

    # Live <-> Backtest Box level parity: calculate_daily_box_levels() must equal prepare_backtest() for the same day
    import pandas as pd
    import random
    random.seed(7)
    n_days = 300
    px, rows = 7.0, []
    for i in range(n_days):
        o = px
        c = max(0.5, o * (1 + random.uniform(-0.05, 0.05)))
        h = max(o, c) * (1 + random.uniform(0, 0.03))
        l = min(o, c) * (1 - random.uniform(0, 0.03))
        rows.append({"timestamp": 1700000000000 + i * 86400000, "open": o, "high": h, "low": l, "close": c, "volume": 1.0})
        px = c
    d_par = pd.DataFrame(rows)
    d_par["date_str"] = pd.to_datetime(d_par["timestamp"], unit="ms").dt.tz_localize("UTC").dt.tz_convert(eng.IST).dt.strftime("%Y-%m-%d")
    ctx_par = strat.BoxTheorySweep().prepare_backtest(pd.DataFrame({"close": [1.0, 1.0]}), d_par)
    for i_day in (n_days - 20, n_days - 1):
        with patch.object(eng, "fetch_coindcx_candles", return_value=d_par.iloc[:i_day + 1].reset_index(drop=True)):
            lv_par = eng.calculate_daily_box_levels("B-INJ_USDT")
        bt_par = ctx_par["boxes"][d_par.iloc[i_day]["date_str"]]
        for k_lv in ("RH", "RL", "SH", "SL", "MID"):
            assert abs(lv_par[k_lv] - bt_par[k_lv]) < 1e-9, f"Live/backtest {k_lv} mismatch: {lv_par[k_lv]} vs {bt_par[k_lv]}"
        assert lv_par["trend_bias"] == bt_par["bias"]

    print(f"  -> PASS: LONG ({long_lvls}), SHORT ({short_lvls}) & SH/SL structural Entry2/SL + Strategy 1/2/3 rules verified.")


def test_5_daily_bias_enforcement():
    print("[5/10] Verifying Daily 50 & 200 EMA Bias rules (BEARISH->SHORT, BULLISH->LONG, RANGE->Both Box Zones)...")
    import coindcx_engine as eng
    import pandas as pd

    neutral_levels = {
        "RH": 7.31, "RL": 6.89, "SH": 7.43, "SL": 6.86, "MID": 7.10,
        "EMA50": 7.38, "EMA200": 6.09, "daily_close": 6.98, "trend_bias": "NEUTRAL"
    }

    with patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}), \
         patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]):
        bear_levels = {**neutral_levels, "EMA50": 1.73, "EMA200": 1.72, "daily_close": 1.51, "trend_bias": "BEARISH"}
        with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}):
            ok_b, msg_b, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-RENDER_USDT",
                sig={"signal": "LONG", "entry": 1.50, "entry2_sweep": 1.49, "tp1": 1.53, "tp2": 1.59, "stop_loss": 1.48, "levels": bear_levels},
                single_trade_margin_inr=15762.39,
                leverage=10,
            )
            assert not ok_b and "Intraday Trend Matrix Guard" in msg_b, f"Expected counter-trend LONG in CLEAN_DOWNTREND block, got: {ok_b} {msg_b}"

        bull_levels = {**neutral_levels, "EMA50": 85.0, "EMA200": 80.0, "daily_close": 92.0, "trend_bias": "BULLISH"}
        with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_UPTREND", "summary": "CLEAN_UPTREND"}):
            ok_u, msg_u, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-SOL_USDT",
                sig={"signal": "SHORT", "entry": 92.0, "entry2_sweep": 92.5, "tp1": 90.5, "tp2": 88.0, "stop_loss": 93.0, "levels": bull_levels},
                single_trade_margin_inr=15762.39,
                leverage=10,
            )
            assert not ok_u and "Intraday Trend Matrix Guard" in msg_u, f"Expected counter-trend SHORT in CLEAN_UPTREND block, got: {ok_u} {msg_u}"

        # CHOP / RANGE MUST block all trades under Intraday Trend Decision Matrix!
        with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CHOP_RANGE", "summary": "CHOP_RANGE"}):
            ok_r, msg_r, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-INJ_USDT",
                sig={"signal": "SHORT", "entry": 7.30, "entry2_sweep": 7.43, "tp1": 7.15, "tp2": 6.89, "stop_loss": 7.49, "levels": neutral_levels},
                single_trade_margin_inr=15762.39,
                leverage=10,
            )
            assert not ok_r and "CHOP / RANGE" in msg_r, f"Expected CHOP_RANGE blocked, got: {ok_r} {msg_r}"

    with patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}), \
         patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[
             {"pair": "B-INJ_USDT", "direction": "SHORT", "id": "pos_inj"},
             {"pair": "B-NEAR_USDT", "direction": "LONG", "id": "pos_near"},
             {"pair": "B-SUI_USDT", "direction": "LONG", "id": "pos_sui"},
         ]):
        ok_dup, msg_dup, _ = eng.execute_autotrade_two_entry_signal(
            pair="B-INJ_USDT",
            sig={"signal": "SHORT", "entry": 7.30, "entry2_sweep": 7.43, "tp1": 7.15, "tp2": 6.89, "stop_loss": 7.49, "levels": bear_levels},
            single_trade_margin_inr=20000.0,
            leverage=10,
        )
        assert not ok_dup and "Duplicate Pair Guard" in msg_dup, f"Expected duplicate pair guard, got: {ok_dup} {msg_dup}"

        ok_4th, msg_4th, _ = eng.execute_autotrade_two_entry_signal(
            pair="B-RENDER_USDT",
            sig={"signal": "SHORT", "entry": 1.51, "entry2_sweep": 1.63, "tp1": 1.48, "tp2": 1.45, "stop_loss": 1.64, "levels": bear_levels},
            single_trade_margin_inr=20000.0,
            leverage=10,
        )
        assert not ok_4th and "3-Slot Wallet Guard" in msg_4th, (
            f"Expected 4th concurrent trade blocked by 3-Slot Wallet Guard, got: {ok_4th} {msg_4th}"
        )

    base_closes = [6.0] * 250 + [7.20]
    df_low_today = pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(252)],
        "open": base_closes + [7.20],
        "high": [c + 0.15 for c in base_closes] + [7.50],
        "low": [c - 0.15 for c in base_closes] + [7.00],
        "close": base_closes + [5.50],
        "volume": [1000.0] * 252,
    })
    df_high_today = df_low_today.copy()
    df_high_today.loc[251, "close"] = 9.50

    with patch.object(eng, "fetch_coindcx_candles", return_value=df_low_today):
        lv_low = eng.calculate_daily_box_levels("B-INJ_USDT")
    with patch.object(eng, "fetch_coindcx_candles", return_value=df_high_today):
        lv_high = eng.calculate_daily_box_levels("B-INJ_USDT")

    assert lv_low["trend_bias"] == lv_high["trend_bias"] == "BULLISH"
    assert lv_low["daily_close"] == lv_high["daily_close"] == 7.20
    # Wallet-aware sizing: Rs.5,500 wallet with a Rs.20,000 margin setting -> capped to wallet/3 slots
    w55 = {"is_live_api": True, "total_inr": 5500.0, "available_inr": 5500.0}
    eff_m, eff_note = eng.compute_wallet_capped_margin(20000.0, 10, w55, 3)
    assert abs(eff_m - 1833.33) < 0.02 and "capped" in eff_note, (eff_m, eff_note)
    assert eff_m * 10 * 0.5 >= 2448.0, "Each 50% tranche must still clear CoinDCX Rs.2,448 minimum notional"
    tiny_m, _ = eng.compute_wallet_capped_margin(20000.0, 10, {"is_live_api": True, "total_inr": 600.0, "available_inr": 600.0}, 3)
    assert tiny_m * 10 < 2448.0
    unv_m, unv_note = eng.compute_wallet_capped_margin(20000.0, 10, {"is_live_api": False, "total_inr": 5500.0}, 3)
    assert unv_m == 20000.0 and unv_note == ""

    # Live 5% daily loss stop: day-start Rs.5,500 -> Rs.5,200 (-Rs.300 >= Rs.275 limit) blocks; Rs.5,300 does not
    today_s = eng.datetime.now(eng.IST).strftime("%Y-%m-%d")
    cfg_ds = {"enabled": True, "daily_start_wallet": {"date": today_s, "inr": 5500.0}}
    with patch.object(eng, "get_autotrade_config", return_value=dict(cfg_ds)), \
         patch.object(eng, "save_autotrade_config", return_value={}):
        hit, hit_msg, _ = eng.check_live_daily_loss_stop({"is_live_api": True, "total_inr": 5200.0})
        assert hit and "5% Daily Loss Stop" in hit_msg, hit_msg
        ok_hit, _, _ = eng.check_live_daily_loss_stop({"is_live_api": True, "total_inr": 5300.0})
        assert not ok_hit
        with patch.object(eng, "fetch_coindcx_futures_balance", return_value={"is_live_api": True, "total_inr": 5200.0, "available_inr": 5200.0}):
            ok_x, msg_x, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-INJ_USDT",
                sig={"signal": "SHORT", "entry": 7.30, "entry2_sweep": 7.43, "tp1": 7.15, "tp2": 6.89, "stop_loss": 7.49, "levels": neutral_levels},
                single_trade_margin_inr=20000.0, leverage=10,
            )
            assert not ok_x and "5% Daily Loss Stop" in msg_x, msg_x
    # New IST day -> baseline resets to current wallet, no block
    with patch.object(eng, "get_autotrade_config", return_value={"daily_start_wallet": {"date": "2000-01-01", "inr": 9999.0}}), \
         patch.object(eng, "save_autotrade_config", return_value={}) as m_save:
        hit2, _, info2 = eng.check_live_daily_loss_stop({"is_live_api": True, "total_inr": 5200.0})
        assert not hit2 and info2["day_start_inr"] == 5200.0 and m_save.called

    # signal_monitor constant must exist (was an undefined-name crash) & local runs never touch the shared sheet state
    import signal_monitor as _sm
    assert _sm.MAX_CONCURRENT_PORTFOLIO_TRADES == eng.MAX_CONCURRENT_TRADES == 3
    if not os.getenv("APP_DEPLOYMENT_ID"):
        assert eng._get_deployment_id() == ""
    print("  -> PASS: Completed-Candle Daily Bias lock + NEUTRAL/counter-trend blocks verified.")
    print("  -> PASS: Wallet-capped margin (Rs.5,500 -> Rs.1,833/trade), live 5% daily loss stop & slot constant verified.")


def test_6_deployment_regression_guards():
    print("[6/10] Verifying deployment regression guards & TP1 profit-lock SL...")
    import inspect
    import coindcx_engine as eng
    import signal_monitor as sm

    src_kill = inspect.getsource(eng._check_and_kill_obsolete_daemon)
    assert "SystemExit" not in src_kill, "_check_and_kill_obsolete_daemon must raise _ObsoleteDaemonStop, never SystemExit"

    src_req = inspect.getsource(eng._send_coindcx_signed_request)
    assert "ThreadPoolExecutor" not in src_req, "_send_coindcx_signed_request must never use ThreadPoolExecutor"

    src_pin = inspect.getsource(eng._pin_coindcx_nat_session)
    assert "_NAT_PIN_LOCK" in src_pin and "cand_pool.append" in src_pin, (
        "_pin_coindcx_nat_session must use single-flight _NAT_PIN_LOCK and hold candidate sockets in cand_pool"
    )

    with open(os.path.join(ROOT_DIR, "app.py"), "r", encoding="utf-8") as f:
        app_src = f.read()
    assert 'st.markdown(f"""\n<style>' not in app_src, "app.py must use st.html() for <style> blocks, never st.markdown()"
    assert "on_change=_on_sidebar_autotrade_toggle_change" in app_src

    sl_short_base = eng.compute_tp1_profit_lock_sl("B-INJ_USDT", "SHORT", entry_px=7.30, tp1_px=7.10)
    assert abs(sl_short_base - 7.20) < 1e-4
    sl_short_prev15m = eng.compute_tp1_profit_lock_sl("B-INJ_USDT", "SHORT", entry_px=7.30, tp1_px=7.10, prev_candle_high=7.16)
    assert abs(sl_short_prev15m - 7.16) < 1e-4

    sl_long_base = eng.compute_tp1_profit_lock_sl("B-NEAR_USDT", "LONG", entry_px=3.80, tp1_px=4.00)
    assert abs(sl_long_base - 3.90) < 1e-4
    sl_long_prev15m = eng.compute_tp1_profit_lock_sl("B-NEAR_USDT", "LONG", entry_px=3.80, tp1_px=4.00, prev_candle_low=3.94)
    assert abs(sl_long_prev15m - 3.94) < 1e-4

    assert sm._canon_pair("B-INJ_USDT") == sm._canon_pair("I-INJ_INR") == sm._canon_pair("INJUSDT") == "INJ"
    fake_sig = {
        "signal": "SHORT", "signal_kind": "SWEEP", "entry": 7.30, "entry2_sweep": 7.43,
        "tp1": 7.10, "tp2": 6.89, "stop_loss": 7.47, "roe_tp1": 15.0, "candle_ts": 999999999,
        "margin_inr": 15000.0, "leverage": 10, "trigger_zone": "SELL ZONE", "trigger_reason": "Test"
    }
    with patch.object(sm, "scan_pair", return_value=fake_sig), \
         patch.object(eng, "get_autotrade_config", return_value={"email_alerts_enabled": True, "single_trade_margin_inr": 15000.0}), \
         patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}), \
         patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[{"pair": "I-INJ_INR", "direction": "SHORT"}]), \
         patch.object(sm.email_notifier, "send_trade_email") as mock_email:
        sm._LAST_SCAN_CACHE["results"] = []
        res_scan = sm.scan_and_alert(pairs=["B-INJ_USDT"], send=True, strategy_ids=["box_theory"], autotrade=False)
        assert not mock_email.called, "send_trade_email must NEVER be called when asset is in an active live trade"
        assert "already in an active Live Trade" in res_scan[0]["message"]

    forbidden_tokens = (
        "_DEFAULT_ACTIVE_KEY",
        "_DEFAULT_ACTIVE_SECRET",
        "_DEFAULT_APP_PWD_B64",
        "_FALLBACK_SA_B64",
        "bcce1ecadc5a06815a9e6e30ad6b5849463a4ec647ae74be",
        "f2e91a5bbe065891afad811250a31b82891b7869174b9aac3a4fe883ffb1b411",
    )
    for fname in ("coindcx_engine.py", "app.py", "email_notifier.py", "sheets_logger.py", "alert_notifier.py", "gemini_advisor.py", "signal_monitor.py"):
        with open(os.path.join(ROOT_DIR, fname), "r", encoding="utf-8") as f_chk:
            txt = f_chk.read()
            for tok in forbidden_tokens:
                assert tok not in txt, f"Hardcoded secret token '{tok}' found in {fname}!"

    print("  -> PASS: All deployment & hot-reload regression guards + Zero Hardcoded Secrets verified.")


def test_7_ui_render_and_navigation_tabs_integrity():
    print("[7/10] Verifying full UI layout, navigation tabs rendering, and fragment loop guards...")
    import coindcx_engine as eng

    with open(os.path.join(ROOT_DIR, "app.py"), "r", encoding="utf-8") as f:
        app_src = f.read()

    # 1. Verify _DAEMON_VERSION in app.py matches _REQUIRED_DAEMON_VERSION in coindcx_engine.py
    m_ver = re.search(r"^_DAEMON_VERSION\s*=\s*(\d+)", app_src, re.MULTILINE)
    assert m_ver, "Missing _DAEMON_VERSION in app.py"
    app_daemon_ver = int(m_ver.group(1))
    assert app_daemon_ver == eng._REQUIRED_DAEMON_VERSION, (
        f"_DAEMON_VERSION in app.py ({app_daemon_ver}) != _REQUIRED_DAEMON_VERSION in coindcx_engine.py ({eng._REQUIRED_DAEMON_VERSION})"
    )

    # 2. Verify NO @st.fragment before `active_section = st.radio("Navigate Section"` calls st.rerun()
    nav_idx = app_src.find('active_section = st.radio(\n    "Navigate Section"')
    assert nav_idx > 0, "Could not locate `active_section = st.radio(\"Navigate Section\", ...)` in app.py"
    before_nav = app_src[:nav_idx]
    assert "_auto_sync_live_account_fragment" not in app_src, (
        "CRITICAL UI BUG: `_auto_sync_live_account_fragment` found in app.py! "
        "Mid-page fragments that call st.rerun() abort script execution and prevent navigation tabs from rendering."
    )
    frag_idx = before_nav.find("@st.fragment")
    if frag_idx >= 0:
        assert "st.rerun()" not in before_nav[frag_idx:], (
            "CRITICAL UI BUG: `@st.fragment` before `Navigate Section` contains `st.rerun()`!"
        )

    # 3. Verify no top-level st.stop() or non-button st.rerun() exists between check_authentication() and Navigate Section
    auth_call_idx = app_src.find("check_authentication()")
    assert 0 < auth_call_idx < nav_idx
    between_auth_and_nav = app_src[auth_call_idx:nav_idx]
    assert "\nst.stop()" not in between_auth_and_nav, (
        "Top-level st.stop() found between check_authentication() and Navigate Section!"
    )
    assert "input_coindcx_static_proxy_url" not in between_auth_and_nav, (
        "CRITICAL UI BUG: Sidebar text_input with st.rerun() found before Navigate Section!"
    )
    lines_between = between_auth_and_nav.splitlines()
    for idx_l, line_txt in enumerate(lines_between):
        if "st.rerun()" in line_txt:
            context_window = "\n".join(lines_between[max(0, idx_l - 10):idx_l + 1])
            assert ("st.button(" in context_window or "st.sidebar.button(" in context_window or "st.form_submit_button(" in context_window), (
                f"CRITICAL UI BUG: Unconditional/non-button st.rerun() found before Navigate Section at line {idx_l}:\n{context_window}"
            )

    # 4. Verify all 7 required navigation tabs exist in NAV_SECTIONS and have matching render blocks
    expected_tabs = [
        "⚡ Signals",
        "🎯 Execute",
        "📊 Positions",
        "💰 Funds",
        "📈 Chart & Levels",
        "🧪 Backtest",
        "🤖 AI Advisor",
    ]
    after_nav = app_src[nav_idx:]
    for tab in expected_tabs:
        assert f'"{tab}"' in before_nav, f"Missing navigation tab '{tab}' in NAV_SECTIONS"
        assert (f'active_section == "{tab}"' in after_nav), f"Missing render section for tab '{tab}'"

    # 5. Verify end-of-page fragment condition is strictly complementary (cannot loop)
    assert '_cold_wallet_synced_once' in after_nav
    assert 'if isinstance(cur_bal, dict) and cur_bal.get("is_live_api") and coindcx_engine._PERSIST.get("session_verified"):' in after_nav

    # 6. Verify legacy "Smart Hybrid" / "2-Entry" UI labels are completely removed from app.py
    for stale_ui_label in ("Smart Hybrid", "10x 2-Entry", "Entry 2 @ Sweep", "Entry 2 / Trade 2"):
        assert stale_ui_label not in app_src, f"Stale UI label '{stale_ui_label}' found in app.py!"
    assert "#### 🎫 Trade Execution Ticket" in app_src

    # 7. Parse AST of app.py to ensure clean top-level structure
    tree = ast.parse(app_src, filename="app.py")
    assert len(tree.body) > 20
    print(f"  -> PASS: All 7 UI tabs ({', '.join(expected_tabs)}) & fragment non-loop invariants verified.")


def test_8_stale_cache_expiry_and_nat_pinner():
    print("[8/10] Verifying stale unverified cache expiry, 0ms lock auto-release, and 8-thread priority NAT pinner...")
    import inspect
    import coindcx_engine as eng

    # 1. Verify _pin_coindcx_nat_session uses 8 concurrent worker threads and only tests priority_ips in Phase 1
    src_pin = inspect.getsource(eng._pin_coindcx_nat_session)
    assert "if cand_ip in priority_ips and not found_evt.is_set():" in src_pin, (
        "_pin_coindcx_nat_session must use 8 concurrent worker threads and only call _test_signed_on_sess on priority_ips during Phase 1"
    )

    # 2. Verify unverified session expires last_good_live after 45s (never masks dead session for 24h)
    saved_ver = eng._PERSIST.get("session_verified")
    saved_data = eng._WALLET_BALANCE_CACHE.get("data")
    saved_lg = eng._WALLET_BALANCE_CACHE.get("last_good_live")
    saved_lg_ts = eng._WALLET_BALANCE_CACHE.get("last_good_ts")
    try:
        k, _ = eng._get_coindcx_credentials()
        prefix = k[:8] if k else ""
        eng._PERSIST["session_verified"] = False
        eng._WALLET_BALANCE_CACHE["data"] = None
        eng._WALLET_BALANCE_CACHE["last_good_live"] = {
            "total_inr": 56762.88,
            "available_inr": 56762.88,
            "is_live_api": True,
            "_key_prefix": prefix,
        }
        eng._WALLET_BALANCE_CACHE["last_good_ts"] = time.time() - 120.0  # 2 minutes old while unverified
        with patch.object(eng, "_trigger_bg_wallet_refresh"):
            res_unver = eng.fetch_coindcx_futures_balance(force_refresh=False)
            assert res_unver.get("is_live_api") is False, (
                f"Expected unverified 2-min-old last_good_live to return is_live_api=False, got {res_unver}"
            )
    finally:
        eng._PERSIST["session_verified"] = saved_ver
        eng._WALLET_BALANCE_CACHE["data"] = saved_data
        eng._WALLET_BALANCE_CACHE["last_good_live"] = saved_lg
        eng._WALLET_BALANCE_CACHE["last_good_ts"] = saved_lg_ts

    # 3. Verify _fetch_coindcx_active_positions_sync clears stale positions when session is unverified
    saved_pos = eng._ACTIVE_POSITIONS_CACHE.get("data")
    saved_ok_ts = eng._ACTIVE_POSITIONS_CACHE.get("last_ok_ts")
    try:
        eng._PERSIST["session_verified"] = False
        eng._ACTIVE_POSITIONS_CACHE["data"] = [{"pair": "B-NEAR_USDT", "direction": "LONG"}]
        eng._ACTIVE_POSITIONS_CACHE["last_ok_ts"] = time.time() - 300.0
        with patch.object(eng, "_send_coindcx_signed_request", return_value=(None, "HTTP 401")), patch.object(eng, "_try_load_sheet_account_bridge", return_value=None):
            pos_res = eng._fetch_coindcx_active_positions_sync()
            assert pos_res == [], f"Expected stale unverified positions to be purged to [], got {pos_res}"
    finally:
        eng._PERSIST["session_verified"] = saved_ver
        eng._ACTIVE_POSITIONS_CACHE["data"] = saved_pos
        eng._ACTIVE_POSITIONS_CACHE["last_ok_ts"] = saved_ok_ts

    # 4. Verify get_active_portfolio_trade_status(manage_exchange=False) clears stale lock in 0ms when live positions are confirmed empty
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_cfg = os.path.join(tmpdir, "autotrade_config.json")
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", temp_cfg):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            eng.save_autotrade_config({
                "active_trade_lock": {
                    "pair": "B-NEAR_USDT",
                    "direction": "LONG",
                    "entry": 3.71,
                    "opened_ts": time.time() - 600.0,
                    "is_live_exchange": True,
                }
            })
            eng._PERSIST["session_verified"] = True
            eng._ACTIVE_POSITIONS_CACHE["data"] = []
            eng._ACTIVE_POSITIONS_CACHE["last_ok_ts"] = time.time()
            try:
                st_res = eng.get_active_portfolio_trade_status(manage_exchange=False)
                assert st_res["is_occupied"] is False, f"Expected stale NEAR lock to auto-clear in 0ms, got {st_res}"
            finally:
                eng._PERSIST["session_verified"] = saved_ver
                eng._ACTIVE_POSITIONS_CACHE["data"] = saved_pos
                eng._ACTIVE_POSITIONS_CACHE["last_ok_ts"] = saved_ok_ts

    # 5. Verify Static IP Proxy (`COINDCX_PROXY_URL`) attaches to single-socket sessions and Cross-Server Sheet Bridge syncs live wallet/positions
    saved_proxy = eng._PERSIST.get("proxy_url", "")
    try:
        with patch.dict(os.environ, {"COINDCX_PROXY_URL": "http://coindcx:tok123@34.100.200.1:8888"}):
            eng._PERSIST["proxy_url"] = ""
            p_url = eng._get_coindcx_proxy_url()
            assert p_url == "http://coindcx:tok123@34.100.200.1:8888", f"Unexpected proxy_url: {p_url}"
            s_prox = eng._make_single_socket_session()
            assert s_prox.proxies.get("https") == "http://coindcx:tok123@34.100.200.1:8888"
            s_prox.close()
    finally:
        eng._PERSIST["proxy_url"] = saved_proxy
        os.environ.pop("COINDCX_PROXY_URL", None)

    mock_bridge_snap = {
        "ts": time.time(),
        "pinned_ip": "35.230.78.192",
        "proxy_url": "",
        "wallet": {
            "total_inr": 58585.19,
            "available_inr": 58585.19,
            "inr_cash": 58585.19,
            "locked_inr": 0.0,
            "usdt_cash": 0.0,
            "available_usdt": 0.0,
            "locked_margin_usd": 0.0,
            "cross_user_margin_usd": 0.0,
            "live_usd_inr": 102.0,
            "is_live_api": True,
            "source": "CoinDCX Live Futures API",
        },
        "positions": [],
    }
    try:
        with patch.object(eng, "_get_coindcx_credentials", return_value=("d6d123456789c512", "sec123456789")),              patch.object(eng, "_send_coindcx_signed_request", return_value=(None, "HTTP 401")),              patch.object(eng, "_try_load_sheet_account_bridge", return_value=mock_bridge_snap):
            bridged_bal = eng._fetch_coindcx_futures_balance_sync()
            assert bridged_bal.get("is_live_api") is True and abs(bridged_bal.get("total_inr", 0) - 58585.19) < 1e-2, (
                f"Expected Sheet Bridge to sync live wallet ₹58,585.19 on NAT rotation, got {bridged_bal}"
            )
            bridged_pos = eng._fetch_coindcx_active_positions_sync()
            assert bridged_pos == [], f"Expected Sheet Bridge to sync 0 positions, got {bridged_pos}"
    finally:
        eng._PERSIST["session_verified"] = saved_ver
        eng._PERSIST["using_sheet_bridge"] = False
        eng._WALLET_BALANCE_CACHE["data"] = saved_data
        eng._WALLET_BALANCE_CACHE["last_good_live"] = saved_lg
        eng._WALLET_BALANCE_CACHE["last_good_ts"] = saved_lg_ts
        eng._ACTIVE_POSITIONS_CACHE["data"] = saved_pos
        eng._ACTIVE_POSITIONS_CACHE["last_ok_ts"] = saved_ok_ts

    print("  -> PASS: Stale unverified cache expiry, 0ms lock auto-release, Static IP Proxy, and Cross-Server Sheet Bridge verified.")


def test_9_ai_advisor_and_tick_precision():
    print("[9/10] Verifying AI Advisor live quant engine, zero manual API key prompt, and tick-exact formatting...")
    import coindcx_engine as eng
    import gemini_advisor as ga

    # 1. Verify app.py does NOT render the manual GEMINI_API_KEY text input prompt
    with open(os.path.join(ROOT_DIR, "app.py"), "r", encoding="utf-8") as f:
        app_src = f.read()
    assert "Paste AIza..." not in app_src, "app.py must not ask user to paste a manual GEMINI_API_KEY on screen"
    assert "Connected via Streamlit Server Secrets" in app_src

    # 2. Verify tick-exact price formatting (INJ = 3 decimals, ETH = 2, BTC = 1, DOGE = 5)
    assert eng.format_order_price("B-INJ_USDT", 8.3654) == 8.365
    assert ga._fmt_tick("B-INJ_USDT", 8.365) == "$8.365"
    assert ga._fmt_tick("B-ETH_USDT", 2233.35) == "$2233.35"
    assert ga._fmt_tick("B-DOGE_USDT", 0.07691) == "$0.07691"

    # 2b. Verify zero deprecated gemini-2.5-* / 2.0-* / 1.5-* models remain & dynamic Latest-and-Greatest discovery works
    all_m_ids = [m[0] for m in ga.AVAILABLE_GEMINI_MODELS] + list(ga.FALLBACK_MODEL_CHAIN)
    for bad_prefix in ("gemini-2.5", "gemini-2.0", "gemini-1.5"):
        assert not any(m.startswith(bad_prefix) for m in all_m_ids), f"Deprecated model prefix '{bad_prefix}' in {all_m_ids}"
    assert ga.AVAILABLE_GEMINI_MODELS[0][0] == "auto", "Default model selector option must be 'auto' (dynamic latest & greatest)"
    assert ga.rank_gemini_model_id("gemini-5.0-pro") > ga.rank_gemini_model_id("gemini-4-carbon") > ga.rank_gemini_model_id("gemini-4-argon") > ga.rank_gemini_model_id("gemini-3.8-flash") > ga.rank_gemini_model_id("gemini-3.5-flash-lite")

    from types import SimpleNamespace as _NS
    from unittest.mock import MagicMock as _MM
    fake_api_models = [
        _NS(name="models/gemini-embedding-2", display_name="Embedding 2", supported_actions=["embedContent"]),
        _NS(name="models/gemini-3.8-live", display_name="Gemini 3.8 Live", supported_actions=["bidiGenerateContent"]),
        _NS(name="models/gemini-nano-banana-2.1", display_name="Nano Banana", supported_actions=["generateContent"]),
        _NS(name="models/gemini-2.5-flash", display_name="Gemini 2.5 Flash", supported_actions=["generateContent"]),
        _NS(name="models/gemini-3.8-flash", display_name="Gemini 3.8 Flash", supported_actions=["generateContent"]),
        _NS(name="models/gemini-4-argon", display_name="Gemini 4 Argon", supported_actions=["generateContent"]),
        _NS(name="models/gemini-5.0-pro", display_name="Gemini 5.0 Pro", supported_actions=["generateContent"]),
    ]
    fake_client = _MM()
    fake_client.models.list.return_value = fake_api_models
    fake_inter = _NS(output_text="Dynamic latest model answer!", id="inter_123")
    fake_client.interactions.create.return_value = fake_inter
    with patch.object(ga.genai, "Client", return_value=fake_client):
        disc = ga.discover_available_gemini_models(api_key="test_dynamic_discovery_key", force_refresh=True)
        assert disc["ok"] is True and disc["top_model"] == "gemini-5.0-pro", disc
        assert disc["model_ids"] == ["gemini-5.0-pro", "gemini-4-argon", "gemini-3.8-flash"], disc["model_ids"]
        resp_auto = ga.ask_gemini_trade_advisor(
            user_prompt="Top coins today?", preferred_model="auto", api_key="test_dynamic_discovery_key", prefer_vertex=False
        )
        assert resp_auto["ok"] and resp_auto["llm_used"] and "gemini-5.0-pro" in resp_auto["model_used"], resp_auto

    # 2c. Regression guard: when BOTH VERTEX_ADC_JSON AND GEMINI_API_KEY are configured (Staging/Main Secrets),
    #     Vertex AI Priority 1 MUST still run (never bypassed by api_key!), and 403-blocked models auto-fallback cleanly.
    fake_v_client = _MM()
    def _fake_v_gen(model, contents, config=None):
        if model == "gemini-4-neon":
            raise RuntimeError("403 PERMISSION_DENIED: eligible paid billing account required")
        return _NS(text=f"Vertex live reply from {model}")
    fake_v_client.models.generate_content.side_effect = _fake_v_gen
    ga._VERTEX_WORKING_MODEL_CACHE.update({"ts": 0.0, "model": "", "project": ""})
    ga._VERTEX_BLOCKED_MODELS.clear()
    ga._VERTEX_SLOW_MODELS.clear()
    with patch.object(ga, "_get_vertex_adc_client", return_value=(object(), "gen-lang-client-test")), \
         patch.object(ga, "discover_available_gemini_models", return_value={
             "ok": True, "model_ids": ["gemini-4-neon", "gemini-4-hydrogen"], "top_model": "gemini-4-neon"
         }), \
         patch.object(ga.genai, "Client", return_value=fake_v_client):
        resp_v_coexist = ga.ask_gemini_trade_advisor(
            user_prompt="Audit my trades",
            preferred_model="gemini-4-neon",
            api_key="AIzaFakeCoexistingKey1234567890123456",
            prefer_vertex=True,
        )
        assert resp_v_coexist["ok"] and resp_v_coexist["llm_used"], resp_v_coexist
        assert "gemini-4-hydrogen" in resp_v_coexist["model_used"] and "Vertex AI" in resp_v_coexist["model_used"], resp_v_coexist
        assert "Auto-Fallback from gemini-4-neon" in resp_v_coexist["model_used"], resp_v_coexist
        assert ("gen-lang-client-test", "gemini-4-neon") in ga._VERTEX_BLOCKED_MODELS
    ga._VERTEX_WORKING_MODEL_CACHE.update({"ts": 0.0, "model": "", "project": ""})
    ga._VERTEX_BLOCKED_MODELS.clear()

    # 2d. Verify High-Tech AI Advisor avatar asset, Google profile avatar loader, and auto-scroll chat window wiring
    ai_avatar_file = os.path.join(ROOT_DIR, "assets", "ai_advisor_avatar.png")
    assert os.path.isfile(ai_avatar_file) and os.path.getsize(ai_avatar_file) > 1024, "Missing assets/ai_advisor_avatar.png"
    assert "ai_advisor_chat_shell" in app_src and "_scroll_ai_chat_into_view" in app_src
    assert "_load_user_google_avatar" in app_src and "_load_ai_advisor_avatar" in app_src and "prefer_vertex=True" in app_src

    # 3. Verify AI Advisor generates distinct, intent-routed, tick-exact responses (with real pnl_inr, NOT Rs.0.00!)
    mock_struct = {
        "pair": "B-INJ_USDT", "symbol": "INJ",
        "live_price": 8.365, "high_24h": 8.510, "low_24h": 7.720, "change_24h": 8.96,
        "SH": 8.288, "RH": 8.081, "MID": 7.542, "RL": 7.003, "SL": 6.861,
        "ema50_d": 8.120, "ema200_d": 7.450, "daily_bias": "BULLISH", "daily_close": 8.210,
        "ema20_15m": 8.340, "ema50_15m": 8.210, "ema200_15m": 7.990, "rsi_15m": 64.2, "rsi_1h": 68.5,
        "prev15_high": 8.390, "prev15_low": 8.310, "prev15_close": 8.355,
    }
    mock_sheet = {
        "ok": True,
        "spreadsheet_title": "Crypto_Trades_Journal",
        "live_trades": [{"Pair": "B-INJ_USDT", "Direction": "SHORT", "Entry ($)": "7.870"}],
        "closed_trades": [
            {"Pair": "B-INJ_USDT", "Direction": "LONG", "Entry": "7.500", "Exit": "7.850", "Result": "WIN", "Realized PnL (INR)": "1800.00"},
            {"Pair": "B-NEAR_USDT", "Direction": "LONG", "Entry": "4.050", "Exit": "3.980", "Result": "LOSS", "Realized PnL (INR)": "-549.50"},
        ],
    }
    mock_wl = [
        {"pair": "B-BTC_USDT", "sym": "BTC", "price": 62000.0, "chg_24h": -2.5, "bias": "BEARISH", "action_side": "SHORT", "target_edge": 63500.0, "dist_pct": 0.4, "zone_status": "IN SELL ZONE (RH–SH)", "SH": 64000.0, "RH": 63500.0, "MID": 62000.0, "RL": 60500.0, "SL": 60000.0},
    ]
    with patch.object(ga, "_compute_exact_pair_structure", return_value=mock_struct), \
         patch.object(ga, "_scan_watchlist_opportunities", return_value=mock_wl), \
         patch.object(eng, "compute_market_regime", return_value={"regime": "RANGING_CHOP", "label": "RANGING / CHOP", "summary": "RANGING / CHOP — Box Only"}), \
         patch.object(eng, "fetch_coindcx_active_positions", return_value=[{
             "pair": "B-INJ_USDT", "direction": "SHORT", "entry_price": 7.870, "mark_price": 8.365,
             "quantity": 100.0, "leverage": 10, "pnl_inr": -55536.31, "roe_pct": -61.70, "liquidation_price": 12.144
         }]), \
         patch("sheets_logger.fetch_all_sheet_trades", return_value=mock_sheet):
        r_audit = ga._generate_live_quant_advisor_response("Audit All Sheet Trades", selected_pair="B-INJ_USDT")
        r_setup = ga._generate_live_quant_advisor_response("Best Setup on INJ Now", selected_pair="B-INJ_USDT")
        r_open = ga._generate_live_quant_advisor_response("Review Open Position Risk", selected_pair="B-INJ_USDT")
        r_top = ga._generate_live_quant_advisor_response(
            "Based on our Google Sheet trade history, which coins have performed best for us and what is the gameplan for today's sessions?",
            selected_pair="B-INJ_USDT",
        )
        r_strat = ga._generate_live_quant_advisor_response("Which strategy should I select for today's market regime?", selected_pair="B-INJ_USDT")

        assert "Crypto_Trades_Journal" in r_audit and "INJ" in r_audit and "NEAR" in r_audit, r_audit[:250]
        assert "Live Setup Analysis for `B-INJ_USDT`" in r_setup and "$8.365" in r_setup, r_setup[:250]
        assert "Open Position #1" in r_open and "-55,536.31" in r_open and "Rs.0.00" not in r_open, r_open[:300]
        assert "Top Coins to Trade Today" in r_top and "BTC/USDT" in r_top and "Open Position #1" not in r_top, r_top[:300]
        assert "Live Market Regime, Recommended Strategy" in r_strat and "Open Position #1" not in r_strat, r_strat[:300]
        assert len({r_audit, r_setup, r_open, r_top, r_strat}) == 5, "All 5 distinct prompts must produce distinct intent-routed responses!"

    print("  -> PASS: AI Advisor intent-routed quant engine, real pnl_inr, non-deprecated Gemini models & tick precision verified.")


def _ws_fetch_lock_screen_pill(host: str, max_attempts: int = 6) -> str:
    """Connects to a Streamlit Cloud host over WebSocket and returns the rendered CoinDCX status pill."""
    ctx = ssl.create_default_context()
    raw_sock = socket.create_connection((host, 443), timeout=10)
    sock = ctx.wrap_socket(raw_sock, server_hostname=host)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        req = (
            f"GET /~/+/_stcore/stream HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Sec-WebSocket-Protocol: streamlit\r\n"
            f"Origin: https://{host}\r\n"
            f"User-Agent: Mozilla/5.0\r\n\r\n"
        )
        sock.sendall(req.encode("ascii"))
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = sock.recv(4096)
            if not chunk:
                break
            buf += chunk
        _, leftover = buf.split(b"\r\n\r\n", 1)
        data_buf = bytearray(leftover)

        def send_ws_binary(payload: bytes):
            mask_key = os.urandom(4)
            header = bytearray([0x82, 0x80 | len(payload)]) + mask_key
            masked = bytearray(b ^ mask_key[i % 4] for i, b in enumerate(payload))
            sock.sendall(header + masked)

        def read_exact(n: int) -> bytes:
            while len(data_buf) < n:
                c = sock.recv(8192)
                if not c:
                    raise EOFError("Socket closed")
                data_buf.extend(c)
            out = bytes(data_buf[:n])
            del data_buf[:n]
            return out

        def read_until_finished(timeout_sec: float = 3.0) -> bytes:
            sock.settimeout(timeout_sec)
            collected = []
            try:
                while True:
                    b1, b2 = read_exact(2)
                    opcode = b1 & 0x0F
                    masked = (b2 & 0x80) != 0
                    length = b2 & 0x7F
                    if length == 126:
                        length = struct.unpack("!H", read_exact(2))[0]
                    elif length == 127:
                        length = struct.unpack("!Q", read_exact(8))[0]
                    mask_k = read_exact(4) if masked else b""
                    payload = bytearray(read_exact(length))
                    if masked:
                        for i in range(length):
                            payload[i] ^= mask_k[i % 4]
                    if opcode == 8:
                        break
                    if opcode == 9:
                        sock.sendall(bytearray([0x8A, 0x80]) + os.urandom(4))
                    elif opcode in (1, 2):
                        b_pay = bytes(payload)
                        collected.append(b_pay)
                        if len(b_pay) < 30 and b"\x30\x00" in b_pay:
                            break
            except Exception:
                pass
            return b"".join(collected)

        last_pill = ""
        for attempt in range(1, max_attempts + 1):
            send_ws_binary(b"\x5a\x00")
            resp = read_until_finished(2.8)
            text = resp.decode("utf-8", "ignore")
            for line in text.splitlines():
                if "CoinDCX" in line:
                    last_pill = re.sub(r"<[^>]+>", "", line).strip()
            if "CoinDCX Live Synced" in last_pill and "35.230.78.192" in last_pill:
                return last_pill
            if attempt < max_attempts:
                time.sleep(2.5)
        return last_pill
    finally:
        try:
            sock.close()
        except Exception:
            pass


def test_10_live_cloud_deployments_sync():
    print("[10/10] Verifying live Streamlit Cloud deployments (`staging` & `main`)...")
    staging_host = "np-shiv-prakash-trade-assistant.streamlit.app"
    main_host = "shiv-prakash-trade-assistant.streamlit.app"

    stg_pill = _ws_fetch_lock_screen_pill(staging_host, max_attempts=6)
    print(f"  [Staging] {stg_pill}")
    assert "CoinDCX Live Synced" in stg_pill and "NEAR" not in stg_pill, (
        f"Staging failed live CoinDCX sync check: {stg_pill}"
    )

    main_pill = _ws_fetch_lock_screen_pill(main_host, max_attempts=6)
    print(f"  [Main]    {main_pill}")
    assert "CoinDCX Live Synced" in main_pill and "NEAR" not in main_pill and "56,762.88" not in main_pill, (
        f"Main failed live CoinDCX sync check: {main_pill}"
    )
    print("  -> PASS: Both `staging` and `main` are online, rendering cleanly, and free of stale wallet/position caches.")


def test_10_strategy3_four_improvements_and_staging_paper_autotrade():
    print("[10/10] Verifying Strategy 3 (4 Post-Mortem Improvements) + Staging Paper-Only AutoTrade...")
    import coindcx_engine as eng
    import strategies as strat

    # Build a synthetic 12-candle 5m series for LONG 9 EMA cross -> touch & confirm (like SOL $86.33)
    # Candles 0..6 below/around 85.40, candle 7..8 confirm cross above EMA9, candle 9 touches EMA9 & closes green
    recs_long = [
        {"open": 85.50, "high": 85.70, "low": 85.35, "close": 85.45, "EMA9": 85.60, "EMA50": 85.55},
        {"open": 85.45, "high": 85.65, "low": 85.38, "close": 85.50, "EMA9": 85.58, "EMA50": 85.55},
        {"open": 85.50, "high": 85.75, "low": 85.40, "close": 85.52, "EMA9": 85.56, "EMA50": 85.55},
        {"open": 85.52, "high": 86.25, "low": 85.45, "close": 86.10, "EMA9": 85.70, "EMA50": 85.60},  # >=20% ATR move
        {"open": 86.10, "high": 86.28, "low": 85.95, "close": 86.20, "EMA9": 85.85, "EMA50": 85.65},  # 2nd close > EMA9 (confirmed cross at idx 4)
        {"open": 86.20, "high": 86.38, "low": 86.00, "close": 86.33, "EMA9": 86.01, "EMA50": 85.72},  # touches EMA9 (86.00 <= 86.01) & closes green > prev
    ]
    atr_sol = 3.30

    # Improvement 2: Block LONG when Daily Bias is BEARISH (like SOL L[41])
    sig_blocked_bear = strat.detect_ema9_retest_entry(
        recs_long, 5, atr_sol,
        box={"trend_bias": "BEARISH", "RH": 89.50, "RL": 84.00, "MID": 86.75, "SH": 91.0, "SL": 83.0},
        ema50_15m=87.21,
    )
    assert sig_blocked_bear is None, f"Expected BEARISH Daily Bias to block LONG Strategy 3, got: {sig_blocked_bear}"

    # Improvement 3B: Block LONG in top 20% of Daily Box [RL, RH]
    sig_blocked_top20 = strat.detect_ema9_retest_entry(
        recs_long, 5, atr_sol,
        box={"trend_bias": "BULLISH", "RH": 86.60, "RL": 84.00, "MID": 85.30, "SH": 88.0, "SL": 83.0},
        ema50_15m=88.00,
    )
    assert sig_blocked_top20 is None, f"Expected top-20% Box zone to block LONG Strategy 3, got: {sig_blocked_top20}"

    # Improvement 1 & 4: Allowed in BULLISH/NEUTRAL bias, SL anchored below 12-candle swing low (85.35) & >=1.0% away,
    # and TP1 capped inside opposing 15m 50 EMA ($87.21 * 0.999 = $87.1228) instead of $87.48!
    sig_ok_long = strat.detect_ema9_retest_entry(
        recs_long, 5, atr_sol,
        box={"trend_bias": "NEUTRAL", "RH": 89.50, "RL": 84.00, "MID": 87.80, "SH": 91.0, "SL": 83.0},
        ema50_15m=87.21,
    )
    assert sig_ok_long is not None and sig_ok_long["direction"] == "LONG", f"Expected valid LONG signal, got: {sig_ok_long}"
    assert sig_ok_long["stop"] <= 85.35 * (1 - strat.SL_BUFFER) and sig_ok_long["stop"] <= 86.33 * 0.990, (
        f"Expected 12-candle structural SL <= 85.18, got: {sig_ok_long['stop']}"
    )
    assert sig_ok_long["tp1"] <= 87.21, f"Expected TP1 capped inside 15m 50 EMA ($87.21), got: {sig_ok_long['tp1']}"

    # Improvement 4B: Early 80% TP1 Breakeven SL Ratchet in get_active_portfolio_trade_status
    fake_lock = {
        "pair": "B-XRP_USDT",
        "direction": "SHORT",
        "strategy_id": "ema9_retest",
        "entry": 1.0905,
        "entry2_sweep": 0.0,
        "tp1": 1.0749,
        "tp2": 1.0562,
        "stop_loss": 1.1020,
        "tp1_hit": False,
        "opened_ts": time.time() - 60.0,
        "is_live_exchange": False,
        "mode": "Staging Paper AutoTrade (Live Market)",
    }
    saved_locks = []
    # Price reaches $1.0760 (93% of distance from 1.0905 to 1.0749, shy of TP1 by $0.0011)
    with patch.object(eng, "get_autotrade_config", return_value={"active_trade_lock": dict(fake_lock)}),          patch.object(eng, "fetch_live_ticker", return_value={"last_price": 1.0760}),          patch.object(eng, "_check_recent_15m_tp1_touch_and_prev_hl", return_value=(False, None, None)),          patch.object(eng, "save_autotrade_config", side_effect=lambda d, **kw: saved_locks.append(d) or {}):
        st_res = eng.get_active_portfolio_trade_status(manage_exchange=True)
        assert st_res["stop_loss"] < 1.0905 and abs(st_res["stop_loss"] - round(1.0905 * 0.9982, 4)) <= 0.0002, (
            f"Expected 80% TP1 breakeven ratchet below entry 1.0905, got: {st_res['stop_loss']}"
        )

    # Staging Paper-Only AutoTrade Guard: verify place_coindcx_futures_order is NEVER called on staging
    with patch.object(eng, "is_staging_environment", return_value=True),          patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}),          patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]),          patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}),          patch.object(eng, "place_coindcx_futures_order") as mock_live_order,          patch.object(eng, "save_autotrade_config", return_value={}),          patch("sheets_logger.log_trade_to_google_sheet", return_value=True):
        ok_stg, msg_stg, meta_stg = eng.execute_autotrade_two_entry_signal(
            pair="B-AVAX_USDT",
            sig={
                "signal": "SHORT",
                "strategy_id": "box_theory",
                "entry": 9.01,
                "entry2_sweep": 9.20,
                "tp1": 8.91,
                "tp2": 8.75,
                "stop_loss": 9.25,
                "levels": {"trend_bias": "BEARISH", "RH": 9.10, "RL": 8.60, "MID": 8.85, "SH": 9.20, "SL": 8.50},
            },
            single_trade_margin_inr=19500.0,
            leverage=10,
        )
        assert ok_stg and meta_stg.get("paper_mode") is True, f"Expected Staging Paper AutoTrade success, got: {ok_stg} {msg_stg}"
        assert not mock_live_order.called, "place_coindcx_futures_order MUST NEVER be called when is_staging_environment() is True!"
        assert meta_stg["lock"]["is_live_exchange"] is False
        assert meta_stg["lock"]["strategy_id"] == "box_theory"

        # Counter-trend LONG in CLEAN_DOWNTREND MUST ALWAYS be blocked
        ok_ct, msg_ct, _ = eng.execute_autotrade_two_entry_signal(
            pair="B-FET_USDT",
            sig={
                "signal": "LONG",
                "signal_kind": "BREAKOUT_CONTINUATION",
                "strategy_id": "box_theory",
                "entry": 0.1525,
                "entry2_sweep": 0.1473,
                "tp1": 0.1543,
                "tp2": 0.1772,
                "stop_loss": 0.1466,
                "levels": {"trend_bias": "BEARISH", "RH": 0.1473, "RL": 0.1399, "MID": 0.1436, "SH": 0.1515, "SL": 0.1371},
            },
            single_trade_margin_inr=23267.74,
            leverage=10,
        )
        assert not ok_ct and "Intraday Trend Matrix Guard" in msg_ct, f"Expected Intraday Trend Matrix Guard to block counter-trend LONG, got: {ok_ct} {msg_ct}"

    # Box Theory Sweep: Broken-Box Invalidation Guard & Setup 0 Removal (RENDER 2026-11-09 & FET 2026-11-12 scenarios)
    render_recs = [
        {"open": 1.574, "high": 1.589, "low": 1.563, "close": 1.584, "EMA9": 1.556, "EMA50": 1.555},
        {"open": 1.584, "high": 1.626, "low": 1.581, "close": 1.613, "EMA9": 1.567, "EMA50": 1.557},
        {"open": 1.612, "high": 1.621, "low": 1.600, "close": 1.615, "EMA9": 1.577, "EMA50": 1.560},
        {"open": 1.615, "high": 1.617, "low": 1.603, "close": 1.604, "EMA9": 1.582, "EMA50": 1.561},
        {"open": 1.604, "high": 1.618, "low": 1.603, "close": 1.608, "EMA9": 1.587, "EMA50": 1.563},
        {"open": 1.607, "high": 1.614, "low": 1.597, "close": 1.610, "EMA9": 1.592, "EMA50": 1.565},
        {"open": 1.610, "high": 1.616, "low": 1.602, "close": 1.605, "EMA9": 1.595, "EMA50": 1.567},
        {"open": 1.605, "high": 1.607, "low": 1.591, "close": 1.594, "EMA9": 1.594, "EMA50": 1.568},
        {"open": 1.593, "high": 1.601, "low": 1.591, "close": 1.597, "EMA9": 1.595, "EMA50": 1.569},
        {"open": 1.597, "high": 1.599, "low": 1.584, "close": 1.589, "EMA9": 1.594, "EMA50": 1.570},  # idx 9: 16:30 IST top-down pullback (must NOT short!)
        {"open": 1.589, "high": 1.604, "low": 1.589, "close": 1.597, "EMA9": 1.595, "EMA50": 1.574},  # idx 10: 17:30 IST broken-box top bounce (must NOT buy Setup 0!)
    ]
    for r_c in render_recs:
        r_c["date_str"] = "2026-11-09"
    render_box = {
        "RH": 1.580, "RL": 1.471, "MID": 1.5255, "SH": 1.594, "SL": 1.448,
        "EMA50": 1.6937, "EMA200": 1.7106, "ATR": 0.1012, "bias": "BEARISH", "trend_bias": "BEARISH",
    }
    render_ctx = {
        "boxes": {"2026-11-09": render_box},
        "ema50_15m": [x["EMA50"] for x in render_recs],
        "ema9_15m": [x["EMA9"] for x in render_recs],
    }
    s1_box = strat.BoxTheorySweep()
    # 16:30 IST (idx 9): top-down pullback to $1.589 after $1.626 breakout must NOT trigger a SHORT reversal
    sig_1630 = s1_box.backtest_entry(9, render_recs[9], render_ctx, render_recs)
    assert sig_1630 is None, f"Expected broken-box guard to block top-down SHORT at 16:30 IST, got: {sig_1630}"

    # 17:30 IST (idx 10): with Setup 0 removed, broken upper box in BEARISH bias must stay flat (NO LONG at top!)
    sig_1730 = s1_box.backtest_entry(10, render_recs[10], render_ctx, render_recs)
    assert sig_1730 is None, f"Expected Setup 0 removal to block LONG at broken-box top, got: {sig_1730}"

    # B-FET_USDT 2026-11-12 00:00 IST regression guard: spike to $0.1543 above SH ($0.1515) in BEARISH bias must NOT trigger LONG at $0.1520-$0.1525
    fet_recs = [
        {"open": 0.1513, "high": 0.1528, "low": 0.1511, "close": 0.1525, "EMA9": 0.1506, "EMA50": 0.1482, "date_str": "2026-11-11"},
        {"open": 0.1524, "high": 0.1543, "low": 0.1522, "close": 0.1535, "EMA9": 0.1512, "EMA50": 0.1484, "date_str": "2026-11-11"},
        {"open": 0.1536, "high": 0.1540, "low": 0.1526, "close": 0.1526, "EMA9": 0.1514, "EMA50": 0.1486, "date_str": "2026-11-11"},
        {"open": 0.1526, "high": 0.1537, "low": 0.1517, "close": 0.1533, "EMA9": 0.1518, "EMA50": 0.1488, "date_str": "2026-11-11"},
        {"open": 0.1534, "high": 0.1539, "low": 0.1525, "close": 0.1526, "EMA9": 0.1520, "EMA50": 0.1489, "date_str": "2026-11-11"},
        {"open": 0.1526, "high": 0.1528, "low": 0.1518, "close": 0.1518, "EMA9": 0.1519, "EMA50": 0.1490, "date_str": "2026-11-11"},
        {"open": 0.1519, "high": 0.1529, "low": 0.1518, "close": 0.1520, "EMA9": 0.1520, "EMA50": 0.1491, "date_str": "2026-11-11"},
    ]
    fet_box = {
        "RH": 0.1473, "RL": 0.1399, "MID": 0.1436, "SH": 0.1515, "SL": 0.1371,
        "EMA50": 0.1772, "EMA200": 0.2013, "ATR": 0.0130, "bias": "BEARISH", "trend_bias": "BEARISH",
    }
    fet_ctx = {
        "boxes": {"2026-11-11": fet_box},
        "ema50_15m": [x["EMA50"] for x in fet_recs],
        "ema9_15m": [x["EMA9"] for x in fet_recs],
    }
    sig_fet_0000 = s1_box.backtest_entry(6, fet_recs[6], fet_ctx, fet_recs)
    assert sig_fet_0000 is None, f"Expected FET 00:00 IST broken-box top bounce to stay flat, got: {sig_fet_0000}"

    # AutoTrade Maker Limit Order Conversion & Pending Entry 1 Lifecycle Verification
    m_buy = eng.compute_maker_limit_entry_price(
        "B-FET_USDT", "LONG", desired_entry_px=0.1468,
        live_ticker={"last_price": 0.1468, "bid": 0.1468, "ask": 0.1469},
        sl_px=0.1410, entry2_px=0.1425, tp1_px=0.1510,
    )
    assert abs(m_buy - 0.1467) < 1e-6, f"Expected Maker BUY 1 tick below 0.1468 -> 0.1467, got {m_buy}"
    m_sell = eng.compute_maker_limit_entry_price(
        "B-INJ_USDT", "SHORT", desired_entry_px=7.300,
        live_ticker={"last_price": 7.304, "bid": 7.303, "ask": 7.305},
        sl_px=7.490, entry2_px=7.430, tp1_px=7.150,
    )
    assert abs(m_sell - 7.305) < 1e-6, f"Expected Maker SELL at ask 7.305 (> 7.300 & > 7.304), got {m_sell}"

    placed_orders = []
    def _fake_place_limit(**kwargs):
        placed_orders.append(kwargs)
        return True, "OK_LIMIT", {"order_id": f"oid_{len(placed_orders)}"}

    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg), \
             patch.object(eng, "is_staging_environment", return_value=False), \
             patch.object(eng, "is_experiment_environment", return_value=False), \
             patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]), \
             patch.object(eng, "fetch_coindcx_active_positions", return_value=[]), \
             patch.object(eng, "fetch_coindcx_futures_balance", return_value={"is_live_api": True, "total_inr": 60000.0, "available_inr": 60000.0}), \
             patch.object(eng, "_get_coindcx_credentials", return_value=("k1", "s1")), \
             patch.object(eng, "compute_market_bias", return_value={"bias": "BEARISH"}), \
             patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}), \
             patch.object(eng, "fetch_live_ticker", return_value={"last_price": 7.300, "bid": 7.299, "ask": 7.301}), \
             patch.object(eng, "place_coindcx_futures_order", side_effect=_fake_place_limit), \
             patch.object(eng.time, "sleep", return_value=None), \
             patch("sheets_logger.log_trade_to_google_sheet", return_value=True):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            with patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}):
                ok_lim, msg_lim, meta_lim = eng.execute_autotrade_two_entry_signal(
                    pair="B-INJ_USDT",
                    sig={
                        "signal": "SHORT",
                        "strategy_id": "box_theory",
                        "entry": 7.300,
                        "entry2_sweep": 7.430,
                        "tp1": 7.150,
                        "tp2": 6.890,
                        "stop_loss": 7.490,
                        "levels": {"trend_bias": "BEARISH", "RH": 7.31, "RL": 6.89, "MID": 7.10, "SH": 7.43, "SL": 6.86},
                    },
                    single_trade_margin_inr=20000.0,
                    leverage=10,
                )
            assert ok_lim, f"Expected Live Maker Limit AutoTrade success, got: {ok_lim} {msg_lim}"
            assert len(placed_orders) == 1, f"Expected strictly 1 Single-Slot Maker Limit Entry 1 order (Entry 2 removed), got: {placed_orders}"
            assert placed_orders[0]["order_type"] == "limit_order", f"Expected strictly limit_order, got: {placed_orders}"
            assert placed_orders[0]["price"] >= 7.301, f"Expected Maker SELL price >= 7.301, got {placed_orders[0]}"
            assert placed_orders[0]["quantity"] >= 25.0, f"Expected 100% slot margin sizing (~32 INJ at 10x), got {placed_orders[0]['quantity']}"
            assert meta_lim["lock"]["entry2_sweep"] == 0.0 and meta_lim["lock"]["qty2"] == 0.0
            assert meta_lim["lock"]["entry1_pending"] is True and meta_lim["lock"]["entry1_order_id"] == "oid_1"

            # Verify Strategy 1 runner does NOT prematurely exit on 5m 9 EMA cross after TP1
            should_ex_box, _, _ = eng._evaluate_smart_hybrid_runner_step(
                pair="B-INJ_USDT", is_long=False, entry_p=7.301, tp1_p=7.150, cur_sl=7.225,
                opened_ts=time.time() - 900.0, strategy_id="box_theory",
            )
            assert should_ex_box is False, "Expected 5m 9 EMA cross runner exit disabled for Strategy 1 (box_theory)"

            # Verify UI fast-path (manage_exchange=False) does NOT clear pending Entry 1 limit lock after 90s
            lk_now = eng.get_autotrade_config()["active_trade_lock"]
            lk_now["opened_ts"] = time.time() - 300.0
            eng.save_autotrade_config({"active_trade_lock": lk_now})
            eng._PERSIST["session_verified"] = True
            eng._ACTIVE_POSITIONS_CACHE["data"] = []
            eng._ACTIVE_POSITIONS_CACHE["last_ok_ts"] = time.time()
            st_fast = eng.get_active_portfolio_trade_status(manage_exchange=False)
            assert st_fast["has_active_trade"] is True and st_fast["entry1_pending"] is True, f"Expected pending Entry 1 kept alive, got {st_fast}"

            # Verify once Entry 1 fills into a live position, daemon auto-attaches TP2/SL + TP1 Limit & clears entry1_pending
            with patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[{
                "id": "pos_inj_1", "pair": "B-INJ_USDT", "direction": "SHORT", "quantity": 15.0,
                "entry_price": 7.301, "mark_price": 7.295, "leverage": 10, "stop_loss": None, "take_profit": None,
            }]), \
                 patch.object(eng, "fetch_coindcx_active_positions", return_value=[{
                     "id": "pos_inj_1", "pair": "B-INJ_USDT", "direction": "SHORT", "quantity": 15.0,
                     "entry_price": 7.301, "mark_price": 7.295, "leverage": 10, "stop_loss": None, "take_profit": None,
                 }]), \
                 patch.object(eng, "fetch_coindcx_open_orders", return_value=[{"id": "oid_2", "pair": "B-INJ_USDT", "side": "sell", "order_type": "limit_order", "total_quantity": 15.0, "price": 7.430}]), \
                 patch.object(eng, "update_coindcx_position_tpsl", return_value=(True, "OK")):
                st_filled = eng.get_active_portfolio_trade_status(manage_exchange=True)
                lk_after = eng.get_autotrade_config()["active_trade_lock"]
                assert lk_after["entry1_pending"] is False, f"Expected entry1_pending cleared upon fill, got {lk_after}"

            # Verify unfilled Entry 1 auto-cancels cleanly if price runs to TP1 before filling
            lk_run = dict(meta_lim["lock"], opened_ts=time.time() - 180.0, entry1_pending=True)
            eng.save_autotrade_config({"active_trade_lock": lk_run})
            with patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]), \
                 patch.object(eng, "fetch_live_ticker", return_value={"last_price": 7.140}), \
                 patch.object(eng, "cancel_coindcx_open_entry_orders", return_value=(1, "Cancelled")) as mock_canc:
                st_canc = eng.get_active_portfolio_trade_status(manage_exchange=True)
                assert st_canc["is_occupied"] is False and mock_canc.called, f"Expected unfilled Entry 1 cancelled at TP1, got {st_canc}"

    print("  -> PASS: Strategy 3 (4 improvements), Box Broken-Level Guard, Setup 0 Removal, Staging Paper AutoTrade, and Maker Limit Order Lifecycle verified.")


def test_11_ema50_200_pullback_and_combo_modes():
    print("[11/11] Verifying 15m 50/200 EMA Pullback Strategy, Combo Modes & Guardrails across all layers...")
    import tempfile
    import coindcx_engine as eng
    import strategies as strat
    import signal_monitor as sm

    # 1. Registry & mode resolver checks
    assert "ema50_200" in strat.STRATEGY_REGISTRY
    assert "box_plus_ema50_200_regime" in strat.STRATEGY_REGISTRY
    assert "box_plus_ema50_200_bear" in strat.STRATEGY_REGISTRY
    assert "box_plus_ema50_200_both" in strat.STRATEGY_REGISTRY
    assert any(s.id == "ema50_200" for s in strat.list_strategies())
    assert strat.resolve_autotrade_mode(None) == "box_plus_ema50_200_regime"
    assert strat.autotrade_mode_strategy_ids("box_plus_ema50_200_bear") == ["box_theory", "ema50_200"]

    # 2. Bearish Daily Bias -> SHORT @ 15m 50/200 EMA Pullback with SL > 15m 200 EMA -> TP2 = RL
    bear_box = {"trend_bias": "BEARISH", "RH": 7.50, "RL": 6.80, "MID": 7.15, "SH": 7.60, "SL": 6.72}
    recs_bear = [
        {"open": 7.04, "high": 7.06, "low": 7.01, "close": 7.03},
        {"open": 7.03, "high": 7.05, "low": 7.02, "close": 7.04},
        {"open": 7.04, "high": 7.07, "low": 7.03, "close": 7.05},
        {"open": 7.05, "high": 7.08, "low": 7.04, "close": 7.06},
        {"open": 7.06, "high": 7.10, "low": 7.05, "close": 7.08},
        {"open": 7.08, "high": 7.16, "low": 7.07, "close": 7.13},  # touches near 50/200 ceiling
        {"open": 7.13, "high": 7.17, "low": 7.07, "close": 7.09},  # bearish rejection close < 50 EMA (7.12)
    ]
    # 2. CLEAN_DOWNTREND + 15m 50<200 EMA -> Red Trigger touching 50 EMA & closing < 50 + Confirm closing < Trigger close
    recs_bear_exp = [
        {"open": 7.11, "high": 7.14, "low": 7.06, "close": 7.09},  # Trigger: red, high>=7.12, close<7.12
        {"open": 7.09, "high": 7.10, "low": 7.02, "close": 7.05},  # Confirm: close < 7.09 -> Entry = 7.02
    ]
    sig_bear = strat._detect_ema50_200_setup(
        recs_bear_exp, 1, bear_box, ema50_val=7.12, ema200_val=7.18,
        allow_bear=True, allow_bull=False, intraday_regime="CLEAN_DOWNTREND", leverage=10, prev_ema50_val=7.12,
    )
    assert sig_bear is not None and sig_bear["direction"] == "SHORT"
    assert abs(sig_bear["entry"] - 7.02) < 1e-6 and sig_bear["pending_breakout"] is True
    assert sig_bear["stop"] > 7.18, f"Expected SL strictly above 15m 200 EMA ($7.18), got {sig_bear['stop']}"
    assert abs(sig_bear["tp2"] - 6.80) < 1e-6, f"Expected TP2 == RL ($6.80, >15% ROE), got {sig_bear['tp2']}"

    # 3. CLEAN_UPTREND + 15m 50>200 EMA -> Mirror LONG replica with SL < 15m 200 EMA -> TP = RH (>15% ROE)
    bull_box = {"trend_bias": "BEARISH", "RH": 7.60, "RL": 6.90, "MID": 7.25, "SH": 7.68, "SL": 6.82}  # Daily Bias intentionally BEARISH -> ignored!
    recs_bull_exp = [
        {"open": 7.21, "high": 7.25, "low": 7.18, "close": 7.23},  # Trigger: green, low<=7.20, close>7.20
        {"open": 7.23, "high": 7.29, "low": 7.22, "close": 7.27},  # Confirm: close > 7.23 -> Entry = 7.29
    ]
    assert strat._detect_ema50_200_setup(
        recs_bull_exp, 1, bull_box, ema50_val=7.20, ema200_val=7.14,
        allow_bear=True, allow_bull=False, intraday_regime="CLEAN_UPTREND", leverage=10, prev_ema50_val=7.20,
    ) is None, "Expected Bear-Only EMA mode to skip Bullish EMA Longs"
    sig_bull = strat._detect_ema50_200_setup(
        recs_bull_exp, 1, bull_box, ema50_val=7.20, ema200_val=7.14,
        allow_bear=True, allow_bull=True, intraday_regime="CLEAN_UPTREND", leverage=10, prev_ema50_val=7.20,
    )
    assert sig_bull is not None and sig_bull["direction"] == "LONG"
    assert abs(sig_bull["entry"] - 7.29) < 1e-6 and sig_bull["stop"] < 7.14
    assert abs(sig_bull["tp2"] - 7.60) < 1e-6, f"Expected TP2 == RH ($7.60, >15% ROE), got {sig_bull['tp2']}"

    # 4. Tight 15m 200 EMA SL is preserved when levels=None (not inflated by Box SH/SL anchor)
    tight_norm = eng.normalize_two_entry_runner_levels(
        pair="B-INJ_USDT", direction="SHORT", entry1_px=7.090, entry2_px=None,
        tp1_px=6.950, tp2_px=6.800, sl_px=7.129, live_px=7.090, levels=None,
    )
    assert abs(tight_norm["stop_loss"] - 7.129) < 1e-4, f"Expected tight 15m 200 EMA SL preserved, got {tight_norm}"

    # 5. signal_monitor & execute_autotrade_two_entry_signal mode guards
    assert sm._autotrade_signal_eligible("box_theory", "LONG", "box_plus_ema50_200_bear") is True
    assert sm._autotrade_signal_eligible("ema50_200", "SHORT", "box_plus_ema50_200_bear") is True
    assert sm._autotrade_signal_eligible("ema50_200", "LONG", "box_plus_ema50_200_bear") is False
    assert sm._autotrade_signal_eligible("ema50_200", "LONG", "box_plus_ema50_200_both") is True

    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg), \
             patch.object(eng, "is_staging_environment", return_value=True), \
             patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]), \
             patch.object(eng, "fetch_coindcx_futures_balance", return_value={"is_live_api": False, "total_inr": 60000.0, "available_inr": 60000.0}), \
             patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}), \
             patch.object(eng, "fetch_live_ticker", return_value={"last_price": 7.090}), \
             patch("sheets_logger.log_trade_to_google_sheet", return_value=True):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            eng.save_autotrade_config({"autotrade_strategy_mode": "box_plus_ema50_200_bear"})
            with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_UPTREND", "summary": "CLEAN_UPTREND"}):
                ok_blk, msg_blk, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-INJ_USDT",
                    sig={"signal": "LONG", "strategy_id": "ema50_200", "entry": 7.24, "tp1": 7.38, "tp2": 7.60, "stop_loss": 7.12, "levels": bull_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert not ok_blk and "Bear-Only 15m 50/200 EMA" in msg_blk, f"Expected Bear-Only mode block on EMA LONG, got: {ok_blk} {msg_blk}"
            with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}):
                ok_ema_s, msg_ema_s, meta_ema_s = eng.execute_autotrade_two_entry_signal(
                    pair="B-INJ_USDT",
                    sig={"signal": "SHORT", "strategy_id": "ema50_200", "entry": 7.090, "tp1": 6.950, "tp2": 6.800, "stop_loss": 7.185, "levels": bear_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert ok_ema_s, f"Expected Bearish EMA50/200 SHORT allowed in Combo Bear mode, got: {ok_ema_s} {msg_ema_s}"
                assert abs(meta_ema_s["lock"]["stop_loss"] - 7.185) < 1e-4, f"Expected EMA SL preserved in lock: {meta_ema_s['lock']}"

    print("  -> PASS: 15m 50/200 EMA Pullback, Bear/Both Combo Modes & Tight 200 EMA SL preservation verified.")


def test_12_sidebar_unlock_autotrade():
    print("[12/12] Verifying Sidebar 'Unlock AutoTrade' button & Daily Loss Stop unlock...")
    import tempfile
    import coindcx_engine as eng

    with open(os.path.join(ROOT_DIR, "app.py"), "r", encoding="utf-8") as f_app:
        app_src = f_app.read()
    assert '"🔓 Unlock AutoTrade"' in app_src and "unlock_autotrade_daily_loss_stop" in app_src

    today_s = eng.datetime.now(eng.IST).strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            eng.save_autotrade_config({
                "enabled": True,
                "daily_start_wallet": {"date": today_s, "inr": 69788.04},
                "daily_loss_stop_hit": today_s,
            })
            w_now = {"is_live_api": True, "total_inr": 56698.93, "available_inr": 56698.93}
            hit_before, msg_before, _ = eng.check_live_daily_loss_stop(w_now)
            assert hit_before and "5% Daily Loss Stop" in msg_before

            ds_new = eng.unlock_autotrade_daily_loss_stop(w_now)
            assert abs(ds_new["inr"] - 56698.93) < 0.02
            assert eng.get_autotrade_config().get("daily_loss_stop_hit") == ""

            hit_after, _, info_after = eng.check_live_daily_loss_stop(w_now)
            assert not hit_after and abs(info_after["day_start_inr"] - 56698.93) < 0.02
    print("  -> PASS: Sidebar 'Unlock AutoTrade' cleanly unlocks 5% Daily Loss Stop & syncs wallet baseline.")


def test_13_regime_adaptive_routing_and_structure_tp1():
    print("[13/13] Verifying Market-Regime Classifier, Regime-Adaptive Routing, 3h Structure-Aware TP1 & Max 2 EMA Slots...")
    import tempfile
    import coindcx_engine as eng
    import strategies as strat
    import signal_monitor as sm

    # 1. Market Trend Regime Classifier across all 3 market conditions
    assert eng.classify_universe_regime_from_stats(0.67, 0.08, 12.4, 4.2, 1.8) == "STRONG_UPTREND"
    assert eng.classify_universe_regime_from_stats(0.0, 0.83, -18.7, -11.7, -7.3) == "STRONG_DOWNTREND"
    # Post-crash inside-bar / relief consolidation (like Nov 17: bear=83%, r14=-17.9%, r5=-12.1%, r2=+2.27%) -> RANGING_CHOP!
    assert eng.classify_universe_regime_from_stats(0.0, 0.83, -17.9, -12.1, 2.27) == "RANGING_CHOP"
    assert eng.classify_universe_regime_from_stats(0.25, 0.33, -1.2, 0.4, 0.2) == "RANGING_CHOP"

    # 2. Experiment 15m 50/200 EMA: CHOP_RANGE blocked; RL < 15% ROE falls back to +15% ROE; 3rd EMA slot ALLOWED (Max 2 EMA cap removed)
    bear_box = {"trend_bias": "BEARISH", "RH": 7.50, "RL": 7.00, "MID": 7.25, "SH": 7.60, "SL": 6.72}
    recs_tight_rl = [
        {"open": 7.11, "high": 7.14, "low": 7.06, "close": 7.09},
        {"open": 7.09, "high": 7.10, "low": 7.05, "close": 7.06},  # entry=7.05; RL=7.00 is only 0.71% (<15% ROE = 1.5% -> TP must be +15% ROE = 6.94425)
    ]
    assert strat._detect_ema50_200_setup(
        recs_tight_rl, 1, bear_box, ema50_val=7.12, ema200_val=7.18,
        allow_bear=True, allow_bull=True, intraday_regime="CHOP_RANGE", leverage=10, prev_ema50_val=7.12,
    ) is None, "Expected CHOP_RANGE to block EMA50/200 setup"
    sig_roe15 = strat._detect_ema50_200_setup(
        recs_tight_rl, 1, bear_box, ema50_val=7.12, ema200_val=7.18,
        allow_bear=True, allow_bull=True, intraday_regime="CLEAN_DOWNTREND", leverage=10, prev_ema50_val=7.12,
    )
    assert sig_roe15 is not None and abs(sig_roe15["tp2"] - (7.05 * 0.985)) < 1e-4 and "+15% ROE" in sig_roe15["tp1_label"], sig_roe15

    # 3. Intraday Trend Decision Matrix Guardrails: CHOP_RANGE blocks ALL trades; 3rd concurrent EMA trade ALLOWED (Guardrail #5 removed)
    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        now_t = time.time()
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg), \
             patch.object(eng, "is_staging_environment", return_value=True), \
             patch.object(eng, "fetch_coindcx_futures_balance", return_value={"is_live_api": False, "total_inr": 60000.0, "available_inr": 60000.0}), \
             patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}), \
             patch.object(eng, "fetch_live_ticker", return_value={"last_price": 7.090}), \
             patch("sheets_logger.log_trade_to_google_sheet", return_value=True):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            eng.save_autotrade_config({
                "autotrade_strategy_mode": "box_plus_ema50_200_regime",
                "history": [
                    {"pair": "B-SUI_USDT", "strategy_id": "ema50_200", "opened_ts": now_t - 600},
                    {"pair": "B-AVAX_USDT", "strategy_id": "ema50_200", "opened_ts": now_t - 300},
                ],
            })
            # CHOP_RANGE blocks BOTH EMA and Box trades!
            with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CHOP_RANGE", "summary": "CHOP_RANGE"}), \
                 patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]):
                ok_ch, msg_ch, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-INJ_USDT",
                    sig={"signal": "SHORT", "strategy_id": "ema50_200", "entry": 7.09, "tp1": 6.95, "tp2": 6.80, "stop_loss": 7.185, "levels": bear_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert not ok_ch and "CHOP / RANGE" in msg_ch, f"Expected CHOP_RANGE block on EMA, got {ok_ch} {msg_ch}"
                ok_ch_b, msg_ch_b, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-INJ_USDT",
                    sig={"signal": "SHORT", "strategy_id": "box_theory", "entry": 7.51, "tp1": 7.36, "tp2": 6.80, "stop_loss": 7.64, "levels": bear_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert not ok_ch_b and "CHOP / RANGE" in msg_ch_b, f"Expected CHOP_RANGE block on Box, got {ok_ch_b} {msg_ch_b}"

            # With 2 EMA trades open & CLEAN_DOWNTREND -> 3rd EMA trade IS ALLOWED (Guardrail #5 removed)!
            two_open = [{"pair": "B-SUI_USDT"}, {"pair": "B-AVAX_USDT"}]
            with patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}), \
                 patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=two_open):
                ok_ema3, msg_ema3, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-INJ_USDT",
                    sig={"signal": "SHORT", "strategy_id": "ema50_200", "entry": 7.09, "tp1": 6.95, "tp2": 6.80, "stop_loss": 7.185, "levels": bear_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert ok_ema3, f"Expected 3rd EMA trade allowed after removing Guardrail #5, got {ok_ema3} {msg_ema3}"

    print("  -> PASS: Market-Regime Classifier, Regime-Adaptive Routing, 3h Structure-Aware TP1 & Max 2 EMA Slots verified.")


def test_14_v34_three_fixes_slot_margin_and_apt_box_floor():
    print("[14/14] Verifying v34 Fixes: Resting-Order 3-Slot & Partial-Fill Guard, Exact Sidebar Margin (No Crumbs) & Bottom-of-Box/SL-Drift Guard...")
    import tempfile
    import coindcx_engine as eng
    import strategies as strat
    import signal_monitor as sm

    bear_box = {"trend_bias": "BEARISH", "RH": 7.50, "RL": 6.80, "MID": 7.15, "SH": 7.60, "SL": 6.72}

    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg), \
             patch("sheets_logger.log_trade_to_google_sheet", return_value=True):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None

            # --- FIX #2A: Custom Sidebar Margin (Rs.26,500 on Rs.53,750 wallet) persists across balance sync & is honored ---
            eng.save_autotrade_config({
                "single_trade_margin_inr": 26500.0,
                "user_custom_margin": True,
                "wallet_balance_inr": 53750.0,
                "autotrade_strategy_mode": "box_plus_ema50_200_regime",
            })
            assert "user_custom_margin" in eng._DURABLE_AUTOTRADE_KEYS
            assert "active_trade_locks" in eng._DURABLE_AUTOTRADE_KEYS
            w_53k = {"is_live_api": True, "total_inr": 53750.0, "available_inr": 53750.0}
            eff_cust, _ = eng.compute_wallet_capped_margin(26500.0, 10, w_53k, 3, honor_custom_margin=True)
            assert abs(eff_cust - 26500.0) < 0.01, f"Expected exact Rs.26,500 Sidebar margin honored, got {eff_cust}"

            # Simulate 25s background balance sync -> must NOT overwrite Rs.26,500 back to 1/3 wallet (Rs.17,916.67)!
            def _fake_wallet_200(method, url, payload=None, timeout=3.5):
                return _MockResponse(200, [{"currency_short_name": "INR", "balance": "53750.0", "locked_balance": "0.0", "cross_user_margin": "0.0"}]), None

            with patch.object(eng, "_send_coindcx_signed_request", side_effect=_fake_wallet_200):
                eng._fetch_coindcx_futures_balance_sync()
            assert abs(float(eng.get_autotrade_config()["single_trade_margin_inr"]) - 26500.0) < 0.01, (
                f"Balance sync overwrote user's Rs.26,500 Sidebar margin: {eng.get_autotrade_config()}"
            )

            # --- FIX #2B: Anti-Crumb Guard blocks leftover-cash dust trades (Rs.893 free vs Rs.26,500 Sidebar margin) ---
            w_crumb = {"is_live_api": True, "total_inr": 53750.0, "available_inr": 893.64}
            with patch.object(eng, "is_staging_environment", return_value=False), \
                 patch.object(eng, "is_experiment_environment", return_value=False), \
                 patch.object(eng, "fetch_coindcx_futures_balance", return_value=w_crumb), \
                 patch.object(eng, "check_live_daily_loss_stop", return_value=(False, "", {})):
                ok_cr, msg_cr, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-NEAR_USDT",
                    sig={"signal": "SHORT", "strategy_id": "box_theory", "entry": 3.405, "tp1": 3.35, "tp2": 3.25, "stop_loss": 3.46, "levels": bear_box},
                    single_trade_margin_inr=26500.0, leverage=10,
                )
                assert not ok_cr and "Insufficient Free Margin Guard" in msg_cr, f"Expected dust crumb trade blocked, got {ok_cr} {msg_cr}"

            # --- FIX #1A: Multi-pair `active_trade_locks` + Resting Open Entry Limit Orders enforce 3-Slot & Max 2 EMA ---
            eng.register_app_trade_lock(
                pair="B-APT_USDT", direction="SHORT", entry=0.4319, stop_loss=0.4446, tp1=0.4257, tp2=0.4195,
                margin_inr=17916.0, leverage=10, qty1=9899.1, is_live_exchange=True,
                strategy_id="ema50_200", entry1_order_id="oid_apt", entry1_pending=True,
            )
            eng.register_app_trade_lock(
                pair="B-FET_USDT", direction="SHORT", entry=0.1286, stop_loss=0.1310, tp1=0.1268, tp2=0.1245,
                margin_inr=17916.0, leverage=10, qty1=13650.0, is_live_exchange=True,
                strategy_id="ema50_200", entry1_order_id="oid_fet", entry1_pending=True,
            )
            locks_now = eng._get_active_locks_map()
            assert "B-APT_USDT" in locks_now and "B-FET_USDT" in locks_now, f"Multi-pair locks overwritten: {locks_now}"

            resting_ords = [
                {"id": "oid_apt", "pair": "B-APT_USDT", "side": "sell", "order_type": "limit_order", "status": "open", "stage": "default"},
                {"id": "oid_fet", "pair": "B-FET_USDT", "side": "sell", "order_type": "limit_order", "status": "open", "stage": "default"},
                # Opposite-side TP1 reduce order on an already-open INJ SHORT position must NOT double-count as a new entry!
                {"id": "oid_inj_tp1", "pair": "B-INJ_USDT", "side": "buy", "order_type": "limit_order", "status": "open", "stage": "default"},
            ]
            open_pos_1 = [{"id": "pos_inj", "pair": "B-INJ_USDT", "direction": "SHORT", "quantity": 25.0, "entry_price": 7.30}]
            entry_only = eng.get_open_entry_limit_orders(open_orders=resting_ords, live_positions=open_pos_1)
            assert [o["pair"] for o in entry_only] == ["B-APT_USDT", "B-FET_USDT"], f"Unexpected entry orders: {entry_only}"
            assert eng.count_open_ema50_200_slots(live_positions=open_pos_1, open_orders=resting_ords) == 2

            # With 1 filled position (INJ) + 2 resting entry limit orders (APT, FET) = 3 slots -> 4th trade (BTC) MUST be blocked!
            w_full = {"is_live_api": True, "total_inr": 60000.0, "available_inr": 40000.0}
            with patch.object(eng, "is_staging_environment", return_value=False), \
                 patch.object(eng, "is_experiment_environment", return_value=False), \
                 patch.object(eng, "fetch_coindcx_futures_balance", return_value=w_full), \
                 patch.object(eng, "check_live_daily_loss_stop", return_value=(False, "", {})), \
                 patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=open_pos_1), \
                 patch.object(eng, "fetch_coindcx_open_orders", return_value=resting_ords), \
                 patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False, "active_pairs": ["B-INJ_USDT"]}):
                eng.save_autotrade_config({"user_custom_margin": False, "single_trade_margin_inr": 20000.0})
                ok_4r, msg_4r, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-BTC_USDT",
                    sig={"signal": "SHORT", "strategy_id": "box_theory", "entry": 64200.0, "tp1": 63500.0, "tp2": 62500.0, "stop_loss": 64900.0, "levels": bear_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert not ok_4r and "3-Slot Wallet Guard" in msg_4r, f"Expected 3-Slot guard with resting orders, got {ok_4r} {msg_4r}"

            # --- FIX #1B: Dust partial fill (6.5 of 9,899.1 APT) keeps entry1_pending=True until >=50% filled ---
            eng.clear_autotrade_active_lock("B-FET_USDT")
            with patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[{
                "id": "pos_apt_dust", "pair": "B-APT_USDT", "direction": "SHORT", "quantity": 6.5,
                "entry_price": 0.4319, "mark_price": 0.4318, "leverage": 10, "stop_loss": None, "take_profit": None,
            }]), \
                 patch.object(eng, "update_coindcx_position_tpsl", return_value=(True, "OK")), \
                 patch.object(eng, "fetch_live_ticker", return_value={"last_price": 0.4318}):
                eng.get_active_portfolio_trade_status(manage_exchange=True)
                apt_lk = eng._get_active_locks_map()["B-APT_USDT"]
                assert apt_lk["entry1_pending"] is True and abs(apt_lk["target_qty1"] - 9899.1) < 0.1, (
                    f"Expected 6.5/9899.1 APT partial fill to keep entry1_pending=True, got {apt_lk}"
                )

            # --- FIX #3A: Bottom-of-Box APT 11:15 IST trap (z_pos=30.9% & room_3h=0.49%) & Extreme Bottom 15% blocked ---
            apt_box = {"trend_bias": "BEARISH", "RH": 0.4548, "RL": 0.4195, "MID": 0.4371, "SH": 0.4623, "SL": 0.4132}
            apt_recs = [{"open": 0.4312, "high": 0.4318, "low": 0.4283, "close": 0.4310} for _ in range(12)] + [
                {"open": 0.4312, "high": 0.4323, "low": 0.4301, "close": 0.4311},
                {"open": 0.4311, "high": 0.4322, "low": 0.4295, "close": 0.4304},  # z_pos = 30.9%, room_3h to 0.4283 = 0.488% < 0.55%!
            ]
            sig_apt_bot = strat._detect_ema50_200_setup(
                apt_recs, 13, apt_box, ema50_val=0.4317, ema200_val=0.4409,
                prior_e50=[0.4318] * 6, prior_e200=[0.4410] * 6, allow_bear=True, allow_bull=False,
            )
            assert sig_apt_bot is None, f"Expected APT bottom-of-box 0.49% dead-zone short blocked, got {sig_apt_bot}"

            # --- FIX #3B: Post-Nudge < 0.35% SL Price-Drift Guard (RENDER $1.4080 vs $1.4085 SL) ---
            eng.clear_autotrade_active_lock()
            with patch.object(eng, "is_staging_environment", return_value=True), \
                 patch.object(eng, "_fetch_coindcx_active_positions_sync", return_value=[]), \
                 patch.object(eng, "fetch_coindcx_futures_balance", return_value={"is_live_api": False, "total_inr": 60000.0, "available_inr": 60000.0}), \
                 patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}), \
                 patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}), \
                 patch.object(eng, "fetch_live_ticker", return_value={"last_price": 1.4079, "bid": 1.4078, "ask": 1.4080}):
                ok_dr, msg_dr, _ = eng.execute_autotrade_two_entry_signal(
                    pair="B-RENDER_USDT",
                    sig={"signal": "SHORT", "strategy_id": "ema50_200", "entry": 1.3870, "tp1": 1.3720, "tp2": 1.3450, "stop_loss": 1.4085, "levels": bear_box},
                    single_trade_margin_inr=20000.0, leverage=10,
                )
                assert not ok_dr and "Price Drift Guard" in msg_dr, f"Expected <0.35% SL drift guard block on RENDER, got {ok_dr} {msg_dr}"

            # --- FIX #3C: 4h (240m) Same-Price-Zone (0.8%) AutoTrade Re-Entry Lock in signal_monitor ---
            temp_state = os.path.join(tmpdir, "alert_state.json")
            key_apt = "ema50_200|B-APT_USDT|EMA50_200|SHORT"
            fake_apt_sig = {
                "signal": "SHORT", "signal_kind": "EMA50_200", "strategy_id": "ema50_200",
                "entry": 0.4320, "entry2_sweep": 0.0, "tp1": 0.4260, "tp2": 0.4195, "stop_loss": 0.4430,
                "roe_tp1": 13.8, "candle_ts": int(time.time() * 1000), "margin_inr": 20000.0, "leverage": 10,
                "trigger_zone": "15m 50/200 EMA CEILING", "trigger_reason": "Test", "levels": apt_box,
            }
            with patch.object(sm, "STATE_FILE", temp_state), \
                 patch.dict(sm._MEM_STATE, {
                     key_apt: {
                         "candle_ts": int(time.time() * 1000) - 8100000,
                         "sent_at": time.time() - 8100.0,       # 2h 15m ago (< 4h!)
                         "autotraded": True,
                         "autotraded_at": time.time() - 8100.0, # 2h 15m ago (< 4h!)
                         "direction": "SHORT",
                         "entry": 0.4319,                       # within 0.8% of 0.4320!
                     }
                 }, clear=True), \
                 patch.object(sm, "scan_pair", return_value=fake_apt_sig), \
                 patch.object(eng, "compute_pair_intraday_trend_stack", return_value={"regime": "CLEAN_DOWNTREND", "summary": "CLEAN_DOWNTREND"}), \
                 patch.object(eng, "compute_market_regime", return_value={"regime": "STRONG_DOWNTREND", "label": "STRONG DOWNTREND", "median_2d_pct": -4.0}), \
                 patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False, "active_pairs": []}), \
                 patch.object(eng, "fetch_coindcx_active_positions", return_value=[]), \
                 patch.object(eng, "execute_autotrade_two_entry_signal") as mock_exec_auto:
                sm._LAST_SCAN_CACHE["results"] = []
                res_re = sm.scan_and_alert(pairs=["B-APT_USDT"], send=False, strategy_ids=["ema50_200"], autotrade=True)
                assert not mock_exec_auto.called, f"Expected 4h same-zone lock to block 2h15m APT re-entry, got {res_re}"

    print("  -> PASS: All 3 v34 Fixes (Strict 3-Slot/Partial-Fill, Exact Sidebar Margin/No Crumbs, Box-Floor/SL-Drift/4h Lock) verified!")


def test_15_v35_funds_section_and_wallet_ledger():
    print("[15/15] Verifying Daemon v35 Funds Section, Transaction Pagination, Capital Accounting & Statement CSV Parser...")
    from unittest.mock import MagicMock
    import coindcx_engine as eng

    page1_tx = [
        {"id": f"tx_p1_{i}", "transaction_type": "credit", "amount": "1000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": 1760000000000 + i * 1000}
        for i in range(100)
    ]
    page2_tx = [
        {"id": "tx_p1_99", "transaction_type": "credit", "amount": "1000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": 1760000099000},  # duplicate
        {"id": "tx_p2_1", "transaction_type": "debit", "amount": "25000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": 1761000000000},
    ]

    def _fake_signed_req(method, url, payload=None, timeout=10.0):
        resp = MagicMock()
        if "users/balances" in url:
            resp.status_code = 200
            resp.json.return_value = [{"currency": "INR", "balance": "4500.50", "locked_balance": "0.0"}, {"currency": "USDT", "balance": "12.5", "locked_balance": "0"}]
            return resp, None
        if "size=1000" in url or "size=500" in url:
            resp.status_code = 422
            resp.text = "size too large"
            resp.json.return_value = {"message": "size too large"}
            return resp, None
        if "page=1&size=100" in url:
            resp.status_code = 200
            resp.json.return_value = page1_tx
            return resp, None
        if "page=2&size=100" in url:
            resp.status_code = 200
            resp.json.return_value = page2_tx
            return resp, None
        resp.status_code = 200
        resp.json.return_value = []
        return resp, None

    with patch.object(eng, "_get_coindcx_credentials", return_value=("k12345678", "s12345678")), \
         patch.object(eng, "_send_coindcx_signed_request", side_effect=_fake_signed_req):
        res_tx = eng.fetch_coindcx_futures_wallet_transactions(force_refresh=True, max_pages=10)
        assert res_tx["ok"] is True, res_tx
        assert len(res_tx["transactions"]) == 101, f"Expected 101 deduplicated tx, got {len(res_tx['transactions'])}"
        assert res_tx["pages_fetched"] == 2
        assert len(res_tx["spot_balances"]) == 2 and res_tx["spot_balances"][0]["currency"] == "INR"

    sample_tx = [
        {"id": "1", "transaction_type": "credit", "amount": "100000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": "2026-10-05T10:00:00Z"},
        {"id": "2", "transaction_type": "credit", "amount": "100", "currency_short_name": "USDT", "reason": "by_universal_wallet", "created_at": "2026-10-12T10:00:00Z"},  # @ 100 INR = 10,000
        {"id": "3", "transaction_type": "debit", "amount": "20000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": "2026-11-01T10:00:00Z"},
        {"id": "4", "transaction_type": "credit", "amount": "18500", "currency_short_name": "INR", "reason": "by_futures_order", "created_at": "2026-11-10T10:00:00Z"},
        {"id": "5", "transaction_type": "debit", "amount": "500", "currency_short_name": "INR", "reason": "by_futures_funding", "created_at": "2026-11-12T10:00:00Z"},
    ]
    summ = eng.compute_futures_funds_summary(
        transactions=sample_tx,
        wallet={"total_inr": 108000.0, "available_inr": 88000.0, "live_usd_inr": 100.0},
        positions=[{"pair": "B-BTC_USDT", "pnl_inr": 2000.0}],
        spot_balances=[{"currency": "INR", "total": 5000.0}],
        usd_inr=100.0,
    )
    assert summ["total_added_all_inr"] == 110000.0, summ
    assert summ["total_withdrawn_all_inr"] == 20000.0, summ
    assert summ["net_capital_inr"] == 90000.0, summ
    assert summ["peak_net_capital_inr"] == 110000.0, summ
    assert summ["current_realized_wallet_inr"] == 108000.0, summ
    assert summ["current_equity_inr"] == 110000.0, summ
    assert summ["realized_growth_inr"] == 18000.0 and summ["total_growth_inr"] == 20000.0, summ
    assert abs(summ["growth_pct_net_capital"] - 22.22) < 0.02, summ["growth_pct_net_capital"]
    assert summ["ledger_reconciliation_diff_inr"] == 0.0, summ["ledger_reconciliation_diff_inr"]
    assert len(summ["monthly_rows"]) == 2 and len(summ["transfers_rows"]) == 3

    # House-money safety (withdrew more than added -> net_capital <= 0 must not crash or divide by zero)
    hm_summ = eng.compute_futures_funds_summary(
        transactions=[
            {"id": "a", "transaction_type": "credit", "amount": "50000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": "2026-10-01T00:00:00Z"},
            {"id": "b", "transaction_type": "debit", "amount": "60000", "currency_short_name": "INR", "reason": "by_universal_wallet", "created_at": "2026-11-01T00:00:00Z"},
        ],
        wallet={"total_inr": 15000.0, "available_inr": 15000.0},
        usd_inr=100.0,
    )
    assert hm_summ["net_capital_inr"] == -10000.0 and hm_summ["growth_pct_net_capital"] is None and hm_summ["total_growth_inr"] == 25000.0

    csv_sample = (
        "Date,Type,Currency,Amount,Status\n"
        "2026-10-01,INR Deposit,INR,50000,Success\n"
        "2026-10-05,INR Deposit,INR,25000,Failed\n"
        "2026-10-15,INR Withdrawal,INR,15000,Completed\n"
    ).encode("utf-8")
    csv_res = eng.parse_coindcx_statement_csv(csv_sample)
    assert csv_res["ok"] and csv_res["total_deposited_inr"] == 50000.0 and csv_res["total_withdrawn_inr"] == 15000.0 and csv_res["net_bank_invested_inr"] == 35000.0

    print("  -> PASS: Daemon v35 Funds Section, Transaction Pagination, Capital Accounting & Statement CSV Parser verified!")


def test_16_three_tier_main_staging_experiment_parity():
    print("[16/16] Verifying 3-Tier Architecture (Main Live / Staging Paper + Staging_Trades / Experiment Parity Backtest)...")
    import tempfile
    import pandas as pd
    import coindcx_engine as eng
    import sheets_logger as sl

    # 1. Verify mutually exclusive 3-tier environment detection (main / staging / experiment)
    with patch.dict(os.environ, {"APP_ENV": "experiment"}):
        assert eng.is_experiment_environment() is True and eng.is_staging_environment() is False and eng.get_environment_tier() == "experiment"
    with patch.dict(os.environ, {"APP_ENV": "staging"}):
        assert eng.is_staging_environment() is True and eng.is_experiment_environment() is False and eng.get_environment_tier() == "staging"
    with patch.dict(os.environ, {"APP_ENV": "main"}):
        assert eng.is_staging_environment() is False and eng.is_experiment_environment() is False and eng.get_environment_tier() == "main"

    # 2. Verify Staging Paper Trading mirrors Main setup, enforces 5% Daily SL Threshold & Free-Margin Guard, and routes to Staging_Trades
    assert sl.STAGING_TRADES_SHEET_NAME == "Staging_Trades"
    assert sl._is_staging_paper_record({"status": "PAPER_AUTOTRADE_OPEN"}) is True
    assert sl._is_staging_paper_record({"exit_reason": "[STAGING PAPER] Stop Loss Hit"}) is True
    assert sl._is_staging_paper_record({"status": "LOGGED_PENDING", "strategy_name": "Box Theory Sweep (App Live Order)"}) is False

    today_s = eng.datetime.now(eng.IST).strftime("%Y-%m-%d")
    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg), \
             patch.dict(os.environ, {"APP_ENV": "staging"}), \
             patch.object(sl, "save_autotrade_state_to_sheet", return_value=True), \
             patch.object(sl, "log_trade_to_google_sheet", return_value=True), \
             patch.object(sl, "log_trade_closed", return_value=True):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            fake_main_setup = {
                "wallet_balance_inr": 24423.86,
                "single_trade_margin_inr": 8000.0,
                "user_custom_margin": True,
                "leverage": 10,
                "autotrade_strategy_mode": "box_plus_ema50_200_regime",
            }
            with patch.object(sl, "load_main_live_setup_from_sheet", return_value=fake_main_setup):
                ok_sy, msg_sy, cfg_sy = eng.sync_setup_from_main(reset_paper_wallet=True)
                assert ok_sy and abs(float(cfg_sy["paper_wallet_inr"]) - 24423.86) < 0.01, (ok_sy, msg_sy, cfg_sy)
                assert abs(float(cfg_sy["single_trade_margin_inr"]) - 8000.0) < 0.01

            # Simulate paper wallet dropping by Rs.1,500 (> 5% of Rs.24,423.86 = Rs.1,221.19) -> MUST lock Staging AutoTrade!
            eng.save_autotrade_config({
                "paper_wallet_inr": 22900.0,
                "paper_daily_start_wallet": {"date": today_s, "inr": 24423.86},
            })
            pw_snap = eng.get_paper_wallet_snapshot()
            hit_stg, msg_stg, info_stg = eng.check_live_daily_loss_stop(pw_snap)
            assert hit_stg and "5% Daily Loss Stop (Staging Paper)" in msg_stg, (hit_stg, msg_stg)
            assert info_stg.get("is_paper_wallet") is True

            # Verify execute_autotrade_two_entry_signal blocks new Staging paper trades while locked by 5% SL threshold
            ok_blk_sl, msg_blk_sl, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-SOL_USDT",
                sig={"signal": "SHORT", "strategy_id": "box_theory", "entry": 70.0, "tp1": 69.0, "tp2": 67.5, "stop_loss": 71.5, "levels": {"trend_bias": "BEARISH", "RH": 70.5, "RL": 67.5, "MID": 69.0, "SH": 71.2, "SL": 66.5}},
                single_trade_margin_inr=8000.0, leverage=10,
            )
            assert not ok_blk_sl and "5% Daily Loss Stop" in msg_blk_sl, (ok_blk_sl, msg_blk_sl)

            # Unlock Staging AutoTrade -> baseline syncs to Rs.22,900 and unlocks cleanly
            eng.unlock_autotrade_daily_loss_stop(pw_snap)
            hit_after_u, _, _ = eng.check_live_daily_loss_stop(eng.get_paper_wallet_snapshot())
            assert not hit_after_u

            # Verify Staging Paper Free-Margin Anti-Crumb Guard blocks 3rd trade when free paper margin < 90% of slot margin
            eng.save_autotrade_config({
                "paper_wallet_inr": 20000.0,
                "paper_daily_start_wallet": {"date": today_s, "inr": 20000.0},
                "daily_loss_stop_hit": "",
                "active_trade_locks": {
                    "B-BTC_USDT": {"pair": "B-BTC_USDT", "margin_inr": 8000.0, "is_live_exchange": False, "opened_ts": time.time()},
                    "B-ETH_USDT": {"pair": "B-ETH_USDT", "margin_inr": 8000.0, "is_live_exchange": False, "opened_ts": time.time()},
                },
            })
            # Remaining free paper margin = 20000 - 16000 = Rs.4,000 (< 90% of Rs.8,000)
            ok_fm_stg, msg_fm_stg, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-SOL_USDT",
                sig={"signal": "SHORT", "strategy_id": "box_theory", "entry": 70.0, "tp1": 69.0, "tp2": 67.5, "stop_loss": 71.5, "levels": {"trend_bias": "BEARISH", "RH": 70.5, "RL": 67.5, "MID": 69.0, "SH": 71.2, "SL": 66.5}},
                single_trade_margin_inr=8000.0, leverage=10,
            )
            assert not ok_fm_stg and "Insufficient Free Margin Guard" in msg_fm_stg, (ok_fm_stg, msg_fm_stg)

    # 3. Verify Experiment Backtest Engine enforces Main's 5% SL Threshold, Free-Margin Guard, & Guard Telemetry
    synth_trades = pd.DataFrame([
        # Trade 1 loses Rs.1,500 on 2026-11-10 (> 5% of Rs.24,000 = Rs.1,200) -> locks 2026-11-10!
        {"pair": "B-BTC_USDT", "strategy": "Box Theory Sweep", "direction": "SHORT", "entry_time": "2026-11-10 08:00", "exit_time": "2026-11-10 09:00", "entry_price": 60000.0, "exit_price": 61200.0, "roe_pct": -18.75, "net_pnl_inr": -1500.0, "fees_inr": 40.0, "is_win": False, "exit_reason": "SL"},
        # Trade 2 enters later on the SAME locked day 2026-11-10 -> MUST be blocked by 5% SL Threshold!
        {"pair": "B-ETH_USDT", "strategy": "Box Theory Sweep", "direction": "SHORT", "entry_time": "2026-11-10 11:00", "exit_time": "2026-11-10 13:00", "entry_price": 1700.0, "exit_price": 1650.0, "roe_pct": 25.0, "net_pnl_inr": 2000.0, "fees_inr": 40.0, "is_win": True, "exit_reason": "TP2"},
        # Trade 3 enters NEXT day 2026-11-11 -> allowed again!
        {"pair": "B-SOL_USDT", "strategy": "Box Theory Sweep", "direction": "SHORT", "entry_time": "2026-11-11 08:00", "exit_time": "2026-11-11 10:00", "entry_price": 70.0, "exit_price": 68.0, "roe_pct": 25.0, "net_pnl_inr": 2000.0, "fees_inr": 40.0, "is_win": True, "exit_reason": "TP2"},
    ])
    def _mock_bt(pair, **kwargs):
        sub = synth_trades[synth_trades["pair"] == pair].copy()
        return {"total_trades": len(sub), "win_count": int((sub["is_win"] == True).sum()), "loss_count": int((sub["is_win"] == False).sum()), "win_rate_pct": 50.0, "net_profit_inr": float(sub["net_pnl_inr"].sum()), "profit_factor": 1.0, "trades_df": sub}

    with patch.object(eng, "run_strategy_backtest", side_effect=_mock_bt):
        bt_res = eng.run_portfolio_single_slot_backtest(
            pairs=["B-BTC_USDT", "B-ETH_USDT", "B-SOL_USDT"],
            duration_days=30,
            margin_inr=8000.0,
            leverage=10,
            wallet_inr=24000.0,
            daily_loss_stop_pct=5.0,
            enforce_free_margin_guard=True,
        )
        ga_bt = bt_res["guards_audit"]
        assert bt_res["total_trades"] == 2, f"Expected ETH trade on locked day blocked, got {bt_res['total_trades']}"
        assert ga_bt["days_locked_by_sl_threshold"] == 1 and ga_bt["blocked_by_sl_threshold"] == 1, ga_bt
        assert ga_bt["locked_dates"] == ["2026-11-10"], ga_bt
        assert abs(bt_res["ending_wallet_inr"] - 24500.0) < 0.01, bt_res["ending_wallet_inr"]
        assert len(bt_res["equity_curve"]) == 2

    print("  -> PASS: 3-Tier Architecture (Main Live / Staging Paper + Staging_Trades / Experiment Parity Backtest) verified!")


def test_17_paper_trading_journal_fixes():
    print("[17/17] Verifying Paper Trading Journal Fixes (Multi-Slot Monitor, No 8h Silent Eviction, Strict Row Match, v35 Tag)...")
    import tempfile
    import coindcx_engine as eng
    import sheets_logger as sl

    assert eng._REQUIRED_DAEMON_VERSION == 35, f"Expected v35, got {eng._REQUIRED_DAEMON_VERSION}"

    # 1. Strict Staging_Trades row matching in log_trade_closed (direction + entry_time guard)
    fake_rows = [
        list(sl.STAGING_TRADES_HEADERS),
        ["2026-11-26 06:01:07 IST", "B-APT_USDT", "SHORT", "0.376", "0.3883", "0.3679", "0.3484", "200", "802.47", "10x", "", "", "PAPER_AUTOTRADE_OPEN", "Strategy 1", "[v35] open", "", "", "", "", "18499.48", ""],
    ]
    updated_cells = []
    appended_rows = []

    class _FakeWS:
        def get_all_values(self):
            return [list(r) for r in fake_rows]
        def update_cell(self, r, c, val):
            updated_cells.append((r, c, val))
        def update(self, rng, vals):
            updated_cells.append((rng, vals))
        def append_row(self, row):
            appended_rows.append(row)

    class _FakeBook:
        def worksheet(self, name):
            return _FakeWS()

    class _FakeClient:
        def open(self, name):
            return _FakeBook()

    with patch.object(sl, "_client", return_value=_FakeClient()):
        # A LONG close on B-APT_USDT must NEVER overwrite an open SHORT row!
        ok_mism, _ = sl.log_trade_closed({
            "entry_time": "2026-11-26 22:15:48 IST",
            "exit_time": "2026-11-26 22:15:48 IST",
            "pair": "B-APT_USDT",
            "direction": "LONG",
            "entry_price": 6.849,
            "exit_price": 7.12,
            "net_pnl_inr": 1382.04,
            "roe_pct": 38.39,
            "is_staging_paper": True,
            "exit_reason": "[STAGING PAPER | v35] Test",
        }, return_details=True)
        assert ok_mism and len(updated_cells) == 0 and len(appended_rows) == 1, (updated_cells, appended_rows)

        # Matching SHORT close with exact entry_time MUST update row 2 cleanly!
        ok_match, _ = sl.log_trade_closed({
            "entry_time": "2026-11-26 06:01:07 IST",
            "exit_time": "2026-11-26 09:00:00 IST",
            "pair": "B-APT_USDT",
            "direction": "SHORT",
            "entry_price": 0.376,
            "exit_price": 0.365,
            "net_pnl_inr": 200.0,
            "roe_pct": 24.9,
            "is_staging_paper": True,
            "exit_reason": "[STAGING PAPER | v35] TP2 Target Hit",
        }, return_details=True)
        assert ok_match and len(updated_cells) == 2 and updated_cells[0][0] == 2, updated_cells

    # 2. Multi-slot paper monitor + No 8h silent eviction for filled paper trades + v35 tagging (all sheet calls mocked)
    with tempfile.TemporaryDirectory() as tmpdir:
        t_cfg = os.path.join(tmpdir, "autotrade_config.json")
        closed_payloads = []
        opened_payloads = []
        with patch.object(eng, "AUTOTRADE_CONFIG_FILE", t_cfg), \
             patch.dict(os.environ, {"APP_ENV": "staging"}), \
             patch.object(sl, "save_autotrade_state_to_sheet", return_value=True), \
             patch.object(sl, "log_trade_to_google_sheet", side_effect=lambda d, **kw: opened_payloads.append(d) or True), \
             patch.object(sl, "log_trade_closed", side_effect=lambda d, **kw: closed_payloads.append(d) or True):
            eng._AUTOTRADE_CFG_MEM_CACHE["data"] = None
            eng.save_autotrade_config({
                "paper_wallet_inr": 20000.0,
                "paper_starting_wallet_inr": 20000.0,
                "paper_realized_pnl_inr": 0.0,
                "active_trade_locks": {},
                "active_trade_lock": None,
            })

            # Open 2 paper trades via register_app_trade_lock -> verify [v35] tag stamped
            eng.register_app_trade_lock(
                pair="B-ETH_USDT", direction="SHORT", entry=1700.0, tp1=1680.0, tp2=1650.0, stop_loss=1750.0,
                margin_inr=5000.0, leverage=10, qty1=0.3, mode="Staging Paper AutoTrade (Live Market)",
                is_live_exchange=False, strategy_id="box_theory",
            )
            eng.register_app_trade_lock(
                pair="B-NEAR_USDT", direction="SHORT", entry=3.00, tp1=2.95, tp2=2.85, stop_loss=3.10,
                margin_inr=5000.0, leverage=10, qty1=160.0, mode="Staging Paper AutoTrade (Live Market)",
                is_live_exchange=False, strategy_id="ema50_200",
            )
            assert len(opened_payloads) == 2 and all("[v35]" in p.get("trigger_reason", "") for p in opened_payloads), opened_payloads

            # Age BOTH filled paper locks to 10 hours old (> 8h) -> MUST NOT be silently evicted!
            cfg_now = eng.get_autotrade_config()
            locks_now = eng._get_active_locks_map(cfg_now)
            for lk in locks_now.values():
                lk["opened_ts"] = time.time() - 10 * 3600
            eng.save_autotrade_config({"active_trade_locks": locks_now, "active_trade_lock": locks_now["B-NEAR_USDT"]})

            # Neutral prices (neither TP1/TP2/SL hit) -> both must stay open!
            def _neutral_tk(pair):
                return {"last_price": 1705.0 if pair == "B-ETH_USDT" else 3.01}

            with patch.object(eng, "fetch_live_ticker", side_effect=_neutral_tk), \
                 patch.object(eng, "_check_recent_15m_tp1_touch_and_prev_hl", return_value=(False, None, None)):
                mon1 = eng.get_active_portfolio_trade_status(manage_exchange=True)
            assert mon1.get("has_active_trade") and len(eng._get_active_locks_map()) == 2, (mon1, eng._get_active_locks_map())

            # Now ETH hits SL (1760) AND NEAR hits TP2 (2.80) in the SAME daemon pass -> BOTH must close & settle!
            def _exit_tk(pair):
                return {"last_price": 1760.0 if pair == "B-ETH_USDT" else 2.80}

            with patch.object(eng, "fetch_live_ticker", side_effect=_exit_tk), \
                 patch.object(eng, "_check_recent_15m_tp1_touch_and_prev_hl", return_value=(False, None, None)):
                mon2 = eng.get_active_portfolio_trade_status(manage_exchange=True)
            assert not mon2.get("is_occupied") and len(eng._get_active_locks_map()) == 0, (mon2, eng._get_active_locks_map())
            assert len(closed_payloads) == 2, closed_payloads
            assert all("[STAGING PAPER | v35]" in cp.get("exit_reason", "") for cp in closed_payloads), closed_payloads
            # Verify paper_wallet_inr settled BOTH trades accurately!
            expected_net = round(sum(float(cp["net_pnl_inr"]) for cp in closed_payloads), 2)
            cfg_end = eng.get_autotrade_config()
            assert abs(float(cfg_end["paper_realized_pnl_inr"]) - expected_net) < 0.05, (cfg_end["paper_realized_pnl_inr"], expected_net)
            assert abs(float(cfg_end["paper_wallet_inr"]) - round(20000.0 + expected_net, 2)) < 0.05, cfg_end["paper_wallet_inr"]

    print("  -> PASS: Paper Trading Journal Fixes verified (Multi-Slot Monitor, No 8h Silent Eviction, Strict Row Match, v35 Tag)!")


def test_18_experiment_intraday_matrix_and_ema50_200_rules():
    print("[18/18] Verifying Experiment Intraday Trend Matrix, Box Sweep (No Daily 50 EMA), New 15m 50/200 EMA Engine & 3-Slot Unlimited EMA...")
    import pandas as pd
    import coindcx_engine as eng
    import strategies as strat

    # 1. Box Sweep item #2 (Daily 50 EMA rejection/bounce) MUST be removed
    box_strat = strat.BoxTheorySweep()
    # Price is well inside Box (RH=110, RL=90), touching Daily 50 EMA=100, red candle closing < prev_close
    recs_d50 = [
        {"date_str": "2026-10-01", "open": 99.8, "high": 100.1, "low": 99.4, "close": 99.9},
        {"date_str": "2026-10-01", "open": 99.9, "high": 100.2, "low": 99.1, "close": 99.3},
    ]
    d50_levels = {"trend_bias": "BEARISH", "RH": 110.0, "RL": 90.0, "MID": 100.0, "SH": 112.0, "SL": 88.0, "ema50": 100.0}
    ctx_down = {"boxes": {"2026-10-01": d50_levels}, "ema50_15m": [100.0, 100.0], "intraday": [{"regime": "CLEAN_DOWNTREND"}, {"regime": "CLEAN_DOWNTREND"}]}
    ctx_chop = {"boxes": {"2026-10-01": d50_levels}, "ema50_15m": [100.0, 100.0], "intraday": [{"regime": "CHOP_RANGE"}, {"regime": "CHOP_RANGE"}]}
    ctx_up = {"boxes": {"2026-10-01": d50_levels}, "ema50_15m": [100.0, 100.0], "intraday": [{"regime": "CLEAN_UPTREND"}, {"regime": "CLEAN_UPTREND"}]}
    assert box_strat.backtest_entry(1, recs_d50[1], ctx_down, recs_d50) is None, "Daily 50 EMA rejection (#2) should be removed from Box Sweep!"

    # Box Sweep item #1 (RH Sweep Rejection) MUST fire in CLEAN_DOWNTREND, MUST be blocked in CHOP_RANGE & CLEAN_UPTREND
    recs_rh = [
        {"date_str": "2026-10-01", "open": 109.5, "high": 110.6, "low": 109.2, "close": 109.8},
        {"date_str": "2026-10-01", "open": 109.8, "high": 110.4, "low": 108.8, "close": 109.0},
    ]
    assert box_strat.backtest_entry(1, recs_rh[1], ctx_chop, recs_rh) is None
    assert box_strat.backtest_entry(1, recs_rh[1], ctx_up, recs_rh) is None
    sig_rh = box_strat.backtest_entry(1, recs_rh[1], ctx_down, recs_rh)
    assert sig_rh is not None and sig_rh["direction"] == "SHORT", f"Expected RH Sweep SHORT in CLEAN_DOWNTREND, got {sig_rh}"

    # 2. End-to-end 15m 50/200 EMA backtest: Trigger -> Confirm -> Breakout fill -> Trailing 200 EMA SL & >15% ROE TP
    # Construct synthetic 15m & daily dataframes with a clean downtrend and known EMA50/EMA200
    n_bars = 260
    t0 = int(pd.Timestamp("2026-09-01 00:00:00").timestamp() * 1000)
    rows_15m = []
    # Smooth downtrend from 120 down to 96 so 15m 50 EMA < 200 EMA
    for k in range(n_bars):
        px = 120.0 - (k * 0.09)
        rows_15m.append({
            "timestamp": t0 + k * 900_000,
            "open": px + 0.08,
            "high": px + 0.14,
            "low": px - 0.12,
            "close": px,
            "volume": 1000.0,
        })
    df_15 = pd.DataFrame(rows_15m)
    e50_arr = df_15["close"].ewm(span=50, adjust=False).mean().to_numpy()
    e200_arr = df_15["close"].ewm(span=200, adjust=False).mean().to_numpy()
    # Inject Trigger at bar 230: red candle, high >= e50, close < e50
    t_idx = 230
    e50_t = float(e50_arr[t_idx])
    df_15.loc[t_idx, ["open", "high", "low", "close"]] = [e50_t - 0.05, e50_t + 0.15, e50_t - 0.35, e50_t - 0.20]
    # Inject Confirm at bar 231: closes < trig.close, low = conf_low
    conf_low = round(e50_t - 0.60, 4)
    df_15.loc[t_idx + 1, ["open", "high", "low", "close"]] = [e50_t - 0.20, e50_t - 0.15, conf_low, e50_t - 0.45]
    # Bar 232 breaks below conf_low (fills breakout SHORT at conf_low)
    df_15.loc[t_idx + 2, ["open", "high", "low", "close"]] = [e50_t - 0.45, e50_t - 0.40, conf_low - 0.40, conf_low - 0.30]
    # Bar 233 drops past +15% ROE (at 10x -> -1.5% move) & RL to hit TP
    df_15.loc[t_idx + 3, ["open", "high", "low", "close"]] = [conf_low - 0.30, conf_low - 0.25, conf_low * 0.94, conf_low * 0.95]

    daily_rows = []
    d0 = int(pd.Timestamp("2026-08-20 00:00:00").timestamp() * 1000)
    for d in range(25):
        px = 130.0 - d * 1.2
        daily_rows.append({"timestamp": d0 + d * 86_400_000, "open": px + 1.0, "high": px + 3.0, "low": px - 4.0, "close": px, "volume": 50000.0})
    df_1d = pd.DataFrame(daily_rows)

    e50_post = df_15["close"].ewm(span=50, adjust=False).mean().to_numpy()
    e200_post = df_15["close"].ewm(span=200, adjust=False).mean().to_numpy()
    fake_intraday = [
        {
            "timestamp": int(df_15["timestamp"].iloc[k]),
            "regime": "CLEAN_DOWNTREND" if k >= t_idx else "CHOP_RANGE",
            "htf_1h": "DOWN",
            "htf_4h": "DOWN",
            "vwap_state": "BEAR_VWAP",
            "ema_state": "BEAR_EMA",
            "adx14": 32.0,
            "ema9": float(e50_post[k]),
            "ema50": float(e50_post[k]),
            "ema200": float(e200_post[k]),
        }
        for k in range(len(df_15))
    ]
    def _fake_paginated(pair="B-ETH_USDT", interval="15m", duration_days=30, progress_callback=None):
        return df_1d.copy() if interval == "1d" else df_15.copy()

    with patch.object(eng, "fetch_historical_candles_paginated", side_effect=_fake_paginated), \
         patch.object(eng, "compute_intraday_3layer_series", return_value=fake_intraday):
        res_bt = eng.run_strategy_backtest(
            pair="B-ETH_USDT", duration_days=3, margin_inr=100000.0, leverage=10, strategy_id="ema50_200"
        )
        assert res_bt["total_trades"] >= 1, f"Expected >=1 EMA50/200 breakout trade, got {res_bt}"
        tdf = res_bt["trades_df"]
        first_tr = tdf.iloc[0]
        assert first_tr["direction"] == "SHORT"
        assert abs(float(first_tr["entry_price"]) - conf_low) < 1e-3, f"Expected fill at conf.low {conf_low}, got {first_tr['entry_price']}"
        assert float(first_tr["roe_pct"]) >= 14.0 and first_tr["is_win"] == True, f"Expected winning >=15% ROE exit, got {first_tr.to_dict()}"

    # 3. Portfolio backtest allows 3 concurrent EMA50/200 trades simultaneously (Guardrail #5 removed)
    conc_trades = pd.DataFrame([
        {"pair": "B-BTC_USDT", "strategy": "15m 50/200 EMA Pullback", "direction": "SHORT", "entry_time": "2026-11-10 08:00", "exit_time": "2026-11-10 12:00", "entry_price": 60000.0, "exit_price": 59100.0, "roe_pct": 15.0, "net_pnl_inr": 14000.0, "fees_inr": 1000.0, "is_win": True, "exit_reason": "TP (+15% ROE)"},
        {"pair": "B-ETH_USDT", "strategy": "15m 50/200 EMA Pullback", "direction": "SHORT", "entry_time": "2026-11-10 08:15", "exit_time": "2026-11-10 12:15", "entry_price": 3000.0, "exit_price": 2955.0, "roe_pct": 15.0, "net_pnl_inr": 14000.0, "fees_inr": 1000.0, "is_win": True, "exit_reason": "TP (+15% ROE)"},
        {"pair": "B-SOL_USDT", "strategy": "15m 50/200 EMA Pullback", "direction": "SHORT", "entry_time": "2026-11-10 08:30", "exit_time": "2026-11-10 12:30", "entry_price": 150.0, "exit_price": 147.75, "roe_pct": 15.0, "net_pnl_inr": 14000.0, "fees_inr": 1000.0, "is_win": True, "exit_reason": "TP (+15% ROE)"},
        {"pair": "B-AVAX_USDT", "strategy": "15m 50/200 EMA Pullback", "direction": "SHORT", "entry_time": "2026-11-10 08:45", "exit_time": "2026-11-10 12:45", "entry_price": 30.0, "exit_price": 29.55, "roe_pct": 15.0, "net_pnl_inr": 14000.0, "fees_inr": 1000.0, "is_win": True, "exit_reason": "TP (+15% ROE)"},
    ])
    def _mock_bt3(pair, **kwargs):
        sub = conc_trades[conc_trades["pair"] == pair].copy()
        return {"total_trades": len(sub), "win_count": len(sub), "loss_count": 0, "win_rate_pct": 100.0, "net_profit_inr": float(sub["net_pnl_inr"].sum()), "profit_factor": 99.0, "trades_df": sub}

    with patch.object(eng, "run_strategy_backtest", side_effect=_mock_bt3):
        p_res = eng.run_portfolio_single_slot_backtest(
            pairs=["B-BTC_USDT", "B-ETH_USDT", "B-SOL_USDT", "B-AVAX_USDT"],
            duration_days=30, margin_inr=100000.0, leverage=10, strategy_id="ema50_200",
            max_concurrent_trades=3, wallet_inr=300000.0, daily_loss_stop_pct=5.0,
        )
        assert p_res["total_trades"] == 3, f"Expected all 3 concurrent EMA slots filled (4th blocked by 3-slot cap), got {p_res['total_trades']}"

    print("  -> PASS: Experiment Intraday Trend Matrix, Box Sweep (No Daily 50 EMA), New 15m 50/200 EMA Engine & 3-Slot Unlimited EMA verified!")


if __name__ == "__main__":
    test_1_syntax_and_imports()
    test_2_simulated_200_ok_wallet_and_positions_no_recursion()
    test_3_ui_non_blocking_latency_gate()
    test_4_strategy_and_two_entry_levels()
    test_5_daily_bias_enforcement()
    test_6_deployment_regression_guards()
    test_7_ui_render_and_navigation_tabs_integrity()
    test_8_stale_cache_expiry_and_nat_pinner()
    test_9_ai_advisor_and_tick_precision()
    test_10_strategy3_four_improvements_and_staging_paper_autotrade()
    test_11_ema50_200_pullback_and_combo_modes()
    test_12_sidebar_unlock_autotrade()
    test_13_regime_adaptive_routing_and_structure_tp1()
    test_14_v34_three_fixes_slot_margin_and_apt_box_floor()
    test_15_v35_funds_section_and_wallet_ledger()
    test_16_three_tier_main_staging_experiment_parity()
    test_17_paper_trading_journal_fixes()
    test_18_experiment_intraday_matrix_and_ema50_200_rules()
    if "--live" in sys.argv:
        test_10_live_cloud_deployments_sync()
    print("\nALL AUTOMATED CHECKS PASSED (100%)!")
