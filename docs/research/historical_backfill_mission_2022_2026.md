# Historical OHLCV Backfill Mission — Completion Report

Date completed: 2026-07-30

## 1. Mission status

Mission status: COMPLETE
Dataset audit: PASS
Production strategy changes: None
Live paper namespace modified: No
Historical namespace: `coinbase_history_2022_20260209`

The Coinbase BTC/USD 5-minute historical dataset was backfilled,
validated, partitioned, and audited for:

- Start inclusive: `2022-01-01T00:00:00Z`
- End exclusive: `2026-02-09T00:00:00Z`

Final results:

- 1,500 daily Parquet partitions
- 431,842 stored 5-minute bars
- 432,000 theoretical 5-minute bars
- 158 confirmed missing Coinbase bars
- 0 duplicate timestamps
- 7 confirmed Coinbase source outages
- Exact first and last timestamps
- Full dataset audit passed

## 2. Purpose

The goal was to create a sufficiently long, reproducible historical
dataset for scorer and strategy research without modifying the active
paper-trading data or production behavior.

The resulting dataset will support:

- chronological train and validation windows
- walk-forward scorer research
- broader market-regime coverage
- out-of-sample evaluation
- repeatable parameter research
- improved trade-count evidence

This mission did not change strategy parameters, scorer settings, live
execution policy, or the LONG_ONLY runtime baseline.

## 3. Storage contract

Historical data is stored under:

`data/raw/coinbase_history_2022_20260209/BTC_USD/5m/`

Daily partition layout:

`date=YYYY-MM-DD/bars.parquet`

The namespace is intentionally separate from:

`paper_oldbox_live`

The historical backfill therefore did not modify or merge with the live
paper namespace.

## 4. Git and deployment findings

During the mission, two overly broad ignore rules were discovered.

### 4.1 Git ignore rule

The previous `.gitignore` entry was:

`data/`

That rule matched every directory named `data`, including the source
directory:

`files/data/`

As a result, these existing core modules had never been tracked by Git:

- `files/data/decisions.py`
- `files/data/paths.py`
- `files/data/trades.py`

The rule was corrected to:

`/data/`

This now ignores only the top-level runtime data directory.

The previously hidden source modules were compared between LOCAL and
OLD-BOX. Their SHA-256 checksums matched exactly before they were added
to Git.

### 4.2 Rsync exclusion rule

The previous `ops/rsync_exclude.txt` entry was also:

`data/`

That prevented most of `files/data/` from deploying to OLD-BOX. A
single exception for `files/data/paths.py` had acted as a partial
workaround.

The deploy exclusion was corrected to:

`/data/`

The path-specific workaround was removed. Source files under
`files/data/` now deploy normally, while top-level runtime data remains
excluded.

### 4.3 Tooling-container mount

The new CLI was deployed under:

`ops/research/backfill_ohlcv.py`

The running `trade` container initially could not import it because
only `files/`, `data/`, and `notebooks/` were mounted.

The `trade` service now also mounts:

`./ops:/work/ops`

The live `paper` service was not given this mount because it does not
need research CLI tools.

## 5. New implementation

### 5.1 Reusable module

Added:

`files/data/historical_backfill.py`

Responsibilities include:

- constructing the CCXT exchange client
- deterministic `since` pagination
- inclusive-start and exclusive-end range handling
- timeframe conversion
- OHLCV normalization
- timestamp deduplication
- schema and numeric validation
- exact boundary validation
- cadence validation
- retry with exponential backoff
- persistence through the existing atomic Parquet writer

### 5.2 CLI

Added:

`ops/research/backfill_ohlcv.py`

Capabilities include:

- read-only dry-run mode by default
- explicit `--write` requirement for persistence
- isolated data-tag selection
- bounded 30-day chunks by default
- independently validated and persisted chunks
- safe reruns through timestamp-deduplicating storage
- configurable page size
- configurable page retries
- configurable exponential-backoff delay
- structured per-chunk and total summaries

### 5.3 Persistence behavior

Validated bars are written using:

`files.data.storage.append_ohlcv_parquet`

That writer provides:

- canonical daily partitioning
- merge with existing partitions
- timestamp deduplication
- sorted output
- atomic temporary-file replacement

## 6. Validation sequence

The backfill path was proven incrementally.

### 6.1 Read-only sample

Range:

`2026-02-07T00:00:00Z` to `2026-02-09T00:00:00Z`

Result:

- 576 expected bars
- 576 validated bars
- 0 duplicates
- exact boundaries
- correct 5-minute cadence
- no persistence

### 6.2 Controlled sample write

The same two-day range was persisted.

Result:

- 2 daily partitions
- 576 stored rows
- 0 duplicate timestamps
- 0 cadence errors

### 6.3 Idempotent rerun

The sample was rerun with one-day chunks and `--write`.

Result:

- both chunks passed
- existing partitions remained at 576 total rows
- 0 duplicate timestamps
- exact boundaries preserved
- idempotent storage check passed

### 6.4 Full historical execution

The complete range was downloaded in bounded chunks. Each chunk was
fully validated before persistence.

When a chunk contained missing exchange candles, the entire chunk was
rejected before writing. Valid sections on either side of confirmed
gaps were then persisted separately.

No synthetic candles were created.

No prices from another exchange were substituted.

## 7. Row-accounting correction

The first dry run reported exchange-returned rows beyond the requested
exclusive end as duplicate rows.

The metric was corrected into two separate fields:

- `out_of_window_rows_filtered`
- `duplicate_rows_removed`

After correction, the proven sample reported:

- 24 out-of-window rows filtered
- 0 duplicate rows removed
- 576 validated rows

## 8. Transient response versus genuine source gap

Two data-quality situations were observed.

### 8.1 Transient incomplete response

One early request temporarily returned an incomplete sequence. A later
read-only rerun returned complete data.

This demonstrated that retries for exceptions alone cannot guarantee
that every successful HTTP response is complete.

The final validator still protected storage because it rejected the
incomplete chunk.

### 8.2 Genuine Coinbase outages

Seven intervals were repeatedly absent from Coinbase's 5-minute feed.

Each interval was also checked against Coinbase's 1-minute feed. Every
underlying minute was missing, confirming source-data outages rather
than aggregation or pagination errors.

## 9. Confirmed Coinbase gaps

### Gap 1

- Start: `2022-08-12T11:25:00Z`
- End exclusive: `2022-08-12T11:30:00Z`
- Missing 5-minute bars: 1
- Missing 1-minute bars: 5

### Gap 2

- Start: `2023-03-04T17:00:00Z`
- End exclusive: `2023-03-04T21:35:00Z`
- Missing 5-minute bars: 55
- Missing 1-minute bars: 275

### Gap 3

- Start: `2023-05-19T07:45:00Z`
- End exclusive: `2023-05-19T08:25:00Z`
- Missing 5-minute bars: 8
- Missing 1-minute bars: 40

### Gap 4

- Start: `2024-05-31T22:20:00Z`
- End exclusive: `2024-05-31T23:15:00Z`
- Missing 5-minute bars: 11
- Missing 1-minute bars: 55

### Gap 5

- Start: `2024-10-26T16:10:00Z`
- End exclusive: `2024-10-26T17:15:00Z`
- Missing 5-minute bars: 13
- Missing 1-minute bars: 65

### Gap 6

- Start: `2025-10-25T14:55:00Z`
- End exclusive: `2025-10-25T15:00:00Z`
- Missing 5-minute bars: 1
- Missing 1-minute bars: 5

### Gap 7

- Start: `2025-10-25T15:15:00Z`
- End exclusive: `2025-10-25T21:00:00Z`
- Missing 5-minute bars: 69
- Missing 1-minute bars: 345

Total missing 5-minute bars: 158

The authoritative machine-readable manifest is:

`docs/research/coinbase_history_2022_20260209_gaps.json`

## 10. Final dataset audit

Final authoritative audit:

- Dataset root:
  `data/raw/coinbase_history_2022_20260209/BTC_USD/5m`
- Partition count: 1,500
- Expected partition count: 1,500
- Stored rows: 431,842
- Theoretical rows: 432,000
- Missing rows: 158
- Duplicate timestamps: 0
- First timestamp: `2022-01-01T00:00:00Z`
- Last timestamp: `2026-02-08T23:55:00Z`
- Cadence-gap count: 7
- Gap missing-bar total: 158
- Audit result: PASS

## 11. Old-box operational verification

Before and after deployment changes, the active paper system was
checked using the correct namespace:

`paper_oldbox_live`

Verified state:

- `DATA_TAG=paper_oldbox_live`
- `CCXT_EXCHANGE=coinbase`
- `SYMBOL=BTC/USD`
- `TIMEFRAME=5m`
- `DRY_RUN=1`
- `ARMED=1`

Observed runtime behavior:

- market data fetched normally
- raw bars persisted normally
- one decision recorded per closed 5-minute bar
- already-processed bars skipped safely
- live-paper namespace remained separate from historical data

Health-check result after deployment:

- healthcheck pass
- 0 bad recent rows
- 0 bad tail rows
- 249 clean trailing cadence differences
- raw data fresh
- decisions fresh

The `event_risk` orphan warning remains informational because that
service is intentionally isolated.

## 12. Commits created during the mission

- `4054304` — Add scorer research and walk-forward framework
- `277bcdb` — Track data modules and add historical backfill support
- `53c7dd6` — Fix deploy exclusion for source data modules
- `d876f8f` — Add historical OHLCV backfill CLI
- `01803f8` — Mount ops tools in trade container
- `9a0ef53` — Fix historical backfill row accounting
- `40d57c0` — Add resumable chunked historical backfill

## 13. Research-use contract

The dataset is suitable for research provided that the seven confirmed
gaps are treated explicitly.

Required rules:

- Do not synthesize missing prices.
- Do not substitute another exchange inside this Coinbase dataset.
- Do not interpret a gap as a normal 5-minute return.
- Do not allow a simulated position to remain active across a gap
  without an explicit gap policy.
- Do not build train, validation, or test boundaries that silently cross
  a gap.
- Reset or re-warm stateful indicators after a gap when appropriate.
- Include the gap manifest in reproducibility artifacts.
- Keep validation and out-of-sample periods locked once defined.

## 14. Recommended next mission

The next mission should integrate the historical namespace and gap
manifest into the research loader.

The loader should:

1. Load the isolated historical data tag.
2. Detect segments separated by confirmed gaps.
3. Expose continuous segments explicitly.
4. Prevent backtests from silently crossing outages.
5. Apply deterministic feature warmup per segment.
6. Define chronological train, validation, and out-of-sample windows.
7. Preserve the previously rejected entry-sequence candidate as frozen.
8. Start a new scorer-search cycle using the expanded history.

## 15. Final conclusion

The historical backfill mission is complete.

The project now has a long, independently stored, audited Coinbase
BTC/USD 5-minute dataset suitable for disciplined chronological
research.

The dataset is not perfectly continuous because Coinbase itself lacks
158 bars across seven confirmed outages. Those absences are documented
rather than hidden, repaired, or fabricated.

Production behavior was preserved throughout the mission.
