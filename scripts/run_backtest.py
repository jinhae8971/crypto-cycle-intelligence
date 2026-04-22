"""Crypto Cycle Intelligence — Historical Backtest.

Validates the CCS model against 5 well-known crypto cycle events
since 2017. Generates `backtest_results.json` matching the schema
used by ASCI for consistency across systems.

Data source: yfinance BTC-USD (free, no API key, gives full history).
Indicators: technical + on-chain proxies that can be computed from
just price+volume time series (Pi Cycle, Mayer, Weekly RSI, Daily RSI,
distance from 200D SMA, etc.).
"""
from __future__ import annotations

import json
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# ══════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════

OUT_FILE = Path(__file__).resolve().parent.parent / "data" / "backtest_results.json"
OUT_FILE.parent.mkdir(parents=True, exist_ok=True)

# 5 well-documented Bitcoin cycle events 2017→present
CYCLE_EVENTS = [
    {
        "name": "2017 Cycle Top",
        "target_date": "2017-12-17",
        "expected_phase": "Late Bull / Euphoria",
        "expected_score": ">70",
        "context": "BTC reached $19,800 amid retail mania. Pi Cycle Top triggered on Dec 17.",
        "type": "top",
    },
    {
        "name": "2018 Crypto Winter Bottom",
        "target_date": "2018-12-15",
        "expected_phase": "Capitulation",
        "expected_score": "<25",
        "context": "BTC bottom at ~$3,200. -84% drawdown from 2017 peak. Maximum capitulation.",
        "type": "bottom",
    },
    {
        "name": "2020 COVID Crash",
        "target_date": "2020-03-13",
        "expected_phase": "Capitulation",
        "expected_score": "<25",
        "context": "Black Thursday: BTC crashed 50% in 24h. Brief 4-week shock — long-horizon indicators (Pi Cycle, Mayer) lag behind such fast moves.",
        "type": "bottom",
    },
    {
        "name": "2021 Pi Cycle Top Trigger",
        "target_date": "2021-04-13",
        "expected_phase": "Late Bull / Euphoria",
        "expected_score": ">70",
        "context": "BTC ATH at $64,895. Pi Cycle Top officially triggered. (Nov 2021 second peak followed but model already warned at first peak.)",
        "type": "top",
    },
    {
        "name": "2022 FTX Bottom",
        "target_date": "2022-11-21",
        "expected_phase": "Capitulation",
        "expected_score": "<25",
        "context": "BTC bottom at ~$15,500 post-FTX collapse. -77% drawdown. Major capitulation.",
        "type": "bottom",
    },
]

# Same scoring rules as in run_pipeline.py — keep these in sync!
RULES = [
    # Valuation
    {"metric": "pi_cycle_ratio", "dimension": "valuation",   "bottom": 0.20, "top": 1.00, "weight": 1.5},
    {"metric": "mayer_multiple", "dimension": "valuation",   "bottom": 0.80, "top": 2.40, "weight": 1.0},
    # Technical
    {"metric": "weekly_rsi",     "dimension": "technical",   "bottom": 30,   "top": 85,   "weight": 1.5},
    {"metric": "daily_rsi",      "dimension": "technical",   "bottom": 30,   "top": 75,   "weight": 1.0},
    {"metric": "dist_sma200_pct","dimension": "technical",   "bottom": -25,  "top": 80,   "weight": 1.0},
    {"metric": "wk52_pos_pct",   "dimension": "technical",   "bottom": 5,    "top": 95,   "weight": 1.0},
    # On-chain proxy (volume-derived) — keeps onchain dim populated for backtest
    {"metric": "vol_zscore_30d", "dimension": "onchain",     "bottom": -1.5, "top": 3.0,  "weight": 1.0},
]

DIMENSION_WEIGHTS = {
    "valuation":   0.30,
    "onchain":     0.20,
    "sentiment":   0.15,
    "derivatives": 0.10,
    "macro":       0.10,
    "technical":   0.15,
}

PHASE_RANGES = [
    (0, 20,   "Deep Bottom",    "🧊"),
    (20, 40,  "Accumulation",   "🌱"),
    (40, 60,  "Mid-Cycle",      "📈"),
    (60, 80,  "Late Markup",    "🔥"),
    (80, 101, "Distribution",   "🚨"),
]


def phase_for(score: float | None) -> str:
    if score is None or np.isnan(score):
        return "Unknown"
    for lo, hi, name, _ in PHASE_RANGES:
        if lo <= score < hi:
            return name
    return "Distribution"


# ══════════════════════════════════════════════════════════════
# Indicator computations
# ══════════════════════════════════════════════════════════════

def compute_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Add all indicator columns to a daily OHLCV BTC dataframe."""
    px = df["Close"]
    out = pd.DataFrame(index=df.index)
    out["price"] = px

    # Pi Cycle ratio: 111DMA / (350DMA × 2)
    sma111 = px.rolling(111).mean()
    sma350 = px.rolling(350).mean()
    out["pi_cycle_ratio"] = sma111 / (sma350 * 2)

    # Mayer multiple
    sma200 = px.rolling(200).mean()
    out["mayer_multiple"] = px / sma200

    # Distance from 200D SMA (%)
    out["dist_sma200_pct"] = (px / sma200 - 1) * 100

    # 52-week (252-day) position percentile
    rolling_min = px.rolling(252).min()
    rolling_max = px.rolling(252).max()
    out["wk52_pos_pct"] = ((px - rolling_min) / (rolling_max - rolling_min) * 100)

    # Daily RSI (14)
    out["daily_rsi"] = compute_rsi(px, 14)

    # Weekly RSI (resample to W, compute RSI, reindex back to daily)
    weekly = px.resample("W").last()
    w_rsi = compute_rsi(weekly, 14)
    out["weekly_rsi"] = w_rsi.reindex(out.index, method="ffill")

    # Volume z-score (30d) — proxy for on-chain activity intensity
    if "Volume" in df.columns:
        vol = df["Volume"].astype(float)
        out["vol_zscore_30d"] = (vol - vol.rolling(30).mean()) / vol.rolling(30).std()
    else:
        out["vol_zscore_30d"] = np.nan

    return out


def score_indicator(value: float, rule: dict) -> float | None:
    if value is None or pd.isna(value):
        return None
    if rule["top"] == rule["bottom"]:
        return 50.0
    pct = (value - rule["bottom"]) / (rule["top"] - rule["bottom"])
    return max(0.0, min(100.0, pct * 100))


def compute_ccs_at(indicators_row: pd.Series) -> tuple[float | None, dict]:
    """Apply scoring rules to a single timestamp's indicator row."""
    by_dim: dict[str, list[tuple[float, float]]] = {d: [] for d in DIMENSION_WEIGHTS}
    for rule in RULES:
        v = indicators_row.get(rule["metric"])
        s = score_indicator(v, rule)
        if s is not None:
            by_dim[rule["dimension"]].append((s, rule["weight"]))

    dim_scores = {}
    for dim, items in by_dim.items():
        if items:
            tw = sum(w for _, w in items)
            dim_scores[dim] = sum(s * w for s, w in items) / tw
        else:
            dim_scores[dim] = None

    present = {d: s for d, s in dim_scores.items() if s is not None}
    if not present:
        return None, dim_scores
    total_w = sum(DIMENSION_WEIGHTS[d] for d in present)
    composite = sum(s * DIMENSION_WEIGHTS[d] for d, s in present.items()) / total_w
    return composite, dim_scores


# ══════════════════════════════════════════════════════════════
# Forward returns
# ══════════════════════════════════════════════════════════════

def forward_returns(df: pd.DataFrame, anchor_date: pd.Timestamp) -> dict:
    """Compute 1m / 3m / 6m / 12m forward returns from BTC price at anchor."""
    if anchor_date not in df.index:
        # find nearest
        idx = df.index.searchsorted(anchor_date)
        if idx >= len(df):
            return {}
        anchor_date = df.index[idx]
    anchor_px = df.loc[anchor_date, "Close"]
    result = {}
    for label, days in [("1m", 30), ("3m", 90), ("6m", 180), ("12m", 365)]:
        target = anchor_date + pd.Timedelta(days=days)
        if target > df.index[-1]:
            continue
        idx = df.index.searchsorted(target)
        if idx >= len(df):
            continue
        future_px = df["Close"].iloc[idx]
        result[label] = round(float((future_px / anchor_px - 1) * 100), 1)
    return result


# ══════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════

def main() -> int:
    print("=" * 64)
    print(f"  CCI Backtest  ·  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 64)

    # ── Fetch BTC history ──
    print("\n📥 Fetching BTC-USD daily history (2016 → present)...")
    btc = yf.Ticker("BTC-USD").history(start="2016-01-01", auto_adjust=True)
    if btc.empty:
        print("❌ Failed to fetch BTC history")
        return 1
    btc.index = btc.index.tz_localize(None)
    print(f"  Got {len(btc)} daily bars · {btc.index[0].date()} → {btc.index[-1].date()}")
    print(f"  BTC range: ${btc['Close'].min():,.0f} → ${btc['Close'].max():,.0f}")

    # ── Compute indicators across full history ──
    print("\n⚙️  Computing indicators across full history...")
    indicators = compute_indicators(btc)
    print(f"  Indicator columns: {[c for c in indicators.columns if c != 'price']}")

    # ── Compute CCS time series (weekly samples for chart) ──
    print("\n📊 Computing CCS time series...")
    ccs_series = []
    for ts, row in indicators.iterrows():
        score, _ = compute_ccs_at(row)
        if score is not None:
            ccs_series.append({"ts": ts.date().isoformat(),
                               "ccs": round(score, 2),
                               "btc": round(float(row["price"]), 0)})
    print(f"  Computed CCS for {len(ccs_series)} days")

    # Down-sample to weekly for the chart payload
    weekly_ts = pd.DataFrame(ccs_series).set_index("ts")
    weekly_ts.index = pd.to_datetime(weekly_ts.index)
    weekly_resampled = weekly_ts.resample("W").last().dropna()
    timeseries_weekly = [
        {"ts": idx.date().isoformat(), "ccs": float(row["ccs"]), "btc": float(row["btc"])}
        for idx, row in weekly_resampled.iterrows()
    ]
    print(f"  Weekly samples for chart: {len(timeseries_weekly)}")

    # ── Validate against historical events ──
    print("\n🎯 Validating against historical cycle events...\n")
    event_results = []
    correct_count = 0

    for event in CYCLE_EVENTS:
        target = pd.Timestamp(event["target_date"])
        # Find nearest available date
        if target not in indicators.index:
            idx = indicators.index.searchsorted(target)
            actual_date = indicators.index[min(idx, len(indicators) - 1)]
        else:
            actual_date = target

        score, dim_scores = compute_ccs_at(indicators.loc[actual_date])
        actual_phase = phase_for(score)

        # Evaluate match (CCI phase semantics)
        expected = event["expected_phase"]
        if "Capitulation" in expected and actual_phase in ("Deep Bottom", "Accumulation"):
            match = "✅"
            signal_correct = True
        elif "Late Bull" in expected and actual_phase in ("Late Markup", "Distribution"):
            match = "✅"
            signal_correct = True
        elif "Recovery" in expected and actual_phase in ("Accumulation", "Mid-Cycle"):
            match = "✅"
            signal_correct = True
        else:
            match = "⚠️"
            signal_correct = False

        if match == "✅":
            correct_count += 1

        fwd = forward_returns(btc, actual_date)
        btc_px = float(btc.loc[actual_date, "Close"])

        result = {
            "name":            event["name"],
            "target_date":     event["target_date"],
            "actual_date":     actual_date.date().isoformat(),
            "expected_phase":  expected,
            "expected_score":  event["expected_score"],
            "actual_score":    round(float(score), 1) if score is not None else None,
            "actual_phase":    actual_phase,
            "match":           match,
            "context":         event["context"],
            "btc_price":       round(btc_px, 0),
            "forward_returns": fwd,
            "signal_correct":  signal_correct,
        }
        event_results.append(result)

        score_str = f"{score:.1f}" if score is not None else "N/A"
        print(f"  {match} {event['name']:<35} → score {score_str:>6} ({actual_phase})")
        print(f"     BTC ${btc_px:,.0f} · Forward: {fwd}")

    accuracy = correct_count / len(CYCLE_EVENTS) * 100
    print(f"\n  Overall accuracy: {correct_count}/{len(CYCLE_EVENTS)} ({accuracy:.0f}%)")

    # ── Statistics ──
    print("\n📈 Computing statistics...")
    all_scores = [s["ccs"] for s in ccs_series]
    ccs_stats = {
        "min":    round(min(all_scores), 2),
        "max":    round(max(all_scores), 2),
        "mean":   round(float(np.mean(all_scores)), 2),
        "std":    round(float(np.std(all_scores)), 2),
        "median": round(float(np.median(all_scores)), 2),
    }
    print(f"  CCS stats: {ccs_stats}")

    # Phase distribution
    phase_counts = {p[2]: 0 for p in PHASE_RANGES}
    for s in all_scores:
        phase_counts[phase_for(s)] += 1
    total = sum(phase_counts.values())
    phase_distribution_pct = {p: round(c / total * 100, 2) for p, c in phase_counts.items()}
    print(f"  Phase distribution: {phase_distribution_pct}")

    # ── Indicator coverage (which ones we successfully used) ──
    indicators_used = [
        col for col in indicators.columns
        if col != "price" and indicators[col].notna().sum() > 100
    ]

    # ── Build payload ──
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "backtest_window": {
            "start":  btc.index[0].date().isoformat(),
            "end":    btc.index[-1].date().isoformat(),
            "n_days": len(btc),
        },
        "indicators_used":         indicators_used,
        "event_results":           event_results,
        "ccs_stats":               ccs_stats,
        "phase_distribution_pct":  phase_distribution_pct,
        "timeseries_weekly":       timeseries_weekly,
        "model_version":           "1.0",
        "accuracy_pct":            round(accuracy, 1),
    }

    # ── Persist ──
    OUT_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"\n💾 Saved: {OUT_FILE} ({OUT_FILE.stat().st_size:,} bytes)")
    print("\n✅ Backtest complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
