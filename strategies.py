"""
Pluggable strategy registry for the Crypto Trade Assistant.

Every strategy implements the same small interface, so the signal monitor, e-mail alerts, the
Key Levels / Trade Execution / Backtest tabs and the backtester can loop over STRATEGY_REGISTRY
without knowing anything strategy-specific.

Interface
  compute_levels(pair)                                   -> dict | None   (live reference levels)
  evaluate_signal(pair, levels, margin, lev, usd_inr)    -> dict | None   (last CLOSED candle)
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
    df = eng.fetch_coindcx_candles(pair=pair, interval="15m", limit=limit + 5, sync_live_price=False)
    if df.empty:
        return df
    now_ms = int(time.time() * 1000)
    closed = df[df["timestamp"] + 900000 <= now_ms].reset_index(drop=True)
    if closed.empty:
        closed = df.iloc[:-1].reset_index(drop=True)
    if not closed.empty:
        closed["EMA50"] = closed["close"].ewm(span=50, adjust=False).mean()
        closed["EMA200"] = closed["close"].ewm(span=200, adjust=False).mean()
    return closed.iloc[-limit:].reset_index(drop=True) if len(closed) > limit else closed


def _closed_5m(pair: str, limit: int) -> pd.DataFrame:
    df = eng.fetch_coindcx_candles(pair=pair, interval="5m", limit=limit + 5, sync_live_price=False)
    if df.empty:
        return df
    now_ms = int(time.time() * 1000)
    closed = df[df["timestamp"] + 300000 <= now_ms].reset_index(drop=True)
    if closed.empty:
        closed = df.iloc[:-1].reset_index(drop=True)
    if not closed.empty:
        closed["EMA50"] = closed["close"].ewm(span=50, adjust=False).mean()
        closed["EMA200"] = closed["close"].ewm(span=200, adjust=False).mean()
    return closed.iloc[-limit:].reset_index(drop=True) if len(closed) > limit else closed


def classify_daily_ema_bias(close_val: float, ema50_val: float, ema200_val: float) -> str:
    """
    Strict Daily Trend Bias Rule:
      - Daily Close < 50 EMA AND Daily Close < 200 EMA -> BEARISH (SHORT setups only)
      - Daily Close > 50 EMA AND Daily Close > 200 EMA -> BULLISH (LONG setups only)
      - Otherwise (price between 50 EMA and 200 EMA)   -> NEUTRAL (NO TRADE)
    """
    if close_val < ema50_val and close_val < ema200_val:
        return "BEARISH"
    if close_val > ema50_val and close_val > ema200_val:
        return "BULLISH"
    return "NEUTRAL"


# Dynamic Single-TP & Strict-SL Constants (at 5x default leverage)
MAX_TP_ROE_PCT = 20.0         # Max TP = 20% ROE (4.0% price move at 5x) or MID whichever is lower/closer
MIN_TP_ROE_PCT = 5.0          # Skip trade if TP distance is < 5% ROE (1.0% price move at 5x)
MAX_SL_ROE_PCT = 5.0          # Strict SL = 5% ROE (1.0% price move at 5x) or Sweep SL whichever is lower/closer
MAX_TRADES_PER_DAY = 2        # Max 2 trades per coin per day
DAILY_WIN_ROE_LOCK_PCT = 10.0 # Done for the day once a trade hits >= 10% ROE


def apply_dynamic_roe_tp_sl(
    direction: str,
    entry: float,
    struct_stop: float,
    struct_tp1: float,
    leverage: int = 5,
    max_tp_roe: float = MAX_TP_ROE_PCT,
    max_sl_roe: float = MAX_SL_ROE_PCT,
    min_tp_roe: float = MIN_TP_ROE_PCT,
    enforce_min_tp: bool = True,
) -> tuple[float, float, str] | None:
    """
    Computes the single complete-exit Take Profit and strict Stop Loss:
      1. TP = min(structural TP [MID / 50% retrace], Max TP ROE [15-20% ROE]) — 100% complete exit, no split.
      2. If enforce_min_tp and TP ROE < 5% ROE, returns None so low-reward mid-box trades are skipped.
      3. SL = min(structural sweep SL [SH/SL / Flush Extreme], 5% ROE [1.0% price move at 5x]) — whichever is closer.
    Returns (stop_price, single_tp_price, tp_label) or None.
    """
    if entry <= 0:
        return None
    lev = max(1, int(leverage))
    struct_tp_dist = abs(struct_tp1 - entry)
    max_tp_dist = entry * (max_tp_roe / 100.0 / lev)
    min_tp_dist = entry * (min_tp_roe / 100.0 / lev)

    tp_dist = min(struct_tp_dist, max_tp_dist)
    if enforce_min_tp and tp_dist < (min_tp_dist * 0.98):
        return None

    struct_sl_dist = abs(struct_stop - entry) if struct_stop > 0 else entry * (max_sl_roe / 100.0 / lev)
    max_sl_dist = entry * (max_sl_roe / 100.0 / lev)
    sl_dist = min(struct_sl_dist, max_sl_dist)

    is_long = direction.upper() in ("LONG", "BUY")
    if is_long:
        tp_price = entry + tp_dist
        sl_price = entry - sl_dist
    else:
        tp_price = entry - tp_dist
        sl_price = entry + sl_dist

    tp_roe = round((tp_dist / entry) * lev * 100.0, 1)
    tp_label = f"Single TP ({tp_roe:.0f}% ROE)" if tp_dist < struct_tp_dist else f"MID ({tp_roe:.1f}% ROE)"
    return sl_price, tp_price, tp_label


class Strategy:
    id = "base"
    name = "Base Strategy"
    short = "Base"
    timeframe = "15m"
    description = ""
    daily_warmup_days = 220   # extra daily candles fetched before backtest window for 200 EMA warmup
    tp1_name, tp2_name = "TP1", "TP2"
    uses_live_price = False
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
# Strategy 1: Box Theory + 50/200 EMA Trend & Rejection
# ----------------------------------------------------------------------------------------------
class BoxTheorySweep(Strategy):
    id = "box_theory"
    name = "Box Theory Sweep"
    short = "Box"
    timeframe = "Daily 50/200 EMA Bias -> 15m/5m Zone or 50 EMA Next-Candle Rejection"
    description = (
        "Daily 50 EMA & 200 EMA trend-filtered strategy: "
        "When Daily is below 50 & 200 EMA (Bearish), ONLY takes SHORT setups when price reaches Sell Zone (RH-SH) "
        "or 50 EMA and rejects on the next candle. "
        "When Daily is above 50 & 200 EMA (Bullish), ONLY takes LONG setups when price reaches Buy Zone (RL-SL) "
        "or 50 EMA and rejects on the next candle."
    )
    daily_warmup_days = 220
    tp1_name, tp2_name = "MID", "Extreme"
    uses_live_price = True

    def compute_levels(self, pair):
        return eng.calculate_daily_box_levels(pair)

    @staticmethod
    def _reason(sig: dict) -> str:
        return sig.get("trigger_reason", "")

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
        levels = levels or self.compute_levels(pair)
        if not levels:
            return None
        df_15m = _closed_15m(pair, 80)
        df_5m = _closed_5m(pair, 80)
        if df_15m.empty or df_5m.empty or len(df_15m) < 3 or len(df_5m) < 3:
            return None

        rh, rl = float(levels["RH"]), float(levels["RL"])
        sh, sl = float(levels["SH"]), float(levels["SL"])
        mid = float(levels["MID"])
        daily_ema50 = float(levels.get("EMA50", rh))
        daily_ema200 = float(levels.get("EMA200", rh))
        daily_close = float(levels.get("daily_close", mid))
        trend_bias = levels.get("trend_bias") or classify_daily_ema_bias(daily_close, daily_ema50, daily_ema200)

        session = eng.get_current_session_info(datetime.now(IST))

        recs_15m = df_15m.to_dict("records")
        recs_5m = df_5m.to_dict("records")
        c5 = recs_5m[-1]
        prev_c5 = recs_5m[-2]
        c15 = recs_15m[-1]
        prev_c15 = recs_15m[-2]

        c5_close = float(c5["close"])
        c5_open = float(c5.get("open", c5_close))
        c5_high = float(c5["high"])
        c5_low = float(c5["low"])
        prev_c5_close = float(prev_c5["close"])

        c15_close = float(c15["close"])
        c15_open = float(c15.get("open", c15_close))
        c15_high = float(c15["high"])
        c15_low = float(c15["low"])
        prev_c15_close = float(prev_c15["close"])
        ema50_15m = float(c15.get("EMA50", daily_ema50))
        prev_ema50_15m = float(prev_c15.get("EMA50", ema50_15m))

        candle_time = datetime.fromtimestamp(c5["timestamp"] / 1000, tz=IST).strftime("%H:%M IST")

        out = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "candle_evaluated": f"Daily {trend_bias} Bias | 15m/5m confirmation ({candle_time}) [{session['emoji']} {session['name']}]",
            "session": session, "session_name": f"{session['emoji']} {session['name']}",
            "is_prime_session": session["is_prime"], "is_us_open_candle": session["session_id"] == "NEW_YORK",
            "pair": pair, "levels": levels, "candle_ts": int(c5["timestamp"]),
            "signal": "NEUTRAL", "signal_kind": None, "trigger_zone": None, "trigger_reason": "",
            "setup": f"WAIT / NO TRADE (Daily Bias: {trend_bias} | 50 EMA: ${daily_ema50:,.2f}, 200 EMA: ${daily_ema200:,.2f})",
            "entry": c5_close, "stop_loss": 0.0, "tp1": mid, "tp2": rl if trend_bias == "BEARISH" else rh,
        }
        out.update(position_metrics(pair, c5_close, 0.0, mid, out["tp2"], margin_inr, leverage, usd_inr))

        # 1. Strict Daily Trend Bias Gate: Do not alert if price is trapped between Daily 50 EMA & 200 EMA
        if trend_bias == "NEUTRAL":
            out["setup"] = (
                f"WAIT / NO TRADE — Daily Close (${daily_close:,.2f}) is between Daily 50 EMA (${daily_ema50:,.2f}) "
                f"& 200 EMA (${daily_ema200:,.2f}). Trend bias is neutral."
            )
            out["trigger_reason"] = "Daily price between 50 EMA and 200 EMA (no directional bias)"
            return self._stamp(out)

        # 2. BEARISH BIAS (Daily below 50 EMA & 200 EMA) -> SHORT SIGNALS ONLY
        if trend_bias == "BEARISH":
            recent_15m = recs_15m[-3:-1]
            # Condition A: Price swept Box Sell Zone (RH-SH) and rejects back below RH
            swept_rh_prior = any(float(r["high"]) >= rh or float(r["open"]) >= rh for r in recent_15m)
            swept_rh_curr15 = (c15_high >= rh) or (float(prev_c15["high"]) >= rh)

            rejected_rh_5m = swept_rh_prior and (c5_close < rh) and (c5_close <= c5_open or c5_close < prev_c5_close)
            rejected_rh_15m = swept_rh_curr15 and (c15_close < rh) and (c15_close <= c15_open or c15_close < prev_c15_close)

            # Condition B: Price reached Daily 50 EMA resistance and next candle rejects lower
            min_short_zone = rl + 0.35 * (rh - rl)
            touched_daily_ema50 = (
                any(float(r["high"]) >= daily_ema50 * 0.999 and float(r["low"]) <= daily_ema50 * 1.005 for r in recs_15m[-3:])
                and c5_close >= min_short_zone
            )
            rejected_d_ema50 = (
                touched_daily_ema50
                and (c5_close < daily_ema50)
                and (c5_close < c5_open)
                and (c5_close < prev_c5_close)
            )

            if rejected_rh_5m or rejected_rh_15m:
                raw_entry = c5_close if rejected_rh_5m else c15_close
                entry = eng.round_asset_price(raw_entry, rh)
                sweep_high = max(float(r["high"]) for r in recs_15m[-3:])
                struct_stop = max(sweep_high, c5_high, sh) * 1.002
                struct_tp1 = mid if entry > mid else rl
                dyn = apply_dynamic_roe_tp_sl("SHORT", entry, struct_stop, struct_tp1, leverage)
                if dyn:
                    stop_raw, tp_raw, tp_lbl = dyn
                    stop = eng.round_asset_price(stop_raw, rh)
                    tp1 = eng.round_asset_price(tp_raw, rh)
                    tp2 = tp1
                    tf_lbl = "5m" if rejected_rh_5m else "15m"
                    reason = (
                        f"Daily Bearish (<50 & 200 EMA) | Swept RH (${rh:,.2f}) + {tf_lbl} rejection "
                        f"(close ${entry:,.2f} < RH | {tp_lbl}, Strict SL <=5% ROE)"
                    )
                    out.update({
                        "signal": "SHORT", "signal_kind": "REVERSAL", "trigger_zone": "Sell Zone RH-SH",
                        "trigger_reason": reason,
                        "setup": f"SELL (Short): RH Sell Zone Sweep + Rejection ({session['name']})",
                        "entry": entry, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                        "candle_ts": int(c5["timestamp"] if rejected_rh_5m else c15["timestamp"]),
                    })
                    out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr))
                    return self._stamp(out)

            if rejected_d_ema50:
                entry = eng.round_asset_price(c5_close, rh)
                sweep_high = max(float(prev_c15["high"]), c15_high, c5_high, daily_ema50)
                struct_stop = sweep_high * 1.0025
                struct_tp1 = mid if entry > mid else rl
                dyn = apply_dynamic_roe_tp_sl("SHORT", entry, struct_stop, struct_tp1, leverage)
                if dyn:
                    stop_raw, tp_raw, tp_lbl = dyn
                    stop = eng.round_asset_price(stop_raw, rh)
                    tp1 = eng.round_asset_price(tp_raw, rh)
                    tp2 = tp1
                    if stop > entry > tp1:
                        reason = (
                            f"Daily Bearish (<50 & 200 EMA) | Touched Daily 50 EMA (${daily_ema50:,.2f}) + next-candle "
                            f"bearish rejection (close ${entry:,.2f} < Daily 50 EMA | {tp_lbl}, Strict SL <=5% ROE)"
                        )
                        out.update({
                            "signal": "SHORT", "signal_kind": "EMA50_REJECTION", "trigger_zone": "Daily 50 EMA Resistance",
                            "trigger_reason": reason,
                            "setup": f"SELL (Short): Daily 50 EMA Touch + Next-Candle Rejection ({session['name']})",
                            "entry": entry, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                            "candle_ts": int(c5["timestamp"]),
                        })
                        out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr))
                        return self._stamp(out)

            out["setup"] = (
                f"WAIT / SHORT ONLY (Daily < 50 EMA ${daily_ema50:,.2f} & 200 EMA ${daily_ema200:,.2f} — "
                f"watching for price to reach RH ${rh:,.2f} or Daily 50 EMA ${daily_ema50:,.2f} and reject)"
            )
            out["trigger_reason"] = "Daily Bearish (<50 & 200 EMA): Long signals blocked; watching RH / Daily 50 EMA for Short rejection"
            return self._stamp(out)

        # 3. BULLISH BIAS (Daily above 50 EMA & 200 EMA) -> LONG SIGNALS ONLY
        if trend_bias == "BULLISH":
            recent_15m = recs_15m[-3:-1]
            swept_rl_prior = any(float(r["low"]) <= rl or float(r["open"]) <= rl for r in recent_15m)
            swept_rl_curr15 = (c15_low <= rl) or (float(prev_c15["low"]) <= rl)

            rejected_rl_5m = swept_rl_prior and (c5_close > rl) and (c5_close >= c5_open or c5_close > prev_c5_close)
            rejected_rl_15m = swept_rl_curr15 and (c15_close > rl) and (c15_close >= c15_open or c15_close > prev_c15_close)

            max_long_zone = rh - 0.35 * (rh - rl)
            touched_daily_ema50 = (
                any(float(r["low"]) <= daily_ema50 * 1.001 and float(r["high"]) >= daily_ema50 * 0.995 for r in recs_15m[-3:])
                and c5_close <= max_long_zone
            )
            rejected_d_ema50 = (
                touched_daily_ema50
                and (c5_close > daily_ema50)
                and (c5_close > c5_open)
                and (c5_close > prev_c5_close)
            )

            if rejected_rl_5m or rejected_rl_15m:
                raw_entry = c5_close if rejected_rl_5m else c15_close
                entry = eng.round_asset_price(raw_entry, rl)
                sweep_low = min(float(r["low"]) for r in recs_15m[-3:])
                struct_stop = min(sweep_low, c5_low, sl) * 0.998
                struct_tp1 = mid if entry < mid else rh
                dyn = apply_dynamic_roe_tp_sl("LONG", entry, struct_stop, struct_tp1, leverage)
                if dyn:
                    stop_raw, tp_raw, tp_lbl = dyn
                    stop = eng.round_asset_price(stop_raw, rl)
                    tp1 = eng.round_asset_price(tp_raw, rl)
                    tp2 = tp1
                    tf_lbl = "5m" if rejected_rl_5m else "15m"
                    reason = (
                        f"Daily Bullish (>50 & 200 EMA) | Swept RL (${rl:,.2f}) + {tf_lbl} rejection "
                        f"(close ${entry:,.2f} > RL | {tp_lbl}, Strict SL <=5% ROE)"
                    )
                    out.update({
                        "signal": "LONG", "signal_kind": "REVERSAL", "trigger_zone": "Buy Zone RL-SL",
                        "trigger_reason": reason,
                        "setup": f"BUY (Long): RL Buy Zone Sweep + Rejection ({session['name']})",
                        "entry": entry, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                        "candle_ts": int(c5["timestamp"] if rejected_rl_5m else c15["timestamp"]),
                    })
                    out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr))
                    return self._stamp(out)

            if rejected_d_ema50:
                entry = eng.round_asset_price(c5_close, rl)
                sweep_low = min(float(prev_c15["low"]), c15_low, c5_low, daily_ema50)
                struct_stop = sweep_low * 0.9975
                struct_tp1 = mid if entry < mid else rh
                dyn = apply_dynamic_roe_tp_sl("LONG", entry, struct_stop, struct_tp1, leverage)
                if dyn:
                    stop_raw, tp_raw, tp_lbl = dyn
                    stop = eng.round_asset_price(stop_raw, rl)
                    tp1 = eng.round_asset_price(tp_raw, rl)
                    tp2 = tp1
                    if stop < entry < tp1:
                        reason = (
                            f"Daily Bullish (>50 & 200 EMA) | Touched Daily 50 EMA (${daily_ema50:,.2f}) + next-candle "
                            f"bullish rejection (close ${entry:,.2f} > Daily 50 EMA | {tp_lbl}, Strict SL <=5% ROE)"
                        )
                        out.update({
                            "signal": "LONG", "signal_kind": "EMA50_REJECTION", "trigger_zone": "Daily 50 EMA Support",
                            "trigger_reason": reason,
                            "setup": f"BUY (Long): Daily 50 EMA Touch + Next-Candle Rejection ({session['name']})",
                            "entry": entry, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                            "candle_ts": int(c5["timestamp"]),
                        })
                        out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr))
                        return self._stamp(out)

            out["setup"] = (
                f"WAIT / LONG ONLY (Daily > 50 EMA ${daily_ema50:,.2f} & 200 EMA ${daily_ema200:,.2f} — "
                f"watching for price to reach RL ${rl:,.2f} or Daily 50 EMA ${daily_ema50:,.2f} and reject)"
            )
            out["trigger_reason"] = "Daily Bullish (>50 & 200 EMA): Short signals blocked; watching RL / Daily 50 EMA for Long rejection"
            return self._stamp(out)

        return self._stamp(out)

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr):
        if not levels:
            return {"BUY": None, "SELL": None, "note": "Box levels unavailable."}
        sig = self.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
        trend_bias = levels.get("trend_bias") or classify_daily_ema_bias(
            float(levels.get("daily_close", levels["MID"])),
            float(levels.get("EMA50", levels["MID"])),
            float(levels.get("EMA200", levels["MID"])),
        )
        b = eng.calculate_trade_setup_details("BUY", levels, live_price, margin_inr, leverage, usd_inr, pair=pair)
        s = eng.calculate_trade_setup_details("SELL", levels, live_price, margin_inr, leverage, usd_inr, pair=pair)
        if b:
            b["trigger_reason"] = "Planned (Daily Bullish > 50 & 200 EMA): RL Buy Zone or 50 EMA touch + next-candle rejection"
        if s:
            s["trigger_reason"] = "Planned (Daily Bearish < 50 & 200 EMA): RH Sell Zone or 50 EMA touch + next-candle rejection"

        if sig and sig.get("signal") == "LONG":
            return {"BUY": self._stamp({**sig, "direction": "BUY"}), "SELL": None,
                    "note": f"⚡ Live confirmed LONG signal: {sig.get('trigger_reason')}"}
        if sig and sig.get("signal") == "SHORT":
            return {"BUY": None, "SELL": self._stamp({**sig, "direction": "SELL"}),
                    "note": f"⚡ Live confirmed SHORT signal: {sig.get('trigger_reason')}"}

        if trend_bias == "BEARISH":
            return {
                "BUY": None,
                "SELL": self._stamp(s),
                "note": f"🔴 Daily Trend Bias is BEARISH (below 50 EMA ${levels.get('EMA50', 0):,.2f} & 200 EMA ${levels.get('EMA200', 0):,.2f}) — SHORT setups only."
            }
        if trend_bias == "BULLISH":
            return {
                "BUY": self._stamp(b),
                "SELL": None,
                "note": f"🟢 Daily Trend Bias is BULLISH (above 50 EMA ${levels.get('EMA50', 0):,.2f} & 200 EMA ${levels.get('EMA200', 0):,.2f}) — LONG setups only."
            }
        return {
            "BUY": None,
            "SELL": None,
            "note": f"⚪ Daily Close is between 50 EMA (${levels.get('EMA50', 0):,.2f}) and 200 EMA (${levels.get('EMA200', 0):,.2f}) — No trade until trend aligns."
        }

    def chart_lines(self, levels, plan=None):
        if not levels:
            return []
        lines = [
            {"label": "SH (Swing High)", "price": levels["SH"], "color": "#ef4444", "dash": "dash"},
            {"label": "RH / PDH", "price": levels["RH"], "color": "#ea580c", "dash": "solid"},
            {"label": "MID (50%)", "price": levels["MID"], "color": "#0284c7", "dash": "dot"},
            {"label": "RL / PDL", "price": levels["RL"], "color": "#16a34a", "dash": "solid"},
            {"label": "SL (Swing Low)", "price": levels["SL"], "color": "#10b981", "dash": "dash"},
        ]
        if "EMA50" in levels:
            lines.append({"label": "Daily 50 EMA", "price": levels["EMA50"], "color": "#8b5cf6", "dash": "dash"})
        if "EMA200" in levels:
            lines.append({"label": "Daily 200 EMA", "price": levels["EMA200"], "color": "#f59e0b", "dash": "dash"})
        return lines

    # ---- backtest: Daily 50 & 200 EMA Bias + Box RH/RL or 50 EMA Touch + Next-Candle Rejection ----
    def prepare_backtest(self, df, df_daily):
        d = df_daily.copy().reset_index(drop=True)
        d["EMA50"] = d["close"].ewm(span=50, adjust=False).mean()
        d["EMA200"] = d["close"].ewm(span=200, adjust=False).mean()
        daily_records = d.to_dict("records")

        # Also precompute 15m 50 EMA across the execution candles
        ema50_15m_list = df["close"].ewm(span=50, adjust=False).mean().tolist()

        daily_boxes = {}
        for i in range(1, len(daily_records)):
            curr_day_str = daily_records[i]["date_str"]
            prev_day = daily_records[i - 1]
            rh = float(prev_day["high"])
            rl = float(prev_day["low"])
            prev_close = float(prev_day["close"])
            ema50 = float(prev_day["EMA50"])
            ema200 = float(prev_day["EMA200"])
            mid = (rh + rl) / 2.0
            bias = classify_daily_ema_bias(prev_close, ema50, ema200)

            lookback_start = max(0, i - 30)
            prior_slice = daily_records[lookback_start:i - 1]
            prior_highs = [float(x["high"]) for x in prior_slice] if prior_slice else []
            prior_lows = [float(x["low"]) for x in prior_slice] if prior_slice else []

            sh_c = [h for h in prior_highs if h > rh]
            sh = min(sh_c) if sh_c else rh * 1.015
            sl_c = [l for l in prior_lows if l < rl]
            sl = max(sl_c) if sl_c else rl * 0.985

            daily_boxes[curr_day_str] = {
                "RH": rh, "RL": rl, "MID": mid, "SH": sh, "SL": sl,
                "EMA50": ema50, "EMA200": ema200, "bias": bias
            }
        return {"boxes": daily_boxes, "ema50_15m": ema50_15m_list}

    def backtest_has_context(self, candle, ctx):
        return bool(ctx["boxes"].get(candle["date_str"]))

    def backtest_entry(self, idx, candle, ctx, records):
        if idx < 1:
            return None
        box = ctx["boxes"][candle["date_str"]]
        bias = box["bias"]
        if bias == "NEUTRAL":
            return None

        rh, rl, mid = box["RH"], box["RL"], box["MID"]
        sh, sl = box["SH"], box["SL"]
        daily_ema50 = box["EMA50"]
        prev = records[idx - 1]

        c_high = float(candle["high"])
        c_low = float(candle["low"])
        c_close = float(candle["close"])
        c_open = float(candle.get("open", c_close))
        candle_range = c_high - c_low

        p_high = float(prev["high"])
        p_low = float(prev["low"])
        p_close = float(prev["close"])

        # BEARISH BIAS (Daily Close < 50 EMA & < 200 EMA) -> SHORT ONLY
        if bias == "BEARISH":
            upper_wick = c_high - max(c_open, c_close)
            is_bearish_rejection = (
                (c_high >= rh) and (c_close < rh) and (c_high <= sh * 1.005) and (
                    (candle_range > 0 and (upper_wick / candle_range) >= 0.15) or
                    (c_close <= c_open) or
                    (candle_range > 0 and (c_high - c_close) / candle_range >= 0.45)
                )
            )
            if is_bearish_rejection:
                struct_stop = max(c_high, sh) * 1.002
                dyn = apply_dynamic_roe_tp_sl("SHORT", c_close, struct_stop, mid, leverage=5)
                if dyn:
                    stop_p, tp_p, tp_lbl = dyn
                    return {
                        "direction": "SHORT", "entry": c_close, "stop": stop_p,
                        "tp1": tp_p, "tp2": tp_p, "tp1_label": tp_lbl, "tp2_label": tp_lbl,
                        "reason": "Daily <50/200 EMA + Swept RH Sell Zone"
                    }

            # Daily 50 EMA Touch + Next-Candle Rejection
            min_short_zone = rl + 0.35 * (rh - rl)
            touched_d_ema50 = (p_high >= daily_ema50 * 0.9995) and (p_low <= daily_ema50 * 1.005)
            if touched_d_ema50 and (c_close < daily_ema50) and (c_close < c_open) and (c_close < p_close) and (c_close >= min_short_zone):
                struct_stop = max(p_high, c_high, daily_ema50) * 1.0025
                struct_tp1 = mid if c_close > mid else rl
                if struct_stop > c_close > struct_tp1:
                    dyn = apply_dynamic_roe_tp_sl("SHORT", c_close, struct_stop, struct_tp1, leverage=5)
                    if dyn:
                        stop_p, tp_p, tp_lbl = dyn
                        return {
                            "direction": "SHORT", "entry": c_close, "stop": stop_p,
                            "tp1": tp_p, "tp2": tp_p, "tp1_label": tp_lbl, "tp2_label": tp_lbl,
                            "reason": "Daily <50/200 EMA + Daily 50 EMA Rejection"
                        }
            return None

        # BULLISH BIAS (Daily Close > 50 EMA & > 200 EMA) -> LONG ONLY
        if bias == "BULLISH":
            lower_wick = min(c_open, c_close) - c_low
            is_bullish_rejection = (
                (c_low <= rl) and (c_close > rl) and (c_low >= sl * 0.995) and (
                    (candle_range > 0 and (lower_wick / candle_range) >= 0.15) or
                    (c_close >= c_open) or
                    (candle_range > 0 and (c_close - c_low) / candle_range >= 0.45)
                )
            )
            if is_bullish_rejection:
                struct_stop = min(c_low, sl) * 0.998
                dyn = apply_dynamic_roe_tp_sl("LONG", c_close, struct_stop, mid, leverage=5)
                if dyn:
                    stop_p, tp_p, tp_lbl = dyn
                    return {
                        "direction": "LONG", "entry": c_close, "stop": stop_p,
                        "tp1": tp_p, "tp2": tp_p, "tp1_label": tp_lbl, "tp2_label": tp_lbl,
                        "reason": "Daily >50/200 EMA + Swept RL Buy Zone"
                    }

            # Daily 50 EMA Touch + Next-Candle Rejection
            max_long_zone = rh - 0.35 * (rh - rl)
            touched_d_ema50 = (p_low <= daily_ema50 * 1.0005) and (p_high >= daily_ema50 * 0.995)
            if touched_d_ema50 and (c_close > daily_ema50) and (c_close > c_open) and (c_close > p_close) and (c_close <= max_long_zone):
                struct_stop = min(p_low, c_low, daily_ema50) * 0.9975
                struct_tp1 = mid if c_close < mid else rh
                if struct_stop < c_close < struct_tp1:
                    dyn = apply_dynamic_roe_tp_sl("LONG", c_close, struct_stop, struct_tp1, leverage=5)
                    if dyn:
                        stop_p, tp_p, tp_lbl = dyn
                        return {
                            "direction": "LONG", "entry": c_close, "stop": stop_p,
                            "tp1": tp_p, "tp2": tp_p, "tp1_label": tp_lbl, "tp2_label": tp_lbl,
                            "reason": "Daily >50/200 EMA + Daily 50 EMA Rejection"
                        }
            return None

        return None


# ----------------------------------------------------------------------------------------------
# Strategy 2: 1-Candle 25% ATR Reversal (The Rumers, youtu.be/4zazKDSXlh8 + Daily 50/200 EMA Bias)
# ----------------------------------------------------------------------------------------------
ATR_PERIOD = 14
SMA_PERIOD = 50
ATR_FRACTION = 0.25
FLUSH_MAX_CANDLES = 3     # a flush/spike is 1 to 3 consecutive 15m candles
FLUSH_LOOKBACK = 8        # the crossover must come within 8 x 15m candles (2h) of the flush ending
SL_BUFFER = 0.0015        # LONG SL = flush_low x 0.9985 ; SHORT SL = spike_high x 1.0015


def daily_sma_atr(df_daily: pd.DataFrame) -> pd.DataFrame:
    """Adds EMA50, EMA200, SMA50 and Wilder ATR_14 columns to a daily OHLC frame (ascending)."""
    d = df_daily.copy()
    prev_close = d["close"].shift(1)
    tr = pd.concat([d["high"] - d["low"], (d["high"] - prev_close).abs(), (d["low"] - prev_close).abs()], axis=1).max(axis=1)
    d["ATR"] = tr.ewm(alpha=1.0 / ATR_PERIOD, adjust=False, min_periods=ATR_PERIOD).mean()
    d["SMA50"] = d["close"].rolling(SMA_PERIOD).mean()
    d["EMA50"] = d["close"].ewm(span=50, adjust=False).mean()
    d["EMA200"] = d["close"].ewm(span=200, adjust=False).mean()
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
    bias BULLISH (daily close > EMA50 & EMA200) -> LONG only ; BEARISH (< EMA50 & EMA200) -> SHORT only.
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
        extreme = min(float(r["low"]) for r in seg)
        struct_stop = extreme * (1 - SL_BUFFER)
        struct_tp1 = extreme + 0.5 * (origin - extreme)
        if not (struct_stop < entry < struct_tp1):
            return None
        side_txt = "above 50 & 200 EMA"
        move = "Flush"
    else:
        origin = flush["low"]
        extreme = max(float(r["high"]) for r in seg)
        struct_stop = extreme * (1 + SL_BUFFER)
        struct_tp1 = extreme - 0.5 * (extreme - origin)
        if not (struct_tp1 < entry < struct_stop):
            return None
        side_txt = "below 50 & 200 EMA"
        move = "Spike"

    dyn = apply_dynamic_roe_tp_sl(direction, entry, struct_stop, struct_tp1, leverage=5)
    if not dyn:
        return None
    stop_p, tp_p, tp_lbl = dyn
    return {
        "direction": direction, "entry": entry, "stop": stop_p, "tp1": tp_p, "tp2": tp_p,
        "tp1_label": tp_lbl, "tp2_label": tp_lbl,
        "flush": flush, "extreme": extreme,
        "reason": f"15m {move} = {flush['pct_atr']:.0f}% of Daily ATR (>25% threshold) {side_txt}",
    }


class AtrReversal(Strategy):
    id = "atr_reversal"
    name = "1-Candle 25% ATR Reversal"
    short = "ATR Rev"
    timeframe = "15m Flush -> 5m Crossover"
    description = ("Daily 50 & 200 EMA bias + 14-day ATR: 15m candle watches for >=25% ATR manipulation flush/spike, "
                   "switching to 5m timeframe for 1-candle reversal crossover entry (SL beyond flush extreme, "
                   "TP1 50% retrace, TP2 origin).")
    daily_warmup_days = 220
    tp1_name, tp2_name = "50% Retrace", "Origin"
    uses_live_price = False
    chart_marker_hint = "▲▼ markers = 15m candles whose high-low range is >= 25% of Daily ATR (shown on the 15m timeframe)."

    # ---- live ----
    def compute_levels(self, pair):
        d = eng.fetch_coindcx_candles(pair=pair, interval="1d", limit=1000, sync_live_price=False)
        if d.empty or len(d) < SMA_PERIOD + 2:
            return None
        d_full = daily_sma_atr(d.reset_index(drop=True))
        d_comp = daily_sma_atr(d.iloc[:-1].reset_index(drop=True))   # completed days for ATR
        last = d_full.iloc[-1]
        last_comp = d_comp.iloc[-1]
        if pd.isna(last["EMA50"]) or pd.isna(last_comp["ATR"]):
            return None
        close = float(last["close"])
        ema50 = float(last["EMA50"])
        ema200 = float(last["EMA200"])
        atr = float(last_comp["ATR"])
        bias = classify_daily_ema_bias(close, ema50, ema200)
        return {
            "SMA50": eng.round_asset_price(ema50, close),
            "EMA50": eng.round_asset_price(ema50, close),
            "EMA200": eng.round_asset_price(ema200, close),
            "ATR": round(atr, 6), "ATR25": round(ATR_FRACTION * atr, 6),
            "daily_close": close, "bias": bias,
            "prev_day_date": datetime.fromtimestamp(last_comp["timestamp"] / 1000, tz=IST).strftime("%Y-%m-%d"),
        }

    def _context(self, pair, levels):
        levels = levels or self.compute_levels(pair)
        if not levels:
            return None, None, None
        df15 = _closed_15m(pair, 60)
        df5 = _closed_5m(pair, 60)
        recs15 = df15.to_dict("records") if not df15.empty else []
        recs5 = df5.to_dict("records") if not df5.empty else []
        return levels, recs15, recs5

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=5, usd_inr=85.0):
        levels, recs15, recs5 = self._context(pair, levels)
        if not levels or not recs15:
            return None
        bias = levels["bias"]
        session = eng.get_current_session_info(datetime.now(IST))
        last_c5 = recs5[-1] if recs5 else recs15[-1]
        candle_time = datetime.fromtimestamp(last_c5["timestamp"] / 1000, tz=IST).strftime("%H:%M IST")

        out = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "candle_evaluated": f"15m trigger + 5m confirmation ({candle_time}) [{session['emoji']} {session['name']}]",
            "session": session, "session_name": f"{session['emoji']} {session['name']}",
            "is_prime_session": session["is_prime"], "is_us_open_candle": session["session_id"] == "NEW_YORK",
            "pair": pair, "levels": levels, "candle_ts": int(last_c5["timestamp"]),
            "signal": "NEUTRAL", "signal_kind": None, "trigger_zone": None, "trigger_reason": "",
            "setup": f"WAIT / NO TRADE (Daily Bias: {bias})",
            "entry": float(last_c5["close"]), "stop_loss": 0.0, "tp1": 0.0, "tp2": 0.0,
        }
        out.update(position_metrics(pair, out["entry"], 0.0, out["entry"], out["entry"], margin_inr, leverage, usd_inr))

        if bias not in ("BULLISH", "BEARISH"):
            out["setup"] = (
                f"WAIT / NO TRADE — Daily Close (${levels['daily_close']:,.2f}) is between "
                f"50 EMA (${levels['EMA50']:,.2f}) and 200 EMA (${levels['EMA200']:,.2f})"
            )
            return self._stamp(out)

        direction = "LONG" if bias == "BULLISH" else "SHORT"
        move = "Flush" if direction == "LONG" else "Spike"
        out["setup"] = f"WAIT / NO TRADE (Watching 15m candles for >={levels['ATR25']:,.2f} {move} manipulation)"

        # Step 1: Detect 15m manipulation move >= 25% Daily ATR
        j15 = len(recs15) - 1
        flush = find_flush(recs15, j15, levels["ATR"], direction)
        if not flush:
            return self._stamp(out)

        # Step 2: Switch to 5m timeframe for 1-candle reversal crossover confirmation
        if recs5 and len(recs5) >= 2:
            k5 = len(recs5) - 1
            if _crossover(recs5, k5, direction):
                cur5 = recs5[k5]
                prev5 = recs5[k5 - 1]
                entry = float(cur5["close"])
                if direction == "LONG":
                    extreme = flush["low"]
                    struct_stop = extreme * (1 - SL_BUFFER)
                    struct_tp1 = extreme + 0.5 * (flush["high"] - extreme)
                    valid_rr = struct_stop < entry < struct_tp1
                    side_txt = "above 50 & 200 EMA"
                    crossover_info = f"close ${entry:,.2f} > prev 5m red high ${float(prev5['high']):,.2f}"
                else:
                    extreme = flush["high"]
                    struct_stop = extreme * (1 + SL_BUFFER)
                    struct_tp1 = extreme - 0.5 * (extreme - flush["low"])
                    valid_rr = struct_tp1 < entry < struct_stop
                    side_txt = "below 50 & 200 EMA"
                    crossover_info = f"close ${entry:,.2f} < prev 5m green low ${float(prev5['low']):,.2f}"

                dyn = apply_dynamic_roe_tp_sl(direction, entry, struct_stop, struct_tp1, leverage) if valid_rr else None
                if dyn:
                    stop, tp1, tp_lbl = dyn
                    tp2 = tp1
                    word = "BUY (Long)" if direction == "LONG" else "SELL (Short)"
                    reason = (
                        f"15m {move} = {flush['pct_atr']:.0f}% ATR confirmed by 5m crossover "
                        f"({crossover_info} | {tp_lbl}, Strict SL <=5% ROE) {side_txt}"
                    )
                    out.update({
                        "signal": direction, "signal_kind": "ATR_REVERSAL",
                        "trigger_zone": "Bullish flush above 50/200 EMA" if direction == "LONG" else "Bearish spike below 50/200 EMA",
                        "trigger_reason": reason, "setup": f"{word}: 15m {move} + 5m Crossover Confirmation - {reason}",
                        "entry": eng.round_asset_price(entry, entry),
                        "stop_loss": eng.round_asset_price(stop, entry),
                        "tp1": eng.round_asset_price(tp1, entry),
                        "tp2": eng.round_asset_price(tp2, entry),
                        "flush": flush,
                    })
                    out.update(position_metrics(pair, out["entry"], out["stop_loss"], out["tp1"], out["tp2"], margin_inr, leverage, usd_inr))
                    return self._stamp(out)

        out["setup"] = f"WAIT / WATCHING 5m (15m {move} = {flush['pct_atr']:.0f}% ATR active — watching 5m timeframe for 1-candle crossover)"
        out["trigger_reason"] = f"15m {move} = {flush['pct_atr']:.0f}% ATR active — waiting for 5m crossover confirmation"
        return self._stamp(out)

    def armed_plan(self, pair, levels):
        """Latest qualifying flush still waiting for its crossover (or None)."""
        levels, recs15, recs5 = self._context(pair, levels)
        if not levels or not recs15 or levels["bias"] not in ("BULLISH", "BEARISH"):
            return None
        direction = "LONG" if levels["bias"] == "BULLISH" else "SHORT"
        j15 = len(recs15) - 1
        flush = find_flush(recs15, j15, levels["ATR"], direction)
        if not flush:
            return None
        use_recs = recs5 if recs5 else recs15
        if any(_crossover(use_recs, m, direction) for m in range(max(1, len(use_recs) - 6), len(use_recs))):
            return None
        pick = _is_red if direction == "LONG" else _is_green
        ref = next((r for r in reversed(use_recs[-12:]) if pick(r)), use_recs[-1])
        if direction == "LONG":
            extreme = flush["low"]
            entry, struct_stop, tp2 = float(ref["high"]), extreme * (1 - SL_BUFFER), flush["high"]
            struct_tp1 = extreme + 0.5 * (tp2 - extreme)
        else:
            extreme = flush["high"]
            entry, struct_stop, tp2 = float(ref["low"]), extreme * (1 + SL_BUFFER), flush["low"]
            struct_tp1 = extreme - 0.5 * (extreme - tp2)
        dyn = apply_dynamic_roe_tp_sl(direction, entry, struct_stop, struct_tp1, leverage=5, enforce_min_tp=False)
        if dyn:
            stop, tp1, _ = dyn
            tp2 = tp1
        else:
            stop, tp1 = struct_stop, struct_tp1
        return {"direction": direction, "entry": entry, "stop": stop, "tp1": tp1, "tp2": tp2, "flush": flush,
                "levels": levels}

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr):
        out = {"BUY": None, "SELL": None, "note": ""}
        sig = self.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
        if sig and sig["signal"] in ("LONG", "SHORT"):
            key = "BUY" if sig["signal"] == "LONG" else "SELL"
            out[key] = self._stamp({**sig, "direction": key, "setup": sig["setup"]})
            out["note"] = f"⚡ Live crossover confirmed on 5m candle: {sig.get('trigger_reason')}"
            return out
        plan = self.armed_plan(pair, levels)
        if not plan:
            lv = (sig or {}).get("levels") or levels
            if lv and lv.get("bias") == "NEUTRAL":
                out["note"] = f"Daily Close is between 50 EMA (${lv['EMA50']:,.2f}) and 200 EMA (${lv['EMA200']:,.2f}) — no setup armed."
                return out
            side = "bearish flush (LONG idea)" if (lv or {}).get("bias") == "BULLISH" else "bullish spike (SHORT idea)"
            thr = f" of >= ${lv['ATR25']:,.4f}" if lv else ""
            out["note"] = f"Waiting for a 15m {side}{thr} — no order ticket until a qualifying move prints."
            return out
        ref = plan["entry"]
        e, sl, t1, t2 = (eng.round_asset_price(plan[k], ref) for k in ("entry", "stop", "tp1", "tp2"))
        key = "BUY" if plan["direction"] == "LONG" else "SELL"
        move = "Flush" if key == "BUY" else "Spike"
        reason = (f"Armed: 15m {move} = {plan['flush']['pct_atr']:.0f}% of Daily ATR — watching 5m timeframe for close "
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
            lines.append({"label": "Daily 50 EMA", "price": levels["EMA50"], "color": "#8b5cf6", "dash": "dash"})
            if "EMA200" in levels:
                lines.append({"label": "Daily 200 EMA", "price": levels["EMA200"], "color": "#f59e0b", "dash": "dash"})
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
        bias_txt = (
            "🟢 BULLISH (longs only)" if levels["bias"] == "BULLISH"
            else ("🔴 BEARISH (shorts only)" if levels["bias"] == "BEARISH" else "⚪ NEUTRAL (no trade)")
        )
        return [
            ("Daily 50 EMA", f"${levels['EMA50']:,.4f}", f"Daily close ${levels['daily_close']:,.4f}"),
            ("Daily 200 EMA", f"${levels['EMA200']:,.4f}", None),
            ("25% ATR Threshold", f"${levels['ATR25']:,.4f}", f"Daily ATR ${levels['ATR']:,.4f}"),
            ("Daily Bias", bias_txt, None),
        ]

    def level_rows(self, levels, live_price):
        if not levels:
            return []

        def dist(p):
            return f"{(p - live_price) / live_price * 100:.2f}%" if live_price else "N/A"
        return [
            {"Level Name": "Daily 50 EMA", "Price": f"${levels['EMA50']:,.4f}", "Role in Strategy": "Primary trend & pullback filter (Close > 50 & 200 EMA = LONG only)", "Distance from Live": dist(levels["EMA50"])},
            {"Level Name": "Daily 200 EMA", "Price": f"${levels['EMA200']:,.4f}", "Role in Strategy": "Macro trend filter (Close < 50 & 200 EMA = SHORT only)", "Distance from Live": dist(levels["EMA200"])},
            {"Level Name": "Daily ATR (14)", "Price": f"${levels['ATR']:,.4f}", "Role in Strategy": "Average daily range used to size the manipulation move", "Distance from Live": "—"},
            {"Level Name": "25% ATR Threshold", "Price": f"${levels['ATR25']:,.4f}", "Role in Strategy": "Minimum 1-3 candle 15m flush / spike size to arm a setup", "Distance from Live": "—"},
        ]

    # ---- backtest ----
    def prepare_backtest(self, df, df_daily):
        d = daily_sma_atr(df_daily.reset_index(drop=True))
        stats = {}
        for i in range(1, len(d)):
            prev = d.iloc[i - 1]   # completed prior day only (no look-ahead)
            if pd.isna(prev["EMA50"]) or pd.isna(prev["ATR"]):
                continue
            bias = classify_daily_ema_bias(float(prev["close"]), float(prev["EMA50"]), float(prev["EMA200"]))
            stats[d.iloc[i]["date_str"]] = {"atr": float(prev["ATR"]), "bias": bias}
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
