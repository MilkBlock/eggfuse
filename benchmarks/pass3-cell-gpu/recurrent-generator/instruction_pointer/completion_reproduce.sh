#!/bin/sh
# Run in instruction_pointer, against the replay example built from this commit.
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
PY=${PYTHON:-python3}
OUT=${COMPLETION_OUT:-"$ARTIFACT_ROOT/completion-named-curriculum"}
DEST=${RESULTS_DIR:-run-recall/completion-curriculum}
INITIAL="$ARTIFACT_ROOT/discovery-dual-credit/weights/9633/initial.pt"
ARCHIVE="$ARTIFACT_ROOT/discovery-control"
NAME_ARG=
case "${COMPLETION_NAMING:-permuted}" in
    canonical) NAME_ARG=--canonical-names ;;
    permuted) ;;
    *) exit 2 ;;
esac
mkdir -p "$OUT"
run() {
    file=$1
    shift
    "$PY" "$file" --out "$OUT" --data "$CELL_DATA" --previous "$ARTIFACT_ROOT/transition-credit-1127/dynamic" \
        --corpus "$ARTIFACT_ROOT/run-continuation-1126" --audit "$ARTIFACT_ROOT/address-audit-1126" \
        --contract "$ARTIFACT_ROOT/query-contract-1126" --runtime-binary "$CELL_REPLAY" "$@"
}
build() { run completion_context.py $NAME_ARG --compiler "$CELL_COMPILER" "$@"; }
build --sizes 4 64 > "$OUT/pack-0.log" 2>&1 & p0=$!
build --sizes 8 128 > "$OUT/pack-1.log" 2>&1 & p1=$!
build --sizes 16 256 > "$OUT/pack-2.log" 2>&1 & p2=$!
build --sizes 32 1024 > "$OUT/pack-3.log" 2>&1 & p3=$!
wait "$p0"; wait "$p1"; wait "$p2"; wait "$p3"
build --sizes 4 8 --variants pair --instances $(seq 90 105) > "$OUT/pack-confirm.log" 2>&1
run completion_fit.py --initial "$INITIAL" > "$OUT/fit.log" 2>&1
run completion_probe.py $NAME_ARG --initial "$INITIAL" --compiler "$CELL_COMPILER" > "$OUT/probe.log" 2>&1
run completion_binding.py > "$OUT/binding.log" 2>&1
free() {
    run completion_free.py --seed "$1"
    run completion_free.py --seed "$1" --sizes 4 8 --variants pair --instances $(seq 90 105)
}
free 9633 > "$OUT/free9633.log" 2>&1 & p0=$!
free 5003 > "$OUT/free5003.log" 2>&1 & p1=$!
free 1777 > "$OUT/free1777.log" 2>&1 & p2=$!
wait "$p0"; wait "$p1"; wait "$p2"
run completion_early.py --archive "$ARCHIVE" --cases fact loopfact sum-divisors > "$OUT/early.log" 2>&1
run credit_scale_eval.py native --archive "$ARCHIVE" --initial "$INITIAL" --seeds 9633 5003 1777 --arms initial A B C --cases fact loopfact sum-divisors > "$OUT/independent.log" 2>&1
"$PY" completion_results.py --out "$OUT" --dest "$DEST"
"${PLOT_PYTHON:-$PY}" completion_plot.py "$DEST"
