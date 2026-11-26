#!/bin/sh
# Run from recurrent-generator/instruction_pointer, using the archived first-tier inputs.
set -eu
: "${DATA:?EggCC runtime data}" "${PREVIOUS:?data-scale-1126}" "${CORPUS:?run-continuation-1126}" "${AUDIT:?address-audit-1126}" "${CONTRACT:?query-contract-1126}" "${RUNTIME:?cell_token_replay}" "${COMPILER:?eggfuse-cell-compiler}" "${OUT:?new working directory}"
py=${PY:-python3}
base=$(dirname "$OUT")
initial=${INITIAL:-"$base/credit-scaling-1126/weights/9633/mixed-n480-u1920.pt"}
archive=${ARCHIVE:-"$base/discovery-control"}
f="$OUT/fine"
bank="$OUT/dynamic"
mkdir -p "$bank" "$f" "$OUT/tmp"
export TMPDIR="$OUT/tmp" PYTHONDONTWRITEBYTECODE=1
for name in held s243; do
    if [ ! -e "$bank/$name" ]; then ln -s "$PREVIOUS/$name" "$bank/$name"; fi
done
run() {
    script=$1; corpus_bank=$2; destination=$3; shift 3
    "$py" "$script" --data "$DATA" --previous "$corpus_bank" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --runtime-binary "$RUNTIME" --out "$destination" "$@"
}
collect() {
    location=$1; destination=$2; checkpoint=$3; first=$4; stop=$5; cap=$6; seed=$7; shift 7
    run credit_scale_buffer.py "$location" "$destination" --checkpoint "$checkpoint" --first "$first" --stop "$stop" --cap "$cap" --lanes 6 --rollout-seed "$seed" --branches "$@"
}
"$py" transition_programs.py --out "$OUT" --prior "$PREVIOUS" --compiler "$COMPILER" --count 200
"$py" transition_programs.py --out "$OUT" --prior "$PREVIOUS" --compiler "$COMPILER" --first 256 --count 264
# Matched static/dynamic experiment followed by the original million-token cohort.
collect "$PREVIOUS" "$OUT/static" "$initial" 0 32 256 0 1 2
collect "$bank" "$OUT" "$initial" 0 32 256 0 1 2
for objective in slot complete; do
    steps=384
    if [ "$objective" = complete ]; then steps=192; fi
    for size in static dynamic; do
        run transition_fit.py "$bank" "$OUT" --objective "$objective" --size "$size" --initial "$initial" --static-bank "$PREVIOUS" --programs 32 --steps "$steps"
    done
done
collect "$bank" "$OUT" "$initial" 32 34 256 0 1 2
donor="$OUT/weights/9633/dynamic-paired.pt"
collect "$bank" "$OUT" "$donor" 34 200 512 0 2
collect "$bank" "$OUT" "$donor" 34 66 128 0 1
collect "$bank" "$OUT/diverse" "$initial" 0 200 64 90071 2
collect "$bank" "$OUT/held" "$initial" 256 264 256 0 1 2
for seed in 9633 5003; do cp "$initial" "$OUT/weights/$seed/initial.pt"; done
# Held-state distribution controls from the preceding matched-data experiment.
run transition_held.py "$bank" "$OUT" --label fixed --arms factored initial static-plain dynamic-plain dynamic-flat dynamic-paired dynamic-no-omission
run transition_held.py "$bank" "$OUT" --label complete-fixed --arms complete-static-plain complete-dynamic-plain complete-dynamic-flat complete-dynamic-paired complete-dynamic-no-omission
# Fresh two-observer data. All new offline supervision is produced after the rollout.
collect "$bank" "$f" "$initial" 0 80 48 171731 1 2
"$py" fine_credit.py "$f" "$bank" "$RUNTIME" --limit 4
"$py" fine_credit.py "$OUT/held" "$bank" "$RUNTIME" --limit 8
for dir in "$OUT" "$OUT/diverse"; do "$py" fine_credit.py "$dir" "$bank" "$RUNTIME" --limit 2; done
"$py" transition_credit.py "$f" --bank "$bank" --output "$f/fine-inventory.json"
"$py" transition_credit.py "$OUT" --also "$OUT/diverse" "$f" --bank "$bank" --output "$f/pooled-inventory.json"
"$py" transition_controls.py --out "$f" --runtime "$RUNTIME" --compiler "$COMPILER"
"$py" fine_higher.py --out "$f" --runtime "$RUNTIME" --compiler "$COMPILER" --data "$DATA" --actor run-recall/higher-scaling/weights/actor.pt
"$py" fine_ports.py --out "$f" --runtime "$RUNTIME" --compiler "$COMPILER"
for objective in slot complete; do
    tag=fine; small=small
    if [ "$objective" = complete ]; then tag=full; small=full-small; fi
    run fine_fit.py "$bank" "$f" --initial "$initial" --programs 80 --steps 400 --objective "$objective" --tag "$tag"
    run fine_fit.py "$bank" "$f" --initial "$initial" --programs 16 --steps 400 --objective "$objective" --tag "$small" --arms A E
done
# The slot pilot ran all arms on fact for the first draw. Formal evaluation is the complete-token panel.
run credit_scale_eval.py "$bank" "$f" native --cases fact --initial "$initial" --archive "$archive" --seeds 9633 --arms initial fine-A fine-B fine-C fine-D fine-E small-A small-E
run credit_scale_eval.py "$bank" "$f" native --initial "$initial" --archive "$archive" --seeds 9633 5003 --arms initial full-A full-B full-C full-D full-E
run fine_held.py "$bank" "$f" --held "$OUT/held" --label fine --arms factored initial fine-A fine-B fine-C fine-D fine-E small-A small-E full-A full-B full-C full-D full-E
run fine_held.py "$bank" "$f" --held "$OUT/held" --label small-complete --arms full-small-A full-small-E
run fine_egg_audit.py "$bank" "$f"
mkdir -p "$f/timing"
if [ ! -e "$f/timing/weights" ]; then ln -s "$f/weights" "$f/timing/weights"; fi
run credit_scale_eval.py "$bank" "$f/timing" native --cases sum-divisors --initial "$initial" --archive "$archive" --seeds 9633 --arms initial full-E
run experience_clock.py "$bank" "$f"
"$py" fine_report.py "$f" "$f/published"
"${PLOT_PY:-python3}" run-recall/fine-credit/plot.py "$f/published"
FINE_CREDIT_OUTPUT="$f" "$py" -m unittest discover
