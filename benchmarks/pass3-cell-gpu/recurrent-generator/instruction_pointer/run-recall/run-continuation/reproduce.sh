#!/bin/sh
# Run in benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer.
set -eu
: "${OUT:?New scratch directory for weights, native traces, and checkpoints}"
: "${PREVIOUS:?Previous data-scaling corpus and checkpoints}"
: "${DATA:?Native programs, teacher tapes, actor artifacts and CCP replay executable}"
PY=${PY:-python3}
export PYTORCH_ENABLE_MPS_FALLBACK=0
study() {
    script=$1
    shift
    "$PY" "$script" --out "$OUT" --previous "$PREVIOUS" --data "$DATA" "$@"
}
study continuation_audit.py
study continuation_fragments.py
study continuation_capture.py
study continuation_data.py
study continuation_data.py --full
study continuation_fit.py --arms editor flow uncensored editor-response flow-response editor-full flow-full
study continuation_native.py
study continuation_native.py --arms uncensored --cases sum-divisors
study continuation_native.py --arms editor-response flow-response
study continuation_native.py --arms editor-full flow-full
study continuation_hints.py
study continuation_hints.py --arms editor-response flow-response --suffix=-response
study continuation_hints.py --arms editor-full flow-full --cases sum-divisors --suffix=-full
study continuation_native.py --arms prior editor flow editor-response flow-response editor-full flow-full --cases sum-divisors --paid-curves
study continuation_results.py --destination "$OUT/summary"
uv run --script continuation_plot.py "$OUT/summary"
"$PY" -m unittest discover
