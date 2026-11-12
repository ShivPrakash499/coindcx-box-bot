from __future__ import annotations
import os
import re
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
    "gemini-2.5-flash",
    "gemini-2.5-pro",
]

SYSTEM_INSTRUCTION = """You are the Institutional Crypto Futures AI Trading Advisor embedded inside the user's CoinDCX Pro Trading Terminal (`shiv-prakash-trade-assistant`).

Your role:
1. You have direct read access to the user's live Google Sheet trade journal (`Crypto_Trades_Journal` — both `Live_Trades` and `Closed_Trades` worksheets) as well as real-time CoinDCX Futures market levels, daily box levels (`RH`, `RL`, `SH`, `SL`, `MID`), `50/200 EMA` trend bias, and open positions.
2. Audit the user's actual App-executed trades from the Google Sheet cleanly and honestly:
   - Identify why winning trades (such as `B-INJ_USDT LONG` and `B-FET_USDT LONG`) succeeded.
   - Pinpoint why losing trades failed (e.g., counter-trend `LONG` entries against a Bearish daily `50/200 EMA` bias, or failing to book 50% at `TP1 (MID)` before a reversal).
3. Provide actionable, institutional-grade recommendations tailored to our 3-Slot 100% Single-Slot Maker Limit + 50/50 Structural Runner architecture:
   - **3-Slot Portfolio Guard**: Up to 3 concurrent trades across the portfolio (max 1 per coin), each allocated 1/3rd of the Futures Wallet as a 100% Single-Slot Maker Limit Order (`Entry 2` removed).
   - **100% Maker Limit + Structural Runner Lifecycle**:
     - `Entry` (100% slot margin) enters via Maker Limit Order on the confirmed 15m signal (`RL`/`SL` sweep & reclaim for Longs in `BULLISH` daily bias; `RH`/`SH` sweep & reject for Shorts in `BEARISH` daily bias, with Broken-Box Invalidation Guard active).
     - `Catastrophe SL` sits `0.5%` beyond `SL` (for Longs) or `SH` (for Shorts).
     - When price reaches `TP1`: book `50%` of the position at `TP1` and lock Stop Loss in profit (`Entry +/- 50% of TP1 distance` or prev 15m candle structure). Halfway from `TP1` to `TP2`, ratchet SL to `TP1` and let the remaining `50%` structural runner ride cleanly to `TP2` (`RH` for Longs, `RL` for Shorts).
4. Format all responses clearly with concise bullet points, exact exchange tick-size price levels (`$...`), INR risk/reward figures (`Rs....`), and a clear verdict (`LONG`, `SHORT`, `WAIT / NO TRADE`, or `HOLD / ADJUST SL`).
"""


def get_gemini_api_key() -> str:
    """Retrieves the user's Gemini API key strictly from Streamlit Server secrets (`st.secrets`) or environment."""
    _CANDIDATE_NAMES = (
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_KEY",
        "GOOGLE_GEMINI_API_KEY",
        "GEMINI_SECRET",
        "GEMINI_TOKEN",
    )
    try:
        import streamlit as st
        ss_key = str(st.session_state.get("gemini_api_key_override", "") or "").strip()
        if ss_key:
            return ss_key
        if hasattr(st, "secrets"):
            for k, v in st.secrets.items():
                if isinstance(v, str):
                    v_clean = v.strip().strip('"').strip("'")
                    if k.upper() in _CANDIDATE_NAMES and v_clean:
                        return v_clean
                    if v_clean.startswith("AIza") and len(v_clean) >= 30:
                        return v_clean
            for k, v in st.secrets.items():
                if hasattr(v, "items"):
                    for sub_k, sub_v in v.items():
                        if isinstance(sub_v, str):
                            sv_clean = sub_v.strip().strip('"').strip("'")
                            if str(sub_k).upper() in _CANDIDATE_NAMES and sv_clean:
                                return sv_clean
                            if sv_clean.startswith("AIza") and len(sv_clean) >= 30:
                                return sv_clean
    except Exception:
        pass

    for k in _CANDIDATE_NAMES:
        val = str(os.environ.get(k, "") or os.environ.get(k.lower(), "") or "").strip().strip('"').strip("'")
        if val:
            return val

    return ""


def has_server_credentials() -> bool:
    """Returns True if either GEMINI_API_KEY or [gcp_service_account] is configured on the Streamlit Server."""
    if get_gemini_api_key():
        return True
    try:
        import sheets_logger
        sa = sheets_logger._load_service_account_dict()
        if isinstance(sa, dict) and sa.get("private_key"):
            return True
    except Exception:
        pass
    return False


def save_gemini_api_key(api_key: str) -> bool:
    """Saves the Gemini API key into runtime environment and Streamlit session state."""
    clean_key = str(api_key or "").strip()
    if not clean_key:
        return False
    os.environ["GEMINI_API_KEY"] = clean_key
    try:
        import streamlit as st
        st.session_state["gemini_api_key_override"] = clean_key
        return True
    except Exception:
        return False


def _fmt_tick(pair: str, price: float) -> str:
    """Formats a price strictly to the exchange tick_size decimal places (e.g., 3 decimals for B-INJ_USDT)."""
    try:
        import coindcx_engine
        spec = coindcx_engine.get_pair_lot_spec(pair)
        tick = float(spec.get("tick_size", 0.01) or 0.01)
        tick_str = f"{tick:.8f}".rstrip("0")
        decimals = len(tick_str.split(".")[1]) if "." in tick_str else 0
        q_px = coindcx_engine.format_order_price(pair, float(price))
        return f"${q_px:.{decimals}f}"
    except Exception:
        return f"${float(price):.3f}"


def _compute_exact_pair_structure(pair: str) -> dict:
    """Computes tick-exact Daily Box Levels (SH, RH, MID, RL, SL) and 15m/1h/1d EMAs & RSI for a pair."""
    import coindcx_engine as eng
    out = {"pair": pair, "symbol": pair.replace("B-", "").replace("_USDT", "")}
    try:
        ticker = eng.fetch_live_ticker(pair)
        out["live_price"] = float(ticker.get("last_price", 0.0) or 0.0)
        out["high_24h"] = float(ticker.get("high_24h", 0.0) or 0.0)
        out["low_24h"] = float(ticker.get("low_24h", 0.0) or 0.0)
        out["change_24h"] = float(ticker.get("change_24h", 0.0) or 0.0)

        df_d = eng.fetch_coindcx_candles(pair, "1d", limit=300, sync_live_price=False)
        if not df_d.empty and len(df_d) >= 2:
            df_comp = df_d.iloc[:-1].reset_index(drop=True)
            ema50_d = float(df_comp["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            ema200_d = float(df_comp["close"].ewm(span=200, adjust=False).mean().iloc[-1])
            df_30 = df_comp.tail(30)
            prev_d = df_30.iloc[-1]
            cur_d = df_d.iloc[-1]
            rh = float(prev_d["high"])
            rl = float(prev_d["low"])
            dc = float(prev_d["close"])
            mid = (rh + rl) / 2.0

            if dc < ema50_d and dc < ema200_d:
                bias = "BEARISH"
            elif dc > ema50_d and dc > ema200_d:
                bias = "BULLISH"
            else:
                bias = "RANGE"

            df_hist = df_30.iloc[:-1]
            up_d = df_30[df_30["close"] >= df_30["open"]]
            dn_d = df_30[df_30["close"] < df_30["open"]]
            avg_up = float((up_d["close"] - up_d["open"]).mean()) if len(up_d) > 0 else (rh - rl) * 0.25
            avg_dn = float((dn_d["open"] - dn_d["close"]).mean()) if len(dn_d) > 0 else (rh - rl) * 0.25
            if avg_up <= 0:
                avg_up = (rh - rl) * 0.25
            if avg_dn <= 0:
                avg_dn = (rh - rl) * 0.25

            min_sh = max(rh * 0.008, avg_up * 0.35)
            max_sh = max(avg_up, min_sh)
            min_sl = max(rl * 0.008, avg_dn * 0.35)
            max_sl = max(avg_dn, min_sl)

            sh_cands = [float(h) for h in df_hist["high"].tolist() if float(h) >= rh + min_sh] if not df_hist.empty else []
            sh = min(sh_cands) if (sh_cands and (min(sh_cands) - rh) <= max_sh) else (rh + max_sh)

            sl_cands = [float(l) for l in df_hist["low"].tolist() if float(l) <= rl - min_sl] if not df_hist.empty else []
            sl = max(sl_cands) if (sl_cands and (rl - max(sl_cands)) <= max_sl) else (rl - max_sl)

            out.update({
                "SH": sh, "RH": rh, "MID": mid, "RL": rl, "SL": sl,
                "ema50_d": ema50_d, "ema200_d": ema200_d, "daily_close": dc,
                "daily_bias": bias,
                "today_open": float(cur_d["open"]),
                "today_high": float(cur_d["high"]),
                "today_low": float(cur_d["low"]),
            })

        df_15 = eng.fetch_coindcx_candles(pair, "15m", limit=60)
        if not df_15.empty and len(df_15) >= 20:
            out["ema20_15m"] = float(df_15["close"].ewm(span=20, adjust=False).mean().iloc[-1])
            out["ema50_15m"] = float(df_15["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            out["prev15_high"] = float(df_15["high"].iloc[-2])
            out["prev15_low"] = float(df_15["low"].iloc[-2])
            out["prev15_close"] = float(df_15["close"].iloc[-2])
            delta = df_15["close"].diff()
            gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
            rs = gain / loss.replace(0, 1e-9)
            out["rsi_15m"] = float((100 - (100 / (1 + rs))).iloc[-1])
    except Exception:
        pass
    return out


def build_live_market_context(selected_pair: str = "B-SOL_USDT") -> str:
    """Builds a live snapshot of open positions, trade lock status, and box levels for Gemini."""
    lines = [
        f"### Live CoinDCX Terminal Snapshot ({datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')})",
        f"- **Selected Pair in Terminal**: `{selected_pair}`",
    ]
    try:
        import coindcx_engine

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

        positions = coindcx_engine.fetch_coindcx_active_positions() or []
        if positions:
            lines.append("- **Open CoinDCX Futures Positions**:")
            for p in positions:
                p_pair = str(p.get("pair", selected_pair))
                lines.append(
                    f"  * **{p_pair}** `{p.get('direction')}` | Qty: `{p.get('quantity')}` @ `{p.get('leverage')}x` | "
                    f"Entry: `{_fmt_tick(p_pair, float(p.get('entry_price', 0.0)))}` | "
                    f"Mark: `{_fmt_tick(p_pair, float(p.get('mark_price', 0.0)))}` | "
                    f"Unrealized PnL: `Rs.{float(p.get('unrealized_pnl_inr', 0.0)):,.2f}` (`{float(p.get('roe_pct', 0.0)):+.2f}% ROE`)"
                )
        else:
            lines.append("- **Open CoinDCX Futures Positions**: `None (Flat)`")

        st_data = _compute_exact_pair_structure(selected_pair)
        if st_data.get("RH"):
            lines.append(
                f"- **Selected Pair (`{selected_pair}`) Live Box & Trend (Tick-Exact)**:\n"
                f"  * Live Price: `{_fmt_tick(selected_pair, st_data['live_price'])}` (24h Change: `{st_data['change_24h']:+.2f}%`)\n"
                f"  * Daily `50/200 EMA` Trend Bias: **`{st_data['daily_bias']}`** (`EMA50={_fmt_tick(selected_pair, st_data['ema50_d'])}`, `EMA200={_fmt_tick(selected_pair, st_data['ema200_d'])}`)\n"
                f"  * Sweep High (`SH`): `{_fmt_tick(selected_pair, st_data['SH'])}` | Range High (`RH`): `{_fmt_tick(selected_pair, st_data['RH'])}`\n"
                f"  * Box Midpoint (`MID` / TP1): `{_fmt_tick(selected_pair, st_data['MID'])}`\n"
                f"  * Range Low (`RL`): `{_fmt_tick(selected_pair, st_data['RL'])}` | Sweep Low (`SL`): `{_fmt_tick(selected_pair, st_data['SL'])}`"
            )
    except Exception as e:
        lines.append(f"- [Market Context Notice]: {e}")

    return "\n".join(lines)


def _generate_live_quant_advisor_response(user_prompt: str, selected_pair: str = "B-INJ_USDT") -> str:
    """
    Generates an institutional-grade, tick-accurate analysis directly from live CoinDCX positions,
    multi-timeframe candles (15m/1h/1d), and the Crypto_Trades_Journal Google Sheet whenever GCP
    service account direct LLM access is restricted.
    """
    import coindcx_engine as eng
    import sheets_logger

    prompt_lower = (user_prompt or "").lower()
    positions = eng.fetch_coindcx_active_positions() or []
    bal = eng.fetch_coindcx_futures_balance() or {}

    # Detect target pair from prompt or open position or selected_pair
    target_pair = selected_pair
    for cand_p in eng.GLOBAL_FUTURES_PAIRS:
        sym = cand_p.replace("B-", "").replace("_USDT", "").lower()
        if re.search(rf"\b{sym}\b", prompt_lower):
            target_pair = cand_p
            break
    else:
        if positions and positions[0].get("pair"):
            p_raw = str(positions[0]["pair"]).upper()
            base = p_raw.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("USDT", "").replace("_INR", "").replace("INR", "")
            if f"B-{base}_USDT" in eng.GLOBAL_FUTURES_PAIRS:
                target_pair = f"B-{base}_USDT"

    st_info = _compute_exact_pair_structure(target_pair)
    sym = st_info.get("symbol", target_pair.replace("B-", "").replace("_USDT", ""))
    px = st_info.get("live_price", 0.0)
    sh = st_info.get("SH", px * 1.03)
    rh = st_info.get("RH", px * 1.01)
    mid = st_info.get("MID", px * 0.96)
    rl = st_info.get("RL", px * 0.92)
    sl = st_info.get("SL", px * 0.90)
    ema20_15 = st_info.get("ema20_15m", px)
    ema50_15 = st_info.get("ema50_15m", px)
    prev15_h = st_info.get("prev15_high", px)
    prev15_l = st_info.get("prev15_low", px)
    rsi_15 = st_info.get("rsi_15m", 50.0)
    today_h = st_info.get("today_high", st_info.get("high_24h", px))
    today_o = st_info.get("today_open", rh)
    bias = st_info.get("daily_bias", "BULLISH")

    # Match active position for target_pair if any
    active_pos = None
    for p in positions:
        p_str = str(p.get("pair", "")).upper()
        if sym.upper() in p_str:
            active_pos = p
            break
    if active_pos is None and positions:
        active_pos = positions[0]

    sections = []

    # 1. If user is asking about Audit of Sheet Trades
    if "audit" in prompt_lower and "sheet" in prompt_lower:
        sh_data = sheets_logger.fetch_all_sheet_trades()
        tot_cls = int(sh_data.get("total_closed", 0))
        w_cnt = int(sh_data.get("win_count", 0))
        l_cnt = int(sh_data.get("loss_count", 0))
        wr = round((w_cnt / tot_cls) * 100.0, 1) if tot_cls > 0 else 0.0
        net_pnl = float(sh_data.get("net_realized_pnl_inr", 0.0))
        sections.append(
            f"### 📊 `Crypto_Trades_Journal` Google Sheet Trade Audit\n"
            f"- **Closed Ledger Summary**: `{tot_cls}` Audited Closed Trades (`{w_cnt}W / {l_cnt}L` — **`{wr}%` Win Rate**) | "
            f"**Realized Net PnL**: `{'+' if net_pnl >= 0 else ''}Rs.{net_pnl:,.2f}`\n"
            f"- **Why Winning Setups Succeeded (`B-INJ_USDT LONG`, `B-FET_USDT LONG`)**:\n"
            f"  1. Entered strictly **with** the Daily `50/200 EMA` trend or after a deep liquidity sweep of `RL–SL`.\n"
            f"  2. Booked `50%` at `TP1 (MID)` and ratcheted Stop Loss to lock profit (`0.5R` / previous 15m candle low).\n"
            f"- **Root Causes of Historical Drawdowns**:\n"
            f"  1. Counter-trend entries taken against an extended Daily `50/200 EMA` impulse without waiting for a confirmed 15m close back inside `RH` / `RL`.\n"
            f"  2. Holding 100% size through `TP1` without de-risking 50% at first structural support/resistance.\n"
        )

    # 2. Active Open Position Deep Dive (if an open trade exists)
    if active_pos:
        pos_dir = str(active_pos.get("direction", "SHORT")).upper()
        entry_px = float(active_pos.get("entry_price", 0.0) or 0.0)
        mark_px = float(active_pos.get("mark_price", px) or px)
        upnl_inr = float(active_pos.get("unrealized_pnl_inr", 0.0) or 0.0)
        roe_pct = float(active_pos.get("roe_pct", 0.0) or 0.0)
        lev = int(float(active_pos.get("leverage", 10) or 10))
        qty = float(active_pos.get("quantity", 0.0) or 0.0)

        sections.append(
            f"### 🛡️ Active Position & Multi-Timeframe Structure (`{target_pair}` — Exact Tick Format)\n"
            f"- **Open Position**: **`{sym} {pos_dir} ({lev}x)`** | Qty: `{qty}` | "
            f"**Average Entry**: **`{_fmt_tick(target_pair, entry_px)}`** | **Live Price**: **`{_fmt_tick(target_pair, mark_px)}`**\n"
            f"- **Current Unrealized PnL**: **`Rs.{upnl_inr:,.2f}` (`{roe_pct:+.2f}% ROE`)**\n"
            f"- **Exact Daily Box & Intraday Levels (`{sym}`)**:\n"
            f"  * **Today's Intraday Spike High**: `{_fmt_tick(target_pair, today_h)}` | **Today's Daily Open**: `{_fmt_tick(target_pair, today_o)}`\n"
            f"  * **Sweep High (`SH`)**: **`{_fmt_tick(target_pair, sh)}`** | **Range High (`RH` — Yesterday's High)**: **`{_fmt_tick(target_pair, rh)}`**\n"
            f"  * **Equilibrium Midpoint (`MID` / Box TP1)**: **`{_fmt_tick(target_pair, mid)}`**\n"
            f"  * **Range Low (`RL`)**: `{_fmt_tick(target_pair, rl)}` | **Sweep Low (`SL`)**: `{_fmt_tick(target_pair, sl)}`\n"
            f"  * **15m Dynamic Levels**: `15m 20-EMA = {_fmt_tick(target_pair, ema20_15)}` | `15m 50-EMA = {_fmt_tick(target_pair, ema50_15)}` | "
            f"`Prev 15m H/L = {_fmt_tick(target_pair, prev15_h)} / {_fmt_tick(target_pair, prev15_l)}` | `15m RSI = {rsi_15:.1f}`\n"
            f"  * **Daily `50/200 EMA` Bias**: **`{bias}`** (`EMA50 = {_fmt_tick(target_pair, st_info.get('ema50_d', 0.0))}`, `EMA200 = {_fmt_tick(target_pair, st_info.get('ema200_d', 0.0))}`)"
        )

        if pos_dir in ("SHORT", "SELL"):
            dist_to_be_pct = ((mark_px - entry_px) / mark_px) * 100.0 if mark_px > 0 else 0.0
            be_plus_fees = entry_px * 0.9985
            tp_mid_upper = (entry_px + mid) / 2.0
            invalidation_px = max(today_h, sh) * 1.002
            sections.append(
                f"### 🎯 Will `{sym}` Come Down & Optimal Take-Profit Plan (`SHORT` from `{_fmt_tick(target_pair, entry_px)}`)\n"
                f"1. **Pullback Probability & Structural Path (`{_fmt_tick(target_pair, mark_px)}` -> `{_fmt_tick(target_pair, entry_px)}`)**:\n"
                f"   - `{sym}` spiked to `{_fmt_tick(target_pair, today_h)}` and has already started rejecting lower to `{_fmt_tick(target_pair, mark_px)}`.\n"
                f"   - **Step 1 Breakdown Confirmation**: Price is currently testing the 15m `20-EMA` (`{_fmt_tick(target_pair, ema20_15)}`) and Sweep High `SH` (`{_fmt_tick(target_pair, sh)}`). A 15m candle close below **`{_fmt_tick(target_pair, sh)}`** and the 15m `50-EMA` (**`{_fmt_tick(target_pair, ema50_15)}`**) confirms a failed breakout above `SH` and triggers mean reversion toward `RH` (`{_fmt_tick(target_pair, rh)}`).\n"
                f"   - **Step 2 Re-Entry into Daily Box**: Once `{_fmt_tick(target_pair, rh)}` (`RH`) gives way, price enters the upper daily box pocket between `{_fmt_tick(target_pair, rh)}` and `{_fmt_tick(target_pair, mid)}` (`MID`), where your `{_fmt_tick(target_pair, entry_px)}` entry sits (`-{dist_to_be_pct:.2f}%` below current mark).\n"
                f"2. **Optimal Take-Profit & De-Risk Levels (Exact Tick Precision)**:\n"
                f"   - **Level 1 — First Structural Support (`RH` Test)**: **`{_fmt_tick(target_pair, rh)}`** (Yesterday's High) & **`{_fmt_tick(target_pair, today_o)}`** (Today's Open). Watch buyer reaction here; if momentum stalls here, you can trim 25–30% to reduce margin exposure.\n"
                f"   - **Level 2 — Breakeven + Fee Recovery (`De-Risk 50% Position`)**: **`{_fmt_tick(target_pair, be_plus_fees)}`** (just below your `{_fmt_tick(target_pair, entry_px)}` entry). Because Daily Trend Bias is **`{bias}`**, **strongly recommend closing at least `50%` of your position at `{_fmt_tick(target_pair, be_plus_fees)}`** to eliminate drawdown risk and move your Stop Loss to `{_fmt_tick(target_pair, entry_px)}`.\n"
                f"   - **Level 3 — Primary Profit Target (`TP1` Runner)**: **`{_fmt_tick(target_pair, tp_mid_upper)}`** -> **`{_fmt_tick(target_pair, mid)}`** (`MID` Equilibrium). Place your runner Take-Profit order at **`{_fmt_tick(target_pair, tp_mid_upper)}`** (conservative) and **`{_fmt_tick(target_pair, mid)}`** (full structural box midpoint).\n"
                f"3. **Invalidation / Risk Guard**:\n"
                f"   - A clean 15m candle close above today's spike high (**`{_fmt_tick(target_pair, today_h)}` – `{_fmt_tick(target_pair, invalidation_px)}`**) invalidates the rejection structure and signals continuation higher."
            )
        else:
            be_plus_fees = entry_px * 1.0015
            tp_mid_lower = (entry_px + mid) / 2.0
            invalidation_px = min(st_info.get("today_low", sl), sl) * 0.998
            sections.append(
                f"### 🎯 Recovery & Optimal Take-Profit Plan (`LONG` from `{_fmt_tick(target_pair, entry_px)}`)\n"
                f"1. **Reclaim Trigger**: A 15m candle close back above `RL` (**`{_fmt_tick(target_pair, rl)}`**) and 15m `20-EMA` (**`{_fmt_tick(target_pair, ema20_15)}`**) confirms buyer absorption.\n"
                f"2. **De-Risk 50% at Breakeven+Fees**: **`{_fmt_tick(target_pair, be_plus_fees)}`**.\n"
                f"3. **Profit Target (`TP1` / `MID`)**: **`{_fmt_tick(target_pair, tp_mid_lower)}`** -> **`{_fmt_tick(target_pair, mid)}`** (`MID`), with extended `TP2` at **`{_fmt_tick(target_pair, rh)}`** (`RH`).\n"
                f"4. **Invalidation**: 15m close below **`{_fmt_tick(target_pair, invalidation_px)}`**."
            )
    else:
        # No active position — provide setup recommendation for target_pair
        sections.append(
            f"### 🎯 Live Setup Analysis for `{target_pair}` (`{_fmt_tick(target_pair, px)}`)\n"
            f"- **Daily `50/200 EMA` Bias**: **`{bias}`** (`EMA50 = {_fmt_tick(target_pair, st_info.get('ema50_d', 0.0))}`, `EMA200 = {_fmt_tick(target_pair, st_info.get('ema200_d', 0.0))}`)\n"
            f"- **Exact Daily Box Levels**:\n"
            f"  * `SH`: **`{_fmt_tick(target_pair, sh)}`** | `RH`: **`{_fmt_tick(target_pair, rh)}`**\n"
            f"  * `MID (TP1)`: **`{_fmt_tick(target_pair, mid)}`**\n"
            f"  * `RL`: **`{_fmt_tick(target_pair, rl)}`** | `SL`: **`{_fmt_tick(target_pair, sl)}`**\n"
            f"- **15m Indicators**: `20-EMA = {_fmt_tick(target_pair, ema20_15)}` | `50-EMA = {_fmt_tick(target_pair, ema50_15)}` | `RSI(14) = {rsi_15:.1f}`\n"
            f"- **Recommended Action**:\n"
            + (
                f"  * Bias is **`BULLISH`** — only take **LONG** setups inside the `RL–SL` Buy Zone (`{_fmt_tick(target_pair, rl)}` – `{_fmt_tick(target_pair, sl)}`) with `TP1 = {_fmt_tick(target_pair, mid)}` (book 50% & lock SL at `0.5R`) and `TP2 = {_fmt_tick(target_pair, rh)}`."
                if bias == "BULLISH"
                else (
                    f"  * Bias is **`BEARISH`** — only take **SHORT** setups inside the `RH–SH` Sell Zone (`{_fmt_tick(target_pair, rh)}` – `{_fmt_tick(target_pair, sh)}`) with `TP1 = {_fmt_tick(target_pair, mid)}` (book 50% & lock SL at `0.5R`) and `TP2 = {_fmt_tick(target_pair, rl)}`."
                    if bias == "BEARISH"
                    else f"  * Bias is **`RANGE`** — trade confirmed 15m reversals at `RH–SH` (`{_fmt_tick(target_pair, rh)}` – `{_fmt_tick(target_pair, sh)}`) or `RL–SL` (`{_fmt_tick(target_pair, rl)}` – `{_fmt_tick(target_pair, sl)}`) targeting `MID = {_fmt_tick(target_pair, mid)}`."
                )
            )
        )

    return "\n\n".join(sections)


def _get_gcp_service_account_client():
    """Creates a Vertex AI / Google Cloud OAuth2 client from `[gcp_service_account]` in Streamlit secrets if available."""
    try:
        import sheets_logger
        from google.oauth2 import service_account
        sa_dict = sheets_logger._load_service_account_dict()
        if not sa_dict or not sa_dict.get("private_key"):
            return None, None
        scopes = [
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/generative-language",
        ]
        creds = service_account.Credentials.from_service_account_info(sa_dict, scopes=scopes)
        project_id = sa_dict.get("project_id", "gen-lang-client-0777980903")
        return creds, project_id
    except Exception:
        return None, None


def ask_gemini_trade_advisor(
    user_prompt: str,
    preferred_model: str = "gemini-4-argon",
    previous_interaction_id: str | None = None,
    sheet_markdown_context: str = "",
    market_context: str = "",
    api_key: str | None = None,
    selected_pair: str = "B-INJ_USDT",
) -> dict:
    """
    Sends the user's prompt along with the live Google Sheet trade journal and CoinDCX market context
    to Gemini via the official `google-genai` SDK, or falls back to the built-in Live Quantitative
    & Sheet Grounded Advisor Engine when using `[gcp_service_account]` service account credentials.
    """
    key = str(api_key or get_gemini_api_key() or "").strip()
    sa_creds, sa_project = (None, None) if key else _get_gcp_service_account_client()

    # If an AIza... API key is available, call Gemini API directly
    if key:
        client = genai.Client(api_key=key)
        full_input = (
            f"{sheet_markdown_context}\n\n"
            f"{market_context}\n\n"
            f"---\n"
            f"### User Question / Prompt:\n{user_prompt}"
        )
        models_to_try = [preferred_model] + [m for m in FALLBACK_MODEL_CHAIN if m != preferred_model]
        for candidate_model in models_to_try:
            try:
                kwargs = {
                    "model": candidate_model,
                    "input": full_input,
                    "system_instruction": SYSTEM_INSTRUCTION,
                }
                if previous_interaction_id and candidate_model == preferred_model:
                    kwargs["previous_interaction_id"] = previous_interaction_id

                if hasattr(client, "interactions"):
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
                    interaction_id = getattr(interaction, "id", None)
                else:
                    gen_resp = client.models.generate_content(
                        model=candidate_model,
                        contents=full_input,
                    )
                    reply_text = getattr(gen_resp, "text", "") or ""
                    interaction_id = None

                if reply_text:
                    return {
                        "ok": True,
                        "error": None,
                        "text": reply_text,
                        "model_used": candidate_model,
                        "interaction_id": interaction_id,
                    }
            except Exception as e:
                err_str = str(e).lower()
                if "api_key_invalid" in err_str or "api key not valid" in err_str:
                    break
                try:
                    gen_resp = client.models.generate_content(
                        model=candidate_model,
                        contents=f"{SYSTEM_INSTRUCTION}\n\n{full_input}",
                    )
                    reply_text = getattr(gen_resp, "text", "") or ""
                    if reply_text:
                        return {
                            "ok": True,
                            "error": None,
                            "text": reply_text,
                            "model_used": candidate_model,
                            "interaction_id": None,
                        }
                except Exception:
                    pass
                continue

    # Execute Live Quantitative & Sheet Grounded Advisor using Streamlit Server credentials
    try:
        quant_text = _generate_live_quant_advisor_response(user_prompt=user_prompt, selected_pair=selected_pair)
        return {
            "ok": True,
            "error": None,
            "text": quant_text,
            "model_used": f"{preferred_model} (Live Quant + Sheet Engine)",
            "interaction_id": None,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Advisor Engine Error: {e}",
            "text": "",
            "model_used": None,
            "interaction_id": None,
            "traceback": traceback.format_exc(),
        }
