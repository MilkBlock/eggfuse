#!/bin/sh
# From benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer at this revision.
set -eu
: "${DATA:?Native captures, compiler artifacts and recursive-agent weights}"
: "${FORKS:?Native paired forks from the latent-flow experiment}"
: "${ROLLOUT:?Directory containing sum-issued.json and sum-native-memory.jsonl}"
: "${COMPILER:?Path to release eggfuse-cell-compiler}"
PY=${PY:-python3}
OUT=${OUT:-run-recall/response-edit}
ACTOR=${ACTOR:-run-recall/higher-scaling/weights/actor.pt}
mkdir -p "$OUT"
do_study() {
    "$PY" response_study.py "$@" --data "$DATA" --actor "$ACTOR" --out "$OUT" --compiler "$COMPILER"
}
do_study train --forks "$FORKS" --rollout "$ROLLOUT"
do_study train --forks "$FORKS" --rollout "$ROLLOUT" --macro
"$PY" response_owner.py "$DATA" "$ACTOR" "$OUT"
for case_name in fact loopfact grammar-benefit-left-17119 sum-divisors; do
    "$PY" response_reference.py run --data "$DATA" --actor "$ACTOR" --out "$OUT" --case "$case_name" --seconds 720
done
for case_name in fact loopfact sum-divisors grammar-benefit-left-17119 response-held-merge6; do
    do_study run --case "$case_name" --arms P4,O4,C1,D1,D2,D4,D8,E1,E2,E4,E8
done
for case_name in fact loopfact sum-divisors grammar-benefit-left-17119; do
    do_study run --case "$case_name" --arms C1,D4,E4 --pages 8
done
do_study run --case response-held-merge6 --primitive-only --arms C1,D1,D4,E1,E4
do_study run --case response-held-permit --arms C1,D1,D4,E1,E4 --pages 8
for case_name in fact loopfact sum-divisors response-held-merge6; do
    do_study run --case "$case_name" --fresh-requests --arms C1,D4,E4
done
do_study run --case response-held-permit --fresh-requests --arms C1,D1,D4,E1,E4 --pages 8
"$PY" response_feedback.py run --data "$DATA" --actor "$ACTOR" --out "$OUT" --forks "$FORKS"
"$PY" response_counterfactual.py run --data "$DATA" --actor "$ACTOR" --out "$OUT"
"$PY" response_manifest.py run --data "$DATA" --actor "$ACTOR" --out "$OUT" --compiler "$COMPILER" --forks "$FORKS" --rollout "$ROLLOUT"
"$PY" response_results.py "$OUT"
"$PY" -m unittest discover -p 'test_*.py'
