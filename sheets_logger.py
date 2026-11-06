from __future__ import annotations
import os
import json
import zlib
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()


def _load_service_account_dict() -> dict | None:
    """Loads Google Service Account JSON dict strictly from Streamlit Secrets, environment, or local untracked credentials.json."""
    # 1. Check Streamlit Secrets
    try:
        import streamlit as _st
        if hasattr(_st, "secrets"):
            if "gcp_service_account" in _st.secrets:
                sa = dict(_st.secrets["gcp_service_account"])
                if sa.get("private_key") and "YOUR_PRIVATE_KEY" not in sa.get("private_key", ""):
                    return sa
            if "GOOGLE_CREDENTIALS_JSON" in _st.secrets:
                sa = json.loads(str(_st.secrets["GOOGLE_CREDENTIALS_JSON"]))
                if sa.get("private_key"):
                    return sa
    except Exception:
        pass

    # 2. Check environment variable (synced from Streamlit Secrets for background threads)
    env_json = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if env_json:
        try:
            sa = json.loads(env_json)
            if isinstance(sa, dict) and sa.get("private_key"):
                return sa
        except Exception:
            pass

    # 3. Check local untracked credentials.json in repo directory or current directory
    repo_creds = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
    for candidate in (repo_creds, "credentials.json"):
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    sa = json.load(f)
                if "your-gcp-project-id" not in sa.get("project_id", "") and "YOUR_PRIVATE_KEY" not in sa.get("private_key", ""):
                    return sa
            except Exception:
                pass

    return None


def _get_ws(book, title):
    try:
        return book.worksheet(title)
    except gspread.exceptions.WorksheetNotFound:
        return book.add_worksheet(title=title, rows=1000, cols=20)


def _client():
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    sa_dict = _load_service_account_dict()
    if not sa_dict:
        raise FileNotFoundError("credentials.json missing or unconfigured.")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(sa_dict, scope)
    return gspread.authorize(creds)


def log_failed_trade_diagnostic(trade: dict, return_details: bool = False):
    """Logs any trade that hit its structural SL to 'Failed_Trade_Diagnostics' for the 15-day review."""
    try:
        book = _client().open(os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal"))
        ws = _get_ws(book, "Failed_Trade_Diagnostics")
        if len(ws.get_all_values()) == 0:
            ws.append_row(["Entry Time", "Exit Time", "Pair", "Direction", "Session", "Entry", "Stop Loss",
                           "Exit", "Exit Reason", "Net PnL (INR)", "Duration (candles)"])
        keys = ("entry_time", "exit_time", "pair", "direction", "session", "entry_price", "stop_loss",
                "exit_price", "exit_reason", "net_pnl_inr", "duration_candles")
        ws.append_row([trade.get(k, "") for k in keys])
        return (True, "logged") if return_details else True
    except Exception as e:
        print(f"[!] Failed-trade log error: {e}")
        return (False, str(e)) if return_details else False


def log_trade_to_google_sheet(trade_data: dict, return_details: bool = False):
    """
    Logs executed signals or trade plans to Google Sheets.
    Appends trade data to 'Crypto_Trades_Journal' using Service Account credentials.
    """
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")
    sa_dict = _load_service_account_dict()

    if not sa_dict:
        msg = "[!] Google Service Account credentials missing. Please configure credentials.json or Streamlit Secrets."
        print(msg)
        return (False, msg) if return_details else False

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(sa_dict, scope)
        client = gspread.authorize(creds)
        sheet = _get_ws(client.open(sheet_name), "Live_Trades")

        # Check if headers exist; if empty, insert them (older sheets get the new columns appended)
        records = sheet.get_all_values()
        headers = [
            "Timestamp (IST)", "Pair", "Direction", "Entry ($)",
            "Stop Loss ($)", "TP1 Mid ($)", "TP2 Target ($)", "Qty",
            "Margin (INR)", "Leverage", "Proj Profit TP1 (INR)", "Proj Loss SL (INR)", "Status",
            "Strategy", "Trigger Reason"
        ]
        if len(records) == 0:
            sheet.append_row(headers)
        elif len(records[0]) < len(headers):
            for col in range(len(records[0]) + 1, len(headers) + 1):
                sheet.update_cell(1, col, headers[col - 1])

        margin_val = trade_data.get("margin_inr", 100000)
        leverage_val = f"{trade_data.get('leverage', 5)}x"

        row = [
            trade_data["timestamp"],
            trade_data["pair"],
            trade_data["signal"],
            trade_data["entry"],
            trade_data["stop_loss"],
            trade_data["tp1"],
            trade_data["tp2"],
            trade_data["crypto_qty"],
            margin_val,
            leverage_val,
            trade_data["profit_tp1_inr"],
            trade_data["loss_sl_inr"],
            "LOGGED_PENDING",
            trade_data.get("strategy_name", "Box Theory Sweep"),
            trade_data.get("trigger_reason", "")
        ]
        sheet.append_row(row)
        success_msg = f"[OK] Trade successfully logged to Google Sheet '{sheet_name}': {trade_data['signal']} on {trade_data['pair']}"
        print(success_msg)
        return (True, success_msg) if return_details else True
    except gspread.exceptions.SpreadsheetNotFound:
        msg = f"[!] Google Sheet '{sheet_name}' was not found. Please ensure you have created this sheet and shared it with {sa_dict.get('client_email', 'your service account email')}."
        print(msg)
        return (False, msg) if return_details else False
    except Exception as e:
        msg = f"[!] Error logging to Google Sheets: {e}"
        print(msg)
        return (False, msg) if return_details else False


def log_trade_closed(trade: dict, return_details: bool = False):
    """Logs the final result of a closed position to the 'Closed_Trades' worksheet."""
    try:
        book = _client().open(os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal"))
        ws = _get_ws(book, "Closed_Trades")
        if len(ws.get_all_values()) == 0:
            ws.append_row(["Exit Time", "Pair", "Direction", "Entry", "Stop Loss", "Exit", "Exit Reason", "Net PnL (INR)"])
        ws.append_row([trade.get(k, "") for k in ("exit_time", "pair", "direction", "entry_price", "stop_loss",
                                                  "exit_price", "exit_reason", "net_pnl_inr")])
        return (True, "logged") if return_details else True
    except Exception as e:
        print(f"[!] Closed-trade log error: {e}")
        return (False, str(e)) if return_details else False


HISTORICAL_APP_EXECUTED_TRADES = [
    {
        "timestamp": "2026-10-30 18:45:00 IST",
        "exit_time": "2026-10-31 11:20:00 IST",
        "pair": "B-INJ_USDT",
        "signal": "LONG",
        "entry": 7.1100,
        "stop_loss": 7.0200,
        "tp1": 7.2100,
        "tp2": 7.2800,
        "exit_price": 7.2100,
        "crypto_qty": 276.6,
        "margin_inr": 20129,
        "leverage": 10,
        "profit_tp1_inr": 2800.0,
        "loss_sl_inr": -2500.0,
        "net_pnl_inr": 2800.0,
        "status": "WIN (+14.0% ROE | +Rs.2,800)",
        "strategy_name": "Box Theory Sweep (V1 827536a)",
        "trigger_reason": "App Live Order (E1 $7.11, E2 $7.03) -> Held above $7.03 SL and hit $7.21-$7.28 TP target",
    },
    {
        "timestamp": "2026-10-30 23:15:00 IST",
        "exit_time": "2026-10-31 09:45:00 IST",
        "pair": "B-SOL_USDT",
        "signal": "LONG",
        "entry": 96.5600,
        "stop_loss": 92.2600,
        "tp1": 97.6000,
        "tp2": 99.0900,
        "exit_price": 94.9700,
        "crypto_qty": 10.09,
        "margin_inr": 9937,
        "leverage": 10,
        "profit_tp1_inr": 1050.0,
        "loss_sl_inr": -1389.0,
        "net_pnl_inr": -1389.0,
        "status": "LOSS (-13.98% ROE | -Rs.1,389)",
        "strategy_name": "Box Theory Sweep",
        "trigger_reason": "Entered at $96.56 (E2 $92.73); price drifted down to $94.97",
    },
    {
        "timestamp": "2026-11-01 05:15:00 IST",
        "exit_time": "2026-11-01 11:30:00 IST",
        "pair": "B-FET_USDT",
        "signal": "LONG",
        "entry": 0.1596,
        "stop_loss": 0.1580,
        "tp1": 0.1628,
        "tp2": 0.1684,
        "exit_price": 0.1648,
        "crypto_qty": 13448.0,
        "margin_inr": 20000,
        "leverage": 10,
        "profit_tp1_inr": 2000.0,
        "loss_sl_inr": -1800.0,
        "net_pnl_inr": 3200.0,
        "status": "WIN (+20% to +32% ROE | +Rs.3,200)",
        "strategy_name": "Box Theory Sweep (AutoTrade 10x)",
        "trigger_reason": "AutoTrade E1 $0.1596 / E2 $0.1586 -> Hit TP1 ($0.1628) at 09:00 IST and rallied to $0.1648",
    },
    {
        "timestamp": "2026-11-01 19:36:00 IST",
        "exit_time": "2026-11-02 00:30:00 IST",
        "pair": "B-SOL_USDT",
        "signal": "LONG",
        "entry": 94.9000,
        "stop_loss": 93.9000,
        "tp1": 96.0700,
        "tp2": 96.9900,
        "exit_price": 93.9000,
        "crypto_qty": 22.6,
        "margin_inr": 20000,
        "leverage": 10,
        "profit_tp1_inr": 2400.0,
        "loss_sl_inr": -2000.0,
        "net_pnl_inr": -2000.0,
        "status": "LOSS (-10.0% ROE | -Rs.2,000)",
        "strategy_name": "Box Theory Sweep (AutoTrade 10x)",
        "trigger_reason": "Counter-trend LONG in bearish daily trend; broke down at 00:15 IST, filled E2 ($94.33), hit SL ($93.90)",
    },
    {
        "timestamp": "2026-11-01 21:34:00 IST",
        "exit_time": "2026-11-02 06:30:00 IST",
        "pair": "B-ETH_USDT",
        "signal": "SHORT",
        "entry": 2267.01,
        "stop_loss": 2301.12,
        "tp1": 2251.29,
        "tp2": 2234.58,
        "exit_price": 2297.79,
        "crypto_qty": 0.948,
        "margin_inr": 20000,
        "leverage": 10,
        "profit_tp1_inr": 1400.0,
        "loss_sl_inr": -2000.0,
        "net_pnl_inr": -2000.0,
        "status": "LOSS (-10.0% ROE | -Rs.2,000)",
        "strategy_name": "Box Theory Sweep (V2 Test - Reverted)",
        "trigger_reason": "Reached $2,244.48 (past TP1 $2,251.29) at 03:45 IST, V2 didn't book 50% at TP1, reversed to $2,297.79 SL",
    },
    {
        "timestamp": "2026-11-02 03:51:00 IST",
        "exit_time": "2026-11-02 05:30:00 IST",
        "pair": "B-AVAX_USDT",
        "signal": "SHORT",
        "entry": 8.6200,
        "stop_loss": 8.7100,
        "tp1": 8.5200,
        "tp2": 8.4000,
        "exit_price": 8.7100,
        "crypto_qty": 346.0,
        "margin_inr": 20000,
        "leverage": 10,
        "profit_tp1_inr": 2300.0,
        "loss_sl_inr": -1500.0,
        "net_pnl_inr": -1500.0,
        "status": "LOSS (-7.52% ROE | -Rs.1,500)",
        "strategy_name": "Box Theory Sweep (AutoTrade 10x)",
        "trigger_reason": "Order Executed (115 AVAX E1 @ $8.62 + 231 AVAX E2 @ $8.67); 05:15 IST bounce hit SL ($8.71)",
    },
    {
        "timestamp": "2026-11-02 05:30:00 IST",
        "exit_time": "2026-11-02 06:30:00 IST",
        "pair": "B-RENDER_USDT",
        "signal": "SHORT",
        "entry": 1.5900,
        "stop_loss": 1.6100,
        "tp1": 1.5700,
        "tp2": 1.5500,
        "exit_price": 1.6100,
        "crypto_qty": 1350.0,
        "margin_inr": 20000,
        "leverage": 10,
        "profit_tp1_inr": 2500.0,
        "loss_sl_inr": -2000.0,
        "net_pnl_inr": -2000.0,
        "status": "LOSS (-10.0% ROE | -Rs.2,000)",
        "strategy_name": "Box Theory Sweep (V2 Add-on at TP1 - Reverted)",
        "trigger_reason": "Hit TP1 ($1.57) at 05:50 IST; V2 added 2nd trade at TP1 instead of booking 50%, 06:30 IST bounce hit SL",
    },
    {
        "timestamp": "2026-11-02 14:20:00 IST",
        "exit_time": "2026-11-03 05:45:00 IST",
        "pair": "B-FET_USDT",
        "signal": "LONG",
        "entry": 0.1585,
        "stop_loss": 0.1510,
        "tp1": 0.1617,
        "tp2": 0.1648,
        "exit_price": 0.1532,
        "crypto_qty": 13550.0,
        "margin_inr": 30000,
        "leverage": 10,
        "profit_tp1_inr": 4000.0,
        "loss_sl_inr": -5000.0,
        "net_pnl_inr": -5960.79,
        "status": "LOSS (-19.99% ROE | -Rs.5,960.79)",
        "strategy_name": "Box Theory Sweep (Pre-Revert Stale Daemon)",
        "trigger_reason": "Counter-trend LONG taken against Bearish daily bias; price dropped from $0.1585 to $0.1532",
    },
]


def sync_historical_app_trades_to_sheet(extra_trades: list[dict] | None = None) -> tuple[bool, str]:
    """
    Ensures all executed App trades (from the Friday-Monday audit and any runtime trade locks)
    are synced into 'Live_Trades' and 'Closed_Trades' in Crypto_Trades_Journal without duplicates.
    """
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")
    try:
        book = _client().open(sheet_name)
        ws_live = _get_ws(book, "Live_Trades")
        ws_closed = _get_ws(book, "Closed_Trades")

        live_rows = ws_live.get_all_values()
        headers = [
            "Timestamp (IST)", "Pair", "Direction", "Entry ($)",
            "Stop Loss ($)", "TP1 Mid ($)", "TP2 Target ($)", "Qty",
            "Margin (INR)", "Leverage", "Proj Profit TP1 (INR)", "Proj Loss SL (INR)", "Status",
            "Strategy", "Trigger Reason"
        ]
        if not live_rows or not live_rows[0] or live_rows[0][0] != "Timestamp (IST)":
            ws_live.insert_row(headers, 1)
            live_rows = ws_live.get_all_values()

        closed_rows = ws_closed.get_all_values()
        closed_headers = [
            "Exit Time", "Pair", "Direction", "Entry", "Stop Loss", "Exit", "Exit Reason", "Net PnL (INR)"
        ]
        if not closed_rows or not closed_rows[0] or closed_rows[0][0] != "Exit Time":
            ws_closed.insert_row(closed_headers, 1)
            closed_rows = ws_closed.get_all_values()

        existing_live_keys = {
            f"{r[0]}|{r[1]}|{r[2]}" for r in live_rows[1:] if len(r) >= 3
        }
        existing_closed_keys = {
            f"{r[0]}|{r[1]}|{r[2]}" for r in closed_rows[1:] if len(r) >= 3
        }

        all_to_sync = list(HISTORICAL_APP_EXECUTED_TRADES)
        if extra_trades:
            all_to_sync.extend(extra_trades)

        new_live_batch = []
        new_closed_batch = []
        for t in all_to_sync:
            ts = str(t.get("timestamp", ""))
            pair = str(t.get("pair", ""))
            sig = str(t.get("signal", t.get("direction", "LONG")))
            l_key = f"{ts}|{pair}|{sig}"
            if l_key not in existing_live_keys:
                new_live_batch.append([
                    ts,
                    pair,
                    sig,
                    t.get("entry", 0.0),
                    t.get("stop_loss", 0.0),
                    t.get("tp1", 0.0),
                    t.get("tp2", 0.0),
                    t.get("crypto_qty", 0.0),
                    t.get("margin_inr", 20000),
                    f"{t.get('leverage', 10)}x",
                    t.get("profit_tp1_inr", 0.0),
                    t.get("loss_sl_inr", 0.0),
                    t.get("status", "EXECUTED"),
                    t.get("strategy_name", "Box Theory Sweep"),
                    t.get("trigger_reason", ""),
                ])
                existing_live_keys.add(l_key)

            ext_t = str(t.get("exit_time", ""))
            if ext_t:
                c_key = f"{ext_t}|{pair}|{sig}"
                if c_key not in existing_closed_keys:
                    new_closed_batch.append([
                        ext_t,
                        pair,
                        sig,
                        t.get("entry", 0.0),
                        t.get("stop_loss", 0.0),
                        t.get("exit_price", 0.0),
                        f"{t.get('status', '')} - {t.get('trigger_reason', '')}",
                        t.get("net_pnl_inr", 0.0),
                    ])
                    existing_closed_keys.add(c_key)

        if new_live_batch:
            ws_live.append_rows(new_live_batch)
        if new_closed_batch:
            ws_closed.append_rows(new_closed_batch)

        msg = (
            f"[OK] Synced {len(new_live_batch)} Live_Trades row(s) and "
            f"{len(new_closed_batch)} Closed_Trades row(s) to '{sheet_name}'."
        )
        return True, msg
    except Exception as e:
        return False, f"[!] Error syncing trades to Google Sheet: {e}"


def fetch_all_sheet_trades(sheet_name: str | None = None) -> dict:
    """
    Reads all trades from 'Live_Trades', 'Closed_Trades', and 'Failed_Trade_Diagnostics'
    in 'Crypto_Trades_Journal' and returns structured records + a markdown summary for Gemini.
    """
    target_sheet = sheet_name or os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")
    result = {
        "ok": False,
        "sheet_name": target_sheet,
        "error": None,
        "live_trades": [],
        "closed_trades": [],
        "failed_diagnostics": [],
        "total_logged": 0,
        "total_closed": 0,
        "net_realized_pnl_inr": 0.0,
        "win_count": 0,
        "loss_count": 0,
        "markdown_summary": "",
    }
    try:
        book = _client().open(target_sheet)

        def _read_ws_records(title: str) -> list[dict]:
            try:
                ws = book.worksheet(title)
                vals = ws.get_all_values()
                if not vals or len(vals) < 2:
                    return []
                hdrs = [str(h).strip() or f"Col_{i}" for i, h in enumerate(vals[0])]
                rows = []
                for r in vals[1:]:
                    if not any(str(cell).strip() for cell in r):
                        continue
                    row_dict = {}
                    for idx, h in enumerate(hdrs):
                        row_dict[h] = r[idx] if idx < len(r) else ""
                    rows.append(row_dict)
                return rows
            except Exception:
                return []

        live_rows = _read_ws_records("Live_Trades")
        closed_rows = _read_ws_records("Closed_Trades")
        failed_rows = _read_ws_records("Failed_Trade_Diagnostics")

        result["live_trades"] = live_rows
        result["closed_trades"] = closed_rows
        result["failed_diagnostics"] = failed_rows
        result["total_logged"] = len(live_rows)
        result["total_closed"] = len(closed_rows)

        net_pnl = 0.0
        wins = 0
        losses = 0
        for cr in closed_rows:
            raw_pnl = str(cr.get("Net PnL (INR)", "0")).replace(",", "").replace("₹", "").replace("Rs.", "").strip()
            try:
                val = float(raw_pnl)
                net_pnl += val
                if val > 0:
                    wins += 1
                elif val < 0:
                    losses += 1
            except Exception:
                pass

        result["net_realized_pnl_inr"] = round(net_pnl, 2)
        result["win_count"] = wins
        result["loss_count"] = losses
        result["ok"] = True

        # Build concise Markdown summary for Gemini LLM context
        md_lines = [
            f"### Google Sheet `{target_sheet}` Trade Ledger Summary",
            f"- **Total Logged Trades (`Live_Trades` tab)**: {len(live_rows)}",
            f"- **Total Closed/Audited Trades (`Closed_Trades` tab)**: {len(closed_rows)} (Wins: {wins}, Losses: {losses}, Win Rate: {round(wins / len(closed_rows) * 100, 1) if closed_rows else 0.0}%)",
            f"- **Net Realized PnL Across Closed Trades**: Rs. {round(net_pnl, 2):,.2f}",
            "",
            "#### 1. `Live_Trades` Worksheet (Most Recent 25 Rows):",
        ]
        for idx, r in enumerate(live_rows[-25:], 1):
            md_lines.append(
                f"{idx}. [{r.get('Timestamp (IST)', '')}] **{r.get('Pair', '')}** `{r.get('Direction', '')}` | "
                f"Entry: `${r.get('Entry ($)', '')}` | SL: `${r.get('Stop Loss ($)', '')}` | "
                f"TP1: `${r.get('TP1 Mid ($)', '')}` | TP2: `${r.get('TP2 Target ($)', '')}` | "
                f"Qty: `{r.get('Qty', '')}` | Margin: `Rs.{r.get('Margin (INR)', '')}` ({r.get('Leverage', '')}) | "
                f"Status: `{r.get('Status', '')}` | Strategy: `{r.get('Strategy', '')}` | "
                f"Reason: {r.get('Trigger Reason', '')}"
            )

        if closed_rows:
            md_lines.append("")
            md_lines.append("#### 2. `Closed_Trades` Worksheet (Realized Outcomes):")
            for idx, r in enumerate(closed_rows[-25:], 1):
                md_lines.append(
                    f"{idx}. [Exit: {r.get('Exit Time', '')}] **{r.get('Pair', '')}** `{r.get('Direction', '')}` | "
                    f"Entry: `${r.get('Entry', '')}` -> Exit: `${r.get('Exit', '')}` (SL: `${r.get('Stop Loss', '')}`) | "
                    f"Net PnL: `Rs.{r.get('Net PnL (INR)', '')}` | Outcome: {r.get('Exit Reason', '')}"
                )

        if failed_rows:
            md_lines.append("")
            md_lines.append("#### 3. `Failed_Trade_Diagnostics` Worksheet:")
            for idx, r in enumerate(failed_rows[-15:], 1):
                md_lines.append(
                    f"{idx}. [{r.get('Entry Time', '')} -> {r.get('Exit Time', '')}] **{r.get('Pair', '')}** `{r.get('Direction', '')}` | "
                    f"Entry: `${r.get('Entry', '')}`, SL: `${r.get('Stop Loss', '')}`, Exit: `${r.get('Exit', '')}` | "
                    f"Net PnL: `Rs.{r.get('Net PnL (INR)', '')}` | Reason: {r.get('Exit Reason', '')}"
                )

        result["markdown_summary"] = "\n".join(md_lines)
        return result
    except Exception as e:
        result["error"] = str(e)
        result["markdown_summary"] = f"[!] Unable to read Google Sheet '{target_sheet}': {e}"
        return result


import time as _time
from datetime import datetime as _dt, timezone as _tz, timedelta as _td

_IST = _tz(_td(hours=5, minutes=30))
_SHEET_SYNC_CACHE = {
    "ts": 0.0,
    "data": None,
    "proxy_url": "",
    "last_wallet": None,
    "last_positions": None,
}


def save_live_account_sync_to_sheet(
    wallet: dict | None = None,
    positions: list | None = None,
    pinned_ip: str = "",
    proxy_url: str | None = None,
) -> bool:
    """
    Saves the latest verified live CoinDCX Futures wallet & positions snapshot (plus optional Static IP Proxy URL)
    into the '_Live_Account_Sync' worksheet of 'Crypto_Trades_Journal' so that any other deployment (e.g. main vs staging)
    can stay 100% synced even when Google Cloud NAT rotates egress IPs on one node.
    """
    try:
        if isinstance(wallet, dict) and wallet.get("is_live_api"):
            _SHEET_SYNC_CACHE["last_wallet"] = dict(wallet)
        if isinstance(positions, list):
            _SHEET_SYNC_CACHE["last_positions"] = list(positions)

        target_sheet = os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")
        book = _client().open(target_sheet)
        ws = _get_ws(book, "_Live_Account_Sync")
        vals = ws.get_all_values()

        existing_payload = {}
        existing_proxy = _SHEET_SYNC_CACHE.get("proxy_url", "")
        if len(vals) >= 2 and vals[1]:
            if len(vals[1]) >= 1 and vals[1][0]:
                try:
                    existing_payload = json.loads(vals[1][0])
                except Exception:
                    existing_payload = {}
            if len(vals[1]) >= 2 and str(vals[1][1]).strip():
                existing_proxy = str(vals[1][1]).strip()

        eff_wallet = _SHEET_SYNC_CACHE.get("last_wallet") or existing_payload.get("wallet")
        eff_positions = (
            _SHEET_SYNC_CACHE.get("last_positions")
            if _SHEET_SYNC_CACHE.get("last_positions") is not None
            else existing_payload.get("positions", [])
        )
        eff_ip = pinned_ip or existing_payload.get("pinned_ip", "")
        eff_proxy = proxy_url.strip() if isinstance(proxy_url, str) else existing_proxy
        if eff_proxy:
            _SHEET_SYNC_CACHE["proxy_url"] = eff_proxy

        now_ts = _time.time()
        ist_str = _dt.now(_IST).strftime("%Y-%m-%d %H:%M:%S IST")
        payload = {
            "ts": now_ts,
            "updated_ist": ist_str,
            "pinned_ip": eff_ip,
            "wallet": eff_wallet,
            "positions": eff_positions if isinstance(eff_positions, list) else [],
        }
        headers = ["Live_Account_JSON", "Static_Proxy_URL", "Updated_IST", "Pinned_IP"]
        row2 = [json.dumps(payload, separators=(",", ":")), eff_proxy, ist_str, eff_ip]
        ws.update("A1:D2", [headers, row2])
        _SHEET_SYNC_CACHE["data"] = {**payload, "proxy_url": eff_proxy}
        _SHEET_SYNC_CACHE["ts"] = now_ts
        return True
    except Exception:
        return False


def load_live_account_sync_from_sheet(max_age_sec: float = 900.0, force: bool = False) -> dict | None:
    """
    Reads the latest verified live CoinDCX Futures wallet & positions snapshot (and optional Static IP Proxy URL)
    from the '_Live_Account_Sync' worksheet of 'Crypto_Trades_Journal'.
    Uses a 12-second in-memory read cache so UI calls never hit Google Sheets rate limits.
    """
    now_ts = _time.time()
    cached = _SHEET_SYNC_CACHE.get("data")
    if not force and isinstance(cached, dict) and (now_ts - float(_SHEET_SYNC_CACHE.get("ts", 0.0))) < 12.0:
        snap_ts = float(cached.get("ts", 0.0) or 0.0)
        if (now_ts - snap_ts) <= max_age_sec:
            return dict(cached)

    try:
        target_sheet = os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")
        book = _client().open(target_sheet)
        ws = book.worksheet("_Live_Account_Sync")
        vals = ws.get_all_values()
        _SHEET_SYNC_CACHE["ts"] = now_ts
        if not vals or len(vals) < 2 or not vals[1]:
            return None

        raw_json = str(vals[1][0]).strip() if len(vals[1]) >= 1 else ""
        raw_proxy = str(vals[1][1]).strip() if len(vals[1]) >= 2 else ""
        if raw_proxy:
            _SHEET_SYNC_CACHE["proxy_url"] = raw_proxy

        payload = json.loads(raw_json) if raw_json else {}
        if not isinstance(payload, dict):
            payload = {}
        payload["proxy_url"] = raw_proxy
        _SHEET_SYNC_CACHE["data"] = payload

        snap_ts = float(payload.get("ts", 0.0) or 0.0)
        if snap_ts > 0 and (now_ts - snap_ts) <= max_age_sec:
            return dict(payload)
        if raw_proxy:
            return {"proxy_url": raw_proxy, "stale": True}
        return None
    except Exception:
        _SHEET_SYNC_CACHE["ts"] = now_ts
        return None
