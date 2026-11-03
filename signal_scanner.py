"""
Standalone signal scanner (24/7 CLI & GitHub Actions):  python signal_scanner.py [--interval 60] [--once]
Scans the High-Volatility Crypto Futures Watchlist at 10x leverage, enforces 1 Crypto at a Time,
sends email alerts, and executes 2-Entry + Runner AutoTrades when enabled in Sidebar config.
"""
import argparse
import time
from datetime import datetime

import coindcx_engine as eng
import signal_monitor as sm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="seconds between scans")
    ap.add_argument("--pairs", nargs="*", default=None)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    while True:
        auto_cfg = eng.get_autotrade_config()
        lev = int(auto_cfg.get("leverage", 10))
        rot = eng.get_rotational_margin_inr(lev)
        m_inr = float(auto_cfg.get("single_trade_margin_inr") or rot["margin_inr"])
        usd_inr = eng.get_coindcx_live_usdt_inr_rate()
        pairs = args.pairs or eng.get_high_volatility_watchlist(top_n=12)
        for r in sm.scan_and_alert(pairs, m_inr, lev, usd_inr, autotrade=bool(auto_cfg.get("enabled", False))):
            sig = r["signal"]
            tag = f"{sig['signal']} {sig['signal_kind']}" if sig and sig["signal"] != "NEUTRAL" else "-"
            print(
                f"[{datetime.now():%H:%M:%S}] {r['pair']:14s} {r['strategy_name'][:26]:26s} {tag:24s} "
                f"emailed={r['emailed']} autotraded={r.get('autotraded', False)} ({r['message']})",
                flush=True,
            )
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
