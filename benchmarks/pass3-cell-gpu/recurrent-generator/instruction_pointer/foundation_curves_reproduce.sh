#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_COMPILER:?}" "${CELL_REPLAY:?}"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
export FC_CATS="multi primitive short medium half medium-half"
run() { sh partner_index_reproduce.sh "$@"; }
run foundation_fit.py train
run foundation_fresh.py train
run foundation_long.py train
run foundation_wake.py evaluate
run foundation_observable.py evaluate
run foundation_catalogue_probe.py evaluate
run foundation_frontier.py evaluate
run foundation_egg.py evaluate
run foundation_egg_catalogue.py evaluate
FC_RECEIPTS=1 run foundation_egg_catalogue.py evaluate
out=${RESULTS_DIR:-run-recall/foundation-curves}
"${PYTHON:-python3}" foundation_curve_results.py "$PARTNER_INDEX_OUT/foundation-curves" "$out"
"${PLOT_PYTHON:-python3}" foundation_curve_plot.py "$out"
