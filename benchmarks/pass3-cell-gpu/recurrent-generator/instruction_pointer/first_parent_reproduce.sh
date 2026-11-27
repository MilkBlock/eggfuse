#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
out=${FIRST_PARENT_OUT:-"$ARTIFACT_ROOT/first-parent"}
py=${PYTHON:-python3}
run() {
    script=$1
    shift
    "$py" "$script" "$@" --out "$out" --data "$CELL_DATA" --previous "$ARTIFACT_ROOT/transition-credit-1127/dynamic" \
      --audit "$ARTIFACT_ROOT/address-audit-1126" --contract "$ARTIFACT_ROOT/query-contract-1126" \
      --corpus "$ARTIFACT_ROOT/run-continuation-1126" --initial "$ARTIFACT_ROOT/discovery-dual-credit/weights/9633/initial.pt" \
      --previous-binding "$ARTIFACT_ROOT/variable-binding" --compiler "$CELL_COMPILER" --runtime-binary "$CELL_REPLAY"
}
for task in prepare train eval live guard; do run first_parent.py "$task"; done
run first_parent_probes.py eval
run first_parent_cost.py eval
run first_parent_cpu.py live
run first_parent.py guard --reuse-guard-weights
"${PLOT_PYTHON:-$py}" first_parent_results.py "$out" "${RESULTS_DIR:-run-recall/first-parent}"
