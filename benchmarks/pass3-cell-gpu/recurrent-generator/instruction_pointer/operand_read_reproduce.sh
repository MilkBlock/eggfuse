#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?set the existing experiment root}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
# Reuse the value_read_reproduce.sh native corpus, blind worlds and the rich C checkpoints.
sh partner_index_reproduce.sh operand_read_train.py train
sh partner_index_reproduce.sh operand_read_eval.py evaluate
sh partner_index_reproduce.sh operand_read_probe.py evaluate
"${PYTHON:-python3}" operand_read_results.py "$PARTNER_INDEX_OUT/operand-read" "${RESULTS_DIR:-run-recall/operand-read}"
