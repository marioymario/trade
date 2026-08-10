# Data Universe Expansion

Current branch:
research/data-universe-expansion

Purpose:
Expand historical research beyond the original Coinbase BTC/USD 5m universe while preserving independent provenance, manifests, fingerprints, gap handling, and replay identity.

## Current audited research sources

### Coinbase BTC/USD

Data tag:
coinbase_history_2022_20260209

Timeframe:
5m

Coverage:
2022-01-01T00:00:00Z
through
2026-02-09T00:00:00Z exclusive

Stored bars:
431842

Confirmed gaps:
7

Physical segments:
8

Manifest fingerprint:
43b10397ff6b513eb6917266e0cfccb4f866721ec829fff90b60fa907f10478c

Manifest:
files/research/contracts/coinbase_history_2022_20260209_gaps.json

This dataset remains unchanged.

### Coinbase ETH/USD

Data tag:
coinbase_eth_history_2018_20260209

Timeframe:
5m

Coverage:
2018-01-01T00:00:00Z
through
2026-02-09T00:00:00Z exclusive

Daily partitions:
2961

Theoretical bars:
852768

Stored bars:
852321

Missing bars:
447

Duplicate timestamps:
0

Gap count:
42

Physical segments:
43

Manifest fingerprint:
f870466613827e1b7a7062d9428956444f7e48e159394a9aeaf7a5b7349f8314

Manifest:
files/research/contracts/coinbase_eth_history_2018_20260209_gaps.json

Gap verification:
40 gaps are confirmed Coinbase source outages with all underlying
1-minute bars absent.

2 gaps are confirmed missing 5-minute candles with partial underlying
1-minute availability.

No synthetic bars were created.

No cross-exchange substitution was used.

## Reusable ingestion changes

ops/research/backfill_ohlcv.py

Existing strict historical validation remains the default.

New explicit:
--recover-gaps

Behavior:
- strict validation is still used
- valid source ranges are persisted
- missing intervals are isolated
- unresolved intervals are reported
- no missing candles are fabricated
- non-recoverable acquisition failures still abort

The original strict mode was regression tested against the known
2018-02-01 ETH gap and still exits with HistoricalBackfillError.

## Reusable manifest generation

Added:

files/research/historical_manifest_builder.py

ops/research/build_historical_gap_manifest.py

The builder:
- audits persisted historical bars
- verifies boundaries and row accounting
- rejects duplicate timestamps
- discovers missing timeframe intervals
- verifies missing intervals against Coinbase 1-minute history
- assigns explicit gap classifications
- writes the canonical manifest deterministically

ETH manifest deterministic rerun:
PASS

Manifest SHA-256:
b850241df4fbdf545deecc16613c561c5f2d0e0e99898c233729aeef636dca48

## Manifest schema compatibility

Historical manifest schema v1 remains supported.

The original BTC manifest still resolves with its exact original
fingerprint.

Schema v2 adds accurate classification for missing timeframe candles
where underlying 1-minute data is partially available.

Both classifications remain physical replay gaps.

## Research contract

Each research universe remains independent through:

source exchange
data tag
symbol
timeframe
dataset boundaries
manifest
manifest fingerprint
physical segments

Datasets are not merged at the raw-data layer.

Cross-symbol evidence should be combined only at the research
observation/aggregation layer while retaining source identity.

## Next mission

Bring Coinbase ETH/USD through the existing gap-aware strategy and
entry-quality research machinery.

The purpose is replication on an independent asset universe, not
retuning against ETH.

BTC 2025+ remains locked and is not opened by this expansion.
