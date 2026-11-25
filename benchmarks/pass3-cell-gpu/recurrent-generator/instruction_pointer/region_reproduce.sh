#!/usr/bin/env bash
set -eu
: "${ROOT:?runtime data}" "${OUT:?scratch}" "${COMPILER:?compiler}"
py=${PYTHON:-python3}
actor=${ACTOR:-run-recall/higher-scaling/weights/actor.pt}
weights=run-recall/discrete-computation-flow
mkdir -p "$OUT"
if [[ ! -s "$OUT/menu.json" ]]; then
  "$py" region_bake.py "$ROOT" "$OUT"
fi
natural=(fact loopfact sum-divisors grammar-benefit-left-17119)
run() { "$py" scaling_native.py "$ROOT" "$OUT" "$actor" "$weights" "$@" --trace-menu "$OUT/menu.json"; }
for pages in 1 2 4 8; do
  run "${natural[@]}" --modes A B C D E --methods empty --repeats 2 --pages "$pages" --label "pair$pages"
done
run "${natural[@]}" --modes A B C D E --methods empty --repeats 1 --pages 4 --label profile --profile --save-trace
for n in 64 128 256 512 1024 2048; do
  if [[ ! -f "$ROOT/recursive-agent/scale-fork-$n-1-17/reference-state.json" ]]; then
    "$py" -c 'from pathlib import Path; import sys; from scaling_bake import prepare; prepare(*map(Path,sys.argv[1:4]),"fork",int(sys.argv[4]),1,17)' "$ROOT" "$COMPILER" "$OUT" "$n"
  fi
  run "scale-fork-$n-1-17" --modes old-scale owned-scale --methods empty --one-job --label sizes --repeats 2 --seconds 600
  run "scale-fork-$n-1-17" --modes old-scale owned-scale --methods empty --one-job --label sizeprofile --profile --repeats 1 --seconds 600
done
"$py" region_fixture.py "$ROOT" "$OUT" "$COMPILER" "$actor"
"$py" region_transfer.py "$ROOT" "$OUT"
