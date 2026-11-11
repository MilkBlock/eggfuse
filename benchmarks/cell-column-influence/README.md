# Compile Cell field influence into summary publication

Control: `50316626`. Scope: **standalone Cell CPU**, not native egglog.
This removes actual summary maintenance. It does not establish elapsed-time
improvement, global egraph sparsity or the requested 2x speedup.

## Opportunity from actual execution

The last complete Raytrace record contains 8,380,801 Sieve summary-row updates;
the normal checkpoint also attributes substantial time to index/publication
work. `Columns::put` already compares old and new field fingerprints, but its
notification discarded which fields changed. Sieve consequently retried all
built summaries of the table even if a summary read only unchanged fields.

The shared Cell query already determines a summary's output columns and the
receiving columns of every child condition. `Spec::new` now compiles their union
into a field-influence mask. Summaries of the same table with the same mask
share one static influence group. Index publication carries its existing field
comparison forward in the **same change stream**. One non-overlapping mask
test skips every built member of a group without visiting its summary state,
including guard evaluation, projection construction, support insertion and
attempted propagation. This replaces those operations rather than adding a
new cache, fact graph or per-producer consumer list. It is compiler-derived
maintenance scope, not an expanded Ripsat catalog or a cross-Run block switch.

## Why a skipped update remains complete

When output and guard fingerprints are unchanged, this row presents exactly the
same input to that summary. If a child condition acquires support, the existing
static parent wiring still revisits current matching rows in the propagation
queue, including rows skipped by the field test. A newly indexed witness always
carries the all-fields sentinel, so empty projections and new membership are
not omitted. Each group counts its existing built members; `ensure` increments
that count once, and invalidation clears it with the summary states. Hidden/retired rows retain existing removal behavior; recreation
is a new index membership. Ordinary matching, visibility, delta ownership and
source Run ordering remain authoritative.

These are masks of **fingerprint reads**, not proof that exact values are equal.
Exact values and read leases keep their previous handling. Columns 63 and above
share the high bit; collisions can retain extra maintenance, never omit a
relevant field. Full-width masks conservatively behave like the all-fields
sentinel. No schema-width restriction is added.

## Measured work and costs

Both frozen diagnostics use four query workers, grain 64, repair ports, Entry
publication and Cell absorption. Entry reverse selection remains off on both.

| Summary-row admission calls | Before | After | Omitted | New group checks |
|---|---:|---:|---:|---:|
| sum-bits | 30,833 | 29,067 | 1,766 | 6,026 |
| Raytrace first 1,280 Runs | 1,822,520 | 1,802,443 | 20,077 | 255,996 |
| Complete Raytrace | 8,380,801 | 6,983,829 | 1,396,972 | 2,185,417 |

Complete Raytrace omits about 16.7% of these calls. Added support keys remain
1,100,851 and dependency-row visits remain 365,850. All other Sieve work,
ordinary queries, Free Join admission, Entry/index publication and actual graph
effects agree. Omitted calls are not omitted rule applications or mutations.

Costs remain explicit: one `u64` mask payload per summary, shared group headers
(including the built-member count), one additional `u64` payload per transient
change record, field-bit accumulation while comparing fingerprints, and one
mask test per group with built members considered. The 1,163 summaries form
374 groups; masks plus live group headers add 24,264 bytes on this target.
Existing member IDs remain shared plan storage. Spare capacities and allocator
headers are not included. Eligible groups retain ordinary member checks.
The change stream is still sorted and allocated by its existing owner. Payload
bytes do not measure allocator requests or peak RSS, and a saved admission is
not a saved cycle count. An index is still maintained even when Sieve skips its
notification. These limits matter for the next normal-binary checkpoint.

Bake work accounting now charges `column_checks` as well as remaining summary
admissions. `unchanged_column_rows` is an outcome, not an additional reward.
A versioned report field distinguishes historical reports from new reports with
missing counters; missing and unknown new contracts fail closed. Equal operation
weights remain a coarse work comparison, not a latency prediction.
The equally weighted summary-update-plus-field-check subtotal actually rises
by 788,445 on full Raytrace: 1,396,972 removed admissions versus 2,185,417 new
group checks. This prevents claiming a net work-credit win from the omission
counter alone. The bit test and full summary admission have different costs;
only the scheduled normal-binary checkpoint can resolve the time tradeoff.

## Validation

- 101 runtime unit tests, five Bake-credit tests and 31 selected compiler
  integration tests pass. New
  tests compare scoped publication with full publication at each change,
  including irrelevant scalar changes, relevant output changes, late child
  support and initially empty projections. Wide-column collisions retain work; invalidation and re-preparation restore
  group counts. Credit tests charge new checks, avoid double rewards and reject
  missing/unknown accounting.
  Existing integrations cover union, deletion/recreation, source Run snapshots,
  ordered matches, residual enumeration and serial/four-worker execution.
- sum-bits, Raytrace prefix and complete Raytrace have byte-identical final
  states and identical ordered Run fields (excluding diagnostic timing), with
  identical committed effects. Full Raytrace is relative evidence against the
  frozen current-branch control, not independent native acceptance.
- The unchanged sum-bits `choice_diagnosis.py` accepts the candidate with
  `pass` / exit 0. No proof rules or exclusions change.
- No-default-feature compilation and fresh README compile/run/bench (repeat 1)
  pass. These are command smoke checks, not a new throughput checkpoint.

## Reproduction

Freeze the current-branch control before building. Use the same `cell-fixed-reads`
programs and new output paths:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,cell-entry-reverse,view-ports --example query_prefix
cp target/release/examples/query_prefix ROOT/runtime-grouped
ROOT/runtime-grouped SUM_PROGRAM ROOT/sum-grouped 2000 4 64 canonical --repair-ports --entry-publications --cell-absorption
ROOT/runtime-grouped RAY_PROGRAM ROOT/ray1280-grouped 1280 4 64 canonical --repair-ports --entry-publications --cell-absorption
ROOT/runtime-grouped RAY_PROGRAM ROOT/ray-full-grouped 20000 4 64 canonical --repair-ports --entry-publications --cell-absorption
CONTROL RAY_PROGRAM ROOT/ray-control 20000 4 64 canonical --repair-ports --entry-publications --cell-absorption
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-column-influence/collect.py ROOT RESULTS.json
```

Prepare semantic inputs under the existing sum-bits contract, substituting the
candidate export for `run-values/state.json`. The collector binds the frozen
control and previous short observations by hashes. It reads saved results and
never executes or times a workload. Raw data stay in ignored `out/`.
