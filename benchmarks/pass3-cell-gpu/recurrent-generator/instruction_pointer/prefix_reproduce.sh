#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}" KV_READOUT=full VALUE_READ_SCALE=rich
for TR_CASE in fact loopfact sum-divisors; do
    export TR_CASE
    sh partner_index_reproduce.sh prefix_corpus.py evaluate
done
for TR_CASE in fact loopfact sum-divisors; do
    export TR_CASE
    sh partner_index_reproduce.sh prefix_train.py train
    sh partner_index_reproduce.sh prefix_fields.py evaluate
    sh partner_index_reproduce.sh prefix_diagnostic.py evaluate
    sh partner_index_reproduce.sh prefix_live.py evaluate
    PREFIX_PAID=1 sh partner_index_reproduce.sh prefix_live.py evaluate
done
for TR_CASE in fact loopfact sum-divisors; do
    export TR_CASE
    PREFIX_SERIAL=1 sh partner_index_reproduce.sh prefix_live.py evaluate
done
"${PYTHON:-python3}" prefix_attention_results.py "$PARTNER_INDEX_OUT/prefix-attention" "${RESULTS_DIR:-run-recall/prefix-attention}"
