#!/usr/bin/env bash
# Use the existing recursive_train data layout. The native grammar and EggCC inputs
# are pinned in inputs.json. OUT and ROOT/recursive-agent must be writable.
set -eu
: "${ROOT:?native runtime and workloads}" "${COMPILER:?eggfuse-cell-compiler}" "${OUT:?experiment output directory}" "${ACCEPTANCE:?saved sum-bits exports}"
PY=${PYTHON:-python3}
REPORT=${REPORT:-run-recall/higher-scaling}
ACTOR=${ACTOR:-run-recall/higher-scaling/weights/actor.pt}
models=run-recall/discrete-computation-flow
natural=(fact loopfact sum-divisors grammar-benefit-left-17119)
sizes=(6 16 32 64 128 256 512)
circuits=()
forks=()
for n in "${sizes[@]}"; do
  circuits+=("scale-fork-$n-1-17" "scale-line-$n-1-17")
  forks+=("scale-fork-$n-1-17")
done
jobs=(scale-fork-32-{1,2,4}-17-jobs8)
mkdir -p "$OUT/cases" "$OUT/acceptance"
"$PY" scaling_bake.py "$ROOT" "$COMPILER" "$OUT/cases"
"$PY" scaling_bake.py "$ROOT" "$COMPILER" "$OUT/cases" --jobs 8
run() { "$PY" scaling_native.py "$ROOT" "$OUT" "$ACTOR" "$models" "$@"; }
run "${circuits[@]}" scale-fork-32-2-17 scale-fork-32-4-17 scale-fork-32-1-73 "${jobs[@]}"
run "${natural[@]}" --modes prim small flat root
run "${natural[@]}" --modes wide --label wide
run "${natural[@]}" --modes recursive wide-recursive --label hierarchy
run "${circuits[@]}" --modes prim flat --one-job --label single
run "${forks[@]}" scale-line-{6,32,128,512}-1-17 scale-fork-32-{2,4}-17 "${jobs[@]}" --modes flat root --methods empty --vary --repeats 8 --seed 1564 --label seeds
"$PY" scaling_native.py "$ROOT" "$OUT" "$ACTOR" "$models/primitive-fit" scale-fork-{6,64,256,512}-1-17 --modes flat root --methods empty --repeats 4 --vary --seed 1564 --label primitivefit
run "${forks[@]}" --modes prim flat --repeats 4 --label clean
run "${forks[@]}" --modes prim flat --one-job --repeats 4 --label singleclean
run "${natural[@]}" --modes prim small flat wide --repeats 4 --label clean
for pages in 1 4 8; do
  run "${natural[@]}" --modes prim small flat wide --pages "$pages" --label "budget$pages"
done
run scale-fork-{6,256,512}-1-17 "${natural[@]}" --modes prim small flat --profile --repeats 1 --label profile
run "${forks[@]}" --profile --modes flat --methods empty --repeats 1 --label scan
run fact loopfact sum-divisors --modes small flat wide --profile --repeats 1 --pages 8 --label verdict8
"$PY" scaling_witness.py "$ROOT" "$OUT" "$ACTOR"
"$PY" scaling_wiring.py "$ROOT" "$COMPILER" "$OUT" "$ACTOR" "$models"
"$PY" ../../../../benchmarks/marker-handoff/choice_diagnosis.py "$ACCEPTANCE" "$OUT/acceptance/semantic.json"
"$PY" -m unittest discover -p 'test_*.py'
"$PY" scaling_report.py "$OUT" "$REPORT" "$ROOT" "$ACTOR" --compiler "$COMPILER"
"${PLOT_PYTHON:-$PY}" scaling_plot.py "$REPORT"
