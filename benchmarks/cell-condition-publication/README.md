# Publish Cell conditions in dependency layers

Control: `77f0dc81`. Scope: **standalone Cell CPU**, not native egglog. This
extends the existing `--parallel-publication` path beyond column publication
to the existing Sieve condition summaries. It does not parallelize union,
ordered RHS effects or graph repair.

## Opportunity and proof

The last complete Raytrace execution performed 6,983,829 direct summary
updates and 365,850 updates propagated from child support. Those remained on
the coordinator after column publication. The existing Cell query links
already define the guards, shared column influence groups and static parent
wiring. They form nine dependency layers. A connected-component partition
would leave a large component (789 of 1,163 specifications in the saved audit)
on one worker; independent summaries within a layer permit finer ownership.

The first large publication prepares a layer/address plan from those existing
definitions. Small executions allocate no plan. At a legal publication
boundary, the coordinator routes changed-row addresses through the existing
field influence groups. One group input stream serves its matching summaries.
Workers own distinct existing Summary values and borrow completed child
summaries. They finish a whole summary before handing it back. No support set,
binding frame or graph is cloned, and there are no new per-instance consumers.

After a layer joins, newly added support activates parents through the existing
static wiring. Lazy index columns needed by propagation are completed before
borrowing them into workers. The existing query Domain supplies candidate
membership directly, removing the old temporary `hash_candidates` witness
vectors on this covered path. Digest collisions still require the same support
checks; summaries remain necessary filters, not proofs of whole rule matches.

Only the current publication's row addresses and newly added projections are
held temporarily. All are cleared after the join, retaining empty capacity.
Source Run ordering, visibility, deletion/invalidation and residual matching
remain authoritative. Unbuilt summaries, small batches and unsupported
dependency ordering retain the existing path. No cross-Run completion credit
is awarded merely for changing summary ownership; reusable support retains
the existing lifetime and invalidation rules.

## Work and acceptance

[results.json](results.json) records complete runs and charged transport costs.
Every prior Sieve counter, graph effect, key query, reverse-maintenance counter,
Entry/publication counter and ordered Run agrees with the control. Exact final
states match for all 1,428 sum-bits and 16,883 Raytrace Runs. The reviewed
sum-bits native acceptance returns **pass / exit 0**. Raytrace is a relative
regression check, not an extension of the independent native contract.

| Complete workload | sum-bits | Raytrace |
|---|---:|---:|
| Existing publication summary updates | 31,561 | 7,349,679 |
| Updates executed on workers | 0 | 6,165,681 |
| Updates remaining on coordinator | 31,561 | 1,183,998 |
| Additional pool executions | 0 | 1,806 |
| Layer tasks | 0 | 47,041 |
| Plan payload bytes | 0 | 71,363 |
| Retained scratch capacity bytes | 0 | 6,621,920 |

The 83.9% transfer is of publication updates only. It excludes cold summary
builds, query probes, Entry preparation and graph effects. Raytrace also pays
894,453 group row headers, 25,924 prepared-column requests and 306,396 candidate
visits. Cumulative task-vector and row-header capacities are 12,418,824 and
37,197,888 bytes; these are neither simultaneously live bytes nor allocation
counts. The sum-bits path makes 657 small-batch checks and allocates no plan.

The new counters distinguish worker updates from inline updates, and expose
task/group/row headers, prepared columns, retained scratch and phase residence
times. Worker rows are existing work moved off the coordinator, not eliminated
operations. Candidate visits include rows rejected by exact hash checks.
Header byte totals count vector capacities across dispatches, not allocator
events; scratch excludes allocator metadata and spilled projection payloads.
Plan payload excludes the enclosing State's fixed headers and counters.
Phase/worker seconds are wall residence, not CPU time or throughput evidence.

The separate stack diagnostic is retained in [profile.json](profile.json).
Its five-second window enables progress logging and sampling; inclusive
frames overlap. It cannot establish speedup or overall CPU utilization.
In the final binary's sample, each thread has 1,621 observations. Worker
condition waits account for 1,433 / 1,443 / 1,446 / 1,456 observations
(88.4–89.8%). Coordinator inclusive frames include matching 474, Entry batches
302, finished-table publication 302, RHS 178 and repair 143. Entry batches
include their query-dispatch callback; they are not solely refresh cost.
Worker waiting remains substantial, so **full multithread utilization is not
achieved**. Entry batch preparation, matching and ordered graph work remain
next targets. The earlier [timing checkpoint](../cell-parallel-current/README.md)
measures the code before this change; it must not be credited as its speedup.

109 runtime unit tests and 23 selected integration tests pass. Tests cover
branching dependencies, late child support, field masks, lazy
summary activation, invalidation, wide and empty projections, forced hash/Bloom
collisions, union, deletion/recreation and original Run order. Runtime units,
worker/residual/absorption/publication integrations, minimal/all-feature checks
and README compile/run/bench smoke commands are recorded in the ignored raw
directory. Bench repeat 1 is a smoke check only.

## Reproduce

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_absorption --test parallel_publication --test parallel_residuals --test query_workers
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test cell_absorption --test parallel_publication --test parallel_residuals
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
# Freeze runtime. Run each frozen program into ROOT/sum and ROOT/ray:
ROOT/runtime --program PROGRAM --output OUTPUT --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-condition-publication/check.py ROOT PRIOR_ROOT RESULTS.json
python3 benchmarks/parallel-cell-publication/profile.py ROOT/runtime RAY_PROGRAM ROOT/ray ROOT/profile
```

Raw artifacts live under ignored `out/cell-condition-publication`; the control
is `out/cell-canonical-subscriptions`. Frozen programs come from worktree
`7c16/out/cell-fixed-reads/{sum,ray}-program.json`. Saved native proof inputs
are reused with this execution's `semantic/run-values/state.json`.
