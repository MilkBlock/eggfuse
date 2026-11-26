#!/bin/sh
# Run in recurrent-generator/instruction_pointer with an empty OUT.
set -eu
: "${DATA:?compiled workload root}" "${PREVIOUS:?transition-credit-1127/dynamic}" "${CORPUS:?run-continuation-1126}" "${AUDIT:?address-audit-1126}" "${CONTRACT:?query-contract-1126}" "${CHECKPOINT:?frozen initial.pt}" "${RUNTIME:?cell_token_replay}" "${OUT:?experiment output}"
py=${PY:-python3}
run() {
    script=$1
    shift
    "$py" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --checkpoint "$CHECKPOINT" --runtime-binary "$RUNTIME" --out "$OUT" "$@"
}
run execution_control_data.py collect
run execution_control_data.py collect --out "$OUT/shuffle" --shuffle-prefix
run execution_control_data.py train
run execution_control_data.py train --no-exit-credit
run execution_control_data.py train --extra-experience "$OUT/shuffle"
for seed in 536 1129; do
    blocks=1
    if [ "$seed" = 536 ]; then blocks=2; fi
    run execution_control_eval.py --blocks "$blocks" --generation-seed "$seed"
    run execution_control_eval.py --blocks "$blocks" --generation-seed "$seed" --arms C-no-exit-credit C-no-bank
    run execution_control_eval.py --blocks "$blocks" --generation-seed "$seed" --arms C-shuffle
done
run execution_control_audit.py
EXECUTION_CONTROL_OUTPUT="$OUT" "$py" -m unittest test_execution_control
