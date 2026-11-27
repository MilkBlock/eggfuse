#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}"
export MULTIRULE_OUT="${MULTIRULE_OUT:-$ARTIFACT_ROOT/multi-association}"
export PARTNER_INDEX_OUT="${FOUNDATION_OUT:-$ARTIFACT_ROOT/foundation-memory}"
mkdir -p "$PARTNER_INDEX_OUT"
run() { sh partner_index_reproduce.sh "$@"; }
run foundation_study.py prepare
run foundation_study.py train
run foundation_study.py live
FOUNDATION_ARMS=prior-index,prior-rule,ce-rule-no-field BLOCKS=2 run foundation_study.py live
for seed in 9805 9997; do
  FOUNDATION_ARMS=ce-rule,ce-evidence DRAW="$seed" BLOCKS=1 run foundation_study.py live
done
FOUNDATION_CAP=1 BLOCKS=1 FOUNDATION_ARMS=ce-rule,ce-evidence run foundation_study.py live
FOUNDATION_AUDIT=1 BLOCKS=1 FOUNDATION_ARMS=ce-evidence run foundation_study.py live
FOUNDATION_ARMS=ce-evidence-force-rule,ce-rule,ce-evidence BLOCKS=2 run foundation_study.py live
FOUNDATION_SLOTS=1904 BLOCKS=1 FOUNDATION_ARMS=ce-rule,ce-evidence run foundation_study.py live
for task in evaluate live cost cpu; do run foundation_diagnostics.py "$task"; done
run foundation_results.py evaluate
