# DATA LAYOUT & LIFECYCLE

This document explains the on-disk data layout under `data/`, its lifecycle,
and how LIVE and BACKTEST interact with it.

---

## 1) High-level structure

data/
├── raw/ # Canonical market data (ground truth)
├── processed/ # Decisions & trades emitted by runs
│ ├── decisions/
│ ├── trades/
│ └── _archive/
├── cache/ # Ephemeral, safe to delete
└── data_map.txt # Human reference only


Each layer has a **single responsibility**.

---

## 2) `data/raw/` — market data (ground truth)

`data/raw/{exchange}/{SYMBOL}/{timeframe}/date=YYYY-MM-DD/bars.parquet`


Example:

`data/raw/coinbase/BTC_USD/5m/date=2026-02-06/bars.parquet`


Properties:
- Contains **closed bars only**
- UTC timestamps
- Atomic writes
- Append-only by timestamp
- Duplicate timestamps resolved deterministically

Used by:
- BACKTEST replay
- LIVE restart safety
- Equivalence validation

This directory alone is sufficient to reproduce historical behavior.

---

## 3) `data/processed/decisions/` — decision logs

data/processed/decisions/{run_id}/{SYMBOL}/{timeframe}/decisions.csv


Examples:

coinbase/
coinbase_bt_20260205_202235_p2a/
monotonic_test/


Properties:
- One row per closed bar
- Strictly increasing `ts_ms`
- Append-only
- Run-specific isolation

Folder names encode **run identity**, not strategy versions.

---

## 4) `data/processed/trades/` — trade records

data/processed/trades/{run_id}/{SYMBOL}/{timeframe}/trades.csv


Properties:
- One row per completed trade
- Emitted on exit only
- PnL may diverge between LIVE and BACKTEST

Trades are derived artifacts, not primary state.

---

## 5) `data/processed/_archive/` — historical snapshots

Purpose:
- Preserve pre-migration data
- Enable forensic comparison

Rules:
- Never read by code
- Safe to delete after backup
- Exists only for human reference

---

## 6) Cache & test artifacts

### `data/cache/`
- Ephemeral
- Safe to delete at any time

### Test folders

monotonic_test/
storage_test/


Used for:
- Invariant testing
- Manual validation
- CI experiments

Not used by LIVE or BACKTEST.

---

## 7) Data lifecycle summary

Market Fetch
↓
data/raw/ (atomic, canonical)
↓
LIVE or BACKTEST
↓
decisions.csv (append-only)
↓
trades.csv (on exit only)


No stage mutates earlier stages.

---

## 8) What must never be done

- Editing CSVs in place
- Deleting rows from decision logs
- Writing BACKTEST output into LIVE directories
- Inferring correctness from PnL alone

---

## 9) Design intent

The data layout is intentionally verbose to enable:
- Deterministic replay
- Post-mortem debugging
- Correctness proofs
- Safe iteration

Disk is cheap. Ambiguity is not.

