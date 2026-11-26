#!/bin/sh
# Run from the instruction_pointer directory on the Metal host.
set -eu
: "${DATA:?native dataset}" "${PREVIOUS:?data-scaling weights}" "${CORPUS:?continuation trial}" "${AUDIT:?address audit}" "${CONTRACT:?9317cbc7 query-contract trial}" "${OUT:?new output directory}" "${ACCEPTANCE:?saved sum-bits exports}"
repo=$(git rev-parse --show-toplevel)
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$repo/target"}
export PYTORCH_ENABLE_MPS_FALLBACK=0
PY=${PY:-python3}
(cd "$repo" && cargo build --locked --release -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay)
run() {
    script=$1
    shift
    "$PY" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --runtime-binary "$CARGO_TARGET_DIR/release/examples/cell_token_replay" --out "$OUT" "$@"
}
run discovery_states.py
run discovery_dirty.py
run discovery_sampling.py
run discovery_score.py
run discovery_native.py
for seed in 1129 3449 5011 7733; do
    run discovery_native.py --generation-seed "$seed" --blocks 1
done
run discovery_native.py --paired-clock
python3 "$repo/benchmarks/marker-handoff/choice_diagnosis.py" "$ACCEPTANCE" "$OUT/semantic.json"
run discovery_summary.py --dest "$OUT/published"
"$PY" -m unittest discover
# Optional figure, using a Python environment with Matplotlib installed.
# python3 discovery_plot.py "$OUT/published"
