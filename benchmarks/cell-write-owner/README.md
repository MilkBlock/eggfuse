# Scalar write owners admit their own Cell inputs

This measures work in the actual standalone Cell CPU, not native egglog
performance. The control is `772b98f5`, with unchanged frozen programs and
catalogs. This checkpoint contains no new comparative timing campaign.

## Opportunity, proof and takeover

The last Raytrace catalog execution already produced 840,367 scalar write
candidates on the covered path. Workers owned their actual Function writes, but
the coordinator still projected every key, looked up every target, allocated
new identities, grouped destinations and later restored source order. Thus a
successful Cell's input slots reached a worker only after substantial admission
work had already happened on the source thread.

The existing compiler `PortWrite` proof supplies one matched Eq key and an i64
value from matched inputs or the supported checked-add prefix. The table merge
is `old`, `min` or `max`. The existing scheduler also excludes pending source
origins, mutable-writer parents, unsupported completion modes and insufficient
identity capacity. Constructor-backed parents remain immutable during this
scalar-only region. These are facts about the authoritative Cell instructions,
not a new fact graph, marker or shadow binding layout.

The same successful instance slots now pass into one table-owner worker region:

```text
original input slots
  -> parallel key projection and exact existing-target lookup
  -> source-ordered assignment for missing keys
  -> parallel destination ordering
  -> existing parallel compute / merge / actual row write
  -> parallel restoration of source ordinals
  -> source lifecycle and Cell publication
```

Both sorting passes operate on the original task array. The same actual
Function rows and writer-slot allocations are mutated/adopted; no RHS operation
log or new answer vector is introduced. The former coordinator key-projection,
lookup and sorting loops are removed. Source wrapping still separates non-Send
Cursor/query evidence from the transferable slots; that loop remains.

All keys are validated before shared mutation. The parallel reduction retains
the first source error, rather than the first worker to finish. A missing key
rechecks the evolving exact directory during ordered assignment: two workers
may independently observe absence, but duplicate new keys get one real row.
The ID scan and target-borrow construction are still sequential inside the
owner; moving them is not counted as parallelizing those operations.

The existing per-destination source merge and invalidation remain unchanged.
Workers may compute duplicate candidates; superseded private slots are dropped,
and only the final writer occupies the authoritative row. Source-position
improvements remain available for ordered effects and receipts. No next-Run
query sees provisional rows. Error-prefix, retirement, retained parents, actual
result witnesses and Run visibility obligations remain live.

Unchecked arithmetic still uses the existing speculative prepass and ordinary
source fallback on failure. The measured workloads use the direct input-ready
path for every scalar write batch. This change adds no cross-Run composition;
the same scheduled Cell switches and Shared Entry projections consume the
completed writes at their original publication boundary.

## Measured work and additional cost

Features: `cell-absorption,view-ports,parallel-publication`. Frozen candidate4
program paths and flags come from `out/cell-events/{sum,ray}-manifest.json`:

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

| Raytrace | Control | Candidate |
| --- | ---: | ---: |
| Scalar candidates | 840,367 | 840,367 |
| Key projections and initial target lookups on workers | 0 | 840,367 |
| Records in the two sorts on workers | 0 | 1,680,734 |
| Actual write pool calls | 3,660 | 3,660 |
| Extra new-key directory rechecks | 0 | 4,656 |
| New actual Function rows | 4,385 | 4,385 |
| Final row writes | 755,389 | 755,389 |
| Invalidated candidate writers | 84,978 | 84,978 |
| Logical improvements | 763,097 | 763,097 |
| Scalar-write payload capacity, cumulative bytes | 197,995,912 | 197,995,912 |
| Global query lookups | 4,027,756 | 4,027,756 |

New-key rechecks add about 0.55% to write-directory probe count. They are
separate from global query lookups, so the unchanged global counter must not
hide this cost. Failed admissions also charge completed probes and projections.
The capacity counter covers the existing task, target, context and completion
arrays; it is not peak heap or total Rayon/allocator traffic. Parallel sorting
and reductions also consume scheduler work. No speed or utilization conclusion
follows from moving these operations.

`execution_ns` now includes admission and both sorts within the same pool
region. `boundary_ns` covers the remaining source lifecycle/index completion.
These timers therefore cannot be compared as unchanged phase definitions, nor
interpreted as pure waiting. The earlier whole-runtime regression remains
unresolved until the next scheduled complete timing checkpoint.

sum-bits has no eligible scalar write batches. Its global lookups remain
14,012; no gain on that workload is claimed. Full scheduler and Unit-owner
counters are retained in `results.json`, including scheduling-dependent changes
outside this path. The initial execution before completing failed-admission
probe accounting is retained under `out/cell-write-owner/initial`; it is not a
separate timing result.

## Validation

154 runtime tests and 85 relevant integration tests pass. New assertions require
real worker key projection, one owner pool call per write batch and both sorts
inside that owner. The min/max/old fixture verifies duplicate targets, source
effect digests, union and downstream Run visibility against the ordinary path.
A new 1/4-worker malformed-key test verifies that failed projection reserves no
Cell IDs, Function rows or directory entries while still charging its probes.
The existing checked-arithmetic test preserves exact prior effects on failure.
Forced hash/Bloom collision checks, all-feature, sparse-only and legacy builds
also pass.

sum-bits and Raytrace final exports, all 1,428 / 16,883 ordered Run summaries,
logical effect counts and every pre-existing non-timing scalar-write counter
match the control. Run summaries are not whole-graph snapshots; the integration
fixtures provide exact snapshot and binding/effect-order checks. Saved native
sum-bits acceptance is `pass`, with its CPU hash checked against this run.
Raytrace remains an exact differential check, not an extended native proof.

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-write-owner/semantic-acceptance.json
python3 benchmarks/cell-write-owner/check.py out/cell-table-owner out/cell-write-owner benchmarks/cell-write-owner/results.json
cargo cell-compile --case sum-bits --output out/cell-write-owner/readme-program
cargo cell-run --program out/cell-write-owner/readme-program/program.json --output out/cell-write-owner/readme-run
cargo cell-bench --program out/cell-write-owner/readme-program/program.json --repeat 1
```

Use fresh paths for the README smoke commands. Their first compile encountered
a full filesystem before execution; after deleting only this worktree's
rebuildable Debug incremental cache and rebuilding the compiler, all three
commands passed. Historical results were retained. The one-repeat bench is a
workflow check, not comparative performance evidence.

Remaining source boundaries include writer retirement/parent retention,
membership and change publication, Cursor completion and constructor-index
adoption. The scalar owner still returns as a batch. This is a larger ownership
scope within the active scheduler refactor, not a claim of full event-driven
graph mutation or saturated workers.
