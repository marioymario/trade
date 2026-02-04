# files/main_live_vs_backtest_equivalence.py
from __future__ import annotations

import argparse
import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# ----------------------------
# Utilities
# ----------------------------

def _exists(path: str) -> bool:
    return os.path.exists(path) and os.path.getsize(path) > 0


def _safe_int(x) -> Optional[int]:
    try:
        if x in (None, "", "nan"):
            return None
        return int(float(x))
    except Exception:
        return None


def _safe_float(x) -> Optional[float]:
    try:
        if x in (None, "", "nan"):
            return None
        return float(x)
    except Exception:
        return None


def _boolish(x) -> bool:
    if x is None:
        return False
    s = str(x).strip().lower()
    return s in ("1", "true", "t", "yes", "y")


def _norm_side(x: str) -> str:
    s = (x or "").strip().upper()
    if s in ("LONG", "SHORT"):
        return s
    return ""


def _decision_ts(row: Dict[str, str]) -> Optional[int]:
    return _safe_int(row.get("ts_ms"))


def _trade_sig(row: Dict[str, str]) -> Tuple[int, int, str, str]:
    e = _safe_int(row.get("entry_ts_ms")) or 0
    x = _safe_int(row.get("exit_ts_ms")) or 0
    side = _norm_side(row.get("side", ""))
    reason = (row.get("exit_reason") or "").strip()
    return (e, x, side, reason)


def _decision_sig(row: Dict[str, str]) -> Tuple[int, int, str, int, str, str, int, int]:
    """
    Signature used to compare lifecycle behavior.
    Keep it minimal and robust.

    Returns:
      (ts_ms,
       entry_should_enter,
       entry_side,
       exit_should_exit,
       exit_reason,
       position_side,
       has_stop,
       has_anchor)
    """
    ts = _safe_int(row.get("ts_ms")) or 0

    enter = 1 if _boolish(row.get("entry_should_enter")) else 0
    entry_side = _norm_side(row.get("entry_side", ""))

    ex = 1 if _boolish(row.get("exit_should_exit")) else 0
    exit_reason = (row.get("exit_reason") or "").strip()

    pos_side = _norm_side(row.get("position_side", ""))

    has_stop = 1 if (row.get("position_stop_price") not in (None, "", "nan")) else 0
    has_anchor = 1 if (row.get("position_trailing_anchor_price") not in (None, "", "nan")) else 0

    return (ts, enter, entry_side, ex, exit_reason, pos_side, has_stop, has_anchor)


def _is_noop_decision(row: Dict[str, str]) -> bool:
    """
    A row that exists but does nothing / no lifecycle change:
    - no entry, no exit, no position
    (This is safe to treat as ignorable missing-in-one-side noise when ts-keyed.)
    """
    enter = _boolish(row.get("entry_should_enter"))
    ex = _boolish(row.get("exit_should_exit"))
    pos = (row.get("position_side") or "").strip()
    return (not enter) and (not ex) and (pos == "")


def _fmt_dec_sig(sig: Tuple[int, int, str, int, str, str, int, int]) -> str:
    ts, enter, side, ex, reason, pos, has_stop, has_anchor = sig
    # keep this short (matches your prior output vibe)
    return (
        f"ts={ts}|enter={enter}|side={side}|exit={ex}|reason={reason}"
        f"|pos={pos}|stop={has_stop}|anch={has_anchor}"
    )


# ----------------------------
# Path helpers (matches your folder layout)
# ----------------------------

def decisions_path(tag: str, symbol: str, timeframe: str) -> str:
    # tag is like "coinbase" or "coinbase_bt_runid"
    return os.path.join(
        "data",
        "processed",
        "decisions",
        tag,
        symbol,
        timeframe,
        "decisions.csv",
    )


def trades_path(tag: str, symbol: str, timeframe: str) -> str:
    return os.path.join(
        "data",
        "processed",
        "trades",
        tag,
        symbol,
        timeframe,
        "trades.csv",
    )


# ----------------------------
# CSV loaders
# ----------------------------

def _load_csv_dicts(path: str) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            out.append(row)
    return out


def _load_decisions(path: str) -> List[Dict[str, str]]:
    if not _exists(path):
        return []
    rows = _load_csv_dicts(path)
    # ensure sorted by ts for sanity
    rows = [r for r in rows if _decision_ts(r) is not None]
    rows.sort(key=lambda r: _decision_ts(r) or 0)
    return rows


def _load_trades(path: str) -> List[Dict[str, str]]:
    if not _exists(path):
        return []
    rows = _load_csv_dicts(path)
    # keep order stable; equivalence comparator will sort signatures anyway
    return rows


# ----------------------------
# Window + sync logic
# ----------------------------

def _min_max_ts(rows: List[Dict[str, str]]) -> Tuple[Optional[int], Optional[int]]:
    if not rows:
        return None, None
    ts = [_decision_ts(r) for r in rows]
    ts = [t for t in ts if t is not None]
    if not ts:
        return None, None
    return min(ts), max(ts)


def _find_first_mutual_flat_ts(
    live_by_ts: Dict[int, Dict[str, str]],
    bt_by_ts: Dict[int, Dict[str, str]],
    overlap_start: int,
    overlap_end: int,
) -> Optional[int]:
    """
    Find the first ts where BOTH sides are flat (no position).
    Used to "sync" comparison after warmup differences.
    """
    common_ts = sorted(set(live_by_ts.keys()) & set(bt_by_ts.keys()))
    for t in common_ts:
        if t < overlap_start or t > overlap_end:
            continue
        lpos = (live_by_ts[t].get("position_side") or "").strip()
        bpos = (bt_by_ts[t].get("position_side") or "").strip()
        if lpos == "" and bpos == "":
            return t
    return None


# ----------------------------
# Comparators
# ----------------------------

def compare_decisions_by_ts(
    *,
    live_path: str,
    bt_path: str,
) -> Tuple[bool, str, int, int, int]:
    """
    Compare decisions keyed by ts_ms within overlap window, synced at first mutual-flat ts.

    Returns:
      (ok, msg, overlap_start, overlap_end, sync_ts)
    """
    if not _exists(live_path):
        return False, f"[missing] {live_path}", 0, 0, 0
    if not _exists(bt_path):
        return False, f"[missing] {bt_path}", 0, 0, 0

    live_rows = _load_decisions(live_path)
    bt_rows = _load_decisions(bt_path)

    l0, l1 = _min_max_ts(live_rows)
    b0, b1 = _min_max_ts(bt_rows)

    if l0 is None or l1 is None:
        return False, "[decisions] LIVE has no ts_ms rows", 0, 0, 0
    if b0 is None or b1 is None:
        return False, "[decisions] BT has no ts_ms rows", 0, 0, 0

    overlap_start = max(int(l0), int(b0))
    overlap_end = min(int(l1), int(b1))

    msg_lines: List[str] = []
    msg_lines.append(f"[window] decisions LIVE=[{int(l0)},{int(l1)}]  BT=[{int(b0)},{int(b1)}]")
    msg_lines.append(f"[window] overlap=[{int(overlap_start)},{int(overlap_end)}]")

    if overlap_start > overlap_end:
        msg_lines.append("[decisions] FAIL: no overlap window")
        return False, "\n".join(msg_lines), overlap_start, overlap_end, overlap_start

    live_by_ts: Dict[int, Dict[str, str]] = {}
    for r in live_rows:
        t = _decision_ts(r)
        if t is None:
            continue
        if overlap_start <= t <= overlap_end:
            # if duplicates exist, keep last
            live_by_ts[int(t)] = r

    bt_by_ts: Dict[int, Dict[str, str]] = {}
    for r in bt_rows:
        t = _decision_ts(r)
        if t is None:
            continue
        if overlap_start <= t <= overlap_end:
            bt_by_ts[int(t)] = r

    sync_ts = _find_first_mutual_flat_ts(live_by_ts, bt_by_ts, overlap_start, overlap_end)
    if sync_ts is None:
        sync_ts = overlap_start
        msg_lines.append(f"[sync] no mutual-flat found; starting at overlap_start ts_ms={sync_ts}")
    else:
        msg_lines.append(f"[sync] starting comparison at first mutual-flat ts_ms={int(sync_ts)}")

    # restrict to >= sync_ts
    live_by_ts = {t: r for (t, r) in live_by_ts.items() if t >= sync_ts}
    bt_by_ts = {t: r for (t, r) in bt_by_ts.items() if t >= sync_ts}

    common_ts = sorted(set(live_by_ts.keys()) & set(bt_by_ts.keys()))
    if not common_ts:
        msg_lines.append("[decisions] FAIL: no common timestamps after sync")
        return False, "\n".join(msg_lines), overlap_start, overlap_end, sync_ts

    # Find ts present on one side only
    missing_in_live = sorted(set(bt_by_ts.keys()) - set(live_by_ts.keys()))
    missing_in_bt = sorted(set(live_by_ts.keys()) - set(bt_by_ts.keys()))

    # Tolerate "missing noop" rows:
    missing_noop_live = [t for t in missing_in_live if _is_noop_decision(bt_by_ts[t])]
    missing_noop_bt = [t for t in missing_in_bt if _is_noop_decision(live_by_ts[t])]

    # If anything missing is NOT a noop, fail loudly
    missing_bad_live = [t for t in missing_in_live if t not in set(missing_noop_live)]
    missing_bad_bt = [t for t in missing_in_bt if t not in set(missing_noop_bt)]

    if missing_bad_live or missing_bad_bt:
        msg_lines.append(
            f"[decisions] FAIL missing timestamps after sync: "
            f"missing_in_live={len(missing_bad_live)} missing_in_bt={len(missing_bad_bt)}"
        )
        msg_lines.append(f"missing_in_live (first 20): {missing_bad_live[:20]}")
        msg_lines.append(f"missing_in_bt   (first 20): {missing_bad_bt[:20]}")
        return False, "\n".join(msg_lines), overlap_start, overlap_end, sync_ts

    # Compare signatures for common timestamps
    for i, t in enumerate(common_ts):
        lsig = _decision_sig(live_by_ts[t])
        bsig = _decision_sig(bt_by_ts[t])
        if lsig != bsig:
            # build context around mismatch
            msg_lines.append(f"[decisions] first mismatch at index={i} ts_ms={t}")
            msg_lines.append("")
            msg_lines.append(f"--- context around mismatch (decisions) index={i} ---")

            left = max(0, i - 3)
            right = min(len(common_ts), i + 4)
            for j in range(left, right):
                tt = common_ts[j]
                l = _decision_sig(live_by_ts[tt])
                b = _decision_sig(bt_by_ts[tt])
                prefix = ">>" if j == i else "  "
                msg_lines.append(f"{prefix} {j:06d}  LIVE: {_fmt_dec_sig(l)}")
                msg_lines.append(f"{prefix} {j:06d}   BT : {_fmt_dec_sig(b)}")

            return False, "\n".join(msg_lines), overlap_start, overlap_end, sync_ts

    msg_lines.append(
        f"[decisions] PASS (common_ts={len(common_ts)} rows; "
        f"missing_noop_live={len(missing_noop_live)} missing_noop_bt={len(missing_noop_bt)})"
    )
    return True, "\n".join(msg_lines), overlap_start, overlap_end, sync_ts


def compare_trades_windowed(
    *,
    live_path: str,
    bt_path: str,
    start_ts_ms: int,
    end_ts_ms: int,
) -> Tuple[bool, str]:
    """
    Compare trade lifecycle only within [start_ts_ms, end_ts_ms] using entry_ts_ms.
    This prevents warmup trades (BT) from mismatching the LIVE capture.
    """
    # Missing trades files are allowed if both missing/empty.
    live_rows = _load_trades(live_path) if _exists(live_path) else []
    bt_rows = _load_trades(bt_path) if _exists(bt_path) else []

    def in_window(row: Dict[str, str]) -> bool:
        e = _safe_int(row.get("entry_ts_ms"))
        if e is None:
            return False
        return int(start_ts_ms) <= int(e) <= int(end_ts_ms)

    live_f = [r for r in live_rows if in_window(r)]
    bt_f = [r for r in bt_rows if in_window(r)]

    live_sigs = sorted((_trade_sig(r) for r in live_f), key=lambda t: (t[0], t[1], t[2], t[3]))
    bt_sigs = sorted((_trade_sig(r) for r in bt_f), key=lambda t: (t[0], t[1], t[2], t[3]))

    if live_sigs == bt_sigs:
        return True, f"[trades] PASS windowed ({len(live_sigs)} rows) window=[{start_ts_ms},{end_ts_ms}]"

    lines: List[str] = []
    lines.append(f"[trades] WINDOWED mismatch window=[{start_ts_ms},{end_ts_ms}]")
    lines.append(f"[trades] length mismatch: LIVE={len(live_sigs)} BT={len(bt_sigs)}")

    m = min(len(live_sigs), len(bt_sigs))
    first = None
    for i in range(m):
        if live_sigs[i] != bt_sigs[i]:
            first = i
            break
    if first is None and len(live_sigs) != len(bt_sigs):
        first = m

    lines.append(f"[trades] first mismatch at index={first}")
    lines.append("")
    lines.append(f"--- context around mismatch (trades) index={first} ---")

    def fmt(sig: Optional[Tuple[int, int, str, str]]) -> str:
        if not sig:
            return "<none>"
        e, x, side, reason = sig
        return f"entry={e}|exit={x}|side={side}|reason={reason}"

    left = max(0, (first or 0) - 3)
    right = min(max(len(live_sigs), len(bt_sigs)), (first or 0) + 4)

    for j in range(left, right):
        lsig = live_sigs[j] if j < len(live_sigs) else None
        bsig = bt_sigs[j] if j < len(bt_sigs) else None
        prefix = ">>" if j == first else "  "
        lines.append(f"{prefix} {j:06d}  LIVE: {fmt(lsig)}")
        lines.append(f"{prefix} {j:06d}   BT : {fmt(bsig)}")

    return False, "\n".join(lines)


# ----------------------------
# CLI
# ----------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="LIVE vs BACKTEST Behavioral Equivalence")
    ap.add_argument("--symbol", required=True, help="e.g. BTC_USD (folder form) or BTC/USD (config form)")
    ap.add_argument("--timeframe", required=True, help="e.g. 5m")
    ap.add_argument("--live-tag", required=True, help="e.g. coinbase")
    ap.add_argument("--bt-tag", required=True, help="e.g. coinbase_bt_<runid>")

    args = ap.parse_args()

    symbol = args.symbol.strip()
    timeframe = args.timeframe.strip()

    d_live = decisions_path(args.live_tag, symbol, timeframe)
    d_bt = decisions_path(args.bt_tag, symbol, timeframe)
    t_live = trades_path(args.live_tag, symbol, timeframe)
    t_bt = trades_path(args.bt_tag, symbol, timeframe)

    print("=== LIVE vs BACKTEST Behavioral Equivalence (overlap + sync-at-flat, ts-keyed) ===")
    print(f"symbol={symbol} timeframe={timeframe}")
    print(f"live_tag={args.live_tag}")
    print(f"bt_tag={args.bt_tag}")
    print("")
    print(f"[decisions] LIVE: {d_live}")
    print(f"[decisions]  BT : {d_bt}")
    print(f"[trades]    LIVE: {t_live}")
    print(f"[trades]     BT : {t_bt}")
    print("")

    ok_dec, msg_dec, overlap_start, overlap_end, sync_ts = compare_decisions_by_ts(
        live_path=d_live,
        bt_path=d_bt,
    )
    print(msg_dec)

    # If decisions failed, stop early (trades are meaningless if decisions diverge)
    if not ok_dec:
        print("")
        print("🚨 OVERALL FAIL: mismatch detected.")
        raise SystemExit(1)

    ok_tr, msg_tr = compare_trades_windowed(
        live_path=t_live,
        bt_path=t_bt,
        start_ts_ms=int(sync_ts),
        end_ts_ms=int(overlap_end),
    )
    print(msg_tr)

    if ok_dec and ok_tr:
        print("")
        print("✅ OVERALL PASS: Live paper and backtest match on lifecycle behavior (synced overlap).")
        raise SystemExit(0)

    print("")
    print("🚨 OVERALL FAIL: mismatch detected.")
    raise SystemExit(1)


if __name__ == "__main__":
    main()

