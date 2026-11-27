#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
sh partner_index_reproduce.sh feedback_stall.py evaluate
sh partner_index_reproduce.sh feedback_intervention.py evaluate
sh partner_index_reproduce.sh feedback_data.py evaluate
for FB_ARM in blind visible; do
  export FB_ARM
  sh partner_index_reproduce.sh feedback_train.py train
done
sh partner_index_reproduce.sh feedback_measure.py evaluate
sh partner_index_reproduce.sh feedback_live.py evaluate
FB_FIXED_PAID=1 sh partner_index_reproduce.sh feedback_live.py evaluate
"${PYTHON:-python3}" feedback_report.py "$PARTNER_INDEX_OUT/response-memory" "${RESULTS_DIR:-run-recall/response-memory}"
