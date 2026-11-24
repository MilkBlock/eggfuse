# First divergence and native oracle headroom

Symbolic Execution offline diagnosis. The reference is the Rust EggFuse Cell runtime. Exclusive A uses the frozen unlimited symbolic one/two-owner generator. The oracle consumes a complete prerecorded tape and checks named parents. This study ran no network and changed no model.

## Earliest observable difference in A

The immediately preceding independent-state export, per-Run schedule, writes, effects and events match native reference. At the first different Run the two whole-graph digests differ. Issue all of A's requests on the aligned snapshot, match accepted proofs to native teacher winner identities, then enumerate the full Cartesian product of typed visible named ports for every missing rule. Native verification checks each tuple against that Run. The enumeration includes tuples which fail delta ownership or a guard. Each teacher proof was recovered. Every missed binding has exactly one valid named tuple at this boundary, with three owners. None belonged to A. In a second check, delete only those requests from the teacher tape and replay through this boundary. All five observables (schedule, writes, ordered RHS, events, final digest) exactly reproduce independent A.

| Program | First Run | Teacher | A proposals | A hits | Missing teacher token IDs by rule 532 / 534 (inclusive) | Typed tuples checked |
|---|---:|---:|---:|---:|---|---:|
| fact | 9 | 21 | 23 | 15 | 21–24 / 25–26 | 4,200 |
| loopfact | 10 | 16 | 19 | 12 | 26–27 / 28–29 | 3,000 |
| sum-divisors | 14 | 39 | 32 | 21 | 75–88 / 89–92 | 11,400 |

Both rules read a Bop, type metadata (bop-of-type or bpred-of-type), and bop->string, producing ExpectType effects. No later teacher token directly names any of the 28 missing tokens in these tapes. Native graph effects or missing checks can still matter. This experiment identifies the cause of the first difference and does not establish the cause of every later divergence. Other rules, future snapshots and alternative derivations outside the first-Run named-proof search remain possible. Across the earlier 120 frozen Runs, 447 teacher proofs have at least three parents and two have zero; subtracting 1,505 from 1,954 counts both groups. Per-commit named parents, versions, candidate membership and causal checks are in [divergence.json](divergence.json).

## Where a perfect proposer has room

Four alternating pairs per program, changing which arm runs first. Each trial starts a fresh process on the same machine. Validate full exact and capture trajectories, then check oracle schedule, ordered RHS, writes, resumes, events, reference digest, accepted count and zero pending/duplicate/rejected tokens. Timed runs disable detailed audit, repeat schedule and digest checks and include normal receiver work. Engine time starts after parsing program/tape and ends before export; process wall includes both. Search, RHS and repair are native phase timers. Setup, delivery and index maintenance account for remaining time. Report medians of times and medians of *paired ratios*. Last column is the hypothetical engine ratio with all search time removed and every other cost fixed. It assumes free verification. Actual oracle ratios include verification and receipt bookkeeping. Tape acquisition is offline.

| Workload | Runs | Commits | Exact engine ms | Search ms | RHS ms | Repair ms | Oracle engine ms | Engine ratio | Exact wall ms | Oracle wall ms | Wall ratio | Faster pairs, engine / wall | Free-search bound |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|
| jacobi-1d | 1990 | 41,319 | 125.762 | 52.743 | 32.726 | 12.926 | 104.578 | 1.21 | 316.12 | 303.65 | 1.04 | 4/4, 4/4 | 1.71 |
| conjugate-gradient | 2896 | 131,371 | 378.597 | 161.179 | 99.747 | 40.242 | 323.808 | 1.18 | 661.93 | 642.70 | 1.03 | 4/4, 4/4 | 1.74 |
| 3mm | 4260 | 294,917 | 1015.459 | 417.636 | 286.236 | 112.938 | 845.748 | 1.18 | 1603.90 | 1462.52 | 1.07 | 4/4, 4/4 | 1.70 |
| deriche | 5687 | 635,818 | 1670.683 | 697.380 | 465.607 | 167.622 | 1512.427 | 1.09 | 2332.44 | 2406.41 | 0.97 | 4/4, 0/4 | 1.72 |
| points-to | 3 | 5 | 0.177 | 0.045 | 0.013 | 0.001 | 0.159 | 1.13 | 6.99 | 7.63 | 0.94 | 3/4, 0/4 | 1.37 |
| eqsat-basic | 3 | 11 | 0.205 | 0.055 | 0.026 | 0.016 | 0.171 | 1.19 | 6.53 | 6.15 | 1.03 | 3/4, 2/4 | 1.37 |
| points-to-256 | 4 | 1,285 | 5.626 | 1.763 | 0.788 | 0.002 | 4.735 | 1.16 | 24.63 | 25.07 | 0.98 | 4/4, 1/4 | 1.45 |
| path-chain160 | 161 | 12,880 | 14.168 | 5.097 | 6.363 | 0.007 | 18.133 | 0.79 | 46.19 | 51.57 | 0.89 | 0/4, 0/4 | 1.55 |
| cykjson-rows | 43 | 4,991 | 98.319 | 90.862 | 4.374 | 0.009 | 12.791 | 7.81 | 125.11 | 43.15 | 2.87 | 4/4, 4/4 | 13.20 |

The four larger EggCC programs use frozen seed-1703 compiled Pass 3 artifacts. All four replay through their full source schedule. For the egglog cases the receiver cannot witness a terminal check. Both timed arms therefore stop after all original inference Runs. The unrestricted exact reference executes the checks; both endpoints reproduce its entire inference trajectory and final graph. The original points-to example requests exactly three Runs. The scaled variant also includes its quiescent Run.

CYK uses the stock grammar, three rules, schedule and all 801 tokens of the upstream small JSON input. The standalone compiler requires inlined CSV facts. It also rejects a post-run unused global binding; the derived source removes that binding but preserves its P check. We ran the unmodified upstream file with the installed egglog CLI (exit 0) and confirmed both the omitted final B lookup and the P relation in the exported native state. [Final witnesses](cyk-final-check.json). The speed ratios compare EggFuse exact to EggFuse oracle. They do not compare EggFuse to upstream egglog.

Points-to and eqsat-basic are unmodified bundled examples. Points-to-256 and path-chain160 use stock rules with generated extra input; the latter uses a two-edge Bake donor. They are workload-shape controls. The source preparation script also tried the stock path, CYK, CYK JSON, matrix, unification-points-to, fibonacci-demand, hardboiled_conv1d_32, eggcc-extraction and math-microbenchmark files. The flat compiler rejected input/surface or command ordering on the first seven. EggCC extraction failed on an unbound Bake symbol; math-microbenchmark exceeded the 25-second compile allowance. None of those failures enters a speed ratio. This is a targeted survey, not a complete upstream compatibility suite.

The 801-token CYK case meets 2× on both clocks. Large EggCC Pass 3 alone did not reach this threshold, even on the free-search estimate. This establishes headroom for avoiding search on the selected parser; the cost and coverage of a frontier, a learned proposer, or a higher-order activation policy remain unmeasured.

## Reproduce

In the instruction_pointer directory, use the existing captured workspace. [Raw pairs and artifact digests](paired.json) identify exact inputs and the timed receiver; the divergence audit uses the previous frozen A receiver. The single reporting change exposes the already-measured RHS phase. The saved reviewed sum-bits semantic exports are checked separately.

```sh
root=/Volumes/EggFuseWorkspace/experiments/actor-eggcctraining-20261123
py=/Volumes/EggFuseWorkspace/envs/eggfuse-ml/bin/python
bench="$PWD"
cd "$root/model-tree"
cargo build --release --locked -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay --target-dir "$root/unified-scale/build"
cd "$bench"
out="$root/oracle-survey"
bin="$root/unified-scale/build/release/examples/cell_token_replay"
"$py" oracle_survey_inputs.py "$root/unified-scale/build/release/eggfuse-cell-compiler" "$root/model-tree/egglog/tests" "$out"
"$py" audit_first_divergence.py "$root" "$out/divergence.json"
for c in jacobi-1d conjugate-gradient 3mm deriche; do
  "$py" oracle_headroom.py "$bin" "$root/../frozen-native-plans-parity-v2/$c/rust-1703/program.json" "$out/$c"
done
for c in points-to eqsat-basic points-to-256 path-chain160 cykjson-rows; do
  "$py" oracle_headroom.py "$bin" "$out/$c/program.json" "$out/$c"
done
(cd "$root/model-tree/egglog" && egglog tests/cykjson.egg)
"$bin" reference "$out/cykjson-rows/program.json" - audit --export "$out/cykjson-rows/state.json" > "$out/cykjson-rows/check.json"
```
