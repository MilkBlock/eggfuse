# Select Cell Entries from existing joined support

Control: `217e3285`. Scope: **standalone Cell CPU**, sum-bits and the first
1,280 Raytrace Runs. This is an opt-in work experiment, not a native egglog
optimization, full-Raytrace validation, speed result or proof of global sparsity.

## Opportunity and proof

The [last actual-execution census](../cell-entry-admission/README.md) found little
identical whole-batch reuse. It does not justify another full-batch cache. The
existing Sieve already maintains typed, joined necessary conditions from Cell
queries. A small joined support can instead drive enumeration of a large Entry
delta, avoiding visits to rows that the same condition would reject.

After the existing Free Join reverse route and optional frontiers decline a
batch, the new route chooses its smallest built one-column Sieve support.
The receiving column comes from the same compiled query wiring. It looks up
support fingerprints in an **already built, current** source-column index;
it never creates an index, retained frontier, binding copy or consumer list.
This differs from the older reverse route, which enumerates unjoined follower
table keys. No scheduled cross-Run block switch or new Ripsat completion is
claimed here. There is no new Bake credit.

Each source row has one fingerprint in that column and each support key is
unique, so the selected buckets are disjoint and include every row that could
pass this Sieve condition. Fingerprint collisions only add candidates: ordinary
exact matching still proves the query. Each selected witness is rechecked
against the existing Entry predicate, visibility and consumer watermark.
The same candidate vector is sorted by `(epoch, witness)`, restoring source
order, then consumed directly. Exactly the selected necessary guard is omitted
from subsequent Sieve checks; all other guards and query obligations remain.

Only global completion is admitted. Unbuilt/stale indexes, wider projections,
large support sets and over-budget buckets retain the original route. Support
is capped at 4,096 keys; key probes plus copied references must fit
`max(8, 4 * support_keys)`, and the delta must exceed that budget. This cap is an
experimental admission policy, not a proof that the route is profitable.

## Work and new costs

Same binary, option off/on, four query workers, grain 64, repair ports, Entry
publication and Cell absorption enabled:

| Observation | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Sieve probes before | 12,873 | 573,074 |
| Sieve probes after | 10,885 | 483,921 |
| Selection attempts | 4,927 | 12,321 |
| Guard descriptors inspected | 2,231 | 8,567 |
| Epoch bins inspected | 1,586 | 7,827 |
| Support-key lookups | 186 | 11,216 |
| Candidate references copied, including failed attempts | 246 | 13,400 |
| Sum of candidate buffer capacities, bytes | 9,216 | 440,064 |
| Over-budget fallbacks | 4 | 853 |
| Selected batches / empty selected batches | 59 / 20 | 446 / 367 |
| Selected rows | 101 | 1,323 |
| Sort comparisons | 104 | 8,238 |
| Free Join entry probes, unchanged | 17,430 | 1,218,004 |

Probe reduction is about 15.4% / 15.6%, **not elapsed-time improvement**. The
selected-row guard omissions are part of this reduction, not extra savings.
Most avoided visits would already fail Sieve, so downstream Free Join work
does not decrease. Query index construction/storage, Sieve support maintenance,
Entry maintenance and actual graph effects are unchanged.

The implementation adds fourteen `u64` counters and an enable flag to Sieve
when compiled, plus temporary candidate vectors while enabled. Capacity bytes
sum the final capacities of those vectors, including failed attempts; they are
neither allocation-call counts nor peak memory. Entry membership is checked
once during selection and again on delivery for the selected rows. Ordering,
guard selection, fallbacks and these reads remain costs. Raytrace's 853 failed
budget attempts versus 446 selections warrant particular attention before
expanding scope. Worker scratch allocation and distribution can vary with
scheduling; no allocator reduction is claimed.

## Validation

- 99 runtime unit tests and 31 selected compiler integration tests pass.
  The new native-checked fixture compares every source Run snapshot and ordered
  input audit, in serial and four-worker modes, through late input, union,
  deletion and recreation. The unit test covers zero-bit collisions, stale and
  unbuilt columns, bounded copying and current late-input membership.
- Short off/on exports have byte-identical states, complete ordered logical and
  executed Run signatures, and identical actual graph effects. The off control
  also reproduces the saved current-branch observations. Raytrace evidence is
  relative and limited to this prefix.
- The unchanged sum-bits `choice_diagnosis.py` returns `pass` / exit 0 against
  the candidate export. No exclusions or proof rules are broadened.
- Minimal and combined-feature compilation plus README compile/run/bench
  (repeat 1) are smoke checks only. Throughput remains for the scheduled
  checkpoint; this experiment remains disabled by default.

## Reproduction

Use the frozen `cell-fixed-reads` programs, saved prior observations and fresh
output directories. Freeze the diagnostic binary before other builds:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,cell-entry-reverse,view-ports --example query_prefix
cp target/release/examples/query_prefix ROOT/runtime-final
ROOT/runtime-final SUM_PROGRAM ROOT/sum-final-off 2000 4 64 canonical --repair-ports --entry-publications --cell-absorption
ROOT/runtime-final SUM_PROGRAM ROOT/sum-final-on 2000 4 64 canonical --repair-ports --entry-publications --cell-absorption --cell-entry-reverse
ROOT/runtime-final RAY_PROGRAM ROOT/ray1280-final-off 1280 4 64 canonical --repair-ports --entry-publications --cell-absorption
ROOT/runtime-final RAY_PROGRAM ROOT/ray1280-final-on 1280 4 64 canonical --repair-ports --entry-publications --cell-absorption --cell-entry-reverse
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-entry-reverse/collect.py ROOT RESULTS.json
```

Prepare semantic inputs per the existing [contract](../marker-handoff/choice-diagnosis.md),
using the candidate sum export as `run-values/state.json`. `collect.py` binds
the controls, states, ordered Runs and acceptance by hashes and never times a
workload. Raw outputs/binaries remain ignored in `out/cell-entry-reverse`.
