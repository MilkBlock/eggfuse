#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
export KV_READOUT=full VALUE_READ_SCALE=rich
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
# Use the checkpoint/corpus layout from joint_cell_reproduce.sh and continuous_reproduce.sh.
for c in fact loopfact sum-divisors; do
    export TR_CASE="$c"
    sh partner_index_reproduce.sh incremental_fit.py train
    sh partner_index_reproduce.sh incremental_eval.py evaluate
    sh partner_index_reproduce.sh incremental_audit.py evaluate
    IK_MODELS="A-71-e3 B-71-e3 C-71-e3 A-113-e3 B-113-e3 C-113-e3" IK_METHODS=ref IK_CAP=256 sh partner_index_reproduce.sh incremental_native.py live
    sh partner_index_reproduce.sh incremental_windows.py live
    sh partner_index_reproduce.sh incremental_native.py live
    IK_CAP=128 IK_METHODS=ref IK_DRAW='193 307 411 509' sh partner_index_reproduce.sh incremental_native.py live
    sh partner_index_reproduce.sh incremental_batch.py live
    IK_BATCH_KV=1 sh partner_index_reproduce.sh incremental_batch.py live
done
TR_CASE=fact IK_BATCH_KV=1 IK_TIMED_KERNELS=1 sh partner_index_reproduce.sh incremental_batch.py live
for i in 0 1; do
    methods='ref cache'
    if [ "$i" = 1 ]; then methods='cache ref'; fi
    for c in fact loopfact sum-divisors; do
        TR_CASE="$c" IK_DRAW=193 IK_CAP=full IK_METHODS="$methods" IK_REP="-pair$i" sh partner_index_reproduce.sh incremental_native.py live
    done
done
"${PYTHON:-python3}" incremental_results.py "$PARTNER_INDEX_OUT/incremental-foundation" "${RESULTS_DIR:-run-recall/incremental-foundation}"
