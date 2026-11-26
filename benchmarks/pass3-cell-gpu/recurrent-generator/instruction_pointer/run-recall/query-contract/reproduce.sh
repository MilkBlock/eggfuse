#!/bin/sh
# Run in benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer.
set -eu
: "${OUT:?new output directory}" "${DATA:?native dataset root}" "${PREVIOUS:?data scaling trial}" "${CORPUS:?run continuation trial}" "${AUDIT:?previous address audit}" "${ACCEPTANCE:?sum-bits exports}"
PY=${PY:-python3}
repo=$(git rev-parse --show-toplevel)
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-"$repo/target"}
export PYTORCH_ENABLE_MPS_FALLBACK=0
(cd "$repo" && cargo build --release --locked -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay)
run() {
    script=$1
    shift
    "$PY" "$script" --out "$OUT" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --runtime-binary "$CARGO_TARGET_DIR/release/examples/cell_token_replay" "$@"
}
run query_witnesses.py
run query_witnesses.py --verify
run query_examples.py
run query_fit.py fit
run query_fit.py eval
run query_execution.py frozen
run query_execution.py native
for held in fact loopfact sum-divisors; do
    run query_fit.py fit --holdout "$held" --arms A C
    run query_fit.py eval --holdout "$held" --arms A C
done
python3 "$repo/benchmarks/marker-handoff/choice_diagnosis.py" "$ACCEPTANCE" "$OUT/semantic.json"
run query_report.py --dest "$OUT/published"
"$PY" -m unittest discover
