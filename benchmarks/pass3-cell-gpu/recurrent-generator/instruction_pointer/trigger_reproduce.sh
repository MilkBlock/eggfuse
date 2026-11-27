#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
for TR_SEED in 71 113; do
    export TR_SEED
    sh partner_index_reproduce.sh trigger_training.py train
done
for TR_CASE in controlled fact loopfact sum-divisors; do
    export TR_CASE
    sh partner_index_reproduce.sh trigger_execution.py evaluate
    if [ "$TR_CASE" != controlled ]; then
        sh partner_index_reproduce.sh trigger_snapshots.py evaluate
        sh partner_index_reproduce.sh trigger_windows.py evaluate
    fi
done
"${PYTHON:-python3}" trigger_results.py "$PARTNER_INDEX_OUT/rule-publication" "${RESULTS_DIR:-run-recall/rule-publication}"
