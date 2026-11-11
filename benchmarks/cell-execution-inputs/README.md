# Input-derived RHS results in the existing Cell query invocation

Scope: **standalone Cell CPU**, not native egglog execution. Control:
`4ed640e2`, using its frozen `ed662552` runtime. The overall execution-ownership
and parallel-utilization objective remains in
[the refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md).

The last actual Raytrace execution dispatched 71,912 later scalar segments,
averaging 1.46 operations each. Grain-1 resumption regressed throughput. The
source inventory found 21 later scalar sites in 14 rules with operands derivable
from matched inputs. This is evidence to remove dependency round trips, not a
reason to relax source effects or a claim of independent shared graph writes.

The typed Cell plan now contains the original positions of input-derived scalar
operations after the first boundary. Copy wiring is resolved statically; Eq
operations and mutable-return dependencies are excluded. Templates rewriting
captured input slots retain ordinary execution. Compilation stops considering
positions after unconditional Panic. Version-2 artifacts include this plan;
the loader reconstructs it from source and rejects forged eligibility. Old
version-1 cuts remain checked and receive the same source-derived analysis.

Query completion reserves these result slots in its existing allocation and
evaluates them in its current worker invocation. Each result has a unique SSA
destination. Presence in that slot supplies the evidence at the original RHS
position: no second binding, per-instance readiness bitmap, effect log or extra
pool pass is introduced. The RHS consumes the result without recomputation or
post-boundary dispatch. Mixed worker segments likewise consume prepared slots.
The specialized single-write executor also consumes them when an earlier
unprepared primitive prevented contiguous-prefix preparation.

Missing/failed preparation leaves the result absent and stops further
preparation. The original instruction still reports failure at its proper
position. Earlier effects, constructor reuse, queued union, failed Hide, winner
selection, residual matching and Run publication retain their ordinary paths.
Prepared work on losing candidates or after an early stop is charged but never
credited as saved execution. A later Run still needs its original visibility
boundary; this change alone does not remove an inter-Run Entry.

Metrics distinguish total preparation, its later-operation subset, actually
consumed later results, deferred failures, reserved bytes and capacity growth.
`prepared_rhs_later_operations` is the single source of consumed-work credit.
The nested resumption counter for the same work is a diagnostic subset, not an
additional saving. Completed source instructions and committed graph mutations
remain different quantities.

## Complete work comparison

[results.json](results.json) records complete executions with the existing
four-worker query pool and grain-1 post-boundary resumption enabled. Exact final
exports, the schedule/epoch/match summaries of all 1,428 / 16,883 ordered Runs,
and the checked existing graph, query and maintenance counters match the
control. Native sum-bits acceptance passes with
exit 0. This is a work/semantic comparison, not a new throughput measurement.

| Work / storage | sum-bits | Raytrace |
|---|---:|---:|
| Later prepared results | 83 | 9,280 |
| Prepared on workers / inline in small Runs | 62 / 21 | 9,219 / 61 |
| Later results consumed at their source positions | 83 | 9,280 |
| Later prepared results not consumed | 0 | 0 |
| Worker resumption segments, before → after | 550 → 467 | 71,912 → 62,632 |
| Remaining local operations, before → after | 717 → 634 | 104,982 → 95,702 |
| Additional reserved query-slot bytes, cumulative | 1,992 | 222,720 |
| Resumption capacity growth bytes, before → after | 47,400 → 37,488 | 6,034,416 → 5,228,856 |

Both programs have 21 eligible later source positions. Compiled plan storage
increases by 14,416 bytes, including one shared vector header per rule. Query
preparation performs no capacity growth. Initial-prefix preparation is disjoint
from these counts; its existing unconsumed Raytrace work remains 336 operations.
Capacity growth and reserved bytes are not peak memory or a complete allocation
profile and must not be subtracted to claim a total memory saving.

The remaining 95,702 Raytrace local operations make the coverage limitation
explicit. The next ownership opportunity is already completed matches held in
the source Run's `work` groups before `Workers::finish_run`. Their eligible local
state could join the existing query invocation rather than taking a second pool
pass or individual post-effect round trips. Parent projections, continuation
evidence, winner order and actual coverage still need proof; this is not yet
implemented here. Shared effects and publication ownership also remain live
parts of the overall refactor.

## Validation and reproduction

114 runtime unit tests and 38 selected integration tests pass, including forced
hash/Sieve collisions and exact intermediate graph checks in the Run-boundary
fixtures. The all-feature runtime check and README Cargo compile/run/bench
commands pass; bench repeat 1 is a minimal-path smoke check, not a timing result.
Raw complete work
and native acceptance outputs are under ignored `out/cell-execution-inputs`;
the accepted integration log is
`out/cell-execution-refactor/input-ready-integration-accepted.log`.

Use fresh output directories and freeze the runtime before executing saved
programs. The work checker compares exact final graphs, every ordered Run and
existing graph/query/maintenance counters with the previous checkpoint. It
requires actual consumed preparation, fewer worker segments and reconciles
removed local operations exactly. Native sum-bits acceptance uses the reviewed
contract; Raytrace is a relative regression check.

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_execution --test closed_aliases --test query_workers --test ripsat_completion
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-execution-inputs/check.py ROOT PRIOR_ROOT RESULTS.json
```

Tests cover no initial scalar prefix, linked scalar chains, input overwrites,
Copy wiring, original-position arithmetic failure, early visibility termination,
foreign constructor reuse, union and actual Entry publication. A typed-runtime
test resolves a mutable read after an earlier update and mixes its dependent
computations with prepared values in the same worker segment. The current native
frontend rejects direct mutable function reads in rule RHSs; this test does not
expand that frontend contract.
