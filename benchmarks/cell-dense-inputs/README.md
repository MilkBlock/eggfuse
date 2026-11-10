# Dense Cell input storage: rejected production candidate

Baseline: `560faaf7`. The production kernel remains unchanged. This directory
retains a reproducible experiment and its allocation results, rather than
adding another representation to the active execution path. These measurements
cover the standalone Cell CPU, not native egglog. They establish neither a
throughput regression nor a speedup: allocator instrumentation is unsuitable
for either conclusion.

## Opportunity and remaining obligations

The [actual Raytrace query profile](../cell-fixed-reads/profile.md) attributes
44.05% of query time and 51.25% of successful bindings to fifteen `Expr-size`
writers. A successful binding is not necessarily a committed change. The
existing single-write path already avoids many RHS frames; those cannot be
counted as new savings.

All 582 rules in the current source have consecutive input slots. Their shared
typed layout proves that each instance need not store the same input slot IDs.
The experiment derives that proof once, writes query results directly into a
value array, and moves the same owned instance through winner selection, RHS
and retained Cell storage. It preserves original logical slot addresses and
map ordering. Unordered/nonconsecutive input layouts keep the sparse map.

This proof discharges repeated input-ID storage only. No source-Run block
switch, repeated query, history validity check or publication is removed.
Mutable values, later input arrivals, union-enabled matches, actual witnesses,
delta ownership, retirement and visibility keep their existing obligations.
There is no new runtime fact graph or producer subscriber list.

## Why it was not admitted

An initial dense vector converted to a sparse pair vector at its first RHS
hole. It removed one third of the measured query-fragment payload bytes, but
added 4,589 allocation calls on sum-bits and 19,140 on the Raytrace prefix.
That is the cost of moving to another representation later in the same Cell.

The retained patch uses optional slots to keep small SSA gaps in the existing
array. A span is admitted only when its element storage costs no more than
the equivalent occupied pairs; wide gaps still use sparse storage. Expansion
reserves the complete destination span in one operation. Serialization and
winner comparison use logical slot/value order, independent of representation.
The measured slot element is 16 bytes, versus 24 for the original pair. An
instance header grows from 120 to 128 bytes; a winner from 208 to 216 bytes.

| Execute-only allocator requests | sum-bits | Raytrace first 128 Runs |
|---|---:|---:|
| Allocation calls, before → after | 94,101 → 94,110 | 331,419 → 331,422 |
| Reallocation calls, before → after | 18,243 → 19,322 | 42,373 → 48,182 |
| Allocation + reallocation events | 112,344 → 113,432 | 373,792 → 379,604 |
| Requested bytes | 24,596,739 → 23,693,691 | 138,827,207 → 136,303,991 |
| Query-fragment payload capacity bytes | 283,896 → 189,264 | 370,896 → 247,264 |

Requested bytes decrease 3.67% / 1.82%, while allocation events increase
0.97% / 1.55%. Peak/live request accounting and header sizes are included in
results.json. Byte requests are cumulative, not RSS; smaller byte totals do
not establish lower execution cost. Queries and graph work remain identical.
We retain the simpler production representation because this experiment has
not established the intended reduction in runtime work. The decision does not
claim that a properly timed dense layout could never be beneficial.

## What this says about locality

Neither this rejection nor the [throughput checkpoint](../cell-fixed-reads/checkpoint.md)
proves a dense egraph. Bounded constructor arity, a small set of affected facts,
and a small amount of necessary query work are different properties. Even a
small-arity representation can have large equivalence classes, joins and
repeated attribute propagation. Conversely, a compressed Cell layout can still
require expensive boundary queries and publication.

The next structural test belongs to the hot attribute-propagation family:
attribute actual matched/rejected queries, changed writes and absorbed min
writes to the same source rules. Determine which repeat executions have still
valid input evidence and which are required by changed children, new equality
or visibility. Only the former can be discharged by a completed Cell. Current
global unchanged-write counts do not prove that attribution. If most cost is
necessary boundary enumeration, change the Cell partition or query strategy;
do not enlarge a catalog merely to improve coverage counters.

## Validation and reproduction

The final experimental kernel passes 99 runtime unit tests and 39 integration
tests covering query workers/receipts, Entry publication and stable ports.
Allocator builds preserve the exact final graph, all ordered Run records
(1,428 / 128), graph work and query counts against the baseline. Sum-bits native
choice diagnosis returns `pass` / exit 0. Run-boundary graph/binding fixtures
remain separate from that final-state contract. Raytrace here is a bounded
prefix, not a completed workload or independent native semantic proof.

The production branch also passes minimal compilation and the README
compile/run/bench commands. The single bench repetition is a smoke check.
There is no new full-workload speed campaign.

To reproduce, use `560faaf7` plus the allocation-enabled `query_prefix` helper
from this experiment. Freeze baseline executables from Cargo JSON output, then
apply `experiment.patch` with `git apply --unidiff-zero` in that isolated tree
and freeze candidate executables using the identical features:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics --bin eggfuse-cell-runtime --example query_prefix --message-format=json
RUNTIME --program SUM_PROGRAM --output FRESH --repair-ports --entry-publications --query-workers 4 --query-grain 64
PREFIX RAY_PROGRAM FRESH_PREFIX 128 4 64 canonical
```

Use the same frozen programs as cell-fixed-reads. The prefix helper accounts
only `execute_until`; setup, graph export and reporting are outside its meter.
The collector reads saved artifacts, checks semantics and accounting, and
launches no workloads:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-dense-inputs/semantic out/cell-dense-inputs/semantic-acceptance.json
python3 benchmarks/cell-dense-inputs/collect.py out/cell-dense-inputs benchmarks/cell-dense-inputs/results.json
```

The first draft's saved exports are retained as a diagnosed comparison; the
patch is the final bounded-hole candidate. Binaries, graphs and Cargo outputs
remain ignored. The source patch, input/binary hashes and text results are
tracked.
