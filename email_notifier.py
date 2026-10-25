"""
Gmail trade notifications (SSL, smtp.gmail.com:465).

Config is read from environment / .env / Streamlit secrets - nothing is hard-coded:
    GMAIL_SENDER, GMAIL_APP_PASSWORD, GMAIL_RECEIVER
Subject format:  "<SYMBOL> - trade notification"   e.g.  "SOL - trade notification"
"""
from __future__ import annotations

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import pytz
from dotenv import load_dotenv

load_dotenv()
IST = pytz.timezone("Asia/Kolkata")


def _cfg(name: str, default: str = "") -> str:
    """Streamlit secrets first (cloud), then environment / .env."""
    try:
        import streamlit as st  # noqa: WPS433
        if hasattr(st, "secrets") and name in st.secrets:
            return str(st.secrets[name]).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


def short_name(pair: str) -> str:
    return pair.replace("B-", "").replace("I-", "").split("_")[0].upper()


def get_email_config() -> dict:
    sender = _cfg("GMAIL_SENDER") or _cfg("SENDER_EMAIL")
    password = _cfg("GMAIL_APP_PASSWORD") or _cfg("SENDER_APP_PASSWORD")
    receiver = _cfg("GMAIL_RECEIVER") or _cfg("RECEIVER_EMAIL") or sender
    return {"sender": sender, "password": password.replace(" ", ""), "receiver": receiver,
            "configured": bool(sender and password and receiver)}


def _send(subject: str, html: str, text: str) -> tuple[bool, str]:
    cfg = get_email_config()
    if not cfg["configured"]:
        return False, "Email not configured: set GMAIL_SENDER, GMAIL_APP_PASSWORD and GMAIL_RECEIVER in .env / Streamlit secrets."
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"CoinDCX Box Bot <{cfg['sender']}>"
    msg["To"] = cfg["receiver"]
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=15) as server:
            server.login(cfg["sender"], cfg["password"])
            server.sendmail(cfg["sender"], [cfg["receiver"]], msg.as_string())
        return True, f"Email sent to {cfg['receiver']}"
    except smtplib.SMTPAuthenticationError:
        return False, "Gmail rejected the login. Use a 16-character App Password (2-Step Verification must be on)."
    except Exception as e:  # network, DNS, timeout ...
        return False, f"Failed to send email: {e}"


def send_trade_email(pair: str, direction: str, entry: float, stop_loss: float, tp1: float, tp2: float,
                     margin_inr: float, leverage: int = 5, zone: str = "", kind: str = "SIGNAL",
                     note: str = "", app_url: str = "") -> tuple[bool, str]:
    """kind: SIGNAL (alert), EXECUTED (order placed) or CLOSED."""
    direction = direction.upper()
    is_long = direction in ("LONG", "BUY")
    direction = "LONG" if is_long else "SHORT"
    zone = zone or ("Buy Zone RL-SL" if is_long else "Sell Zone RH-SH")
    sym = short_name(pair)
    now = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    url = app_url or _cfg("APP_WEB_URL", "http://localhost:8501")
    colour = "#16a34a" if is_long else "#dc2626"
    heading = {"SIGNAL": "Trade signal", "EXECUTED": "Order executed", "CLOSED": "Position closed"}.get(kind, kind)

    rows = [
        ("Direction", direction), ("Trigger Zone", zone), ("Entry Price", f"${entry:,.4f}"),
        ("Structural Stop Loss", f"${stop_loss:,.4f}"), ("TP1 (MID)", f"${tp1:,.4f}"), ("TP2", f"${tp2:,.4f}"),
        ("Allocated Rotational Margin", f"₹{margin_inr:,.0f}"), ("Leverage", f"{leverage}x"), ("Timestamp (IST)", now),
    ]
    tr = "".join(f"<tr><td style='padding:6px 10px;color:#475569'>{k}</td>"
                 f"<td style='padding:6px 10px;font-weight:700;text-align:right'>{v}</td></tr>" for k, v in rows)
    html = f"""<html><body style="font-family:-apple-system,Segoe UI,Roboto,Arial,sans-serif;background:#f1f5f9;padding:16px">
      <div style="max-width:520px;margin:auto;background:#fff;border-radius:12px;border:1px solid #e2e8f0;overflow:hidden">
        <div style="background:#0f172a;color:#fff;padding:16px;text-align:center">
          <div style="font-size:13px;opacity:.8">{heading} &bull; {pair}</div>
          <div style="margin-top:6px;display:inline-block;padding:4px 14px;border-radius:16px;background:{colour};font-weight:800">{direction}</div>
        </div>
        <table style="width:100%;border-collapse:collapse;font-size:14px">{tr}</table>
        {f'<p style="padding:0 14px;color:#334155;font-size:13px">{note}</p>' if note else ''}
        <p style="text-align:center;padding:10px"><a href="{url}" style="background:#2563eb;color:#fff;padding:12px 18px;border-radius:8px;text-decoration:none;font-weight:700">Open terminal &amp; review</a></p>
      </div></body></html>"""
    text = (f"{heading}: {direction} {pair}\n" + "\n".join(f"{k}: {v}" for k, v in rows)
            + (f"\n{note}" if note else "") + f"\n{url}")
    return _send(f"{sym} - trade notification", html, text)


def send_test_trade_email(pair: str = "B-SOL_USDT", live_price: float = 100.0, margin_inr: float = 10000.0) -> tuple[bool, str]:
    return send_trade_email(
        pair=pair, direction="LONG", entry=live_price, stop_loss=round(live_price * 0.985, 4),
        tp1=round(live_price * 1.02, 4), tp2=round(live_price * 1.04, 4), margin_inr=margin_inr, leverage=5,
        zone="Buy Zone RL-SL", kind="SIGNAL", note="This is a TEST alert - no trade was placed.")
