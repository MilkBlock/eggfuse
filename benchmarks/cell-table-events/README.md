# Table completion releases Cell query conditions

This is the actual standalone Cell CPU executor, not native egglog performance.
The control is `1bb73355`, runtime `79e6fe0f`. Frozen programs/catalogs and the
four-worker flags are unchanged. This checkpoint verifies work and semantics;
it does not replace the preceding unfavorable timing campaign or claim a speedup.

## Opportunity and proof

The preceding Raytrace execution published 2,137,009 column notifications in
parallel-capable table batches. It entered 783 table pool scopes, restored every
table to the source, then entered 719 additional condition pool scopes. A quiet
profile put 21.64% of main-thread inference samples under finished-table
publication, including waits; this is inclusive wall residence, not isolated
CPU or synchronization cost.

The Cell query's existing `Spec` identifies the table read by each condition;
its `Guard` edges identify required child summaries and shared columns. The
compiled influence groups identify which row fields can affect each condition.
Those facts prove that a condition can execute after **its own table and its
active children** finish. An unrelated table is not a prerequisite. The last
catalog already supplies these facts, so this change adds no learned history,
marker relation, bindings copy or second runtime fact graph. Across Runs, the
same Shared Entry/query projections consume the finished state at the original
visibility boundary.

## Connected execution

Table tasks still own the actual column, range, neighbor and warm Entry stores.
Each successful task places its original column owner in a write-once result
slot, groups its existing change-buffer positions using the static field masks,
and releases that table's affected conditions. Conditions use the original
index keys and membership maps. A child completion releases its static parents;
multiple guards must all complete before the parent executes. Empty conditions
propagate readiness inline. One worker can run the same dependency schedule.

The table and condition tasks now share one Rayon scope. The covered path removes:

* The whole-table join before condition evaluation can begin.
* Copying per-table changes into the source's combined `QueryIndexes.changes`
  vector, globally sorting/scanning that vector, and building its row-pointer
  vector. Each table sorts its own original buffer and clears it after success.
* The later independent condition pool invocation. The runtime recognizes the
  completed publication and skips both old condition-publication entrypoints.

The old and new condition schedulers call the same evaluator, including exact
support insertion for duplicate candidates. Bloom collisions only enlarge
candidate sets. The new path uses `OnceLock` for lazy columns in
`parallel-publication` builds, permitting safe immutable access to a completed
owner while other owners write. It does not copy columns. First readers of the
same missing column can synchronize on that column; this is a remaining local
dependency and added implementation cost, not a claim of zero synchronization.

Preparation selects a conservative affected closure from changed tables before
exact field changes are known. This adds empty nodes and headers. Group row-index
buffers are moved from the existing plan and returned empty for reuse. Nodes
only prepare reverse columns when a child actually added support, reducing
unnecessary column preparation.

No next-Run query sees partial publication. Repaired/canonical graph readiness,
Entry lifetimes, actual witnesses, original table error order and the final Run
visibility fence remain authoritative. A failed table releases no readers;
successful speculative condition caches are invalidated on error, and original
change notifications are retained. This permits safe lazy recovery without
copying summaries for rollback. Fatal panics retain the existing unwind model,
not a new transactional rollback promise. Unproved/disconnected guard plans and
preexisting unconsumed index notifications retain the ordinary path.

## Work and new costs

| Frozen Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Table pool invocations | 783 | 783 |
| Separate condition pool invocations | 719 | 0 |
| Batches whose table owners complete the conditions | 0 | 1,448 |
| Notifications avoiding source change-vector handoff | 0 | 1,972,540 |
| Prepared condition nodes | 66,124 | 97,487 |
| Conditions doing work before unrelated table computation finishes | — | 32,155 |
| Empty conditions propagated inline by the new path | — | 46,988 |
| Condition column preparations | 61,003 | 27,085 |
| Condition event header capacity, cumulative bytes | 50,263,592 | 56,713,624 |
| Source row-pointer header capacity, cumulative bytes | 37,197,888 | 0 |
| New table descriptors / group headers, cumulative bytes | 0 | 72,160 / 239,448 |
| Global query lookups | 4,027,756 | 4,027,756 |

The new grouping path also reports 104,746,360 cumulative capacity bytes, of
which only 239,448 are the new group headers; the rest describes reused index
buffers. Capacity growth in those buffers is 1,627,872 bytes. These figures are
not complete allocator traffic or peak live memory. They must not all be charged
as newly allocated storage, nor may the removed row-pointer capacity be called
an equal elapsed-time saving.

The extra 31,363 prepared nodes are an unresolved cost. Some batches previously
used ordinary inline publication, so the old/new staged-path counters cover
different subsets; all total Sieve dispatch, condition-row, added-key and guard
counters remain exactly equal. All 97,487 prepared nodes complete. `early_nodes`
includes empty propagation; `early_work_nodes` excludes it and checks actual
unfinished table computation after the condition finishes. Neither measures
CPU utilization. The first counter version's artifacts remain under `initial/`;
its grouping capacity was not yet split into reuse/header/growth components.

`sieve.publication.stats.execute_seconds` now includes overlapped table work for
fused batches. It must not be added to `publication.parallel.execute_seconds` or
compared as isolated condition execution against the previous version. Timing
and worker distribution from these work runs are not performance evidence.
sum-bits has no eligible batches and keeps 14,012 global lookups.

## Acceptance and reproduction

162 runtime tests and 85 relevant integration tests pass. The new handshake
test blocks an unrelated table until a multi-guard successor finishes; a global
table barrier would time out. Tests also cover one/four workers, field masks,
delete/recreate, a previously cold summary, forced hash/Bloom collisions,
failure without releasing dependent readers, and lazy recovery after cache
invalidation. Existing integration fixtures compare every Run graph and ordered
bindings across unions, late values, deletion, shared Entries and scoped repair.
The forced-collision integration run, all-feature, sparse-only and legacy builds
also pass. The README compile/run/single-repeat bench smoke commands pass.

Frozen sum-bits and Raytrace exports and all 1,428 / 16,883 ordered Run summaries
exactly match the control. Logical effects, Sieve totals, index coverage and
query counts also match. Run summaries are not whole-graph snapshots; the small
integration fixtures provide those intermediate checks. The unchanged native
sum-bits acceptance is `pass` and is tied to this CPU export by hash. Raytrace is
an exact differential check, not an extension of the native proof contract.

Release features: `cell-absorption,view-ports,parallel-publication`. Frozen paths
and commands are in `out/cell-table-events/manifest.json`; use fresh directories:

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-table-events/semantic-acceptance.json
python3 benchmarks/cell-table-events/check.py out/cell-write-completion out/cell-table-events benchmarks/cell-table-events/results.json
cargo cell-compile --case sum-bits --output out/cell-table-events/readme-program
cargo cell-run --program out/cell-table-events/readme-program/program.json --output out/cell-table-events/readme-run
cargo cell-bench --program out/cell-table-events/readme-program/program.json --repeat 1
```

Shared constructor adoption, source query admission/Cursor sealing, table-size
imbalance, ordinary repair and the final Run fence remain. This change removes
one real cross-table dependency and handoff. It does not establish saturated
workers or repair the preceding performance regression by assertion. The next
periodic timing gate must judge the net result, including the larger prepared
closure, synchronized lazy-column reads and source restoration.
