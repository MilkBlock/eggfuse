#!/bin/sh
# Execute from instruction_pointer after building the native compiler and replay example.
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
py=${PYTHON:-python3}
out=${BINDING_OUT:-"$ARTIFACT_ROOT/variable-binding"}
dest=${RESULTS_DIR:-run-recall/variable-binding}
initial="$ARTIFACT_ROOT/discovery-dual-credit/weights/9633/initial.pt"
mkdir -p "$out"
run() {
    script=$1
    shift
    "$py" "$script" --out "$out" --data "$CELL_DATA" --corpus "$ARTIFACT_ROOT/run-continuation-1126" \
        --previous "$ARTIFACT_ROOT/transition-credit-1127/dynamic" --audit "$ARTIFACT_ROOT/address-audit-1126" \
        --contract "$ARTIFACT_ROOT/query-contract-1126" --runtime-binary "$CELL_REPLAY" "$@"
}
"$py" binding_worlds.py --out "$out" --compiler "$CELL_COMPILER" --runtime-binary "$CELL_REPLAY"
run binding_packets.py
run binding_model.py --initial "$initial" --previous-corpus "$ARTIFACT_ROOT/completion-named-curriculum"
run binding_eval.py --initial "$initial"
for probe in interventions precision query_probe; do
    run "binding_${probe}.py" --compiler "$CELL_COMPILER" --initial "$initial"
done
run binding_parity.py --initial "$initial"
run binding_transfer.py --initial "$initial" --arms B flat C D --archive "$ARTIFACT_ROOT/discovery-control"
run binding_online.py --initial "$initial" --arms B C D
run binding_egg.py --initial "$initial" --cases fact loopfact sum-divisors --arms flat D
"$py" binding_results.py --out "$out" --dest "$dest"
"${PLOT_PYTHON:-$py}" binding_plot.py "$dest"
