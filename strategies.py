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

import numpy as np
import pandas as pd

import coindcx_engine as eng

IST = eng.IST


# ----------------------------------------------------------------------------------------------
# Shared helpers
# ----------------------------------------------------------------------------------------------
def position_metrics(pair: str, entry: float, stop: float, tp1: float, tp2: float,
                     margin_inr: float, leverage: int, usd_inr: float,
                     entry2_sweep: float | None = 0.0) -> dict:
    """Quantity, ROE and INR projections for a Single-Entry (100% Slot) or 2-Entry + Runner setup."""
    margin_usd = margin_inr / usd_inr if usd_inr else 0.0
    position_usd = margin_usd * leverage
    qty = eng.format_order_quantity(pair, position_usd / entry) if entry > 0 else 0

    entry2_val = float(entry2_sweep or 0.0)
    has_entry2 = entry2_val > 0.0
    tranche_qty = (
        eng.format_order_quantity(pair, (position_usd * 0.5) / entry)
        if (entry > 0 and has_entry2)
        else qty
    )
    tranche_margin_inr = round(margin_inr * 0.5, 2) if has_entry2 else round(margin_inr, 2)
    avg_entry_2x = eng.round_asset_price((entry + entry2_val) / 2.0, entry) if has_entry2 else entry

    risk = abs(entry - stop) if stop > 0 else 0
    r1 = abs(entry - tp1)
    r2 = abs(entry - tp2)

    def roe(x):
        return round((x / entry) * leverage * 100, 2) if entry > 0 else 0

    # Blended Runner PnL if 50% exits at TP1 and 50% rides to TP2 / Trailing SL
    profit_tp1_full_inr = round(r1 * qty * usd_inr, 2)
    profit_tp2_full_inr = round(r2 * qty * usd_inr, 2)
    profit_blended_runner_inr = round(0.5 * profit_tp1_full_inr + 0.5 * profit_tp2_full_inr, 2)
    roe_blended_runner = round(0.5 * roe(r1) + 0.5 * roe(r2), 2)

    return {
        "crypto_qty": qty,
        "tranche_qty": tranche_qty,
        "tranche_margin_inr": tranche_margin_inr,
        "entry2_sweep": eng.round_asset_price(entry2_val, entry) if has_entry2 else 0.0,
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
    """Session bucket used in backtest reports."""
    h, m = c_time.hour, c_time.minute
    if (h == 7) or (h == 8 and m <= 30):
        return "🌅 Asia Open"
    if (h == 13) or (h == 14 and m <= 30):
        return "🏛️ London Open"
    if (h == 18 and m >= 45) or (h == 19) or (h == 20 and m <= 15):
        return "⚡ New York Open"
    return "🌐 Intraday Monitor"


def _add_box_v2_15m_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Adds Wilder 15m ATR(14), 20-period volume SMA, and IST `date_str` (if timestamp present) for Box Sweep v2."""
    if df is None or df.empty:
        return df
    out = df
    if {"high", "low", "close"}.issubset(out.columns):
        _hi = out["high"].to_numpy(dtype=float)
        _lo = out["low"].to_numpy(dtype=float)
        _cl = out["close"].to_numpy(dtype=float)
        _pc = np.empty_like(_cl)
        _pc[0] = _cl[0]
        _pc[1:] = _cl[:-1]
        _tr = np.maximum(_hi - _lo, np.maximum(np.abs(_hi - _pc), np.abs(_lo - _pc)))
        out["ATR14"] = pd.Series(_tr, index=out.index).ewm(alpha=1.0 / 14.0, adjust=False, min_periods=1).mean()
    if "volume" in out.columns:
        out["VOL_SMA20"] = out["volume"].rolling(20, min_periods=5).mean()
    if "timestamp" in out.columns and "date_str" not in out.columns:
        try:
            out["date_str"] = (
                pd.to_datetime(out["timestamp"], unit="ms")
                .dt.tz_localize("UTC")
                .dt.tz_convert(IST)
                .dt.strftime("%Y-%m-%d")
            )
        except Exception:
            pass
    return out


def _closed_15m(pair: str, limit: int) -> pd.DataFrame:
    fetch_limit = max(int(limit) + 5, 650)
    df = eng.fetch_coindcx_candles(pair=pair, interval="15m", limit=fetch_limit, sync_live_price=False)
    if df.empty:
        return df
    now_ms = int(time.time() * 1000)
    closed = df[df["timestamp"] + 900000 <= now_ms].reset_index(drop=True)
    if closed.empty:
        closed = df.iloc[:-1].reset_index(drop=True)
    if not closed.empty:
        closed["EMA9"] = closed["close"].ewm(span=9, adjust=False).mean()
        closed["EMA50"] = closed["close"].ewm(span=50, adjust=False).mean()
        closed["EMA200"] = closed["close"].ewm(span=200, adjust=False).mean()
        closed = _add_box_v2_15m_indicators(closed)
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
        closed["EMA9"] = closed["close"].ewm(span=9, adjust=False).mean()
        closed["EMA50"] = closed["close"].ewm(span=50, adjust=False).mean()
        closed["EMA200"] = closed["close"].ewm(span=200, adjust=False).mean()
    return closed.iloc[-limit:].reset_index(drop=True) if len(closed) > limit else closed


def classify_daily_ema_bias(close_val: float, ema50_val: float, ema200_val: float) -> str:
    """
    Strict Daily Trend Bias Rule:
      - Daily Close < 50 EMA AND Daily Close < 200 EMA -> BEARISH (SHORT setups only in Box Strategy)
      - Daily Close > 50 EMA AND Daily Close > 200 EMA -> BULLISH (LONG setups only in Box Strategy)
      - Otherwise (price between 50 EMA and 200 EMA)   -> NEUTRAL (Both outer Box edges active)
    """
    if close_val < ema50_val and close_val < ema200_val:
        return "BEARISH"
    if close_val > ema50_val and close_val > ema200_val:
        return "BULLISH"
    return "NEUTRAL"


# Dynamic 2-Entry + Runner TP1/TP2 & Discipline Constants
DEFAULT_LEVERAGE = 10               # 10x leverage per trade
MAX_TP_ROE_PCT = 10.0               # TP1 (50% Early Book) = min(2.0% price move [10% total-margin ROE], nearer of MID / 15m 50 EMA)
MIN_TP_ROE_PCT = 3.0                # Skip trade if TP1 distance is < 0.6% price move
MAX_SL_ROE_PCT = 5.0                # Legacy constant (not enforced): Box catastrophe SL = 0.5% beyond Entry 2 (SH/SL),
                                    # i.e. typically 1.3%-5% from Entry 1 depending on how far the sweep level is
DAILY_WALLET_LOSS_STOP_PCT = 5.0    # STOP trading for the day if 5% of total futures wallet is lost including fees
MAX_TRADES_PER_DAY = 999            # Legacy trade-count cap removed per discipline update
DAILY_WIN_ROE_LOCK_PCT = 9999.0     # Legacy daily win-lock removed per discipline update


def _nearest_box_tp1(
    direction: str,
    entry: float,
    mid: float,
    ema50_15m: float,
    fallback_edge: float,
) -> tuple[float, str]:
    """
    Strategy 1 Rule: Keep TP1 at the Midpoint between `Entry 1` and `TP2` (`(entry + TP2) / 2`)
    or `15m 50 EMA`, whichever is NEARER to `entry` in the profitable direction (requiring at least
    the minimum valid distance so `15m 50 EMA` is never selected when sitting right next to a mid-box entry).
    """
    is_long = direction.upper() in ("LONG", "BUY")
    min_dist = entry * 0.0059
    if is_long:
        tp2_ref = fallback_edge if (fallback_edge > entry * 1.008) else (mid if mid > entry * 1.012 else entry * 1.024)
        tp_mid = (entry + tp2_ref) / 2.0
        mid_lbl = "MID" if (mid > 0 and abs(tp_mid - mid) / max(1e-9, entry) <= 0.002) else "Mid(Entry1,TP2)"
        min_ema_dist = max(entry * 0.008, abs(tp_mid - entry) * 0.50)

        valid_cands = []
        if tp_mid > entry and (tp_mid - entry) >= min_dist:
            valid_cands.append((tp_mid - entry, tp_mid, mid_lbl))
        if ema50_15m > entry and (ema50_15m - entry) >= max(min_dist, min_ema_dist):
            valid_cands.append((ema50_15m - entry, ema50_15m, "15m 50 EMA"))

        if valid_cands:
            _, best_px, best_lbl = min(valid_cands, key=lambda c: c[0])
            return best_px, best_lbl
        if tp_mid > entry:
            return tp_mid, mid_lbl
        if fallback_edge > entry and (fallback_edge - entry) >= min_dist:
            return (entry + fallback_edge) / 2.0, mid_lbl
        return entry * 1.012, mid_lbl
    else:
        tp2_ref = fallback_edge if (0 < fallback_edge < entry * 0.992) else (mid if 0 < mid < entry * 0.988 else entry * 0.976)
        tp_mid = (entry + tp2_ref) / 2.0
        mid_lbl = "MID" if (mid > 0 and abs(tp_mid - mid) / max(1e-9, entry) <= 0.002) else "Mid(Entry1,TP2)"
        min_ema_dist = max(entry * 0.008, abs(entry - tp_mid) * 0.50)

        valid_cands = []
        if 0 < tp_mid < entry and (entry - tp_mid) >= min_dist:
            valid_cands.append((entry - tp_mid, tp_mid, mid_lbl))
        if 0 < ema50_15m < entry and (entry - ema50_15m) >= max(min_dist, min_ema_dist):
            valid_cands.append((entry - ema50_15m, ema50_15m, "15m 50 EMA"))

        if valid_cands:
            _, best_px, best_lbl = min(valid_cands, key=lambda c: c[0])
            return best_px, best_lbl
        if 0 < tp_mid < entry:
            return tp_mid, mid_lbl
        if 0 < fallback_edge < entry and (entry - fallback_edge) >= min_dist:
            return (entry + fallback_edge) / 2.0, mid_lbl
        return entry * 0.988, mid_lbl


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
    tp1_ref_name: str = "MID",
    include_entry2: bool = False,
) -> dict | None:
    """
    100% Single-Slot Maker Limit Entry + Structural Runner Plan (10x Leverage for Box Strategy):
      - Entry 1 (100% Slot Margin): Confirmed 15m rejection close price (`entry`) placed as Maker Limit.
      - Entry 2 Removed (`entry2_sweep = 0.0` by default): Eliminates doubling into failed breakouts.
      - Emergency Catastrophe SL (`stop_price`): Placed 0.5% beyond the `SH` / `SL` / wick `sweep_level`
        so genuine liquidity sweeps inside `[RH, SH]` / `[SL, RL]` have structural room to reverse.
      - TP1 (Close 50% / Book Early Profit): Nearer of `MID` or `15m 50 EMA` (capped at 2.0% price move),
        ratcheting SL into guaranteed profit (`compute_tp1_profit_lock_sl`).
      - Remaining 50% Structural Runner: Holds with Profit-Locked SL -> Halfway Ratchet to TP1 -> Fixed `TP2`
        (no premature 5m 9 EMA cross choke).
    """
    if entry <= 0:
        return None
    lev = max(1, int(leverage))
    eff_lev = 5.0  # Preserves proven 0.6% min / 2.0% max TP1 structural distance geometry
    is_long = direction.upper() in ("LONG", "BUY")

    struct_tp1_dist = abs(struct_tp1 - entry)
    max_tp1_dist = entry * (max_tp1_roe / 100.0 / eff_lev)
    min_tp1_dist = entry * (min_tp1_roe / 100.0 / eff_lev)

    tp1_dist = min(struct_tp1_dist, max_tp1_dist)
    if enforce_min_tp and tp1_dist < (min_tp1_dist * 0.98):
        return None

    if is_long:
        sweep_anchor = min(sweep_level, entry * 0.992) if (0 < sweep_level < entry) else entry * 0.992
        stop_price = min(sweep_anchor * 0.995, sweep_level * 0.995 if sweep_level > 0 else sweep_anchor * 0.995)
        tp1_price = entry + tp1_dist
        raw_tp2_dist = (struct_tp2 - entry) if struct_tp2 > tp1_price else max(tp1_dist * 2.2, entry * (22.0 / 100.0 / eff_lev))
        tp2_dist = max(raw_tp2_dist, tp1_dist * 1.6)
        tp2_price = entry + tp2_dist
    else:
        sweep_anchor = max(sweep_level, entry * 1.008) if (sweep_level > entry) else entry * 1.008
        stop_price = max(sweep_anchor * 1.005, sweep_level * 1.005 if sweep_level > 0 else sweep_anchor * 1.005)
        tp1_price = entry - tp1_dist
        raw_tp2_dist = (entry - struct_tp2) if (0 < struct_tp2 < tp1_price) else max(tp1_dist * 2.2, entry * (22.0 / 100.0 / eff_lev))
        tp2_dist = max(raw_tp2_dist, tp1_dist * 1.6)
        tp2_price = entry - tp2_dist

    entry2 = sweep_anchor if include_entry2 else 0.0
    avg_entry = ((entry + entry2) / 2.0) if include_entry2 else entry

    tp1_roe = round((tp1_dist / entry) * lev * 100.0, 1)
    tp2_roe = round((tp2_dist / entry) * lev * 100.0, 1)
    tp1_label = (
        f"50% Book ({tp1_roe:.0f}% ROE -> Profit-Lock SL)"
        if tp1_dist < struct_tp1_dist
        else f"50% Book {tp1_ref_name} ({tp1_roe:.1f}% ROE -> Profit-Lock SL)"
    )
    tp2_label = f"50% Structural Runner (Halfway Ratchet -> TP2, ref {tp2_roe:.0f}% ROE)"

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


def build_single_entry_runner_plan(
    direction: str,
    entry: float,
    struct_stop: float,
    struct_tp1: float,
    struct_tp2: float,
    leverage: int = DEFAULT_LEVERAGE,
    max_tp1_roe: float = MAX_TP_ROE_PCT,
    min_tp1_roe: float = MIN_TP_ROE_PCT,
    enforce_min_tp: bool = True,
    tp1_ref_name: str = "50% Retrace",
) -> dict | None:
    """
    Single-Entry Plan (`entry2_sweep = 0.0`) used for Strategy 2 (1-Candle ATR Reversal) and Strategy 3 (9 EMA Retest),
    where Entry 2 scale-in is not used.
    """
    if entry <= 0:
        return None
    lev = max(1, int(leverage))
    eff_lev = 5.0
    is_long = direction.upper() in ("LONG", "BUY")

    struct_tp1_dist = abs(struct_tp1 - entry)
    max_tp1_dist = entry * (max_tp1_roe / 100.0 / eff_lev)
    min_tp1_dist = entry * (min_tp1_roe / 100.0 / eff_lev)

    tp1_dist = min(struct_tp1_dist, max_tp1_dist)
    if enforce_min_tp and tp1_dist < (min_tp1_dist * 0.98):
        return None

    if is_long:
        raw_stop = struct_stop if (0 < struct_stop < entry) else entry * 0.992
        stop_price = max(min(raw_stop, entry * 0.9965), entry * 0.985)
        tp1_price = entry + tp1_dist
        raw_tp2_dist = (struct_tp2 - entry) if struct_tp2 > tp1_price else max(tp1_dist * 2.2, entry * 0.044)
        tp2_dist = max(raw_tp2_dist, tp1_dist * 1.6)
        tp2_price = entry + tp2_dist
    else:
        raw_stop = struct_stop if (struct_stop > entry) else entry * 1.008
        stop_price = min(max(raw_stop, entry * 1.0035), entry * 1.015)
        tp1_price = entry - tp1_dist
        raw_tp2_dist = (entry - struct_tp2) if (0 < struct_tp2 < tp1_price) else max(tp1_dist * 2.2, entry * 0.044)
        tp2_dist = max(raw_tp2_dist, tp1_dist * 1.6)
        tp2_price = entry - tp2_dist

    tp1_roe = round((tp1_dist / entry) * lev * 100.0, 1)
    tp2_roe = round((tp2_dist / entry) * lev * 100.0, 1)
    tp1_label = f"50% Book {tp1_ref_name} ({tp1_roe:.1f}% ROE -> 15m Trail)"
    tp2_label = f"50% Runner (15m Trail + 9 EMA / 20% ATR Exit, ref {tp2_roe:.0f}% ROE)"

    return {
        "entry": entry,
        "entry2_sweep": 0.0,
        "avg_entry_2x": entry,
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
    """Backwards-compatible wrapper returning (stop_price, tp1_price, tp1_label)."""
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
            d.setdefault("strategy_id", self.id)
            d.setdefault("strategy_name", self.name)
        return d


# ----------------------------------------------------------------------------------------------
# Strategy 1: Box Theory + 50/200 EMA Trend, 15m Rejection & Broken-Box Invalidation Guard
# ----------------------------------------------------------------------------------------------
def _check_box_breakout_state(
    recs_15m: list,
    idx: int,
    rh: float,
    rl: float,
    sh: float,
    sl: float,
    ema50_15m: float,
    lookback: int = 16,
) -> dict:
    """
    Inspects the prior `lookback` closed 15m candles (default 16 candles = 4 hours) before `idx` to
    detect whether the upper box (`RH`/`SH`) or lower box (`RL`/`SL`) has already been broken out
    (`upper_box_broken` / `lower_box_broken`), preventing active breakouts from being faded prematurely.
    Setup 0 (Box Breakout-Retest Continuation buying at SH / selling at SL) is disabled so broken
    boxes stay flat rather than entering at exhausted extremes or against the Daily 50/200 EMA bias.
    """
    cur = recs_15m[idx]
    prior = recs_15m[max(0, idx - lookback):idx]

    c_high = float(cur["high"])
    c_low = float(cur["low"])
    c_close = float(cur["close"])
    ema9_15m = float(cur.get("EMA9", c_close) or c_close)

    max_prior_high = max((float(x["high"]) for x in prior), default=c_high)
    min_prior_low = min((float(x["low"]) for x in prior), default=c_low)
    closes_above_sh = sum(1 for x in prior if float(x["close"]) > sh)
    closes_below_sl = sum(1 for x in prior if sl > 0 and float(x["close"]) < sl)

    # Outer Box [SL, SH] is only broken when price decisively breaks beyond the outer SH/SL boundary
    # (>= 3 closed 15m candles beyond SH/SL + >= 0.8% extension + 15m EMA9/EMA50 alignment).
    # Trading inside [RH, SH] (Sell Zone) or [SL, RL] (Buy Zone) is normal zone activity, NOT a broken box.
    upper_box_broken = bool(
        sh > 0
        and closes_above_sh >= 3
        and max_prior_high >= sh * 1.008
        and ema9_15m > ema50_15m
    )
    lower_box_broken = bool(
        sl > 0
        and closes_below_sl >= 3
        and min_prior_low <= sl * 0.992
        and ema9_15m < ema50_15m
    )

    return {
        "upper_box_broken": upper_box_broken,
        "lower_box_broken": lower_box_broken,
        "bull_breakout_retest": False,
        "bear_breakdown_retest": False,
        "max_prior_high": max_prior_high,
        "min_prior_low": min_prior_low,
        "retest_low": c_low,
        "retest_high": c_high,
    }


def _is_box_session_open_blackout(ts_ms) -> bool:
    """
    Returns True if a 15m candle's open timestamp falls inside one of the 3 Session-Open spike windows (IST):
      - Tokyo Open:    07:00 - 08:30 IST (420 <= mins < 510)
      - London Open:   13:00 - 14:30 IST (780 <= mins < 870)
      - New York Open: 18:45 - 20:15 IST (1125 <= mins < 1215)
    """
    try:
        t_val = int(ts_ms or 0)
    except Exception:
        return False
    if t_val <= 0:
        return False
    dt_ist = datetime.fromtimestamp(t_val / 1000.0, tz=IST)
    mins = dt_ist.hour * 60 + dt_ist.minute
    return (420 <= mins < 510) or (780 <= mins < 870) or (1125 <= mins < 1215)


def _count_unbounced_edge_touches(
    records: list,
    idx: int,
    edge_px: float,
    mid_px: float,
    direction: str,
) -> int:
    """
    2-Touch Limit per Box Edge (within the current day):
    Counts how many discrete prior touch episodes of `RL` (for LONG) or `RH` (for SHORT) occurred earlier
    on the same day WITHOUT price bouncing cleanly back to `MID` in between.
    Resets to 0 whenever any candle touches `MID`. Consecutive candles touching the same edge count as 1 episode,
    and the active sweep candle (`idx`) plus its immediate predecessor (`idx - 1`, if part of the same sweep)
    are excluded so we only count *prior* failed tests.
    """
    if idx < 2 or edge_px <= 0 or mid_px <= 0:
        return 0
    is_long = str(direction).upper() in ("LONG", "BUY")
    cur_date = records[idx].get("date_str")
    # Exclude current candle `idx`, and also `idx - 1` if `idx - 1` is part of the same sweep event
    prev_r = records[idx - 1]
    prev_in_sweep = (
        (float(prev_r.get("low", edge_px + 1)) <= edge_px * 1.001) if is_long
        else (float(prev_r.get("high", 0.0)) >= edge_px * 0.999)
    )
    end_idx = idx - 1 if prev_in_sweep else idx
    start_idx = max(0, end_idx - 96)

    touches = 0
    in_touch = False
    for k in range(start_idx, end_idx):
        rec = records[k]
        if cur_date and rec.get("date_str") and rec.get("date_str") != cur_date:
            continue
        hi = float(rec.get("high", 0.0) or 0.0)
        lo = float(rec.get("low", 0.0) or 0.0)
        if is_long:
            if hi >= mid_px:
                touches = 0
                in_touch = False
                continue
            if lo <= edge_px * 1.0015:
                if not in_touch:
                    touches += 1
                    in_touch = True
            elif lo > edge_px * 1.003:
                in_touch = False
        else:
            if lo <= mid_px:
                touches = 0
                in_touch = False
                continue
            if hi >= edge_px * 0.9985:
                if not in_touch:
                    touches += 1
                    in_touch = True
            elif hi < edge_px * 0.997:
                in_touch = False
    return touches


def _build_box_v2_plan(
    direction: str,
    entry: float,
    sweep_wick: float,
    atr14_15m: float,
    mid: float,
    ema50_15m: float,
    opp_edge: float,
    ext_edge: float,
    leverage: int = DEFAULT_LEVERAGE,
    is_broken_retest: bool = False,
) -> dict | None:
    """
    Box Sweep v2 Risk/Reward Planner:
      - Tight Wick-Anchored SL: `sweep_wick +/- 0.35 * 15m ATR(14)` with `>= 0.55%` noise floor
        and hard `<= 2.0%` max SL cap (skips oversized sweep wicks `> 2.0%`).
      - TP1 (50% Book): Nearer of Box `MID` or `15m 50 EMA` in trade direction, minimum `0.85%` away
        (capped at `2.0%` max), shifting SL to `+/-0.20%` fee-covered breakeven.
      - TP2 (50% Runner): Opposite box edge (`RH`/`RL`, or `SH`/`SL` on broken-edge retests).
    """
    if entry <= 0:
        return None
    is_long = str(direction).upper() in ("LONG", "BUY")
    lev = max(1, int(leverage))
    atr = float(atr14_15m or 0.0)
    if atr <= 0 or atr != atr:
        atr = entry * 0.004

    min_tp1_pct = 0.0085
    max_tp1_pct = 0.0200
    max_sl_pct = 0.0200
    min_sl_pct = 0.0055

    if is_long:
        if sweep_wick <= 0 or sweep_wick >= entry:
            sweep_wick = entry * 0.995
        wick_dist_pct = (entry - sweep_wick) / entry
        if wick_dist_pct > max_sl_pct:
            return None
        raw_sl = sweep_wick - 0.35 * atr
        stop_price = max(min(raw_sl, entry * (1.0 - min_sl_pct)), entry * (1.0 - max_sl_pct))
        if stop_price >= entry:
            return None

        cands: list[tuple[float, float, str]] = []
        if not is_broken_retest:
            if mid > entry and (mid - entry) / entry >= min_tp1_pct:
                cands.append((mid - entry, mid, "MID"))
            if ema50_15m > entry and (ema50_15m - entry) / entry >= min_tp1_pct:
                cands.append((ema50_15m - entry, ema50_15m, "15m 50 EMA"))
            if cands:
                _, chosen_px, tp1_ref = min(cands, key=lambda c: c[0])
                tp1_dist = min(chosen_px - entry, entry * max_tp1_pct)
            elif opp_edge > entry and (opp_edge - entry) / entry >= 0.0125:
                tp1_dist = entry * min_tp1_pct
                tp1_ref = "0.85% Min TP1"
            else:
                return None
            tp1_price = entry + tp1_dist
            tp2_base = opp_edge if opp_edge > tp1_price * 1.004 else (ext_edge if ext_edge > tp1_price * 1.004 else entry + tp1_dist * 2.0)
            tp2_price = max(tp2_base, entry + max(tp1_dist * 1.45, entry * 0.014))
        else:
            sl_dist = entry - stop_price
            if ext_edge > entry and (ext_edge - entry) / entry >= min_tp1_pct:
                tp1_dist = min(ext_edge - entry, entry * max_tp1_pct)
                tp1_ref = "SH"
            else:
                tp1_dist = min(max(entry * min_tp1_pct, sl_dist), entry * max_tp1_pct)
                tp1_ref = "1R Retest"
            tp1_price = entry + tp1_dist
            tp2_base = ext_edge if ext_edge > tp1_price * 1.006 else entry + tp1_dist * 2.0
            tp2_price = max(tp2_base, entry + max(tp1_dist * 1.8, entry * 0.018))
    else:
        if sweep_wick <= entry:
            sweep_wick = entry * 1.005
        wick_dist_pct = (sweep_wick - entry) / entry
        if wick_dist_pct > max_sl_pct:
            return None
        raw_sl = sweep_wick + 0.35 * atr
        stop_price = min(max(raw_sl, entry * (1.0 + min_sl_pct)), entry * (1.0 + max_sl_pct))
        if stop_price <= entry:
            return None

        cands = []
        if not is_broken_retest:
            if 0 < mid < entry and (entry - mid) / entry >= min_tp1_pct:
                cands.append((entry - mid, mid, "MID"))
            if 0 < ema50_15m < entry and (entry - ema50_15m) / entry >= min_tp1_pct:
                cands.append((entry - ema50_15m, ema50_15m, "15m 50 EMA"))
            if cands:
                _, chosen_px, tp1_ref = min(cands, key=lambda c: c[0])
                tp1_dist = min(entry - chosen_px, entry * max_tp1_pct)
            elif 0 < opp_edge < entry and (entry - opp_edge) / entry >= 0.0125:
                tp1_dist = entry * min_tp1_pct
                tp1_ref = "0.85% Min TP1"
            else:
                return None
            tp1_price = entry - tp1_dist
            tp2_base = opp_edge if (0 < opp_edge < tp1_price * 0.996) else (ext_edge if (0 < ext_edge < tp1_price * 0.996) else entry - tp1_dist * 2.0)
            tp2_price = min(tp2_base, entry - max(tp1_dist * 1.45, entry * 0.014))
        else:
            sl_dist = stop_price - entry
            if 0 < ext_edge < entry and (entry - ext_edge) / entry >= min_tp1_pct:
                tp1_dist = min(entry - ext_edge, entry * max_tp1_pct)
                tp1_ref = "SL"
            else:
                tp1_dist = min(max(entry * min_tp1_pct, sl_dist), entry * max_tp1_pct)
                tp1_ref = "1R Retest"
            tp1_price = entry - tp1_dist
            tp2_base = ext_edge if (0 < ext_edge < tp1_price * 0.994) else entry - tp1_dist * 2.0
            tp2_price = min(tp2_base, entry - max(tp1_dist * 1.8, entry * 0.018))

    tp1_roe = round((abs(tp1_price - entry) / entry) * lev * 100.0, 1)
    tp2_roe = round((abs(tp2_price - entry) / entry) * lev * 100.0, 1)
    tp1_label = f"50% Book {tp1_ref} ({tp1_roe:.1f}% ROE -> +/-0.20% Fee-BE)"
    tp2_label = f"50% Opposite-Edge Runner (TP2 ref {tp2_roe:.0f}% ROE)"

    return {
        "entry": entry,
        "entry2_sweep": 0.0,
        "avg_entry_2x": entry,
        "stop": stop_price,
        "tp1": tp1_price,
        "tp2": tp2_price,
        "tp1_ref": tp1_ref,
        "tp1_label": tp1_label,
        "tp2_label": tp2_label,
    }


def _detect_box_sweep_reclaim_setup(
    records: list,
    idx: int,
    rh: float,
    rl: float,
    sh: float,
    sl: float,
    mid: float,
    bias: str,
    ema50_15m: float,
    atr14_15m: float,
    vol_sma20: float,
    leverage: int = DEFAULT_LEVERAGE,
) -> dict | None:
    """
    Single shared Box Sweep v2 detector used identically by BOTH live (`BoxTheorySweep.evaluate_signal`)
    and backtest (`BoxTheorySweep.backtest_entry`):
      1. No Middle Trades (Daily 50 EMA middle-of-box trades removed).
      2. Session-Open Spike Blackout: skips Tokyo (07:00-08:30), London (13:00-14:30), NY (18:45-20:15) IST.
      3. 3-Step Sweep-Reclaim with Conviction (solid body >= 35% OR rejection wick >= 30%) + Volume >= 1.15x 20-SMA.
      4. 2-Touch Limit per Edge (resets on MID touch; 3rd unbounced test skipped).
      5. Regime-Aware Broken-Edge Retest: Uptrend bullish retest of broken RH; Downtrend bearish retest of broken RL.
      6. Tight Wick-Anchored SL (`sweep_wick +/- 0.35 * 15m ATR(14)`, <= 2.0% cap) & 50/50 Exit (`TP1 >= 0.85%`, `TP2 = opposite edge`).
    """
    if idx < 1 or idx >= len(records):
        return None
    c = records[idx]
    p = records[idx - 1]

    # 1. Session-Open Spike Blackout (IST)
    if _is_box_session_open_blackout(c.get("timestamp")):
        return None

    c_open = float(c.get("open", c["close"]))
    c_high = float(c["high"])
    c_low = float(c["low"])
    c_close = float(c["close"])
    c_rng = c_high - c_low
    c_body = abs(c_close - c_open)

    p_high = float(p["high"])
    p_low = float(p["low"])

    # Volume confirmation (>= 1.15x 20-SMA whenever real volume series exists)
    if "volume" in c and vol_sma20 and vol_sma20 > 0:
        c_vol = float(c.get("volume", 0.0) or 0.0)
        vol_ok = c_vol >= (1.15 * float(vol_sma20))
    else:
        vol_ok = True
    if not vol_ok:
        return None

    if not atr14_15m or atr14_15m <= 0:
        atr14_15m = max(c_rng, c_close * 0.004)

    brk = _check_box_breakout_state(records, idx, rh, rl, sh, sl, ema50_15m)
    upper_box_broken = brk["upper_box_broken"]
    lower_box_broken = brk["lower_box_broken"]

    upper_wick = c_high - max(c_open, c_close)
    lower_wick = min(c_open, c_close) - c_low
    has_bear_conv = c_rng > 0 and (
        (c_close < c_open and (c_body / c_rng) >= 0.35)
        or ((upper_wick / c_rng) >= 0.30 and c_close <= c_open + 0.10 * c_rng)
    )
    has_bull_conv = c_rng > 0 and (
        (c_close > c_open and (c_body / c_rng) >= 0.35)
        or ((lower_wick / c_rng) >= 0.30 and c_close >= c_open - 0.10 * c_rng)
    )

    prior16 = records[max(0, idx - 16) : idx]

    # ------------------------------------------------------------------
    # SHORT SETUPS (BEARISH & NEUTRAL only — NEVER short RH/SH in BULLISH)
    # ------------------------------------------------------------------
    if bias in ("BEARISH", "NEUTRAL") and has_bear_conv:
        # 1A: RH-SH Kill Zone Sweep + Closed 15m Reclaim Below RH
        swept_rh_zone = (
            (not upper_box_broken)
            and (p_high >= rh or c_high >= rh)
            and (c_close < rh)
            and (max(p_high, c_high) <= sh * 1.012)
        )
        if swept_rh_zone and _count_unbounced_edge_touches(records, idx, rh, mid, "SHORT") < 2:
            sweep_wick = max(c_high, p_high) if p_high >= rh else c_high
            plan = _build_box_v2_plan(
                "SHORT", c_close, sweep_wick, atr14_15m, mid, ema50_15m, rl, sl,
                leverage=leverage, is_broken_retest=False,
            )
            if plan:
                hit_sh = max(p_high, c_high) >= sh
                return {
                    "direction": "SHORT",
                    "signal_kind": "REVERSAL",
                    "trigger_zone": "Sell Zone RH-SH",
                    "lvl_tag": f"SH (${sh:,.2f})" if hit_sh else f"RH (${rh:,.2f})",
                    "short_tag": "Swept SH Swing High" if hit_sh else "Swept RH Sell Zone",
                    "plan": plan,
                }

        # 1B: Broken-RL retest disabled after 5-horizon ablation (90d: 97T, 34.0% WR, -Rs.24,418 vs Pure Sweep +Rs.32,097)
        if False and bias == "BEARISH":
            closes_below_rl = sum(1 for r in prior16 if float(r["close"]) < rl * 0.998)
            retest_rl = (
                (lower_box_broken or closes_below_rl >= 2)
                and (p_high >= rl * 0.997 or c_high >= rl * 0.997)
                and (max(p_high, c_high) <= rl * 1.015)
                and (c_close < rl * 0.999)
            )
            if retest_rl:
                sweep_wick = max(c_high, p_high) if p_high >= rl * 0.997 else c_high
                plan = _build_box_v2_plan(
                    "SHORT", c_close, sweep_wick, atr14_15m, mid, ema50_15m, rl, sl,
                    leverage=leverage, is_broken_retest=True,
                )
                if plan:
                    return {
                        "direction": "SHORT",
                        "signal_kind": "BROKEN_EDGE_RETEST",
                        "trigger_zone": "Broken RL Flip Resistance",
                        "lvl_tag": f"Broken RL (${rl:,.2f})",
                        "short_tag": "Bearish Retest of Broken RL",
                        "plan": plan,
                    }

    # ------------------------------------------------------------------
    # LONG SETUPS (BULLISH & NEUTRAL only — NEVER long RL/SL in BEARISH)
    # ------------------------------------------------------------------
    if bias in ("BULLISH", "NEUTRAL") and has_bull_conv:
        # 2A: RL-SL Kill Zone Sweep + Closed 15m Reclaim Above RL
        swept_rl_zone = (
            (not lower_box_broken)
            and (p_low <= rl or c_low <= rl)
            and (c_close > rl)
            and (min(p_low, c_low) >= sl * 0.988)
        )
        if swept_rl_zone and _count_unbounced_edge_touches(records, idx, rl, mid, "LONG") < 2:
            sweep_wick = min(c_low, p_low) if p_low <= rl else c_low
            plan = _build_box_v2_plan(
                "LONG", c_close, sweep_wick, atr14_15m, mid, ema50_15m, rh, sh,
                leverage=leverage, is_broken_retest=False,
            )
            if plan:
                hit_sl = min(p_low, c_low) <= sl
                return {
                    "direction": "LONG",
                    "signal_kind": "REVERSAL",
                    "trigger_zone": "Buy Zone RL-SL",
                    "lvl_tag": f"SL (${sl:,.2f})" if hit_sl else f"RL (${rl:,.2f})",
                    "short_tag": "Swept SL Swing Low" if hit_sl else "Swept RL Buy Zone",
                    "plan": plan,
                }

        # 2B: Broken-RH retest disabled after 5-horizon ablation (90d: 97T, 34.0% WR, -Rs.24,418 vs Pure Sweep +Rs.32,097)
        if False and bias == "BULLISH":
            closes_above_rh = sum(1 for r in prior16 if float(r["close"]) > rh * 1.002)
            retest_rh = (
                (upper_box_broken or closes_above_rh >= 2)
                and (p_low <= rh * 1.003 or c_low <= rh * 1.003)
                and (min(p_low, c_low) >= rh * 0.985)
                and (c_close > rh * 1.001)
            )
            if retest_rh:
                sweep_wick = min(c_low, p_low) if p_low <= rh * 1.003 else c_low
                plan = _build_box_v2_plan(
                    "LONG", c_close, sweep_wick, atr14_15m, mid, ema50_15m, rh, sh,
                    leverage=leverage, is_broken_retest=True,
                )
                if plan:
                    return {
                        "direction": "LONG",
                        "signal_kind": "BROKEN_EDGE_RETEST",
                        "trigger_zone": "Broken RH Flip Support",
                        "lvl_tag": f"Broken RH (${rh:,.2f})",
                        "short_tag": "Bullish Retest of Broken RH",
                        "plan": plan,
                    }

    return None


class BoxTheorySweep(Strategy):
    id = "box_theory"
    name = "Box Theory Sweep"
    short = "Box"
    timeframe = "Daily 50/200 EMA Bias -> Strictly 15m Zone or 50 EMA Rejection"
    description = (
        "Daily 50 EMA & 200 EMA trend-filtered Box strategy using strictly 15m candle confirmation "
        "and 100% Single-Slot Maker Limit sizing (Entry 2 removed): "
        "(A/C) Sweeps RH/SH (Short) or RL/SL (Long) and closes back inside on 15m candle; "
        "(B/D) Touches Daily 50 EMA and rejects on 15m candle (no 65% box-zone restriction). "
        "TP1 books 50% at Box Midpoint (MID) or 15m 50 EMA (whichever is nearer) and locks SL into profit; "
        "remaining 50% runner holds with Halfway-to-TP2 SL Ratchet toward full TP2 (no 5m 9 EMA cross choke)."
    )
    daily_warmup_days = 1000  # match live 1000-candle Daily EMA200
    tp1_name, tp2_name = "TP1 (50% Book Nearer of MID / 15m 50 EMA)", "50% Structural Runner (Profit-Lock SL -> Halfway Ratchet -> TP2)"
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
        df_15m = _closed_15m(pair, 200)
        if df_15m.empty or len(df_15m) < 3:
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
        c15 = recs_15m[-1]

        c15_close = float(c15["close"])
        ema50_15m = float(c15.get("EMA50", mid))
        atr14_15m = float(c15.get("ATR14", 0.0) or 0.0)
        vol_sma20 = float(c15.get("VOL_SMA20", 0.0) or 0.0)

        candle_time = datetime.fromtimestamp(c15["timestamp"] / 1000, tz=IST).strftime("%H:%M IST")
        near_tp1, _ = _nearest_box_tp1(
            "SHORT" if trend_bias == "BEARISH" else "LONG",
            c15_close, mid, ema50_15m,
            rl if trend_bias == "BEARISH" else rh,
        )

        out = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "candle_evaluated": f"Daily {trend_bias} Bias | 15m Box Sweep v2 ({candle_time}) [{session['emoji']} {session['name']}]",
            "session": session, "session_name": f"{session['emoji']} {session['name']}",
            "is_prime_session": session["is_prime"], "is_us_open_candle": session["session_id"] == "NEW_YORK",
            "pair": pair, "levels": levels, "candle_ts": int(c15["timestamp"]),
            "signal": "NEUTRAL", "signal_kind": None, "trigger_zone": None, "trigger_reason": "",
            "setup": f"WAIT / NO TRADE (Daily Bias: {trend_bias} | 50 EMA: ${daily_ema50:,.2f}, 200 EMA: ${daily_ema200:,.2f})",
            "entry": c15_close, "stop_loss": 0.0, "tp1": near_tp1, "tp2": rl if trend_bias == "BEARISH" else rh,
        }
        out.update(position_metrics(pair, c15_close, 0.0, near_tp1, out["tp2"], margin_inr, leverage, usd_inr))

        bias_label = (
            f"Daily Bearish (<50 EMA ${daily_ema50:,.2f} & <200 EMA ${daily_ema200:,.2f})" if trend_bias == "BEARISH"
            else (
                f"Daily Bullish (>50 EMA ${daily_ema50:,.2f} & >200 EMA ${daily_ema200:,.2f})" if trend_bias == "BULLISH"
                else f"Daily Range (Between 50 EMA ${daily_ema50:,.2f} & 200 EMA ${daily_ema200:,.2f})"
            )
        )
        out["daily_trend_summary"] = bias_label

        hit = _detect_box_sweep_reclaim_setup(
            recs_15m, len(recs_15m) - 1, rh, rl, sh, sl, mid, trend_bias,
            ema50_15m=ema50_15m, atr14_15m=atr14_15m, vol_sma20=vol_sma20, leverage=leverage,
        )
        if hit:
            plan = hit["plan"]
            d_hit = hit["direction"]
            ref_px = rh if d_hit == "SHORT" else rl
            entry = eng.round_asset_price(plan["entry"], ref_px)
            stop = eng.round_asset_price(plan["stop"], ref_px)
            tp1 = eng.round_asset_price(plan["tp1"], ref_px)
            tp2 = eng.round_asset_price(plan["tp2"], ref_px)
            lvl_tag = hit["lvl_tag"]
            side_lbl = "SELL (Short)" if d_hit == "SHORT" else "BUY (Long)"
            reason = (
                f"{bias_label} | Box Sweep v2 {hit['short_tag']} [{lvl_tag}] "
                f"(100% Maker Limit @ ${entry:,.2f} | Wick+0.35ATR SL ${stop:,.2f} | {plan['tp1_label']} & {plan['tp2_label']})"
            )
            out.update({
                "signal": d_hit,
                "signal_kind": hit["signal_kind"],
                "trigger_zone": hit["trigger_zone"],
                "trigger_reason": reason,
                "setup": f"{side_lbl}: {hit['short_tag']} ({session['name']})",
                "entry": entry, "entry2_sweep": 0.0, "stop_loss": stop, "tp1": tp1, "tp2": tp2,
                "candle_ts": int(c15["timestamp"]),
            })
            out.update(position_metrics(pair, entry, stop, tp1, tp2, margin_inr, leverage, usd_inr, entry2_sweep=0.0))
            return self._stamp(out)

        if _is_box_session_open_blackout(c15.get("timestamp")):
            out["setup"] = f"WAIT / SESSION-OPEN BLACKOUT ({session['name']} — avoiding open breakout spikes)"
            out["trigger_reason"] = f"{bias_label}: Session-Open spike blackout active ({candle_time})"
        else:
            out["setup"] = (
                f"WAIT / WATCHING ZONES ({bias_label} — "
                f"watching Buy Zone RL ${rl:,.2f} / SL ${sl:,.2f} & Sell Zone RH ${rh:,.2f} / SH ${sh:,.2f} on 15m)"
            )
            out["trigger_reason"] = f"{bias_label}: Waiting for RL/SL or RH/SH 15m sweep-reclaim with >=1.15x volume"
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
            b["trigger_reason"] = f"Planned ({trend_bias}): 100% Maker Limit @ RL/SL | SL beyond SL (${levels.get('SL', 0):,.2f}) | TP1 Nearer of MID/15m EMA50 -> TP2 Runner"
        if s:
            s["trigger_reason"] = f"Planned ({trend_bias}): 100% Maker Limit @ RH/SH | SL beyond SH (${levels.get('SH', 0):,.2f}) | TP1 Nearer of MID/15m EMA50 -> TP2 Runner"

        if sig and sig.get("signal") == "LONG":
            return {"BUY": self._stamp({**sig, "direction": "BUY"}), "SELL": self._stamp(s),
                    "note": f"⚡ Live confirmed 15m LONG signal: {sig.get('trigger_reason')}"}
        if sig and sig.get("signal") == "SHORT":
            return {"BUY": self._stamp(b), "SELL": self._stamp({**sig, "direction": "SELL"}),
                    "note": f"⚡ Live confirmed 15m SHORT signal: {sig.get('trigger_reason')}"}

        if trend_bias == "BEARISH":
            note_txt = f"🔴 Daily Trend Bias is BEARISH (< 50 EMA ${levels.get('EMA50', 0):,.2f} & 200 EMA ${levels.get('EMA200', 0):,.2f}) — Primary Short bias on 15m confirmation."
        elif trend_bias == "BULLISH":
            note_txt = f"🟢 Daily Trend Bias is BULLISH (> 50 EMA ${levels.get('EMA50', 0):,.2f} & 200 EMA ${levels.get('EMA200', 0):,.2f}) — Primary Long bias on 15m confirmation."
        else:
            note_txt = f"🟡 Daily Range Mode: Price (${levels.get('daily_close', 0):,.2f}) is between 50 EMA (${levels.get('EMA50', 0):,.2f}) and 200 EMA (${levels.get('EMA200', 0):,.2f}) — Both Box Edges Active on 15m."
        return {
            "BUY": self._stamp(b),
            "SELL": self._stamp(s),
            "note": note_txt,
        }

    def chart_lines(self, levels, plan=None):
        if not levels:
            return []
        lines = [
            {"label": "SH (Swing High / Short SL Anchor)", "price": levels["SH"], "color": "#ef4444", "dash": "dash"},
            {"label": "RH / PDH (Short Entry Zone)", "price": levels["RH"], "color": "#ea580c", "dash": "solid"},
            {"label": "MID (50% / TP1 Zone)", "price": levels["MID"], "color": "#0284c7", "dash": "dot"},
            {"label": "RL / PDL (Long Entry Zone)", "price": levels["RL"], "color": "#16a34a", "dash": "solid"},
            {"label": "SL (Swing Low / Long SL Anchor)", "price": levels["SL"], "color": "#10b981", "dash": "dash"},
        ]
        if "EMA50" in levels:
            lines.append({"label": "Daily 50 EMA", "price": levels["EMA50"], "color": "#8b5cf6", "dash": "dash"})
        if "EMA200" in levels:
            lines.append({"label": "Daily 200 EMA", "price": levels["EMA200"], "color": "#f59e0b", "dash": "dash"})
        return lines

    # ---- backtest: Box Sweep v2 (5-10d Regime-Aware Box + 3-Step Sweep-Reclaim + Wick SL + 50/50 Exit) ----
    def prepare_backtest(self, df, df_daily):
        d = daily_sma_atr(df_daily.copy().reset_index(drop=True))
        daily_records = d.to_dict("records")

        ema50_15m_list = df["close"].ewm(span=50, adjust=False).mean().tolist()
        ema9_15m_list = df["close"].ewm(span=9, adjust=False).mean().tolist()
        if {"high", "low", "close"}.issubset(df.columns):
            _hi15 = df["high"].to_numpy(dtype=float)
            _lo15 = df["low"].to_numpy(dtype=float)
            _cl15 = df["close"].to_numpy(dtype=float)
            _pc15 = np.empty_like(_cl15)
            _pc15[0] = _cl15[0]
            _pc15[1:] = _cl15[:-1]
            _tr15 = np.maximum(_hi15 - _lo15, np.maximum(np.abs(_hi15 - _pc15), np.abs(_lo15 - _pc15)))
            atr14_15m_list = pd.Series(_tr15).ewm(alpha=1.0 / 14.0, adjust=False, min_periods=1).mean().tolist()
        else:
            atr14_15m_list = [0.0] * len(df)
        if "volume" in df.columns:
            vol_sma20_list = df["volume"].rolling(20, min_periods=5).mean().fillna(0.0).tolist()
        else:
            vol_sma20_list = [0.0] * len(df)

        # Causal 4H swing pools per trading day (skipped gracefully if `df` is a minimal mock DF)
        day_cutoffs = {}
        for i in range(1, len(daily_records)):
            prev_ts = int(daily_records[i - 1].get("timestamp", 0) or 0)
            if prev_ts > 0:
                day_cutoffs[daily_records[i]["date_str"]] = prev_ts + 86_400_000
        h4_by_day = eng.extract_causal_4h_swings_by_day(df, day_cutoffs, lookback_days=10) if day_cutoffs else {}

        daily_boxes = {}
        for i in range(1, len(daily_records)):
            curr_day_str = daily_records[i]["date_str"]
            prev_day = daily_records[i - 1]
            prev_close = float(prev_day["close"])
            ema50 = float(prev_day["EMA50"])
            ema200 = float(prev_day["EMA200"])
            atr_raw = prev_day.get("ATR")
            atr_val = float(atr_raw) if (atr_raw is not None and not pd.isna(atr_raw)) else None
            bias = classify_daily_ema_bias(prev_close, ema50, ema200)

            # Same shared Regime-Aware 5-10d Box formula as live calculate_daily_box_levels()
            swing = eng.compute_box_swing_levels(
                d.iloc[max(0, i - 20):i],
                bias=bias,
                daily_atr=atr_val,
                h4_swings=h4_by_day.get(curr_day_str),
            )
            rh, rl = swing["RH"], swing["RL"]
            sh, sl = swing["SH"], swing["SL"]
            mid = (rh + rl) / 2.0

            # Identical rounding to live calculate_daily_box_levels() so sweep checks see exact same levels
            daily_boxes[curr_day_str] = {
                "RH": eng.round_asset_price(rh), "RL": eng.round_asset_price(rl),
                "MID": eng.round_asset_price(mid, rh),
                "SH": eng.round_asset_price(sh, rh), "SL": eng.round_asset_price(sl, rl),
                "macro_RH": eng.round_asset_price(swing.get("macro_RH", rh), rh),
                "macro_RL": eng.round_asset_price(swing.get("macro_RL", rl), rl),
                "EMA50": eng.round_asset_price(ema50, rh), "EMA200": eng.round_asset_price(ema200, rh),
                "ATR": float(swing.get("daily_atr", rh - rl)), "bias": bias,
            }
        return {
            "boxes": daily_boxes,
            "ema50_15m": ema50_15m_list,
            "ema9_15m": ema9_15m_list,
            "atr14_15m": atr14_15m_list,
            "vol_sma20": vol_sma20_list,
        }

    def backtest_has_context(self, candle, ctx):
        return bool(ctx["boxes"].get(candle["date_str"]))

    def backtest_entry(self, idx, candle, ctx, records):
        if idx < 1:
            return None
        box = ctx["boxes"][candle["date_str"]]
        bias = box["bias"]

        rh, rl, mid = box["RH"], box["RL"], box["MID"]
        sh, sl = box["SH"], box["SL"]
        ema50_15m = float(ctx["ema50_15m"][idx]) if idx < len(ctx.get("ema50_15m", [])) else mid
        atr14_15m = float(ctx["atr14_15m"][idx]) if idx < len(ctx.get("atr14_15m", [])) else 0.0
        vol_sma20 = float(ctx["vol_sma20"][idx]) if idx < len(ctx.get("vol_sma20", [])) else 0.0

        tag = (
            "Daily <50/200 EMA" if bias == "BEARISH"
            else ("Daily >50/200 EMA" if bias == "BULLISH" else "Daily Range (Between 50/200 EMA)")
        )

        if "EMA9" not in candle and idx < len(ctx.get("ema9_15m", [])):
            candle["EMA9"] = float(ctx["ema9_15m"][idx])

        hit = _detect_box_sweep_reclaim_setup(
            records, idx, rh, rl, sh, sl, mid, bias,
            ema50_15m=ema50_15m, atr14_15m=atr14_15m, vol_sma20=vol_sma20, leverage=DEFAULT_LEVERAGE,
        )
        if not hit:
            return None

        plan = hit["plan"]
        return {
            "direction": hit["direction"],
            "entry": plan["entry"],
            "entry2_sweep": 0.0,
            "stop": plan["stop"],
            "tp1": plan["tp1"],
            "tp2": plan["tp2"],
            "tp1_label": plan["tp1_label"],
            "tp2_label": plan["tp2_label"],
            "reason": f"{tag} + Box v2 {hit['short_tag']} (TP1: {plan['tp1_ref']})",
            "strategy_tag": "Strategy 1 (Box)",
        }


# ----------------------------------------------------------------------------------------------
# Strategy 2: 1-Candle 25% ATR Reversal (Both LONG & SHORT, Single Entry / No Entry 2)
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
    _hi = d["high"].to_numpy(dtype=float)
    _lo = d["low"].to_numpy(dtype=float)
    _cl = d["close"].to_numpy(dtype=float)
    _pc = np.empty_like(_cl)
    _pc[0] = _cl[0]
    _pc[1:] = _cl[:-1]
    tr = pd.Series(np.maximum(_hi - _lo, np.maximum(np.abs(_hi - _pc), np.abs(_lo - _pc))), index=d.index)
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


def detect_atr_reversal(records, j: int, atr: float, bias: str = None):
    """
    Evaluates candle j for the 1-candle crossover entry (works for BOTH LONG and SHORT on any day;
    Single Entry with entry2_sweep = 0.0).
    """
    if j < 2 or atr is None or atr <= 0:
        return None

    for direction in ("LONG", "SHORT"):
        if not _crossover(records, j, direction):
            continue
        flush = find_flush(records, j - 1, atr, direction)
        if not flush:
            continue
        if any(_crossover(records, m, direction) for m in range(flush["end"] + 1, j)):
            continue   # this flush already produced its crossover

        entry = float(records[j]["close"])
        seg = records[flush["start"]:j + 1]
        if direction == "LONG":
            origin = flush["high"]
            extreme = min(float(r["low"]) for r in seg)
            struct_stop = extreme * (1 - SL_BUFFER)
            struct_tp1 = extreme + 0.5 * (origin - extreme)
            if not (struct_stop < entry < struct_tp1):
                continue
            move = "Flush"
        else:
            origin = flush["low"]
            extreme = max(float(r["high"]) for r in seg)
            struct_stop = extreme * (1 + SL_BUFFER)
            struct_tp1 = extreme - 0.5 * (extreme - origin)
            if not (struct_tp1 < entry < struct_stop):
                continue
            move = "Spike"

        plan = build_single_entry_runner_plan(
            direction, entry, struct_stop, struct_tp1, origin,
            leverage=DEFAULT_LEVERAGE, tp1_ref_name="50% Retrace",
        )
        if not plan:
            continue
        return {
            "direction": direction, "entry": entry, "entry2_sweep": 0.0,
            "stop": plan["stop"], "tp1": plan["tp1"], "tp2": plan["tp2"],
            "tp1_label": plan["tp1_label"], "tp2_label": plan["tp2_label"],
            "flush": flush, "extreme": extreme,
            "reason": f"15m {move} = {flush['pct_atr']:.0f}% of Daily ATR (>25% threshold) -> 1-Candle {direction} Reversal",
            "strategy_tag": "Strategy 2 (ATR Reversal)",
        }
    return None


class AtrReversal(Strategy):
    id = "atr_reversal"
    name = "1-Candle 25% ATR Reversal"
    short = "ATR Rev"
    timeframe = "15m Flush/Spike -> Crossover (Long & Short, Single Entry)"
    description = (
        "14-day Daily ATR manipulation reversal strategy (works for BOTH Long and Short on any day, Single Entry): "
        "Detects a 1-3 candle 15m manipulation flush or spike >= 25% of Daily ATR and enters on the first "
        "1-candle reversal crossover (no Entry 2; SL beyond flush/spike extreme, TP1 at 50% retrace, Runner managed by 15m SL & 9 EMA)."
    )
    daily_warmup_days = 220
    tp1_name, tp2_name = "50% Retrace", "Origin / 9 EMA Trail"
    uses_live_price = False
    chart_marker_hint = "▲▼ markers = 15m candles whose high-low range is >= 25% of Daily ATR (shown on the 15m timeframe)."

    # ---- live ----
    def compute_levels(self, pair):
        d = eng.fetch_coindcx_candles(pair=pair, interval="1d", limit=1000, sync_live_price=False)
        if d.empty or len(d) < SMA_PERIOD + 2:
            return None
        d_comp = daily_sma_atr(d.iloc[:-1].reset_index(drop=True))
        last_comp = d_comp.iloc[-1]
        if pd.isna(last_comp["EMA50"]) or pd.isna(last_comp["ATR"]):
            return None
        close = float(last_comp["close"])
        ema50 = float(last_comp["EMA50"])
        ema200 = float(last_comp["EMA200"])
        atr = float(last_comp["ATR"])
        bias = classify_daily_ema_bias(close, ema50, ema200)
        return {
            "SMA50": eng.round_asset_price(ema50, close),
            "EMA50": eng.round_asset_price(ema50, close),
            "EMA200": eng.round_asset_price(ema200, close),
            "ATR": round(atr, 6), "ATR25": round(ATR_FRACTION * atr, 6),
            "daily_close": eng.round_asset_price(close, close), "bias": bias,
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
            "setup": f"WAIT / NO TRADE (Watching 15m candles for >={levels['ATR25']:,.2f} Flush/Spike manipulation)",
            "entry": float(last_c5["close"]), "entry2_sweep": 0.0, "stop_loss": 0.0, "tp1": 0.0, "tp2": 0.0,
        }
        out.update(position_metrics(pair, out["entry"], 0.0, out["entry"], out["entry"], margin_inr, leverage, usd_inr, entry2_sweep=0.0))

        j15 = len(recs15) - 1
        active_flush_msg = None
        for direction in ("LONG", "SHORT"):
            move = "Flush" if direction == "LONG" else "Spike"
            flush = find_flush(recs15, j15, levels["ATR"], direction)
            if not flush:
                continue
            active_flush_msg = (direction, move, flush)
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
                        crossover_info = f"close ${entry:,.2f} > prev 5m red high ${float(prev5['high']):,.2f}"
                    else:
                        extreme = flush["high"]
                        origin = flush["low"]
                        struct_stop = extreme * (1 + SL_BUFFER)
                        struct_tp1 = extreme - 0.5 * (extreme - origin)
                        valid_rr = struct_tp1 < entry < struct_stop
                        crossover_info = f"close ${entry:,.2f} < prev 5m green low ${float(prev5['low']):,.2f}"

                    plan = build_single_entry_runner_plan(
                        direction, entry, struct_stop, struct_tp1, origin, leverage, tp1_ref_name="50% Retrace"
                    ) if valid_rr else None
                    if plan:
                        stop, tp1, tp2 = plan["stop"], plan["tp1"], plan["tp2"]
                        word = "BUY (Long)" if direction == "LONG" else "SELL (Short)"
                        reason = (
                            f"15m {move} = {flush['pct_atr']:.0f}% ATR confirmed by 5m crossover "
                            f"({crossover_info} | Single Entry | {plan['tp1_label']} & {plan['tp2_label']})"
                        )
                        out.update({
                            "signal": direction, "signal_kind": "ATR_REVERSAL",
                            "trigger_zone": f"15m >=25% ATR {move} Reversal",
                            "trigger_reason": reason, "setup": f"{word}: 15m {move} + 5m Crossover (Single Entry) - {reason}",
                            "entry": eng.round_asset_price(entry, entry),
                            "entry2_sweep": 0.0,
                            "stop_loss": eng.round_asset_price(stop, entry),
                            "tp1": eng.round_asset_price(tp1, entry),
                            "tp2": eng.round_asset_price(tp2, entry),
                            "flush": flush,
                        })
                        out.update(position_metrics(pair, out["entry"], out["stop_loss"], out["tp1"], out["tp2"], margin_inr, leverage, usd_inr, entry2_sweep=0.0))
                        return self._stamp(out)

        if active_flush_msg:
            _, move, flush = active_flush_msg
            out["setup"] = f"WAIT / WATCHING 5m (15m {move} = {flush['pct_atr']:.0f}% ATR active — watching 5m timeframe for 1-candle crossover)"
            out["trigger_reason"] = f"15m {move} = {flush['pct_atr']:.0f}% ATR active — waiting for 5m crossover confirmation"
        return self._stamp(out)

    def armed_plan(self, pair, levels):
        """Latest qualifying flush/spike in either direction still waiting for its crossover (or None)."""
        levels, recs15, recs5 = self._context(pair, levels)
        if not levels or not recs15:
            return None
        j15 = len(recs15) - 1
        use_recs = recs5 if recs5 else recs15
        for direction in ("LONG", "SHORT"):
            flush = find_flush(recs15, j15, levels["ATR"], direction)
            if not flush:
                continue
            if any(_crossover(use_recs, m, direction) for m in range(max(1, len(use_recs) - 6), len(use_recs))):
                continue
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
            plan = build_single_entry_runner_plan(direction, entry, struct_stop, struct_tp1, tp2, leverage=DEFAULT_LEVERAGE, enforce_min_tp=False)
            stop = plan["stop"] if plan else struct_stop
            tp1 = plan["tp1"] if plan else struct_tp1
            return {"direction": direction, "entry": entry, "entry2_sweep": 0.0, "stop": stop, "tp1": tp1, "tp2": tp2, "flush": flush, "levels": levels}
        return None

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
            thr = f" of >= ${lv['ATR25']:,.4f}" if lv else ""
            out["note"] = f"Waiting for a 15m Flush (LONG) or Spike (SHORT){thr} — both directions active."
            return out
        ref = plan["entry"]
        e, sl, t1, t2 = (eng.round_asset_price(plan[k], ref) for k in ("entry", "stop", "tp1", "tp2"))
        key = "BUY" if plan["direction"] == "LONG" else "SELL"
        move = "Flush" if key == "BUY" else "Spike"
        reason = (f"Armed: 15m {move} = {plan['flush']['pct_atr']:.0f}% of Daily ATR — watching 5m timeframe for close "
                  f"{'above' if key == 'BUY' else 'below'} {e:,.4f} (Single Entry)")
        setup = {"direction": key, "setup": f"{'BUY (Long)' if key == 'BUY' else 'SELL (Short)'}: 1-Candle Crossover (Single Entry armed)",
                 "entry": e, "entry2_sweep": 0.0, "stop_loss": sl, "tp1": t1, "tp2": t2, "trigger_reason": reason, "flush": plan["flush"]}
        setup.update(position_metrics(pair, e, sl, t1, t2, margin_inr, leverage, usd_inr, entry2_sweep=0.0))
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
        return [
            ("Daily 50 EMA", f"${levels['EMA50']:,.4f}", f"Daily close ${levels['daily_close']:,.4f}"),
            ("Daily 200 EMA", f"${levels['EMA200']:,.4f}", None),
            ("25% ATR Threshold", f"${levels['ATR25']:,.4f}", f"Daily ATR ${levels['ATR']:,.4f}"),
            ("Mode", "🟢🔴 LONG & SHORT (Single Entry)", None),
        ]

    def level_rows(self, levels, live_price):
        if not levels:
            return []

        def dist(p):
            return f"{(p - live_price) / live_price * 100:.2f}%" if live_price else "N/A"
        return [
            {"Level Name": "Daily 50 EMA", "Price": f"${levels['EMA50']:,.4f}", "Role in Strategy": "Reference trend EMA (Both Long & Short active)", "Distance from Live": dist(levels["EMA50"])},
            {"Level Name": "Daily 200 EMA", "Price": f"${levels['EMA200']:,.4f}", "Role in Strategy": "Macro reference EMA", "Distance from Live": dist(levels["EMA200"])},
            {"Level Name": "Daily ATR (14)", "Price": f"${levels['ATR']:,.4f}", "Role in Strategy": "Average daily range used to size the manipulation move", "Distance from Live": "—"},
            {"Level Name": "25% ATR Threshold", "Price": f"${levels['ATR25']:,.4f}", "Role in Strategy": "Minimum 1-3 candle 15m flush / spike size to arm a setup", "Distance from Live": "—"},
        ]

    # ---- backtest ----
    def prepare_backtest(self, df, df_daily):
        d = daily_sma_atr(df_daily.reset_index(drop=True))
        stats = {}
        for i in range(1, len(d)):
            prev = d.iloc[i - 1]
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
# Strategy 3: 9 EMA Touch & Confirm Retest (Fallback when Strategies 1 & 2 have no setup)
# ----------------------------------------------------------------------------------------------
def _has_confirmed_ema9_cross(recs, k: int, direction: str, atr: float = 0.0, max_lookback: int = 12) -> int | None:
    """
    Checks whether a confirmed 9 EMA cross (2 consecutive closes on the new side of EMA9 after crossing
    from the opposite side, driven by or following a >=20% Daily ATR move in the recent window) occurred
    at some index `m` in `[k - max_lookback, k - 1]`, and price has stayed on that side of EMA9 until `k`.
    Never triggers on the cross candle `m` itself (`m <= k - 1`).
    """
    if k < 4 or not atr or atr <= 0:
        return None
    # Require a >=20% Daily ATR 1-to-3 candle move in the recent window [k - 18, k - 1]
    win_start = max(0, k - 18)
    has_atr20_move = False
    for idx_w in range(win_start, k):
        w_slice = recs[max(win_start, idx_w - 2):idx_w + 1]
        hi_w = max(float(x["high"]) for x in w_slice)
        lo_w = min(float(x["low"]) for x in w_slice)
        if (hi_w - lo_w) >= 0.20 * atr:
            has_atr20_move = True
            break
    if not has_atr20_move:
        return None

    start_m = max(2, k - max_lookback)
    for m in range(k - 1, start_m - 1, -1):
        c_m = float(recs[m]["close"])
        e_m = float(recs[m]["EMA9"])
        c_m1 = float(recs[m - 1]["close"])
        e_m1 = float(recs[m - 1]["EMA9"])
        c_m2 = float(recs[m - 2]["close"])
        e_m2 = float(recs[m - 2]["EMA9"])
        if direction == "LONG":
            crossed_up = (c_m2 <= e_m2) and (c_m1 > e_m1) and (c_m > e_m)
            if crossed_up:
                invalidated = False
                for t in range(m + 1, k):
                    if float(recs[t]["close"]) < float(recs[t]["EMA9"]) * 0.998:
                        invalidated = True
                        break
                if not invalidated:
                    return m
        else:
            crossed_dn = (c_m2 >= e_m2) and (c_m1 < e_m1) and (c_m < e_m)
            if crossed_dn:
                invalidated = False
                for t in range(m + 1, k):
                    if float(recs[t]["close"]) > float(recs[t]["EMA9"]) * 1.002:
                        invalidated = True
                        break
                if not invalidated:
                    return m
    return None


def _is_ema9_touch_and_confirm(recs, k: int, direction: str, atr: float) -> bool:
    """True if candle k (after an earlier confirmed 9 EMA cross) touches 9 EMA and confirms rejection."""
    if k < 2:
        return False
    cur = recs[k]
    prev = recs[k - 1]
    c_open = float(cur["open"])
    c_high = float(cur["high"])
    c_low = float(cur["low"])
    c_close = float(cur["close"])
    ema9 = float(cur["EMA9"])
    p_high = float(prev["high"])
    p_low = float(prev["low"])
    p_close = float(prev["close"])
    p_ema9 = float(prev["EMA9"])
    c_range = c_high - c_low

    # Do not enter on an overextended >=20% Daily ATR separator candle
    if atr and atr > 0:
        if c_range >= 0.20 * atr or abs(c_close - ema9) >= 0.20 * atr:
            return False

    if direction == "LONG":
        touched = (c_low <= ema9 * 1.0008 and c_high >= ema9) or (p_low <= p_ema9 * 1.0008 and p_close >= p_ema9 * 0.999)
        confirmed = (c_close > ema9) and (c_close > c_open) and (c_close > p_close)
        return bool(touched and confirmed)
    else:
        touched = (c_high >= ema9 * 0.9992 and c_low <= ema9) or (p_high >= p_ema9 * 0.9992 and p_close <= p_ema9 * 1.001)
        confirmed = (c_close < ema9) and (c_close < c_open) and (c_close < p_close)
        return bool(touched and confirmed)


def detect_ema9_retest_entry(recs, k: int, atr: float, box: dict | None = None, ema50_15m: float = 0.0):
    """
    Strategy 3 Fallback Entry (Upgraded with 4 Live-Trade Post-Mortem Protections):
      1. Earlier confirmed 9 EMA cross (2 consecutive closes across 9 EMA) — never enters on the cross itself.
      2. A subsequent candle `k` pulls back to touch the 9 EMA and confirms in the new direction.
      3. First retest since the confirmed cross (`one trade per confirmed cross`), within <=30% Daily ATR of cross origin.
      4. Daily 50 & 200 EMA Trend Bias Filter: BEARISH -> SHORT only; BULLISH -> LONG only; NEUTRAL -> both.
      5. Daily Box [RL, RH] Outer 20% Exhaustion Guard: no SHORT in bottom 20% of [RL, RH]; no LONG in top 20% of [RL, RH].
      6. Structural 1-Hour (12x5m) Swing + 5m 50 EMA SL Anchor (min 1.0% distance from entry).
      7. Cap TP1 inside opposing 15m 50 EMA, Box MID, or RL/RH/SL/SH support/resistance floor.
    """
    if k < 3 or not atr or atr <= 0:
        return None

    daily_bias = ""
    rh = rl = sh = sl_box = mid = 0.0
    if isinstance(box, dict) and box:
        raw_bias = str(box.get("trend_bias") or box.get("bias") or "").upper()
        if "BEARISH" in raw_bias:
            daily_bias = "BEARISH"
        elif "BULLISH" in raw_bias:
            daily_bias = "BULLISH"
        elif raw_bias:
            daily_bias = "NEUTRAL"
        rh = float(box.get("RH", 0.0) or 0.0)
        rl = float(box.get("RL", 0.0) or 0.0)
        sh = float(box.get("SH", 0.0) or 0.0)
        sl_box = float(box.get("SL", 0.0) or 0.0)
        mid = float(box.get("MID", 0.0) or 0.0)

    for direction in ("LONG", "SHORT"):
        # Improvement 2: Strict Daily 50 & 200 EMA Trend Bias Filter
        if daily_bias == "BEARISH" and direction != "SHORT":
            continue
        if daily_bias == "BULLISH" and direction != "LONG":
            continue

        cross_idx = _has_confirmed_ema9_cross(recs, k, direction, atr=atr)
        if cross_idx is None:
            continue
        if not _is_ema9_touch_and_confirm(recs, k, direction, atr):
            continue
        # Only take the FIRST touch-and-confirm after `cross_idx`
        if any(_is_ema9_touch_and_confirm(recs, m, direction, atr) for m in range(cross_idx + 1, k)):
            continue

        cur = recs[k]
        entry = float(cur["close"])
        ema9 = float(cur["EMA9"])

        # Improvement 3A: Overextended Cross-Origin Distance Guard (<= 30% Daily ATR from cross close)
        cross_close = float(recs[cross_idx].get("close", entry))
        if abs(entry - cross_close) > 0.30 * atr:
            continue

        # Improvement 3B: Daily Box [RL, RH] Outer 20% Exhaustion Guard
        if rh > rl > 0:
            box_span = rh - rl
            if direction == "SHORT" and entry <= (rl + 0.20 * box_span):
                continue
            if direction == "LONG" and entry >= (rh - 0.20 * box_span):
                continue

        # Improvement 1: 1-Hour (12x5m) Structural Swing + 5m 50 EMA Stop Loss Anchor (min 1.0% buffer)
        win12 = recs[max(0, k - 11):k + 1]
        ema50_5m = float(cur.get("EMA50") or ema9)
        tp1_move = max(min(0.35 * atr, entry * 0.015), entry * 0.0068)

        if direction == "LONG":
            swing_low_12 = min(float(x["low"]) for x in win12)
            near_ema50_low = ema50_5m if (0 < ema50_5m < entry and (entry - ema50_5m) <= entry * 0.012) else swing_low_12
            anchor_low = min(swing_low_12, near_ema50_low, ema9)
            struct_stop = min(anchor_low * (1 - SL_BUFFER), entry * 0.990)
            struct_tp1 = entry + tp1_move
            struct_tp2 = entry + max(0.80 * atr, tp1_move * 2.2)

            # Improvement 4 (LONG): Cap TP1 inside opposing 15m 50 EMA, Box MID, or RH/SH resistance ceiling
            if rh > entry:
                struct_tp1 = min(struct_tp1, rh * 0.9985)
            elif sh > entry >= rh > 0:
                struct_tp1 = min(struct_tp1, sh * 0.9975)
            for ceil_lvl in (float(ema50_15m or 0.0), mid):
                if ceil_lvl > 0 and (ceil_lvl * 0.999) >= (entry * 1.0062) and (ceil_lvl * 0.999) < struct_tp1:
                    struct_tp1 = ceil_lvl * 0.999
        else:
            swing_high_12 = max(float(x["high"]) for x in win12)
            near_ema50_high = ema50_5m if (ema50_5m > entry and (ema50_5m - entry) <= entry * 0.012) else swing_high_12
            anchor_high = max(swing_high_12, near_ema50_high, ema9)
            struct_stop = max(anchor_high * (1 + SL_BUFFER), entry * 1.010)
            struct_tp1 = entry - tp1_move
            struct_tp2 = entry - max(0.80 * atr, tp1_move * 2.2)

            # Improvement 4 (SHORT): Cap TP1 inside opposing 15m 50 EMA, Box MID, or RL/SL support floor
            if 0 < rl < entry:
                struct_tp1 = max(struct_tp1, rl * 1.0015)
            elif 0 < sl_box < entry <= rl:
                struct_tp1 = max(struct_tp1, sl_box * 1.0025)
            for floor_lvl in (float(ema50_15m or 0.0), mid):
                if floor_lvl > 0 and (floor_lvl * 1.001) <= (entry * 0.9938) and (floor_lvl * 1.001) > struct_tp1:
                    struct_tp1 = floor_lvl * 1.001

        plan = build_single_entry_runner_plan(
            direction, entry, struct_stop, struct_tp1, struct_tp2,
            leverage=DEFAULT_LEVERAGE, tp1_ref_name="9 EMA Pullback Target",
        )
        if not plan:
            continue
        return {
            "direction": direction,
            "entry": entry,
            "entry2_sweep": 0.0,
            "stop": plan["stop"],
            "tp1": plan["tp1"],
            "tp2": plan["tp2"],
            "tp1_label": plan["tp1_label"],
            "tp2_label": plan["tp2_label"],
            "reason": f"Confirmed 9 EMA Cross -> Subsequent 9 EMA Touch & {direction} Rejection",
            "strategy_tag": "Strategy 3 (9 EMA Retest)",
        }
    return None


class Ema9RetestStrategy(Strategy):
    id = "ema9_retest"
    name = "9 EMA Touch & Confirm (Fallback)"
    short = "9EMA Retest"
    timeframe = "5m Confirmed 9 EMA Cross -> Subsequent 5m 9 EMA Touch & Rejection"
    description = (
        "Strategy 3 Fallback Entry & Active Trade Exit Engine: "
        "Only takes a new trade when Strategies 1 & 2 have no setup. "
        "Does NOT enter immediately on a 9 EMA cross; waits for a confirmed 5m 9 EMA cross (2 consecutive closes) "
        "followed by a later 5m candle that touches the 9 EMA and confirms rejection (<20% Daily ATR), "
        "filtered by Daily 50/200 EMA Trend Bias, Daily Box outer-20% exhaustion guard, and 12-candle structural SL."
    )
    daily_warmup_days = 1000
    tp1_name, tp2_name = "TP1 (50% Book)", "50% Runner (15m Trail + 9 EMA / 20% ATR Exit)"
    uses_live_price = False

    def compute_levels(self, pair):
        box_lvls = eng.calculate_daily_box_levels(pair)
        d = eng.fetch_coindcx_candles(pair=pair, interval="1d", limit=1000, sync_live_price=False)
        if d.empty or len(d) < SMA_PERIOD + 2:
            return box_lvls
        d_comp = daily_sma_atr(d.iloc[:-1].reset_index(drop=True))
        last_comp = d_comp.iloc[-1]
        if pd.isna(last_comp["ATR"]):
            return box_lvls
        close = float(last_comp["close"])
        atr = float(last_comp["ATR"])
        ema50_d = float(last_comp["EMA50"])
        ema200_d = float(last_comp["EMA200"])
        trend_bias = classify_daily_ema_bias(close, ema50_d, ema200_d)
        df5 = _closed_5m(pair, 40)
        ema9_5m = float(df5["EMA9"].iloc[-1]) if (not df5.empty and "EMA9" in df5) else close
        df15 = _closed_15m(pair, 60)
        ema50_15m = float(df15["EMA50"].iloc[-1]) if (not df15.empty and "EMA50" in df15) else close
        base = dict(box_lvls) if isinstance(box_lvls, dict) else {}
        base.update({
            "EMA9_5M": eng.round_asset_price(ema9_5m, close),
            "EMA50_15M": eng.round_asset_price(ema50_15m, close),
            "ATR": round(atr, 6),
            "ATR20": round(0.20 * atr, 6),
            "daily_close": eng.round_asset_price(close, close),
            "trend_bias": base.get("trend_bias") or trend_bias,
            "bias": base.get("bias") or trend_bias,
            "prev_day_date": datetime.fromtimestamp(last_comp["timestamp"] / 1000, tz=IST).strftime("%Y-%m-%d"),
        })
        return base

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
        levels = levels or self.compute_levels(pair)
        if not levels:
            return None
        if "RH" not in levels or "trend_bias" not in levels:
            try:
                box_extra = eng.calculate_daily_box_levels(pair) or {}
                merged = dict(box_extra)
                merged.update(levels)
                levels = merged
            except Exception:
                pass
        df5 = _closed_5m(pair, 60)
        if df5.empty or len(df5) < 6:
            return None
        recs5 = df5.to_dict("records")
        last_c5 = recs5[-1]
        ema50_15m = float(levels.get("EMA50_15M", 0.0) or 0.0)
        if ema50_15m <= 0:
            df15 = _closed_15m(pair, 60)
            if not df15.empty and "EMA50" in df15:
                ema50_15m = float(df15["EMA50"].iloc[-1])
        session = eng.get_current_session_info(datetime.now(IST))
        candle_time = datetime.fromtimestamp(last_c5["timestamp"] / 1000, tz=IST).strftime("%H:%M IST")
        entry_px = float(last_c5["close"])

        out = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "candle_evaluated": f"5m 9 EMA Touch & Confirm ({candle_time}) [{session['emoji']} {session['name']}]",
            "session": session, "session_name": f"{session['emoji']} {session['name']}",
            "is_prime_session": session["is_prime"], "is_us_open_candle": session["session_id"] == "NEW_YORK",
            "pair": pair, "levels": levels, "candle_ts": int(last_c5["timestamp"]),
            "signal": "NEUTRAL", "signal_kind": None, "trigger_zone": None, "trigger_reason": "",
            "setup": f"WAIT / WATCHING 5m 9 EMA (${levels.get('EMA9_5M', entry_px):,.4f}) for post-cross touch & confirmation",
            "entry": entry_px, "entry2_sweep": 0.0, "stop_loss": 0.0, "tp1": entry_px, "tp2": entry_px,
        }
        out.update(position_metrics(pair, entry_px, 0.0, entry_px, entry_px, margin_inr, leverage, usd_inr, entry2_sweep=0.0))

        sig3 = detect_ema9_retest_entry(recs5, len(recs5) - 1, float(levels["ATR"]), box=levels, ema50_15m=ema50_15m)
        if sig3:
            direction = sig3["direction"]
            word = "BUY (Long)" if direction == "LONG" else "SELL (Short)"
            e = eng.round_asset_price(sig3["entry"], sig3["entry"])
            sl = eng.round_asset_price(sig3["stop"], e)
            tp1 = eng.round_asset_price(sig3["tp1"], e)
            tp2 = eng.round_asset_price(sig3["tp2"], e)
            out.update({
                "signal": direction,
                "signal_kind": "EMA9_RETEST",
                "trigger_zone": "5m 9 EMA Retest",
                "trigger_reason": sig3["reason"],
                "setup": f"{word}: 5m 9 EMA Touch & Confirm (Fallback) - {sig3['reason']}",
                "entry": e, "entry2_sweep": 0.0, "stop_loss": sl, "tp1": tp1, "tp2": tp2,
            })
            out.update(position_metrics(pair, e, sl, tp1, tp2, margin_inr, leverage, usd_inr, entry2_sweep=0.0))
        return self._stamp(out)

    def prepare_backtest(self, df, df_daily):
        d = daily_sma_atr(df_daily.reset_index(drop=True))
        ema50_15m_list = df["close"].ewm(span=50, adjust=False).mean().tolist() if (df is not None and not df.empty) else []
        stats = {}
        for i in range(1, len(d)):
            prev = d.iloc[i - 1]
            if pd.isna(prev["ATR"]):
                continue
            rh = float(prev["high"])
            rl = float(prev["low"])
            prev_close = float(prev["close"])
            ema50_d = float(prev["EMA50"])
            ema200_d = float(prev["EMA200"])
            mid = (rh + rl) / 2.0
            bias = classify_daily_ema_bias(prev_close, ema50_d, ema200_d)
            swing = eng.compute_box_swing_levels(d.iloc[max(0, i - 30):i])
            stats[d.iloc[i]["date_str"]] = {
                "atr": float(prev["ATR"]),
                "RH": eng.round_asset_price(rh),
                "RL": eng.round_asset_price(rl),
                "MID": eng.round_asset_price(mid, rh),
                "SH": eng.round_asset_price(swing["SH"], rh),
                "SL": eng.round_asset_price(swing["SL"], rl),
                "EMA50": eng.round_asset_price(ema50_d, rh),
                "EMA200": eng.round_asset_price(ema200_d, rh),
                "bias": bias,
                "trend_bias": bias,
            }

        # Use 5m candles attached to df.attrs["df_5m"] when available; otherwise compute EMA9/EMA50 on df
        df_5m = df.attrs.get("df_5m") if hasattr(df, "attrs") else None
        sub5_by_15m = {}
        recs5 = []
        if df_5m is not None and not df_5m.empty:
            c5 = df_5m.copy().reset_index(drop=True)
            if "EMA9" not in c5:
                c5["EMA9"] = c5["close"].ewm(span=9, adjust=False).mean()
            if "EMA50" not in c5:
                c5["EMA50"] = c5["close"].ewm(span=50, adjust=False).mean()
            recs5 = c5.to_dict("records")
            for idx5, r5 in enumerate(recs5):
                bucket = (int(r5["timestamp"]) // 900000) * 900000
                sub5_by_15m.setdefault(bucket, []).append(idx5)
        else:
            c15 = df.copy().reset_index(drop=True)
            c15["EMA9"] = c15["close"].ewm(span=9, adjust=False).mean()
            if "EMA50" not in c15:
                c15["EMA50"] = c15["close"].ewm(span=50, adjust=False).mean()
            recs5 = c15.to_dict("records")
            for idx15, r15 in enumerate(recs5):
                bucket = (int(r15["timestamp"]) // 900000) * 900000
                sub5_by_15m[bucket] = [idx15]

        return {"daily": stats, "recs5": recs5, "sub5_by_15m": sub5_by_15m, "ema50_15m": ema50_15m_list}

    def backtest_has_context(self, candle, ctx):
        return candle["date_str"] in ctx["daily"]

    def backtest_entry(self, idx, candle, ctx, records):
        day = ctx["daily"].get(candle["date_str"])
        if not day:
            return None
        atr = day["atr"]
        ema50_15m = float(ctx["ema50_15m"][idx]) if idx < len(ctx.get("ema50_15m", [])) else float(day.get("MID", 0.0) or 0.0)
        bucket = (int(candle["timestamp"]) // 900000) * 900000
        idx5_list = ctx.get("sub5_by_15m", {}).get(bucket, [])
        recs5 = ctx.get("recs5", [])
        for k5 in idx5_list:
            sig = detect_ema9_retest_entry(recs5, k5, atr, box=day, ema50_15m=ema50_15m)
            if sig:
                return sig
        return None


# ----------------------------------------------------------------------------------------------
# Combined Priority Strategy (Strategy 1 -> Strategy 2 -> Strategy 3 Fallback)
# ----------------------------------------------------------------------------------------------
class CombinedPriorityStrategy(Strategy):
    id = "combined"
    name = "Combined (1: Box -> 2: ATR Rev -> 3: 9 EMA Fallback)"
    short = "Combined 1->2->3"
    timeframe = "15m Box & ATR Reversal + 5m 9 EMA Touch-Retest Fallback"
    description = (
        "Evaluates Strategy 1 (15m Box Sweep / Daily 50 EMA Rejection) first, "
        "then Strategy 2 (1-Candle 25% ATR Reversal, Long & Short, Single Entry), "
        "and ONLY falls back to Strategy 3 (5m Confirmed 9 EMA Cross -> 9 EMA Touch & Confirm) "
        "when Strategies 1 & 2 yield no setup."
    )
    daily_warmup_days = 1000  # match live 1000-candle Daily EMA200
    tp1_name, tp2_name = "TP1 (50% Book Nearer of MID / 15m 50 EMA)", "50% Runner (15m Trail + 9 EMA / 20% ATR Exit)"
    uses_live_price = True

    def __init__(self, include_strategy3_entry: bool = True):
        self.s1 = BoxTheorySweep()
        self.s2 = AtrReversal()
        self.s3 = Ema9RetestStrategy()
        self.include_strategy3_entry = include_strategy3_entry

    def compute_levels(self, pair):
        return self.s1.compute_levels(pair)

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
        sig1 = self.s1.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
        if sig1 and sig1.get("signal") in ("LONG", "SHORT"):
            return sig1
        sig2 = self.s2.evaluate_signal(pair, None, margin_inr, leverage, usd_inr)
        if sig2 and sig2.get("signal") in ("LONG", "SHORT"):
            return sig2
        if self.include_strategy3_entry:
            sig3 = self.s3.evaluate_signal(pair, None, margin_inr, leverage, usd_inr)
            if sig3 and sig3.get("signal") in ("LONG", "SHORT"):
                return sig3
        return sig1

    def prepare_backtest(self, df, df_daily):
        ctx1 = self.s1.prepare_backtest(df, df_daily)
        ctx2 = self.s2.prepare_backtest(df, df_daily)
        ctx3 = self.s3.prepare_backtest(df, df_daily)
        return {
            "ctx1": ctx1,
            "ctx2": ctx2,
            "ctx3": ctx3,
            "boxes": ctx1["boxes"],
            "s1_s2_days": set(),
            "s3_days": set(),
        }

    def backtest_has_context(self, candle, ctx):
        return self.s1.backtest_has_context(candle, ctx["ctx1"])

    def backtest_entry(self, idx, candle, ctx, records):
        day_str = candle["date_str"]
        # Priority 1: Strategy 1 (Box Theory 15m)
        e1 = self.s1.backtest_entry(idx, candle, ctx["ctx1"], records)
        if e1:
            ctx["s1_s2_days"].add(day_str)
            return e1
        # Priority 2: Strategy 2 (1-Candle 25% ATR Reversal, Long & Short, Single Entry)
        if self.s2.backtest_has_context(candle, ctx["ctx2"]):
            e2 = self.s2.backtest_entry(idx, candle, ctx["ctx2"], records)
            if e2:
                ctx["s1_s2_days"].add(day_str)
                return e2
        # Priority 3: Strategy 3 Fallback (ONLY if Strategies 1 & 2 have yielded no setup on this day, max 1 fallback per day)
        if (
            self.include_strategy3_entry
            and day_str not in ctx["s1_s2_days"]
            and day_str not in ctx["s3_days"]
            and self.s3.backtest_has_context(candle, ctx["ctx3"])
        ):
            e3 = self.s3.backtest_entry(idx, candle, ctx["ctx3"], records)
            if e3:
                ctx["s3_days"].add(day_str)
                return e3
        return None


# ----------------------------------------------------------------------------------------------
# Strategy 4: 15m 50/200 EMA Pullback Strategy (Trending Continuation -> RL / RH Target)
# ----------------------------------------------------------------------------------------------
def _compute_warmed_15m_emas(df_sub: pd.DataFrame) -> tuple[list[float], list[float]]:
    """Computes 15m EMA50 and EMA200 using extended pre-window history if attached in df_sub.attrs['df_full_15m']."""
    df_full = df_sub.attrs.get("df_full_15m") if hasattr(df_sub, "attrs") else None
    if df_full is not None and not df_full.empty and len(df_full) >= len(df_sub):
        e50 = df_full["close"].ewm(span=50, adjust=False).mean()
        e200 = df_full["close"].ewm(span=200, adjust=False).mean()
        tail_n = len(df_sub)
        return e50.iloc[-tail_n:].tolist(), e200.iloc[-tail_n:].tolist()
    return (
        df_sub["close"].ewm(span=50, adjust=False).mean().tolist(),
        df_sub["close"].ewm(span=200, adjust=False).mean().tolist(),
    )


def _detect_ema50_200_setup(
    recs15: list[dict],
    idx: int,
    box: dict,
    ema50_val: float,
    ema200_val: float,
    prior_e50: list[float],
    prior_e200: list[float],
    allow_bear: bool = True,
    allow_bull: bool = True,
) -> dict | None:
    """
    Shared 15m 50/200 EMA Pullback detection (100% live <-> backtest parity):
      - Bearish Daily Bias -> SHORT when 15m EMA50 < EMA200, price pulls up from below into [50, 200] EMA,
        and 15m candle rejects back below EMA50. SL placed above max(15m EMA200, reach_high); TP2 = RL.
      - Bullish Daily Bias -> LONG (Mirror Replica) when 15m EMA50 > EMA200, price pulls down from above
        into [200, 50] EMA, and 15m candle rejects back above EMA50. SL placed below min(15m EMA200, reach_low); TP2 = RH.
    """
    if idx < 6 or not box or len(prior_e50) < 4 or len(prior_e200) < 4:
        return None
    bias = str(box.get("trend_bias") or box.get("bias") or "").upper()
    if bias not in ("BEARISH", "BULLISH"):
        return None

    rh = float(box.get("RH", 0.0) or 0.0)
    rl = float(box.get("RL", 0.0) or 0.0)
    e50 = float(ema50_val or 0.0)
    e200 = float(ema200_val or 0.0)
    if rh <= 0 or rl <= 0 or e50 <= 0 or e200 <= 0:
        return None

    candle = recs15[idx]
    prev = recs15[idx - 1]
    prior = recs15[idx - len(prior_e50):idx]

    c_open = float(candle.get("open", candle["close"]))
    c_high = float(candle["high"])
    c_low = float(candle["low"])
    c_close = float(candle["close"])
    c_rng = c_high - c_low
    p_high = float(prev["high"])
    p_low = float(prev["low"])
    p_close = float(prev["close"])

    if allow_bear and bias == "BEARISH" and e50 < e200:
        below_cnt = sum(1 for r, em in zip(prior, prior_e50) if float(r["close"]) < float(em))
        above_e200_cnt = sum(1 for r, em2 in zip(prior, prior_e200) if float(r["close"]) > float(em2))
        if below_cnt >= 3 and above_e200_cnt <= 1:
            reach_high = max(c_high, p_high)
            if reach_high >= e50 * 0.9995 and reach_high <= e200 * 1.004:
                u_wick = c_high - max(c_open, c_close)
                bear_rej = (
                    c_close < e50
                    and c_close < c_open
                    and ((c_close < p_close) or (c_rng > 0 and (u_wick / c_rng) >= 0.35))
                )
                if bear_rej and rl < c_close * 0.992:
                    lb = min(idx, 12)
                    loc_low_3h = min(float(recs15[k]["low"]) for k in range(idx - lb, idx))
                    room_3h = c_close - loc_low_3h
                    box_w = max(1e-9, rh - rl)
                    z_pos = (c_close - rl) / box_w
                    # 1. Bottom-of-Box Floor Guard (v34): never short in the extreme bottom 15% of the Daily Box [RL, RH],
                    #    and in the bottom 35% require >=0.55% 3h structural room (prevents APT $0.4304 bottom-of-box traps).
                    # 2. 3h Structure Guard: skip shorting directly into a 3h local double-bottom (<0.45% room).
                    bottom_box_blocked = (z_pos < 0.15) or (idx >= 12 and z_pos < 0.35 and room_3h < c_close * 0.0055)
                    if not bottom_box_blocked and room_3h >= c_close * 0.0045:
                        stop_px = max(e200, reach_high) * 1.0025
                        if ((stop_px - c_close) / c_close) * 100.0 < 0.30:
                            stop_px = c_close * 1.004
                        rew_dist = c_close - rl
                        tp1_dist = min(rew_dist * 0.50, c_close * 0.020)
                        tp1_src_lbl = "Mid(Entry,RL)"
                        # 3h Structure-Capped TP1: book 50% right above 3h local swing low before support bounces
                        if room_3h >= c_close * 0.008 and room_3h < tp1_dist:
                            tp1_dist = max(c_close * 0.008, room_3h * 0.94)
                            tp1_src_lbl = "3h-SwingLow"
                        if tp1_dist >= c_close * 0.006:
                            tp1_px = c_close - tp1_dist
                            tp1_roe = round((tp1_dist / c_close) * DEFAULT_LEVERAGE * 100.0, 1)
                            tp2_roe = round((rew_dist / c_close) * DEFAULT_LEVERAGE * 100.0, 1)
                            return {
                                "direction": "SHORT",
                                "entry": c_close,
                                "entry2_sweep": 0.0,
                                "stop": stop_px,
                                "tp1": tp1_px,
                                "tp2": rl,
                                "tp1_label": f"50% Book {tp1_src_lbl} ({tp1_roe:.1f}% ROE -> Profit-Lock SL)",
                                "tp2_label": f"50% Runner @ RL (Halfway Ratchet, ref {tp2_roe:.0f}% ROE)",
                                "reason": f"Bear 15m 50<200 EMA Pullback Rejection -> RL (TP1: {tp1_src_lbl})",
                                "trigger_zone": "15m 50/200 EMA CEILING",
                                "strategy_tag": "Strategy 4 (15m 50/200 EMA)",
                                "ema50_15m": e50,
                                "ema200_15m": e200,
                            }

    if allow_bull and bias == "BULLISH" and e50 > e200:
        above_cnt = sum(1 for r, em in zip(prior, prior_e50) if float(r["close"]) > float(em))
        below_e200_cnt = sum(1 for r, em2 in zip(prior, prior_e200) if float(r["close"]) < float(em2))
        if above_cnt >= 3 and below_e200_cnt <= 1:
            reach_low = min(c_low, p_low)
            if reach_low <= e50 * 1.0005 and reach_low >= e200 * 0.996:
                l_wick = min(c_open, c_close) - c_low
                bull_rej = (
                    c_close > e50
                    and c_close > c_open
                    and ((c_close > p_close) or (c_rng > 0 and (l_wick / c_rng) >= 0.35))
                )
                if bull_rej and rh > c_close * 1.008:
                    lb = min(idx, 12)
                    loc_high_3h = max(float(recs15[k]["high"]) for k in range(idx - lb, idx))
                    room_3h = loc_high_3h - c_close
                    box_w = max(1e-9, rh - rl)
                    z_top = (rh - c_close) / box_w
                    # 1. Top-of-Box Ceiling Guard (v34): never buy in the extreme top 15% of the Daily Box [RL, RH],
                    #    and in the top 35% require >=0.55% 3h structural room.
                    # 2. 3h Structure Guard: skip longing directly into a 3h local double-top (<0.45% room).
                    top_box_blocked = (z_top < 0.15) or (idx >= 12 and z_top < 0.35 and room_3h < c_close * 0.0055)
                    if not top_box_blocked and room_3h >= c_close * 0.0045:
                        stop_px = min(e200, reach_low) * 0.9975
                        if ((c_close - stop_px) / c_close) * 100.0 < 0.30:
                            stop_px = c_close * 0.996
                        rew_dist = rh - c_close
                        tp1_dist = min(rew_dist * 0.50, c_close * 0.020)
                        tp1_src_lbl = "Mid(Entry,RH)"
                        # 3h Structure-Capped TP1: book 50% right below 3h local swing high before resistance stalls
                        if room_3h >= c_close * 0.008 and room_3h < tp1_dist:
                            tp1_dist = max(c_close * 0.008, room_3h * 0.94)
                            tp1_src_lbl = "3h-SwingHigh"
                        if tp1_dist >= c_close * 0.006:
                            tp1_px = c_close + tp1_dist
                            tp1_roe = round((tp1_dist / c_close) * DEFAULT_LEVERAGE * 100.0, 1)
                            tp2_roe = round((rew_dist / c_close) * DEFAULT_LEVERAGE * 100.0, 1)
                            return {
                                "direction": "LONG",
                                "entry": c_close,
                                "entry2_sweep": 0.0,
                                "stop": stop_px,
                                "tp1": tp1_px,
                                "tp2": rh,
                                "tp1_label": f"50% Book {tp1_src_lbl} ({tp1_roe:.1f}% ROE -> Profit-Lock SL)",
                                "tp2_label": f"50% Runner @ RH (Halfway Ratchet, ref {tp2_roe:.0f}% ROE)",
                                "reason": f"Bull 15m 50>200 EMA Pullback Bounce -> RH (TP1: {tp1_src_lbl})",
                                "trigger_zone": "15m 50/200 EMA FLOOR",
                                "strategy_tag": "Strategy 4 (15m 50/200 EMA)",
                                "ema50_15m": e50,
                                "ema200_15m": e200,
                            }

    return None


class Ema50200PullbackStrategy(Strategy):
    id = "ema50_200"
    name = "15m 50/200 EMA Pullback"
    short = "15m 50/200 EMA"
    timeframe = "15m 50/200 EMA Pullback Rejection -> RL/RH (Single Entry)"
    description = (
        "Trending-market pullback continuation strategy: in Bearish Daily Bias (15m 50 < 200 EMA), shorts a "
        "pullback up into the 50/200 EMA ceiling that rejects back below 50 EMA with SL above 15m 200 EMA and "
        "TP2 at Range Low (RL). Mirror Long replica in Bullish Daily Bias (15m 50 > 200 EMA) targeting RH."
    )
    daily_warmup_days = 1000
    tp1_name, tp2_name = "TP1 (50% Book Mid)", "TP2 (50% Runner @ RL/RH)"
    uses_live_price = True

    def __init__(self, allow_bear: bool = True, allow_bull: bool = True):
        self.allow_bear = allow_bear
        self.allow_bull = allow_bull

    def compute_levels(self, pair):
        lv = eng.calculate_daily_box_levels(pair)
        if not lv:
            return None
        df15 = _closed_15m(pair, 30)
        if df15 is not None and not df15.empty:
            e50 = float(df15["EMA50"].iloc[-1])
            e200 = float(df15["EMA200"].iloc[-1])
            ref_px = float(lv.get("RH") or lv.get("daily_close") or e50)
            lv["EMA50_15m"] = eng.round_asset_price(e50, ref_px)
            lv["EMA200_15m"] = eng.round_asset_price(e200, ref_px)
            lv["ema_15m_trend"] = "BEAR (50 < 200)" if e50 < e200 else ("BULL (50 > 200)" if e50 > e200 else "FLAT")
        return lv

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
        levels = levels or self.compute_levels(pair)
        if not levels:
            return None
        df15 = _closed_15m(pair, 40)
        if df15.empty or len(df15) < 8:
            return None

        recs15 = df15.to_dict("records")
        idx = len(recs15) - 1
        cur = recs15[idx]
        e50 = float(cur["EMA50"])
        e200 = float(cur["EMA200"])
        ref_px = float(cur["close"])
        levels["EMA50_15m"] = eng.round_asset_price(e50, ref_px)
        levels["EMA200_15m"] = eng.round_asset_price(e200, ref_px)
        levels["ema_15m_trend"] = "BEAR (50 < 200)" if e50 < e200 else ("BULL (50 > 200)" if e50 > e200 else "FLAT")

        session = eng.get_current_session_info(datetime.now(IST))
        candle_time = datetime.fromtimestamp(cur["timestamp"] / 1000, tz=IST).strftime("%H:%M IST")
        out = {
            "timestamp": datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST"),
            "candle_evaluated": f"15m ({candle_time}) [{session['emoji']} {session['name']}]",
            "session": session, "session_name": f"{session['emoji']} {session['name']}",
            "is_prime_session": session["is_prime"], "is_us_open_candle": session["session_id"] == "NEW_YORK",
            "pair": pair, "levels": levels, "candle_ts": int(cur["timestamp"]),
            "signal": "NEUTRAL", "signal_kind": None, "trigger_zone": None, "trigger_reason": "",
            "setup": (
                f"WAIT / NO TRADE (Bias: {levels.get('trend_bias', 'RANGE')} • "
                f"15m 50/200 EMA: {eng.round_asset_price(e50, ref_px)} / {eng.round_asset_price(e200, ref_px)})"
            ),
            "entry": ref_px, "entry2_sweep": 0.0, "stop_loss": 0.0, "tp1": 0.0, "tp2": 0.0,
        }
        out.update(position_metrics(pair, out["entry"], 0.0, out["entry"], out["entry"], margin_inr, leverage, usd_inr, entry2_sweep=0.0))

        prior = recs15[idx - 6:idx]
        prior_e50 = [float(r["EMA50"]) for r in prior]
        prior_e200 = [float(r["EMA200"]) for r in prior]
        sig = _detect_ema50_200_setup(
            recs15, idx, levels, e50, e200, prior_e50, prior_e200,
            allow_bear=self.allow_bear, allow_bull=self.allow_bull,
        )
        if sig:
            e_px = eng.round_asset_price(sig["entry"], ref_px)
            sl_px = eng.round_asset_price(sig["stop"], ref_px)
            tp1_px = eng.round_asset_price(sig["tp1"], ref_px)
            tp2_px = eng.round_asset_price(sig["tp2"], ref_px)
            out.update({
                "signal": sig["direction"],
                "signal_kind": "EMA50_200",
                "trigger_zone": sig["trigger_zone"],
                "trigger_reason": sig["reason"],
                "setup": f"{sig['direction']} 15m 50/200 EMA -> {'RL' if sig['direction'] == 'SHORT' else 'RH'}",
                "entry": e_px,
                "entry2_sweep": 0.0,
                "stop_loss": sl_px,
                "tp1": tp1_px,
                "tp2": tp2_px,
                "tp1_label": sig["tp1_label"],
                "tp2_label": sig["tp2_label"],
            })
            out.update(position_metrics(pair, e_px, sl_px, tp1_px, tp2_px, margin_inr, leverage, usd_inr, entry2_sweep=0.0))
        return self._stamp(out)

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr):
        if not levels:
            return {"BUY": None, "SELL": None, "note": ""}
        e50 = float(levels.get("EMA50_15m") or 0.0)
        e200 = float(levels.get("EMA200_15m") or 0.0)
        if e50 <= 0 or e200 <= 0:
            df15 = _closed_15m(pair, 10)
            if not df15.empty:
                e50 = float(df15["EMA50"].iloc[-1])
                e200 = float(df15["EMA200"].iloc[-1])
        px = float(live_price or e50 or levels["MID"])
        if e50 <= 0:
            e50 = px
        if e200 <= 0:
            e200 = e50 * (1.012 if e50 < px else 0.988)

        rh, rl = float(levels["RH"]), float(levels["RL"])

        # SELL Limit Plan: entry near min(e50, live) / e50 ceiling, SL > e200, TP2 = RL
        s_ent = eng.round_asset_price(e50, px)
        s_sl = eng.round_asset_price(max(e200 * 1.0025, s_ent * 1.004), px)
        s_tp2 = eng.round_asset_price(rl if rl < s_ent * 0.992 else s_ent * 0.976, px)
        s_tp1_d = min(abs(s_ent - s_tp2) * 0.50, s_ent * 0.020)
        s_tp1 = eng.round_asset_price(s_ent - max(s_tp1_d, s_ent * 0.008), px)
        sell_setup = {
            "direction": "SELL", "setup": "SHORT at 15m 50 EMA -> RL",
            "entry": s_ent, "entry2_sweep": 0.0, "stop_loss": s_sl, "tp1": s_tp1, "tp2": s_tp2,
            **position_metrics(pair, s_ent, s_sl, s_tp1, s_tp2, margin_inr, leverage, usd_inr, entry2_sweep=0.0),
        }

        # BUY Limit Plan: entry near 15m 50 EMA floor, SL < 15m 200 EMA, TP2 = RH
        b_ent = eng.round_asset_price(e50, px)
        b_sl = eng.round_asset_price(min(e200 * 0.9975, b_ent * 0.996), px)
        b_tp2 = eng.round_asset_price(rh if rh > b_ent * 1.008 else b_ent * 1.024, px)
        b_tp1_d = min(abs(b_tp2 - b_ent) * 0.50, b_ent * 0.020)
        b_tp1 = eng.round_asset_price(b_ent + max(b_tp1_d, b_ent * 0.008), px)
        buy_setup = {
            "direction": "BUY", "setup": "LONG at 15m 50 EMA -> RH",
            "entry": b_ent, "entry2_sweep": 0.0, "stop_loss": b_sl, "tp1": b_tp1, "tp2": b_tp2,
            **position_metrics(pair, b_ent, b_sl, b_tp1, b_tp2, margin_inr, leverage, usd_inr, entry2_sweep=0.0),
        }

        note = (
            f"15m 50/200 EMA: ${eng.round_asset_price(e50, px)} / ${eng.round_asset_price(e200, px)} "
            f"({levels.get('ema_15m_trend', '')}) | RL=${eng.round_asset_price(rl, px)}, RH=${eng.round_asset_price(rh, px)}"
        )
        return {"BUY": self._stamp(buy_setup), "SELL": self._stamp(sell_setup), "note": note}

    def chart_lines(self, levels, plan=None):
        lines = list(BoxTheorySweep().chart_lines(levels, plan)) if levels else []
        if levels and levels.get("EMA50_15m"):
            lines.append({"label": "15m 50 EMA (Pullback Zone)", "price": levels["EMA50_15m"], "color": "#a855f7", "dash": "solid"})
        if levels and levels.get("EMA200_15m"):
            lines.append({"label": "15m 200 EMA (SL Anchor)", "price": levels["EMA200_15m"], "color": "#eab308", "dash": "dot"})
        return lines

    def metric_badges(self, levels):
        if not levels:
            return []
        badges = []
        if levels.get("EMA50_15m"):
            badges.append({"label": "15m 50 EMA", "value": levels["EMA50_15m"]})
        if levels.get("EMA200_15m"):
            badges.append({"label": "15m 200 EMA", "value": levels["EMA200_15m"]})
        if levels.get("RL"):
            badges.append({"label": "RL Target (Short)", "value": levels["RL"]})
        if levels.get("RH"):
            badges.append({"label": "RH Target (Long)", "value": levels["RH"]})
        return badges

    def level_rows(self, levels, live_price):
        if not levels:
            return []
        rows = []
        for k, lbl in (("EMA200_15m", "15m 200 EMA (SL Wall)"), ("EMA50_15m", "15m 50 EMA (Pullback)"), ("RH", "Range High (Long TP2)"), ("RL", "Range Low (Short TP2)")):
            val = float(levels.get(k, 0.0) or 0.0)
            if val > 0:
                rows.append({"Level": lbl, "Price": val, "Distance %": round(((val - live_price) / live_price) * 100.0, 2) if live_price > 0 else 0.0})
        return rows

    def prepare_backtest(self, df, df_daily):
        box_ctx = BoxTheorySweep().prepare_backtest(df, df_daily)
        e50, e200 = _compute_warmed_15m_emas(df)
        return {"boxes": box_ctx["boxes"], "ema50_15m": e50, "ema200_15m": e200}

    def backtest_has_context(self, candle, ctx):
        return bool(ctx["boxes"].get(candle["date_str"]))

    def backtest_entry(self, idx, candle, ctx, records):
        if idx < 6:
            return None
        box = ctx["boxes"].get(candle["date_str"])
        if not box:
            return None
        e50 = float(ctx["ema50_15m"][idx])
        e200 = float(ctx["ema200_15m"][idx])
        prior_e50 = ctx["ema50_15m"][idx - 6:idx]
        prior_e200 = ctx["ema200_15m"][idx - 6:idx]
        return _detect_ema50_200_setup(
            records, idx, box, e50, e200, prior_e50, prior_e200,
            allow_bear=self.allow_bear, allow_bull=self.allow_bull,
        )


# ----------------------------------------------------------------------------------------------
# Combo Strategy (Priority 1: Box Theory Sweep -> Priority 2: 15m 50/200 EMA Pullback)
# ----------------------------------------------------------------------------------------------
class BoxPlusEma50200Strategy(Strategy):
    daily_warmup_days = 1000
    tp1_name, tp2_name = "TP1 (50% Book)", "TP2 (50% Structural Runner)"
    uses_live_price = True

    def __init__(self, sid: str, name: str, short_lbl: str, allow_bull_ema: bool = False, regime_adaptive: bool = False):
        self.id = sid
        self.name = name
        self.short = short_lbl
        self.allow_bull_ema = allow_bull_ema
        self.regime_adaptive = regime_adaptive
        if regime_adaptive:
            self.timeframe = "v34 + 3-Layer Intraday Trend Stack (1H/4H Structure+CHoCH + Session VWAP + 15m EMA/ADX)"
            self.description = (
                "v34 Core (50% TP1 Profit-Lock + Halfway Ratchet) upgraded with the 3-Layer Intraday Trend Stack: "
                "(1) 1H/4H HH/HL/LH/LL & CHoCH Early Reversal Warning, (2) 00:00 UTC Session VWAP slope & slicing-chop filter, "
                "(3) 15m EMA separation/slope & Wilder ADX(14) trend-strength gate (>25 strong, 20-25 confirm, <20 chop). "
                "Blocks Box fades against active intraday trends/CHoCH and gates 15m 50/200 EMA pullbacks by all 3 layers."
            )
        else:
            self.timeframe = (
                "15m Box Sweep (Long & Short) + Bear 15m 50/200 EMA Pullback"
                if not allow_bull_ema
                else "15m Box Sweep (Long & Short) + Bull & Bear 15m 50/200 EMA Pullback"
            )
            self.description = (
                "Priority 1 runs Strategy 1 (15m Box Theory Sweep Long & Short). When price trends away from Box "
                f"edges, Priority 2 runs 15m 50/200 EMA Pullback ({'Bear Short only' if not allow_bull_ema else 'Bull & Bear'})."
            )
        self.s1 = BoxTheorySweep()
        self.s4 = Ema50200PullbackStrategy(allow_bear=True, allow_bull=(allow_bull_ema or regime_adaptive))

    def compute_levels(self, pair):
        lv = self.s4.compute_levels(pair)
        if lv and self.regime_adaptive:
            try:
                st = eng.compute_pair_intraday_trend_stack(pair)
                if isinstance(st, dict) and float(st.get("vwap", 0.0) or 0.0) > 0:
                    ref_px = float(lv.get("RH") or lv.get("daily_close") or st["vwap"])
                    lv["Session_VWAP"] = eng.round_asset_price(st["vwap"], ref_px)
                    lv["Intraday_Regime"] = st.get("regime", "CHOP_RANGE")
                    lv["HTF_1H_Struct"] = st.get("s1_struct", "CHOP")
                    lv["HTF_1H_CHoCH"] = st.get("s1_choch", "NONE")
                    lv["ADX14_15m"] = float(st.get("adx", 0.0) or 0.0)
                    lv["Intraday_Summary"] = st.get("summary", "")
            except Exception:
                pass
        return lv

    def evaluate_signal(self, pair, levels=None, margin_inr=100000, leverage=DEFAULT_LEVERAGE, usd_inr=85.0):
        levels = levels or self.compute_levels(pair)
        sig1 = self.s1.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
        if self.regime_adaptive:
            reg_info = eng.compute_market_regime()
            day_reg = str(reg_info.get("regime", "RANGING_CHOP"))
            mkt_i_reg = str(reg_info.get("intraday_regime", "CHOP_RANGE"))
            p_stack = eng.compute_pair_intraday_trend_stack(pair)
            coin_i_reg = str(p_stack.get("regime", "CHOP_RANGE"))
            s1_choch = str(p_stack.get("s1_choch", "NONE"))
            has_stack = float(p_stack.get("vwap", 0.0) or 0.0) > 0

            if sig1 and sig1.get("signal") in ("LONG", "SHORT"):
                d1 = str(sig1.get("signal", "")).upper()
                box_blocked = (
                    (d1 == "SHORT" and (mkt_i_reg == "CLEAN_UPTREND" or coin_i_reg == "CLEAN_UPTREND" or s1_choch == "BULLISH_CHOCH"))
                    or (d1 == "LONG" and (mkt_i_reg == "CLEAN_DOWNTREND" or coin_i_reg == "CLEAN_DOWNTREND" or s1_choch == "BEARISH_CHOCH"))
                )
                if not box_blocked:
                    return sig1
                sig1 = dict(sig1)
                sig1["signal"] = "NEUTRAL"
                sig1["trigger_reason"] = (
                    f"3-Layer Intraday Trend Guard: Blocked Box {d1} against active intraday trend/CHoCH "
                    f"(Mkt15m={mkt_i_reg}, Coin={coin_i_reg}, 1H CHoCH={s1_choch})"
                )

            if day_reg == "RANGING_CHOP":
                return sig1
            if day_reg == "STRONG_DOWNTREND" and mkt_i_reg != "CLEAN_UPTREND" and ((not has_stack) or bool(p_stack.get("s4_bear_ok", False))):
                sig4 = self.s4.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
                if sig4 and sig4.get("signal") == "SHORT":
                    return sig4
            if day_reg == "STRONG_UPTREND" and mkt_i_reg != "CLEAN_DOWNTREND" and ((not has_stack) or bool(p_stack.get("s4_bull_ok", False))):
                sig4 = self.s4.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
                if sig4 and sig4.get("signal") == "LONG":
                    return sig4
            return sig1

        if sig1 and sig1.get("signal") in ("LONG", "SHORT"):
            return sig1
        sig4 = self.s4.evaluate_signal(pair, levels, margin_inr, leverage, usd_inr)
        if sig4 and sig4.get("signal") in ("LONG", "SHORT"):
            return sig4
        return sig1

    def plan_setups(self, pair, levels, live_price, margin_inr, leverage, usd_inr):
        return self.s1.plan_setups(pair, levels, live_price, margin_inr, leverage, usd_inr)

    def chart_lines(self, levels, plan=None):
        lines = list(self.s4.chart_lines(levels, plan))
        if levels and levels.get("Session_VWAP"):
            lines.append({"label": "Session VWAP (00:00 UTC)", "price": levels["Session_VWAP"], "color": "#06b6d4", "dash": "dash"})
        return lines

    def metric_badges(self, levels):
        badges = self.s1.metric_badges(levels) + self.s4.metric_badges(levels)
        if levels and levels.get("Session_VWAP"):
            badges.append({"label": "Session VWAP", "value": levels["Session_VWAP"]})
        if levels and levels.get("ADX14_15m"):
            badges.append({"label": "15m ADX(14)", "value": levels["ADX14_15m"]})
        return badges

    def level_rows(self, levels, live_price):
        rows = list(self.s1.level_rows(levels, live_price))
        if levels and levels.get("Session_VWAP"):
            vw = float(levels["Session_VWAP"])
            rows.append({
                "Level": f"Session VWAP ({levels.get('HTF_1H_Struct', 'CHOP')} | ADX {levels.get('ADX14_15m', 0):.1f})",
                "Price": vw,
                "Distance %": round(((vw - live_price) / live_price) * 100.0, 2) if live_price > 0 else 0.0,
            })
        return rows

    def prepare_backtest(self, df, df_daily):
        ctx1 = self.s1.prepare_backtest(df, df_daily)
        reg_map = {}
        intraday_mkt_map = {}
        stack_by_ts = {}
        if self.regime_adaptive:
            reg_map = dict(eng._PERSIST.get("backtest_regime_map") or {})
            if not reg_map and df_daily is not None and len(df_daily) >= 18:
                d = df_daily.copy().reset_index(drop=True)
                if "date_str" not in d.columns:
                    d["dt_ist"] = pd.to_datetime(d["timestamp"], unit="ms").dt.tz_localize("UTC").dt.tz_convert(IST)
                    d["date_str"] = d["dt_ist"].dt.strftime("%Y-%m-%d")
                e50_s = d["close"].ewm(span=50, adjust=False).mean().tolist()
                e200_s = d["close"].ewm(span=200, adjust=False).mean().tolist()
                closes = d["close"].tolist()
                dates = d["date_str"].tolist()
                for i in range(16, len(closes)):
                    pc, pe50, pe200 = float(closes[i - 1]), float(e50_s[i - 1]), float(e200_s[i - 1])
                    bf = 1.0 if (pc > pe50 and pc > pe200) else 0.0
                    brf = 1.0 if (pc < pe50 and pc < pe200) else 0.0
                    r14 = (pc / float(closes[i - 15]) - 1.0) * 100.0
                    r5 = (pc / float(closes[i - 6]) - 1.0) * 100.0
                    r2 = (pc / float(closes[i - 3]) - 1.0) * 100.0
                    reg_map[dates[i]] = eng.classify_universe_regime_from_stats(bf, brf, r14, r5, r2)
            intraday_mkt_map = dict(eng._PERSIST.get("backtest_intraday_regime_map") or {})
            if df is not None and not df.empty:
                st_list = eng.compute_intraday_3layer_series(df)
                stack_by_ts = {int(x["timestamp"]): x for x in st_list}
        return {
            "ctx1": ctx1,
            "ctx4": self.s4.prepare_backtest(df, df_daily),
            "boxes": ctx1["boxes"],
            "regime_map": reg_map,
            "intraday_mkt_map": intraday_mkt_map,
            "stack_by_ts": stack_by_ts,
        }

    def backtest_has_context(self, candle, ctx):
        return self.s1.backtest_has_context(candle, ctx["ctx1"])

    def backtest_entry(self, idx, candle, ctx, records):
        if self.regime_adaptive:
            ts_bar = int(candle.get("timestamp", 0) or 0)
            pair_name = ctx.get("pair")
            p_stacks = eng._PERSIST.get("backtest_pair_stacks") or {}
            st = (p_stacks.get(pair_name) or {}).get(ts_bar) if pair_name else None
            if st is None:
                st = (ctx.get("stack_by_ts") or {}).get(ts_bar)
            mkt_i_reg = (ctx.get("intraday_mkt_map") or {}).get(ts_bar, "CHOP_RANGE")
            coin_i_reg = str((st or {}).get("regime", "CHOP_RANGE"))
            s1_choch = str((st or {}).get("s1_choch", "NONE"))

            e1 = self.s1.backtest_entry(idx, candle, ctx["ctx1"], records)
            if e1:
                d1 = str(e1.get("direction", "")).upper()
                if d1 == "SHORT" and (mkt_i_reg == "CLEAN_UPTREND" or coin_i_reg == "CLEAN_UPTREND" or s1_choch == "BULLISH_CHOCH"):
                    e1 = None
                elif d1 == "LONG" and (mkt_i_reg == "CLEAN_DOWNTREND" or coin_i_reg == "CLEAN_DOWNTREND" or s1_choch == "BEARISH_CHOCH"):
                    e1 = None
            if e1:
                return e1

            day_reg = (ctx.get("regime_map") or {}).get(candle["date_str"], "RANGING_CHOP")
            if day_reg == "RANGING_CHOP":
                return None
            if day_reg == "STRONG_DOWNTREND" and mkt_i_reg != "CLEAN_UPTREND" and (st is None or bool(st.get("s4_bear_ok", False))):
                e4 = self.s4.backtest_entry(idx, candle, ctx["ctx4"], records)
                if e4 and e4.get("direction") == "SHORT":
                    return e4
            if day_reg == "STRONG_UPTREND" and mkt_i_reg != "CLEAN_DOWNTREND" and (st is None or bool(st.get("s4_bull_ok", False))):
                e4 = self.s4.backtest_entry(idx, candle, ctx["ctx4"], records)
                if e4 and e4.get("direction") == "LONG":
                    return e4
            return None

        e1 = self.s1.backtest_entry(idx, candle, ctx["ctx1"], records)
        if e1:
            return e1
        return self.s4.backtest_entry(idx, candle, ctx["ctx4"], records)


AUTOTRADE_MODE_CHOICES: list[tuple[str, str]] = [
    ("box_plus_ema50_200_regime", "Combo: v34 + 3-Layer Intraday Stack [1H/VWAP/ADX] (Recommended)"),
    ("box_plus_ema50_200_bear", "Combo: Box (L+S) + Bear 15m 50/200 EMA"),
    ("box_plus_ema50_200_both", "Combo: Box + Bull & Bear 15m 50/200 EMA"),
    ("box_theory", "Box Theory Sweep Only (v27)"),
    ("ema50_200", "15m 50/200 EMA Pullback Only"),
]
DEFAULT_AUTOTRADE_MODE = "box_plus_ema50_200_regime"


def resolve_autotrade_mode(mode: str | None) -> str:
    valid = {k for k, _ in AUTOTRADE_MODE_CHOICES}
    m = str(mode or "").strip()
    return m if m in valid else DEFAULT_AUTOTRADE_MODE


def autotrade_mode_label(mode: str | None) -> str:
    m = resolve_autotrade_mode(mode)
    return dict(AUTOTRADE_MODE_CHOICES).get(m, m)


def autotrade_mode_strategy_ids(mode: str | None) -> list[str]:
    """Ordered component strategies for live scanning under a given AutoTrade/Backtest mode."""
    m = resolve_autotrade_mode(mode)
    if m == "box_theory":
        return ["box_theory"]
    if m == "ema50_200":
        return ["ema50_200"]
    if m == "box_plus_ema50_200_regime":
        try:
            reg = str(eng.compute_market_regime().get("regime", "RANGING_CHOP"))
            if reg == "RANGING_CHOP":
                return ["box_theory"]
        except Exception:
            pass
    return ["box_theory", "ema50_200"]


# ----------------------------------------------------------------------------------------------
# Registry
# ----------------------------------------------------------------------------------------------
STRATEGY_REGISTRY: dict[str, Strategy] = {
    BoxTheorySweep.id: BoxTheorySweep(),
    AtrReversal.id: AtrReversal(),
    Ema9RetestStrategy.id: Ema9RetestStrategy(),
    Ema50200PullbackStrategy.id: Ema50200PullbackStrategy(allow_bear=True, allow_bull=True),
    "box_plus_ema50_200_regime": BoxPlusEma50200Strategy(
        sid="box_plus_ema50_200_regime",
        name="Combo: Regime-Adaptive [Box + Auto Trend EMA]",
        short_lbl="Combo (Regime-Adaptive)",
        allow_bull_ema=True,
        regime_adaptive=True,
    ),
    "box_plus_ema50_200_bear": BoxPlusEma50200Strategy(
        sid="box_plus_ema50_200_bear",
        name="Combo: Box (L+S) + Bear 15m 50/200 EMA",
        short_lbl="Combo (Box + Bear EMA)",
        allow_bull_ema=False,
    ),
    "box_plus_ema50_200_both": BoxPlusEma50200Strategy(
        sid="box_plus_ema50_200_both",
        name="Combo: Box + Bull & Bear 15m 50/200 EMA",
        short_lbl="Combo (Box + Bull&Bear EMA)",
        allow_bull_ema=True,
    ),
    CombinedPriorityStrategy.id: CombinedPriorityStrategy(include_strategy3_entry=True),
}
DEFAULT_STRATEGY_ID = BoxTheorySweep.id


def get_strategy(strategy_id: str | None) -> Strategy:
    return STRATEGY_REGISTRY.get(strategy_id or DEFAULT_STRATEGY_ID, STRATEGY_REGISTRY[DEFAULT_STRATEGY_ID])


def list_strategies() -> list[Strategy]:
    return [
        STRATEGY_REGISTRY[BoxTheorySweep.id],
        STRATEGY_REGISTRY[Ema50200PullbackStrategy.id],
        STRATEGY_REGISTRY[AtrReversal.id],
        STRATEGY_REGISTRY[Ema9RetestStrategy.id],
    ]


def strategy_by_name(name: str) -> Strategy | None:
    return next((s for s in STRATEGY_REGISTRY.values() if s.name == name), None)


def setup_tag(strategy_id: str, kind: str) -> str:
    """Session-state tag for execution inputs; Box Theory keeps the legacy BUY / SELL / SIGNAL tags."""
    return kind if strategy_id == DEFAULT_STRATEGY_ID else f"{strategy_id}_{kind}"
