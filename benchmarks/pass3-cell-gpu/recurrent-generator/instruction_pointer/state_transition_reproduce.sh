#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
TRANS_IDS='0 1 2 3 4 5 6 7 8 9 10 11' TRANS_SPLIT=train sh partner_index_reproduce.sh state_transition_corpus.py evaluate
TRANS_IDS='0 1 2 3 4 5' TRANS_SPLIT=test sh partner_index_reproduce.sh state_transition_corpus.py evaluate
for TRANS_ARM in teacher transition; do
  export TRANS_ARM
  sh partner_index_reproduce.sh state_transition_train.py train
done
sh partner_index_reproduce.sh state_transition_probes.py evaluate
sh partner_index_reproduce.sh state_transition_measure.py evaluate
sh partner_index_reproduce.sh state_transition_rollout.py evaluate
export TRANS_CASES='mixed fact loopfact sum-divisors'
TRANS_IDLE=1 sh partner_index_reproduce.sh state_transition_live.py evaluate
for TRANS_GLOBAL in 0 1; do
  export TRANS_GLOBAL
  sh partner_index_reproduce.sh state_transition_live.py evaluate
done
"${PYTHON:-python3}" state_transition_report.py "$PARTNER_INDEX_OUT/state-transition" "${RESULTS_DIR:-run-recall/state-transition}"
