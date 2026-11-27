#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
run() { sh partner_index_reproduce.sh "$@"; }
run constructible_replay.py evaluate
CB_ARMS='A B C' CB_CAPS='0 96 32' run constructible_study.py evaluate
CB_ARMS='A B C' CB_CAPS=96 CB_DRAW=827 run constructible_study.py evaluate
for slots in 96 384; do
  CB_ARMS='A B C' CB_CAPS=0 CB_SLOT_LIMIT="$slots" run constructible_study.py evaluate
done
run constructible_train.py train
CB_ARMS='TB TC' CB_CAPS='0 96' run constructible_study.py evaluate
run constructible_branches.py evaluate
run abstraction_catalogue.py evaluate
run abstraction_timing.py evaluate
"${PYTHON:-python3}" constructible_results.py "$PARTNER_INDEX_OUT/constructible" run-recall/constructible
