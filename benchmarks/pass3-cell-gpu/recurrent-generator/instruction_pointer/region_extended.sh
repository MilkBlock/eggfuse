#!/usr/bin/env bash
set -eu
py=${PYTHON:-python3}
actor=${ACTOR:-run-recall/higher-scaling/weights/actor.pt}
run() { "$py" scaling_native.py "$ROOT" "$OUT" "$actor" run-recall/discrete-computation-flow fact loopfact sum-divisors grammar-benefit-left-17119 --modes A B C D E --methods empty --trace-menu "$OUT/menu.json" "$@"; }
for pages in 16 32; do
  run --pages "$pages" --label "pair$pages" --repeats 2
done
for seed in 137 211; do
  run --pages 4 --seed "$seed" --label "seed$seed" --repeats 2
done
for pages in 4 8; do
  "$py" scaling_native.py "$ROOT" "$OUT" "$actor" run-recall/discrete-computation-flow fact loopfact sum-divisors grammar-benefit-left-17119 --modes common-topo common-trace --methods empty --trace-menu "$OUT/menu.json" --pages "$pages" --label "common$pages" --repeats 2
done
"$py" scaling_native.py "$ROOT" "$OUT" "$actor" run-recall/discrete-computation-flow fact loopfact sum-divisors grammar-benefit-left-17119 --modes E --methods empty --trace-menu "$OUT/menu.json" --pages 32 --label routes32 --repeats 1 --profile --save-issued
run --pages 32 --label confirm32 --repeats 4
run --pages 32 --label clean32 --repeats 4
"$py" region_roots.py "$ROOT" "$OUT"
