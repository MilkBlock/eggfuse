#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export KV_OWNER_OUT="${KV_OWNER_OUT:-$ARTIFACT_ROOT/cell-kv-balanced}"
export PARTNER_INDEX_OUT="$KV_OWNER_OUT"
run() { sh partner_index_reproduce.sh "$@"; }
export KV_READOUT=owner
run cell_kv_study.py prepare
KV_ARMS=CD run cell_kv_study.py train
KV_ARMS=CD KV_NATIVE_FILE=readout-control.json run cell_kv_study.py live
export KV_READOUT=full PARTNER_INDEX_OUT="${CELL_KV_OUT:-$ARTIFACT_ROOT/cell-kv-fullread}"
run cell_kv_study.py prepare
KV_ARMS=ABCDU run cell_kv_study.py train
run cell_kv_study.py live
KV_ARMS=U KV_NATIVE_FILE=untyped.json run cell_kv_study.py live
run cell_kv_controls.py evaluate
run cell_kv_probes.py evaluate
run cell_kv_probes.py live
run cell_kv_probes.py cost
run cell_kv_owner_probe.py evaluate
run cell_kv_fit.py evaluate
run cell_kv_export.py evaluate
