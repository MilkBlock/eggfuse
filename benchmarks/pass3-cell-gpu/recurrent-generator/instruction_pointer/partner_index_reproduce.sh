#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
out=${PARTNER_INDEX_OUT:-"$ARTIFACT_ROOT/partner-index"}
mkdir -p "$out"
run() {
  "${PYTHON:-python3}" "$@" --out "$out" --data "$CELL_DATA" \
    --previous "$ARTIFACT_ROOT/transition-credit-1127/dynamic" --audit "$ARTIFACT_ROOT/address-audit-1126" \
    --contract "$ARTIFACT_ROOT/query-contract-1126" --corpus "$ARTIFACT_ROOT/run-continuation-1126" \
    --initial "$ARTIFACT_ROOT/discovery-dual-credit/weights/9633/initial.pt" --previous-binding "$ARTIFACT_ROOT/variable-binding" \
    --previous-first "$ARTIFACT_ROOT/first-parent" --previous-joint "$ARTIFACT_ROOT/joint-partner" \
    --selective "$ARTIFACT_ROOT/selective-partner" --compiler "$CELL_COMPILER" --runtime-binary "$CELL_REPLAY"
}
if [ "$#" -gt 0 ]; then run "$@"; exit; fi
run partner_index_worlds.py prepare
run partner_index_trials.py evaluate
run partner_index_trials.py live
run partner_index_shared.py evaluate
run partner_index_shared.py live
run partner_index_cost.py cost
run partner_index_diagnostics.py evaluate
"${PLOT_PYTHON:-python3}" partner_index_results.py "$out" "${RESULTS_DIR:-run-recall/partner-index}"
