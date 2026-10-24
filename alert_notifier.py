from __future__ import annotations
import os
import time
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

IST = pytz.timezone('Asia/Kolkata')

# In-memory alert cooldown tracker to prevent email spam (15-min cooldown per pair+signal)
_ALERT_COOLDOWN_SECONDS = 900
_last_alert_timestamps = {}

def is_alert_on_cooldown(pair: str, signal: str) -> bool:
    key = f"{pair}_{signal}"
    last_time = _last_alert_timestamps.get(key, 0)
    return (time.time() - last_time) < _ALERT_COOLDOWN_SECONDS

def record_alert_dispatched(pair: str, signal: str):
    key = f"{pair}_{signal}"
    _last_alert_timestamps[key] = time.time()

def send_email_notification(subject: str, html_content: str, text_content: str = "") -> tuple[bool, str]:
    """
    Sends an email using standard SMTP (supports Gmail App Passwords, custom SMTP, etc.).
    Returns (success_boolean, status_message).
    """
    enabled = os.getenv("ALERT_EMAIL_ENABLED", "True").strip().lower() in ["true", "1", "yes"]
    if not enabled:
        return False, "Email alerts are disabled in .env (ALERT_EMAIL_ENABLED=False)"

    sender = os.getenv("SENDER_EMAIL", "").strip()
    password = os.getenv("SENDER_APP_PASSWORD", "").strip()
    receiver = os.getenv("RECEIVER_EMAIL", "").strip() or sender
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("SMTP_PORT", 587))

    if not sender or not password:
        return False, "SENDER_EMAIL or SENDER_APP_PASSWORD missing in .env"

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"CoinDCX Box Sentinel <{sender}>"
        msg["To"] = receiver

        if text_content:
            msg.attach(MIMEText(text_content, "plain"))
        if html_content:
            msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())

        return True, f"Email successfully sent to {receiver}"
    except Exception as e:
        return False, f"Failed to send email: {str(e)}"

def send_sweep_alert(pair: str, signal_type: str, session_name: str, live_price: float, 
                     entry: float, stop_loss: float, tp1: float, tp2: float, 
                     roe_tp1: float = 0.0, box_levels: dict = None, force: bool = False) -> tuple[bool, str]:
    """
    Dispatches a high-priority liquidity sweep signal alert with terminal web link.
    Respects anti-spam cooldown unless force=True.
    """
    if not force and is_alert_on_cooldown(pair, signal_type):
        return False, f"Alert for {pair} {signal_type} suppressed by 15-min cooldown."

    app_url = os.getenv("APP_WEB_URL", "http://localhost:8501").strip()
    now_str = datetime.now(IST).strftime("%I:%M %p IST (%d %b %Y)")

    is_buy = signal_type.upper() in ["BUY", "LONG"]
    badge_color = "#16a34a" if is_buy else "#dc2626"
    badge_bg = "#dcfce7" if is_buy else "#fee2e2"
    action_text = "🟢 BUY / LONG SETUP" if is_buy else "🔴 SELL / SHORT SETUP"

    subject = f"⚡ [{signal_type}] CoinDCX Liquidity Sweep: {pair} ({session_name})"

    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f1f5f9; margin: 0; padding: 20px; }}
            .container {{ max-width: 600px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }}
            .header {{ background: #0f172a; padding: 20px; color: #ffffff; text-align: center; }}
            .badge {{ display: inline-block; padding: 6px 14px; border-radius: 20px; font-weight: 800; font-size: 14px; background: {badge_bg}; color: {badge_color}; }}
            .content {{ padding: 24px; }}
            .card {{ background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin: 16px 0; }}
            .row {{ display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
            .row:last-child {{ border-bottom: none; }}
            .btn {{ display: block; width: 85%; margin: 24px auto 10px; background: #2563eb; color: #ffffff !important; text-align: center; padding: 14px 20px; border-radius: 8px; font-weight: 700; font-size: 16px; text-decoration: none; }}
            .footer {{ text-align: center; color: #64748b; font-size: 12px; padding: 16px; border-top: 1px solid #e2e8f0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2 style="margin:0 0 8px 0;">⚡ CoinDCX Box Theory Sentinel</h2>
                <div class="badge">{action_text}</div>
            </div>
            <div class="content">
                <p style="font-size: 15px; color: #334155; margin-top:0;">
                    A confirmed liquidity sweep has triggered on <b>{pair}</b> during the <b>{session_name}</b> window.
                </p>

                <div class="card">
                    <div style="font-size: 12px; color: #64748b; text-transform: uppercase; font-weight: 700; margin-bottom: 8px;">Institutional Order Parameters</div>
                    <div class="row"><span>Instrument Pair:</span><b>{pair}</b></div>
                    <div class="row"><span>Trading Session:</span><b>{session_name}</b></div>
                    <div class="row"><span>Signal Triggered At:</span><b>{now_str}</b></div>
                    <div class="row"><span>Current Market Price:</span><b>${live_price:,.4f}</b></div>
                    <div class="row"><span>Planned Entry:</span><b>${entry:,.4f}</b></div>
                    <div class="row"><span>Stop Loss (SL):</span><b style="color:#dc2626;">${stop_loss:,.4f}</b></div>
                    <div class="row"><span>Take Profit 1 (MID):</span><b style="color:#0284c7;">${tp1:,.4f} (+{roe_tp1}% ROE @ 5x)</b></div>
                    <div class="row"><span>Take Profit 2 (Extreme):</span><b style="color:#16a34a;">${tp2:,.4f}</b></div>
                </div>

                <p style="font-size: 13px; color: #64748b; text-align:center;">
                    Please visually confirm the candlestick rejection on the terminal before manually triggering your margin order:
                </p>

                <a href="{app_url}" class="btn" target="_blank">
                    🚀 Open Trading Terminal & Confirm Order
                </a>

                <div style="text-align:center; font-size: 12px; color: #94a3b8; margin-top: 6px;">
                    Link: <a href="{app_url}" style="color:#2563eb;">{app_url}</a>
                </div>
            </div>
            <div class="footer">
                Automated 24/7 Box Theory Engine • CoinDCX Futures System
            </div>
        </div>
    </body>
    </html>
    """

    plain_content = f"""
    CoinDCX Box Theory Alert: {signal_type} on {pair}
    Session: {session_name}
    Time: {now_str}
    Current Price: ${live_price}
    Entry: ${entry}
    Stop Loss: ${stop_loss}
    Take Profit 1 (MID): ${tp1} (Estimated ROE: +{roe_tp1}% @ 5x)
    Take Profit 2: ${tp2}

    Open Trading Terminal & Confirm Order:
    {app_url}
    """

    success, msg = send_email_notification(subject, html_content, plain_content)
    if success:
        record_alert_dispatched(pair, signal_type)
    return success, msg
