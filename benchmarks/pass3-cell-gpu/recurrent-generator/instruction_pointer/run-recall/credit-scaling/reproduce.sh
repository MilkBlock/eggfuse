#!/bin/sh
# Run in recurrent-generator/instruction_pointer with a new OUT on the experiment disk.
set -eu
: "${DATA:?native program bank}" "${PREVIOUS:?data-scale-1126}" "${CORPUS:?run-continuation-1126}" "${CONTRACT:?query-contract-1126}" "${AUDIT:?address-audit-1126}" "${OUT:?fresh experiment folder}" "${RUNTIME:?cell_token_replay}" "${COMPILER:?eggfuse-cell-compiler}"
py=${PY:-python3}
base=$(dirname "$OUT")
initial="$base/experience-ablation/weights/9633/TSO.pt"
updated="$OUT/weights/9633/omission-n16-u192.pt"
mkdir -p "$OUT" "$OUT/tmp"
export TMPDIR="$OUT/tmp" PYTHONDONTWRITEBYTECODE=1
run() {
    script=$1
    shift
    "$py" "$script" --data "$DATA" --previous "$PREVIOUS" --corpus "$CORPUS" --audit "$AUDIT" --contract "$CONTRACT" --runtime-binary "$RUNTIME" --out "$OUT" "$@"
}
collect() {
    run credit_scale_buffer.py --first "$1" --stop "$2" --checkpoint "$3" --lanes "$4" --cap "$5" --branches $6
}
fit() {
    n=$1; u=$2; shift 2
    run credit_scale_fit.py --programs "$n" --updates "$u" --initial "$initial" --arms "$@"
}
collect 0 2 "$initial" 4 160 '0 1'
collect 2 96 "$initial" 6 160 '0 1'
fit 16 192 omission
collect 96 152 "$updated" 6 160 '0 1'
collect 0 210 "$updated" 6 256 2
"$py" credit_scale_programs.py --data "$DATA" --previous "$PREVIOUS" --out "$OUT" --compiler "$COMPILER"
collect 210 480 "$updated" 6 256 2
run credit_scale_archive.py
"$py" credit_scale_inventory.py "$OUT" "$PREVIOUS/programs"
"$py" credit_scale_contrasts.py --runtime "$RUNTIME" --previous "$PREVIOUS" --out "$OUT"
clang -dynamiclib -fobjc-arc -framework Foundation -framework Metal metal_wait.m -o "$OUT/metal-waits.dylib"
run credit_scale_profile.py --checkpoint "$updated" --library "$OUT/metal-waits.dylib"
fit 64 192 omission
fit 152 192 teacher self omission duplicate failure shuffle downstream
for n in 16 64 152; do fit "$n" 1216 omission; done
fit 152 192 mixed
fit 480 192 mixed
fit 480 1920 mixed
run credit_scale_eval.py native --initial "$initial" --archive "$base/discovery-control"
run credit_scale_held.py --arms factored initial omission-n16-u192 omission-n64-u192 omission-n152-u192 omission-n16-u1216 omission-n64-u1216 omission-n152-u1216 mixed-n480-u192 mixed-n480-u1920
run credit_scale_eval.py frozen --initial "$initial" --archive "$base/discovery-control" --arms initial teacher-n152-u192 self-n152-u192 omission-n152-u192 duplicate-n152-u192 failure-n152-u192 shuffle-n152-u192 downstream-n152-u192 mixed-n480-u192 mixed-n480-u1920
run experience_clock.py
"$py" credit_scale_report.py "$OUT" "$OUT/published"
cp "$OUT"/inventory.json "$OUT"/archive.json "$OUT"/metal-profile.json "$OUT"/controlled-timing.csv "$OUT"/clock.csv "$OUT"/shards.csv "$OUT"/nested.csv "$OUT"/held-dags.jsonl "$OUT/published/"
"${PLOT_PY:-python3}" credit_scale_plot.py "$OUT/published"
"$py" -m unittest discover
