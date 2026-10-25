"""
Standalone signal scanner (no orders, no UI):  python signal_scanner.py [--interval 60] [--once]
E-mails a trade notification for every new zone-reversal / tower-continuation confirmation.
"""
import argparse
import time
from datetime import datetime

import coindcx_engine as eng
import signal_monitor as sm


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=int, default=60, help="seconds between scans")
    ap.add_argument("--pairs", nargs="*", default=sm.DEFAULT_WATCHLIST)
    ap.add_argument("--once", action="store_true")
    args = ap.parse_args()

    while True:
        rot = eng.get_rotational_margin_inr(5)
        usd_inr = eng.get_coindcx_live_usdt_inr_rate()
        for r in sm.scan_and_alert(args.pairs, rot["margin_inr"], 5, usd_inr):
            sig = r["signal"]
            tag = f"{sig['signal']} {sig['signal_kind']}" if sig and sig["signal"] != "NEUTRAL" else "-"
            print(f"[{datetime.now():%H:%M:%S}] {r['pair']:11s} {tag:24s} emailed={r['emailed']} ({r['message']})", flush=True)
        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
