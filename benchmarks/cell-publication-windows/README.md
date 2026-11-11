# Full checkpoint and source-Run choice evidence

Candidate engine: `4cfd0f7e`; historical fastest control: `8fffff65`, frozen
binary SHA recorded in results.json. This measures the standalone Cell CPU,
not native egglog. No production optimization from this experiment is retained.
It measures the earlier support gates and collision-delta correction together;
their individual latency contributions are not isolated.

## Complete measurements

Three lanes use the same historical compatible program per workload, canonical
repair ports and Entry publication. Seven sum-bits and five Raytrace samples
are interleaved after one warmup per lane. Binaries are ordinary release builds
with `sparse-cells,view-ports,storage-metrics`, without allocation/profiling
instrumentation. No compilation or source edits run during measurement.

| Median | Fast control | Current serial | Current four workers |
|---|---:|---:|---:|
| sum-bits inference | 18.084 ms | 15.183 ms | 15.243 ms |
| sum-bits whole process | 126.256 ms | 124.690 ms | 131.812 ms |
| Raytrace inference | 6.633 s | 5.921 s | 5.914 s |
| Raytrace whole process | 9.353 s | 8.605 s | 8.649 s |

For current serial / fast, paired median inference ratios are 0.8514 and
0.8951; paired bootstrap 95% intervals are [0.8438, 0.8724] and
[0.8857, 0.9658]. Raytrace whole-process ratio is 0.9281
[0.8930, 0.9810]. Sum-bits whole-process benefit is not established
(interval [0.9513, 1.0289]). Four workers do not demonstrate improvement over
current serial on either workload. These finite samples establish neither a
2x result nor a general sparsity theorem. Ratios of medians, paired ratios and
raw observations are recorded separately in results.json.

The historical sum-bits executable rejects the newer `multi_stage` relative
binding layout in the development program. Both timed sum-bits lanes therefore
use the exact historical checkpoint input, SHA `a174bd88...`; its source core
is unchanged. The Raytrace input is byte-identical to the earlier checkpoint.
Do not substitute the development sum-bits file when reproducing this campaign.

## Why strict final equality failed

The initial strict check failed at a `to-hoist` result, not at an independently
established core Eq mismatch. Excluding only this selector, **all 1,034,430
remaining rows and 524,655 Eq values have an exact rooted bijection**, including
terms, marker tables and visibility. There are 84 selected hoists per side.
The original sum-bits validator remains unchanged and passes its native
comparisons for the timed sum-bits exports.

The final-state sum-bits hoist condition cannot simply be applied to Raytrace:
both old and current executions contain one selected expression whose final
size is 1 although `to-hoist-size` and the current eligible maximum are 3.
The source uses `Expr-size :merge min`, `to-hoist-size :merge max` and
`to-hoist :merge new`; it does not automatically retract a historical choice
when the selected expression's size later decreases.

The current selection's observed timeline is:

| Source boundary | Selected expression size | Stored maximum |
|---|---:|---:|
| Run 14659, new selection published | 3 | 3 |
| Before Run 15205 | 1 | 3 |
| Final state | 1 | 3 |

This is why checking only the final value does not validate its original match.
It is not permission to accept an arbitrary nonmaximum choice.

## Explicit frozen Raytrace comparison contract

`check.py` is a separate, relative Cell-runtime check. It requires:

1. The exact frozen Raytrace source-core fingerprint and the reviewed sum-bits
   source-core fingerprint. All table declarations, schedule and non-rule
   metadata agree. Of 613 rules, 612 are identical modulo bound variable names;
   only workload initialization differs. Structural-key semantics agree, with
   explicitly checked literal string encodings. The sole selector writer is
   the unchanged `boundary-analysis` rule.
2. Snapshots immediately before and after every observed writer Run, with no
   union inside those windows. Every newly visible selection satisfies the
   original LHS in the **input** snapshot: DoWhile membership, invariant fact,
   Base type, and equality of the expression's size with `to-hoist-size`.
   The two executions validate 158 / 122 observed selection changes.
3. Selection continuity between windows through final Eq forwarding, no
   unexplained initial choices or merged selector keys, and exact agreement of
   the last forwarded selections with the final selector. Missing evidence
   fails closed. Readiness cannot be inferred from equal costs alone.
4. Exact equality of every other final table, every value, every visibility bit
   and all initial anchors. No term identities or additional table exclusions
   are introduced. Each diagnostic must reproduce its ordinary executable's
   exact final export and ordered Run records.

This contract proves the stated **relative final-state comparison with source
choice evidence**. It is not independent native Raytrace validation or a full
per-Run graph equivalence proof. Run ordinals, paths, rulesets, epochs, iteration
counts and changed flags agree between versions; binding counts intentionally
differ after correcting synthetic collision deltas. Every timed sample must
match its separately validated version's exact graph and full Run signature.
The strict whole-graph diagnostic remains `difference`.

The checker has negative tests for a mismatched input size, missing premises,
hidden/duplicate selectors and an unexplained choice between windows. The
existing sum-bits acceptance rules and exclusions are untouched.

## Optimization decision

A trial reused an exclusively owned decoded function row on value updates,
retaining immutable snapshots when readers existed. It saved only six
allocations on sum-bits and none on the 1,280-Run Raytrace prefix (150 / 0
eligible update checks). The candidate was reverted. The patch is retained
only as a reproducible rejected experiment; it is not part of the engine.

The refreshed complete serial profile attributes 46.81% of timed query work
to the 15 `Expr-size` rules: 1,918,618 matches, 1,128,542 actual function updates
and 790,076 unchanged single writes. This query fraction is not a fraction of
total inference. The earlier short prefix missed most repeated value updates.
An unchanged write does not by itself justify deleting matching or Cell
completion: source ordering, late inputs, live continuations and publication
ownership still need proof.

The next candidate is the completion/publication of an unchanged scalar write
whose existing Entry remains valid. Check whether a root completion can reuse
that Entry instead of constructing another source context. Keep live-history
continuations, current-Run updates, visibility and boundary obligations until
the compiler and lifecycle checks prove they are unnecessary. This opportunity
is not yet a takeover or a claimed speedup.

## Reproduction and checks

`source_windows` runs the ordinary executor without audit mode. It pauses only
at requested source Run boundaries, exports selected tables, records final
forwarding for selector Eq ports, then finishes the original schedule. These
extra reads are diagnostics, never used to select matches or make decisions.
Its final output equals the ordinary binary for both versions. Build the same
example against each frozen engine and keep separate executable files.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --example source_windows
WINDOWS RAY_PROGRAM WINDOWS_SPEC OUTPUT
python3 benchmarks/cell-publication-windows/test_check.py
python3 benchmarks/cell-publication-windows/check.py ROOT SUM_PROGRAM RAY_PROGRAM ROOT/ray-window-acceptance.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/sum-acceptance.json
python3 benchmarks/cell-publication-windows/measure.py ROOT ROOT/timing CURRENT FASTEST
python3 benchmarks/cell-publication-windows/collect.py ROOT benchmarks/cell-publication-windows/results.json
```

The specification contains sorted `runs`, the seven `tables` used in the source
proof, and `track_roots: "to-hoist"`. Derive windows from nonempty
`boundary-analysis` Runs in each ordinary report; preserve both before/after
boundaries. `ROOT` holds `ray-{fast,current}`, `sum-{fast,current}` ordinary
exports, `windows-{fast,current}` diagnostics, the compatible frozen inputs,
and `ray-profile` from a separate `CELL_CPU_PROFILE=1` run. The rejected
allocation exports live in the sibling `cell-row-reuse` directory. Full JSON
exports, binaries and logs stay in ignored `out/`; compact results retain hashes.

Minimal example compilation, four negative/positive checker tests, unchanged
sum-bits native acceptance and README compile/run/bench repeat 1 pass. The
repeat-1 bench is a smoke check and is excluded from the timing results above.
