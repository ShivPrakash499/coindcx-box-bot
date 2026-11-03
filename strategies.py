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
                     margin_inr: float, leverage: int, usd_inr: float,
                     entry2_sweep: float = 0.0) -> dict:
    """Quantity, ROE and INR projections for a 2-Entry + Runner setup (Tranche 1 at Entry + Tranche 2 at Sweep Level,
    50% TP1 Early Book + 50% TP2 Runner to opposite Box Edge)."""
    margin_usd = margin_inr / usd_inr if usd_inr else 0.0
    position_usd = margin_usd * leverage
    qty = eng.format_order_quantity(pair, position_usd / entry) if entry > 0 else 0
    tranche_qty = eng.format_order_quantity(pair, (position_usd * 0.5) / entry) if entry > 0 else 0

    if entry2_sweep <= 0 and entry > 0:
        is_long = tp1 >= entry
        entry2_sweep = eng.round_asset_price(entry * (0.99 if is_long else 1.01), entry)
    avg_entry_2x = eng.round_asset_price((entry + entry2_sweep) / 2.0, entry) if entry2_sweep > 0 else entry

    risk = abs(entry - stop) if stop > 0 else 0
    r1 = abs(entry - tp1)
    r2 = abs(entry - tp2)

    def roe(x):
        return round((x / entry) * leverage * 100, 2) if entry > 0 else 0

    # Blended Runner PnL if 50% exits at TP1 and 50% rides to TP2
    profit_tp1_full_inr = round(r1 * qty * usd_inr, 2)
    profit_tp2_full_inr = round(r2 * qty * usd_inr, 2)
    profit_blended_runner_inr = round(0.5 * profit_tp1_full_inr + 0.5 * profit_tp2_full_inr, 2)
    roe_blended_runner = round(0.5 * roe(r1) + 0.5 * roe(r2), 2)

    return {
        "crypto_qty": qty,
        "tranche_qty": tranche_qty,
        "tranche_margin_inr": round(margin_inr * 0.5, 2),
        "entry2_sweep": eng.round_asset_price(entry2_sweep, entry) if entry2_sweep > 0 else entry,
        "avg_entry_2x": avg_entry_2x,
        "position_usd": round(position_usd, 2),
        "margin_inr": margin_inr,
        "leverage": leverage,
        "usd_inr": usd_inr,
        "roe_tp1": roe(r1),
        "roe_tp2": roe(r2),
        "roe_blended": roe_blended_runner,
        "roe_sl": roe(risk),
        "profit_tp1_inr": profit_tp1_full_inr,
        "profit_tp2_inr": profit_tp2_full_inr,
        "profit_blended_inr": profit_blended_runner_inr,
        "loss_sl_inr": round(risk * qty * usd_inr, 2),
        "target_roe_met": roe(r1) >= 3.0,
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


# Dynamic 2-Entry + Runner TP1/TP2 & Sweep Scale-In Constants (at 10x default leverage; 50% Tranche 1 = 5x effective)
DEFAULT_LEVERAGE = 10         # 10x leverage per trade (50% margin on Entry 1 + 50% margin reserved for Entry 2)
MAX_TP_ROE_PCT = 10.0         # TP1 (50% Early Book) = min(2.0% price move [10% total-margin ROE], MID)
MIN_TP_ROE_PCT = 3.0          # Skip trade if TP1 distance is < 0.6% price move
MAX_SL_ROE_PCT = 5.0          # Strict 1.0% max catastrophe SL price distance (5% ROE on Entry 1's 50% margin at 10x)
MAX_TRADES_PER_DAY = 2        # Max 2 trades per coin per day
DAILY_WIN_ROE_LOCK_PCT = 10.0 # Done for the day once a trade hits >= 10% ROE


def build_two_entry_runner_plan(
    direction: str,
    entry: float,
    sweep_level: float,
    struct_tp1: float,
    struct_tp2: float,
    leverage: int = DEFAULT_LEVERAGE,
    max_tp1_roe: float = MAX_TP_ROE_PCT,
    min_tp1_roe: float = MIN_TP_ROE_PCT,
    enforce_min_tp: bool = True,
) -> dict | None:
    """
    2-Entry Sweep Scale-In + 2-Stage Runner Exit Plan (10x Leverage, 50/50 Tranche Split):
      - Entry 1 (50% Margin): Confirmed rejection close price (`entry`).
      - Entry 2 (50% Margin — Same Amount): Placed at the `SH` / `SL` / wick sweep level (`sweep_level`),
        turning stop-hunts into a 2nd fill instead of a premature stop-out.
      - Emergency Catastrophe SL (`stop_price`): Placed just beyond `Entry 2` (`SH`/`SL`) and strictly
        capped at 1.0% price move (`5% ROE` on Tranche 1's 50% margin at 10x).
      - TP1 (Close 50% / Book Early Profit + Free-Ride Runner):
        `min(struct_tp1 [MID], 2.0% price move [20% ROE on Tranche 1 / 10% ROE on Total Trade Margin])`.
      - TP2 (Hold Remaining 50% Risk-Free Runner for Big Drop):
        Opposite Box Edge (`RL`/`SL` for SHORT, `RH`/`SH` for LONG).
    """
    if entry <= 0:
        return None
    lev = max(1, int(leverage))
    eff_lev = 5.0  # 50% Tranche 1 @ 10x leverage = 5x effective leverage on total trade margin
    is_long = direction.upper() in ("LONG", "BUY")

    # 1. TP1 (Early Profit Booking on 50% of position: <= 2.0% price move or MID whichever is closer)
    struct_tp1_dist = abs(struct_tp1 - entry)
    max_tp1_dist = entry * (max_tp1_roe / 100.0 / eff_lev)
    min_tp1_dist = entry * (min_tp1_roe / 100.0 / eff_lev)
    max_sl_dist = entry * (MAX_SL_ROE_PCT / 100.0 / eff_lev)  # 1.0% structural price distance

    tp1_dist = min(struct_tp1_dist, max_tp1_dist)
    if enforce_min_tp and tp1_dist < (min_tp1_dist * 0.98):
        return None

    # 2. Entry 2 (Equal-size scale-in order at SH / SL sweep level) & Strict Catastrophe SL Cap
    if is_long:
        raw_e2 = min(sweep_level, entry * 0.996) if (0 < sweep_level < entry) else entry * 0.995
        entry2 = max(raw_e2, entry * 0.994)  # Entry 2 sits 0.4% - 0.6% below Entry 1 at SL/sweep wick
        avg_entry = (entry + entry2) / 2.0
        stop_price = max(min(entry2 * 0.995, sweep_level * 0.9955 if sweep_level > 0 else entry2 * 0.995), entry - max_sl_dist)
        tp1_price = entry + tp1_dist
        raw_tp2_dist = (struct_tp2 - entry) if struct_tp2 > tp1_price else max(tp1_dist * 2.2, entry * (22.0 / 100.0 / eff_lev))
        tp2_dist = max(raw_tp2_dist, tp1_dist * 1.6)
        tp2_price = entry + tp2_dist
    else:
        raw_e2 = max(sweep_level, entry * 1.004) if (sweep_level > entry) else entry * 1.005
        entry2 = min(raw_e2, entry * 1.006)  # Entry 2 sits 0.4% - 0.6% above Entry 1 at SH/sweep wick
        avg_entry = (entry + entry2) / 2.0
        stop_price = min(max(entry2 * 1.005, sweep_level * 1.0045 if sweep_level > 0 else entry2 * 1.005), entry + max_sl_dist)
        tp1_price = entry - tp1_dist
        raw_tp2_dist = (entry - struct_tp2) if (0 < struct_tp2 < tp1_price) else max(tp1_dist * 2.2, entry * (22.0 / 100.0 / eff_lev))
        tp2_dist = max(raw_tp2_dist, tp1_dist * 1.6)
        tp2_price = entry - tp2_dist

    tp1_roe = round((tp1_dist / entry) * lev * 100.0, 1)
    tp2_roe = round((tp2_dist / entry) * lev * 100.0, 1)
    tp1_label = f"50% Book ({tp1_roe:.0f}% ROE -> SL to BE)" if tp1_dist < struct_tp1_dist else f"50% Book MID ({tp1_roe:.1f}% ROE -> SL to BE)"
    tp2_label = f"50% Runner ({tp2_roe:.0f}% ROE Big Drop)"

    return {
        "entry": entry,
        "entry2_sweep": entry2,
        "avg_entry_2x": avg_entry,
        "stop": stop_price,
        "tp1": tp1_price,
        "tp2": tp2_price,
        "tp1_label": tp1_label,
        "tp2_label": tp2_label,
    }


def apply_dynamic_roe_tp_sl(
    direction: str,
    entry: float,
    struct_stop: float,
    struct_tp1: float,
    leverage: int = DEFAULT_LEVERAGE,
    max_tp_roe: float = MAX_TP_ROE_PCT,
    max_sl_roe: float = MAX_SL_ROE_PCT,
    min_tp_roe: float = MIN_TP_ROE_PCT,
    enforce_min_tp: bool = True,
    struct_tp2: float = 0.0,
) -> tuple[float, float, str] | None:
    """
    Backwards-compatible wrapper returning (stop_price, tp1_price, tp1_label) from build_two_entry_runner_plan.
    """
    plan = build_two_entry_runner_plan(
        direction=direction,
        entry=entry,
        sweep_level=struct_stop,
        struct_tp1=struct_tp1,
        struct_tp2=struct_tp2,
        leverage=leverage,
        max_tp1_roe=max_tp_roe,
        min_tp1_roe=min_tp_roe,
        enforce_min_tp=enforce_min_tp,
    )
    if not plan:
        return None
    return plan["stop"], plan["tp1"], plan["tp1_label"]


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

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
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
    tp1_name, tp2_name = "TP1 (50% Book <=10% ROE / MID)", "TP2 (50% Runner to RL/RH)"
    uses_live_price = True

    def compute_levels(self, pair):
        return eng.calculate_daily_box_levels(pair)

    @staticmethod
    def _reason(sig: dict) -> str:
        return sig.get("trigger_reason", "")

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
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

        bias_label = (
            f"Daily Bearish (<50 EMA ${daily_ema50:,.2f} & <200 EMA ${daily_ema200:,.2f})" if trend_bias == "BEARISH"
            else (
                f"Daily Bullish (>50 EMA ${daily_ema50:,.2f} & >200 EMA ${daily_ema200:,.2f})" if trend_bias == "BULLISH"
                else f"Daily Range Mode (Between 50 EMA ${daily_ema50:,.2f} & 200 EMA ${daily_ema200:,.2f})"
            )
        )
        out["daily_trend_summary"] = bias_label

        recent_15m = recs_15m[-3:]

        # ------------------------------------------------------------------
        # 1. SHORT SETUPS:
        #    - Outer Box RH or SH Liquidity Sweep + Rejection (active in all regimes; tagged with Daily Bias)
        #    - Daily 50 EMA Touch + Next-Candle Rejection (strictly when Daily Bias == BEARISH)
        # ------------------------------------------------------------------
        swept_rh_prior = any(float(r["high"]) >= rh or float(r["open"]) >= rh for r in recent_15m)
        swept_rh_curr15 = (c15_high >= rh) or (float(prev_c15["high"]) >= rh)
        rejected_rh_5m = swept_rh_prior and (c5_close < rh) and (c5_close <= c5_open or c5_close < prev_c5_close)
        rejected_rh_15m = swept_rh_curr15 and (c15_close < rh) and (c15_close <= c15_open or c15_close < prev_c15_close)

        swept_sh_prior = any(float(r["high"]) >= sh or float(r["open"]) >= sh for r in recent_15m)
        swept_sh_curr15 = (c15_high >= sh) or (float(prev_c15["high"]) >= sh)
        rejected_sh_5m = swept_sh_prior and (c5_close < sh) and (c5_close <= c5_open or c5_close < prev_c5_close)
        rejected_sh_15m = swept_sh_curr15 and (c15_close < sh) and (c15_close <= c15_open or c15_close < prev_c15_close)

        if rejected_rh_5m or rejected_rh_15m or rejected_sh_5m or rejected_sh_15m:
            use_5m = rejected_rh_5m or rejected_sh_5m
            raw_entry = c5_close if use_5m else c15_close
            entry = eng.round_asset_price(raw_entry, rh)
            sweep_high = max(float(r["high"]) for r in recent_15m)
            scale_in_lvl = max(sh, sweep_high, entry * 1.008)
            struct_tp1 = mid if entry > mid else rl
            struct_tp2 = rl if entry > rl * 1.012 else sl
            plan = build_two_entry_runner_plan("SHORT", entry, scale_in_lvl, struct_tp1, struct_tp2, leverage)
            if plan:
                stop = eng.round_asset_price(plan["stop"], rh)
                tp1 = eng.round_asset_price(plan["tp1"], rh)
                tp2 = eng.round_asset_price(plan["tp2"], rh)
                entry2 = eng.round_asset_price(plan["entry2_sweep"], rh)
                tf_lbl = "5m" if use_5m else "15m"
                lvl_tag = f"SH (${sh:,.2f})" if (rejected_sh_5m or rejected_sh_15m) else f"RH (${rh:,.2f})"
                reason = (
                    f"{bias_label} | Swept {lvl_tag} + {tf_lbl} rejection "
                    f"(Entry1 ${entry:,.2f} + Entry2 @ Sweep ${entry2:,.2f} | {plan['tp1_label']} & {plan['tp2_label']})"
                )
                out.update({
                    "signal": "SHORT", "signal_kind": "REVERSAL", "trigger_zone": "Sell Zone RH-SH",
                    "trigger_reason": reason,
                    "setup": f"SELL (Short): {lvl_tag} Sweep + 2-Entry Runner ({session['name']})",
                    "entry": entry, "entry2_sweep": entry2, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                    "candle_ts": int(c5["timestamp"] if use_5m else c15["timestamp"]),
                })
                out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr, entry2_sweep=entry2))
                return self._stamp(out)

        if trend_bias == "BEARISH":
            min_short_zone = rl + 0.35 * (rh - rl)
            touched_daily_ema50 = (
                (daily_close < daily_ema50)
                and any(float(r["high"]) >= daily_ema50 * 0.999 and float(r["low"]) <= daily_ema50 * 1.005 for r in recent_15m)
                and c5_close >= min_short_zone
            )
            rejected_d_ema50 = (
                touched_daily_ema50
                and (c5_close < daily_ema50)
                and (c5_close < c5_open)
                and (c5_close < prev_c5_close)
            )
            if rejected_d_ema50:
                entry = eng.round_asset_price(c5_close, rh)
                sweep_high = max(float(prev_c15["high"]), c15_high, c5_high, daily_ema50)
                struct_tp1 = mid if entry > mid else rl
                struct_tp2 = rl if entry > rl * 1.012 else sl
                plan = build_two_entry_runner_plan("SHORT", entry, max(sweep_high, sh), struct_tp1, struct_tp2, leverage)
                if plan:
                    stop = eng.round_asset_price(plan["stop"], rh)
                    tp1 = eng.round_asset_price(plan["tp1"], rh)
                    tp2 = eng.round_asset_price(plan["tp2"], rh)
                    entry2 = eng.round_asset_price(plan["entry2_sweep"], rh)
                    if stop > entry > tp1:
                        reason = (
                            f"{bias_label} | Touched Daily 50 EMA (${daily_ema50:,.2f}) + next-candle "
                            f"bearish rejection (Entry1 ${entry:,.2f} + Entry2 @ Sweep ${entry2:,.2f} | {plan['tp1_label']} & {plan['tp2_label']})"
                        )
                        out.update({
                            "signal": "SHORT", "signal_kind": "EMA50_REJECTION", "trigger_zone": "Daily 50 EMA Resistance",
                            "trigger_reason": reason,
                            "setup": f"SELL (Short): Daily 50 EMA Touch + 2-Entry Runner ({session['name']})",
                            "entry": entry, "entry2_sweep": entry2, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                            "candle_ts": int(c5["timestamp"]),
                        })
                        out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr, entry2_sweep=entry2))
                        return self._stamp(out)

        # ------------------------------------------------------------------
        # 2. LONG SETUPS:
        #    - Outer Box RL or SL Liquidity Sweep + Rejection (active in all regimes; tagged with Daily Bias)
        #    - Daily 50 EMA Touch + Next-Candle Rejection (strictly when Daily Bias == BULLISH)
        # ------------------------------------------------------------------
        swept_rl_prior = any(float(r["low"]) <= rl or float(r["open"]) <= rl for r in recent_15m)
        swept_rl_curr15 = (c15_low <= rl) or (float(prev_c15["low"]) <= rl)
        rejected_rl_5m = swept_rl_prior and (c5_close > rl) and (c5_close >= c5_open or c5_close > prev_c5_close)
        rejected_rl_15m = swept_rl_curr15 and (c15_close > rl) and (c15_close >= c15_open or c15_close > prev_c15_close)

        swept_sl_prior = any(float(r["low"]) <= sl or float(r["open"]) <= sl for r in recent_15m)
        swept_sl_curr15 = (c15_low <= sl) or (float(prev_c15["low"]) <= sl)
        rejected_sl_5m = swept_sl_prior and (c5_close > sl) and (c5_close >= c5_open or c5_close > prev_c5_close)
        rejected_sl_15m = swept_sl_curr15 and (c15_close > sl) and (c15_close >= c15_open or c15_close > prev_c15_close)

        if rejected_rl_5m or rejected_rl_15m or rejected_sl_5m or rejected_sl_15m:
            use_5m = rejected_rl_5m or rejected_sl_5m
            raw_entry = c5_close if use_5m else c15_close
            entry = eng.round_asset_price(raw_entry, rl)
            sweep_low = min(float(r["low"]) for r in recent_15m)
            scale_in_lvl = min(sl, sweep_low, entry * 0.992)
            struct_tp1 = mid if entry < mid else rh
            struct_tp2 = rh if entry < rh * 0.988 else sh
            plan = build_two_entry_runner_plan("LONG", entry, scale_in_lvl, struct_tp1, struct_tp2, leverage)
            if plan:
                stop = eng.round_asset_price(plan["stop"], rl)
                tp1 = eng.round_asset_price(plan["tp1"], rl)
                tp2 = eng.round_asset_price(plan["tp2"], rl)
                entry2 = eng.round_asset_price(plan["entry2_sweep"], rl)
                tf_lbl = "5m" if use_5m else "15m"
                lvl_tag = f"SL (${sl:,.2f})" if (rejected_sl_5m or rejected_sl_15m) else f"RL (${rl:,.2f})"
                reason = (
                    f"{bias_label} | Swept {lvl_tag} + {tf_lbl} rejection "
                    f"(Entry1 ${entry:,.2f} + Entry2 @ Sweep ${entry2:,.2f} | {plan['tp1_label']} & {plan['tp2_label']})"
                )
                out.update({
                    "signal": "LONG", "signal_kind": "REVERSAL", "trigger_zone": "Buy Zone RL-SL",
                    "trigger_reason": reason,
                    "setup": f"BUY (Long): {lvl_tag} Sweep + 2-Entry Runner ({session['name']})",
                    "entry": entry, "entry2_sweep": entry2, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                    "candle_ts": int(c5["timestamp"] if use_5m else c15["timestamp"]),
                })
                out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr, entry2_sweep=entry2))
                return self._stamp(out)

        if trend_bias == "BULLISH":
            max_long_zone = rh - 0.35 * (rh - rl)
            touched_daily_ema50 = (
                (daily_close > daily_ema50)
                and any(float(r["low"]) <= daily_ema50 * 1.001 and float(r["high"]) >= daily_ema50 * 0.995 for r in recent_15m)
                and c5_close <= max_long_zone
            )
            rejected_d_ema50 = (
                touched_daily_ema50
                and (c5_close > daily_ema50)
                and (c5_close > c5_open)
                and (c5_close > prev_c5_close)
            )
            if rejected_d_ema50:
                entry = eng.round_asset_price(c5_close, rl)
                sweep_low = min(float(prev_c15["low"]), c15_low, c5_low, daily_ema50)
                struct_tp1 = mid if entry < mid else rh
                struct_tp2 = rh if entry < rh * 0.988 else sh
                plan = build_two_entry_runner_plan("LONG", entry, min(sweep_low, sl), struct_tp1, struct_tp2, leverage)
                if plan:
                    stop = eng.round_asset_price(plan["stop"], rl)
                    tp1 = eng.round_asset_price(plan["tp1"], rl)
                    tp2 = eng.round_asset_price(plan["tp2"], rl)
                    entry2 = eng.round_asset_price(plan["entry2_sweep"], rl)
                    if stop < entry < tp1:
                        reason = (
                            f"{bias_label} | Touched Daily 50 EMA (${daily_ema50:,.2f}) + next-candle "
                            f"bullish rejection (Entry1 ${entry:,.2f} + Entry2 @ Sweep ${entry2:,.2f} | {plan['tp1_label']} & {plan['tp2_label']})"
                        )
                        out.update({
                            "signal": "LONG", "signal_kind": "EMA50_REJECTION", "trigger_zone": "Daily 50 EMA Support",
                            "trigger_reason": reason,
                            "setup": f"BUY (Long): Daily 50 EMA Touch + 2-Entry Runner ({session['name']})",
                            "entry": entry, "entry2_sweep": entry2, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                            "candle_ts": int(c5["timestamp"]),
                        })
                        out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr, entry2_sweep=entry2))
                        return self._stamp(out)

        out["setup"] = (
            f"WAIT / WATCHING ZONES ({bias_label} — "
            f"watching Buy Zone RL ${rl:,.2f} / SL ${sl:,.2f} & Sell Zone RH ${rh:,.2f} / SH ${sh:,.2f} for rejection)"
        )
        out["trigger_reason"] = f"{bias_label}: Watching RL/SL Buy Zone and RH/SH Sell Zone for sweep + rejection"
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
            b["trigger_reason"] = f"Planned ({trend_bias}): Entry1 @ RL/SL + Entry2 @ SL (${levels.get('SL', 0):,.2f}) | TP1 50% Book -> TP2 Runner to RH"
        if s:
            s["trigger_reason"] = f"Planned ({trend_bias}): Entry1 @ RH/SH + Entry2 @ SH (${levels.get('SH', 0):,.2f}) | TP1 50% Book -> TP2 Runner to RL"

        if sig and sig.get("signal") == "LONG":
            return {"BUY": self._stamp({**sig, "direction": "BUY"}), "SELL": self._stamp(s),
                    "note": f"⚡ Live confirmed LONG signal: {sig.get('trigger_reason')}"}
        if sig and sig.get("signal") == "SHORT":
            return {"BUY": self._stamp(b), "SELL": self._stamp({**sig, "direction": "SELL"}),
                    "note": f"⚡ Live confirmed SHORT signal: {sig.get('trigger_reason')}"}

        if trend_bias == "BEARISH":
            note_txt = f"🔴 Daily Trend Bias is BEARISH (< 50 EMA ${levels.get('EMA50', 0):,.2f} & 200 EMA ${levels.get('EMA200', 0):,.2f}) — Primary Short bias (2-Entry Runner armed on both RH/SH & RL/SL)."
        elif trend_bias == "BULLISH":
            note_txt = f"🟢 Daily Trend Bias is BULLISH (> 50 EMA ${levels.get('EMA50', 0):,.2f} & 200 EMA ${levels.get('EMA200', 0):,.2f}) — Primary Long bias (2-Entry Runner armed on both RL/SL & RH/SH)."
        else:
            note_txt = f"🟡 Daily Range Mode: Price (${levels.get('daily_close', 0):,.2f}) is between 50 EMA (${levels.get('EMA50', 0):,.2f}) and 200 EMA (${levels.get('EMA200', 0):,.2f}) — Both Box Edges Active."
        return {
            "BUY": self._stamp(b),
            "SELL": self._stamp(s),
            "note": note_txt,
        }

    def chart_lines(self, levels, plan=None):
        if not levels:
            return []
        lines = [
            {"label": "SH (Swing High / Short Entry 2)", "price": levels["SH"], "color": "#ef4444", "dash": "dash"},
            {"label": "RH / PDH (Short Entry 1)", "price": levels["RH"], "color": "#ea580c", "dash": "solid"},
            {"label": "MID (50% / TP1 Zone)", "price": levels["MID"], "color": "#0284c7", "dash": "dot"},
            {"label": "RL / PDL (Long Entry 1)", "price": levels["RL"], "color": "#16a34a", "dash": "solid"},
            {"label": "SL (Swing Low / Long Entry 2)", "price": levels["SL"], "color": "#10b981", "dash": "dash"},
        ]
        if "EMA50" in levels:
            lines.append({"label": "Daily 50 EMA", "price": levels["EMA50"], "color": "#8b5cf6", "dash": "dash"})
        if "EMA200" in levels:
            lines.append({"label": "Daily 200 EMA", "price": levels["EMA200"], "color": "#f59e0b", "dash": "dash"})
        return lines

    # ---- backtest: Daily 50 & 200 EMA Bias + Box RH/SH/RL/SL or 50 EMA Touch + 2-Entry Runner ----
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

        tag = (
            "Daily <50/200 EMA" if bias == "BEARISH"
            else ("Daily >50/200 EMA" if bias == "BULLISH" else "Daily Range (Between 50/200 EMA)")
        )

        # 1. SHORT SETUPS:
        #    - In BEARISH or NEUTRAL (Range) bias: RH or SH Sweep + Next-Candle Bearish Confirmation
        #    - In BULLISH bias: only take counter-trend Short when outer SH Swing High is swept with bearish engulfing close (< prev low)
        upper_wick = c_high - max(c_open, c_close)
        has_bear_confirm = (c_close < c_open and c_close < p_close) or (
            c_close < c_open and candle_range > 0 and (upper_wick / candle_range) >= 0.30
        )
        swept_rh_seq = (p_high >= rh or c_high >= rh) and (c_close < rh) and (max(p_high, c_high) <= sh * 1.005)
        swept_sh_seq = (p_high >= sh or c_high >= sh) and (c_close < sh) and (max(p_high, c_high) <= sh * 1.012)

        swept_rh_rej = (bias in ("BEARISH", "NEUTRAL")) and swept_rh_seq and has_bear_confirm
        swept_sh_rej = (
            (bias in ("BEARISH", "NEUTRAL") or (c_close < c_open and c_close < p_low))
            and swept_sh_seq
            and has_bear_confirm
        )

        if swept_rh_rej or swept_sh_rej:
            scale_in_lvl = max(sh, p_high, c_high)
            struct_tp1 = mid if c_close > mid else rl
            struct_tp2 = rl if c_close > rl * 1.012 else sl
            plan = build_two_entry_runner_plan("SHORT", c_close, scale_in_lvl, struct_tp1, struct_tp2, leverage=DEFAULT_LEVERAGE)
            if plan:
                z_lbl = "Swept SH Swing High" if swept_sh_rej else "Swept RH Sell Zone"
                return {
                    "direction": "SHORT", "entry": c_close, "entry2_sweep": plan["entry2_sweep"],
                    "stop": plan["stop"], "tp1": plan["tp1"], "tp2": plan["tp2"],
                    "tp1_label": plan["tp1_label"], "tp2_label": plan["tp2_label"],
                    "reason": f"{tag} + {z_lbl}"
                }

        if bias == "BEARISH":
            min_short_zone = rl + 0.35 * (rh - rl)
            touched_d_ema50 = (p_high >= daily_ema50 * 0.9995) and (p_low <= daily_ema50 * 1.005)
            if touched_d_ema50 and (c_close < daily_ema50) and (c_close < c_open) and (c_close < p_close) and (c_close >= min_short_zone):
                sweep_hi = max(p_high, c_high, daily_ema50, sh)
                struct_tp1 = mid if c_close > mid else rl
                struct_tp2 = rl if c_close > rl * 1.012 else sl
                plan = build_two_entry_runner_plan("SHORT", c_close, sweep_hi, struct_tp1, struct_tp2, leverage=DEFAULT_LEVERAGE)
                if plan and plan["stop"] > c_close > plan["tp1"]:
                    return {
                        "direction": "SHORT", "entry": c_close, "entry2_sweep": plan["entry2_sweep"],
                        "stop": plan["stop"], "tp1": plan["tp1"], "tp2": plan["tp2"],
                        "tp1_label": plan["tp1_label"], "tp2_label": plan["tp2_label"],
                        "reason": "Daily <50/200 EMA + Daily 50 EMA Rejection"
                    }

        # 2. LONG SETUPS:
        #    - In BULLISH or NEUTRAL (Range) bias: RL or SL Sweep + Next-Candle Bullish Confirmation
        #    - In BEARISH bias: only take counter-trend Long when outer SL Swing Low is swept with bullish engulfing close (> prev high)
        lower_wick = min(c_open, c_close) - c_low
        has_bull_confirm = (c_close > c_open and c_close > p_close) or (
            c_close > c_open and candle_range > 0 and (lower_wick / candle_range) >= 0.30
        )
        swept_rl_seq = (p_low <= rl or c_low <= rl) and (c_close > rl) and (min(p_low, c_low) >= sl * 0.995)
        swept_sl_seq = (p_low <= sl or c_low <= sl) and (c_close > sl) and (min(p_low, c_low) >= sl * 0.988)

        swept_rl_rej = (bias in ("BULLISH", "NEUTRAL")) and swept_rl_seq and has_bull_confirm
        swept_sl_rej = (
            (bias in ("BULLISH", "NEUTRAL") or (c_close > c_open and c_close > p_high))
            and swept_sl_seq
            and has_bull_confirm
        )

        if swept_rl_rej or swept_sl_rej:
            scale_in_lvl = min(sl, p_low, c_low)
            struct_tp1 = mid if c_close < mid else rh
            struct_tp2 = rh if c_close < rh * 0.988 else sh
            plan = build_two_entry_runner_plan("LONG", c_close, scale_in_lvl, struct_tp1, struct_tp2, leverage=DEFAULT_LEVERAGE)
            if plan:
                z_lbl = "Swept SL Swing Low" if swept_sl_rej else "Swept RL Buy Zone"
                return {
                    "direction": "LONG", "entry": c_close, "entry2_sweep": plan["entry2_sweep"],
                    "stop": plan["stop"], "tp1": plan["tp1"], "tp2": plan["tp2"],
                    "tp1_label": plan["tp1_label"], "tp2_label": plan["tp2_label"],
                    "reason": f"{tag} + {z_lbl}"
                }

        if bias == "BULLISH":
            max_long_zone = rh - 0.35 * (rh - rl)
            touched_d_ema50 = (p_low <= daily_ema50 * 1.0005) and (p_high >= daily_ema50 * 0.995)
            if touched_d_ema50 and (c_close > daily_ema50) and (c_close > c_open) and (c_close > p_close) and (c_close <= max_long_zone):
                sweep_lo = min(p_low, c_low, daily_ema50, sl)
                struct_tp1 = mid if c_close < mid else rh
                struct_tp2 = rh if c_close < rh * 0.988 else sh
                plan = build_two_entry_runner_plan("LONG", c_close, sweep_lo, struct_tp1, struct_tp2, leverage=DEFAULT_LEVERAGE)
                if plan and plan["stop"] < c_close < plan["tp1"]:
                    return {
                        "direction": "LONG", "entry": c_close, "entry2_sweep": plan["entry2_sweep"],
                        "stop": plan["stop"], "tp1": plan["tp1"], "tp2": plan["tp2"],
                        "tp1_label": plan["tp1_label"], "tp2_label": plan["tp2_label"],
                        "reason": "Daily >50/200 EMA + Daily 50 EMA Rejection"
                    }

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

    plan = build_two_entry_runner_plan(direction, entry, extreme, struct_tp1, origin, leverage=DEFAULT_LEVERAGE)
    if not plan:
        return None
    return {
        "direction": direction, "entry": entry, "entry2_sweep": plan["entry2_sweep"],
        "stop": plan["stop"], "tp1": plan["tp1"], "tp2": plan["tp2"],
        "tp1_label": plan["tp1_label"], "tp2_label": plan["tp2_label"],
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

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
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
                    origin = flush["high"]
                    struct_stop = extreme * (1 - SL_BUFFER)
                    struct_tp1 = extreme + 0.5 * (origin - extreme)
                    valid_rr = struct_stop < entry < struct_tp1
                    side_txt = "above 50 & 200 EMA"
                    crossover_info = f"close ${entry:,.2f} > prev 5m red high ${float(prev5['high']):,.2f}"
                else:
                    extreme = flush["high"]
                    origin = flush["low"]
                    struct_stop = extreme * (1 + SL_BUFFER)
                    struct_tp1 = extreme - 0.5 * (extreme - origin)
                    valid_rr = struct_tp1 < entry < struct_stop
                    side_txt = "below 50 & 200 EMA"
                    crossover_info = f"close ${entry:,.2f} < prev 5m green low ${float(prev5['low']):,.2f}"

                plan = build_two_entry_runner_plan(direction, entry, extreme, struct_tp1, origin, leverage) if valid_rr else None
                if plan:
                    stop, tp1, tp2, entry2 = plan["stop"], plan["tp1"], plan["tp2"], plan["entry2_sweep"]
                    word = "BUY (Long)" if direction == "LONG" else "SELL (Short)"
                    reason = (
                        f"15m {move} = {flush['pct_atr']:.0f}% ATR confirmed by 5m crossover "
                        f"({crossover_info} | {plan['tp1_label']} & {plan['tp2_label']}) {side_txt}"
                    )
                    out.update({
                        "signal": direction, "signal_kind": "ATR_REVERSAL",
                        "trigger_zone": "Bullish flush above 50/200 EMA" if direction == "LONG" else "Bearish spike below 50/200 EMA",
                        "trigger_reason": reason, "setup": f"{word}: 15m {move} + 5m Crossover Confirmation - {reason}",
                        "entry": eng.round_asset_price(entry, entry),
                        "entry2_sweep": eng.round_asset_price(entry2, entry),
                        "stop_loss": eng.round_asset_price(stop, entry),
                        "tp1": eng.round_asset_price(tp1, entry),
                        "tp2": eng.round_asset_price(tp2, entry),
                        "flush": flush,
                    })
                    out.update(position_metrics(pair, out["entry"], out["stop_loss"], out["tp1"], out["tp2"], margin_inr, leverage, usd_inr, entry2_sweep=out["entry2_sweep"]))
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
