#!/bin/sh
# Run from instruction_pointer/ with the native captures used for response-edit.
set -eu
: "${DATA:?Native compiled programs, snapshots, recursive weights and Rust binary}"
: "${FORKS:?Native verified forks from latent-flow}"
: "${ROLLOUT:?Directory with sum-issued.json and sum-native-memory.jsonl}"
: "${OUT:?Scratch and checkpoint directory, allow 2 GiB}"
PY=${PY:-python3}
ACTOR=${ACTOR:-run-recall/higher-scaling/weights/actor.pt}
export PYTORCH_ENABLE_MPS_FALLBACK=0
study() {
    "$PY" metal_scaling.py "$@" --data "$DATA" --forks "$FORKS" --rollout "$ROLLOUT" --actor "$ACTOR"
}
study prepare --out "$OUT"
study fit --out "$OUT"
study run --out "$OUT"
study run --out "$OUT" --cases fact --datasets large --devices cpu mps --timing-prefix paired-
"$PY" metal_inference_cost.py "$OUT" "$OUT/dispatch.csv"
mkdir -p "$OUT/long"
for split in large held; do ln -sf "../$split.pt" "$OUT/long/$split.pt"; done
study fit --out "$OUT/long" --sizes base 10M 50M --datasets large --updates 768
study run --out "$OUT/long" --sizes base 10M 50M --datasets large --cases fact sum-divisors
study run --out "$OUT" --device-gnn --timing-prefix gnn- --sizes base 50M --datasets large
study run --out "$OUT" --device-gnn --timing-prefix gnn- --sizes 100K 1M 10M --datasets large
"$PY" metal_results.py "$OUT" "$OUT/summary"
