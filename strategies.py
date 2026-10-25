"""
Pluggable strategy registry for the Crypto Trade Assistant.

Every strategy implements the same small interface, so the signal monitor, e-mail alerts, the
Key Levels / Trade Execution / Backtest tabs and the backtester can loop over STRATEGY_REGISTRY
without knowing anything strategy-specific.

To add a strategy: subclass `Strategy`, implement the methods below, and add one line to
STRATEGY_REGISTRY at the bottom of this file. No UI changes are needed: the tabs fall back to the
generic renderers (`chart_lines`, `chart_markers`, `metric_badges`, `level_rows`, `plan_setups`).

Interface
  compute_levels(pair)                                   -> dict | None   (live reference levels)
  evaluate_signal(pair, levels, margin, lev, usd_inr)    -> dict | None   (last CLOSED 15m candle)
  plan_setups(pair, levels, live_price, margin, lev, usd_inr)
                                                         -> {"BUY": setup|None, "SELL": setup|None, "note": str}
  chart_lines(levels, plan)  / chart_markers(df, levels, tf) / metric_badges(levels) / level_rows(levels, live)
  prepare_backtest(df_15m, df_daily) -> ctx ; backtest_has_context(candle, ctx) -> bool
  backtest_entry(idx, candle, ctx, records) -> {direction, entry, stop, tp1, tp2, tp1_label, tp2_label, reason} | None
"""
from __future__ import annotations

import time
from datetime import datetime

import pandas as pd

import coindcx_engine as eng

IST = eng.IST


# ----------------------------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------------------------
def position_metrics(pair: str, entry: float, stop: float, tp1: float, tp2: float,
                     margin_inr: float, leverage: int, usd_inr: float) -> dict:
    """Quantity, ROE and INR projections for a setup (same formulas as calculate_trade_setup_details)."""
    margin_usd = margin_inr / usd_inr if usd_inr else 0.0
    position_usd = margin_usd * leverage
    qty = eng.format_order_quantity(pair, position_usd / entry) if entry > 0 else 0
    risk, r1, r2 = abs(entry - stop) if stop > 0 else 0, abs(entry - tp1), abs(entry - tp2)

    def roe(x):
        return round((x / entry) * leverage * 100, 2) if entry > 0 else 0

    return {
        "crypto_qty": qty, "position_usd": round(position_usd, 2), "margin_inr": margin_inr,
        "leverage": leverage, "usd_inr": usd_inr,
        "roe_tp1": roe(r1), "roe_tp2": roe(r2), "roe_sl": roe(risk),
        "profit_tp1_inr": round(r1 * qty * usd_inr, 2), "profit_tp2_inr": round(r2 * qty * usd_inr, 2),
        "loss_sl_inr": round(risk * qty * usd_inr, 2), "target_roe_met": roe(r1) >= 5.0,
    }


def backtest_session_name(c_time) -> str:
    """Session bucket used in backtest reports (unchanged from the original backtester)."""
    h, m = c_time.hour, c_time.minute
    if (h == 7) or (h == 8 and m <= 30):
        return "🌅 Asia Open"
    if (h == 13) or (h == 14 and m <= 30):
        return "🏛️ London Open"
    if (h == 18 and m >= 45) or (h == 19) or (h == 20 and m <= 15):
        return "⚡ New York Open"
    return "🌐 Intraday Monitor"


def _closed_15m(pair: str, limit: int) -> pd.DataFrame:
    df = eng.fetch_coindcx_candles(pair=pair, interval="15m", limit=limit, sync_live_price=False)
    if df.empty:
        return df
    now_ms = int(time.time() * 1000)
    closed = df[df["timestamp"] + 900000 <= now_ms].reset_index(drop=True)
    return closed if not closed.empty else df.iloc[:-1].reset_index(drop=True)


class Strategy:
    id = "base"
    name = "Base Strategy"
    short = "Base"
    timeframe = "15m"
    description = ""
    daily_warmup_days = 40   # extra daily candles the backtester fetches before the test window
    tp1_name, tp2_name = "TP1", "TP2"
    uses_live_price = False  # True if plan_setups() depends on the live price (affects UI caching)
    chart_marker_hint = ""

    # ---- live ----
    def compute_levels(self, pair):
        raise NotImplementedError

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
        raise NotImplementedError

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr) -> dict:
        return {"BUY": None, "SELL": None, "note": ""}

    # ---- generic UI hooks ----
    def chart_lines(self, levels, plan=None) -> list:
        return []

    def chart_markers(self, df, levels, tf) -> list:
        return []

    def metric_badges(self, levels) -> list:
        return []

    def level_rows(self, levels, live_price) -> list:
        return []

    # ---- backtest ----
    def prepare_backtest(self, df, df_daily):
        raise NotImplementedError

    def backtest_has_context(self, candle, ctx) -> bool:
        return True

    def backtest_entry(self, idx, candle, ctx, records):
        raise NotImplementedError

    def _stamp(self, d: dict | None) -> dict | None:
        if d is not None:
            d["strategy_id"], d["strategy_name"] = self.id, self.name
        return d


# ----------------------------------------------------------------------------------------------
# Strategy 1: Box Theory Sweep (proven baseline - math untouched, only wrapped)
# ----------------------------------------------------------------------------------------------
class BoxTheorySweep(Strategy):
    id = "box_theory"
    name = "Box Theory Sweep"
    short = "Box"
    description = ("24/7 sweep-and-reject of the previous day's range. SHORT when high >= RH and close < RH "
                   "(SL max(high, SH) x 1.002, TP1 MID, TP2 RL); LONG when low <= RL and close > RL "
                   "(SL min(low, SL) x 0.998, TP1 MID, TP2 RH). 50/50 ratchet trailing SL.")
    daily_warmup_days = 40
    tp1_name, tp2_name = "MID", "Extreme"
    uses_live_price = True

    def compute_levels(self, pair):
        return eng.calculate_daily_box_levels(pair)

    @staticmethod
    def _reason(sig: dict) -> str:
        kind, d = sig.get("signal_kind"), sig.get("signal")
        if kind == "REVERSAL":
            return ("Swept RH Sell Zone (high >= RH, closed back below RH)" if d == "SHORT"
                    else "Swept RL Buy Zone (low <= RL, closed back above RL)")
        if kind == "CONTINUATION":
            return ("Solid tower closed above RH (continuation idea, untested)" if d == "LONG"
                    else "Solid tower closed below RL (continuation idea, untested)")
        return ""

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
        sig = eng.evaluate_tri_session_signal(pair, levels, margin_inr, leverage, usd_inr, trigger_alert=False)
        if sig:
            sig["trigger_reason"] = self._reason(sig)
        return self._stamp(sig)

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr):
        if not levels:
            return {"BUY": None, "SELL": None, "note": "Box levels unavailable."}
        b = eng.calculate_trade_setup_details("BUY", levels, live_price, margin_inr, leverage, usd_inr, pair=pair)
        s = eng.calculate_trade_setup_details("SELL", levels, live_price, margin_inr, leverage, usd_inr, pair=pair)
        if b:
            b["trigger_reason"] = "Planned: sweep of RL Buy Zone + close back above RL"
        if s:
            s["trigger_reason"] = "Planned: sweep of RH Sell Zone + close back below RH"
        return {"BUY": self._stamp(b), "SELL": self._stamp(s), "note": ""}

    def chart_lines(self, levels, plan=None):
        if not levels:
            return []
        return [
            {"label": "SH (Swing High)", "price": levels["SH"], "color": "#ef4444", "dash": "dash"},
            {"label": "RH / PDH", "price": levels["RH"], "color": "#ea580c", "dash": "solid"},
            {"label": "MID (50%)", "price": levels["MID"], "color": "#0284c7", "dash": "dot"},
            {"label": "RL / PDL", "price": levels["RL"], "color": "#16a34a", "dash": "solid"},
            {"label": "SL (Swing Low)", "price": levels["SL"], "color": "#10b981", "dash": "dash"},
        ]

    # ---- backtest: identical to the original run_strategy_backtest internals ----
    def prepare_backtest(self, df, df_daily):
        daily_boxes = {}
        daily_records = df_daily.to_dict('records')
        for i in range(1, len(daily_records)):
            curr_day_str = daily_records[i]['date_str']
            prev_day = daily_records[i - 1]
            rh = float(prev_day['high'])
            rl = float(prev_day['low'])
            mid = (rh + rl) / 2.0

            lookback_start = max(0, i - 15)
            prior_slice = daily_records[lookback_start:i - 1]
            prior_highs = [float(d['high']) for d in prior_slice] if prior_slice else []
            prior_lows = [float(d['low']) for d in prior_slice] if prior_slice else []

            sh_c = [h for h in prior_highs if h > rh]
            sh = min(sh_c) if sh_c else rh * 1.015
            sl_c = [l for l in prior_lows if l < rl]
            sl = max(sl_c) if sl_c else rl * 0.985

            daily_boxes[curr_day_str] = {"RH": rh, "RL": rl, "MID": mid, "SH": sh, "SL": sl}
        return {"boxes": daily_boxes}

    def backtest_has_context(self, candle, ctx):
        return bool(ctx["boxes"].get(candle['date_str']))

    def backtest_entry(self, idx, candle, ctx, records):
        box = ctx["boxes"][candle['date_str']]
        rh, rl, mid = box["RH"], box["RL"], box["MID"]
        sh, sl = box["SH"], box["SL"]
        c_high = float(candle['high'])
        c_low = float(candle['low'])
        c_close = float(candle['close'])
        c_open = float(candle.get('open', c_close))
        candle_range = c_high - c_low

        # Buy Zone Rejection: swept down into Buy Zone (<= RL), closed back above RL
        lower_wick = min(c_open, c_close) - c_low
        is_bullish_rejection = (
            (c_low <= rl) and (c_close > rl) and (c_low >= sl * 0.995) and (
                (candle_range > 0 and (lower_wick / candle_range) >= 0.15) or
                (c_close >= c_open) or
                (candle_range > 0 and (c_close - c_low) / candle_range >= 0.45)
            )
        )
        # Sell Zone Rejection: swept up into Sell Zone (>= RH), closed back below RH
        upper_wick = c_high - max(c_open, c_close)
        is_bearish_rejection = (
            (c_high >= rh) and (c_close < rh) and (c_high <= sh * 1.005) and (
                (candle_range > 0 and (upper_wick / candle_range) >= 0.15) or
                (c_close <= c_open) or
                (candle_range > 0 and (c_high - c_close) / candle_range >= 0.45)
            )
        )
        if not (is_bullish_rejection or is_bearish_rejection):
            return None
        if is_bullish_rejection:
            return {"direction": "LONG", "entry": c_close, "stop": min(c_low, sl) * 0.998, "tp1": mid, "tp2": rh,
                    "tp1_label": "MID", "tp2_label": "RH", "reason": "Swept RL Buy Zone"}
        return {"direction": "SHORT", "entry": c_close, "stop": max(c_high, sh) * 1.002, "tp1": mid, "tp2": rl,
                "tp1_label": "MID", "tp2_label": "RL", "reason": "Swept RH Sell Zone"}


# ----------------------------------------------------------------------------------------------
# Strategy 2: 1-Candle 25% ATR Reversal (The Rumers, youtu.be/4zazKDSXlh8 - rules as specified)
# ----------------------------------------------------------------------------------------------
ATR_PERIOD = 14
SMA_PERIOD = 50
ATR_FRACTION = 0.25
FLUSH_MAX_CANDLES = 3     # a flush/spike is 1 to 3 consecutive 15m candles
FLUSH_LOOKBACK = 8        # the crossover must come within 8 x 15m candles (2h) of the flush ending
SL_BUFFER = 0.0015        # LONG SL = flush_low x 0.9985 ; SHORT SL = spike_high x 1.0015


def daily_sma_atr(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Adds SMA_50 and Wilder ATR_14 columns to a daily OHLC frame (ascending)."""
    d = df_daily.copy()
    prev_close = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev_close).abs(), (d["low"] - prev_close).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False, min_periods=ATR_PERIOD).mean()
    d["SMA50"] = d["close"].rolling(SMA_PERIOD).mean()
    return d


def _is_red(r):
    return float(r["close"]) < float(r["open"])


def _is_green(r):
    return float(r["close"]) > float(r["open"])


def _crossover(records, m, direction) -> bool:
    """LONG: previous candle red and close > its high. SHORT: previous candle green and close < its low."""
    if m < 1:
        return False
    prev, cur = records[m - 1], records[m]
    if direction == "LONG":
        return _is_red(prev) and float(cur["close"]) > float(prev["high"])
    return _is_green(prev) and float(cur["close"]) < float(prev["low"])


def find_flush(records, end_idx: int, atr: float, direction: str, lookback: int = FLUSH_LOOKBACK):
    """
    Most recent 1-3 candle manipulation move ending in [end_idx - lookback + 1, end_idx] whose
    high-to-low range is >= 25% of Daily ATR.
      direction LONG  -> bearish flush (last close < first open)
      direction SHORT -> bullish spike (last close > first open)
    Returns {start, end, high, low, range, pct_atr} or None.
    """
    if atr is None or atr <= 0 or end_idx < 0:
        return None
    threshold = ATR_FRACTION * atr
    for k in range(end_idx, max(-1, end_idx - lookback), -1):
        best = None
        for size in range(1, FLUSH_MAX_CANDLES + 1):
            s = k - size + 1
            if s < 0:
                break
            win = records[s:k + 1]
            hi = max(float(r["high"]) for r in win)
            lo = min(float(r["low"]) for r in win)
            first_open, last_close = float(win[0]["open"]), float(win[-1]["close"])
            directional = last_close < first_open if direction == "LONG" else last_close > first_open
            if directional and (hi - lo) >= threshold and (best is None or (hi - lo) > best["range"]):
                best = {"start": s, "end": k, "high": hi, "low": lo, "range": hi - lo,
                        "pct_atr": round((hi - lo) / atr * 100, 1)}
        if best:
            return best
    return None


def detect_atr_reversal(records, j: int, atr: float, bias: str):
    """
    Evaluates candle j (a CLOSED 15m candle) for the 1-candle crossover entry.
    bias BULLISH (daily close >= SMA50) -> LONG only ; BEARISH -> SHORT only.
    The crossover must be the FIRST one since the flush ended (one trade per flush).
    """
    if bias not in ("BULLISH", "BEARISH") or j < 2:
        return None
    direction = "LONG" if bias == "BULLISH" else "SHORT"
    if not _crossover(records, j, direction):
        return None
    flush = find_flush(records, j - 1, atr, direction)
    if not flush:
        return None
    if any(_crossover(records, m, direction) for m in range(flush["end"] + 1, j)):
        return None   # this flush already produced its crossover

    entry = float(records[j]["close"])
    seg = records[flush["start"]:j + 1]
    if direction == "LONG":
        origin = flush["high"]
        extreme = min(float(r["low"]) for r in seg)          # lowest wick of the flush (incl. follow-through)
        stop = extreme * (1 - SL_BUFFER)
        tp1 = extreme + 0.5 * (origin - extreme)
        if not (stop < entry < tp1):
            return None   # half the flush already retraced: no edge left to TP1
        side_txt = "above 50-SMA"
        move = "Flush"
    else:
        origin = flush["low"]
        extreme = max(float(r["high"]) for r in seg)
        stop = extreme * (1 + SL_BUFFER)
        tp1 = extreme - 0.5 * (extreme - origin)
        if not (tp1 < entry < stop):
            return None
        side_txt = "below 50-SMA"
        move = "Spike"
    return {
        "direction": direction, "entry": entry, "stop": stop, "tp1": tp1, "tp2": origin,
        "tp1_label": "TP1 50%", "tp2_label": "Origin",
        "flush": flush, "extreme": extreme,
        "reason": f"15m {move} = {flush['pct_atr']:.0f}% of Daily ATR (>25% threshold) {side_txt}",
    }


class AtrReversal(Strategy):
    id = "atr_reversal"
    name = "1-Candle 25% ATR Reversal"
    short = "ATR Rev"
    description = ("Daily 50-SMA bias + 14-day ATR. Above the SMA, wait for a 1-3 candle 15m flush >= 25% of "
                   "Daily ATR, then go LONG on the first candle that closes above the previous red candle's high "
                   "(SL below flush low, TP1 50% retrace, TP2 origin of the move). Mirror for SHORT below the SMA.")
    daily_warmup_days = 80
    tp1_name, tp2_name = "50% Retrace", "Origin"
    uses_live_price = False
    chart_marker_hint = "▲▼ markers = 15m candles whose high-low range is >= 25% of Daily ATR (shown on the 15m timeframe)."

    # ---- live ----
    def compute_levels(self, pair):
        d = eng.fetch_coindcx_candles(pair=pair, interval="1d", limit=90, sync_live_price=False)
        if d.empty or len(d) < SMA_PERIOD + 2:
            return None
        d = daily_sma_atr(d.iloc[:-1].reset_index(drop=True))   # completed days only
        last = d.iloc[-1]
        if pd.isna(last["SMA50"]) or pd.isna(last["ATR"]):
            return None
        close, sma, atr = float(last["close"]), float(last["SMA50"]), float(last["ATR"])
        return {
            "SMA50": eng.round_asset_price(sma, close), "ATR": round(atr, 6), "ATR25": round(ATR_FRACTION * atr, 6),
            "daily_close": close, "bias": "BULLISH" if close >= sma else "BEARISH",
            "prev_day_date": datetime.fromtimestamp(last["timestamp"] / 1000, tz=IST).strftime("%Y-%m-%d"),
        }

    def _context(self, pair, levels):
        levels = levels or self.compute_levels(pair)
        if not levels:
            return None, None
        df = _closed_15m(pair, 60)
        return levels, (df.to_dict("records") if not df.empty else [])

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
        levels, recs = self._context(pair, levels)
        if not levels or not recs:
            return None
        j = len(recs) - 1
        last = recs[j]
        session = eng.get_current_session_info(datetime.now(IST))
        hit = detect_atr_reversal(recs, j, levels["ATR"], levels["bias"])
        candle_time = datetime.fromtimestamp(last["timestamp"] / 1000, tz=IST).strftime("%H:%M IST")
        out = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "candle_evaluated": f"Last closed 15m candle ({candle_time}) [{session['emoji']} {session['name']}]",
            "session": session, "session_name": f"{session['emoji']} {session['name']}",
            "is_prime_session": session["is_prime"], "is_us_open_candle": session["session_id"] == "NEW_YORK",
            "pair": pair, "levels": levels, "candle_ts": int(last["timestamp"]),
            "signal": "NEUTRAL", "signal_kind": None, "trigger_zone": None, "trigger_reason": "",
            "setup": "WAIT / NO TRADE (no >=25% ATR flush followed by a 1-candle crossover)",
            "entry": float(last["close"]), "stop_loss": 0.0, "tp1": 0.0, "tp2": 0.0,
        }
        out.update(position_metrics(pair, out["entry"], 0.0, out["entry"], out["entry"], margin_inr, leverage, usd_inr))
        if hit:
            ref = hit["entry"]
            entry = eng.round_asset_price(hit["entry"], ref)
            sl, tp1, tp2 = (eng.round_asset_price(hit[k], ref) for k in ("stop", "tp1", "tp2"))
            word = "BUY (Long)" if hit["direction"] == "LONG" else "SELL (Short)"
            out.update({
                "signal": hit["direction"], "signal_kind": "ATR_REVERSAL",
                "trigger_zone": "Bullish flush above 50-SMA" if hit["direction"] == "LONG" else "Bearish spike below 50-SMA",
                "trigger_reason": hit["reason"], "setup": f"{word}: 1-Candle Crossover - {hit['reason']}",
                "entry": entry, "stop_loss": sl, "tp1": tp1, "tp2": tp2, "flush": hit["flush"],
            })
            out.update(position_metrics(pair, entry, sl, tp1, tp2, margin_inr, leverage, usd_inr))
        return self._stamp(out)

    def armed_plan(self, pair, levels):
        """Latest qualifying flush still waiting for its crossover (or None)."""
        levels, recs = self._context(pair, levels)
        if not levels or not recs:
            return None
        direction = "LONG" if levels["bias"] == "BULLISH" else "SHORT"
        j = len(recs) - 1
        flush = find_flush(recs, j, levels["ATR"], direction)
        if not flush or any(_crossover(recs, m, direction) for m in range(flush["end"] + 1, j + 1)):
            return None
        seg = recs[flush["start"]:]
        # crossover level = high (LONG) / low (SHORT) of the most recent red / green candle since the flush started
        pick = _is_red if direction == "LONG" else _is_green
        ref = next((r for r in reversed(seg) if pick(r)), seg[-1])
        if direction == "LONG":
            extreme = min(float(r["low"]) for r in seg)
            entry, stop, tp2 = float(ref["high"]), extreme * (1 - SL_BUFFER), flush["high"]
            tp1 = extreme + 0.5 * (tp2 - extreme)
        else:
            extreme = max(float(r["high"]) for r in seg)
            entry, stop, tp2 = float(ref["low"]), extreme * (1 + SL_BUFFER), flush["low"]
            tp1 = extreme - 0.5 * (extreme - tp2)
        return {"direction": direction, "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2, "flush": flush,
                "levels": levels}

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr):
        out = {"BUY": None, "SELL": None, "note": ""}
        sig = self.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
        if sig and sig["signal"] in ("LONG", "SHORT"):
            key = "BUY" if sig["signal"] == "LONG" else "SELL"
            out[key] = self._stamp({**sig, "direction": key, "setup": sig["setup"]})
            out["note"] = "Crossover confirmed on the last closed 15m candle."
            return out
        plan = self.armed_plan(pair, levels)
        if not plan:
            lv = (sig or {}).get("levels") or levels
            side = "bearish flush (LONG idea)" if (lv or {}).get("bias") == "BULLISH" else "bullish spike (SHORT idea)"
            thr = f" of >= ${lv['ATR25']:,.4f}" if lv else ""
            out["note"] = f"Waiting for a 15m {side}{thr} — no order ticket until a qualifying move prints."
            return out
        ref = plan["entry"]
        e, sl, t1, t2 = (eng.round_asset_price(plan[k], ref) for k in ("entry", "stop", "tp1", "tp2"))
        key = "BUY" if plan["direction"] == "LONG" else "SELL"
        move = "Flush" if key == "BUY" else "Spike"
        reason = (f"Armed: 15m {move} = {plan['flush']['pct_atr']:.0f}% of Daily ATR — waiting for a close "
                  f"{'above' if key == 'BUY' else 'below'} {e:,.4f}")
        setup = {"direction": key, "setup": f"{'BUY (Long)' if key == 'BUY' else 'SELL (Short)'}: 1-Candle Crossover (armed)",
                 "entry": e, "stop_loss": sl, "tp1": t1, "tp2": t2, "trigger_reason": reason, "flush": plan["flush"]}
        setup.update(position_metrics(pair, e, sl, t1, t2, margin_inr, leverage, usd_inr))
        out[key] = self._stamp(setup)
        out["note"] = reason
        return out

    # ---- UI hooks ----
    def chart_lines(self, levels, plan=None):
        lines = []
        if levels:
            lines.append({"label": "50-Day SMA", "price": levels["SMA50"], "color": "#8b5cf6", "dash": "dash"})
        if plan:
            fl = plan.get("flush") or {}
            if fl:
                lines.append({"label": "Flush High", "price": fl["high"], "color": "#f59e0b", "dash": "dot"})
                lines.append({"label": "Flush Low", "price": fl["low"], "color": "#f59e0b", "dash": "dot"})
            lines += [
                {"label": "Crossover Entry", "price": plan["entry"], "color": "#10b981" if plan["direction"] == "BUY" else "#f43f5e", "dash": "solid"},
                {"label": "Stop Loss", "price": plan["stop_loss"], "color": "#ef4444", "dash": "dash"},
                {"label": "TP1 (50% retrace)", "price": plan["tp1"], "color": "#06b6d4", "dash": "dot"},
                {"label": "TP2 (Origin)", "price": plan["tp2"], "color": "#16a34a", "dash": "dot"},
            ]
        return lines

    def chart_markers(self, df, levels, tf):
        if df is None or df.empty or not levels or tf != "15m":
            return []
        thr = levels["ATR25"]
        out = []
        for i, r in df.iterrows():
            rng = float(r["high"]) - float(r["low"])
            if rng >= thr:
                bear = float(r["close"]) < float(r["open"])
                out.append({"idx": i, "price": float(r["low"]) if bear else float(r["high"]),
                            "text": f"{rng / levels['ATR'] * 100:.0f}% ATR", "bear": bear})
        return out

    def metric_badges(self, levels):
        if not levels:
            return []
        return [
            ("50-Day SMA", f"${levels['SMA50']:,.4f}", f"Daily close ${levels['daily_close']:,.4f}"),
            ("Daily ATR (14)", f"${levels['ATR']:,.4f}", None),
            ("25% ATR Sucker Threshold", f"${levels['ATR25']:,.4f}", None),
            ("Daily Bias", "🟢 BULLISH (longs only)" if levels["bias"] == "BULLISH" else "🔴 BEARISH (shorts only)", None),
        ]

    def level_rows(self, levels, live_price):
        if not levels:
            return []

        def dist(p):
            return f"{(p - live_price) / live_price * 100:.2f}%" if live_price else "N/A"
        return [
            {"Level Name": "50-Day SMA", "Price": f"${levels['SMA50']:,.4f}", "Role in Strategy": "Bias filter: close above = LONG setups only, below = SHORT only", "Distance from Live": dist(levels["SMA50"])},
            {"Level Name": "Daily ATR (14)", "Price": f"${levels['ATR']:,.4f}", "Role in Strategy": "Average daily range used to size the manipulation move", "Distance from Live": "—"},
            {"Level Name": "25% ATR Threshold", "Price": f"${levels['ATR25']:,.4f}", "Role in Strategy": "Minimum 1-3 candle 15m flush / spike size to arm a setup", "Distance from Live": "—"},
        ]

    # ---- backtest ----
    def prepare_backtest(self, df, df_daily):
        d = daily_sma_atr(df_daily.reset_index(drop=True))
        stats = {}
        for i in range(1, len(d)):
            prev = d.iloc[i - 1]   # completed prior day only (no look-ahead)
            if pd.isna(prev["SMA50"]) or pd.isna(prev["ATR"]):
                continue
            stats[d.iloc[i]["date_str"]] = {"atr": float(prev["ATR"]),
                                             "bias": "BULLISH" if float(prev["close"]) >= float(prev["SMA50"]) else "BEARISH"}
        return {"daily": stats}

    def backtest_has_context(self, candle, ctx):
        return candle["date_str"] in ctx["daily"]

    def backtest_entry(self, idx, candle, ctx, records):
        day = ctx["daily"][candle["date_str"]]
        return detect_atr_reversal(records, idx, day["atr"], day["bias"])


# ----------------------------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------------------------
STRATEGY_REGISTRY: dict[str, Strategy] = {
    BoxTheorySweep.id: BoxTheorySweep(),
    AtrReversal.id: AtrReversal(),
}
DEFAULT_STRATEGY_ID = BoxTheorySweep.id


def get_strategy(strategy_id: str | None) -> Strategy:
    return STRATEGY_REGISTRY.get(strategy_id or DEFAULT_STRATEGY_ID, STRATEGY_REGISTRY[DEFAULT_STRATEGY_ID])


def list_strategies() -> list[Strategy]:
    return list(STRATEGY_REGISTRY.values())


def strategy_by_name(name: str) -> Strategy | None:
    return next((s for s in STRATEGY_REGISTRY.values() if s.name == name), None)


def setup_tag(strategy_id: str, kind: str) -> str:
    """Session-state tag for execution inputs; Box Theory keeps the legacy BUY / SELL / SIGNAL tags."""
    return kind if strategy_id == DEFAULT_STRATEGY_ID else f"{strategy_id}_{kind}"
