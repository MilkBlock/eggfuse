#!/bin/sh
set -eu
: "${ARTIFACT_ROOT:?}" "${CELL_DATA:?}" "${CELL_REPLAY:?}" "${CELL_COMPILER:?}"
cd "$(dirname "$0")"
export PARTNER_INDEX_OUT="${PARTNER_INDEX_OUT:-$ARTIFACT_ROOT/conditional-value}"
export KV_READOUT=full VALUE_READ_SCALE=rich
for script in scaling_archive scaling_transitions scaling_rollouts scaling_frequency scaling_effects scaling_egg_effects scaling_validation scaling_inventory; do
    sh partner_index_reproduce.sh "$script.py" evaluate
done
"${PYTHON:-python3}" scaling_size_control.py &
size_pid=$!
CELL_MODEL=factorized-random sh partner_index_reproduce.sh scaling_eval.py evaluate
"${PYTHON:-python3}" scaling_size_control.py --effects &
effect_pid=$!
"${PYTHON:-python3}" scaling_size_control.py --frequency &
frequency_pid=$!
"${PYTHON:-python3}" scaling_campaign.py --workers "${CELL_WORKERS:-3}" --hours "${CELL_HOURS:-8}"
wait "$size_pid"
wait "$effect_pid"
wait "$frequency_pid"
sh partner_index_reproduce.sh scaling_postfit.py evaluate
sh partner_index_reproduce.sh scaling_counterfactual.py evaluate
sh partner_index_reproduce.sh scaling_timing.py evaluate
sh partner_index_reproduce.sh scaling_batch.py evaluate
"${PYTHON:-python3}" full_ce_report.py
