"""
Gmail trade notifications (smtp.gmail.com:587 STARTTLS / 465 SSL).

Config is read from environment / .env / Streamlit secrets:
    GMAIL_SENDER, GMAIL_APP_PASSWORD, GMAIL_RECEIVER
Subject format:  "<SYMBOL> - <STRATEGY> - trade notification"   e.g.  "ETH - Box Theory Sweep - trade notification"
                 (falls back to "<SYMBOL> - trade notification" when no strategy is given)
Direct Action Link: <APP_URL>/?tab=execute&strategy=<ID>&pair=<PAIR>&direction=<DIR>&entry=<ENTRY>&sl=<SL>&tp1=<TP1>&tp2=<TP2>&margin=<MARGIN>&lev=<LEV>
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
    clean_pwd = password.replace(" ", "").strip()
    # 16-character check for standard Google App Passwords
    is_app_password = len(clean_pwd) == 16
    return {
        "sender": sender,
        "password": clean_pwd,
        "receiver": receiver,
        "is_app_password": is_app_password,
        "configured": bool(sender and clean_pwd and receiver)
    }


def _send(subject: str, html: str, text: str) -> tuple[bool, str]:
    cfg = get_email_config()
    if not cfg["configured"]:
        return False, "Email not configured: set GMAIL_SENDER, GMAIL_APP_PASSWORD and GMAIL_RECEIVER in .env / Streamlit secrets."

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Crypto Trade Assistant <{cfg['sender']}>"
    msg["To"] = cfg["receiver"]
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    app_pwd_hint = (
        "\n\n👉 Google requires a 16-character App Password (not your standard account password). "
        "Create one in 30 seconds at: https://myaccount.google.com/apppasswords "
        "and paste it into .env under GMAIL_APP_PASSWORD."
    )

    # Attempt 1: Port 587 with STARTTLS (standard modern Gmail submission)
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=12) as server:
            server.ehlo()
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
            server.login(cfg["sender"], cfg["password"])
            server.sendmail(cfg["sender"], [cfg["receiver"]], msg.as_string())
        return True, f"Email alert sent successfully to {cfg['receiver']}"
    except (smtplib.SMTPAuthenticationError, smtplib.SMTPResponseException) as e:
        err_msg = str(e)
        if "534" in err_msg or "Application-specific" in err_msg or "InvalidSecondFactor" in err_msg or not cfg["is_app_password"]:
            return False, f"Gmail rejected login: {app_pwd_hint}"
        return False, f"Gmail authentication error: {err_msg} {app_pwd_hint}"
    except smtplib.SMTPServerDisconnected:
        # Fallback to Port 465 SSL
        try:
            with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=12) as server:
                server.login(cfg["sender"], cfg["password"])
                server.sendmail(cfg["sender"], [cfg["receiver"]], msg.as_string())
            return True, f"Email alert sent successfully to {cfg['receiver']} via SSL"
        except Exception as e_ssl:
            return False, f"Gmail connection closed. If using normal account password, Google blocks it: {app_pwd_hint}"
    except Exception as e:
        return False, f"Failed to send email ({type(e).__name__}): {e}"


def send_trade_email(pair: str, direction: str, entry: float, stop_loss: float, tp1: float, tp2: float,
                     margin_inr: float, leverage: int = 5, zone: str = "", kind: str = "SIGNAL",
                     note: str = "", app_url: str = "", strategy_name: str = "", trigger_reason: str = "",
                     strategy_id: str = "", levels: dict | None = None, entry2_sweep: float = 0.0) -> tuple[bool, str]:
    """
    Sends structured trade email notification with a 1-click action link
    that opens the Trade Execution tab with all values pre-filled, plus a visual Daily Trend Bias card
    and the 2-Entry Sweep + Runner breakdown.
    """
    direction = direction.upper()
    is_long = direction in ("LONG", "BUY")
    direction = "LONG" if is_long else "SHORT"
    zone = zone or ("Buy Zone RL-SL" if is_long else "Sell Zone RH-SH")
    sym = short_name(pair)
    now = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    base_url = (app_url or _cfg("APP_WEB_URL", "https://shiv-prakash-trade-assistant.streamlit.app")).rstrip("/")

    lv = levels or {}
    if entry2_sweep <= 0 and entry > 0:
        sh_lv = float(lv.get("SH") or (entry * 1.01))
        sl_lv = float(lv.get("SL") or (entry * 0.99))
        entry2_sweep = min(sl_lv, entry * 0.992) if is_long else max(sh_lv, entry * 1.008)
    avg_entry_2x = (entry + entry2_sweep) / 2.0 if entry2_sweep > 0 else entry
    tranche_margin_inr = margin_inr * 0.5

    # Action URL with pre-filled parameters to open execution tab
    action_url = (
        f"{base_url}/?tab=execute{f'&strategy={strategy_id}' if strategy_id else ''}&pair={pair}&direction={direction}&entry={entry:.4f}"
        f"&sl={stop_loss:.4f}&tp1={tp1:.4f}&tp2={tp2:.4f}&margin={int(margin_inr)}&lev={leverage}"
    )

    colour = "#16a34a" if is_long else "#dc2626"
    heading = {"SIGNAL": "Trade Signal Alert", "EXECUTED": "Order Executed", "CLOSED": "Position Closed"}.get(kind, kind)

    tp1_roe = round((abs(tp1 - entry) / entry) * leverage * 100.0, 2) if entry > 0 else 0.0
    tp2_roe = round((abs(tp2 - entry) / entry) * leverage * 100.0, 2) if entry > 0 else 0.0
    sl_roe = round((abs(stop_loss - entry) / entry) * leverage * 100.0, 2) if (entry > 0 and stop_loss > 0) else 0.0

    # Build Daily Trend Bias visual banner if levels are provided
    t_bias = lv.get("trend_bias") or lv.get("bias") or ""
    ema50 = lv.get("EMA50")
    ema200 = lv.get("EMA200")
    d_close = lv.get("daily_close") or entry
    rh_val, mid_val, rl_val = lv.get("RH"), lv.get("MID"), lv.get("RL")
    sh_val, sl_val = lv.get("SH"), lv.get("SL")

    if t_bias == "BEARISH":
        trend_badge = "🔴 BEARISH TREND (< 50 & 200 EMA — Primary Short Bias)"
        trend_bg, trend_border, trend_fg = "#fef2f2", "#ef4444", "#991b1b"
    elif t_bias == "BULLISH":
        trend_badge = "🟢 BULLISH TREND (> 50 & 200 EMA — Primary Long Bias)"
        trend_bg, trend_border, trend_fg = "#f0fdf4", "#22c55e", "#166534"
    elif t_bias == "NEUTRAL":
        trend_badge = "🟡 RANGE MODE (Between 50 & 200 EMA — Both Box Edges Active)"
        trend_bg, trend_border, trend_fg = "#fefce8", "#eab308", "#854d0e"
    else:
        trend_badge = ""
        trend_bg, trend_border, trend_fg = "#f8fafc", "#cbd5e1", "#334155"

    trend_visual_html = ""
    if trend_badge and ema50 is not None and ema200 is not None:
        box_strip = (
            f"<div style='margin-top:6px;font-size:12px;color:#475569;'>"
            f"📦 <strong>Daily Box:</strong> SH: <strong>${float(sh_val or rh_val):,.2f}</strong> &middot; "
            f"RH (Sell): <strong>${float(rh_val):,.2f}</strong> &middot; "
            f"MID (50%): <strong>${float(mid_val):,.2f}</strong> &middot; "
            f"RL (Buy): <strong>${float(rl_val):,.2f}</strong> &middot; "
            f"SL: <strong>${float(sl_val or rl_val):,.2f}</strong></div>"
        ) if (rh_val and mid_val and rl_val) else ""
        trend_visual_html = f"""
        <div style="margin-bottom:14px;padding:12px 14px;background:{trend_bg};border:1px solid {trend_border};border-left:5px solid {trend_border};border-radius:8px;">
          <div style="font-weight:800;font-size:13px;color:{trend_fg};letter-spacing:0.3px;">{trend_badge}</div>
          <div style="margin-top:6px;font-size:12px;color:#1e293b;">
            📊 <strong>Daily Close:</strong> ${float(d_close):,.2f} &nbsp;|&nbsp;
            <strong>50 EMA:</strong> ${float(ema50):,.2f} &nbsp;|&nbsp;
            <strong>200 EMA:</strong> ${float(ema200):,.2f}
          </div>
          {box_strip}
        </div>
        """

    rows = [
        ("Strategy", strategy_name or "Box Theory Sweep"),
        ("Asset / Pair", pair),
        ("Trade Direction", direction),
        ("Trigger Zone", zone),
    ]
    if trend_badge:
        rows.append(("Daily Trend Bias", trend_badge))
    if ema50 is not None and ema200 is not None:
        rows.append(("Daily 50 EMA / 200 EMA", f"${float(ema50):,.2f}  /  ${float(ema200):,.2f}"))
    if trigger_reason:
        rows.append(("Trigger Reason", trigger_reason))
    rows += [
        ("Entry 1 (50% Margin — Zone Rejection)", f"${entry:,.4f}  (₹{tranche_margin_inr:,.0f})"),
        (f"Entry 2 (50% Margin — Equal Limit @ {'SL' if is_long else 'SH'} Sweep)", f"${entry2_sweep:,.4f}  (₹{tranche_margin_inr:,.0f})"),
        ("Averaged Entry (If Both Orders Fill)", f"${avg_entry_2x:,.4f}"),
        ("TP1 — Close 50% (Book Profit & Move SL to BE)", f"${tp1:,.4f}  (+{tp1_roe:.2f}% ROE)"),
        ("TP2 — Hold 50% Runner (Catch Big Drop/Move)", f"${tp2:,.4f}  (+{tp2_roe:.2f}% ROE)"),
        ("Catastrophe SL (Beyond Entry 2 Sweep)", f"${stop_loss:,.4f}  (-{sl_roe:.2f}% ROE)"),
        ("Total Margin (Tranche 1 + Tranche 2)", f"₹{margin_inr:,.0f} INR  (2 x ₹{tranche_margin_inr:,.0f})"),
        ("Leverage", f"{leverage}x"),
        ("Timestamp (IST)", now),
    ]
    tr = "".join(f"<tr style='border-bottom:1px solid #f1f5f9'><td style='padding:8px 12px;color:#64748b'>{k}</td>"
                 f"<td style='padding:8px 12px;font-weight:700;text-align:right;color:#0f172a'>{v}</td></tr>" for k, v in rows)

    html = f"""<html><body style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;background:#f8fafc;padding:20px;color:#1e293b;">
      <div style="max-width:540px;margin:auto;background:#ffffff;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.06);">
        <div style="background:#0f172a;color:#ffffff;padding:20px;text-align:center">
          <div style="font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#94a3b8;font-weight:700">{heading}{f' &middot; {strategy_name}' if strategy_name else ''}</div>
          <div style="font-size:22px;font-weight:800;margin-top:4px;">{pair}</div>
          <div style="margin-top:10px;display:inline-block;padding:5px 18px;border-radius:20px;background:{colour};font-weight:800;font-size:14px;color:#fff;">
            {direction} SETUP
          </div>
        </div>
        <div style="padding:16px;">
          {trend_visual_html}
          <table style="width:100%;border-collapse:collapse;font-size:14px;">{tr}</table>
          {f'<div style="margin-top:14px;padding:10px 14px;background:#f1f5f9;border-left:4px solid {colour};border-radius:4px;color:#334155;font-size:13px;"><strong>Note:</strong> {note}</div>' if note else ''}
          <div style="text-align:center;margin-top:24px;margin-bottom:8px;">
            <a href="{action_url}" style="background:#2563eb;color:#ffffff;padding:14px 28px;border-radius:8px;text-decoration:none;font-weight:800;font-size:15px;display:inline-block;box-shadow:0 4px 12px rgba(37,99,235,0.3);">
              🚀 Review &amp; Execute Trade in Assistant
            </a>
          </div>
          <p style="text-align:center;color:#64748b;font-size:12px;margin-top:10px;line-height:1.4;">
            Clicking opens the <strong>Crypto Trade Assistant</strong> with prefilled entry (${entry:,.2f}), SL, and Single TP ready for manual review.
          </p>
        </div>
      </div>
    </body></html>"""

    text = (
        f"⚡ {heading}: {direction} {pair}{f' [{strategy_name}]' if strategy_name else ''}\n"
        + "=" * 40 + "\n"
        + "\n".join(f"{k}: {v}" for k, v in rows)
        + (f"\nNote: {note}\n" if note else "\n")
        + f"\nOpen & Execute in Assistant (Pre-filled):\n{action_url}\n"
    )
    subject = f"{sym} - {strategy_name} - trade notification" if strategy_name else f"{sym} - trade notification"
    return _send(subject, html, text)


def send_test_trade_email(pair: str = "B-SOL_USDT", live_price: float = 100.0, margin_inr: float = 10000.0,
                          strategy_name: str = "Box Theory Sweep", strategy_id: str = "box_theory") -> tuple[bool, str]:
    return send_trade_email(
        pair=pair, direction="LONG", entry=live_price, stop_loss=round(live_price * 0.985, 4),
        tp1=round(live_price * 1.02, 4), tp2=round(live_price * 1.04, 4), margin_inr=margin_inr, leverage=5,
        zone="Buy Zone RL-SL", kind="SIGNAL", note="This is a TEST alert - opens prefilled Trade Execution tab.",
        strategy_name=strategy_name, strategy_id=strategy_id, trigger_reason="TEST - no real trigger"
    )
