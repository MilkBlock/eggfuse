# Rule-owned worker results

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
no answers. No speedup is claimed before the fixed sequential comparison.

The small-selected-ranges fixture exercises several rules in the same completion
event, checks the new path is used and compares every Run snapshot and ordered
binding against serial execution. The remaining query/residual tests cover
late input, mutation, deletion/recreation and union-enabled matches. The ordinary
sum-bits/Raytrace run must retain exact accepted final states, source Run summaries
and effects, plus the reviewed native sum-bits choice proof.

Reproduction uses the shared job queue and fresh output roots:

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
