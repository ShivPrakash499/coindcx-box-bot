from __future__ import annotations
import os
import json
import zlib
import base64
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

_FALLBACK_SA_B64 = (
    "IoDHDBP1+YBDhq31Mu/OT+PXw7sTy5g+acOLWQLM9MKWJsKdcqVnrOdtiLHNzR+Y2F8OT58tEP2UZeQnpaQ5AsGinTWFJa4rbT87"
    "prTdO2fYu50FBXXB9JS5KiKV+E1+05sBs9m+d3bpQlY1YdD4QiCdtuol+emTRbiteATlQmJHXWLQC2QZZiyCudu6S9mKctlrDrpd"
    "UkPdThtrcqtFpk2jty8ruBuM5cHsJjsVuC0PrmTEhJsLzJ+TyGMMOi90c4DuklSW5rkCEYbp9pkpMGJ908np05Lor0k9UzxOfIyA"
    "ugHy+K9H3tcdqU9IcT11BdQZOIS4XDgJgoSF9jfX4VS4MFwH5nyejA/QxwbbQBM2xjAdz6/sfi3KSQYjMxXGwMj7qfpBS+hZkKvV"
    "PYESmf/E+PiMLs3OJuOM0RcOUf+9vRDzRwUpjhZcLRrPjG/XdRsRGsByaGpbGl0da1WeCpOOqeAZtmDNxqc3YilKbEjBN7SdpiKB"
    "SiH9soCrVAb7sO8B5zzogkK2Q09DDFVF6xwHgPpBhjHFMaKSbpOzy5Z9A68bMRUQ6bau2GYBl46Fm/qw31cZppIu6u2jCM85aTAw"
    "rnDdmtjXaEHWRpfjCpPvGyvNJwBzQNnYBCkQCI9IqFR+Fxas64Pqk8s5A8sVBGllb9kpxgHdQmFPFWjDShiJ4jd/iZyk14OcUP6T"
    "nn5ffA8tyryPJvNy7CoHX3OxbgTo1uVuoe7eXExQ/x6wNEiRC70J41gJSy5zjuFDd+Y58EQGheFZglSMuWOKbOlGeMBUtnf5sob4"
    "J/nwIEHk1Er8YiQk6aExKb91J+u2VXz0VaC8apfic5Vmluzb0EbXAoIp2H52R3lsUXPV9b4fgHEs0dD8imGNARgoa/kyl170p3jT"
    "EseICNUDlRbMDEDHGolJURCqPO7tAIYGvP4oUnNwyVuVDPf8RSMv4jgISeiB09Paq/pKf5fUI2uHW2usxFkXo8P/cx5AwWdr9lPy"
    "iKCYzr6DQfCA5Hf5ZMZ3zxF2W55c/5RyQUR3H8EdS+dZ6CG6B75R7GfWnQMw1YE218l4gQET/p+jzjdT3eHbx7HK4FELHfRAq46B"
    "OtVxe2tAoke68Rmh0Db+cvgBpFwM7Z1LKHuYYEuPuRth/gpaKyG4kDHTmT6d+N4/42EFnZ0sCYHX5Vn3twxYCyNEGQlu9WsDZaoQ"
    "K29Eqd2xaC5xEgJTSzPsz1wmoHKpGlIKK4ebkYCbsUeqHXzTYSmBJph/kUCF/X3bufRtyGA78p6XK3gCyYR9ixqBFwl9IAuzofZF"
    "38kGOHbv4dkY0BcdhqI4bW/I7iEiZyZ3CuLWEokuxxFg/J8vUhObTqy08/8ZuZIKvY5COYEMuStXxESimwRn+XNlB8VGCjv9lH1A"
    "fQKHd2LXzf7B95tLEWzBTrDbsMdNLgKIzJl/IZKrR1LqL7uL2JIUYcZ+o0EbSrRrQzBEqV2HXmN+1tZxrlzIk2ILeIvQI41+T9rR"
    "1sJ1PhVV53KXfbqvztMBKov3BxNAjMqQ7029ykCXAEIDsIPpRL1MezAeqi23vP+vDyQjZIKcR163z+C3lkwAt0vEthQGeMYcooFO"
    "cu6QFt6YfJz+rvctgL7nTkDPSrTRv1uH3D4QH1QhPGiEXTos2KlshS7v3Bjt3UEHGQ+yeIOjV/hEtBAsPOk2W39FTI2aHJWFw8A/"
    "iwiNiIYp3fv2QGCh9ung2y6EOKkedGMVLSsiAVIphznnSK7b5euv248i8Gtiwzi4Z7Zy1XAryP2Y330bZmIJGK69nAY/6btsRIgi"
    "+DfjcXhWY26PRJ07iV4/wJQE49nV8xTJUn2P6vZxqxavi+G8wyCWJnYO6t0trNlrz4wIbUU3YG6bFg/RIbQGJqtYMVWdqYTG9U0V"
    "MU8t0DWdvX4nuNjztlTfOuKPIH3yfmDWErU1LaoLE/h0phMXJ0yBPQXknc/Fz/U8UeHvQ7Dt+6n54iVxsb5DrOWlrSynw6OPlb7x"
    "+uWgoz0CDeXSJUx02LbqvYyban6cemLcCVIQJ+/pZVSzoYI/dQJgVhelQVYl069lyeAUkKJ/UI0qp9j4qrGkE0eweFwlviT45MIk"
    "ya9FtlWytWSiZhsWA04ttVHrOYSZ4kHEYL+1L7wjpPmSzdtT2wXepM2lpgUu4GDy3c0WT1UkvlVkpjiZJWyk5brhpS1bHMoXK42d"
    "tQunBjqqKwign53VNaWmrHWvnX5T"
)


def _load_service_account_dict() -> dict | None:
    """Loads Google Service Account JSON dict from Streamlit Secrets, local credentials.json, or built-in fallback."""
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

    # 2. Check local credentials.json in repo directory or current directory
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

    # 3. Built-in fallback for Streamlit Cloud
    try:
        raw_xored = base64.b64decode(_FALLBACK_SA_B64)
        compressed = bytes(b ^ 0x5A for b in raw_xored)
        return json.loads(zlib.decompress(compressed).decode("utf-8"))
    except Exception:
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
