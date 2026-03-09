# files/utils/trade_report.py
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Tuple

import pandas as pd

from files.data.trades import trades_csv_path
from files.data.paths import reports_dir


@dataclass(frozen=True)
class ReportConfig:
    exchange: str
    symbol: str
    timeframe: str
    days_tail: int = 14
    top_n: int = 10


def _env_int(name: str, default: int) -> int:
    v = os.getenv(name, "").strip()
    if not v:
        return default
    try:
        return int(v)
    except Exception:
        return default


def _read_trades(csv_path: str) -> pd.DataFrame:
    if not os.path.exists(csv_path):
        return pd.DataFrame()

    df = pd.read_csv(csv_path)

    for col in [
        "entry_ts_ms",
        "exit_ts_ms",
        "qty",
        "entry_price",
        "exit_price",
        "realized_pnl_usd",
        "realized_pnl_pct",
        "cum_realized_pnl_usd",
        "trades_closed",
        "stop_price",
        "fee_bps",
        "slippage_bps",
        "cost_usd",
    ]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "entry_ts_ms" in df.columns:
        df["entry_time"] = pd.to_datetime(df["entry_ts_ms"], unit="ms", utc=True, errors="coerce")
    if "exit_ts_ms" in df.columns:
        df["exit_time"] = pd.to_datetime(df["exit_ts_ms"], unit="ms", utc=True, errors="coerce")

    if "entry_time" in df.columns and "exit_time" in df.columns:
        hold = (df["exit_time"] - df["entry_time"]).dt.total_seconds() / 60.0
        df["hold_minutes"] = pd.to_numeric(hold, errors="coerce")

    if "side" in df.columns:
        df["side"] = df["side"].fillna("").astype(str).str.upper().str.strip()

    if "exit_reason" in df.columns:
        df["exit_reason"] = df["exit_reason"].fillna("").astype(str).str.strip()

    if "market_reason" in df.columns:
        df["market_reason"] = df["market_reason"].fillna("").astype(str).str.strip()

    if "exit_time" in df.columns:
        df = df.sort_values("exit_time").reset_index(drop=True)

    return df


def _equity_and_dd(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series, pd.Series]:
    if df.empty or "cum_realized_pnl_usd" not in df.columns:
        equity = pd.Series(dtype=float)
        dd_usd = pd.Series(dtype=float)
        dd_pct = pd.Series(dtype=float)
        return equity, dd_usd, dd_pct

    cum = pd.to_numeric(df["cum_realized_pnl_usd"], errors="coerce")
    equity = cum.ffill().fillna(0.0)

    peak = equity.cummax()
    dd_usd = equity - peak

    dd_pct = pd.Series(0.0, index=equity.index)
    nonzero = peak != 0
    dd_pct.loc[nonzero] = dd_usd.loc[nonzero] / peak.loc[nonzero]

    return equity, dd_usd, dd_pct


def _write_equity_curve_csv(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    df: pd.DataFrame,
    equity: pd.Series,
    dd_usd: pd.Series,
    dd_pct: pd.Series,
) -> Optional[str]:
    if df.empty or "exit_time" not in df.columns:
        return None

    out_dir = reports_dir(exchange=exchange, symbol=symbol, timeframe=timeframe)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "equity_curve.csv"

    out = pd.DataFrame(
        {
            "timestamp": df["exit_time"].dt.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "equity_usd": equity.astype(float),
            "drawdown_usd": dd_usd.astype(float),
            "drawdown_pct": dd_pct.astype(float),
            "trades_closed": pd.to_numeric(
                df.get("trades_closed", pd.Series([None] * len(df))),
                errors="coerce",
            ),
        }
    )
    out.to_csv(str(out_path), index=False)
    return str(out_path)


def _per_day_table(df: pd.DataFrame, days_tail: int) -> pd.DataFrame:
    if df.empty or "exit_time" not in df.columns:
        return pd.DataFrame()

    tmp = df.copy()
    tmp["day"] = tmp["exit_time"].dt.floor("D")

    pnl = pd.to_numeric(tmp.get("realized_pnl_usd"), errors="coerce").fillna(0.0)
    tmp["_win"] = (pnl > 0).astype(int)
    tmp["_loss"] = (pnl < 0).astype(int)

    g = tmp.groupby("day", as_index=False).agg(
        trades=("day", "count"),
        wins=("_win", "sum"),
        losses=("_loss", "sum"),
        pnl_usd=("realized_pnl_usd", "sum"),
        avg_pnl_usd=("realized_pnl_usd", "mean"),
    )
    g["win_rate"] = g.apply(lambda r: (100.0 * r["wins"] / r["trades"]) if r["trades"] else 0.0, axis=1)

    if "cum_realized_pnl_usd" in tmp.columns:
        eod = tmp.groupby("day")["cum_realized_pnl_usd"].last().reset_index()
        eod = eod.rename(columns={"cum_realized_pnl_usd": "equity_eod_usd"})
        g = g.merge(eod, on="day", how="left")
    else:
        g["equity_eod_usd"] = 0.0

    g = g.sort_values("day").reset_index(drop=True)
    if days_tail > 0:
        g = g.tail(days_tail)

    return g


def _print_side_summary(df: pd.DataFrame) -> None:
    if df.empty or "side" not in df.columns:
        print("\n--- By side ---")
        print("No side data.")
        return

    tmp = df.copy()
    tmp["side"] = tmp["side"].replace("", "UNKNOWN")

    pnl = pd.to_numeric(tmp.get("realized_pnl_usd"), errors="coerce").fillna(0.0)
    tmp["_win"] = (pnl > 0).astype(int)
    tmp["_loss"] = (pnl < 0).astype(int)

    if "hold_minutes" not in tmp.columns:
        tmp["hold_minutes"] = pd.NA

    g = tmp.groupby("side", as_index=False).agg(
        trades=("side", "count"),
        wins=("_win", "sum"),
        losses=("_loss", "sum"),
        pnl_usd=("realized_pnl_usd", "sum"),
        avg_pnl_usd=("realized_pnl_usd", "mean"),
        avg_hold_min=("hold_minutes", "mean"),
        median_hold_min=("hold_minutes", "median"),
    )
    g["win_rate"] = g.apply(lambda r: (100.0 * r["wins"] / r["trades"]) if r["trades"] else 0.0, axis=1)
    g = g.sort_values(["pnl_usd", "trades"], ascending=[True, False]).reset_index(drop=True)

    print("\n--- By side ---")
    header = (
        f"{'side':>8}  {'trades':>8}  {'wins':>8}  {'losses':>8}  "
        f"{'win_rate':>10}  {'pnl_usd':>12}  {'avg_pnl':>12}  "
        f"{'avg_hold_m':>12}  {'med_hold_m':>12}"
    )
    print(header)
    print("-" * len(header))
    for _, r in g.iterrows():
        print(
            f"{str(r['side']):>8}  "
            f"{int(r['trades']):>8}  "
            f"{int(r['wins']):>8}  "
            f"{int(r['losses']):>8}  "
            f"{float(r['win_rate']):>9.1f}%  "
            f"{float(r['pnl_usd']):>12.2f}  "
            f"{float(r['avg_pnl_usd']):>12.2f}  "
            f"{float(r['avg_hold_min']) if pd.notna(r['avg_hold_min']) else 0.0:>12.2f}  "
            f"{float(r['median_hold_min']) if pd.notna(r['median_hold_min']) else 0.0:>12.2f}"
        )


def _print_exit_reason_summary(df: pd.DataFrame) -> None:
    if df.empty or "exit_reason" not in df.columns:
        print("\n--- Exit reasons ---")
        print("No exit reason data.")
        return

    tmp = df.copy()
    tmp["exit_reason"] = tmp["exit_reason"].replace("", "UNKNOWN")

    g = (
        tmp.groupby("exit_reason", as_index=False)
        .agg(
            trades=("exit_reason", "count"),
            pnl_usd=("realized_pnl_usd", "sum"),
            avg_pnl_usd=("realized_pnl_usd", "mean"),
        )
        .sort_values(["trades", "pnl_usd"], ascending=[False, True])
        .reset_index(drop=True)
    )

    total = int(len(tmp))
    print("\n--- Exit reasons ---")
    header = f"{'reason':<28}  {'trades':>8}  {'share':>8}  {'pnl_usd':>12}  {'avg_pnl':>12}"
    print(header)
    print("-" * len(header))
    for _, r in g.iterrows():
        share = (100.0 * float(r["trades"]) / total) if total else 0.0
        print(
            f"{str(r['exit_reason'])[:28]:<28}  "
            f"{int(r['trades']):>8}  "
            f"{share:>7.1f}%  "
            f"{float(r['pnl_usd']):>12.2f}  "
            f"{float(r['avg_pnl_usd']):>12.2f}"
        )


def _print_hold_summary(df: pd.DataFrame) -> None:
    print("\n--- Hold duration ---")
    if df.empty or "hold_minutes" not in df.columns:
        print("No hold duration data.")
        return

    hold = pd.to_numeric(df["hold_minutes"], errors="coerce").dropna()
    if hold.empty:
        print("No hold duration data.")
        return

    print(f"avg_hold_min:    {float(hold.mean()):.2f}")
    print(f"median_hold_min: {float(hold.median()):.2f}")
    print(f"min_hold_min:    {float(hold.min()):.2f}")
    print(f"max_hold_min:    {float(hold.max()):.2f}")


def _market_reason_bucket(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return "UNKNOWN"
    return s.split()[0]


def _print_market_reason_summary(df: pd.DataFrame, top_n: int) -> None:
    print("\n--- Market reason buckets ---")
    if df.empty or "market_reason" not in df.columns:
        print("No market reason data.")
        return

    tmp = df.copy()
    tmp["market_reason_bucket"] = tmp["market_reason"].map(_market_reason_bucket)

    g = (
        tmp.groupby("market_reason_bucket", as_index=False)
        .agg(
            trades=("market_reason_bucket", "count"),
            pnl_usd=("realized_pnl_usd", "sum"),
            avg_pnl_usd=("realized_pnl_usd", "mean"),
        )
        .sort_values(["trades", "pnl_usd"], ascending=[False, True])
        .reset_index(drop=True)
    )

    if top_n > 0:
        g = g.head(top_n)

    header = f"{'bucket':<18}  {'trades':>8}  {'pnl_usd':>12}  {'avg_pnl':>12}"
    print(header)
    print("-" * len(header))
    for _, r in g.iterrows():
        print(
            f"{str(r['market_reason_bucket'])[:18]:<18}  "
            f"{int(r['trades']):>8}  "
            f"{float(r['pnl_usd']):>12.2f}  "
            f"{float(r['avg_pnl_usd']):>12.2f}"
        )


def main() -> None:
    exchange = os.getenv("REPORT_EXCHANGE", "coinbase").strip()
    symbol = os.getenv("REPORT_SYMBOL", "BTC/USD").strip()
    timeframe = os.getenv("REPORT_TIMEFRAME", "5m").strip()
    days_tail = _env_int("REPORT_DAYS_TAIL", 14)
    top_n = _env_int("REPORT_TOP_N", 10)

    cfg = ReportConfig(
        exchange=exchange,
        symbol=symbol,
        timeframe=timeframe,
        days_tail=days_tail,
        top_n=top_n,
    )
    csv_path = trades_csv_path(exchange=cfg.exchange, symbol=cfg.symbol, timeframe=cfg.timeframe)
    df = _read_trades(csv_path)

    print("\n=== Trade Report ===")
    print(f"exchange:   {cfg.exchange}")
    print(f"symbol:     {cfg.symbol}")
    print(f"timeframe:  {cfg.timeframe}")
    print(f"csv_path:   {csv_path}\n")

    if df.empty:
        print("No trades found.")
        return

    pnl = pd.to_numeric(df.get("realized_pnl_usd"), errors="coerce").fillna(0.0)
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    breakeven = int((pnl == 0).sum())
    trades = int(len(df))
    win_rate = 100.0 * wins / trades if trades else 0.0

    total_pnl = float(pnl.sum())
    avg_pnl = float(pnl.mean()) if trades else 0.0
    median_pnl = float(pnl.median()) if trades else 0.0
    avg_win = float(pnl[pnl > 0].mean()) if wins else 0.0
    avg_loss = float(pnl[pnl < 0].mean()) if losses else 0.0

    gross_profit = float(pnl[pnl > 0].sum())
    gross_loss = float((-pnl[pnl < 0]).sum())
    profit_fact = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    equity, dd_usd, dd_pct = _equity_and_dd(df)
    max_dd = float(dd_usd.min()) if not dd_usd.empty else 0.0

    first_entry = df["entry_time"].min() if "entry_time" in df.columns else None
    last_exit = df["exit_time"].max() if "exit_time" in df.columns else None

    hold = pd.to_numeric(df.get("hold_minutes"), errors="coerce").dropna()
    avg_hold = float(hold.mean()) if not hold.empty else 0.0
    median_hold = float(hold.median()) if not hold.empty else 0.0

    stop_hit_count = 0
    if "exit_reason" in df.columns:
        stop_hit_count = int((df["exit_reason"] == "stop_hit").sum())
    stop_hit_share = (100.0 * stop_hit_count / trades) if trades else 0.0

    print(f"trades:     {trades}")
    print(f"wins:       {wins}")
    print(f"losses:     {losses}")
    print(f"breakeven:  {breakeven}")
    print(f"win_rate:   {win_rate:,.2f}%\n")

    print(f"total_pnl:   {total_pnl:,.2f} USD")
    print(f"avg_pnl:     {avg_pnl:,.2f} USD")
    print(f"median_pnl:  {median_pnl:,.2f} USD")
    print(f"avg_win:     {avg_win:,.2f} USD")
    print(f"avg_loss:    {avg_loss:,.2f} USD")
    print(f"profit_fact: {profit_fact}")
    print(f"max_dd:      {max_dd:,.2f} USD")
    print(f"avg_hold_m:  {avg_hold:,.2f}")
    print(f"med_hold_m:  {median_hold:,.2f}")
    print(f"stop_hit_n:  {stop_hit_count}")
    print(f"stop_hit_%:  {stop_hit_share:,.2f}%\n")

    if first_entry is not None:
        print(f"first_entry: {first_entry.isoformat()}")
    if last_exit is not None:
        print(f"last_exit:   {last_exit.isoformat()}")

    daily = _per_day_table(df, days_tail=cfg.days_tail)
    print("\n--- Per-day (UTC) ---")
    print(f"(showing last {cfg.days_tail} days)")
    if daily.empty:
        print("No per-day data.")
    else:
        header = (
            f"{'day':>12}  {'trades':>10}  {'wins':>10}  {'losses':>10}  "
            f"{'win_rate':>10}  {'pnl_usd':>12}  {'avg_pnl_usd':>12}  {'equity_eod_usd':>14}"
        )
        print(header)
        print("-" * len(header))
        for _, r in daily.iterrows():
            day = pd.to_datetime(r["day"], utc=True).strftime("%Y-%m-%d")
            print(
                f"{day:>12}  "
                f"{int(r['trades']):>10}  "
                f"{int(r['wins']):>10}  "
                f"{int(r['losses']):>10}  "
                f"{float(r['win_rate']):>9.1f}%  "
                f"{float(r['pnl_usd']):>12.2f}  "
                f"{float(r['avg_pnl_usd']):>12.2f}  "
                f"{float(r.get('equity_eod_usd', 0.0)):>14.2f}"
            )

        best = daily.sort_values("pnl_usd", ascending=False).head(1)
        worst = daily.sort_values("pnl_usd", ascending=True).head(1)
        if len(best) and len(worst):
            best_day = pd.to_datetime(best.iloc[0]["day"], utc=True).strftime("%Y-%m-%d")
            worst_day = pd.to_datetime(worst.iloc[0]["day"], utc=True).strftime("%Y-%m-%d")
            print("\n--- Best/Worst day (shown window) ---")
            print(f"best_day:  {best_day} pnl={float(best.iloc[0]['pnl_usd']):.2f}")
            print(f"worst_day: {worst_day} pnl={float(worst.iloc[0]['pnl_usd']):.2f}")

    _print_side_summary(df)
    _print_exit_reason_summary(df)
    _print_hold_summary(df)
    _print_market_reason_summary(df, top_n=cfg.top_n)

    out_path = _write_equity_curve_csv(
        exchange=cfg.exchange,
        symbol=cfg.symbol,
        timeframe=cfg.timeframe,
        df=df,
        equity=equity,
        dd_usd=dd_usd,
        dd_pct=dd_pct,
    )
    if out_path:
        print(f"\nEquity curve written: {out_path}")

    print("\n--- Last trade ---")
    last = df.iloc[-1]
    print(f"side:       {str(last.get('side', ''))}")
    print(f"qty:        {float(last.get('qty', 0.0) or 0.0)}")
    print(f"entry_price:{float(last.get('entry_price', 0.0) or 0.0)}")
    print(f"exit_price: {float(last.get('exit_price', 0.0) or 0.0)}")
    print(f"reason:     {str(last.get('exit_reason', ''))}")
    print(f"pnl_usd:    {float(last.get('realized_pnl_usd', 0.0) or 0.0)}")
    print(f"pnl_pct:    {float(last.get('realized_pnl_pct', 0.0) or 0.0)}")
    if "hold_minutes" in df.columns and pd.notna(last.get("hold_minutes", None)):
        print(f"hold_min:   {float(last.get('hold_minutes', 0.0) or 0.0):.2f}")
    if "entry_time" in df.columns and pd.notna(last.get("entry_time", None)):
        print(f"entry_time: {pd.to_datetime(last['entry_time'], utc=True)}")
    if "exit_time" in df.columns and pd.notna(last.get("exit_time", None)):
        print(f"exit_time:  {pd.to_datetime(last['exit_time'], utc=True)}")
    print(f"market:     {str(last.get('market_reason', ''))}")


if __name__ == "__main__":
    main()

