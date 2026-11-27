#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?set the existing experiment root}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export VALUE_READ_SCALE=rich KV_READOUT=full
# Reuse the native rich corpus and the existing frozen operand-read D checkpoints.
sh partner_index_reproduce.sh interface_role_train.py train
sh partner_index_reproduce.sh interface_role_eval.py evaluate
sh partner_index_reproduce.sh interface_role_controls.py evaluate
for TRANSFER_MODE in replay mixed; do
  export TRANSFER_MODE
  sh partner_index_reproduce.sh interface_role_transfer.py train
done
sh partner_index_reproduce.sh interface_role_transfer.py evaluate
"${PYTHON:-python3}" interface_role_results.py "$PARTNER_INDEX_OUT/interface-role" "${RESULTS_DIR:-run-recall/interface-role}"
