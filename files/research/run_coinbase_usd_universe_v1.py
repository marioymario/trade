from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from files.research.historical_manifest_builder import (
    canonical_manifest_path,
)


UNIVERSE_ID = "research_universe_coinbase_usd_v1"
SOURCE_EXCHANGE = "coinbase"
TIMEFRAME = "5m"

COMMON_START = "2022-01-01T00:00:00Z"
COMMON_END_EXCLUSIVE = "2026-02-09T00:00:00Z"

RESEARCH_DEVELOPMENT_END_EXCLUSIVE = "2025-01-01T00:00:00Z"

LIQUIDITY_MIN_30D_USD = 10_000_000.0
LIQUIDITY_MIN_24H_USD = 100_000.0

REPO_ROOT = Path(__file__).resolve().parents[2]

BACKFILL_SCRIPT = (
    REPO_ROOT
    / "ops"
    / "research"
    / "backfill_ohlcv.py"
)

MANIFEST_SCRIPT = (
    REPO_ROOT
    / "ops"
    / "research"
    / "build_historical_gap_manifest.py"
)


@dataclass(frozen=True)
class SymbolContract:
    symbol: str
    data_tag: str
    acquisition_start: str
    acquisition_end_exclusive: str
    already_canonical: bool = False


def new_contract(symbol: str) -> SymbolContract:
    base = symbol.split("/", maxsplit=1)[0].lower()

    return SymbolContract(
        symbol=symbol,
        data_tag=(
            f"coinbase_{base}_history_2022_20260209"
        ),
        acquisition_start=COMMON_START,
        acquisition_end_exclusive=COMMON_END_EXCLUSIVE,
    )


SYMBOL_CONTRACTS = (
    SymbolContract(
        symbol="BTC/USD",
        data_tag="coinbase_history_2022_20260209",
        acquisition_start="2022-01-01T00:00:00Z",
        acquisition_end_exclusive=COMMON_END_EXCLUSIVE,
        already_canonical=True,
    ),
    SymbolContract(
        symbol="ETH/USD",
        data_tag="coinbase_eth_history_2018_20260209",
        acquisition_start="2018-01-01T00:00:00Z",
        acquisition_end_exclusive=COMMON_END_EXCLUSIVE,
        already_canonical=True,
    ),
    new_contract("SOL/USD"),
    new_contract("ZEC/USD"),
    new_contract("ADA/USD"),
    new_contract("XLM/USD"),
    new_contract("LINK/USD"),
    new_contract("DOGE/USD"),
    new_contract("LTC/USD"),
    new_contract("UNI/USD"),
    new_contract("AVAX/USD"),
    new_contract("AAVE/USD"),
    new_contract("BICO/USD"),
    new_contract("DOT/USD"),
    new_contract("ICP/USD"),
    new_contract("FET/USD"),
    new_contract("BCH/USD"),
    new_contract("ALGO/USD"),
    new_contract("CRV/USD"),
    new_contract("COTI/USD"),
    new_contract("OXT/USD"),
    new_contract("FIL/USD"),
    new_contract("SHIB/USD"),
    new_contract("TRAC/USD"),
    new_contract("ATOM/USD"),
    new_contract("DASH/USD"),
    new_contract("CRO/USD"),
    new_contract("QNT/USD"),
    new_contract("JASMY/USD"),
)


ACQUISITION_RANGES = (
    (
        "2022",
        "2022-01-01T00:00:00Z",
        "2023-01-01T00:00:00Z",
    ),
    (
        "2023",
        "2023-01-01T00:00:00Z",
        "2024-01-01T00:00:00Z",
    ),
    (
        "2024",
        "2024-01-01T00:00:00Z",
        "2025-01-01T00:00:00Z",
    ),
    (
        "2025",
        "2025-01-01T00:00:00Z",
        "2026-01-01T00:00:00Z",
    ),
    (
        "2026_partial",
        "2026-01-01T00:00:00Z",
        COMMON_END_EXCLUSIVE,
    ),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            value,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    temporary.replace(path)


def load_json(
    path: Path,
    default: dict[str, Any],
) -> dict[str, Any]:
    if not path.exists():
        return default

    value = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    if not isinstance(value, dict):
        raise ValueError(
            f"Expected JSON object: {path}"
        )

    return value


def manifest_contract_matches(
    *,
    contract: SymbolContract,
    manifest_path: Path,
) -> tuple[bool, str]:
    if not manifest_path.exists():
        return False, "manifest_missing"

    try:
        manifest = json.loads(
            manifest_path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as exc:
        return (
            False,
            f"manifest_unreadable:{type(exc).__name__}",
        )

    expected = {
        "data_tag": contract.data_tag,
        "symbol": contract.symbol,
        "timeframe": TIMEFRAME,
    }

    for key, expected_value in expected.items():
        observed = manifest.get(key)

        if observed != expected_value:
            return (
                False,
                f"{key}_mismatch:"
                f"{observed!r}!={expected_value!r}",
            )

    return True, "ok"


def run_command(
    *,
    command: list[str],
    log_path: Path,
) -> int:
    log_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with log_path.open(
        "w",
        encoding="utf-8",
    ) as log:
        process = subprocess.Popen(
            command,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

        started = time.monotonic()
        next_heartbeat_seconds = 30

        while True:
            returncode = process.poll()

            if returncode is not None:
                return returncode

            time.sleep(5)

            elapsed_seconds = int(
                time.monotonic() - started
            )

            if elapsed_seconds >= next_heartbeat_seconds:
                print(
                    "        working "
                    f"elapsed={elapsed_seconds}s "
                    f"log={log_path}",
                    flush=True,
                )
                next_heartbeat_seconds += 30


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Build the frozen Coinbase USD Research Universe V1 "
            "using the existing historical backfill and manifest "
            "contracts."
        )
    )

    parser.add_argument(
        "--data-root",
        default="/work/data",
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Perform backfills and manifest writes. "
            "Without this flag, print the deterministic plan only."
        ),
    )

    parser.add_argument(
        "--only-symbol",
        default="",
        help=(
            "Optional single CCXT symbol for practical verification "
            "or targeted recovery, for example SOL/USD."
        ),
    )

    parser.add_argument(
        "--page-limit",
        type=int,
        default=300,
    )

    parser.add_argument(
        "--chunk-days",
        type=int,
        default=30,
    )

    parser.add_argument(
        "--max-page-attempts",
        type=int,
        default=6,
    )

    parser.add_argument(
        "--initial-backoff-seconds",
        type=float,
        default=1.0,
    )

    return parser


def main() -> None:
    args = build_parser().parse_args()

    data_root = Path(
        args.data_root
    )

    universe_root = (
        data_root
        / "processed"
        / "research"
        / "universe_builds"
        / UNIVERSE_ID
    )

    logs_root = universe_root / "logs"
    state_path = universe_root / "state.json"
    summary_path = universe_root / "summary.json"

    contracts = list(
        SYMBOL_CONTRACTS
    )

    if args.only_symbol:
        contracts = [
            contract
            for contract in contracts
            if contract.symbol == args.only_symbol
        ]

        if not contracts:
            raise SystemExit(
                f"Unknown universe symbol: {args.only_symbol}"
            )

    print()
    print("=== COINBASE USD RESEARCH UNIVERSE V1 ===")
    print(
        f"mode={'execute' if args.execute else 'plan'}"
    )
    print(f"universe_id={UNIVERSE_ID}")
    print(f"source_exchange={SOURCE_EXCHANGE}")
    print(f"timeframe={TIMEFRAME}")
    print(f"candidate_count={len(SYMBOL_CONTRACTS)}")
    print(
        "already_canonical_count="
        f"{sum(c.already_canonical for c in SYMBOL_CONTRACTS)}"
    )
    print(
        "new_dataset_count="
        f"{sum(not c.already_canonical for c in SYMBOL_CONTRACTS)}"
    )
    print(
        "development_research_end_exclusive="
        f"{RESEARCH_DEVELOPMENT_END_EXCLUSIVE}"
    )
    print(f"data_root={data_root}")
    print("=========================================")
    print()

    for index, contract in enumerate(
        contracts,
        start=1,
    ):
        status = (
            "REUSE"
            if contract.already_canonical
            else "ACQUIRE"
        )

        print(
            f"{index:>2}/{len(contracts):<2} "
            f"{contract.symbol:<10} "
            f"{status:<8} "
            f"{contract.data_tag}"
        )

    if not args.execute:
        return

    state = load_json(
        state_path,
        default={
            "universe_id": UNIVERSE_ID,
            "created_utc": utc_now(),
            "symbols": {},
        },
    )

    symbol_results: list[dict[str, Any]] = []

    for index, contract in enumerate(
        contracts,
        start=1,
    ):
        symbol_key = contract.symbol

        symbol_state = state[
            "symbols"
        ].setdefault(
            symbol_key,
            {
                "data_tag": contract.data_tag,
                "ranges": {},
            },
        )

        manifest_path = canonical_manifest_path(
            data_tag=contract.data_tag
        )

        manifest_ok, manifest_reason = (
            manifest_contract_matches(
                contract=contract,
                manifest_path=manifest_path,
            )
        )

        if contract.already_canonical:
            final_status = (
                "REUSED_CANONICAL"
                if manifest_ok
                else "FAILED_EXISTING_MANIFEST"
            )

            print(
                f"[{index:>2}/{len(contracts)}] "
                f"{contract.symbol:<10} "
                f"{final_status}"
            )

            symbol_results.append(
                {
                    "symbol": contract.symbol,
                    "data_tag": contract.data_tag,
                    "status": final_status,
                    "manifest_path": str(
                        manifest_path
                    ),
                    "reason": manifest_reason,
                }
            )

            continue

        if manifest_ok:
            print(
                f"[{index:>2}/{len(contracts)}] "
                f"{contract.symbol:<10} "
                "SKIP_ALREADY_AUDITED"
            )

            symbol_results.append(
                {
                    "symbol": contract.symbol,
                    "data_tag": contract.data_tag,
                    "status": "AUDITED",
                    "manifest_path": str(
                        manifest_path
                    ),
                    "reason": "existing_manifest",
                }
            )

            continue

        print(
            f"[{index:>2}/{len(contracts)}] "
            f"{contract.symbol:<10} START"
        )

        symbol_failed = False
        failure_reason = ""

        for (
            range_name,
            range_start,
            range_end,
        ) in ACQUISITION_RANGES:
            range_state = symbol_state[
                "ranges"
            ].get(
                range_name,
                {}
            )

            if (
                range_state.get("status")
                == "completed"
            ):
                print(
                    f"    {range_name:<12} "
                    "SKIP_CHECKPOINT"
                )
                continue

            log_path = (
                logs_root
                / contract.symbol.replace(
                    "/",
                    "_",
                )
                / f"backfill_{range_name}.log"
            )

            command = [
                sys.executable,
                str(BACKFILL_SCRIPT),
                "--ccxt-exchange",
                SOURCE_EXCHANGE,
                "--data-tag",
                contract.data_tag,
                "--symbol",
                contract.symbol,
                "--timeframe",
                TIMEFRAME,
                "--start",
                range_start,
                "--end",
                range_end,
                "--page-limit",
                str(args.page_limit),
                "--chunk-days",
                str(args.chunk_days),
                "--max-page-attempts",
                str(args.max_page_attempts),
                "--initial-backoff-seconds",
                str(
                    args.initial_backoff_seconds
                ),
                "--recover-gaps",
                "--write",
            ]

            print(
                f"    {range_name:<12} "
                "BACKFILL"
            )

            returncode = run_command(
                command=command,
                log_path=log_path,
            )

            if returncode != 0:
                symbol_failed = True
                failure_reason = (
                    f"backfill_failed:"
                    f"{range_name}:"
                    f"returncode={returncode}"
                )

                symbol_state[
                    "ranges"
                ][range_name] = {
                    "status": "failed",
                    "returncode": returncode,
                    "log_path": str(
                        log_path
                    ),
                    "updated_utc": utc_now(),
                }

                atomic_write_json(
                    state_path,
                    state,
                )

                print(
                    f"    {range_name:<12} "
                    f"FAILED rc={returncode}"
                )

                break

            symbol_state[
                "ranges"
            ][range_name] = {
                "status": "completed",
                "returncode": 0,
                "log_path": str(
                    log_path
                ),
                "updated_utc": utc_now(),
            }

            atomic_write_json(
                state_path,
                state,
            )

            print(
                f"    {range_name:<12} "
                "OK"
            )

        if symbol_failed:
            print(
                f"[{index:>2}/{len(contracts)}] "
                f"{contract.symbol:<10} FAILED"
            )

            symbol_results.append(
                {
                    "symbol": contract.symbol,
                    "data_tag": contract.data_tag,
                    "status": "FAILED",
                    "manifest_path": str(
                        manifest_path
                    ),
                    "reason": failure_reason,
                }
            )

            continue

        manifest_log = (
            logs_root
            / contract.symbol.replace(
                "/",
                "_",
            )
            / "manifest.log"
        )

        manifest_command = [
            sys.executable,
            str(MANIFEST_SCRIPT),
            "--source-exchange",
            SOURCE_EXCHANGE,
            "--data-tag",
            contract.data_tag,
            "--symbol",
            contract.symbol,
            "--timeframe",
            TIMEFRAME,
            "--start",
            COMMON_START,
            "--end",
            COMMON_END_EXCLUSIVE,
            "--data-root",
            str(data_root),
            "--write",
        ]

        print("    manifest     BUILD/AUDIT")

        manifest_returncode = run_command(
            command=manifest_command,
            log_path=manifest_log,
        )

        if manifest_returncode != 0:
            final_status = "FAILED"
            failure_reason = (
                "manifest_failed:"
                f"returncode={manifest_returncode}"
            )

        else:
            manifest_ok, manifest_reason = (
                manifest_contract_matches(
                    contract=contract,
                    manifest_path=manifest_path,
                )
            )

            if manifest_ok:
                final_status = "AUDITED"
                failure_reason = ""
            else:
                final_status = "FAILED"
                failure_reason = (
                    "manifest_contract_invalid:"
                    f"{manifest_reason}"
                )

        symbol_state[
            "final_status"
        ] = final_status

        symbol_state[
            "manifest_path"
        ] = str(
            manifest_path
        )

        symbol_state[
            "updated_utc"
        ] = utc_now()

        atomic_write_json(
            state_path,
            state,
        )

        print(
            f"[{index:>2}/{len(contracts)}] "
            f"{contract.symbol:<10} "
            f"{final_status}"
        )

        symbol_results.append(
            {
                "symbol": contract.symbol,
                "data_tag": contract.data_tag,
                "status": final_status,
                "manifest_path": str(
                    manifest_path
                ),
                "reason": failure_reason,
            }
        )

    counts: dict[str, int] = {}

    for result in symbol_results:
        status = result["status"]

        counts[status] = (
            counts.get(
                status,
                0,
            )
            + 1
        )

    summary = {
        "schema_version": 1,
        "universe_id": UNIVERSE_ID,
        "generated_utc": utc_now(),
        "source_exchange": SOURCE_EXCHANGE,
        "timeframe": TIMEFRAME,
        "common_start": COMMON_START,
        "common_end_exclusive": (
            COMMON_END_EXCLUSIVE
        ),
        "development_research_end_exclusive": (
            RESEARCH_DEVELOPMENT_END_EXCLUSIVE
        ),
        "liquidity_contract": {
            "minimum_30d_usd": (
                LIQUIDITY_MIN_30D_USD
            ),
            "minimum_24h_usd": (
                LIQUIDITY_MIN_24H_USD
            ),
        },
        "full_candidate_count": len(
            SYMBOL_CONTRACTS
        ),
        "executed_contract_count": len(
            contracts
        ),
        "status_counts": counts,
        "symbols": symbol_results,
    }

    atomic_write_json(
        summary_path,
        summary,
    )

    print()
    print("=== UNIVERSE BATCH SUMMARY ===")
    print(
        json.dumps(
            {
                "universe_id": UNIVERSE_ID,
                "summary_path": str(
                    summary_path
                ),
                "state_path": str(
                    state_path
                ),
                "status_counts": counts,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
