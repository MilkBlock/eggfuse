#!/bin/sh
# Run from recurrent-generator/instruction_pointer in a fresh OUT directory.
set -eu
: "${BASE:?existing experiment archive}" "${OUT:?fresh output directory}" "${DATA:?native workload directory}" "${RUNTIME:?cell_token_replay}"
PY=${PY:-python3}
BANK="$BASE/transition-credit-1127/dynamic"
OLD="$BASE/control-credit-pairs"
INITIAL="$BASE/transition-credit-1127/fine/weights/9633/initial.pt"
mkdir -p "$OUT" "$OUT/refreshed"
run() {
    script=$1; dest=$2; shift 2
    "$PY" "$script" --data "$DATA" --previous "$BANK" --corpus "$BASE/run-continuation-1126" --audit "$BASE/address-audit-1126" --contract "$BASE/query-contract-1126" --runtime-binary "$RUNTIME" --out "$dest" "$@"
}
run credit_scale_buffer.py "$OUT" --checkpoint "$INITIAL" --first 0 --stop 96 --lanes 4 --cap 160 --branches 1 2 --rollout-seed 73213
"$PY" fine_credit.py "$OUT" "$BANK" "$RUNTIME" --jobs 6 --limit 4
run dual_credit_pages.py "$OUT" --jobs 3
run control_credit_live.py "$OUT" --checkpoint "$INITIAL" --source "$OLD" --skip 2 --pairs-per-program 2 --programs 96
run dual_credit.py "$OUT" --checkpoint "$INITIAL" --paired "$OLD" --additional-live "$OUT" --programs 96
"$PY" transition_credit.py "$OUT" --bank "$BANK" --output "$OUT/inventory.json"
"$PY" transition_credit.py "$OUT" --also "$BASE/transition-credit-1127" "$BASE/transition-credit-1127/diverse" "$BASE/transition-credit-1127/fine" --bank "$BANK" --output "$OUT/pooled.json"
run fine_fit.py "$OUT" --initial "$INITIAL" --programs 64 --steps 512 --arms D witness --tag dual
run credit_scale_eval.py "$OUT" native --initial "$INITIAL" --archive "$BASE/discovery-control" --arms initial dual-D dual-witness
"$PY" dual_credit_egg.py --out "$OUT" --data "$DATA" --runtime-binary "$RUNTIME"
fresh="$OUT/refreshed"
weights="$OUT/weights/9633/dual-witness.pt"
run control_credit_live.py "$fresh" --checkpoint "$weights" --source "$OLD" --first 64 --programs 96
run dual_credit.py "$fresh" --checkpoint "$weights" --paired "$OLD" --live-only --additional-live "$fresh" --first 64 --programs 96
"$PY" dual_credit_report.py --out "$OUT" --paired "$OLD" --dest "$OUT/report"
CONTROL_CREDIT_OUTPUT="$OLD" "$PY" -m unittest test_dual_credit test_control_credit_pairs
