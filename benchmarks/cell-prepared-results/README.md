# Worker results become the source Cell's result buffer

Scope: **standalone Cell CPU runtime**, not native egglog performance.
Control: `356f0424`. This continues the ownership work in
[the refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md); independent
parked scheduling and concurrent shared effects remain unfinished.

## Opportunity and implemented takeover

The last complete Raytrace prefix execution retained 284,545 temporary witness
arrays, then wrote 262,894 demanded witnesses into source Effects. The actual
constructor results already occupied the instance's value slots, and the source
EffectPlan already knew which operation supplied each result slot. The extra
array and serial re-registration were representational work.

EffectPlan now shares its existing immutable operation-to-result mapping as an
EffectLayout with worker preparation. Source effect owners still use Rc; only
the immutable layout uses Arc, cloned at configuration rather than per instance.
No binding copy, runtime fact graph or per-producer dependency list is added.

A successful worker prefix writes only demanded actual results directly into
that layout. It retains no separate per-constructor witness log. Its existing
preparation position selects a step in the shared constructor program, which
maps directly to the original source operation. This avoids a second instance
field and a source search for the matching operation position. Captured scalars
prepared independently after the prefix stay in their original slots.

At the original source position, union/table readiness still certifies the
prefix. Failed validation clears every speculative constructor value before
allocation or effects. A first witness can still use ordinary exact validation
if it was demanded and retained; otherwise the ordinary source lookup handles
that rare invalidation. No accepted binding is canceled and no committed effect
replays. Foreign-owner results remain actual references, not producer offsets.

Normal Effects takes ownership of the worker array without initializing or
rewriting its existing slots. Later source operations fill remaining slots.
Completion and ordinary publication retain the same ownership transfer already
provided by Effects. Existing joint-history selection is preserved: if it needs
a different layout, an explicit counted import fills that layout. It is not
disabled to improve the new counters. Ordinary history capture still remains
separate where the existing joint path does not apply.

Output layouts can change only during configuration, before the first Run.
Entry configuration refreshes the shared preparation layout there; the CLI
configures Entries before Cell execution to avoid compiling it twice. Each
instance therefore does not repeat a layout-identity check. Source preparation
and publication retain the original Run/effect/visibility boundaries.

## Storage correction from complete execution

The initial full execution removed the source copies but retained 190,424 idle
Raytrace buffers, versus 39,067 in the control. New worker arrays entered the
source pool without replacing the spare the source would normally borrow.
This was additional retention, not saved memory. The initial evidence remains
under ignored `out/cell-prepared-results/initial`.

The final path borrows the original spare even when adopting worker results,
and releases that unused spare. Thus an incoming prepared buffer replaces an
idle cache entry instead of accumulating one on every iteration. Worker arrays
reserve their exact compiled width. Spare releases/bytes, worker allocations,
pool growth and retained capacity are all reported. No removed pool-pop credit
is claimed. A repeated-Run fixture checks replacement rather than accumulation.

## Acceptance and reproduction

The final [results.json](results.json) records byte-identical graph exports and
identical 1,428 / 16,883 ordered Run summaries. Queries, logical graph effects,
repair and source execution boundaries match the control. Native sum-bits
acceptance is `pass` using the saved exports and unchanged reviewed contract.

| Work/storage | sum-bits | Raytrace |
|---|---:|---:|
| Worker arrays adopted into source Effects | 591 | 185,328 |
| Removed source witness writes | 1,107 | 262,894 |
| Removed intermediate writes across worker + source | 2,022 | 483,504 |
| Worker result-array allocations, before → after | 945 → 591 | 284,545 → 185,328 |
| Source result-buffer growths, before → after | 128 → 145 | 39,489 → 23,604 |
| Combined growth events, before → after | 1,073 → 736 | 324,034 → 208,932 |
| Initializations moved from source to worker | 1,621 | 326,468 |
| Worker layout checks | 2,022 | 483,504 |
| Worker preparation-position writes | 945 | 284,545 |
| Source spare buffers released | 534 | 161,951 |
| Explicit joint-history conversions in these workloads | 0 | 0 |
| Final pooled buffer count, unchanged | 121 | 39,067 |
| Final pooled capacity bytes, before → after | 9,520 → 6,096 | 2,742,768 → 698,240 |
| Net saved equally weighted work | -1,733 | -516,722 |

The combined growth count covers these two result-buffer sites, not whole-process
allocator calls. Final-layout worker arrays can be wider than old temporary
witness arrays: their requested capacity totals grow 18,880 → 25,936 bytes and
5,083,984 → 5,223,488 bytes. Source buffer capacity growth falls 9,520 → 8,352
and 2,742,768 → 1,548,320 bytes. The spare releases above cost source work;
they are not hidden behind the removed temporary arrays. Source buffer-take
counts remain unchanged. The initial prototype's extra retention is not shipped.

Instance and RHS-owner headers remain 152 / 456 bytes. Execution-plan payload
grows 487,784 → 492,440 and 2,419,688 → 2,424,344 bytes. Eagerly shared plans
also grow operation-descriptor storage 3,985 → 6,425 and 141,705 → 143,665
bytes. Shared layout allocations contain 9,120 / 11,376 bytes of headers and
reference counts; their slot payload is already included in descriptor storage.
Source EffectPlan headers are smaller after moving that layout, so the new
layout component alone is not a net memory delta. There is no per-instance Arc
clone. New worker and source counters add nine u64 fields per corresponding
counter set. These storage components are separate from the operation score.
Eagerly compiled joint-plan storage grows 1,560 → 1,952 / 2,040 → 2,328 bytes,
and registration storage grows 6,184 → 8,144 / 8,680 → 10,120 bytes. The plan
cache headers remain 4,656 bytes in both workloads.

The check script verifies conservation of required result initialization:
source initializations plus worker initializations equal the control. It also
verifies that the deleted intermediate writes equal consumed prefix operations.
The work score remains negative: new checks, ownership moves and spare releases
are charged, and the equal-weight ledger is not a timing model. Existing source
slot-probe counters also decrease, but are not separately weighted in that
historical ledger. This is an implemented ownership/transfer reduction, not a
claim of net throughput improvement.

128 runtime and 97 compiler/integration checks pass, including forced hash/Sieve
collisions. All-feature and no-default-feature builds pass. The README Cargo
compile/run commands and repeat-1 bench smoke are required for this final build.
All three README checks passed with the final source; the feature executable
was frozen before those default builds.

`check.py` compares full final states, ordered Run summaries, original graph
operations, queries, repair, Entry scheduling and execution boundaries. The
reviewed native sum-bits choice validator is unchanged. Raytrace remains
regression evidence against the control, not a new native acceptance contract.

Targeted checks cover actual foreign results, partial prefixes, first misses,
union/deletion invalidation, the same allocation through ordinary publication,
permuted joint-history import, both configuration orders, later independent
scalar preparation and repeated-Run buffer reuse. Existing residual, winner,
visibility, completion and failure checks remain required.

The work reader accepts `cell-constructor-preparation/v5`, charging result-layout
checks, worker initialization, progress writes, source ownership moves, spare
releases and joint imports. Source initialization counts exclude arrays already
initialized by workers, so these writes count once. Older reports remain readable;
missing current counters fail validation. Equal-weight work is uncalibrated.
No new timing campaign is part of this change; the previous five-change
checkpoint found no overall speedup.

Use fresh directories and the same frozen programs/native exports as the
control. Freeze the feature runtime before README default builds. Raw evidence
and logs live under ignored `out/cell-prepared-results`.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test entry_publications --test joint_results --test parallel_residuals --test query_workers --test ripsat_completion --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-prepared-results/check.py ROOT PRIOR RESULTS.json
```
