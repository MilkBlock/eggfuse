# Rule-owned worker results

**Rejected experiment `bcb5fcb6`; the ordinary runtime has been restored.**
The design below describes that frozen experiment, not the default path.

The preceding actual standalone Cell CPU audit (`905350d8`) found 366,386
Raytrace answers returned in mixed-rule range arrays. They account for 70.5% of
the remaining coordinator row routing, but not necessarily that share of time.
Compiled Cell origins already name the destination rule. No new catalog or
runtime binding graph is needed to prove result-buffer ownership.

Pooled range workers now choose a rule-owned output array once per input range.
Queries append directly into that array while retaining the original Cell-local
job order and scratch. The same rule may occur again later in the task: its
results append to the existing owner, retaining their relative source order.
Each array retains the original compiled origin spans and actual Instance values.
When the rule's accumulated work reaches the existing finishing grain, the
coordinator transfers the whole array to the finishing worker. It does not open
each answer to resolve its rule and append the Instance again.

Inline execution keeps one mixed array. Small pooled rule outputs keep the
ordinary row path until the rule qualifies for worker finishing. The change
introduces neither a new task barrier nor a reordered query schedule; the
existing rule dependency count releases winner selection after all contributors.
Source/error ordering, delta ownership, coverage, actual foreign witnesses and
Run visibility remain authoritative. This is within-Run transport, not additional
cross-Run completion or evidence that a larger Cell is saturated.

The tradeoff is additional worker output arrays for mixed tasks. Existing answer
buffer allocation and capacity counters include those arrays. New counters charge
range owner probes, nonempty result buffers and spilled group headers. Header
heap contains the inline origin capacity also described by the span capacity
counter; those two capacities must not be blindly added. `completion_event_bytes`
records the changed fixed event size. Empty owners are dropped after a range with
no answers. These work counters do not establish a speedup.

The small-selected-ranges fixture exercises several rules in the same completion
event, checks the new path is used and compares every Run snapshot and ordered
binding against serial execution. The remaining query/residual tests cover
late input, mutation, deletion/recreation and union-enabled matches. The ordinary
sum-bits/Raytrace run must retain exact accepted final states, source Run summaries
and effects, plus the reviewed native sum-bits choice proof.

Reproduction requires an isolated checkout of `bcb5fcb6`, the shared job queue
and fresh output roots:

```sh
eggfuse-job run --kind compute -- python3 benchmarks/cell-query-fragments/routing.py CONTROL TARGET OUTPUT --accepted-commit 905350d8
eggfuse-job run --kind timing -- python3 benchmarks/raytrace-parallel/quick.py CONTROL OUTPUT/candidate OUTPUT/timing OUTPUT/timing.json
```

`CONTROL` is the preceding audit's frozen `candidate` directory, with ordinary
`cell-absorption,view-ports,parallel-publication` features and four workers. Its
runtime is unchanged by documentation commit `5d1fa398`. The candidate also
integrates `004fd672`, whose compaction fix is gated on `storage-metrics`, absent
from both ordinary lanes. The fixed timing policy completes all five sum-bits
and three Raytrace control samples before any candidate samples, with one warmup
per group. Retain every sample and reject the trial on guard interference.

## Work, validation and decision

The candidate passes 14 query tests, six residual tests, 212 runtime unit tests
and legacy compilation (compute jobs 205 and 207). The frozen executions (job 208)
preserve both final states, all 1,428 / 16,883 source Run summaries and logical
effects. The reviewed native sum-bits contract passes with the fresh CPU hash.

| Work | sum-bits control → candidate | Raytrace control → candidate |
| --- | ---: | ---: |
| Coordinator row routing | 4,082 → 4,082 | 519,989 → 265,645 |
| Fragment rows handed to workers | 0 → 0 | 1,034,558 → 1,288,902 |
| Fallback rows gathered again | 0 → 0 | 233,598 → 85,923 |
| Answer-buffer allocation events | 1,119 → 1,181 | 202,137 → 216,331 |
| Original answer-buffer capacity | 1,272,936 → 1,305,192 B | 363,177,024 → 359,265,312 B |
| Added spilled owner-group headers | 18,144 B | 1,763,552 B |

Raytrace eliminates 48.9% of remaining coordinator row routing, but adds 7.0%
answer-buffer allocation events. Sum-bits obtains no routing reduction. Capacity
counters accumulate across execution; they are not retained heap or peak RSS.
The fixed event grows from 2,312 to 2,384 bytes in both cases.

Timing job 210 completed all fixed control groups before all candidate groups;
all 48 boundary guards were clear. Every sample and its semantic checks is retained.

| Inference median | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| sum-bits | 25.912 ms | 29.057 ms | +12.14% |
| Raytrace | 4.971804 s | 4.964670 s | -0.14% |

**The speed gate fails.** The small Raytrace difference is within the observed
sample spread and does not establish a speedup. The grouped trial does not prove
the added allocations caused the sum-bits difference. No samples are discarded
or replaced. The default implementation is restored byte-for-byte to the runtime
tree at `0f290893`, retaining the integrated Bake compaction fix. All six residual
and 14 query tests pass again after restoration.

`rule-owner-results.json` records full timing samples, hashes, queue metadata,
state/Run checks and work counts. This experiment and the earlier fragment trial
both reduce coordinator routing without an established end-to-end improvement.
They do not justify further expansion based on routing coverage alone. The next
decision needs current stack evidence for actual serial work; the saved ordinary
Raytrace run spends about 1.94 s in RHS, 1.70 s in search, 0.90 s in query update
and 0.44 s in repair. Those are whole-phase durations, not times attributed to
result routing and not CPU utilization percentages.

## Restored-path stack evidence

A separate queued diagnostic uses the unchanged frozen control executable after
timing, with no progress logging. Sampling starts one second after launch and
runs for two seconds at a two-millisecond requested interval. The complete run
again matches the accepted Raytrace state, Run summaries and effects.

641 of the main thread's 642 samples are within inference; 154 are in condition
variable wait. The four workers respectively have 469, 478, 493 and 512 condition
wait samples out of 642 each (73.1–79.8%). These are bounded wall-residence samples,
not whole-run CPU utilization or proof that all waits can be removed.

Selected main-thread inclusive counts are 135 in `publish_finished_tables`,
108 in `Workers::finish_queries`, 72 in `repair_selected`, 64 in
`resolve_cell_boundary`, 48 in `activate_fields` and 41 in `replace_row_edges`.
These nested counts overlap and cannot be summed. Inlining also limits attribution.
The result supports inspecting publication and shared-state completion barriers;
it does not identify row-result routing as the dominant serial work.

`rule-owner-profile.json` records hashes, provenance, the bounded sample and
semantic checks. Raw stacks remain in the ignored experiment directory. The
source field in that summary identifies `905350d8`; the original profile helper's
`reference_commit` is the manifest's older semantic-comparison baseline.

```sh
eggfuse-job run --kind compute -- python3 benchmarks/cell-rhs-boundaries/profile.py CONTROL OUTPUT/restored-profile --delay 1 --duration 2
```
