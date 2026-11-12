# Cell-owned Entry enumeration, RHS continuation and publication

This measures the actual standalone Cell CPU executor, not native egglog.
The control is `9a0353cf`, the branch immediately before this change; the frozen
final runtime is `8335929d`. Both
binaries use `cell-absorption,view-ports,parallel-publication`; there is no new
runtime toggle. The existing parallel modes remain opt-in.

The previous catalog executions and quiet stack samples showed substantial
serial Entry preparation/publication and mostly parked workers. A new catalog
is not needed to prove this takeover: existing compiled Entry predicates,
point-query plans, input layouts and RHS plans already supply the structure.
The opportunity is to execute those definitions against their existing storage,
without the coordinator expanding every negative Entry or decoding each changed
row again for each maintenance consumer. New cross-Run compositions remain a
separate opportunity; this change does not claim to discover new dominators.

## Connected execution

1. **Published Cell Entry ranges.** The coordinator gives workers the compiled
   pivot, immutable epoch range, Run watermark and existing filter/index views.
   Workers enumerate, check liveness and necessary key support, perform the exact
   query, fill the owned Instance, and continue its existing pure RHS/Unit-row
   preparation. Successful instances return with their actual source witness;
   negative entries never get a source Cursor or per-entry task header. The
   successful instance goes through the existing winner selection and RHS path,
   without a new binding representation or a per-rule intermediate answer vector.

2. **Mixed coverage and deterministic adoption.** Eligibility is per pivot.
   The same rule can combine range answers, old Cell answers and residual joins.
   The exact winner key remains inputs, descending continuation depth, and
   original witness/pivot order. This explicit source key replaces ordinal
   enumeration of negative entries; it is larger and its record size is reported.
   Actual Cursor dispatch happens only for successful range answers. Necessary
   source ordering, delta ownership and residual enumeration remain intact.

3. **Shared Entry publication by the table owner.** The existing table task owns
   warm Entry states together with columns, ranges and neighbor indexes. One
   graph row read feeds all of them. The task updates the actual Entry packet and
   epoch membership, then restores that same state. It does not create a second
   Entry registry, per-producer consumer lists or a separate Entry pool phase.
   Cold/invalidated Entries remain lazy. Earlier pending notifications are
   resolved against the same sealed graph. Immutable row ownership uses `Arc`
   in sparse builds; Cursor roots and their mutable context stay at source.

The preceding terminal Unit ownership mechanism continues to classify exact
keys, invalidate duplicate candidate rows and install adopted indexes on table
workers. This iteration connects owned Entry enumeration and publication to it;
it does not count that previously implemented work as another saving.

## Live obligations and costs

Coverage requires a canonical sealed read view and a compiled point query;
local-witness shortcuts, scoped completion, reverse-selected subsets and tiny
ranges retain their existing paths. A fingerprint can reject only an absent
key; a hit always proceeds to exact query evaluation. Stale/unbuilt support
columns cannot reject anything. Forcing all fingerprints to zero must still
produce identical results.

Original Run visibility and effect order are unchanged. Arbitrary mutable
effects, shared constructor adoption, unions/repair, successful Cursor dispatch
and initial publication/retirement notifications still require the source
path. This is not unrestricted concurrent graph mutation or full CPU saturation.

New costs include range/chunk descriptors, successful answer vectors, atomic
immutable-row ownership, larger winner source keys, table-state task headers,
and sorting changed-row references before epoch insertion. Entry-only work can
also activate a table batch that previously had no index work. Existing clocks
include this cost; no spin/wait timer has been added to ordinary jobs.

`owned_range_*`, `owned_support_*`, `owner_entry_*`, `worker_entry_*` and
`publication.parallel.entry_order_headers` record the takeover and added work.
`owner_entry_*` includes inline table tasks; `worker_entry_*` counts only actual
pool tasks. Byte counters describe cumulative payload capacity, not peak heap
or complete allocator traffic. Moving a decode or a query is not eliminating it;
the results retain global query counts and both publication and Entry work.
Timers in the work-count reports are not the final timing experiment; only the
separate `timing` samples exclude concurrent compilation.

An intermediate implementation missed the old necessary-key support check and
added about 914,000 point queries. That was corrected before final measurement:
workers now borrow the already-current support column, with exact fallback.
The intermediate task also carried an oversized general index view; the final
task borrows only its fingerprint map and support column.

## Validation and reproduction

The 84 relevant compiler/integration tests and 140 runtime unit tests pass.
The new fixture compares every Run snapshot, ordered binding audit and final
graph for 1/2/4 workers against the serial source path, including late inputs,
mutable updates, delete/recreate and union. It asserts real range, RHS-row and
Entry publication coverage. The same fixture passes with
`CELL_CPU_HASH_BITS=0`. All-features and legacy no-default-features compilation
pass, as do the README compile/run/bench commands (fresh output directories).

Frozen sum-bits and Raytrace retain exact final states, all 1,428/16,883 ordered
Run summaries and logical effect counts. The unchanged final-state native
sum-bits validator passes using saved exports whose CPU hash is checked against
the new execution. Raytrace acceptance here is exact differential checking
against the current branch, not an extension of that native proof contract.

Build control and candidate with identical release features and save them as
`out/cell-owner-chain/{control,candidate}-runtime`. Use the frozen program paths
from `out/cell-entry-owned/{sum,ray}-manifest.json`. Each new manifest has
`control1,candidate1,control4,candidate4` lanes, using the matching executable
and worker count with the following flags:

```text
--repair-ports --entry-publications --cell-absorption
--query-workers N --parallel-residuals --parallel-publication
--cell-execution-grain 1
```

Save one four-worker report/state per executable and workload under
`{control,candidate}-{sum,ray}`, then run:

```sh
python3 benchmarks/witness-prefix/measure.py out/cell-owner-chain/sum-manifest.json out/cell-owner-chain/timing-sum --repeat 5 --warmups 1 --timeout 120
python3 benchmarks/witness-prefix/measure.py out/cell-owner-chain/ray-manifest.json out/cell-owner-chain/timing-ray --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-owner-chain/semantic-acceptance.json
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-owner-chain/ray-manifest.json out/cell-owner-chain/timing-ray/samples.json out/cell-owner-chain/profile-control4 --lane control4 --duration 5 --interval-ms 2 --start-delay 0.5
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-owner-chain/ray-manifest.json out/cell-owner-chain/timing-ray/samples.json out/cell-owner-chain/profile-candidate4 --lane candidate4 --duration 5 --interval-ms 2 --start-delay 0.5
python3 benchmarks/cell-owner-chain/check.py out/cell-owner-chain benchmarks/cell-owner-chain/results.json
```

All samples and warmups are retained. `initial-results.json` keeps the first
campaign before correcting aggregate completion-record/error-check counters;
`results.json` measures the frozen final runtime. An executable-permission
failure before candidate launch is retained under `failed-permission-sum` in
the artifact root; that incomplete campaign is not a speed comparison.
Compile jobs are excluded from final
timing. Background macOS Storage Management activity remained active; the
small sample is noisy. Sampling is a separate run with progress logging disabled.
Wall-stack residence is not CPU utilization, inclusive frames overlap, and a
pool-call duration includes useful execution rather than measuring pure wait.

## Measured result

| Inference median | Control 1 worker | Candidate 1 worker | Control 4 workers | Candidate 4 workers |
| --- | ---: | ---: | ---: | ---: |
| sum-bits, five samples | 18.655 ms | 19.115 ms | 22.590 ms | 22.322 ms |
| Raytrace, three samples | 6.304 s | 6.269 s | 5.861 s | 5.825 s |

The four-worker medians improve by 1.19%/0.63%. At one worker, sum-bits regresses
2.46% and Raytrace improves 0.56%. This small, noisy campaign establishes neither
a substantial speedup nor a robust win on both worker counts. Raytrace candidate
four-worker samples are 5.838, 5.825 and 5.732 seconds; all remain in `results.json`.
The initial campaign showed 1.75%/1.08% four-worker improvements and
2.93%/5.03% one-worker regressions. The variation reinforces the limited claim.
Historical fastest results were collected under different load and are not an
apples-to-apples improvement claim here.

| Raytrace work, four workers | Control | Candidate |
| --- | ---: | ---: |
| Per-entry query headers | 1,783,538 | 1,396,673 |
| Additional published Entry rows enumerated in range jobs | 0 | 1,302,283 |
| Successful owned-range instances | 0 | 353,585 |
| Worker support-filter rejections | 0 | 893,105 |
| Total key lookups | 4,021,120 | 4,027,718 |
| Coordinator Entry row decodes | 2,232,211 | 252,541 |
| Publication graph row reads | 2,155,453 | 2,171,680 |
| Entry updates inside table tasks | 0 | 1,950,525 |
| Of those, actually on pool workers | 0 | 1,178,955 |

Range descriptors number 1,568; chunk payload capacity totals 3,973,120 bytes.
Moved Entry state headers total 2,929,920 bytes. Publication additionally sorts
2,073,562 changed-row references, and retains the initial notification and
retirement stream. Thus the decode reduction cannot be reported as an equal
number of eliminated Entry updates. Uncached point execution also replaces
some source witness-cache reads, explaining why global key reads do not fall.
Previously implemented Unit candidates/registrations remain 138,593/79,171;
they are not new gains from this iteration.

The separate five-second quiet stack samples place over 99.8% of main-thread
samples inside inference. Main `matches` inclusive residence falls 27.5% →
22.1%, publication rises 19.0% → 23.1%, and repair stays about 10.1% → 9.8%.
Main condition waits rise 18.4% → 22.5%. Worker condition-wait residence changes
from 82.9–85.1% to 81.7–85.0%; most remains pool idle, not waiting inside a job.
These are partial wall-time windows with sampling overhead, not CPU percentages
or a proof that synchronization primitives themselves became more expensive.

The remaining issue is still substantial source-owned work and Run/batch
boundaries. Query preparation has moved, but shared effects and successful
Cursor/publication processing still serialize progress. Publication also still
queues current notifications before its owner task drains them. This iteration
does not remove that stream or the table ordering cost, and does not claim full
multithread saturation. The measurable takeover is narrower than that goal.
