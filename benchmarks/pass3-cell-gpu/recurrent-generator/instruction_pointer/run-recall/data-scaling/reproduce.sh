#!/bin/sh
# Run from benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer.
set -eu
: "${OUT:?Fresh output directory on a volume with space for tapes, features and weights}"
: "${DATA:?Native workload bundle from response-edit}"
: "${PREVIOUS:?Directory containing large.pt and held.pt from metal-scaling prepare}"
: "${COMPILER:?Path to the native eggfuse-cell-compiler executable}"
PY=${PY:-python3}
WAIT=${TMPDIR:-/tmp}/eggfuse-page-waits.dylib
export PYTORCH_ENABLE_MPS_FALLBACK=0
mkdir -p "$OUT"
"$PY" data_scale_corpus.py --out "$OUT" --data "$DATA" --compiler "$COMPILER"
"$PY" data_scale_features.py --out "$OUT" --data "$DATA"
"$PY" data_scale_corpus.py --out "$OUT/held" --data "$DATA" --compiler "$COMPILER" --first 5001 --programs 8
"$PY" data_scale_features.py --out "$OUT/held" --data "$DATA" --first 5001
"$PY" data_scale_train.py --out "$OUT" --previous "$PREVIOUS"
"$PY" data_scale_train.py --out "$OUT" --previous "$PREVIOUS" --fixed 1568
"$PY" data_scale_generalization.py --out "$OUT"
"$PY" data_scale_tiny.py --out "$OUT" --data "$DATA"
"$PY" data_scale_tiny.py --out "$OUT" --data "$DATA" --steps 4096 --arms frozen joint
"$PY" data_scale_joint.py fit --out "$OUT" --data "$DATA" --previous "$PREVIOUS"
"$PY" data_scale_joint.py run --out "$OUT" --data "$DATA" --previous "$PREVIOUS"
"$PY" data_scale_rollout.py --out "$OUT" --data "$DATA"
"$PY" data_scale_rollout.py --out "$OUT/fixed1568" --data "$DATA"
clang -dynamiclib -fobjc-arc -framework Foundation -framework Metal metal_wait.m -o "$WAIT"
"$PY" data_scale_checks.py --out "$OUT" --data "$DATA"
"$PY" data_scale_rollout.py --out "$OUT" --data "$DATA" --devices scalar stream matched --levels 1000000 --wait-library "$WAIT"
"$PY" data_scale_rollout.py --out "$OUT" --data "$DATA" --devices stream --levels 1000000 --sizes 100K --seeds 243 --profile-index
"$PY" data_scale_results.py "$OUT" "$OUT/summary"
uv run --script data_scale_plot.py "$OUT/summary"
"$PY" -m unittest discover
