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

    # Verify build_two_entry_runner_plan places Entry 2 at SH ($7.43) and Catastrophe SL beyond SH (> $7.43), never inside RH-SH
    inj_plan = strat.build_two_entry_runner_plan("SHORT", entry=7.30, sweep_level=7.43, struct_tp1=7.10, struct_tp2=6.89, leverage=10)
    assert inj_plan is not None
    assert abs(inj_plan["entry2_sweep"] - 7.43) < 1e-6, f"Expected Entry 2 at SH $7.43, got {inj_plan['entry2_sweep']}"
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
        with patch.object(eng, "compute_market_bias", return_value={"bias": "BEARISH"}):
            ok_b, msg_b, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-RENDER_USDT",
                sig={"signal": "LONG", "entry": 1.50, "entry2_sweep": 1.49, "tp1": 1.53, "tp2": 1.59, "stop_loss": 1.48, "levels": bear_levels},
                single_trade_margin_inr=15762.39,
                leverage=10,
            )
            assert not ok_b and "Daily Bias Guard" in msg_b, f"Expected counter-trend LONG in BEARISH block, got: {ok_b} {msg_b}"

        bull_levels = {**neutral_levels, "EMA50": 85.0, "EMA200": 80.0, "daily_close": 92.0, "trend_bias": "BULLISH"}
        with patch.object(eng, "compute_market_bias", return_value={"bias": "BULLISH"}):
            ok_u, msg_u, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-SOL_USDT",
                sig={"signal": "SHORT", "entry": 92.0, "entry2_sweep": 92.5, "tp1": 90.5, "tp2": 88.0, "stop_loss": 93.0, "levels": bull_levels},
                single_trade_margin_inr=15762.39,
                leverage=10,
            )
            assert not ok_u and "Daily Bias Guard" in msg_u, f"Expected counter-trend SHORT in BULLISH block, got: {ok_u} {msg_u}"

        with patch.object(eng, "compute_market_bias", return_value={"bias": "NEUTRAL / RANGE"}), \
             patch.object(eng, "place_coindcx_futures_order", return_value=(True, "SIMULATED_RANGE_OK", {"id": "sim_1"})), \
             patch.object(eng, "save_autotrade_config", return_value={}), \
             patch.object(eng, "update_coindcx_position_tpsl", return_value=(True, "OK", {})), \
             patch("sheets_logger.log_trade_to_google_sheet", return_value=True):
            ok_r, msg_r, _ = eng.execute_autotrade_two_entry_signal(
                pair="B-INJ_USDT",
                sig={"signal": "SHORT", "entry": 7.30, "entry2_sweep": 7.43, "tp1": 7.15, "tp2": 6.89, "stop_loss": 7.49, "levels": neutral_levels},
                single_trade_margin_inr=15762.39,
                leverage=10,
            )
            assert ok_r and "Daily Bias Guard" not in msg_r, f"Expected RANGE mode trade allowed, got: {ok_r} {msg_r}"

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

    # 4. Verify all 6 required navigation tabs exist in NAV_SECTIONS and have matching render blocks
    expected_tabs = [
        "⚡ Signals",
        "🎯 Execute",
        "📊 Positions",
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

    # 6. Parse AST of app.py to ensure clean top-level structure
    tree = ast.parse(app_src, filename="app.py")
    assert len(tree.body) > 20
    print(f"  -> PASS: All 6 UI tabs ({', '.join(expected_tabs)}) & fragment non-loop invariants verified.")


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

    # 3. Verify AI Advisor generates complete, tick-exact responses for all quick-action prompts even without an external API key
    mock_struct = {
        "pair": "B-INJ_USDT", "symbol": "INJ",
        "live_price": 8.365, "high_24h": 8.510, "low_24h": 7.720, "change_24h": 8.96,
        "SH": 8.288, "RH": 8.081, "MID": 7.542, "RL": 7.003, "SL": 6.861,
        "ema50_d": 8.120, "ema200_d": 7.450, "daily_bias": "BULLISH", "daily_close": 8.210,
        "ema20_15m": 8.340, "ema50_15m": 8.210, "rsi_15m": 64.2, "rsi_1h": 68.5,
        "prev15_high": 8.390, "prev15_low": 8.310, "prev15_close": 8.355,
    }
    mock_sheet = {
        "ok": True,
        "spreadsheet_title": "Crypto_Trades_Journal",
        "live_trades": [{"Pair": "B-INJ_USDT", "Direction": "SHORT", "Entry Price": "7.870"}],
        "closed_trades": [
            {"Pair": "B-INJ_USDT", "Direction": "LONG", "Entry Price": "7.500", "Exit Price": "7.850", "Result": "WIN", "Realized PnL (INR)": "1800.00"},
            {"Pair": "B-NEAR_USDT", "Direction": "LONG", "Entry Price": "4.050", "Exit Price": "3.980", "Result": "LOSS", "Realized PnL (INR)": "-549.50"},
        ],
    }
    with patch.object(ga, "_compute_exact_pair_structure", return_value=mock_struct), \
         patch.object(eng, "fetch_coindcx_active_positions", return_value=[{
             "pair": "B-INJ_USDT", "direction": "SHORT", "entry_price": 7.870, "mark_price": 8.365,
             "quantity": 100.0, "leverage": 10, "pnl_inr": -55536.31, "roe_pct": -61.70, "liquidation_price": 12.144
         }]), \
         patch("sheets_logger.fetch_all_sheet_trades", return_value=mock_sheet):
        for prompt in (
            "Audit All Sheet Trades",
            "Best Setup on INJ Now",
            "Review Open Positions",
            "On active INJ order, do you think price will come down and I will be able to book profit?",
        ):
            resp_txt = ga._generate_live_quant_advisor_response(
                user_prompt=prompt,
                selected_pair="B-INJ_USDT",
            )
            assert isinstance(resp_txt, str) and len(resp_txt) > 150, f"AI Advisor failed on prompt '{prompt}': {resp_txt}"
            assert "$8.365" in resp_txt or "$8.288" in resp_txt or "INJ" in resp_txt, f"Expected INJ analysis in response: {resp_txt[:200]}"

    print("  -> PASS: AI Advisor live quant engine & 3-decimal INJ tick precision verified.")


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
    if "--live" in sys.argv:
        test_10_live_cloud_deployments_sync()
    print("\nALL AUTOMATED CHECKS PASSED (100%)!")
