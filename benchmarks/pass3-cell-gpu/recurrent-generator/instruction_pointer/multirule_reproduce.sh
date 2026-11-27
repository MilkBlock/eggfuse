#!/bin/sh
set -eu
export PARTNER_INDEX_OUT="${MULTIRULE_OUT:-$ARTIFACT_ROOT/multi-association}"
mkdir -p "$PARTNER_INDEX_OUT"
run() { sh partner_index_reproduce.sh "$@"; }
MULTI_ARMS=audit run multirule_live.py live
run multirule_corpus.py prepare
run multirule_rollout_data.py prepare
run multirule_oracle.py evaluate
run multirule_ce.py train
MULTI_ARMS=frozen,ce-base,ce-count,ce-support,random,flat-frozen MULTI_BLOCKS=2 run multirule_live.py live
for shift in 71 263; do
  MULTI_DRAW_SHIFT="$shift" MULTI_ARMS=frozen,ce-base,ce-count,ce-support,random run multirule_live.py live
done
MULTI_MATCH_PAID=1 MULTI_ARMS=ce-base,ce-count,ce-support run multirule_live.py live
run multirule_stream.py live
run multirule_maintenance.py cost
run multirule_higher.py cost
run multirule_report.py evaluate
