"""Crypto Cycle Intelligence — Serverless Pipeline.

Runs on GitHub Actions, fetches all free APIs, computes CCS,
writes JSON files consumed by GitHub Pages dashboard,
and sends Telegram report.

Architecture: Stateless. Each run is independent. History persisted via
Git commits of data/*.json files.
"""
from __future__ import annotations

import os
import sys
import json
import time
import traceback
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests
import numpy as np
import pandas as pd


# ══════════════════════════════════════════════════════════════
# Configuration
# ══════════════════════════════════════════════════════════════

DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
SITE_DIR = Path(os.environ.get("SITE_DIR", "docs/site"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

LATEST_FILE = DATA_DIR / "latest.json"
HISTORY_FILE = DATA_DIR / "history.json"
SNAPSHOTS_DIR = DATA_DIR / "snapshots"
SNAPSHOTS_DIR.mkdir(exist_ok=True)

MAX_HISTORY_DAYS = 730   # Keep 2 years of daily snapshots in history.json
TIMEOUT = 25


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


# ══════════════════════════════════════════════════════════════
# Robust HTTP Fetch (retry, graceful failure)
# ══════════════════════════════════════════════════════════════

def robust_get(
    url: str, params: dict | None = None,
    retries: int = 3, backoff: float = 1.5,
) -> dict | list | None:
    """GET with retries on 5xx/network errors. Returns None on final failure."""
    last_err: str = ""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, timeout=TIMEOUT,
                             headers={"User-Agent": "cci-serverless/1.0"})
            if r.status_code == 429:
                # Rate limited — honor Retry-After
                wait = int(r.headers.get("Retry-After", "30"))
                print(f"  [429] {url[:60]}... waiting {wait}s")
                time.sleep(wait)
                continue
            if 500 <= r.status_code < 600:
                last_err = f"HTTP {r.status_code}"
                print(f"  [{r.status_code}] attempt {attempt+1}/{retries}")
                time.sleep(backoff * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.exceptions.RequestException as e:
            last_err = str(e)[:100]
            if attempt < retries - 1:
                time.sleep(backoff * (attempt + 1))
    print(f"  [FAIL] {url[:60]}... final error: {last_err}")
    return None


# ══════════════════════════════════════════════════════════════
# Data Fetchers (6 free sources, no API key except FRED)
# ══════════════════════════════════════════════════════════════

def fetch_btc_history(days: int = 365) -> pd.DataFrame | None:
    """CoinGecko BTC daily price history."""
    days = min(days, 365)
    data = robust_get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
        params={"vs_currency": "usd", "days": str(days), "interval": "daily"},
    )
    if not data or "prices" not in data:
        return None
    df = pd.DataFrame(data["prices"], columns=["ts_ms", "price"])
    df["ts"] = pd.to_datetime(df["ts_ms"], unit="ms", utc=True)
    df = df.set_index("ts").drop(columns="ts_ms").sort_index()
    print(f"  [ok] CoinGecko history: {len(df)} days")
    return df


def fetch_global_market() -> dict | None:
    data = robust_get("https://api.coingecko.com/api/v3/global")
    if not data or "data" not in data:
        return None
    d = data["data"]
    result = {
        "total_mcap_usd":  d["total_market_cap"]["usd"],
        "total_vol_24h":   d["total_volume"]["usd"],
        "btc_dominance":   d["market_cap_percentage"]["btc"],
        "eth_dominance":   d["market_cap_percentage"]["eth"],
        "mcap_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
        "active_cryptos":  d.get("active_cryptocurrencies", 0),
    }
    print(f"  [ok] Global: BTC.D={result['btc_dominance']:.1f}%")
    return result


def fetch_fear_greed(limit: int = 90) -> dict | None:
    data = robust_get(f"https://api.alternative.me/fng/?limit={limit}")
    if not data or "data" not in data:
        return None
    entries = data["data"]
    latest = entries[0]
    history = [
        {"ts": int(e["timestamp"]), "value": int(e["value"]),
         "classification": e["value_classification"]}
        for e in reversed(entries)
    ]
    result = {
        "value": int(latest["value"]),
        "classification": latest["value_classification"],
        "history": history,
    }
    print(f"  [ok] F&G: {result['value']} ({result['classification']})")
    return result


def fetch_pi_cycle() -> dict | None:
    """bitcoin.com Pi Cycle Top indicator (free, no rate limit)."""
    data = robust_get(
        "https://charts.bitcoin.com/api/v1/charts/pi-cycle-top",
        params={"interval": "daily", "timespan": "30d"},
    )
    if not data or "data" not in data:
        return None
    d = data["data"]
    ma111 = d.get("ma111", [])
    ma350x2 = d.get("ma350x2", [])
    if not ma111 or not ma350x2:
        return None
    last111 = float(ma111[-1]["value"])
    last350x2 = float(ma350x2[-1]["value"])
    result = {
        "ma111": last111,
        "ma350x2": last350x2,
        "ratio": last111 / last350x2,
        "crosses": d.get("crosses", []),
    }
    print(f"  [ok] Pi Cycle ratio: {result['ratio']:.3f}")
    return result


def fetch_bgeometrics(endpoint: str, field_name: str) -> float | None:
    """BGeometrics on-chain metric (8 req/hr hard limit)."""
    data = robust_get(
        f"https://api.bitcoin-data.com/v1/{endpoint}/last",
        retries=1,  # Don't waste rate limit budget on retries
    )
    if data is None:
        return None
    if not isinstance(data, dict) or field_name not in data:
        return None
    v = float(data[field_name])
    print(f"  [ok] {endpoint}: {v}")
    return v


def fetch_bybit_funding() -> float | None:
    """Bybit BTC perp funding rate (Korea-friendly)."""
    data = robust_get(
        "https://api.bybit.com/v5/market/funding/history",
        params={"category": "linear", "symbol": "BTCUSDT", "limit": "1"},
    )
    if not data:
        return None
    try:
        rows = data.get("result", {}).get("list", [])
        if rows:
            v = float(rows[0]["fundingRate"])
            print(f"  [ok] Funding: {v:.4%}")
            return v
    except Exception as e:
        print(f"  [err] Funding parse: {e}")
    return None


# ══════════════════════════════════════════════════════════════
# Technical Indicators
# ══════════════════════════════════════════════════════════════

def compute_technicals(df: pd.DataFrame) -> dict:
    if df is None or len(df) < 50:
        return {}
    prices = df["price"]
    result: dict[str, Any] = {"current_price": float(prices.iloc[-1])}

    if len(prices) >= 2:
        result["change_24h_pct"] = float((prices.iloc[-1] / prices.iloc[-2] - 1) * 100)

    if len(prices) >= 200:
        sma200 = float(prices.rolling(200).mean().iloc[-1])
        result["sma_200"] = sma200
        result["mayer_multiple"] = float(prices.iloc[-1] / sma200)

    if len(prices) >= 350:
        sma111 = float(prices.rolling(111).mean().iloc[-1])
        sma350 = float(prices.rolling(350).mean().iloc[-1])
        result["sma_111"] = sma111
        result["sma_350_x2"] = sma350 * 2
        result["pi_cycle_ratio"] = sma111 / (sma350 * 2)

    # RSI
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    daily_rsi = 100 - (100 / (1 + rs))
    if not np.isnan(daily_rsi.iloc[-1]):
        result["daily_rsi"] = float(daily_rsi.iloc[-1])

    # Weekly RSI
    weekly = prices.resample("W").last()
    if len(weekly) >= 14:
        delta_w = weekly.diff()
        gain_w = delta_w.where(delta_w > 0, 0.0)
        loss_w = -delta_w.where(delta_w < 0, 0.0)
        avg_gain_w = gain_w.ewm(alpha=1/14, adjust=False).mean()
        avg_loss_w = loss_w.ewm(alpha=1/14, adjust=False).mean()
        rs_w = avg_gain_w / avg_loss_w.replace(0, np.nan)
        w_rsi = 100 - (100 / (1 + rs_w))
        if not np.isnan(w_rsi.iloc[-1]):
            result["weekly_rsi"] = float(w_rsi.iloc[-1])

    return result


# ══════════════════════════════════════════════════════════════
# CCS Scoring Engine
# ══════════════════════════════════════════════════════════════

@dataclass
class ScoringRule:
    metric: str
    dimension: str
    bottom: float
    top: float
    weight: float = 1.0

    def score(self, value: float | None) -> float | None:
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        if self.top == self.bottom:
            return 50.0
        pct = (value - self.bottom) / (self.top - self.bottom)
        return max(0.0, min(100.0, pct * 100))


DIMENSION_WEIGHTS = {
    "valuation":   0.25,
    "onchain":     0.20,
    "sentiment":   0.15,
    "derivatives": 0.15,
    "macro":       0.10,
    "technical":   0.15,
}

RULES: list[ScoringRule] = [
    # Valuation
    ScoringRule("pi_cycle_ratio",  "valuation", 0.20, 1.00, 1.5),
    ScoringRule("mvrv_zscore",     "valuation", -1.0, 7.00, 1.5),
    ScoringRule("mayer_multiple",  "valuation", 0.80, 2.40, 1.0),
    ScoringRule("nupl",            "valuation", -0.25, 0.75, 1.0),
    # On-chain
    ScoringRule("puell_multiple",  "onchain", 0.30, 4.00, 1.5),
    ScoringRule("sopr",            "onchain", 0.97, 1.05, 1.0),
    # Sentiment
    ScoringRule("fear_greed_index", "sentiment", 10, 90, 1.5),
    # Derivatives
    ScoringRule("funding_rate",    "derivatives", -0.0002, 0.0005, 1.0),
    # Technical
    ScoringRule("weekly_rsi",      "technical", 30, 85, 1.5),
    ScoringRule("daily_rsi",       "technical", 30, 75, 1.0),
]

PHASE_RANGES = [
    (0, 20, "Deep Bottom", "🧊", "#0a4d68"),
    (20, 40, "Accumulation", "🌱", "#3a8891"),
    (40, 60, "Mid-Cycle", "📈", "#f6c945"),
    (60, 80, "Late Markup", "🔥", "#e76f51"),
    (80, 101, "Distribution Top", "🚨", "#c1121f"),
]


def phase_for(score: float | None) -> tuple[str, str, str]:
    if score is None or np.isnan(score):
        return "Unknown", "❓", "#6b7280"
    for lo, hi, name, emoji, color in PHASE_RANGES:
        if lo <= score < hi:
            return name, emoji, color
    return "Distribution Top", "🚨", "#c1121f"


def compute_ccs(raw: dict[str, float]) -> dict:
    by_dim: dict[str, list[tuple[float, float]]] = {d: [] for d in DIMENSION_WEIGHTS}
    indicators = []
    for rule in RULES:
        val = raw.get(rule.metric)
        s = rule.score(val)
        indicators.append({
            "metric": rule.metric, "raw": val, "score": s,
            "dimension": rule.dimension,
            "bottom": rule.bottom, "top": rule.top,
        })
        if s is not None:
            by_dim[rule.dimension].append((s, rule.weight))

    dim_scores = {}
    for dim, items in by_dim.items():
        if items:
            tw = sum(w for _, w in items)
            dim_scores[dim] = sum(s * w for s, w in items) / tw
        else:
            dim_scores[dim] = None

    present = {d: s for d, s in dim_scores.items() if s is not None}
    if not present:
        return {"composite": None, "phase": "Unknown", "emoji": "❓",
                "color": "#6b7280",
                "dimensions": dim_scores, "indicators": indicators}

    total_w = sum(DIMENSION_WEIGHTS[d] for d in present)
    ccs = sum(s * DIMENSION_WEIGHTS[d] for d, s in present.items()) / total_w
    name, emoji, color = phase_for(ccs)
    return {
        "composite": round(ccs, 2),
        "phase": name, "emoji": emoji, "color": color,
        "dimensions": {d: round(v, 2) if v is not None else None for d, v in dim_scores.items()},
        "indicators": indicators,
        "weights_used": {d: round(DIMENSION_WEIGHTS[d]/total_w, 3) for d in present},
    }


# ══════════════════════════════════════════════════════════════
# JSON Persistence (Git as DB)
# ══════════════════════════════════════════════════════════════

def load_history() -> list[dict]:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "snapshots" in data:
            return data["snapshots"]
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"  [warn] history load failed: {e}")
        return []


def append_history(snapshot: dict) -> list[dict]:
    history = load_history()
    # Deduplicate by date (keep latest entry per day)
    snapshot_date = snapshot["ts"][:10]  # YYYY-MM-DD
    history = [h for h in history if h.get("ts", "")[:10] != snapshot_date]
    history.append(snapshot)
    history.sort(key=lambda h: h.get("ts", ""))

    # Trim to MAX_HISTORY_DAYS most recent
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_HISTORY_DAYS)
    history = [
        h for h in history
        if datetime.fromisoformat(h["ts"].replace("Z", "+00:00")) >= cutoff
    ]
    return history


def save_json(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, indent=2, default=str, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  [saved] {path} ({path.stat().st_size:,} bytes)")


# ══════════════════════════════════════════════════════════════
# Telegram
# ══════════════════════════════════════════════════════════════

def send_telegram(message: str, token: str, chat_id: str) -> bool:
    if not token or not chat_id:
        print("  [skip] Telegram credentials missing")
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": chat_id, "text": message,
            "parse_mode": "Markdown", "disable_web_page_preview": True,
        }, timeout=20)
        r.raise_for_status()
        print(f"  [ok] Telegram sent ({len(message)} chars)")
        return True
    except Exception as e:
        print(f"  [err] Telegram markdown failed: {e}")
        # Plain text fallback
        try:
            r = requests.post(url, json={
                "chat_id": chat_id, "text": message[:4000],
            }, timeout=20)
            r.raise_for_status()
            return True
        except Exception as e2:
            print(f"  [err] Telegram plain fallback: {e2}")
            return False


def format_telegram_report(ccs: dict, global_mkt: dict | None,
                            tech: dict, raw: dict,
                            pages_url: str = "") -> str:
    now_kst = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=9))
    ).strftime("%Y-%m-%d %H:%M KST")

    score = ccs.get("composite")
    phase = ccs.get("phase", "Unknown")
    emoji = ccs.get("emoji", "❓")
    price = tech.get("current_price")

    lines = [
        "📊 *Crypto Cycle Daily Report*",
        f"_{now_kst}_",
        "",
    ]

    if price:
        l = f"💰 *BTC:* ${price:,.0f}"
        ch = tech.get("change_24h_pct")
        if ch is not None:
            l += f"  {'🟢' if ch >= 0 else '🔴'} {ch:+.2f}% (24h)"
        lines.append(l)
        if global_mkt:
            lines.append(f"📐 BTC.D: {global_mkt['btc_dominance']:.1f}%  |  "
                         f"ETH.D: {global_mkt['eth_dominance']:.1f}%")
            lines.append(f"💹 Total Mcap: ${global_mkt['total_mcap_usd']/1e12:.2f}T")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    score_str = f"*{score:.0f}* / 100" if score is not None else "N/A"
    lines.append(f"{emoji} *{phase}*")
    lines.append(f"Composite Cycle Score: {score_str}")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")

    lines.append("*📊 6-Dimension Breakdown*")
    for dim in ["valuation", "onchain", "sentiment", "derivatives", "macro", "technical"]:
        v = ccs["dimensions"].get(dim)
        if v is None:
            lines.append(f"▫️ `{dim:<12}` — no data")
        else:
            bar_len = int(v / 10)
            bar = "█" * bar_len + "░" * (10 - bar_len)
            lines.append(f"▪️ `{dim:<12}` {bar} {v:.0f}")
    lines.append("")

    scored = [i for i in ccs["indicators"] if i["score"] is not None]
    scored.sort(key=lambda i: abs(i["score"] - 50), reverse=True)
    if scored:
        lines.append("*🎯 Top 5 Extreme Indicators*")
        for i in scored[:5]:
            tag = "🔴" if i["score"] > 70 else ("🟢" if i["score"] < 30 else "🟡")
            raw_str = f"{i['raw']:.3f}" if abs(i['raw']) < 100 else f"{i['raw']:.1f}"
            lines.append(f"{tag} `{i['metric']:<16}` {raw_str:>8}  (→ {i['score']:.0f})")
        lines.append("")

    # Alerts
    alerts = []
    if raw.get("pi_cycle_ratio") and raw["pi_cycle_ratio"] >= 1.0:
        alerts.append(f"🚨 PI CYCLE TOP CROSS! ({raw['pi_cycle_ratio']:.3f})")
    if raw.get("mvrv_zscore") is not None:
        if raw["mvrv_zscore"] >= 7:
            alerts.append(f"🚨 MVRV-Z euphoria: {raw['mvrv_zscore']:.2f}")
        elif raw["mvrv_zscore"] <= 0:
            alerts.append(f"🌱 MVRV-Z capitulation: {raw['mvrv_zscore']:.2f}")
    if alerts:
        lines.append("*⚠️ Key Alerts*")
        for a in alerts:
            lines.append(a)
        lines.append("")

    if pages_url:
        lines.append(f"🔗 [Dashboard]({pages_url})")
    lines.append("_Model v1.0 · Serverless · CoinGecko, BGeometrics, bitcoin.com, Bybit_")
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════
# Main Pipeline
# ══════════════════════════════════════════════════════════════

def main() -> int:
    print("=" * 64)
    print(f"  CCI Serverless Pipeline  ·  {datetime.now(timezone.utc).isoformat()}")
    print("=" * 64)

    cfg = {
        "telegram_token":   env("TELEGRAM_TOKEN"),
        "telegram_chat_id": env("TELEGRAM_CHAT_ID"),
        "pages_url":        env("PAGES_URL"),
    }

    # ── Fetch ──
    print("\n📥 Phase 1: Fetching data from free APIs...")
    btc_df = fetch_btc_history(365)
    global_mkt = fetch_global_market()
    fg = fetch_fear_greed(90)
    pi = fetch_pi_cycle()
    funding = fetch_bybit_funding()

    # BGeometrics (8/hr hard limit — call sparingly)
    bgeo = {
        "mvrv_zscore":     fetch_bgeometrics("mvrv-zscore", "mvrvZscore"),
        "puell_multiple":  fetch_bgeometrics("puell-multiple", "puellMultiple"),
        "nupl":            fetch_bgeometrics("nupl", "nupl"),
        "sopr":            fetch_bgeometrics("sopr", "sopr"),
    }

    # ── Compute ──
    print("\n⚙️  Phase 2: Computing indicators + CCS...")
    tech = compute_technicals(btc_df) if btc_df is not None else {}

    raw: dict[str, float] = {}
    # Prefer bitcoin.com Pi Cycle, fallback to self-computed
    if pi:
        raw["pi_cycle_ratio"] = pi["ratio"]
    elif "pi_cycle_ratio" in tech:
        raw["pi_cycle_ratio"] = tech["pi_cycle_ratio"]
    # BGeometrics
    for k, v in bgeo.items():
        if v is not None:
            raw[k] = v
    # Technicals
    for k in ("mayer_multiple", "weekly_rsi", "daily_rsi"):
        if k in tech:
            raw[k] = tech[k]
    # Sentiment & derivatives
    if fg:
        raw["fear_greed_index"] = fg["value"]
    if funding is not None:
        raw["funding_rate"] = funding

    ccs = compute_ccs(raw)
    print(f"  CCS = {ccs['composite']} ({ccs['phase']})")

    # ── Persist ──
    print("\n💾 Phase 3: Writing JSON artifacts...")
    now_iso = datetime.now(timezone.utc).isoformat()

    snapshot = {
        "ts":             now_iso,
        "ccs":            ccs["composite"],
        "phase":          ccs["phase"],
        "dimensions":     ccs["dimensions"],
        "indicators_raw": raw,
        "btc_price":      tech.get("current_price"),
        "btc_change_24h": tech.get("change_24h_pct"),
    }

    latest_payload = {
        "generated_at":   now_iso,
        "ccs":            ccs,
        "global_market":  global_mkt,
        "fear_greed":     fg,
        "pi_cycle":       pi,
        "technicals":     tech,
        "funding_rate":   funding,
        "bgeometrics":    bgeo,
        "btc_price_30d":  [
            {"ts": idx.isoformat(), "price": float(row["price"])}
            for idx, row in (btc_df.tail(30).iterrows() if btc_df is not None else [])
        ],
    }
    save_json(LATEST_FILE, latest_payload)

    # Update history (dedup by date)
    history = append_history(snapshot)
    save_json(HISTORY_FILE, history)
    print(f"  History: {len(history)} snapshots")

    # Per-run snapshot (archival)
    snapshot_file = SNAPSHOTS_DIR / f"{now_iso[:10]}.json"
    save_json(snapshot_file, latest_payload)

    # ── Telegram ──
    print("\n📨 Phase 4: Sending Telegram report...")
    report = format_telegram_report(ccs, global_mkt, tech, raw, cfg["pages_url"])
    sent = send_telegram(report, cfg["telegram_token"], cfg["telegram_chat_id"])

    print("\n" + "=" * 64)
    print(f"  ✅ Pipeline complete  ·  CCS={ccs['composite']} ({ccs['phase']})")
    print(f"  Telegram sent: {sent}")
    print("=" * 64)

    # Write a run-summary for GitHub Actions logs
    if env("GITHUB_STEP_SUMMARY"):
        with open(env("GITHUB_STEP_SUMMARY"), "a", encoding="utf-8") as f:
            f.write(f"## CCI Pipeline Summary\n\n")
            f.write(f"- **CCS**: {ccs['composite']} ({ccs['phase']})\n")
            f.write(f"- **BTC**: ${tech.get('current_price', 0):,.0f}\n")
            f.write(f"- **Indicators used**: {len(raw)}\n")
            f.write(f"- **Telegram sent**: {sent}\n")
            f.write(f"- **History size**: {len(history)}\n")

    return 0 if ccs["composite"] is not None else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ FATAL: {e}")
        traceback.print_exc()
        # Try to notify
        token = env("TELEGRAM_TOKEN")
        chat = env("TELEGRAM_CHAT_ID")
        if token and chat:
            send_telegram(
                f"❌ *CCI pipeline failed*\n\n```\n{str(e)[:500]}\n```",
                token, chat,
            )
        sys.exit(1)
