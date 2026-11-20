from __future__ import annotations
import os
import re
import traceback
from datetime import datetime
import pytz
from google import genai
from google.genai import types as genai_types

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
    "gemini-3.1-flash-lite",
]

_VERTEX_SA_STATE = {"checked": False, "usable": False, "reason": ""}

SYSTEM_INSTRUCTION = """You are the Institutional Crypto Futures AI Trading Advisor embedded inside the user's CoinDCX Pro Trading Terminal (`shiv-prakash-trade-assistant`).

Your role:
1. Answer the user's ACTUAL question directly, thoroughly, and honestly using the live data provided in context:
   - The user's live Google Sheet trade journal (`Crypto_Trades_Journal` — `Live_Trades` & `Closed_Trades` worksheets + per-coin performance stats).
   - Live CoinDCX Futures wallet balance, open positions (with real INR PnL & ROE%), 3-Slot trade locks, Market Trend Regime, and the 12-coin high-volatility watchlist.
   - Exact Daily Box Levels (`SH`, `RH`, `MID`, `RL`, `SL`), Daily `50/200 EMA` trend bias, and `15m 20/50/200 EMA` structure.
2. Follow our exact trading architecture when giving advice:
   - **3-Slot Portfolio & Exact Sidebar Margin Guard**: Strictly up to 3 concurrent trades across the portfolio (counting both filled positions AND resting Entry 1 Limit Orders; max 1 per coin), honoring the user's exact Sidebar `Single-Trade Margin (INR)` and skipping cleanly when free margin is `<90%` of target slot margin (zero dust trades).
   - **Priority 1 — Box Theory Sweep (`box_theory`)**: 100% single-slot Maker Limit entry on confirmed 15m `RL/SL` reclaim (`BULLISH` / `RANGE`) or `RH/SH` rejection (`BEARISH` / `RANGE`), with Broken-Box Invalidation Guard. Catastrophe SL sits `0.5%` beyond `SL` / `SH`.
   - **Priority 2 — 15m 50/200 EMA Pullback (`ema50_200`, Regime-Adaptive + 3h Structure-Aware TP1 + Box-Floor Guard)**:
     * Runs Bull `15m 50>200 EMA` Longs in `STRONG_UPTREND`, Bear `15m 50<200 EMA` Shorts in `STRONG_DOWNTREND`, and auto-pauses in `RANGING_CHOP` (letting Box Sweep trade range edges). Max 2 of 3 slots for EMA trades, 4h same-zone re-entry lock, `<0.35%` SL price-drift abort.
   - **50/50 Structural Runner Exit**: Book `50%` at `TP1` and lock SL in profit (`Entry +/- 50% of TP1 distance` or prev 15m structure); halfway from `TP1` to `TP2`, ratchet SL to `TP1` and let remaining `50%` run to `TP2` (`RH`/`RL`).
3. Format all responses clearly with concise bullet points, exact exchange tick-size price levels (`$...`), INR risk/reward figures (`Rs....`), and a clear verdict directly addressing the user's prompt.
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


def _pos_upnl_inr(pos: dict) -> float:
    """Reads Unrealized PnL (INR) accurately from CoinDCX active position dicts (`pnl_inr` or `unrealized_pnl_inr`)."""
    if not isinstance(pos, dict):
        return 0.0
    val = pos.get("pnl_inr")
    if val is None or val == "":
        val = pos.get("unrealized_pnl_inr", 0.0)
    try:
        return float(val or 0.0)
    except Exception:
        return 0.0


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


def _parse_float_safe(raw) -> float:
    s = str(raw if raw is not None else "0").replace(",", "").replace("₹", "").replace("Rs.", "").replace("$", "").replace("%", "").strip()
    try:
        return float(s)
    except Exception:
        return 0.0


def _compute_exact_pair_structure(pair: str) -> dict:
    """
    Computes tick-exact Daily Box Levels (SH, RH, MID, RL, SL) via `coindcx_engine.calculate_daily_box_levels`
    (so levels match Chart & Signals 100% identically!) plus 15m EMAs & RSI(14).
    """
    import coindcx_engine as eng
    out = {"pair": pair, "symbol": pair.replace("B-", "").replace("_USDT", "")}
    try:
        ticker = eng.fetch_live_ticker(pair)
        out["live_price"] = float(ticker.get("last_price", 0.0) or 0.0)
        out["high_24h"] = float(ticker.get("high_24h", 0.0) or 0.0)
        out["low_24h"] = float(ticker.get("low_24h", 0.0) or 0.0)
        out["change_24h"] = float(ticker.get("change_24h", 0.0) or 0.0)

        box = eng.calculate_daily_box_levels(pair)
        if isinstance(box, dict) and box.get("RH"):
            raw_bias = str(box.get("trend_bias", "NEUTRAL")).upper()
            disp_bias = "RANGE" if raw_bias == "NEUTRAL" else raw_bias
            out.update({
                "SH": float(box["SH"]),
                "RH": float(box["RH"]),
                "MID": float(box["MID"]),
                "RL": float(box["RL"]),
                "SL": float(box["SL"]),
                "ema50_d": float(box.get("EMA50", 0.0) or 0.0),
                "ema200_d": float(box.get("EMA200", 0.0) or 0.0),
                "daily_close": float(box.get("daily_close", 0.0) or 0.0),
                "daily_bias": disp_bias,
                "raw_box": box,
            })

        df_d = eng.fetch_coindcx_candles(pair, "1d", limit=3, sync_live_price=False)
        if df_d is not None and not df_d.empty:
            cur_d = df_d.iloc[-1]
            out["today_open"] = float(cur_d["open"])
            out["today_high"] = float(cur_d["high"])
            out["today_low"] = float(cur_d["low"])

        df_15 = eng.fetch_coindcx_candles(pair, "15m", limit=250, sync_live_price=False)
        if df_15 is not None and not df_15.empty and len(df_15) >= 20:
            now_ms_15 = int(datetime.now(IST).timestamp() * 1000)
            c15 = df_15[df_15["timestamp"] + 900000 <= now_ms_15]
            if c15.empty or len(c15) < 20:
                c15 = df_15
            out["ema20_15m"] = float(c15["close"].ewm(span=20, adjust=False).mean().iloc[-1])
            out["ema50_15m"] = float(c15["close"].ewm(span=50, adjust=False).mean().iloc[-1])
            out["ema200_15m"] = float(c15["close"].ewm(span=200, adjust=False).mean().iloc[-1])
            out["prev15_high"] = float(c15["high"].iloc[-2])
            out["prev15_low"] = float(c15["low"].iloc[-2])
            out["prev15_close"] = float(c15["close"].iloc[-2])
            delta = c15["close"].diff()
            gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
            loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
            rs = gain / loss.replace(0, 1e-9)
            out["rsi_15m"] = float((100 - (100 / (1 + rs))).iloc[-1])
    except Exception:
        pass
    return out


def _summarize_sheet_performance(sh_data: dict | None) -> dict:
    """Aggregates `Crypto_Trades_Journal` (`Closed_Trades` & `Live_Trades`) by coin and direction."""
    sd = sh_data if isinstance(sh_data, dict) else {}
    closed = sd.get("closed_trades") or []
    live = sd.get("live_trades") or []

    by_coin: dict[str, dict] = {}
    by_dir: dict[str, dict] = {
        "LONG": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
        "SHORT": {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0},
    }
    tot_wins, tot_losses, tot_pnl = 0, 0, 0.0

    for row in closed:
        if not isinstance(row, dict):
            continue
        pair = str(row.get("Pair") or "UNKNOWN").strip()
        sym = pair.replace("B-", "").replace("_USDT", "")
        d_raw = str(row.get("Direction") or "").upper().strip()
        norm_d = "LONG" if d_raw in ("LONG", "BUY") else "SHORT"
        pnl = _parse_float_safe(
            row.get("Net PnL (INR)") if row.get("Net PnL (INR)") not in (None, "") else row.get("Realized PnL (INR)", 0.0)
        )
        res_txt = str(row.get("Result") or row.get("Exit Reason") or "").upper()
        is_win = (pnl > 0) or (pnl == 0 and "WIN" in res_txt)

        rec = by_coin.setdefault(sym, {"pair": pair, "sym": sym, "trades": 0, "wins": 0, "losses": 0, "pnl": 0.0})
        rec["trades"] += 1
        rec["pnl"] += pnl
        by_dir[norm_d]["trades"] += 1
        by_dir[norm_d]["pnl"] += pnl
        tot_pnl += pnl
        if is_win:
            rec["wins"] += 1
            by_dir[norm_d]["wins"] += 1
            tot_wins += 1
        else:
            rec["losses"] += 1
            by_dir[norm_d]["losses"] += 1
            tot_losses += 1

    coin_list = []
    for rec in by_coin.values():
        t = rec["trades"]
        rec["wr"] = round((rec["wins"] / t) * 100.0, 1) if t > 0 else 0.0
        rec["pnl"] = round(rec["pnl"], 2)
        coin_list.append(rec)
    coin_list.sort(key=lambda x: (-x["pnl"], -x["wr"]))

    # Also summarize recent live_trades activity by coin (last 40 logged orders)
    live_counts: dict[str, int] = {}
    for lr in live[-40:]:
        if isinstance(lr, dict):
            s_l = str(lr.get("Pair") or "").replace("B-", "").replace("_USDT", "")
            if s_l:
                live_counts[s_l] = live_counts.get(s_l, 0) + 1

    tot_cls = tot_wins + tot_losses
    return {
        "total_logged": int(sd.get("total_logged", len(live)) or len(live)),
        "total_closed": tot_cls,
        "wins": tot_wins,
        "losses": tot_losses,
        "win_rate": round((tot_wins / tot_cls) * 100.0, 1) if tot_cls > 0 else 0.0,
        "net_pnl": round(tot_pnl, 2),
        "by_coin": coin_list,
        "by_dir": by_dir,
        "recent_live_counts": live_counts,
        "live_trades": live,
        "closed_trades": closed,
    }


def _scan_watchlist_opportunities(top_n: int = 12) -> list[dict]:
    """Scans the high-volatility watchlist to rank coins closest to actionable Daily Box / EMA zones right now."""
    import coindcx_engine as eng
    rows = []
    try:
        pairs = eng.get_high_volatility_watchlist(top_n=top_n)
    except Exception:
        pairs = list(eng.HIGH_VOL_FUTURES_UNIVERSE[:top_n])

    for p in pairs:
        try:
            tk = eng.fetch_live_ticker(p) or {}
            px = float(tk.get("last_price", 0.0) or 0.0)
            chg = float(tk.get("change_24h", 0.0) or 0.0)
            lv = eng.calculate_daily_box_levels(p)
            if not lv or px <= 0:
                continue
            rh, rl, sh, sl, mid = float(lv["RH"]), float(lv["RL"]), float(lv["SH"]), float(lv["SL"]), float(lv["MID"])
            tb = str(lv.get("trend_bias", "NEUTRAL")).upper()
            sym = p.replace("B-", "").replace("_USDT", "")

            # Compute distance to valid actionable trigger edge matching Daily Bias
            dist_rh = abs(rh - px) / px * 100.0
            dist_rl = abs(px - rl) / px * 100.0

            if tb == "BEARISH":
                action_side = "SHORT"
                target_edge = rh
                dist_pct = 0.0 if (rh <= px <= sh) else dist_rh
                zone_status = "IN SELL ZONE (RH–SH)" if (rh <= px <= sh) else ("ABOVE SH" if px > sh else f"{dist_rh:.1f}% below RH")
            elif tb == "BULLISH":
                action_side = "LONG"
                target_edge = rl
                dist_pct = 0.0 if (sl <= px <= rl) else dist_rl
                zone_status = "IN BUY ZONE (RL–SL)" if (sl <= px <= rl) else ("BELOW SL" if px < sl else f"{dist_rl:.1f}% above RL")
            else:
                if dist_rh <= dist_rl:
                    action_side = "SHORT (Range)"
                    target_edge = rh
                    dist_pct = 0.0 if (rh <= px <= sh) else dist_rh
                    zone_status = (
                        "IN SELL ZONE (RH–SH)" if (rh <= px <= sh)
                        else (f"ABOVE SH ({dist_rh:.1f}% above RH)" if px > sh else f"{dist_rh:.1f}% below RH")
                    )
                else:
                    action_side = "LONG (Range)"
                    target_edge = rl
                    dist_pct = 0.0 if (sl <= px <= rl) else dist_rl
                    zone_status = (
                        "IN BUY ZONE (RL–SL)" if (sl <= px <= rl)
                        else (f"BELOW SL ({dist_rl:.1f}% below RL)" if px < sl else f"{dist_rl:.1f}% above RL")
                    )

            rows.append({
                "pair": p,
                "sym": sym,
                "price": px,
                "chg_24h": chg,
                "bias": "RANGE" if tb == "NEUTRAL" else tb,
                "action_side": action_side,
                "target_edge": target_edge,
                "dist_pct": round(dist_pct, 2),
                "zone_status": zone_status,
                "SH": sh, "RH": rh, "MID": mid, "RL": rl, "SL": sl,
            })
        except Exception:
            continue

    rows.sort(key=lambda r: (r["dist_pct"], -abs(r["chg_24h"])))
    return rows


def build_live_market_context(selected_pair: str = "B-SOL_USDT") -> str:
    """Builds a comprehensive live snapshot of wallet, open positions, regime, watchlist, and selected coin for Gemini."""
    lines = [
        f"### Live CoinDCX Terminal Snapshot ({datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST')})",
        f"- **Selected Pair in Terminal**: `{selected_pair}`",
    ]
    try:
        import coindcx_engine
        import strategies as strat_reg

        auto_cfg = coindcx_engine.get_autotrade_config()
        auto_mode_id = strat_reg.resolve_autotrade_mode(auto_cfg.get("autotrade_strategy_mode"))
        auto_mode_lbl = strat_reg.autotrade_mode_label(auto_mode_id)
        reg_info = coindcx_engine.compute_market_regime()
        bal = coindcx_engine.fetch_coindcx_futures_balance() or {}
        slot = coindcx_engine.get_active_portfolio_trade_status() or {}
        max_slots = int(slot.get("max_slots", coindcx_engine.MAX_CONCURRENT_TRADES) or 3)
        slot_cnt = int(slot.get("count", 0) or 0)
        slot_pairs = ", ".join(slot.get("active_pairs") or []) or "None"
        cfg_margin = float(auto_cfg.get("single_trade_margin_inr", 0.0) or 0.0)
        cfg_lev = int(auto_cfg.get("leverage", 10) or 10)

        lines.append(f"- **Active AutoTrade / Strategy Mode**: `{auto_mode_lbl}` (`{auto_mode_id}`)")
        lines.append(f"- **Detected Market Trend Regime**: `{reg_info.get('summary', '')}`")
        lines.append(
            f"- **Wallet Balance**: `Rs.{float(bal.get('total_inr', 0.0) or 0.0):,.2f}` "
            f"(Available: `Rs.{float(bal.get('available_inr', 0.0) or 0.0):,.2f}`, Live API: `{bal.get('is_live_api')}`)"
        )
        lines.append(f"- **Configured Sidebar Sizing**: `Rs.{cfg_margin:,.2f}` margin @ `{cfg_lev}x` leverage")
        lines.append(
            f"- **3-Slot Portfolio Status**: `{slot_cnt}/{max_slots} Active` (`{slot_pairs}` | {slot.get('source', '')})"
        )

        positions = coindcx_engine.fetch_coindcx_active_positions() or []
        if positions:
            lines.append("- **Open CoinDCX Futures Positions**:")
            for p in positions:
                p_pair = str(p.get("pair", selected_pair))
                upnl = _pos_upnl_inr(p)
                lines.append(
                    f"  * **{p_pair}** `{p.get('direction')}` | Qty: `{p.get('quantity')}` @ `{p.get('leverage')}x` | "
                    f"Entry: `{_fmt_tick(p_pair, float(p.get('entry_price', 0.0) or 0.0))}` | "
                    f"Mark: `{_fmt_tick(p_pair, float(p.get('mark_price', 0.0) or 0.0))}` | "
                    f"Unrealized PnL: `{'+' if upnl >= 0 else ''}Rs.{upnl:,.2f}` (`{float(p.get('roe_pct', 0.0) or 0.0):+.2f}% ROE`) | "
                    f"SL: `{p.get('stop_loss')}` | TP: `{p.get('take_profit')}`"
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
                f"  * Range Low (`RL`): `{_fmt_tick(selected_pair, st_data['RL'])}` | Sweep Low (`SL`): `{_fmt_tick(selected_pair, st_data['SL'])}`\n"
                f"  * `15m 50/200 EMA` Dynamic Zone: `EMA50={_fmt_tick(selected_pair, st_data.get('ema50_15m', st_data['live_price']))}` | `EMA200={_fmt_tick(selected_pair, st_data.get('ema200_15m', st_data['live_price']))}` | `RSI={st_data.get('rsi_15m', 50.0):.1f}`"
            )

        wl_rows = _scan_watchlist_opportunities(top_n=12)
        if wl_rows:
            lines.append("- **Live 12-Coin Watchlist Opportunities (Sorted by Proximity to Actionable Box Edge)**:")
            for r in wl_rows:
                lines.append(
                    f"  * `{r['sym']}`: `{_fmt_tick(r['pair'], r['price'])}` ({r['chg_24h']:+.1f}% 24h) | "
                    f"Bias: `{r['bias']}` | Setup: `{r['action_side']}` | Zone: `{r['zone_status']}` | "
                    f"RH `{_fmt_tick(r['pair'], r['RH'])}` / MID `{_fmt_tick(r['pair'], r['MID'])}` / RL `{_fmt_tick(r['pair'], r['RL'])}`"
                )
    except Exception as e:
        lines.append(f"- [Market Context Notice]: {e}")

    return "\n".join(lines)


def _detect_prompt_intents(prompt_lower: str, explicit_pair: str | None) -> set[str]:
    """Classifies user prompt into one or more concrete advisor intents so every question gets a tailored answer."""
    intents: set[str] = set()
    p = prompt_lower or ""

    if any(k in p for k in (
        "top coin", "which coin", "best coin", "performed best", "what to trade", "coins to trade",
        "gameplan", "today's session", "watchlist", "opportunities", "best performer", "compare coin",
    )):
        intents.add("top_coins")

    if any(k in p for k in (
        "audit", "journal", "sheet", "history", "drawdown", "win rate", "losing trade",
        "why did", "recent trade", "past trade", "closed trade", "checklist",
    )):
        intents.add("sheet_audit")

    if any(k in p for k in (
        "open position", "my position", "active position", "active ", "review open",
        "come down", "go up", "recover", "book profit", "ratchet", "should i hold",
        "should i close", "exit my", "breakeven", "unrealized", "my trade", "liquidation",
    )):
        intents.add("open_positions")

    if any(k in p for k in (
        "strategy", "regime", "market trend", "downtrend", "uptrend", "chop",
        "default strategy", "which strategy", "optimal single-trade margin", "margin", "leverage", "slot",
    )):
        intents.add("regime_strategy")

    if any(k in p for k in (
        "fund", "capital", "deposit", "withdraw", "growth", "roi", "wallet balance", "net invested",
    )):
        intents.add("funds")

    if any(k in p for k in (
        "best setup", "setup on", "should i enter", "buy or sell", "long or short",
        "analyze ", "box level", "entry", "tp1", "tp2", "stop loss level", "levels for",
    )):
        intents.add("coin_setup")

    if not intents:
        if explicit_pair:
            intents.add("coin_setup")
        else:
            intents.add("general")

    return intents


def _render_open_positions_section(positions: list[dict], target_pair: str, st_info: dict) -> str:
    """Formats a thorough tick-exact review for open CoinDCX positions (fixing `pnl_inr`)."""
    if not positions:
        return (
            "### 🛡️ Open Position Risk Review\n"
            "- **Current Exposure**: `0 Open Positions (Flat)` — all 3 portfolio slots are free.\n"
            "- **Risk Status**: Zero liquidation or overnight funding risk. Wait for a confirmed 15m Box Sweep or Regime-Aligned 15m 50/200 EMA Pullback."
        )

    blocks = []
    for idx_p, pos in enumerate(positions, 1):
        p_pair = str(pos.get("pair") or target_pair)
        base_s = p_pair.replace("B-", "").replace("I-", "").replace("_USDT", "").replace("_INR", "")
        norm_pair = f"B-{base_s}_USDT"
        p_struct = st_info if norm_pair == target_pair else _compute_exact_pair_structure(norm_pair)

        sym = p_struct.get("symbol", base_s)
        pos_dir = str(pos.get("direction", "LONG")).upper()
        entry_px = float(pos.get("entry_price", 0.0) or 0.0)
        mark_px = float(pos.get("mark_price", p_struct.get("live_price", 0.0)) or 0.0)
        upnl_inr = _pos_upnl_inr(pos)
        roe_pct = float(pos.get("roe_pct", 0.0) or 0.0)
        lev = int(float(pos.get("leverage", 10) or 10))
        qty = float(pos.get("quantity", 0.0) or 0.0)
        liq_px = float(pos.get("liquidation_price", 0.0) or 0.0)
        cur_sl = pos.get("stop_loss")
        cur_tp = pos.get("take_profit")

        sh = p_struct.get("SH", mark_px * 1.03)
        rh = p_struct.get("RH", mark_px * 1.01)
        mid = p_struct.get("MID", mark_px)
        rl = p_struct.get("RL", mark_px * 0.97)
        sl = p_struct.get("SL", mark_px * 0.95)
        ema20_15 = p_struct.get("ema20_15m", mark_px)
        ema50_15 = p_struct.get("ema50_15m", mark_px)
        ema200_15 = p_struct.get("ema200_15m", ema50_15)
        prev15_h = p_struct.get("prev15_high", mark_px)
        prev15_l = p_struct.get("prev15_low", mark_px)
        rsi_15 = p_struct.get("rsi_15m", 50.0)
        today_h = p_struct.get("today_high", p_struct.get("high_24h", mark_px))
        today_o = p_struct.get("today_open", rh)
        bias = p_struct.get("daily_bias", "RANGE")

        sl_str = _fmt_tick(norm_pair, float(cur_sl)) if cur_sl else "Not Set"
        tp_str = _fmt_tick(norm_pair, float(cur_tp)) if cur_tp else "Not Set"
        liq_str = _fmt_tick(norm_pair, liq_px) if liq_px > 0 else "N/A"

        header = (
            f"### 🛡️ Open Position #{idx_p}: `{norm_pair}` (`{pos_dir} {lev}x` — Tick-Exact)\n"
            f"- **Position**: Qty `{qty}` | **Entry**: **`{_fmt_tick(norm_pair, entry_px)}`** | "
            f"**Mark**: **`{_fmt_tick(norm_pair, mark_px)}`** | **Liq**: `{liq_str}`\n"
            f"- **Unrealized PnL**: **`{'+' if upnl_inr >= 0 else ''}Rs.{upnl_inr:,.2f}` (`{roe_pct:+.2f}% ROE`)** | "
            f"**Exchange SL / TP**: `{sl_str}` / `{tp_str}`\n"
            f"- **Daily Box & 15m Structure (`{sym}`)**:\n"
            f"  * `SH` **`{_fmt_tick(norm_pair, sh)}`** | `RH` **`{_fmt_tick(norm_pair, rh)}`** | `MID` **`{_fmt_tick(norm_pair, mid)}`** | `RL` `{_fmt_tick(norm_pair, rl)}` | `SL` `{_fmt_tick(norm_pair, sl)}`\n"
            f"  * `15m 20-EMA = {_fmt_tick(norm_pair, ema20_15)}` | `50-EMA = {_fmt_tick(norm_pair, ema50_15)}` | `200-EMA = {_fmt_tick(norm_pair, ema200_15)}` | `Prev 15m H/L = {_fmt_tick(norm_pair, prev15_h)} / {_fmt_tick(norm_pair, prev15_l)}` | `RSI = {rsi_15:.1f}`\n"
            f"  * **Daily `50/200 EMA` Bias**: **`{bias}`** (`EMA50 = {_fmt_tick(norm_pair, p_struct.get('ema50_d', 0.0))}`, `EMA200 = {_fmt_tick(norm_pair, p_struct.get('ema200_d', 0.0))}`)"
        )
        blocks.append(header)

        if pos_dir in ("SHORT", "SELL"):
            be_plus_fees = entry_px * 0.9985
            tp_mid_upper = (entry_px + mid) / 2.0
            invalidation_px = max(today_h, sh) * 1.002
            verdict = (
                "HOLD & TRAIL SL IN PROFIT" if upnl_inr > 0
                else ("DE-RISK 50% AT BREAKEVEN ON PULLBACK (Counter-Bias Risk)" if bias == "BULLISH" else "HOLD WITH HARD SL ABOVE SH")
            )
            blocks.append(
                f"#### 🎯 Management Plan (`{sym} SHORT` from `{_fmt_tick(norm_pair, entry_px)}` — Verdict: **{verdict}**)\n"
                f"1. **Confirmation Trigger**: 15m close below `SH` (`{_fmt_tick(norm_pair, sh)}`) and `15m 20/50 EMA` (`{_fmt_tick(norm_pair, ema20_15)}` / `{_fmt_tick(norm_pair, ema50_15)}`) confirms rejection back toward `RH` (`{_fmt_tick(norm_pair, rh)}`) and Today's Open (`{_fmt_tick(norm_pair, today_o)}`).\n"
                f"2. **De-Risk 50% (Breakeven + Fees)**: **`{_fmt_tick(norm_pair, be_plus_fees)}`** — lock SL at `{_fmt_tick(norm_pair, entry_px)}` once reached.\n"
                f"3. **Profit Targets**: `TP1` **`{_fmt_tick(norm_pair, tp_mid_upper)}`** -> **`{_fmt_tick(norm_pair, mid)}`** (`MID`) | Runner `TP2` **`{_fmt_tick(norm_pair, rl)}`** (`RL`).\n"
                f"4. **Hard Invalidation**: 15m close above **`{_fmt_tick(norm_pair, invalidation_px)}`**."
            )
        else:
            be_plus_fees = entry_px * 1.0015
            tp_mid_lower = (entry_px + mid) / 2.0
            invalidation_px = min(p_struct.get("today_low", sl), sl) * 0.998
            verdict = (
                "HOLD & TRAIL SL IN PROFIT" if upnl_inr > 0
                else ("REDUCE EXPOSURE ON BOUNCE (15m 50 < 200 EMA Resistance)" if ema50_15 < ema200_15 else "HOLD WITH HARD SL BELOW SL")
            )
            blocks.append(
                f"#### 🎯 Management Plan (`{sym} LONG` from `{_fmt_tick(norm_pair, entry_px)}` — Verdict: **{verdict}**)\n"
                f"1. **Reclaim Trigger**: 15m close back above `RL` (**`{_fmt_tick(norm_pair, rl)}`**) and `15m 20-EMA` (**`{_fmt_tick(norm_pair, ema20_15)}`**) confirms buyer absorption.\n"
                f"2. **De-Risk 50% (Breakeven + Fees)**: **`{_fmt_tick(norm_pair, be_plus_fees)}`** — ratchet SL to `{_fmt_tick(norm_pair, entry_px)}` once reclaimed.\n"
                f"3. **Profit Targets**: `TP1` **`{_fmt_tick(norm_pair, tp_mid_lower)}`** -> **`{_fmt_tick(norm_pair, mid)}`** (`MID`) | Runner `TP2` **`{_fmt_tick(norm_pair, rh)}`** (`RH`).\n"
                f"4. **Hard Invalidation**: 15m close below **`{_fmt_tick(norm_pair, invalidation_px)}`**."
            )
    return "\n\n".join(blocks)


def _generate_live_quant_advisor_response(user_prompt: str, selected_pair: str = "B-INJ_USDT") -> str:
    """
    Intent-routed live Quantitative & Google Sheet Advisor Engine.
    Answers the user's ACTUAL question (Top Coins, Sheet Audit, Open Positions, Market Regime/Strategy,
    Funds/Capital, or Specific Coin Setup) using real live CoinDCX data + `Crypto_Trades_Journal`.
    """
    import coindcx_engine as eng
    import sheets_logger
    import strategies as strat_reg

    prompt_raw = str(user_prompt or "").strip()
    prompt_lower = prompt_raw.lower()

    positions = eng.fetch_coindcx_active_positions() or []
    bal = eng.fetch_coindcx_futures_balance() or {}
    auto_cfg = eng.get_autotrade_config() or {}
    auto_mode_id = strat_reg.resolve_autotrade_mode(auto_cfg.get("autotrade_strategy_mode"))
    auto_mode_lbl = strat_reg.autotrade_mode_label(auto_mode_id)
    wallet_tot = float(bal.get("total_inr", 0.0) or 0.0)
    wallet_avail = float(bal.get("available_inr", wallet_tot) or 0.0)
    cfg_margin = float(auto_cfg.get("single_trade_margin_inr", 0.0) or 0.0)
    cfg_lev = int(auto_cfg.get("leverage", 10) or 10)
    opt_slot_margin = round(wallet_tot / 3.0, 2) if wallet_tot > 0 else cfg_margin
    daily_loss_cap = round(wallet_tot * 0.05, 2) if wallet_tot > 0 else 0.0

    # Detect whether user explicitly mentioned a coin in their prompt
    explicit_pair = None
    for cand_p in eng.GLOBAL_FUTURES_PAIRS:
        sym_c = cand_p.replace("B-", "").replace("_USDT", "").lower()
        if re.search(rf"\b{re.escape(sym_c)}\b", prompt_lower):
            explicit_pair = cand_p
            break
    target_pair = explicit_pair or selected_pair

    intents = _detect_prompt_intents(prompt_lower, explicit_pair)
    sections: list[str] = []

    # Load Sheet performance lazily only when needed
    sheet_perf = None
    if intents & {"top_coins", "sheet_audit", "general"}:
        sheet_perf = _summarize_sheet_performance(sheets_logger.fetch_all_sheet_trades())

    # ------------------------------------------------------------------
    # INTENT A: TOP COINS TO TRADE TODAY / BEST PERFORMERS / GAMEPLAN
    # ------------------------------------------------------------------
    if "top_coins" in intents:
        reg_info = eng.compute_market_regime()
        wl_rows = _scan_watchlist_opportunities(top_n=12)

        perf_lines = []
        if sheet_perf and sheet_perf["by_coin"]:
            winners = [c for c in sheet_perf["by_coin"] if c["pnl"] > 0]
            losers = [c for c in sheet_perf["by_coin"] if c["pnl"] < 0]
            if winners:
                top_w = ", ".join(f"`{c['sym']}` (`+Rs.{c['pnl']:,.0f}`, `{c['wins']}W/{c['losses']}L`)" for c in winners[:4])
                perf_lines.append(f"- **Top Performing Coins (Sheet Closed Trades)**: {top_w}")
            if losers:
                top_l = ", ".join(f"`{c['sym']}` (`Rs.{c['pnl']:,.0f}`, `{c['wins']}W/{c['losses']}L`)" for c in reversed(losers[-4:]))
                perf_lines.append(f"- **Drawdown Culprits (Sheet Closed Trades)**: {top_l}")
            d_l = sheet_perf["by_dir"]["LONG"]
            d_s = sheet_perf["by_dir"]["SHORT"]
            perf_lines.append(
                f"- **Direction Split (`{sheet_perf['total_closed']}` Closed)**: "
                f"`LONG`: `{d_l['wins']}W/{d_l['losses']}L` (`{'+' if d_l['pnl'] >= 0 else ''}Rs.{d_l['pnl']:,.0f}`) | "
                f"`SHORT`: `{d_s['wins']}W/{d_s['losses']}L` (`{'+' if d_s['pnl'] >= 0 else ''}Rs.{d_s['pnl']:,.0f}`)"
            )
        else:
            perf_lines.append("- **Sheet Closed Trades**: No closed trades logged yet.")

        opp_lines = []
        for idx_o, r in enumerate(wl_rows[:5], 1):
            opp_lines.append(
                f"  {idx_o}. **`{r['sym']}/USDT`** (`{_fmt_tick(r['pair'], r['price'])}`, `{r['chg_24h']:+.1f}%` 24h) — "
                f"Daily Bias: **`{r['bias']}`** | Target: **`{r['action_side']}`** @ `{_fmt_tick(r['pair'], r['target_edge'])}` "
                f"(`{r['zone_status']}`) | `MID`: `{_fmt_tick(r['pair'], r['MID'])}`"
            )

        now_ist_h = datetime.now(IST).hour
        next_sess = (
            "🏛️ London Open (`13:00–14:30 IST`)" if now_ist_h < 14
            else ("⚡ New York Open (`18:45–20:15 IST`)" if now_ist_h < 20 else "🌅 Asia Open (`07:00–08:30 IST`)")
        )
        sections.append(
            f"### 🏆 Top Coins to Trade Today & Session Gameplan\n"
            f"- **Live Market Regime**: {reg_info.get('summary', 'RANGING / CHOP')}\n"
            f"- **Active Sidebar Mode**: `{auto_mode_lbl}`\n"
            + "\n".join(perf_lines)
            + "\n- **Top 5 Live Watchlist Setups (Closest to Confirmed Box Edge Right Now)**:\n"
            + ("\n".join(opp_lines) if opp_lines else "  * Watchlist data temporarily unavailable.")
            + f"\n- **Optimal Margin & Session Plan**:\n"
            f"  * **Wallet**: `Rs.{wallet_tot:,.2f}` (Free: `Rs.{wallet_avail:,.2f}`) | **1/3 Optimal Slot Margin**: **`Rs.{opt_slot_margin:,.2f}`** (Sidebar currently `Rs.{cfg_margin:,.2f}` @ `{cfg_lev}x`) | **5% Daily Loss Stop**: `-Rs.{daily_loss_cap:,.2f}`.\n"
            f"  * **Next Prime Liquidity Window**: {next_sess} — focus strictly on Maker Limit sweeps at `RH–SH` (`BEARISH`/`RANGE`) or `RL–SL` (`BULLISH`/`RANGE`), booking `50%` at `TP1` and trailing the `50%` runner."
        )

    # ------------------------------------------------------------------
    # INTENT B: GOOGLE SHEET TRADE AUDIT / HISTORY / WHY DID COIN LOSE
    # ------------------------------------------------------------------
    if "sheet_audit" in intents and "top_coins" not in intents:
        sp = sheet_perf or _summarize_sheet_performance(sheets_logger.fetch_all_sheet_trades())
        coin_rows_txt = "\n".join(
            f"  * **`{c['sym']}`**: `{c['trades']}` closed (`{c['wins']}W / {c['losses']}L` — `{c['wr']}%` WR) | Net PnL: **`{'+' if c['pnl'] >= 0 else ''}Rs.{c['pnl']:,.2f}`**"
            for c in sp["by_coin"]
        ) or "  * No closed trade rows found yet."

        d_l = sp["by_dir"]["LONG"]
        d_s = sp["by_dir"]["SHORT"]
        extra_coin_note = ""
        if explicit_pair:
            ex_sym = explicit_pair.replace("B-", "").replace("_USDT", "")
            matched_live = [r for r in sp["live_trades"] if ex_sym in str(r.get("Pair", "")).upper()][-6:]
            matched_cls = [r for r in sp["closed_trades"] if ex_sym in str(r.get("Pair", "")).upper()][-5:]
            lines_ex = [f"\n- **Recent `{ex_sym}` Trades in `Crypto_Trades_Journal`**:"]
            for lr in reversed(matched_live):
                lines_ex.append(
                    f"  * `[LIVE]` `{lr.get('Timestamp (IST)', '')}` **{lr.get('Direction', '')}** @ `${lr.get('Entry ($)', '')}` "
                    f"(SL `${lr.get('Stop Loss ($)', '')}`, TP1 `${lr.get('TP1 Mid ($)', '')}`) — {lr.get('Strategy', '')} | `{lr.get('Status', '')}`"
                )
            for cr in reversed(matched_cls):
                lines_ex.append(
                    f"  * `[CLOSED]` `{cr.get('Exit Time', '')}` **{cr.get('Direction', '')}** Entry `${cr.get('Entry', '')}` -> Exit `${cr.get('Exit', '')}` | "
                    f"PnL: `Rs.{cr.get('Net PnL (INR)', cr.get('Realized PnL (INR)', '0'))}` — {cr.get('Exit Reason', '')}"
                )
            extra_coin_note = "\n".join(lines_ex)

        sections.append(
            f"### 📊 `Crypto_Trades_Journal` Google Sheet Trade Audit\n"
            f"- **Journal Totals**: `{sp['total_logged']}` Logged Orders (`Live_Trades`) | **`{sp['total_closed']}` Closed Trades** (`{sp['wins']}W / {sp['losses']}L` — **`{sp['win_rate']}%` WR**) | "
            f"**Realized Net PnL**: **`{'+' if sp['net_pnl'] >= 0 else ''}Rs.{sp['net_pnl']:,.2f}`**\n"
            f"- **Direction Performance**: `LONG` `{d_l['wins']}W/{d_l['losses']}L` (`{'+' if d_l['pnl'] >= 0 else ''}Rs.{d_l['pnl']:,.2f}`) | "
            f"`SHORT` `{d_s['wins']}W/{d_s['losses']}L` (`{'+' if d_s['pnl'] >= 0 else ''}Rs.{d_s['pnl']:,.2f}`)\n"
            f"- **Per-Coin Closed Breakdown**:\n{coin_rows_txt}"
            f"{extra_coin_note}\n"
            f"- **A+ Execution Checklist (From Journal Lessons)**:\n"
            f"  1. Never counter-trade a coin's Daily `50/200 EMA` trend bias (always wait for closed 15m rejection inside `RH`/`RL`).\n"
            f"  2. Enforce `50%` early book at `TP1` + Profit-Lock SL so green trades never flip into full SLs.\n"
            f"  3. Respect the 3-slot cap (`>=90%` free margin guard) and `5%` Daily Wallet Loss Stop (`-Rs.{daily_loss_cap:,.2f}`)."
        )

    # ------------------------------------------------------------------
    # INTENT C: OPEN POSITION RISK / ACTIVE TRADE MANAGEMENT
    # ------------------------------------------------------------------
    if "open_positions" in intents:
        st_info_pos = _compute_exact_pair_structure(target_pair)
        sections.append(_render_open_positions_section(positions, target_pair, st_info_pos))

    # ------------------------------------------------------------------
    # INTENT D: MARKET REGIME / STRATEGY SELECTION / MARGIN SIZING
    # ------------------------------------------------------------------
    if "regime_strategy" in intents and "top_coins" not in intents:
        reg_info = eng.compute_market_regime()
        reg_code = str(reg_info.get("regime", "RANGING_CHOP"))
        rec_strat = (
            "**`Combo: Regime-Adaptive [Box + Auto Trend EMA]`** (auto-enables Bull EMA in Uptrend, Bear EMA in Downtrend, and Box-Only in Chop)"
        )
        action_note = (
            "Market is in **`STRONG DOWNTREND`** — both Box Sweep Shorts & Bear 15m 50/200 EMA Pullback Shorts are active."
            if reg_code == "STRONG_DOWNTREND"
            else (
                "Market is in **`STRONG UPTREND`** — both Box Sweep Longs & Bull 15m 50/200 EMA Pullback Longs are active."
                if reg_code == "STRONG_UPTREND"
                else "Market is in **`RANGING / CHOP`** — Regime-Adaptive automatically pauses 15m 50/200 EMA trend trades and trades **Box Theory Sweep** edges cleanly."
            )
        )
        sections.append(
            f"### 🧭 Live Market Regime, Recommended Strategy & Sizing\n"
            f"- **Detected Market Regime**: {reg_info.get('summary', '')}\n"
            f"- **Recommended Default Strategy**: {rec_strat}\n"
            f"- **Current Active Mode in Sidebar**: `{auto_mode_lbl}`\n"
            f"- **Why**: {action_note}\n"
            f"- **Wallet & Margin Sizing**: Total Wallet `Rs.{wallet_tot:,.2f}` | Available `Rs.{wallet_avail:,.2f}` | "
            f"Max 3 Concurrent Slots (`Rs.{opt_slot_margin:,.2f}` per slot at 1/3 wallet; Sidebar currently set to `Rs.{cfg_margin:,.2f}` @ `{cfg_lev}x`) | "
            f"`5%` Daily Loss Stop: `-Rs.{daily_loss_cap:,.2f}`."
        )

    # ------------------------------------------------------------------
    # INTENT E: FUNDS / CAPITAL / WALLET GROWTH
    # ------------------------------------------------------------------
    if "funds" in intents:
        total_upnl = sum(_pos_upnl_inr(p) for p in positions)
        live_eq = wallet_tot + total_upnl
        f_cache = eng._FUTURES_FUNDS_CACHE if isinstance(getattr(eng, "_FUTURES_FUNDS_CACHE", None), dict) else {}
        if f_cache.get("ok") and f_cache.get("transactions"):
            fs = eng.compute_futures_funds_summary(
                transactions=f_cache["transactions"],
                wallet=bal,
                positions=positions,
                spot_balances=f_cache.get("spot_balances") or [],
            )
            g_str = f"{fs['growth_pct_net_capital']:+.2f}%" if fs["growth_pct_net_capital"] is not None else "House Money"
            sections.append(
                f"### 💰 CoinDCX Futures Funds & Growth Summary\n"
                f"- **Total Added to Futures**: `Rs.{fs['total_added_all_inr']:,.2f}` ({fs['deposit_count']} deposits) | "
                f"**Total Withdrawn**: `Rs.{fs['total_withdrawn_all_inr']:,.2f}` ({fs['withdrawal_count']} withdrawals)\n"
                f"- **Net Capital Invested**: **`Rs.{fs['net_capital_inr']:,.2f}`** (Peak Deployed: `Rs.{fs['peak_net_capital_inr']:,.2f}`)\n"
                f"- **Current Futures Equity**: **`Rs.{fs['current_equity_inr']:,.2f}`** (Realized `Rs.{fs['current_realized_wallet_inr']:,.2f}` + Open `{'+' if total_upnl >= 0 else ''}Rs.{total_upnl:,.2f}`)\n"
                f"- **Net Profit / Growth**: **`{'+' if fs['total_growth_inr'] >= 0 else ''}Rs.{fs['total_growth_inr']:,.2f}`** (**`{g_str}`** vs Net Capital)\n"
                f"- Open the **`💰 Funds`** tab for the full equity growth chart, monthly table, and CSV downloads."
            )
        else:
            sections.append(
                f"### 💰 Live Futures Wallet Snapshot\n"
                f"- **Current Realized Futures Wallet**: **`Rs.{wallet_tot:,.2f}`** (Available: `Rs.{wallet_avail:,.2f}`, Locked: `Rs.{max(0.0, wallet_tot - wallet_avail):,.2f}`)\n"
                f"- **Open Unrealized PnL**: `{'+' if total_upnl >= 0 else ''}Rs.{total_upnl:,.2f}` | **Live Equity**: **`Rs.{live_eq:,.2f}`**\n"
                f"- Open the **`💰 Funds`** tab (and click **🔄 Refresh CoinDCX Ledger**) to load your complete Day-1 Deposits, Withdrawals, Net Invested Capital, and `% Growth`."
            )

    # ------------------------------------------------------------------
    # INTENT F: SPECIFIC COIN SETUP ANALYSIS
    # ------------------------------------------------------------------
    if "coin_setup" in intents:
        st_info = _compute_exact_pair_structure(target_pair)
        sym = st_info.get("symbol", target_pair.replace("B-", "").replace("_USDT", ""))
        px = st_info.get("live_price", 0.0)
        sh = st_info.get("SH", px * 1.03)
        rh = st_info.get("RH", px * 1.01)
        mid = st_info.get("MID", px)
        rl = st_info.get("RL", px * 0.97)
        sl = st_info.get("SL", px * 0.95)
        ema20_15 = st_info.get("ema20_15m", px)
        ema50_15 = st_info.get("ema50_15m", px)
        ema200_15 = st_info.get("ema200_15m", ema50_15)
        rsi_15 = st_info.get("rsi_15m", 50.0)
        bias = st_info.get("daily_bias", "RANGE")

        ema_regime_15m = "50 < 200 EMA (Bearish Pullback Resistance)" if ema50_15 < ema200_15 else "50 > 200 EMA (Bullish Pullback Support)"
        ema_bear_sl = max(ema200_15, ema50_15) * 1.0025
        ema_bull_sl = min(ema200_15, ema50_15) * 0.9975

        # Live signal verdict check
        live_verdict = "WAIT / NO TRADE (Watch Box Edges & 15m Confirmation)"
        try:
            b_sig = strat_reg.get_strategy("box_theory").evaluate_signal(target_pair, st_info.get("raw_box"), cfg_margin or 30000.0, cfg_lev, eng.get_coindcx_live_usdt_inr_rate())
            if b_sig and b_sig.get("signal") in ("LONG", "SHORT"):
                live_verdict = f"ACTIVE BOX SWEEP {b_sig['signal']} @ {_fmt_tick(target_pair, b_sig['entry'])} (TP1 {_fmt_tick(target_pair, b_sig['tp1'])}, SL {_fmt_tick(target_pair, b_sig['stop_loss'])})"
        except Exception:
            pass

        sections.append(
            f"### 🎯 Live Setup Analysis for `{target_pair}` (`{_fmt_tick(target_pair, px)}` | 24h `{st_info.get('change_24h', 0.0):+.2f}%`)\n"
            f"- **Live Signal Verdict**: **`{live_verdict}`**\n"
            f"- **Active AutoTrade Mode**: `{auto_mode_lbl}`\n"
            f"- **Daily `50/200 EMA` Bias**: **`{bias}`** (`EMA50 = {_fmt_tick(target_pair, st_info.get('ema50_d', 0.0))}`, `EMA200 = {_fmt_tick(target_pair, st_info.get('ema200_d', 0.0))}`)\n"
            f"- **Exact Daily Box Levels (Synced with Chart)**:\n"
            f"  * `SH`: **`{_fmt_tick(target_pair, sh)}`** | `RH`: **`{_fmt_tick(target_pair, rh)}`**\n"
            f"  * `MID (TP1)`: **`{_fmt_tick(target_pair, mid)}`**\n"
            f"  * `RL`: **`{_fmt_tick(target_pair, rl)}`** | `SL`: **`{_fmt_tick(target_pair, sl)}`**\n"
            f"- **15m Dynamic Structure**: `20-EMA = {_fmt_tick(target_pair, ema20_15)}` | `50-EMA = {_fmt_tick(target_pair, ema50_15)}` | `200-EMA = {_fmt_tick(target_pair, ema200_15)}` (`{ema_regime_15m}`) | `RSI(14) = {rsi_15:.1f}`\n"
            f"- **Execution Plan (`{sym}`)**:\n"
            + (
                f"  * **Priority 1 (`Box Sweep LONG`)**: Wait for a confirmed 15m sweep/reclaim in `RL–SL` (`{_fmt_tick(target_pair, rl)}` – `{_fmt_tick(target_pair, sl)}`), SL `0.5%` below `SL` (`{_fmt_tick(target_pair, sl * 0.995)}`), `TP1 = {_fmt_tick(target_pair, mid)}`, `TP2 = {_fmt_tick(target_pair, rh)}`.\n"
                f"  * **Priority 2 (`15m 50/200 EMA Pullback LONG`)**: Bullish bounce at `15m 50 EMA` (`{_fmt_tick(target_pair, ema50_15)}`), `SL < 15m 200 EMA` (`{_fmt_tick(target_pair, ema_bull_sl)}`), `TP2 = {_fmt_tick(target_pair, rh)}` (active in `STRONG_UPTREND`)."
                if bias == "BULLISH"
                else (
                    f"  * **Priority 1 (`Box Sweep SHORT`)**: Wait for a confirmed 15m sweep/rejection in `RH–SH` (`{_fmt_tick(target_pair, rh)}` – `{_fmt_tick(target_pair, sh)}`), SL `0.5%` above `SH` (`{_fmt_tick(target_pair, sh * 1.005)}`), `TP1 = {_fmt_tick(target_pair, mid)}`, `TP2 = {_fmt_tick(target_pair, rl)}`.\n"
                    f"  * **Priority 2 (`15m 50/200 EMA Pullback SHORT`)**: Pullback into `15m 50 EMA` (`{_fmt_tick(target_pair, ema50_15)}`) below `200 EMA` (`{_fmt_tick(target_pair, ema200_15)}`), `SL` above `15m 200 EMA` (`{_fmt_tick(target_pair, ema_bear_sl)}`), `TP2 = {_fmt_tick(target_pair, rl)}` (active in `STRONG_DOWNTREND`)."
                    if bias == "BEARISH"
                    else (
                        f"  * Bias is **`RANGE`** — Priority 1 Box Sweep is active at **both** outer edges: `SHORT` on 15m rejection at `RH–SH` (`{_fmt_tick(target_pair, rh)}` – `{_fmt_tick(target_pair, sh)}`) or `LONG` on 15m reclaim at `RL–SL` (`{_fmt_tick(target_pair, rl)}` – `{_fmt_tick(target_pair, sl)}`), targeting `MID = {_fmt_tick(target_pair, mid)}` (`15m 50/200 EMA` stands aside in `RANGE`)."
                    )
                )
            )
        )

    # ------------------------------------------------------------------
    # INTENT G: GENERAL / OPEN-ENDED CUSTOM PROMPT
    # ------------------------------------------------------------------
    if "general" in intents or not sections:
        reg_info = eng.compute_market_regime()
        sp = sheet_perf or _summarize_sheet_performance(sheets_logger.fetch_all_sheet_trades())
        total_upnl = sum(_pos_upnl_inr(p) for p in positions)
        pos_summary = (
            ", ".join(f"`{p.get('pair')}` {p.get('direction')} ({float(p.get('roe_pct', 0.0)):+.1f}%)" for p in positions)
            if positions else "Flat (0/3 slots)"
        )
        sections.append(
            f"### 🤖 Live Quant & Journal Summary (for: *\"{prompt_raw[:120]}\"*)\n"
            f"- **Market Regime**: {reg_info.get('summary', '')}\n"
            f"- **Wallet & Open Positions**: `Rs.{wallet_tot:,.2f}` (Open PnL: `{'+' if total_upnl >= 0 else ''}Rs.{total_upnl:,.2f}`) | Active: {pos_summary}\n"
            f"- **Google Sheet Journal**: `{sp['total_logged']}` logged, `{sp['total_closed']}` closed (`{sp['wins']}W/{sp['losses']}L` — `{sp['win_rate']}%` WR, Net `{'+' if sp['net_pnl'] >= 0 else ''}Rs.{sp['net_pnl']:,.2f}`)\n"
            f"- **Tip for Specific Questions**: Ask about **`top coins`**, **`audit sheet`**, **`open positions`**, **`market strategy/regime`**, **`funds/wallet`**, or any specific coin setup (e.g., *\"Best setup on BTC now\"* or *\"Why did NEAR lose?\"*).\n"
            f"- **Want Full Free-Form Conversational Gemini 4 Argon / 3.8 Flash?** Add `GEMINI_API_KEY = \"AIza...\"` (from Google AI Studio) to your Streamlit Cloud Secrets — the advisor will automatically switch from this built-in Quant Engine to the live Gemini LLM."
        )

    return "\n\n".join(sections)


def _get_gcp_service_account_client():
    """Creates a Google Cloud OAuth2 credential from `[gcp_service_account]` in Streamlit secrets if available."""
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


def _extract_interaction_text(interaction) -> str:
    txt = getattr(interaction, "output_text", None) or ""
    if txt:
        return str(txt).strip()
    if getattr(interaction, "outputs", None):
        parts = []
        for out in interaction.outputs:
            t = getattr(out, "text", None)
            if t:
                parts.append(str(t))
        if parts:
            return "\n".join(parts).strip()
    return ""


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
    to Gemini via the official `google-genai` SDK (`GEMINI_API_KEY` or Vertex AI Service Account if IAM-enabled),
    falling back cleanly to the Intent-Routed Live Quantitative & Sheet Advisor Engine with transparent diagnostics.
    """
    key = str(api_key or get_gemini_api_key() or "").strip()
    full_input = (
        f"{sheet_markdown_context}\n\n"
        f"{market_context}\n\n"
        f"---\n"
        f"### User Question / Prompt:\n{user_prompt}"
    )
    models_to_try = [preferred_model] + [m for m in FALLBACK_MODEL_CHAIN if m != preferred_model]
    last_llm_err = ""

    # 1. Primary: Official Gemini Developer API using GEMINI_API_KEY (`AIza...`)
    if key:
        client = genai.Client(api_key=key)
        for candidate_model in models_to_try:
            try:
                if hasattr(client, "interactions"):
                    kwargs = {
                        "model": candidate_model,
                        "input": full_input,
                        "system_instruction": SYSTEM_INSTRUCTION,
                    }
                    if previous_interaction_id and candidate_model == preferred_model:
                        kwargs["previous_interaction_id"] = previous_interaction_id
                    interaction = client.interactions.create(**kwargs)
                    reply_text = _extract_interaction_text(interaction)
                    interaction_id = getattr(interaction, "id", None)
                    if reply_text:
                        return {
                            "ok": True,
                            "error": None,
                            "text": reply_text,
                            "model_used": candidate_model,
                            "interaction_id": interaction_id,
                            "llm_used": True,
                            "fallback_reason": "",
                        }
            except Exception as e:
                last_llm_err = str(e)[:220]
                if "api_key_invalid" in last_llm_err.lower() or "api key not valid" in last_llm_err.lower():
                    break

            try:
                gen_resp = client.models.generate_content(
                    model=candidate_model,
                    contents=full_input,
                    config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
                )
                reply_text = (getattr(gen_resp, "text", "") or "").strip()
                if reply_text:
                    return {
                        "ok": True,
                        "error": None,
                        "text": reply_text,
                        "model_used": candidate_model,
                        "interaction_id": None,
                        "llm_used": True,
                        "fallback_reason": "",
                    }
            except Exception as e2:
                last_llm_err = str(e2)[:220]
                if "api_key_invalid" in last_llm_err.lower() or "api key not valid" in last_llm_err.lower():
                    break
                continue
    else:
        # 2. Secondary: Try Vertex AI via [gcp_service_account] ONCE if IAM Vertex AI User role is granted
        if not _VERTEX_SA_STATE["checked"] or _VERTEX_SA_STATE["usable"]:
            sa_creds, sa_project = _get_gcp_service_account_client()
            if sa_creds and sa_project:
                try:
                    v_client = genai.Client(
                        vertexai=True,
                        credentials=sa_creds,
                        project=sa_project,
                        location="global",
                    )
                    for candidate_model in models_to_try:
                        try:
                            gen_resp = v_client.models.generate_content(
                                model=candidate_model,
                                contents=full_input,
                                config=genai_types.GenerateContentConfig(system_instruction=SYSTEM_INSTRUCTION),
                            )
                            reply_text = (getattr(gen_resp, "text", "") or "").strip()
                            if reply_text:
                                _VERTEX_SA_STATE.update({"checked": True, "usable": True, "reason": ""})
                                return {
                                    "ok": True,
                                    "error": None,
                                    "text": reply_text,
                                    "model_used": f"{candidate_model} (Vertex AI)",
                                    "interaction_id": None,
                                    "llm_used": True,
                                    "fallback_reason": "",
                                }
                        except Exception as ve:
                            ve_s = str(ve)
                            last_llm_err = ve_s[:220]
                            if "403" in ve_s or "PERMISSION_DENIED" in ve_s or "aiplatform" in ve_s.lower():
                                _VERTEX_SA_STATE.update({"checked": True, "usable": False, "reason": "Service account lacks Vertex AI IAM role (add GEMINI_API_KEY in Streamlit Secrets for live Gemini LLM)"})
                                break
                except Exception as ve_outer:
                    _VERTEX_SA_STATE.update({"checked": True, "usable": False, "reason": str(ve_outer)[:180]})
            else:
                _VERTEX_SA_STATE.update({"checked": True, "usable": False, "reason": "No GEMINI_API_KEY configured in Streamlit Secrets"})

    fallback_reason = (
        last_llm_err if key
        else (_VERTEX_SA_STATE.get("reason") or "No GEMINI_API_KEY configured in Streamlit Secrets")
    )

    # 3. Intent-Routed Built-In Live Quantitative & Sheet Grounded Advisor
    try:
        quant_text = _generate_live_quant_advisor_response(user_prompt=user_prompt, selected_pair=selected_pair)
        return {
            "ok": True,
            "error": None,
            "text": quant_text,
            "model_used": "Live Quant + Sheet Engine",
            "interaction_id": None,
            "llm_used": False,
            "fallback_reason": fallback_reason,
        }
    except Exception as e:
        return {
            "ok": False,
            "error": f"Advisor Engine Error: {e}",
            "text": "",
            "model_used": None,
            "interaction_id": None,
            "llm_used": False,
            "fallback_reason": fallback_reason,
            "traceback": traceback.format_exc(),
        }
