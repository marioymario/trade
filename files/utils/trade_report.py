# files/utils/trade_report.py
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any

import pandas as pd

from files.data.trades import trades_csv_path


@dataclass(frozen=True)
class ReportConfig:
    exchange: str
    symbol: str
    timeframe: str
    days_tail: int  # show last N days in daily grouping


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    return v if v is not None and v.strip() != "" else default


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return int(v)


def _ts_ms_to_dt_utc(ts_ms: Any) -> pd.Timestamp | pd.NaT:
    try:
        if pd.isna(ts_ms):
            return pd.NaT
        x = int(float(ts_ms))
        if x <= 0:
            return pd.NaT
        return pd.to_datetime(x, unit="ms", utc=True)
    except Exception:
        return pd.NaT


def _safe_float(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def _profit_factor(pnl: pd.Series) -> float:
    wins = pnl[pnl > 0].sum()
    losses = pnl[pnl < 0].sum()
    if losses == 0:
        return float("inf") if wins > 0 else 0.0
    return float(wins / abs(losses))


def _max_drawdown(equity: pd.Series) -> float:
    """
    equity: cumulative PnL series (not price). Returns max drawdown in USD.
    """
    if equity.empty:
        return 0.0
    peak = equity.cummax()
    dd = equity - peak
    return float(dd.min())  # negative number (min drawdown)


def _format_usd(x: float) -> str:
    return f"{x:.2f} USD"


def _format_pct(x: float) -> str:
    return f"{100.0 * x:.2f}%"


def _print_kv(k: str, v: str) -> None:
    print(f"{k:<11} {v}")


def _daily_grouping(df: pd.DataFrame, days_tail: int) -> pd.DataFrame:
    """
    Groups by UTC day using exit time. If exit time missing, uses entry time.
    """
    dt_exit = df["exit_time"].copy()
    dt_entry = df["entry_time"].copy()
    day = dt_exit.dt.floor("D")
    day = day.where(day.notna(), dt_entry.dt.floor("D"))
    df = df.copy()
    df["day"] = day

    g = df.dropna(subset=["day"]).groupby("day", as_index=False)

    # core pnl columns
    pnl = "realized_pnl_usd"
    cost_col = "cost_usd" if "cost_usd" in df.columns else None

    def _wins(s: pd.Series) -> int:
        return int((s > 0).sum())

    def _losses(s: pd.Series) -> int:
        return int((s < 0).sum())

    out = g.agg(
        trades=(pnl, "count"),
        pnl_usd=(pnl, "sum"),
        avg_pnl_usd=(pnl, "mean"),
        wins=(pnl, _wins),
        losses=(pnl, _losses),
    )

    if cost_col is not None:
        out["cost_usd"] = g[cost_col].sum()[cost_col].values

    # win rate
    out["win_rate"] = out.apply(
        lambda r: (float(r["wins"]) / float(r["trades"])) if r["trades"] else 0.0, axis=1
    )

    # equity end-of-day (cumulative over all trades, ordered by day)
    out = out.sort_values("day").reset_index(drop=True)
    out["equity_eod_usd"] = out["pnl_usd"].cumsum()

    # tail last N days if desired
    if days_tail > 0 and len(out) > days_tail:
        out = out.tail(days_tail).reset_index(drop=True)

    return out


def main() -> None:
    cfg = ReportConfig(
        exchange=_env("REPORT_EXCHANGE", "coinbase"),
        symbol=_env("REPORT_SYMBOL", "BTC/USD"),
        timeframe=_env("REPORT_TIMEFRAME", "5m"),
        days_tail=_env_int("REPORT_DAYS_TAIL", 14),
    )

    path = trades_csv_path(exchange=cfg.exchange, symbol=cfg.symbol, timeframe=cfg.timeframe)

    if not os.path.exists(path):
        print("=== Trade Report ===")
        _print_kv("exchange:", cfg.exchange)
        _print_kv("symbol:", cfg.symbol)
        _print_kv("timeframe:", cfg.timeframe)
        _print_kv("csv_path:", path)
        print("\nNo trades CSV found yet.")
        sys.exit(0)

    df = pd.read_csv(path)

    if df.empty:
        print("=== Trade Report ===")
        _print_kv("exchange:", cfg.exchange)
        _print_kv("symbol:", cfg.symbol)
        _print_kv("timeframe:", cfg.timeframe)
        _print_kv("csv_path:", path)
        print("\nTrades CSV exists but is empty.")
        sys.exit(0)

    # normalize numeric fields
    df["realized_pnl_usd"] = _safe_float(df.get("realized_pnl_usd", pd.Series([], dtype="float64")))
    df["realized_pnl_pct"] = _safe_float(df.get("realized_pnl_pct", pd.Series([], dtype="float64")))

    if "cost_usd" in df.columns:
        df["cost_usd"] = _safe_float(df["cost_usd"])

    # timestamps
    df["entry_time"] = df.get("entry_ts_ms", pd.Series([pd.NA] * len(df))).apply(_ts_ms_to_dt_utc)
    df["exit_time"] = df.get("exit_ts_ms", pd.Series([pd.NA] * len(df))).apply(_ts_ms_to_dt_utc)

    # sort by exit, fallback to entry
    sort_key = df["exit_time"].fillna(df["entry_time"])
    df = df.assign(_sort=sort_key).sort_values("_sort").drop(columns=["_sort"]).reset_index(drop=True)

    trades = len(df)
    pnl = df["realized_pnl_usd"].fillna(0.0)

    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    breakeven = int((pnl == 0).sum())
    win_rate = float(wins / trades) if trades else 0.0

    total_pnl = float(pnl.sum())
    avg_pnl = float(pnl.mean()) if trades else 0.0
    avg_win = float(pnl[pnl > 0].mean()) if wins else 0.0
    avg_loss = float(pnl[pnl < 0].mean()) if losses else 0.0
    pf = _profit_factor(pnl)

    # equity / dd
    cum = pnl.cumsum()
    equity = cum.ffill().fillna(0.0)  # FutureWarning fixed
    max_dd = _max_drawdown(equity)

    first_entry = df["entry_time"].dropna().min()
    last_exit = df["exit_time"].dropna().max()

    print("\n=== Trade Report ===")
    _print_kv("exchange:", f"{cfg.exchange}")
    _print_kv("symbol:", f"{cfg.symbol}")
    _print_kv("timeframe:", f"{cfg.timeframe}")
    _print_kv("csv_path:", f"{path}")
    print()
    _print_kv("trades:", f"{trades}")
    _print_kv("wins:", f"{wins}")
    _print_kv("losses:", f"{losses}")
    _print_kv("breakeven:", f"{breakeven}")
    _print_kv("win_rate:", f"{_format_pct(win_rate)}")
    print()
    _print_kv("total_pnl:", _format_usd(total_pnl))
    _print_kv("avg_pnl:", _format_usd(avg_pnl))
    _print_kv("avg_win:", _format_usd(avg_win))
    _print_kv("avg_loss:", _format_usd(avg_loss))
    _print_kv("profit_fact:", f"{pf:.4g}" if pf != float("inf") else "inf")
    _print_kv("max_dd:", _format_usd(max_dd))
    print()
    _print_kv("first_entry:", first_entry.isoformat() if pd.notna(first_entry) else "n/a")
    _print_kv("last_exit:", last_exit.isoformat() if pd.notna(last_exit) else "n/a")

    # --- Daily grouping (UTC) ---
    daily = _daily_grouping(df, cfg.days_tail)

    if not daily.empty:
        print("\n--- Per-day (UTC) ---")
        print(f"(showing last {cfg.days_tail} days)" if cfg.days_tail > 0 else "(showing all days)")
        # pretty print as a simple table
        show = daily.copy()
        show["day"] = show["day"].dt.strftime("%Y-%m-%d")
        show["pnl_usd"] = show["pnl_usd"].map(lambda x: f"{float(x):.2f}")
        show["avg_pnl_usd"] = show["avg_pnl_usd"].map(lambda x: f"{float(x):.2f}")
        show["win_rate"] = show["win_rate"].map(lambda x: f"{100.0*float(x):.1f}%")
        show["equity_eod_usd"] = show["equity_eod_usd"].map(lambda x: f"{float(x):.2f}")

        cols = ["day", "trades", "wins", "losses", "win_rate", "pnl_usd", "avg_pnl_usd"]
        if "cost_usd" in show.columns:
            show["cost_usd"] = show["cost_usd"].map(lambda x: f"{float(x):.2f}")
            cols.append("cost_usd")
        cols.append("equity_eod_usd")

        # manual table output (stable, no extra deps)
        header = "  ".join([f"{c:>12}" for c in cols])
        print(header)
        print("-" * len(header))
        for _, r in show[cols].iterrows():
            print("  ".join([f"{str(r[c]):>12}" for c in cols]))

    # --- Last trade ---
    last = df.iloc[-1].to_dict()
    print("\n--- Last trade ---")
    _print_kv("side:", str(last.get("side", "")))
    _print_kv("qty:", str(last.get("qty", "")))
    _print_kv("entry_price:", str(last.get("entry_price", "")))
    _print_kv("exit_price:", str(last.get("exit_price", "")))
    _print_kv("reason:", str(last.get("exit_reason", "")))

    pnl_usd_last = float(last.get("realized_pnl_usd", 0.0) or 0.0)
    pnl_pct_last = float(last.get("realized_pnl_pct", 0.0) or 0.0)
    _print_kv("pnl_usd:", str(pnl_usd_last))
    _print_kv("pnl_pct:", str(pnl_pct_last))

    if "cost_usd" in last:
        try:
            _print_kv("cost_usd:", str(float(last.get("cost_usd") or 0.0)))
        except Exception:
            _print_kv("cost_usd:", str(last.get("cost_usd")))

    et = last.get("entry_time")
    xt = last.get("exit_time")
    _print_kv("entry_time:", et.isoformat() if isinstance(et, pd.Timestamp) and pd.notna(et) else "n/a")
    _print_kv("exit_time:", xt.isoformat() if isinstance(xt, pd.Timestamp) and pd.notna(xt) else "n/a")
    _print_kv("market:", str(last.get("market_reason", "")))


if __name__ == "__main__":
    main()
