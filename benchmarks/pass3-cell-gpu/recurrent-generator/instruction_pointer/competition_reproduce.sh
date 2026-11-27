#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
for COMP_SPLIT in train test; do
  export COMP_SPLIT
  sh partner_index_reproduce.sh competition_corpus.py evaluate
done
for COMP_SEED in 71 113; do
  for COMP_ARM in A B C; do
    export COMP_SEED COMP_ARM
    sh partner_index_reproduce.sh competition_corpus.py train
  done
done
for COMP_PHASE in frozen live; do
  export COMP_PHASE
  sh partner_index_reproduce.sh competition_evaluate.py evaluate
done
sh partner_index_reproduce.sh competition_egg.py evaluate
COMP_MODELS=B COMP_DRAWS="iid unique" COMP_TAG=-draw sh partner_index_reproduce.sh competition_egg.py evaluate
sh partner_index_reproduce.sh competition_reference.py evaluate
"${PYTHON:-python3}" competition_results.py "$PARTNER_INDEX_OUT/competition" "${RESULTS_DIR:-run-recall/competition}"
