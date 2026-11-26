#!/bin/sh
# Run from recurrent-generator/instruction_pointer. Reuse the immutable dual-credit dataset.
set -eu
: "${BASE:?experiment archive}" "${OUT:?new audit output directory}" "${DATA:?native data}" "${RUNTIME:?cell_token_replay}"
PY=${PY:-python3}
donor="$BASE/discovery-dual-credit"
initial="$donor/weights/9633/initial.pt"
archive="$BASE/discovery-control"
mkdir -p "$OUT"
for folder in buffer credit; do
    test -e "$OUT/$folder" || ln -s "$donor/$folder" "$OUT/$folder"
done
run() {
    script=$1; shift
    "$PY" "$script" --data "$DATA" --previous "$BASE/transition-credit-1127/dynamic" --corpus "$BASE/run-continuation-1126" --audit "$BASE/address-audit-1126" --contract "$BASE/query-contract-1126" --runtime-binary "$RUNTIME" --out "$OUT" "$@"
}
run throughput_fit.py --initial "$initial"
run throughput_slots.py --weights "$donor" --cases fact
run throughput_frozen.py --archive "$archive" --donor "$donor"
run throughput_transfer.py --archive "$archive"
run credit_scale_eval.py native --initial "$initial" --archive "$archive" --arms initial isolate-no-inactive conservative
run credit_scale_buffer.py --out "$OUT/observer-regression" --checkpoint "$initial" --first 0 --stop 1 --rollout-seed 73213 --cap 160 --lanes 1 --branches 2 --record-slot-attempts
"$PY" throughput_report.py --out "$OUT" --donor "$donor" --dest "$OUT/report"
CONTROL_CREDIT_OUTPUT="$BASE/control-credit-pairs" "$PY" -m unittest test_throughput test_dual_credit test_control_credit_pairs
