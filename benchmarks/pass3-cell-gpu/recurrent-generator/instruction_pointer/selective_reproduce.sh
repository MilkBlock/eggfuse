#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
out=${SELECTIVE_OUT:-"$ARTIFACT_ROOT/selective-partner"}
mkdir -p "$out"
run() {
  "${PYTHON:-python3}" "$@" --out "$out" --data "$CELL_DATA" \
    --previous "$ARTIFACT_ROOT/transition-credit-1127/dynamic" --audit "$ARTIFACT_ROOT/address-audit-1126" \
    --contract "$ARTIFACT_ROOT/query-contract-1126" --corpus "$ARTIFACT_ROOT/run-continuation-1126" \
    --initial "$ARTIFACT_ROOT/discovery-dual-credit/weights/9633/initial.pt" --previous-binding "$ARTIFACT_ROOT/variable-binding" \
    --previous-first "$ARTIFACT_ROOT/first-parent" --previous-joint "$ARTIFACT_ROOT/joint-partner" \
    --compiler "$CELL_COMPILER" --runtime-binary "$CELL_REPLAY"
}
if [ "$#" -ge 2 ]; then run "$@"; exit; fi
run selective_audit.py evaluate
run selective_worlds.py prepare
run selective_kernel.py train
run selective_controls.py evaluate
run selective_trials.py evaluate
run selective_cost.py cost
run selective_trials.py live
run selective_trials.py live --near
run selective_budget.py live
run selective_replication.py prepare
run selective_replication.py evaluate
run selective_replication.py live
run selective_replication.py cost
run selective_topology.py evaluate
"${PLOT_PYTHON:-python3}" selective_results.py "$out" "${RESULTS_DIR:-run-recall/selective-partner}"
