#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?set the experiment artifact root}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-compatibility-final}"
export KV_READOUT=full
sh partner_index_reproduce.sh compatibility_study.py prepare
sh partner_index_reproduce.sh compatibility_study.py train
sh partner_index_reproduce.sh compatibility_eval.py live
sh partner_index_reproduce.sh compatibility_generalization.py evaluate
sh partner_index_reproduce.sh compatibility_publication.py live
sh partner_index_reproduce.sh compatibility_score_probe.py evaluate
"${PYTHON:-python3}" compatibility_results.py "$PARTNER_INDEX_OUT" "${RESULTS_DIR:-run-recall/conditional-compatibility}"
