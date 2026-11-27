#!/bin/sh
set -eu
# Inputs as in joint_cell_reproduce.sh. Run from instruction_pointer.
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
export KV_READOUT=full VALUE_READ_SCALE=rich
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
trial() {
    TR_CASE=$1 CS_CAPS="$2" CS_ARMS="$3" CS_SEEDS="$4" CS_REP="$5" \
      sh partner_index_reproduce.sh continuous_trials.py live
}
for c in fact loopfact sum-divisors; do
    trial "$c" '16 32 64 128 256 full' 'A B C iid random' '193 307' ''
    trial "$c" '16 32 64 128 256 full' history '193 307' '-ledger'
    TR_CASE=$c sh partner_index_reproduce.sh continuous_forks.py evaluate
    TR_CASE=$c sh partner_index_reproduce.sh continuous_device.py cost
done
for tag in t p paired; do
    for i in 0 1 2 3; do
        case "$tag" in
            t) other=flat; cap=256 ;;
            p) other=exact; cap=256 ;;
            paired) [ "$i" -lt 2 ] || continue; other='exact random'; cap=full ;;
        esac
        arms="A $other"
        if [ $((i % 2)) -ne 0 ]; then
            if [ "$tag" = paired ]; then arms='random exact A'; else arms="$other A"; fi
        fi
        for c in fact loopfact sum-divisors; do trial "$c" "$cap" "$arms" 193 "-$tag$i"; done
    done
done
"${PYTHON:-python3}" continuous_report.py "$PARTNER_INDEX_OUT/continuous-cell-stream" "${RESULTS_DIR:-run-recall/continuous-cell-stream}"
