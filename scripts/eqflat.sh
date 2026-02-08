#!/usr/bin/env bash
# eqflat.sh - operator-friendly wrapper

DATA_TAG="${1:?usage: ./scripts/eqflat.sh <DATA_TAG>}"

SYMBOL="${SYMBOL:-BTC_USD}"
TIMEFRAME="${TIMEFRAME:-5m}"
RUNID="eqflat_$(date -u +%Y%m%d_%H%M%S)"
BT_TAG="${DATA_TAG}_bt_${RUNID}"

LIVE_DEC="data/processed/decisions/${DATA_TAG}/${SYMBOL}/${TIMEFRAME}/decisions.csv"
BT_DEC="data/processed/decisions/${BT_TAG}/${SYMBOL}/${TIMEFRAME}/decisions.csv"
LIVE_TR="data/processed/trades/${DATA_TAG}/${SYMBOL}/${TIMEFRAME}/trades.csv"
BT_TR="data/processed/trades/${BT_TAG}/${SYMBOL}/${TIMEFRAME}/trades.csv"

if [[ ! -s "$LIVE_DEC" ]]; then
  echo "ERROR: missing or empty LIVE decisions: $LIVE_DEC" >&2
  exit 2
fi

START_TS_MS="$(
  awk -F, '
    NR==1{
      for(i=1;i<=NF;i++) if($i=="ts_ms"){c=i; break}
      if(!c){print ""; exit}
      next
    }
    NR==2{
      print $c
      exit
    }
  ' "$LIVE_DEC"
)"

if [[ -z "$START_TS_MS" ]]; then
  echo "ERROR: failed to extract START_TS_MS from $LIVE_DEC" >&2
  exit 2
fi

echo "== eqflat =="
echo "DATA_TAG=$DATA_TAG"
echo "RUNID=$RUNID"
echo "BT_TAG=$BT_TAG"
echo "SYMBOL=$SYMBOL"
echo "TIMEFRAME=$TIMEFRAME"
echo "START_TS_MS=$START_TS_MS"
echo
echo "[paths]"
echo "LIVE_DEC=$LIVE_DEC"
echo "BT_DEC  =$BT_DEC"
echo "LIVE_TR =$LIVE_TR"
echo "BT_TR   =$BT_TR"
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

echo
echo "== next =="
echo "If FAIL: RUNID=$RUNID DATA_TAG=$DATA_TAG make eqflat_triage"
