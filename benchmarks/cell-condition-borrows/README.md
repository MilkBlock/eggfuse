# Condition summaries stay in their original storage

This checkpoint measures work in the actual standalone Cell CPU, not native
egglog performance. The control is `4d42d965`, with the same frozen programs,
catalogs, four-worker flags and release features. It is the second implementation
since the last full timing campaign; no new speedup is claimed. The preceding
sum-bits / Raytrace timing regressions remain unresolved.

## Opportunity and compiler facts

The preceding table-event execution prepared 97,487 condition nodes on Raytrace.
Of those, 46,988 had neither direct notifications nor new child support. Each
still held a complete execution record, moved its original `Summary` out of the
Sieve array and moved it back on the source thread after completion. These are
container/ownership moves, not deep copies of all support keys. Empty nodes
already propagated readiness inline; they did not launch extra Rayon jobs.

The existing Cell query `Spec` and guard links identify both writable affected
summaries and the unchanged child summaries they read. The same static closure
and field masks remain authoritative. Once a node's table and affected children
finish, those facts distinguish actual condition work from empty readiness.
No new catalog learning is needed to establish this distinction. Across Runs,
the same query summaries feed the existing Entry projections at the original
visibility boundary; this change introduces no additional cross-Run proof.

## Takeover

Preparation partitions only the affected summaries and their required guard
inputs into disjoint borrows. An affected summary stays at its original address;
its single mutable borrow is transferred to the ready task. Unchanged child
summaries are borrowed immutably. This uses safe slice splitting, without an
unsafe pointer layer, another fact graph or a copy of the bindings.

An empty completion exposes its original summary without creating an execution
record, delta vector or timer. It still releases static parents, which can read
the child's old support. A nonempty completion uses the unchanged evaluator and
exact insertion checks directly on the original summary. The source no longer
restores each summary. It still consumes completion slots to accumulate counters
and restores table owners; those remaining loops are not removed by this change.

The conservative readiness closure, atomic dependency releases, task/result
slots and final Run fence remain. `OnceLock<Finished>` reserves its maximum
payload even for empty completions. The new borrow partition adds a sorted
address vector, comparisons and compact child handles. These are charged below.
Failed tables still release no dependent readers; speculative summary caches
are invalidated on error, with original notifications retained for recovery.
Source error selection, exact support checks, generations and visibility are
unchanged. This is not general transactional rollback for fatal panics.

## Work against the preceding execution

| Frozen Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Potential/completed condition nodes | 97,487 | 97,487 |
| Materialized execution records | 97,487 | 50,499 |
| Empty readiness completions | 46,988 | 46,988 |
| Summary moves out and back | 194,974 | 0 |
| Table-event header capacity, cumulative bytes | 56,704,320 | 35,029,384 |
| New summary borrow handles | 0 | 97,487 |
| New unchanged-child borrow handles | 0 | 20,827 |
| New borrow partition steps / sort comparisons | 0 / 0 | 118,314 / 906,826 |
| Shared table/condition pool scopes | 783 | 783 |
| Global query lookups | 4,027,756 | 4,027,756 |

Header capacity decreases by 21,674,936 cumulative bytes (38.2%), including the
new partition vector and child handles. Borrow-owner headers contribute
2,339,688 bytes and completion slots 9,358,752 bytes. Capacity is not allocation
traffic, peak live memory or saved elapsed time. The full condition scheduler's
header count includes another unchanged 9,304 bytes outside the table path.
The move count is derived from the old path's one move out and one restoration
per completed summary; it is not a machine-instruction or byte-copy trace.

All direct/dependency row visits, additions, guard/dispatch counters, column
preparations and table work remain equal. All per-rule Sieve counters also match.
The observed early-work count changes with scheduling and is not a throughput
measure. sum-bits has zero eligible batches and retains 14,012 lookups, so this
change cannot be cited as fixing its previous regression.

## Validation and reproduction

163 runtime tests and 42 relevant integration tests pass, plus 15 tests under
forced hash/Bloom collisions and an all-feature build check. The event handshake
checks that completed summaries retain their original addresses. A new fixture
checks both an empty child's old support and an unaffected child's support while
their parents gain new results. Existing tests cover table failure/recovery,
retirement, one/four workers and source Run visibility. README compile/run and
single-repeat bench smoke commands pass; smoke timing is not comparative evidence.

Frozen sum-bits and Raytrace exports, all 1,428 / 16,883 ordered Run summaries,
logical effects, query counts and complete Sieve counters exactly match the
control. Small integration fixtures check intermediate Run graphs; summary
equality alone is not that proof. The unchanged native sum-bits acceptance is
`pass`, linked to this CPU export by hash. Raytrace remains differential
validation, without extending the native contract.

Release features: `cell-absorption,view-ports,parallel-publication`. Commands,
binary hashes and frozen input paths are retained under
`out/cell-condition-borrows/manifest.json`; use fresh output directories.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-condition-borrows/semantic-acceptance.json
python3 benchmarks/cell-condition-borrows/check.py out/cell-table-events out/cell-condition-borrows benchmarks/cell-condition-borrows/results.json
cargo cell-compile --case sum-bits --output out/cell-condition-borrows/readme-program
cargo cell-run --program out/cell-condition-borrows/readme-program/program.json --output out/cell-condition-borrows/readme-run
cargo cell-bench --program out/cell-condition-borrows/readme-program/program.json --repeat 1
```

The next periodic speed gate must include the new address sort, readiness costs
and remaining source work. Worker saturation and net speedup are not established
by smaller records or fewer moves. Query admission/Cursor sealing, shared
constructor adoption, ordinary repair and the final visibility fence remain.
