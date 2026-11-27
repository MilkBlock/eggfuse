#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?set the existing experiment artifact root}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/token-embedding}"
export KV_READOUT=full
for task in prepare train evaluate live; do
  sh partner_index_reproduce.sh token_embedding_study.py "$task"
done
for script in token_embedding_audit token_embedding_interventions token_embedding_guard_probe; do
  sh partner_index_reproduce.sh "$script.py" evaluate
done
"${PYTHON:-python3}" token_embedding_results.py "$PARTNER_INDEX_OUT" "${RESULTS_DIR:-run-recall/token-embedding}"
