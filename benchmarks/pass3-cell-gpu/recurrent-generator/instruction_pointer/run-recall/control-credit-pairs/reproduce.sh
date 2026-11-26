#!/bin/sh
# Start in recurrent-generator/instruction_pointer, with a new OUT on the data volume.
set -eu
: "${OUT:?}" "${DATA:?}" "${PREVIOUS:?dynamic Recipe bank}" "${CORPUS:?}" "${AUDIT:?}" "${CONTRACT:?}" "${RUNTIME:?}" "${COMPILER:?}" "${CHECKPOINT:?frozen Cell address weights}"
py=${PY:-python3}
run() {
    script=$1
    shift
    "$py" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --runtime-binary "$RUNTIME" --checkpoint "$CHECKPOINT" --out "$OUT" --programs 96 "$@"
}
run execution_control_data.py collect
run execution_control_data.py collect --shuffle-prefix --out "$OUT/shuffle"
for c in neural shuffle; do
    run control_credit_pairs.py --cohort "$c"
    run control_credit_ledger.py --cohort "$c"
done
run control_credit_allocation.py
run control_credit_live.py
run control_credit_fit.py
run control_credit_matched_fit.py
run control_credit_matched_fit.py --label matched-2 --seed 9203
run control_credit_matched_fit.py --label live --use-live
for seed in 536 1129; do
    blocks=1
    if [ "$seed" = 536 ]; then blocks=2; fi
    run execution_control_eval.py --blocks "$blocks" --generation-seed "$seed" --arms A factored C-raw C-paired-small C-paired
    run execution_control_eval.py --blocks "$blocks" --generation-seed "$seed" --arms C-matched C-matched-2
    run execution_control_eval.py --blocks "$blocks" --generation-seed "$seed" --arms C-live
done
"$py" fine_ports.py --compiler "$COMPILER" --runtime "$RUNTIME" --out "$OUT"
run control_credit_report.py
CONTROL_CREDIT_OUTPUT="$OUT" "$py" -m unittest test_control_credit_pairs
