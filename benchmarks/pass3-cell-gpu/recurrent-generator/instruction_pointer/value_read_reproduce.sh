#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?set the existing artifact root}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full
sh partner_index_reproduce.sh value_read_world.py prepare
sh partner_index_reproduce.sh value_read_filler.py prepare
for VALUE_READ_SCALE in pilot small rich; do
  export VALUE_READ_SCALE
  sh partner_index_reproduce.sh value_read_train.py train
  sh partner_index_reproduce.sh value_read_eval.py live
done
sh partner_index_reproduce.sh value_read_eval.py evaluate
sh partner_index_reproduce.sh value_read_wiring.py evaluate
sh partner_index_reproduce.sh value_read_audit.py evaluate
"${PYTHON:-python3}" value_read_results.py "$PARTNER_INDEX_OUT" "${RESULTS_DIR:-run-recall/conditional-value}"
