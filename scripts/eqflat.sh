#!/usr/bin/env bash

DATA_TAG="${1:?usage: ./scripts/eqflat.sh <DATA_TAG>}"

SYMBOL="${SYMBOL:-BTC_USD}"
TIMEFRAME="${TIMEFRAME:-5m}"
RUNID="eqflat_$(date -u +%Y%m%d_%H%M%S)"

LIVE="data/processed/decisions/${DATA_TAG}/${SYMBOL}/${TIMEFRAME}/decisions.csv"
if [[ ! -s "$LIVE" ]]; then
  echo "ERROR: missing or empty LIVE decisions: $LIVE" >&2
  exit 2
fi

START_TS_MS="$(awk -F, 'NR==2{print $4; exit}' "$LIVE")"
if [[ -z "$START_TS_MS" ]]; then
  echo "ERROR: failed to extract START_TS_MS from $LIVE" >&2
  exit 2
fi

echo "== eqflat =="
echo "DATA_TAG=$DATA_TAG"
echo "RUNID=$RUNID"
echo "SYMBOL=$SYMBOL"
echo "TIMEFRAME=$TIMEFRAME"
echo "START_TS_MS=$START_TS_MS"
echo

START_TS_MS="$START_TS_MS" RUNID="$RUNID" DATA_TAG="$DATA_TAG" make backtest
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "ERROR: make backtest failed (rc=$rc)" >&2
  exit $rc
fi

RUNID="$RUNID" DATA_TAG="$DATA_TAG" make eq
rc=$?
if [[ $rc -ne 0 ]]; then
  echo "ERROR: make eq failed (rc=$rc)" >&2
  exit $rc
fi
