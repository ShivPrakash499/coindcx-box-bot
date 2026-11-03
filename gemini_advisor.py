from __future__ import annotations
import os
import traceback
from datetime import datetime
import pytz
from google import genai

IST = pytz.timezone("Asia/Kolkata")

AVAILABLE_GEMINI_MODELS = [
    ("gemini-4-argon", "Gemini 4 Argon (Frontier Reasoning — Best for Deep Trade Audits & Strategy)"),
    ("gemini-3.8-flash", "Gemini 3.8 Flash (High-Speed Agentic — Fast Live Setup & Risk Recommendations)"),
    ("gemini-3.5-flash-lite", "Gemini 3.5 Flash-Lite (Ultra-Low Latency Quick Checks)"),
]

FALLBACK_MODEL_CHAIN = [
    "gemini-4-argon",
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
]

SYSTEM_INSTRUCTION = """You are the Institutional Crypto Futures AI Trading Advisor embedded inside the user's CoinDCX Pro Trading Terminal (`shiv-prakash-trade-assistant`).

Your role:
1. You have direct read access to the user's live Google Sheet trade journal (`Crypto_Trades_Journal` — both `Live_Trades` and `Closed_Trades` worksheets) as well as real-time CoinDCX Futures market levels, daily box levels (`RH`, `RL`, `SH`, `SL`, `MID`), `50/200 EMA` trend bias, and open positions.
2. Audit the user's actual App-executed trades from the Google Sheet cleanly and honestly:
   - Identify why winning trades (such as `B-INJ_USDT LONG` and `B-FET_USDT LONG`) succeeded.
   - Pinpoint why losing trades failed (e.g., counter-trend `LONG` entries against a Bearish daily `50/200 EMA` bias, or failing to book 50% at `TP1 (MID)` before a reversal).
3. Provide actionable, institutional-grade recommendations tailored to our exact V1 (`827536a` / `5410c11`) Box Theory Sweep + 2-Entry Scale-In + 50/50 Runner architecture:
   - **Strict 1-Crypto-at-a-Time Rule**: Never open a second coin while an App Trade Lock or live position is open; reserve 50% of single-trade margin for `Entry 2 @ Sweep` (`SL` for Longs, `SH` for Shorts).
   - **2-Entry + 50/50 Runner Lifecycle**:
     - `Entry 1` (50% margin) enters on the signal trigger (`RL` sweep & reclaim for Longs; `RH` sweep & reject for Shorts).
     - `Entry 2` (50% margin) rests as a limit order at `SL` (for Longs) or `SH` (for Shorts).
     - If price hits `TP1` (`MID`) first without touching `Entry 2`: cancel `Entry 2`, book 50% of `Entry 1` at `TP1`, and ratchet Stop Loss into profit (`Entry 1 +/- 50% of TP1 distance`) while letting the remaining 50% ride to `TP2` (`RH` for Longs, `RL` for Shorts).
4. Format all responses clearly with concise bullet points, exact price levels (`$...`), INR risk/reward figures (`Rs....`), and a clear verdict (`LONG`, `SHORT`, `WAIT / NO TRADE`, or `HOLD / ADJUST SL`).
"""


def get_gemini_api_key() -> str:
    """Retrieves the user's Gemini API key from Streamlit secrets, environment, or saved config."""
    # 1. Check Streamlit session state first
    try:
        import streamlit as st
        ss_key = str(st.session_state.get("gemini_api_key_override", "") or "").strip()
        if ss_key:
            return ss_key
        if hasattr(st, "secrets"):
            for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                if k in st.secrets and str(st.secrets[k]).strip():
                    return str(st.secrets[k]).strip()
    except Exception:
        pass

    # 2. Check environment variables
    for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        val = str(os.environ.get(k, "") or "").strip()
        if val:
            return val

    # 3. Check persisted autotrade_config.json
    try:
        import coindcx_engine
        cfg = coindcx_engine.get_autotrade_config()
        saved_key = str(cfg.get("gemini_api_key", "") or "").strip()
        if saved_key:
            return saved_key
    except Exception:
        pass

    return ""


def save_gemini_api_key(api_key: str) -> bool:
    """Saves the Gemini API key into runtime environment, Streamlit session state, and local config."""
    clean_key = str(api_key or "").strip()
    if not clean_key:
        return False
    os.environ["GEMINI_API_KEY"] = clean_key
    try:
        import streamlit as st
        st.session_state["gemini_api_key_override"] = clean_key
    except Exception:
        pass
    try:
        import coindcx_engine
        coindcx_engine.save_autotrade_config({"gemini_api_key": clean_key})
        return True
    except Exception:
        return False


def build_live_market_context(selected_pair: str = "B-SOL_USDT") -> str:
    """Builds a live snapshot of open positions, trade lock status, and box levels for Gemini."""
    lines = [
        f"### Live CoinDCX Terminal Snapshot ({datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')})",
        f"- **Selected Pair in Terminal**: `{selected_pair}`",
    ]
    try:
        import coindcx_engine

        # 1. Wallet & Slot Lock
        bal = coindcx_engine.fetch_coindcx_futures_balance()
        slot = coindcx_engine.get_active_portfolio_trade_status()
        lines.append(
            f"- **Wallet Balance**: `Rs.{float(bal.get('total_inr', 0.0)):,.2f}` "
            f"(Available: `Rs.{float(bal.get('available_inr', 0.0)):,.2f}`, Live API: `{bal.get('is_live_api')}`)"
        )
        lines.append(
            f"- **1-Crypto-at-a-Time Slot Status**: "
            f"`{'OCCUPIED by ' + str(slot.get('active_pair')) if slot.get('is_occupied') else 'FREE (0/1 Active)'}` "
            f"({slot.get('source', '')})"
        )

        # 2. Active CoinDCX Positions
        positions = coindcx_engine.fetch_coindcx_active_positions() or []
        if positions:
            lines.append("- **Open CoinDCX Futures Positions**:")
            for p in positions:
                lines.append(
                    f"  * **{p.get('pair')}** `{p.get('direction')}` | Qty: `{p.get('quantity')}` @ `{p.get('leverage')}x` | "
                    f"Entry: `${p.get('entry_price')}` | Mark: `${p.get('mark_price')}` | "
                    f"TP: `{p.get('take_profit')}` | SL: `{p.get('stop_loss')}` | "
                    f"Unrealized PnL: `Rs.{float(p.get('pnl_inr', 0.0)):+,.2f}` (`{float(p.get('roe_pct', 0.0)):+.2f}% ROE`)"
                )
        else:
            lines.append("- **Open CoinDCX Futures Positions**: None currently open.")

        # 3. Selected Pair Box Levels & Signal Evaluation
        levels = coindcx_engine.calculate_daily_box_levels(selected_pair)
        tk = coindcx_engine.fetch_live_ticker(selected_pair)
        live_px = float(tk.get("last_price", 0.0) or 0.0)
        chg_24h = float(tk.get("change_24h_pct", 0.0) or 0.0)
        if levels:
            lines.append(
                f"- **`{selected_pair}` Live Price**: `${live_px}` (`{chg_24h:+.2f}%` 24h) | "
                f"**Daily Box Levels**: `SH=${levels.get('SH')}`, `RH=${levels.get('RH')}`, "
                f"`MID=${levels.get('MID')}`, `RL=${levels.get('RL')}`, `SL=${levels.get('SL')}`"
            )
            sig = coindcx_engine.evaluate_tri_session_signal(selected_pair, levels)
            if sig:
                lines.append(
                    f"- **`{selected_pair}` Active Signal Status**: `{sig.get('signal')}` | "
                    f"Bias: `{sig.get('market_bias', 'NEUTRAL')}` | "
                    f"Reason: {sig.get('reason', '')}"
                )
    except Exception as e:
        lines.append(f"- [Market Context Notice]: {e}")

    return "\n".join(lines)


def ask_gemini_trade_advisor(
    user_prompt: str,
    preferred_model: str = "gemini-4-argon",
    previous_interaction_id: str | None = None,
    sheet_markdown_context: str = "",
    market_context: str = "",
    api_key: str | None = None,
) -> dict:
    """
    Sends the user's prompt along with the live Google Sheet trade journal and CoinDCX market context
    to Gemini via the official `google-genai` Interactions API (`client.interactions.create`).
    Automatically falls back across `FALLBACK_MODEL_CHAIN` if a model tier is unavailable on the key.
    """
    key = str(api_key or get_gemini_api_key() or "").strip()
    if not key:
        return {
            "ok": False,
            "error": (
                "Missing `GEMINI_API_KEY`. Click **+ Create Gemini API key** on your Google Cloud Console "
                "(Project `gen-lang-client-0777980903`) or Google AI Studio (`https://aistudio.google.com/apikey`) "
                "and paste it in the **Gemini API Key** box above."
            ),
            "text": "",
            "model_used": None,
            "interaction_id": previous_interaction_id,
        }

    client = genai.Client(api_key=key)

    # Construct the grounded input combining live Google Sheet data + terminal snapshot + user question
    full_input = (
        f"{sheet_markdown_context}\n\n"
        f"{market_context}\n\n"
        f"---\n"
        f"### User Question / Prompt:\n{user_prompt}"
    )

    models_to_try = [preferred_model] + [m for m in FALLBACK_MODEL_CHAIN if m != preferred_model]
    last_err = None

    for candidate_model in models_to_try:
        try:
            kwargs = {
                "model": candidate_model,
                "input": full_input,
                "system_instruction": SYSTEM_INSTRUCTION,
            }
            # Only pass previous_interaction_id if continuing on the same model
            if previous_interaction_id and candidate_model == preferred_model:
                kwargs["previous_interaction_id"] = previous_interaction_id

            interaction = client.interactions.create(**kwargs)
            reply_text = getattr(interaction, "output_text", None) or ""
            if not reply_text and getattr(interaction, "outputs", None):
                parts = []
                for out in interaction.outputs:
                    if getattr(out, "type", "") == "text" or hasattr(out, "text"):
                        txt = getattr(out, "text", "")
                        if txt:
                            parts.append(str(txt))
                reply_text = "\n".join(parts)

            if not reply_text:
                reply_text = "No text output returned by the model."

            return {
                "ok": True,
                "error": None,
                "text": reply_text,
                "model_used": candidate_model,
                "interaction_id": getattr(interaction, "id", None),
            }
        except Exception as e:
            last_err = e
            err_str = str(e).lower()
            # If the API key itself is invalid, fail fast without trying other models
            if "api_key_invalid" in err_str or "api key not valid" in err_str:
                break
            continue

    return {
        "ok": False,
        "error": f"Gemini API Error: {last_err}",
        "text": "",
        "model_used": None,
        "interaction_id": previous_interaction_id,
        "traceback": traceback.format_exc(),
    }
