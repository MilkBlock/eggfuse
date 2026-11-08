# Complete stage entries for cross-Run Bake

This experiment follows `320858ca`. It measures the **standalone Cell CPU** on
sum-bits and Raytrace, with the ordinary repair engine. It does not run the new
congruence-cell prototype on the complete applications or measure native egglog.

## Opportunity and compiler change

The previous learned catalog could compose only 32 admitted leaf entries, even
though the programs each contain 582 rules. We collected actual winning Spine
transitions from those frozen programs. The traces contain 97 / 127 distinct
consumer entries and 3,034 / 663,403 resumptions. Visits are consumer executions,
not committed mutations or distinct producer executions.

First, increasing the old admission limit to 128 selects all 79 / 104 eligible
entries. These cover 2,550 / 621,825 observed resumptions. The remaining entries
have dependent table reads or primitive steps. Raising a budget cannot lower
those recipes with the old zero-or-one-table-port block format.

The opt-in `eggfuse-spine-blocks/v2` policy lowers the complete, already certified
stage entry into ordered input projections, table ports, primitive calls and
result checks. Each input must come from the checked anchor, a literal or an
earlier step. Loading independently reconstructs the complete block; the
artifact cannot supply its own wiring or reorder guards. Missing tables, failed
guards, bound-result checks, receipt witnesses, epoch watermarks and the existing
source schedule remain runtime obligations. No extra equality or early union is
introduced. Older v1 artifacts retain their serialized blocks and execution path.

`bake_spine_blocks ... --complete-stage` enables this policy. Rebaking either
policy removes the old iterative catalog, whose leaf indices and seed digest
would otherwise refer to the replaced leaf set. Continuations are learned again
against the new, validated seed.

The new policy admits all 97 / 127 observed entries. All selections here use the
same workload as training and replay; these are not held-out generalization
results. This remains bounded replay-and-recompile learning, not hot replacement.

## Successful work

All variants use depth 8, 16 nodes, 16 admissions per round, 2,048 candidate slots,
support 2 and up to six rounds. Expanded catalogs have a 256-unit budget. Every
variant stops after two admission rounds because no further profitable candidate
is found. No round hits the total-unit or candidate-counter limit.

| Case / leaves / proof | Final units | Reused constructor reads | Reused sets | Complete RHSs |
|---|---:|---:|---:|---:|
| sum-bits / 32 / v1 | 37 | 272 | 165 | 165 |
| sum-bits / 79 / v1 | 86 | 272 | 170 | 165 |
| sum-bits / 97 / v1 | 105 | 274 | 170 | 165 |
| sum-bits / 97 / v2 | 108 | 274 | 170 | 165 |
| Raytrace / 32 / v1 | 39 | 30,900 | 17,346 | 17,152 |
| Raytrace / 104 / v1 | 115 | 31,764 | 17,363 | 18,016 |
| Raytrace / 127 / v1 | 139 | 31,808 | 17,363 | 18,016 |
| Raytrace / 127 / v2 | 149 | 31,811 | 17,363 | 18,016 |

Here proof v1/v2 refers to the **result switch** policy, independently of the
stage-block format. The 97 / 127 leaves use stage-block v2 in both proof lanes.
Wider admission supplies 864 additional complete Raytrace RHSs (5.04% relative
to 17,152). Full stage lowering adds 44 constructor reads under proof v1 and
three further reads under proof v2; it adds no complete RHS. Increased catalog
size alone is not a performance result.

[results.json](results.json) records all learning rounds, admission coverage,
work counts and semantic stamps. Every round in every variant agrees with the
previous 32-leaf learning runs on the final graph, semantic schedule and ordered
RHS-input digest. Compiler stamps are compared only in the compiler domain.

## Inference time and memory

Seven fresh-process samples per lane, after one warmup, run in a seeded shuffled
order with no concurrent builds or training. Each run's final graph and semantic
schedule agree with the parent executable. Setup and export are excluded from
inference time; peak RSS is sampled through inference. [timings.json](timings.json)
keeps every sample, counter set and binary/program hash.

| Lane | sum-bits median (ms) | Raytrace median (s) | Raytrace median peak RSS (MiB) |
|---|---:|---:|---:|
| Parent executable, frozen 64-unit catalog | 20.238 | 7.876 | 1,858.11 |
| New executable, same frozen catalog | 20.032 | 7.828 | 1,857.50 |
| Wider legacy leaves, learned proof v1 | 20.842 | 7.839 | 1,852.14 |
| Complete stage leaves, learned proof v1 | 20.947 | 7.826 | 1,858.06 |
| Complete stage leaves, learned proof v2 | 21.338 | 7.855 | 1,854.02 |

There is **no demonstrated overall throughput improvement**. Raytrace's median
changes are below 1%, with overlapping ranges and drift during the run (parent
7.579–8.266 s; staged v1 7.626–7.977 s). The expanded sum-bits catalogs have higher
medians. These findings do not justify replacing the default frozen catalog.
The work reduction and the additional compiled expression capability are the
positive results; neither establishes that rebuild ceased to be a bottleneck.

## Remaining limits

Repair work is unchanged: Raytrace still performs 643,609 dependency repairs and
226,523 effective unions. Complete stage lowering changes matcher dataflow and
RHS receipt reuse, not repair propagation. In the standalone execution the
stronger result-switch policy initializes 3,763 demanded root states to reuse
three additional constructor reads over staged v1. That is an execution cost,
not evidence of valuable completion.

[Producer coverage](producer-coverage.json) records the other admission gap:
Raytrace has 102 observed producer rules outside the full stage leaf set, with
255,276 outgoing consumer visits. A static
eligibility query over all certified stage entries finds only two additional
Raytrace producer-only rules (seven outgoing consumer visits) that full stage
lowering could admit. These counts are not distinct producer executions. Most
missing producer rules have no complete single-anchor entry; simply raising the
leaf budget again cannot represent them. A future producer receipt node needs a
separate proof based on the completed source execution, with explicit capture
cost and downstream demand, rather than requiring a consumer matching block.

## Verification

166 all-feature workspace tests pass, with four existing tests ignored. The
new integration fixture also passes with the non-sparse iterative backend. It
checks a dependent table/primitive chain, a failed guard, a missing port that
appears in a later Run, successful cross-Run RHS completion, and fallback when
the later update supplies another origin. Final graph and per-Run semantics
match the ordinary execution; native egglog also executes the fixture checks.
A unit test checks input order, earlier-result references and bound results.
Corrupted wiring and relabeling a staged artifact as v1 are rejected.

The full-application profile export initially failed with low disk space; the
successful Raytrace rerun produced an identical trace. Only this experiment's
reproducible duplicate exports were removed. Timing exports are hashed and
checked before removal to keep disk use bounded.

## Reproduce

Use fresh output paths. `PROGRAM` is a frozen compiled input; `CASE` is a local
output prefix. The source programs are described in the repository README.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,spine-shapes --bin eggfuse-cell-runtime --example bake_spine_blocks
target/release/eggfuse-cell-runtime --program PROGRAM --output out/CASE-profile
target/release/examples/bake_spine_blocks PROGRAM out/CASE-profile/spine-shapes.json PROGRAM out/CASE-wide.json 128
target/release/examples/bake_spine_blocks PROGRAM out/CASE-profile/spine-shapes.json PROGRAM out/CASE-staged.json 256 --complete-stage
cargo cell-iterate --program out/CASE-staged.json --output out/CASE-learn --objective rhs-congruence --rounds 6 --max-depth 8 --max-nodes 16 --max-units 256 --new-per-round 16 --candidate-slots 2048
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --features iterative-bake --test compiler complete_stage_blocks
```

For the same compiler configuration used here, build the compiler with
`sparse-cells,view-ports,iterative-bake`, save the executable, and call `iterate`
directly. Compare `rhs-lookups` and `rhs-congruence` for each leaf seed. The
`analyze.py` docstring describes its input manifest; it rejects differing
semantic stamps before writing the collected result. `measure.py` takes a
manifest of runtime/program pairs, interleaves fresh processes, compares each
final graph and semantic schedule, and saves samples before removing large
exports. Build the measured runtime with `sparse-cells,view-ports,storage-metrics`
and without `spine-shapes`; do not include concurrent builds or training in the
timing run.

To reproduce producer coverage, `producer_coverage.py` accepts `--program`,
`--profile`, `--leaves`, `--baker` and `--output`. It uses actual outgoing visits
for coverage and queries static eligibility separately using all certified
stage entries. That synthetic eligibility query is not execution evidence and
is never used as a learned workload catalog.
