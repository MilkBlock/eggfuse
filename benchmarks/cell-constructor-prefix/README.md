# Existing constructor prefixes continue in the original Cell slots

Scope: **standalone Cell CPU runtime**, not native egglog performance.
Control: `8369a224`. This is an opt-in extension of Cell execution; independent
parked scheduling and concurrent shared effects remain unfinished in
[the refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md).

## Opportunity and obligations

The preceding Raytrace execution had zero later scalar worker dispatches and
556,847 accepted constructor witnesses, but every prepared instance stopped
after its first constructor probe. Source RHS still visited 2,503,393 ordinary
constructor boundaries. Typed Cell operations expose longer chains whose next
key uses an earlier actual result. Existing compiled historical handoffs still
suppress preparation where they already supply that result.

The compiler admits consecutive `Let` constructors with known inputs, static
aliases and tables proven permanent by the existing whole-program visibility
analysis. Ordered `Set`, union, mutable reads, arbitrary primitives, Hide, Panic,
structural-depth auditing and single-function-writer plans remain outside this
takeover. Different Cell identifiers do not prove independence. The plan uses
authoritative operations, input definitions and the existing permanent-table
mask; it adds no runtime dependency graph or per-producer subscriber list.

In the existing Run query invocation, a worker fills actual returned Eq values
into the instance's original slots and continues to the next constructor. The
first missing result, unavailable table or operand stops the prefix. A miss
does not prove source-time absence: an earlier RHS may create that result.
Witnesses stay in static prefix order, without another binding or effect log.
A foreign owner's result is valid; `(this Cell, operation)` is not its address.

Before source effects or allocation, the coordinator checks the original Run
union certificate and each used table's readiness/visibility state. Permanent
tables plus no intervening actual union keep those results valid. It records
the original logical request/reuse counts and demanded receipts, then starts
source execution after the last successful prefix operation. The source does
not replay these instructions. Cumulative alias accounting is compiled per step.

Failed validation clears every speculative constructor destination before
source execution. The first witness can still use existing exact key, lifetime
and forwarding validation; ordinary RHS handles the rest. Completed effects
never replay. Winner identity uses original inputs only. Source Run queries,
effect order, completion, residual enumeration and visibility are unchanged.
Prepared constructor lookups are not committed graph mutations.

The temporary prefix witness array still feeds demanded results into Effects.
This is **not yet one result buffer from worker through Entry publication**.
The source driver still resolves shared effects synchronously.

## Complete execution evidence

[results.json](results.json) records byte-identical final states and identical
1,428 / 16,883 ordered Run summaries. Original logical graph work, known-result
handling, repair and Entry scheduling are unchanged. Native sum-bits acceptance
passes the reviewed saved-export contract. Raytrace is regression evidence
against the control, not a newly supported native proof contract.

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Compiled prefix rules / constructor steps | 99 / 304 | 99 / 353 |
| Consumed prefix instances | 945 | 284,545 |
| Source constructor instructions skipped | 2,022 | 483,504 |
| Additional source lookups removed | 1,077 | 198,959 |
| Additional worker probes | 1,330 | 345,339 |
| **Total lookups, before → after** | **14,221 → 14,474** | **4,022,556 → 4,168,936** |
| Source constructor boundaries, before → after | 11,160 → 9,397 | 2,503,393 → 2,066,773 |
| Prefix certificate checks | 945 | 284,545 |
| Prefix table checks | 2,022 | 483,504 |
| Invalidations in these workloads | 0 | 0 |
| Demanded witness writes into Effects | 1,107 | 262,894 |
| Worker Eq slot writes | 2,022 | 483,504 |
| Slot growths / added capacity bytes | 880 / 44,400 | 274,769 / 13,555,992 |
| Witness allocations / capacity bytes | 945 / 18,880 | 284,545 / 5,083,984 |
| Net saved equally weighted operations | -11,800 | -2,772,172 |

The first constructor was already probed in the control. All skipped source
instructions cannot count as additional avoided lookups. The check script
verifies lookup conservation after subtracting prior accepted witnesses.
Wider prefixes add misses and allocations. More worker work and fewer source
boundaries alone do not establish speedup.

Instance headers grow 144 → 152 bytes; RHS owners remain 456 bytes. Compiled
payload grows 438,600 → 487,784 and 2,365,624 → 2,419,688 bytes. Raytrace also
retains 558 additional query-fragment slots / 13,536 capacity bytes; the sealed
subset grows by 576 slots / 13,968 bytes. Those overlapping fragment counters
must not be added as separate allocations. Six worker and seven graph counters
add 104 bytes of payload per corresponding counter set. The work reader charges
source checks, slot writes/growths, witness allocations, receipt writes and
extra probes. Storage is separate; equally weighted work is uncalibrated.

127 runtime and 95 compiler/integration checks pass. The new native fixture
covers zero through three existing constructors, foreign results, first-miss
creation and a later consumer. It compares every Run snapshot, ordered bindings
and final state with one/four workers, canonical repair/stable local congruence,
and with/without a final union. A union's final constructor lowers to ordered
`Set`, which remains outside the prefix. A separate invalidation check unions
or deletes after preparation and verifies removal of all prepared Eq slots
before allocation. Compiler checks force hash/Sieve collisions. All-feature,
no-default-feature and README compile/run/repeat-1 bench smoke checks pass.

## Reproduction

Freeze the feature executable before README default builds. Reuse the control's
frozen programs/native exports and fresh output directories. Raw evidence is in
ignored `out/cell-constructor-prefix`. `initial/` retains the first prototype's
evidence; its extra no-prefix admission dispatch was removed before final checks.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test entry_publications --test joint_results --test parallel_residuals --test query_workers --test ripsat_completion --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-constructor-prefix/check.py ROOT PRIOR RESULTS.json
python3 benchmarks/cell-constructor-prefix/measure.py ROOT/runtime PRIOR/runtime TAG/runtime HISTORICAL/runtime SUM_PROGRAM RAY_PROGRAM TIMING_OUTPUT
```
