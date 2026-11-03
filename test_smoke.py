"""
Pre-merge automated verification suite (`test_smoke.py`) for Crypto Trade Pro.
Run this on the `staging` branch before asking for merge approval into `main`:
    .venv\\Scripts\\python.exe test_smoke.py
"""
from __future__ import annotations

import os
import py_compile
import sys
import tempfile
import time
from unittest.mock import patch

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
    print("[1/4] Checking syntax & compilation across core modules...")
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
    print("[2/4] Testing simulated 200 OK CoinDCX Wallet & Positions under strict recursion guard...")
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
    print("[3/4] Checking UI non-blocking latency gate (< 5.0 ms per call)...")
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
    print("[4/4] Verifying 2-Entry + Runner level normalization (LONG & SHORT)...")
    import coindcx_engine as eng

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
    print(f"  -> PASS: LONG ({long_lvls}) & SHORT ({short_lvls}) level invariants verified.")


def test_5_daily_bias_enforcement():
    print("[5/5] Verifying strict Daily 50 & 200 EMA Bias enforcement (BoxTheorySweep + AutoTrade Guard)...")
    import coindcx_engine as eng
    import strategies as strat

    # 1. Verify BoxTheorySweep returns NEUTRAL (NO TRADE) when trend_bias is NEUTRAL (e.g. INJ between 50 & 200 EMA)
    neutral_levels = {
        "RH": 7.31, "RL": 6.89, "SH": 7.43, "SL": 6.86, "MID": 7.10,
        "EMA50": 7.38, "EMA200": 6.10, "daily_close": 7.29, "trend_bias": "NEUTRAL"
    }
    box_sig = strat.get_strategy("box_theory").evaluate_signal("B-INJ_USDT", levels=neutral_levels)
    assert box_sig is not None and box_sig.get("signal") == "NEUTRAL", (
        f"Expected NEUTRAL (WAIT/NO TRADE) when trend_bias is NEUTRAL, got: {box_sig}"
    )

    # 2. Verify AutoTrade Guard blocks NEUTRAL bias, blocks LONG in BEARISH, and blocks SHORT in BULLISH
    with patch.object(eng, "get_active_portfolio_trade_status", return_value={"is_occupied": False}):
        ok_n, msg_n, _ = eng.execute_autotrade_two_entry_signal(
            pair="B-INJ_USDT",
            sig={"signal": "SHORT", "entry": 7.30, "entry2_sweep": 7.34, "tp1": 7.15, "tp2": 6.89, "stop_loss": 7.37, "levels": neutral_levels},
            single_trade_margin_inr=15762.39,
            leverage=10,
        )
        assert not ok_n and "Daily Bias Guard" in msg_n, f"Expected NEUTRAL bias block, got: {ok_n} {msg_n}"

        bear_levels = {**neutral_levels, "EMA50": 1.73, "EMA200": 1.72, "daily_close": 1.50, "trend_bias": "BEARISH"}
        ok_b, msg_b, _ = eng.execute_autotrade_two_entry_signal(
            pair="B-RENDER_USDT",
            sig={"signal": "LONG", "entry": 1.50, "entry2_sweep": 1.49, "tp1": 1.53, "tp2": 1.59, "stop_loss": 1.48, "levels": bear_levels},
            single_trade_margin_inr=15762.39,
            leverage=10,
        )
        assert not ok_b and "Daily Bias Guard" in msg_b, f"Expected counter-trend LONG in BEARISH block, got: {ok_b} {msg_b}"

        bull_levels = {**neutral_levels, "EMA50": 85.0, "EMA200": 80.0, "daily_close": 92.0, "trend_bias": "BULLISH"}
        ok_u, msg_u, _ = eng.execute_autotrade_two_entry_signal(
            pair="B-SOL_USDT",
            sig={"signal": "SHORT", "entry": 92.0, "entry2_sweep": 92.5, "tp1": 90.5, "tp2": 88.0, "stop_loss": 93.0, "levels": bull_levels},
            single_trade_margin_inr=15762.39,
            leverage=10,
        )
        assert not ok_u and "Daily Bias Guard" in msg_u, f"Expected counter-trend SHORT in BULLISH block, got: {ok_u} {msg_u}"

    print("  -> PASS: NEUTRAL bias (INJ), LONG-in-BEARISH (RENDER), and SHORT-in-BULLISH strictly blocked.")


if __name__ == "__main__":
    test_1_syntax_and_imports()
    test_2_simulated_200_ok_wallet_and_positions_no_recursion()
    test_3_ui_non_blocking_latency_gate()
    test_4_strategy_and_two_entry_levels()
    test_5_daily_bias_enforcement()
    print("\nALL STAGING PRE-MERGE CHECKS PASSED!")
