# Existing Cell handoffs replace constructor preparation

Scope: **standalone Cell CPU runtime**, not native egglog performance.
Control: `0368e471`. The full ownership and parallel-execution objective remains
in [the refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md).

The preceding complete Raytrace execution found 587,939 constructor witnesses,
but 28,106 source inputs never reached constructor validation: existing Cell
completion/handoff paths had already supplied those results. Matching had
retained the Cursor and its compiled operation-to-history-slot mapping before
worker preparation. Speculatively querying the same constructor again was
unnecessary for those successful handoffs.

The checked constructor plan now records whether any state in the authoritative
Bake switch can supply that operation. Only 2 of the 366 preparation rules in
these workloads qualify. Rules without a possible donor skip all per-instance
history admission. This is a shared compile-time flag, not a runtime index.

At the existing serial Cell-match outlet, a qualifying constructor checks its
Cursor's compiled result program. If the selected operation already has an actual
Fact result in the indicated history slot, it keeps that existing handoff and
marks optional constructor preparation finished. No new binding, result array,
runtime dependency graph, subscriber list or full admission pass is introduced.
The existing pending-preparation check also removes groups with no remaining
work. Scalar preparation remains eligible independently.

Admission does not certify the historical witness. Original source execution
still checks its full key, forwarding, lifetime and visibility, and retains its
ordinary first-miss fallback. Nothing is reclassified as a sealed worker witness;
in particular, an old history reference cannot inherit the current Run's key
certificate. Cursor ownership, source ordering, union timing, completion and
Entry visibility are unchanged. Worker-query admission currently excludes
Cursors with result history; these covered matches already use this serial
matching outlet, so no extra per-worker header or result message is needed.

## Complete execution evidence

[results.json](results.json) records both whole workloads. Final graph exports
are byte-identical and all 1,428 / 16,883 ordered Run summaries match the control.
All original logical graph and handoff work is unchanged. Native sum-bits
acceptance passes with the saved exports and reviewed choice contract. Raytrace
is regression evidence against the control, not a new native proof contract.

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Constructor prequeries, before → after | 5,117 → 4,860 | 913,319 → 885,192 |
| Removed prequeries | 257 | 28,127 |
| Rule-level eligibility checks | 635 | 6,124 |
| Instance history-presence checks | 419 | 43,123 |
| Nonempty-history program checks | 257 | 28,127 |
| Compiled operation comparisons | 257 | 28,127 |
| Existing result-slot reads | 257 | 28,127 |
| Additional inherited-frame reads | 0 | 0 |
| Source lookups restored after stale handoffs | 0 | 21 |
| Total key lookups, before → after | 14,478 → 14,221 | 4,050,662 → 4,022,556 |
| Matched-preparation groups, before → after | 481 → 461 | 5,025 → 4,928 |
| Matched-preparation chunks, before → after | 481 → 461 | 11,480 → 11,237 |
| Net saved equally weighted operations | 223 | 90,740 |

The 21 Raytrace stale handoffs explain the difference between 28,127 removed
worker probes and 28,106 fewer total lookups. In the control, their worker probe
supplied a replacement witness after the original handoff failed. The new path
uses the ordinary source lookup in those cases. Those costs are included, not
hidden behind the count of suppressed preparation.

Instance size remains 144 bytes and RHS owner size remains 456 bytes. The new
shared eligibility flag grows the compiled plan headers by 4,656 bytes per
workload: 433,944 → 438,600 bytes for sum-bits and 2,360,968 → 2,365,624 bytes
for Raytrace. The seven global admission counters add 56 bytes of counter payload.
This storage is reported separately from operation counts.
Existing history and publication counters do not
decrease: this takeover removes their duplicate prequery, not the authoritative
handoff itself. The remaining 325,380 Raytrace preparation misses still add
queries. Preparation stays opt-in and no overall speedup or full worker
utilization is established. There is no timing campaign at this checkpoint.

`cell-constructor-preparation/v3` requires the new admission counters in the Bake
work reader, including rule eligibility, empty-history checks, failed plan
searches and inherited reads. An earlier draft omitted the first two categories;
its incomplete accounting is retained only under ignored
`out/cell-constructor-handoff/incomplete-admission-accounting`. It is not the
score reported here. The skip count
is a candidate-state outcome before winner selection and earns no extra credit.
Only actual lookup/preparation/dispatch reductions count as savings. The
equally weighted score remains uncalibrated. Old v1/v2 reports remain readable;
missing current counters fail validation.

126 runtime unit checks and 94 compiler/integration checks pass, with forced
hash/Sieve collisions in the compiler suite. The new cross-stage fixture runs
with one and four workers and compares every Run state, ordered bindings and
the full final graph. It also deletes the historical constructor after matching
but before the consumer's RHS, requiring real source fallback. All-feature and
no-default-feature compilation pass. The README Cargo compile/run commands and
repeat-1 bench smoke pass. The native acceptance input contract and validator
are unchanged.
The first README runtime build ran out of disk space; its failure log is retained.
Removing only the runtime package's regenerable Cargo cache freed 577.3 MiB;
the frozen control/candidate executables and experiment evidence were preserved.

## Reproduction

Use fresh directories and the same frozen programs as the control. Retain the
feature runtime before the README default builds. Raw outputs/logs are under
ignored `out/cell-constructor-handoff`.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test entry_publications --test joint_results --test parallel_residuals --test query_workers --test ripsat_completion --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-constructor-handoff/check.py ROOT PRIOR RESULTS.json
```
