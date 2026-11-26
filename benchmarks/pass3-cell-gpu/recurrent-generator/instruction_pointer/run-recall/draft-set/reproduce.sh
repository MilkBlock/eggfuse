#!/bin/sh
# Run from instruction_pointer. OUT must be an empty output directory.
set -eu
: "${OUT:?Destination for this experiment}"
: "${DATA:?Existing native workload and CCP artifacts}"
: "${PREVIOUS:?Frozen data-scaling checkpoints}"
: "${CORPUS:?Previous run-continuation experiment with verified stream tapes}"
PY=${PY:-python3}
export PYTORCH_ENABLE_MPS_FALLBACK=0
mkdir -p "$OUT"
run() {
    "$PY" draft_experiment.py --data "$DATA" --previous "$PREVIOUS" --out "$OUT" "$@"
}
"$PY" draft_multitarget.py --data "$DATA" --previous "$PREVIOUS" --out "$OUT" --corpus "$CORPUS"
for device in cpu mps; do
    run --device "$device" --label paired --cases sum-divisors fact loopfact grammar-benefit-left-17119 --arms fifo set relative page page-single page-multi --blocks 2
done
run --device cpu --label cut5 --arms set --switch-run 5 --blocks 1 --cases sum-divisors
run --device mps --label fixture --arms set page --declared-layout --blocks 1 --cases response-held-join response-held-permit response-held-merge6
run --device cpu --arms first later rule stream --cases grammar-benefit-left-17119 fact loopfact sum-divisors --blocks 2
"$PY" draft_results.py "$OUT" "$DATA" "$OUT/published"
"$PY" draft_mask_audit.py "$DATA" "$OUT"
uv run --script draft_plot.py "$OUT/published"
"$PY" -m unittest discover
