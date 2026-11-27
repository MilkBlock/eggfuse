#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/shared-sparse}"
export MULTIRULE_OUT="${MULTIRULE_OUT:-$ARTIFACT_ROOT/multi-association}"
run() { sh partner_index_reproduce.sh "$@"; }
run shared_posting_diagnosis.py evaluate
run shared_posting_binding.py evaluate
run shared_posting_cost.py cost
run shared_posting_cost.py evaluate
run shared_posting_study.py evaluate
ARMS=A,B,Bcompact,C DRAWS=9734,9805 run shared_posting_study.py live
ARMS=C-anchor DRAWS=9734,9805 run shared_posting_study.py live
ARMS=A,B,C,C-anchor DRAWS=9876 run shared_posting_study.py live
for page in 4 16; do
  PAGE_SLOTS=$page ARMS=A,B,C,C-anchor DRAWS=9734 run shared_posting_study.py live
done
"${PYTHON:-python3}" shared_posting_export.py "$PARTNER_INDEX_OUT" "${RESULTS_DIR:-run-recall/shared-sparse}"
