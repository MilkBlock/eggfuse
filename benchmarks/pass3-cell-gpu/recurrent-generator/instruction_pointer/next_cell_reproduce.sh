#!/bin/sh
# Execute from the instruction_pointer research directory.
set -eu
: "${ARTIFACT_ROOT:?set ARTIFACT_ROOT to the eggfuse-experiments archive}"
: "${CELL_DATA:?set CELL_DATA to the native workload bank}"
: "${CELL_REPLAY:?set CELL_REPLAY to cell_token_replay}"
: "${CELL_COMPILER:?set CELL_COMPILER to eggfuse-cell-compiler}"
PY=${PYTHON:-python3}
OUT=${PRETRAIN_OUT:-"$ARTIFACT_ROOT/next-cell-pretraining"}
DY="$ARTIFACT_ROOT/transition-credit-1127"
DU="$ARTIFACT_ROOT/discovery-dual-credit"
BASELINE="$DU/weights/9633/initial.pt"
ARCHIVE="$ARTIFACT_ROOT/discovery-control"
run() {
    file=$1
    shift
    "$PY" "$file" --out "$OUT" --data "$CELL_DATA" --previous "$DY/dynamic" \
        --corpus "$ARTIFACT_ROOT/run-continuation-1126" --audit "$ARTIFACT_ROOT/address-audit-1126" \
        --contract "$ARTIFACT_ROOT/query-contract-1126" --runtime-binary "$CELL_REPLAY" "$@"
}
run next_cell_corpus.py --buffer-root "$DY" --dual "$DU" --indices $(seq 0 199) $(seq 256 263)
"$PY" next_cell_inventory.py --out "$OUT" --buffer-root "$DY" --dual "$DU"
run next_cell_witnesses.py
run next_cell_train.py --initial "$BASELINE" --epochs 6 --programs 200
run next_cell_train.py --initial "$BASELINE" --epochs 6 --programs 24
run next_cell_higher.py teacher --compiler "$CELL_COMPILER"
run next_cell_train.py --initial "$BASELINE" --epochs 6 --programs 200 --mixed
run credit_scale_eval.py native --archive "$ARCHIVE" --initial "$BASELINE" --arms initial ce24 ce200 ce200mixed
run next_cell_higher.py test --compiler "$CELL_COMPILER"
run next_cell_higher.py test --trace --compiler "$CELL_COMPILER"
run next_cell_eval.py --archive "$ARCHIVE"
"$PY" -m unittest -v test_next_cell_pretraining
run next_cell_family.py
run next_cell_transfer.py
"$PY" next_cell_report.py --archive "$ARCHIVE" --out "$OUT" --dest "$OUT/report"
"${PLOT_PYTHON:-$PY}" next_cell_plot.py "$OUT/report"
