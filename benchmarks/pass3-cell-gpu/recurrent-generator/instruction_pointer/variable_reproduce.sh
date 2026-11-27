#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}" KV_READOUT=full VALUE_READ_SCALE=rich
for TR_SEED in 71 113; do
    export TR_SEED
    sh partner_index_reproduce.sh variable_completion.py train
done
for TR_CASE in fact loopfact sum-divisors; do
    export TR_CASE
    for SERIAL_TIMING in 0 1; do
        export SERIAL_TIMING
        sh partner_index_reproduce.sh variable_execution.py evaluate
    done
    sh partner_index_reproduce.sh variable_binding_audit.py evaluate
    sh partner_index_reproduce.sh variable_binding_execution.py evaluate
    sh partner_index_reproduce.sh variable_windows.py evaluate
done
TR_CASE=loopfact VC_MATCHED=1 sh partner_index_reproduce.sh variable_binding_execution.py evaluate
sh partner_index_reproduce.sh variable_device.py evaluate
"${PYTHON:-python3}" variable_results.py "$PARTNER_INDEX_OUT/variable-completion" "${RESULTS_DIR:-run-recall/variable-completion}"
