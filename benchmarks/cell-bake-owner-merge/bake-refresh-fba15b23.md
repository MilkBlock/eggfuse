# Merge the retired-prefix iteration from the branch containing d0d8ee33

Merge `451058f3` integrates the whole committed `codex/cell-parallel-admission`
branch through `fba15b23` into `codex/cell-result-routing`. Both `d0d8ee33` and
`fba15b23` are ancestors of the merge. The four new commits follow the previously
merged `89714c74`; this does not select the similarly named structural-compression
branch or include the source worktree's uncommitted source-routing experiment.

The merge adds compiled, address-identical prefix retirement; retirement-event
selection instead of repeated component scans; and replacement of installed
short paths by longer observed paths when the 256-path Bake catalog is full.
It also includes the source-directory audit and reproducible experiment reports.

One integration fix was necessary: `active_rhs` only exists with `sparse-cells`.
The retired-prefix entrypoint now conditionally compiles that check. Its check
for pending unions, dirty facts, frozen readers and active ownership work remains
in force, and sparse-cell execution still checks the active RHS.

## What the actual executions suggest

The incoming [event experiment](retired-prefix-events.md) reduces component
visits from 1,074,658 to 263 while preserving all 129 suffix retirements. This is
a work-count result in the standalone Cell runtime, not a timing result here.
The compiler supplies the legal surviving shape and checks its future append
language. Actual source retirement selects which instances need attention.

The [capacity fix](direct-prefix-growth.md) learns from the last installed
catalog's audited executions: 108 installed paths can grow without increasing
the maximal-path count. Nevertheless, its Graph saving is only 6,176 bytes and
all 2,177 completed source records remain. Larger logical Cells alone do not
remove the old addressing responsibilities.

For our parallel execution work, the useful next target is a composed Cell
whose checked storage specialization supplies both result addressing and source
lifecycle, so completion can discharge the corresponding old source record.
This is narrower than assigning exclusive physical storage to every Cell:
the [audit](source-directory-audit.md) finds 1,320 of 1,364 logical components
share physical owners with outside sources, and structural shape plus native
code does not uniquely identify their storage layouts. Use views of existing
segments and actual returned witnesses; do not copy shared prefixes or add a
third routing directory beside the current two.

The obligations that remain live are old FactRef/source addressing, native Eq
routes, actual foreign constructor results, per-source epochs and recipe depth,
deletion/recreation, residual matching, source ordering and Run visibility.
Observed equal layouts or frequent rule paths do not prove these obligations
redundant. The acceptance target for a future takeover is removal of an old
lookup/record/handoff within compiler-proved coverage, with new dispatch and
storage charged. This merge does not implement that next takeover or move more
RHS work to workers.

## Checks and measurement scope

Job 363 passes 72 ownership, 19 compiler, 13 witness, three Bake selector and
234 runtime tests. Its no-default compile exposed the missing feature guard.
After the fix, job 365 passes default and no-default compiles and reruns both the
retirement/recreation integration test and the future-append-language test.

Job 367 freezes the merge and uses the hash-checked `cf439fae` control from the
preceding experiment. `24bc40ef`, the immediate pre-merge HEAD, adds only that
experiment's Markdown/JSON report; its runtime sources equal `cf439fae`.
Ordinary sum-bits and Raytrace final states, all 1,428/16,883 Run summaries and
logical effect counts agree. The reviewed native sum-bits choice-diagnosis
entrypoint returns `pass`. The unchanged original-source 408-witness catalog
also preserves its final state, 1,428 Run summaries and effects. Recorded work
dictionaries agree on all three inputs. Raytrace and the learned catalog are
differential checks, not extensions of the native contract.

The ordinary four-worker runtime does not invoke `compact_retired_prefixes`.
These measurements check merge overhead, including plan preparation; they do
not measure the optional retirement API's benefit. Its lifecycle behavior is
exercised by the dedicated tests and the separately identified incoming
experiments. New full per-Run graph exports are not claimed for this merge.

Job 368 runs the entire control lane before the entire candidate lane. Each
workload has one warmup; sum-bits and the witness catalog have five measured
samples, Raytrace three. All 76 process-boundary guards pass.

| Workload | Control inference | Merge inference | Change |
| --- | ---: | ---: | ---: |
| sum-bits | 20.940 ms | 21.163 ms | +1.07% |
| Raytrace | 4.749769 s | 4.971150 s | +4.66% |
| original-source 408-witness catalog | 22.079 ms | 23.405 ms | +6.01% |

This is a regression signal, not an accepted speedup. Raytrace candidate samples
are 4.689434, 4.971150 and 5.007587 s: the first is faster than the control
median, while the next two are slower. The later samples rise across search,
RHS, repair and query-update phases. Work counts are unchanged; every new
retired-prefix counter is zero. The disabled hook is still reached from 102,635
source retirements, but this observation does not attribute the whole slowdown
to that hook. Neither machine drift nor binary/layout effects have been isolated.
No repeat is used to replace this result.

Median load times are 68.332 to 65.090 ms (sum-bits), 355.688 to 371.443 ms
(Raytrace), and 100.625 to 100.010 ms (witness catalog). This does not establish
that the new prefix compiler is a general loading bottleneck. Optional prefix
retirement stays opt-in; the merge supplies checked mechanisms and observations,
not a claim that larger Cells already accelerate the parallel runtime.

Timing and binary identities are recorded in `bake-refresh-fba15b23.json`.
Large artifacts reside on the external disk through
`out/cell-bake-routing-refresh/fba15b23` in worktree 3063. The existing shared
external build cache and machine-wide job queue are used throughout.
