#!/bin/sh
# Run from recurrent-generator/instruction_pointer on an Apple Metal host.
set -eu
: "${OUT:?Fresh output directory}" "${DATA:?Native workload root}" "${CORPUS:?Run-continuation artifacts}" "${PREVIOUS:?Data-scaling artifacts}" "${ACCEPTANCE:?sum-bits saved exports}"
PY=${PY:-python3}
export PYTORCH_ENABLE_MPS_FALLBACK=0
run() {
    script=$1
    shift
    "$PY" "$script" --out "$OUT" --data "$DATA" --corpus "$CORPUS" --previous "$PREVIOUS" "$@"
}
run parallel_budget.py
run parallel_fit.py --updates 640
run parallel_trial.py frozen
run parallel_reference.py
run parallel_trial.py native --cases fact loopfact sum-divisors grammar-benefit-left-17119 --blocks 2
run parallel_probe.py
run parallel_trial.py native --cases sum-divisors fact grammar-benefit-left-17119 --arms editor flow --pages 8 --caps 16 --steps 2 --blocks 2
repo=$(git rev-parse --show-toplevel)
python3 "$repo/benchmarks/marker-handoff/choice_diagnosis.py" "$ACCEPTANCE" "$OUT/semantic.json"
"$PY" parallel_results.py "$OUT" "$DATA" "$OUT/published"
uv run --script parallel_plot.py "$OUT/published"
"$PY" -m unittest discover
