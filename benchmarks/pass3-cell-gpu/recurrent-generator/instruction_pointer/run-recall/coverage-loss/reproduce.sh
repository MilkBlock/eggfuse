#!/bin/sh
# Run from recurrent-generator/instruction_pointer on the Metal host.
set -eu
: "${DATA:?training and held-out programs}" "${PREVIOUS:?data-scaling trial}" "${CORPUS:?continuation trial}" "${AUDIT:?address-audit trial}" "${CONTRACT:?query-contract trial}" "${ARCHIVE:?discovery-control trial}" "${OUT:?results directory}" "${RUNTIME:?native cell_token_replay}"
py=${PY:-python3}
mkdir -p "$OUT"
run() {
    script=$1
    output=$2
    shift 2
    "$py" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --runtime-binary "$RUNTIME" --out "$output" "$@"
}
run coverage_examples.py "$OUT" examples
run coverage_examples.py "$OUT" failures
run coverage_fit.py "$OUT"
run coverage_calibration.py "$OUT"
run coverage_onpolicy.py "$OUT/confirmed" --inputs "$OUT"
run coverage_onpolicy.py "$OUT/confirmed" --inputs "$OUT" --training-check
run coverage_eval.py "$OUT/confirmed" frozen --archive "$ARCHIVE"
run coverage_eval.py "$OUT/confirmed" native --archive "$ARCHIVE"
"$py" coverage_report.py "$OUT/confirmed" "$OUT/published"
"$py" -m unittest discover
# Optional figure, using an interpreter with matplotlib.
# python3 coverage_plot.py "$OUT/published"
