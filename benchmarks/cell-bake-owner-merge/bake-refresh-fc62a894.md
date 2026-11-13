# Refresh from the branch containing d0d8ee33

Merge `4b7a9a4d` integrates the whole committed
`codex/cell-parallel-admission` branch through `fc62a894` into
`codex/cell-result-routing`. Both `d0d8ee33` and `fc62a894` are ancestors.
The source worktree's later uncommitted takeover-observer work is untouched.
This is not a merge from the similarly named structural-compression branch.

The two incoming commits colocate ownership routing in completed source
records and reuse retired internal component positions after a settled
boundary. Stable source IDs are never recycled. A frozen reader, active RHS,
pending ownership dispatch, dirty work or pending union prevents early reuse;
old source ports must stay expired when a component position gets a new owner.

Integration preserves our prepared RHS witnesses before source-instance
allocation. It also changes the worker's prepared-witness reader to the shared
`FrameRead` interface. Keeping the old direct directory access failed the
first parallel compilation; that missing adaptation is fixed in the merge.
The duplicate feature guard conflict is resolved without weakening the guard.

## Coverage and remaining obligations

Source-record routing applies to the `sparse-cells,storage-metrics`
representation. Ordinary four-worker builds retain the legacy route directory;
their measurements below exercise component reuse, not completed-source
storage takeover. The incoming [source-routing experiment](source-routing.md)
separately charges the larger source records and fallback routes. Its memory
saving is not attributed to our ordinary runtime lane.

Jobs 394 and 396 pass 672 test executions across the parallel and storage
configurations: 217 and 235 runtime tests, 147 parallel integration tests, and
73 storage ownership tests. No-default-features compilation passes. The first
integration command omitted the compiler's `iterative-bake` feature required
by existing transfer-audit tests; the corrected command passes. The saved test
manifest records the final commands and statuses.

Job 399 freezes the merged runtime and reuses the hash-checked `451058f3`
control. The immediate pre-merge HEAD is `219cf8c6`; its runtime and compiler
library sources are identical to that frozen control. Intervening changes are
catalog examples, experiment tools and evidence, not the measured runtime.

Ordinary sum-bits and Raytrace preserve exact final states, all 1,428 and
16,883 source Run summaries, and logical effect counts. The reviewed native
sum-bits choice diagnosis returns `pass`. The unchanged original-source
408-witness catalog also preserves its final state, 1,428 Run summaries and
effects, exercising prepared witness paths after the interface merge.
Raytrace and the learned catalog are differential checks; they do not extend
the native contract. Full per-Run graph equivalence is not claimed here.

## Actual work in the ordinary four-worker runtime

| Counter | Before | Merge |
| --- | ---: | ---: |
| Raytrace components created | 587,058 | 587,058 |
| Retired component slots reused | 0 | 102,712 |
| Final reserved component positions | 587,058 | 484,346 |
| Lifetime-directory capacity bytes | 8,388,608 | 3,874,816 |
| Lifetime-directory growth events | 19 | 3,791 |
| Dispatch comparisons | 913,642 | 924,120 |
| Key lookups | 4,332,972 | 4,332,972 |

The old position count follows from its monotonic, non-reusing allocator and
the observed creation count; the new count is exported directly. This is one
directory's capacity, not total Graph memory or RSS. The growth policy trades
less spare storage for more allocator calls. No elapsed cost is inferred from
the call count alone. Sum-bits reuses 511 positions, and the witness catalog
reuses 326; their query counts remain 14,653 and 14,373 respectively.

## Sequential timing

Job 400 finishes all control workloads before any candidate workload. Each
workload has one warmup; sum-bits and the witness catalog have five samples,
Raytrace three. All 76 process-boundary guards pass. No sample is removed and
no retry replaces this result.

| Inference median | Before | Merge | Change |
| --- | ---: | ---: | ---: |
| sum-bits | 21.205 ms | 21.511 ms | +1.45% |
| Raytrace | 4.724614 s | 4.714634 s | -0.21% |
| Original-source 408-witness catalog | 21.571 ms | 23.178 ms | +7.45% |

Ordinary Raytrace is approximately unchanged in this short trial. Its whole
process median is 7.147801 to 7.187073 seconds (+0.55%), so the small inference
decrease is not an end-to-end speedup. The learned catalog has a regression
signal that must not be hidden by the ordinary result.

The learned catalog's saved phase medians rise in search (11.450 to 12.301 ms),
RHS (5.367 to 5.714 ms), query update (3.072 to 3.315 ms) and repair (1.175 to
1.280 ms). Its prepared source/worker work, result handling, composition work
and key-query counts are identical. Prepared worker witness reuse still makes
268 hits, including 19 proved hits, with 1,511 route probes. Directory growth
rises from 10 to 20 events and dispatch comparisons from 3,655 to 3,682.
These observations do not isolate the regression to witness lookup, component
reuse or allocation. Group order, machine drift and binary effects remain
unseparated. The merge is not presented as a general speed improvement.

## What this changes in the optimization plan

The useful structural lesson is to make existing Cell storage discharge an
old responsibility: source lookup and lifetime now share one record in the
covered representation. Larger logical templates alone could not remove the
second directory. Likewise, safe position reuse needs the existing source
identity and read-epoch boundaries; it cannot treat equal template shapes as
proof that an old reference is valid.

Our last actual Raytrace catalog already supplies 2,127 observed witness
recipes, including 1,041 with already active receiver rules. The next takeover
should use these actual result addresses to replace proven constructor queries,
while avoiding new Entry/result-capture activation. They are candidates, not
2,127 saved queries. Typed key evidence, actual foreign constructor results,
source liveness, residual matching, ordered effects and Run visibility remain
mandatory. New route selection and storage must be charged. This merge itself
does not remove a query or expand worker mutation scope.

Builds and experiments use the external cache and the shared local queue.
Artifacts, exact commands, identities and retained timing samples live under
worktree 3063's `out/cell-bake-routing-refresh/fc62a894`; the compact manifest
is `bake-refresh-fc62a894.json`.
