# ARCHIVE — Project Snapshots

This file preserves older project-state notes that may still contain useful engineering context, but are not the canonical source of truth for the current system.

Use this file as historical reference only.

--------------------------------------------------
ARCHIVE STATUS
--------------------------------------------------

This material reflects earlier phases of the project, especially around:

- data layout cleanup
- path normalization
- raw/processed storage architecture
- report generation
- trailing stop implementation/testing
- backtest/live equivalence style workflows

It may still contain valid ideas and file references, but it must not override the current canonical handoff or operator guide.

--------------------------------------------------
HISTORICAL SNAPSHOT — DATA ARCHITECTURE PHASE
--------------------------------------------------

Historical layout snapshot:

/
├── raw/                    # market data (parquet, partitioned)
│   └── {exchange}/{symbol}/{timeframe}/date=YYYY-MM-DD/bars.parquet
├── processed/
│   ├── decisions/          # per-bar decisions CSV
│   │   └── {exchange}/{symbol}/{timeframe}/decisions.csv
│   ├── trades/             # closed trades CSV
│   │   └── {exchange}/{symbol}/{timeframe}/trades.csv
│   └── reports/            # analytics outputs
│       └── {exchange}/{symbol}/{timeframe}/equity_curve.csv
├── cache/                  # optional / temporary
└── __init__.py

Historical claims from that phase:

- working trading loop
- enforced data architecture
- decisions, trades, and reports writing consistently
- reports reading the same paths writers use
- no circular imports
- reproducible append_trade_csv + report test
- baseline trailing stop work

Historical path-helper claim:

Canonical path helpers live in:

files/data/paths.py

Historical modules listed in that phase:

- files/main.py
- files/data/paths.py
- files/data/storage.py
- files/data/decisions.py
- files/data/trades.py
- files/utils/trade_report.py
- files/broker/paper.py

Historical testing note:

- live loop
- manual trade append
- report generation

Historical non-issues called out:

- 1970-01-01 in report caused by test timestamps
- report logic considered correct at that time
- deleting data/processed/* was safe during testing

--------------------------------------------------
HISTORICAL SNAPSHOT — TRAILING STOP BASELINE
--------------------------------------------------

Historical summary:

The system had a working end-to-end loop with:

- market fetch
- persist raw bars
- load recent
- compute features
- validate
- determine market state
- entry/exit evaluation
- paper broker tracking
- decisions CSV writing
- trades CSV writing
- report generation

Historical trailing-stop claims included:

- ATR-based ratcheting trailing stops
- side-aware anchor
- intrabar stop detection
- next-bar entry model to avoid same-bar stop artifacts
- stop evaluation skipped on entry bar
- broker storing trailing_anchor_price
- decisions including bar_high and bar_low
- test-mode settings such as MAX_HOLD_BARS = 2
- FORCE_SIDE override
- 0.01 sizing for safe testing
- fee/slippage temporarily 0.0 during tests

Historical “files relevant next time” note:

- files/strategy/rules.py
- files/core/types.py
- files/broker/paper.py

--------------------------------------------------
HOW TO USE THIS ARCHIVE
--------------------------------------------------

Use this file only for:

- historical orientation
- comparing earlier architecture to current architecture
- recovering older design intent
- finding old file references that may still matter

Do not use this file as authority for:

- current operator workflow
- current deploy process
- current old-box runtime truth
- current degraded-mode behavior
- current RAG workflow
- current canonical docs

--------------------------------------------------
RULE
--------------------------------------------------

If archive text conflicts with any current handoff or operator guide, the current handoff/operator guide wins.

Archive is reference.
Canonical docs are truth.
