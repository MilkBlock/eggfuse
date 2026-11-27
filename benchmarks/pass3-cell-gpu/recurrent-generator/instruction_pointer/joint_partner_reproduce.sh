#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
out=${JOINT_PARTNER_OUT:-"$ARTIFACT_ROOT/joint-partner"}
py=${PYTHON:-python3}
run() {
    script=$1
    shift
    "$py" "$script" "$@" --out "$out" --data "$CELL_DATA" --previous "$ARTIFACT_ROOT/transition-credit-1127/dynamic" \
        --audit "$ARTIFACT_ROOT/address-audit-1126" --contract "$ARTIFACT_ROOT/query-contract-1126" \
        --corpus "$ARTIFACT_ROOT/run-continuation-1126" --initial "$ARTIFACT_ROOT/discovery-dual-credit/weights/9633/initial.pt" \
        --previous-binding "$ARTIFACT_ROOT/variable-binding" --previous-first "$ARTIFACT_ROOT/first-parent" \
        --compiler "$CELL_COMPILER" --runtime-binary "$CELL_REPLAY"
}
run joint_partner_worlds.py prepare
run joint_partner.py train
run joint_partner.py evaluate
run joint_partner_stress.py prepare
run joint_partner_stress.py evaluate
run joint_partner_challenge.py prepare
run joint_partner_challenge.py evaluate
run joint_partner.py live
run joint_partner.py cpu
run joint_partner_context.py evaluate
run joint_partner.py cost
run joint_partner_budget.py live
run joint_partner_copy.py live
"${PLOT_PYTHON:-$py}" joint_partner_results.py "$out" "${RESULTS_DIR:-run-recall/joint-partner}"
