# files/main_healthcheck.py
from __future__ import annotations

import argparse
import csv
import json
import os
import time
from pathlib import Path
from typing import Optional

from files.data.decisions import decisions_csv_path
from files.data.paths import raw_symbol_dir


def _read_last_n_rows(path: str, n: int) -> list[dict]:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return []
    rows: list[dict] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    return rows[-n:]


def _parse_ts_ms(v: Optional[str]) -> int:
    try:
        if v is None:
            return 0
        v = v.strip()
        if v == "" or v.lower() == "nan":
            return 0
        return int(float(v))
    except Exception:
        return 0


def _find_newest_bars_parquet(root: Path) -> tuple[Optional[Path], Optional[float]]:
    """
    Returns (path, mtime_epoch_seconds) for newest data/raw/.../date=*/bars.parquet.
    """
    if not root.exists():
        return None, None
    candidates = list(root.glob("date=*/bars.parquet"))
    if not candidates:
        return None, None
    newest = max(candidates, key=lambda p: p.stat().st_mtime)
    return newest, newest.stat().st_mtime


def _emit(status: str, payload: dict, *, as_json: bool) -> None:
    if as_json:
        out = {"status": status, **payload}
        print(json.dumps(out, sort_keys=True))
        return

    # Human output
    if status == "OK":
        print("OK: healthcheck pass")
    elif status == "WARN":
        print("WARN: healthcheck pass with warnings")
    else:
        print("FAIL:", payload.get("reason", "unknown"))

    # Pretty key lines
    for k in (
        "decisions_path",
        "last_ts_ms",
        "tail_rows_checked",
        "bad_recent_found",
        "bad_tail_found",
        "staleness_ms",
        "newest_raw_path",
        "raw_age_ms",
        "clean_trailing_cadence_diffs",
    ):
        if k in payload:
            print(f"  {k}: {payload[k]}")

    # Extras if present
    if "recent_gaps" in payload and payload["recent_gaps"]:
        print("  recent_gaps(index_in_diffs, diff_ms):", payload["recent_gaps"][:10])
    if "last_10_diffs_ms" in payload and payload["last_10_diffs_ms"]:
        print("  last_10_diffs_ms:", payload["last_10_diffs_ms"])
    if "recent_bad_reasons" in payload and payload["recent_bad_reasons"]:
        print("  recent_bad_reasons:")
        for x in payload["recent_bad_reasons"][-10:]:
            print("   -", x)
    if "warns" in payload and payload["warns"]:
        for w in payload["warns"]:
            print("  WARN:", w)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exchange", default="coinbase")
    ap.add_argument("--symbol", default="BTC_USD")
    ap.add_argument("--timeframe", default="5m")

    # decisions read window
    ap.add_argument("--tail", type=int, default=250)

    # cadence expectations
    ap.add_argument("--step-ms", type=int, default=300000)  # 5m
    ap.add_argument("--recent-k", type=int, default=12)     # enforce cadence on last K diffs
    ap.add_argument("--max-recent-gap", type=int, default=1)

    # restart/downtime grace:
    # if fewer than this many trailing diffs are clean, cadence anomalies WARN instead of FAIL.
    ap.add_argument("--cadence-grace-bars", type=int, default=12)

    # marker thresholds (RECENT window only)
    ap.add_argument("--max-bad-recent", type=int, default=2)

    # freshness
    ap.add_argument("--max-staleness-ms", type=int, default=900000)       # decisions freshness
    ap.add_argument("--max-raw-staleness-ms", type=int, default=1800000)  # raw parquet freshness

    # output
    ap.add_argument("--json", type=int, default=0)

    args = ap.parse_args()
    as_json = bool(args.json)

    warns: list[str] = []

    # ------------------------
    # Decisions: existence + parse
    # ------------------------
    dpath = decisions_csv_path(exchange=args.exchange, symbol=args.symbol, timeframe=args.timeframe)
    rows = _read_last_n_rows(dpath, args.tail)

    if not rows:
        _emit(
            "FAIL",
            {"reason": "decisions missing/empty", "decisions_path": dpath},
            as_json=as_json,
        )
        return 2

    ts_all = [_parse_ts_ms(r.get("ts_ms")) for r in rows]
    ts = [x for x in ts_all if x > 0]

    # Require a small absolute minimum, but don't fail just because history is short.
    # A brand-new DATA_TAG namespace may only have a handful of rows at startup.
    min_valid_required = 5
    if len(ts) < min_valid_required:
        _emit(
            "FAIL",
            {
                "reason": "too few valid ts_ms rows",
                "decisions_path": dpath,
                "tail_rows_checked": len(rows),
                "valid_ts_count": len(ts),
                "min_valid_required": min_valid_required,
            },
            as_json=as_json,
        )
        return 2

    # Effective recent window is bounded by available diffs
    diffs = [b - a for a, b in zip(ts, ts[1:])]
    eff_recent_k = max(1, min(int(args.recent_k), len(diffs))) if diffs else 1

    if eff_recent_k != int(args.recent_k):
        warns.append(f"recent_k capped to available history: requested={args.recent_k} effective={eff_recent_k}")

    # ------------------------
    # Hard requirement: monotonic tail
    # ------------------------
    if any(b <= a for a, b in zip(ts, ts[1:])):
        _emit(
            "FAIL",
            {"reason": "ts_ms not strictly increasing in tail", "decisions_path": dpath},
            as_json=as_json,
        )
        return 2

    # ------------------------
    # Cadence: recent diffs; allow grace after downtime
    # ------------------------

    # how many trailing diffs are perfect?
    clean_trailing = 0
    for d in reversed(diffs):
        if d == args.step_ms:
            clean_trailing += 1
        else:
            break

    recent_diffs = diffs[-eff_recent_k:] if eff_recent_k > 0 else diffs
    recent_gaps = [
        (i, d)
        for i, d in enumerate(
            recent_diffs,
            start=max(0, len(diffs) - len(recent_diffs)),
        )
        if d != args.step_ms
    ]

    cadence_failed = False
    if len(recent_gaps) > args.max_recent_gap:
        if clean_trailing < args.cadence_grace_bars:
            warns.append(
                f"recent cadence anomalies, but within grace window "
                f"(clean_trailing={clean_trailing} < cadence_grace_bars={args.cadence_grace_bars})"
            )
        else:
            cadence_failed = True

    if cadence_failed:
        _emit(
            "FAIL",
            {
                "reason": "recent cadence anomalies detected",
                "decisions_path": dpath,
                "recent_gaps": recent_gaps,
                "last_10_diffs_ms": diffs[-10:],
                "clean_trailing_cadence_diffs": clean_trailing,
            },
            as_json=as_json,
        )
        return 2

    # ------------------------
    # Bad marker checks: enforce only in RECENT rows
    # ------------------------
    bad_markers = ("fetch_failed", "persist_failed", "cadence_failed", "features_invalid")

    def is_bad(mr: str) -> bool:
        mr = (mr or "").strip()
        return any(x in mr for x in bad_markers)

    recent_rows = rows[-max(eff_recent_k, 1):]
    bad_recent = [(r.get("market_reason") or "").strip() for r in recent_rows if is_bad(r.get("market_reason") or "")]
    bad_tail = [(r.get("market_reason") or "").strip() for r in rows if is_bad(r.get("market_reason") or "")]

    if len(bad_recent) > args.max_bad_recent:
        _emit(
            "FAIL",
            {
                "reason": "too many bad market_reason markers in RECENT window",
                "decisions_path": dpath,
                "bad_recent_found": len(bad_recent),
                "max_bad_recent": args.max_bad_recent,
                "recent_bad_reasons": bad_recent[-10:],
            },
            as_json=as_json,
        )
        return 2

    # ------------------------
    # Freshness: decisions staleness (hard)
    # ------------------------
    now_ms = int(time.time() * 1000)
    staleness_ms = now_ms - ts[-1]
    if staleness_ms > args.max_staleness_ms:
        _emit(
            "FAIL",
            {
                "reason": "decisions stale",
                "decisions_path": dpath,
                "last_ts_ms": ts[-1],
                "staleness_ms": staleness_ms,
                "max_staleness_ms": args.max_staleness_ms,
            },
            as_json=as_json,
        )
        return 2

    # ------------------------
    # Raw parquet freshness (Tier 3.8) (hard)
    # ------------------------
    raw_root = raw_symbol_dir(exchange=args.exchange, symbol=args.symbol, timeframe=args.timeframe)
    newest_path, newest_mtime = _find_newest_bars_parquet(raw_root)

    if newest_path is None or newest_mtime is None:
        _emit(
            "FAIL",
            {
                "reason": "raw parquet missing",
                "raw_root": str(raw_root),
            },
            as_json=as_json,
        )
        return 2

    raw_age_ms = int((time.time() - newest_mtime) * 1000)
    if raw_age_ms > args.max_raw_staleness_ms:
        _emit(
            "FAIL",
            {
                "reason": "raw parquet stale",
                "newest_raw_path": str(newest_path),
                "raw_age_ms": raw_age_ms,
                "max_raw_staleness_ms": args.max_raw_staleness_ms,
            },
            as_json=as_json,
        )
        return 2

    # ------------------------
    # WARN-only: historical gaps + historical bad markers
    # ------------------------
    hist_gaps = [(a, b, b - a) for a, b in zip(ts, ts[1:]) if (b - a) != args.step_ms]
    big = [g for g in hist_gaps if g[2] >= args.step_ms * 2]
    if big:
        warns.append(f"historical gaps detected (likely downtime): count={len(big)} first={big[0]}")
    if bad_tail:
        warns.append("historical bad markers exist in tail (likely earlier injections)")

    status = "OK" if not warns else "WARN"
    _emit(
        status,
        {
            "decisions_path": dpath,
            "last_ts_ms": ts[-1],
            "tail_rows_checked": len(rows),
            "bad_recent_found": len(bad_recent),
            "bad_tail_found": len(bad_tail),
            "staleness_ms": staleness_ms,
            "newest_raw_path": str(newest_path),
            "raw_age_ms": raw_age_ms,
            "clean_trailing_cadence_diffs": clean_trailing,
            "warns": warns,
        },
        as_json=as_json,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

