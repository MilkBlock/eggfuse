#!/usr/bin/env bash
# Same project options and pinned native binaries as partner_index_reproduce.sh.
set -euo pipefail
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export PARTNER_INDEX_OUT=${PARTNER_INDEX_OUT:-"$ARTIFACT_ROOT/conditional-value"}
export KV_READOUT=full VALUE_READ_SCALE=rich
unset CELL_STOP_AT
PY=${PYTHON:-python3}
OUT="$PARTNER_INDEX_OUT/continuation-exposure"
REPORT=${EXPOSURE_REPORT:-run-recall/continuation-exposure}
run() { sh partner_index_reproduce.sh "$@"; }
train() { EXPOSURE_DATA="$1" EXPOSURE_ARM="$2" CELL_SEED="$3" CELL_MILESTONES="$4" run exposure_train.py train; }
case "${1:-all}" in
  split) run exposure_worlds.py prepare ;;
  collect)
    EXPOSURE_CASES=sum-divisors EXPOSURE_SEEDS="419 733" run exposure_data.py evaluate
    EXPOSURE_CASES="fact sum-divisors" EXPOSURE_SEEDS="947 1151 1459 1663 1871 2081" run exposure_data.py evaluate
    EXPOSURE_MATERIALIZE=1 run exposure_data.py evaluate ;;
  train)
    train A local 71 "250000 500000 1000000"
    train A center 71 250000
    train A layer03 71 250000
    train B local 71 250000
    train C local 71 250000
    train D local 71 "250000 500000"
    train A local 113 250000
    train D local 113 250000 ;;
  evaluate)
    "$PY" exposure_campaign.py --suite development
    "$PY" exposure_campaign.py --suite held ;;
  report)
    "$PY" exposure_checkpoint.py "$OUT" "$REPORT/checkpoints" --once
    "$PY" exposure_results.py "$OUT" "$REPORT" ;;
  all) for phase in split collect train evaluate report; do bash "$0" "$phase"; done ;;
  *) exit 2 ;;
esac
