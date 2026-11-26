#!/bin/sh
# Run from benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer.
set -eu
: "${DATA:?native program bank}" "${PREVIOUS:?data-scaling}" "${CORPUS:?continuation}" "${AUDIT:?address audit}" "${CONTRACT:?query contract}" "${RUNTIME:?cell_token_replay}" "${OUT:?new raw experiment directory}"
py=${PY:-python3}
archive=$(dirname "$OUT")/discovery-control
# Historical receipts live in sibling coverage-loss/failures and coverage-loss/confirmed.
run() {
    script=$1
    shift
    "$py" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --runtime-binary "$RUNTIME" --out "$OUT" "$@"
}
mkdir -p "$OUT"
run experience_audit.py
run experience_capture.py
run experience_labels.py
"$py" experience_manifest.py "$OUT"
run experience_fit.py --updates 256
run experience_eval.py frozen --archive "$archive" --draws 2
run experience_eval.py native --archive "$archive"
run experience_clock.py
"$py" experience_report.py "$OUT" "$OUT/published"
cp "$OUT/accounting/replay.csv" "$OUT/published/accounting.csv"
cp "$OUT/accounting/stalls.csv" "$OUT/clock.csv" "$OUT/published/"
"$py" -m unittest discover
