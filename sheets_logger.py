from __future__ import annotations
import os
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

load_dotenv()

def log_trade_to_google_sheet(trade_data: dict, return_details: bool = False):
    """
    Logs executed signals or trade plans to Google Sheets.
    Appends trade data to 'Crypto_Trades_Journal' using credentials.json.
    """
    creds_file = "credentials.json"
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Crypto_Trades_Journal")

    if not os.path.exists(creds_file):
        msg = f"[!] {creds_file} missing. Please place your Google Service Account key in {creds_file}."
        print(msg)
        return (False, msg) if return_details else False

    # Check if credentials.json is still using placeholder content
    try:
        with open(creds_file, "r") as f:
            creds_data = json.load(f)
            if "your-gcp-project-id" in creds_data.get("project_id", "") or "YOUR_PRIVATE_KEY" in creds_data.get("private_key", ""):
                msg = f"[!] {creds_file} contains placeholder credentials. Replace with your actual Google Cloud Service Account JSON key."
                print(msg)
                return (False, msg) if return_details else False
    except Exception as e:
        msg = f"[!] Error reading {creds_file}: {e}"
        print(msg)
        return (False, msg) if return_details else False

    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
        client = gspread.authorize(creds)
        sheet = client.open(sheet_name).sheet1

        # Check if headers exist; if empty, insert them
        records = sheet.get_all_values()
        if len(records) == 0:
            headers = [
                "Timestamp (IST)", "Pair", "Direction", "Entry ($)", 
                "Stop Loss ($)", "TP1 Mid ($)", "TP2 Target ($)", "Qty", 
                "Margin (INR)", "Leverage", "Proj Profit TP1 (INR)", "Proj Loss SL (INR)", "Status"
            ]
            sheet.append_row(headers)

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
            "LOGGED_PENDING"
        ]
        sheet.append_row(row)
        success_msg = f"[✓] Trade successfully logged to Google Sheet '{sheet_name}': {trade_data['signal']} on {trade_data['pair']}"
        print(success_msg)
        return (True, success_msg) if return_details else True
    except gspread.exceptions.SpreadsheetNotFound:
        msg = f"[!] Google Sheet '{sheet_name}' was not found. Please ensure you have created this sheet and shared it with your service account email."
        print(msg)
        return (False, msg) if return_details else False
    except Exception as e:
        msg = f"[!] Error logging to Google Sheets: {e}"
        print(msg)
        return (False, msg) if return_details else False
