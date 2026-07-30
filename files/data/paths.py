# files/data/paths.py
from __future__ import annotations

from pathlib import Path


def safe_tag(tag: str) -> str:
    """
    Canonical filesystem-safe tag.

    We historically called this "exchange", but it's really a directory tag
    under data/raw and data/processed. Keep it stable and permissive.
    """
    return tag.strip().lower().replace(" ", "_")


# Backward compatible alias (lots of callsites use safe_exchange()).
def safe_exchange(exchange: str) -> str:
    return safe_tag(exchange)


def safe_timeframe(timeframe: str) -> str:
    # canonical: lowercase, no spaces
    return timeframe.strip().lower().replace(" ", "")


def safe_symbol(symbol: str) -> str:
    # canonical: uppercase, filesystem safe
    s = symbol.strip().upper()
    s = s.replace("/", "_").replace(":", "_").replace(" ", "_")
    return s


def data_dir() -> Path:
    return Path("data")


def raw_dir() -> Path:
    return data_dir() / "raw"


def processed_dir() -> Path:
    return data_dir() / "processed"


def cache_dir() -> Path:
    return data_dir() / "cache"


# ---------- RAW (bars) ----------

def raw_symbol_dir(*, exchange: str, symbol: str, timeframe: str) -> Path:
    """
    NOTE: `exchange` here is a DATA TAG, not necessarily the CCXT exchange id.

    Example tags:
      - "coinbase" (legacy default)
      - "coinbase_live_20260207" (clean run tag)
    """
    return raw_dir() / safe_tag(exchange) / safe_symbol(symbol) / safe_timeframe(timeframe)


# ---------- PROCESSED (derived CSVs + reports) ----------

def trades_csv_path(*, exchange: str, symbol: str, timeframe: str) -> Path:
    """
    `exchange` is a DATA TAG (see raw_symbol_dir).
    """
    return (
        processed_dir()
        / "trades"
        / safe_tag(exchange)
        / safe_symbol(symbol)
        / safe_timeframe(timeframe)
        / "trades.csv"
    )


def decisions_csv_path(*, exchange: str, symbol: str, timeframe: str) -> Path:
    """
    `exchange` is a DATA TAG (see raw_symbol_dir).
    """
    return (
        processed_dir()
        / "decisions"
        / safe_tag(exchange)
        / safe_symbol(symbol)
        / safe_timeframe(timeframe)
        / "decisions.csv"
    )


def reports_dir(*, exchange: str, symbol: str, timeframe: str) -> Path:
    """
    `exchange` is a DATA TAG (see raw_symbol_dir).
    """
    return (
        processed_dir()
        / "reports"
        / safe_tag(exchange)
        / safe_symbol(symbol)
        / safe_timeframe(timeframe)
    )


# ---------- PROCESSED (event risk) ----------

def event_risk_dir() -> Path:
    """
    Canonical processed artifact directory for normalized event-risk outputs.

    Current v1 contract paths:
      - data/processed/event_risk/current.json
      - data/processed/event_risk/history.csv   (optional later)
    """
    return processed_dir() / "event_risk"


def event_risk_current_json_path() -> Path:
    return event_risk_dir() / "current.json"


def event_risk_history_csv_path() -> Path:
    return event_risk_dir() / "history.csv"
