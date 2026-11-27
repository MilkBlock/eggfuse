#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
for STUDY_SEED in 71 113; do
  for STUDY_CURRICULUM in mixed curriculum diverse; do
    export STUDY_SEED STUDY_CURRICULUM
    sh partner_index_reproduce.sh selected_cell_study.py train
  done
done
sh partner_index_reproduce.sh selected_cell_audit.py evaluate
for STUDY_PHASE in frozen trained topology; do
  export STUDY_PHASE
  sh partner_index_reproduce.sh selected_cell_study.py evaluate
done
sh partner_index_reproduce.sh selected_cell_probe.py evaluate
"${PYTHON:-python3}" selected_cell_results.py "$PARTNER_INDEX_OUT/selected-cell" "${RESULTS_DIR:-run-recall/selected-cell}"
