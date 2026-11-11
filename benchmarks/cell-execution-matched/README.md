# Prepare existing matched Cells in the source Run's worker invocation

Scope: **standalone Cell CPU**, not native egglog execution. Control: `35a59e30`.
The full ownership, completion/publication and parallel scheduling objective
remains in [the refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md).

The last complete Raytrace execution still dispatched 62,632 source-ordered
worker continuations for 95,702 scalar operations. A source Run already retains
completed matches in its `work` rule groups before joining pending queries.
These matches were missing from the existing query-to-RHS preparation path.
The shared typed Cell plan already proves which scalar expressions use captured
inputs and which source positions still require shared effects. Another
post-winner pool pass would add a new handoff to prepare this same work.

The Run now borrows eligible groups' actual `Instance` arrays into the existing
query invocation. Mixed Runs execute query chunks and matched chunks in the
same pool invocation. Matched-only Runs use the same grain gate and inline
fallback. They require no graph query view, second binding, answer vector or
effect log. New group headers and bounded worker-count reduction scratch are
charged separately. The original rule groups keep their instances and order.

Preparation reads only owned captured scalars. A parent fact or continuation
provenance does not disqualify them; missing projected values remain for the
source operand reader. No worker dereferences a parent or manipulates a Cursor.
An instance records whether preparation was attempted, so a match already
prepared by the earlier per-rule query path is neither recomputed nor retried
after a speculative failure. This is one attempt flag, not a result-readiness
bitmap or a separate runtime fact graph. The existing prepared-prefix position
and unique result slots still supply consumption evidence.

Original-input winner identity, residual matching, source Run snapshots,
shared-effect order, actual foreign constructor references, union completion,
deletion and publication retain their existing authority. A failed arithmetic
operation is reported only at its source position. An earlier RHS deletion
cannot cancel a binding already accepted in the same Run. Prepared results
from losing or terminated executions count as work but not as saved RHS work.

The boundary executor consumes prepared slots and removes their computation
and optional per-segment worker dispatch. This does not independently park
multiple effectful frames or make graph writes concurrent. Cursor/receipt
ownership and Entry projection still need further unification. Across Runs,
the same compiled result sources remain usable only at legal source boundaries;
this change itself does not remove an inter-Run publication.

## Complete work comparison

[results.json](results.json) checks the same programs and four-worker/grain-1
configuration against `35a59e30`. Final state exports are byte-identical, all
1,428 / 16,883 ordered Run summaries match, and checked original graph, query
and maintenance counters are unchanged. Native sum-bits acceptance is `pass`
with exit 0. These are work/semantic results, not a new speed measurement.

| Work / cumulative storage | sum-bits | Raytrace |
|---|---:|---:|
| Additional prepared and source-consumed results | 620 | 93,181 |
| Prepared on workers / inline | 350 / 270 | 90,890 / 2,291 |
| Newly prepared results not consumed | 0 | 0 |
| Later worker segments, before → after | 467 → 29 | 62,632 → 3,046 |
| Local resumption operations, before → after | 634 → 29 | 95,702 → 3,046 |
| Rule eligibility checks | 2,705 | 42,861 |
| Instance admission checks | 135 | 1,362 |
| Borrowed rule groups / chunks | 135 / 135 | 1,362 / 1,933 |
| Mixed / matched-only invocations | 71 / 1 | 664 / 9 |
| New header growth events / capacity bytes | 72 / 9,216 | 674 / 86,272 |
| New preparation slot growth events / bytes | 293 / 11,184 | 29,248 / 1,037,832 |
| Later resumption slot growth bytes, before → after | 37,488 → 3,864 | 5,228,856 → 511,560 |

There are no empty matched chunks and no heap allocations for the worker-count
histogram at four workers. Existing query answer/batch buffer counts and Spine
fragment slot storage are unchanged. The current Instance header is 128 bytes;
this measurement does not by itself establish a header-size reduction. The
compiled execution plan is unchanged. Additional consumed results exceed the
reduction in local-resumption operations by 15 / 525 because those results came
from RHS paths outside that counter. Do not add both numbers as savings.
Raytrace's existing 336 unconsumed query preparations remain; this takeover adds
none in these executions. Reserved and growth capacity do not establish a total
allocation or peak-memory improvement.

The remaining 29 / 3,046 local operations still take individual continuations
with grain 1. Source inspection identifies another ownership gap: serial Spine
answers for a rule with pending worker queries stay in `deferred_queries`, paired
with Cursor, until `finish_worker_rule` seals them after the join. They are not
in the Run's borrowed `work` groups. The offline source inventory still finds
all 21 later scalar sites input-derived, but it does not attribute every remaining
execution to that gap. Further unification must expose the existing frames
without moving Rc-backed cursors to workers or assembling a second binding.
Completion/publication ownership and genuine shared-effect dependencies remain
larger parts of the full objective.

## Validation and reproduction

Use fresh output directories and freeze the runtime before workloads. Compare
complete exports and ordered Run summaries against `out/cell-execution-inputs`.
The checked sum-bits contract uses saved native exports through
`choice_diagnosis.py`; Raytrace remains a relative regression check, not a
native equivalence proof. Targeted tests compare intermediate Run graph states.
The work comparison is not a throughput campaign.

116 runtime unit tests and 46 selected forced-collision integration tests pass.
New cases cover original allocation ownership, parent/continuation provenance,
one-time preparation including failed attempts, mixed and matched-only Runs,
source-positioned failure, and an earlier RHS deleting an accepted match's
source. Existing cases cover unions, foreign reuse, early Hide termination,
recreation, residual enumeration and actual cross-stage publication. Raw logs
and complete exports are in ignored `out/cell-execution-matched`.
The all-feature runtime check and README Cargo compile/run/bench commands pass;
bench repeat 1 is a minimal-path smoke check. Forced-collision validation applies
to the integration suite. An extra unit invocation under forced zero-bit hashes
hit the existing fingerprint-change-mask test's default-hash assumption; normal
unit validation passes without changing that test or the index implementation.

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion --test parallel_residuals
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-matched/check.py ROOT PRIOR_ROOT RESULTS.json
```

Counters distinguish matched preparation (a subset of total query-invocation
preparation), source-consumed results, remaining local continuations, admission
checks, headers, chunks, empty chunks, slot growth and reduction allocations.
Capacity is cumulative and excludes allocator overhead; it is not peak memory.
Do not count matched preparation and its enclosing total as two savings.
