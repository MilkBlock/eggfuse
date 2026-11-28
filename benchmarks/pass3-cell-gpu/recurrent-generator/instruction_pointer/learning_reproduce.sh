#!/bin/sh
# Uses the same native data and environment as partner_index_reproduce.sh.
set -eu
: "${PARTNER_INDEX_OUT:?set the existing CPU teacher-forcing artifact directory}"
export KV_READOUT=full VALUE_READ_SCALE=rich
execute() { sh partner_index_reproduce.sh "$@"; }
execute learning_fork.py train
execute learning_entropy.py evaluate
for name in local-s71-t100000 A-batched/local-s71-t250000 A-batched/local-s71-t500000 A-batched/local-s71-t1000000 matched-end-to-end/full-s71-t250000 matched-end-to-end/full-s71-t500000 matched-end-to-end/full-s71-t1000000 random history
do
    export EXPOSURE_MODELS="$name"
    execute learning_native.py evaluate
    execute learning_effects.py evaluate
    case "$name" in random|history) continue;; esac
    execute learning_probe.py evaluate
done
execute learning_timing.py evaluate
"${PYTHON:-python3}" learning_report.py
