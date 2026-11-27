#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}" KV_READOUT=full VALUE_READ_SCALE=rich
run() { sh partner_index_reproduce.sh "$@"; }
run joint_cell_replay.py evaluate
for TR_CASE in fact loopfact sum-divisors; do
    export TR_CASE
    run joint_cell_corpus.py evaluate
done
for TR_CASE in fact loopfact sum-divisors; do
    export TR_CASE
    JC_TRAIN_ARMS='expanded feedback small replay' run joint_cell_train.py train
    run joint_cell_sweep.py train
    run joint_cell_probabilities.py evaluate
    JC_DIAGNOSTIC=1 run prefix_diagnostic.py evaluate
    run joint_cell_alias.py evaluate
    JC_ARMS='random random_unique original original_unique sparse small expanded feedback replay sweep' run joint_cell_live.py live
    JC_ARMS='iid blind' JC_BUDGETS=full run joint_cell_live.py live
done
run joint_cell_competition.py evaluate
run joint_cell_future_probe.py evaluate
run joint_cell_response_probe.py evaluate
run joint_cell_generalization.py evaluate
run joint_cell_transfer.py evaluate
for JC_REP in 1 2; do
    export JC_REP
    for TR_CASE in fact loopfact sum-divisors; do
        export TR_CASE
        if test "$JC_REP" = 1; then order='expanded sweep'; else order='sweep expanded'; fi
        JC_ARMS="$order" JC_BUDGETS=full JC_DRAWS=193 run joint_cell_live.py live
    done
done
"${PYTHON:-python3}" joint_cell_results.py "$PARTNER_INDEX_OUT/joint-cell-pretraining" "${RESULTS_DIR:-run-recall/joint-cell-pretraining}"
