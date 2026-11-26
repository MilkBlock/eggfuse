#!/bin/sh
# Run in the instruction_pointer directory of the research checkout on Metal.
set -eu
: "${OUT:?fresh output directory}" "${DATA:?native data root}" "${CORPUS:?run-continuation artifacts}" "${PREVIOUS:?data-scaling artifacts}" "${PREVIOUS_TRIAL:?parallel-cell experiment}" "${ACCEPTANCE:?saved sum-bits exports}"
PY=${PY:-python3}
export PYTORCH_ENABLE_MPS_FALLBACK=0
run() {
    script=$1
    shift
    "$PY" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --out "$OUT" "$@"
}
run parallel_budget.py
run address_corpus.py
run address_scores.py --arms tree-fit tree-bilinear direct-fit direct-mlp semantic-mlp
run address_diagnosis.py --arms original tree-dot direct-dot direct-old tree-fit tree-bilinear direct-fit direct-mlp semantic-fit semantic-mlp 'original~without_prefix' 'original~without_reply' 'direct-mlp~without_prefix' 'direct-mlp~without_reply'
run address_runtime.py frozen --arms original tree-fit direct-fit direct-mlp semantic-mlp
run address_runtime.py native --arms original tree-fit direct-fit direct-mlp semantic-mlp --blocks 2
run address_runtime.py native --cap 16 --arms original tree-fit direct-mlp semantic-mlp --blocks 2
run address_microbench.py
run address_alias.py
run address_twins.py
run address_reproduce.py
run address_example.py
repo=$(git rev-parse --show-toplevel)
python3 "$repo/benchmarks/marker-handoff/choice_diagnosis.py" "$ACCEPTANCE" "$OUT/semantic.json"
run address_report.py --dest "$OUT/published" --previous-trial "$PREVIOUS_TRIAL"
"$PY" -m unittest discover
