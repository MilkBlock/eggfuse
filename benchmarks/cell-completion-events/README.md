# Cell completion events

This is the actual standalone Cell CPU executor, not native egglog performance.
The control is `cf452ed6`; its runtime implementation is `8335929d`. Frozen
sum-bits and Raytrace use the existing catalog, without retraining or changing
the source programs. Performance and work results are recorded separately from
the pristine upstream import.

## Opportunity and compiled evidence

The last catalog's Raytrace execution had 5,737 query invocations, 3,388 ready
constructor queues and 1,806 Sieve layer pool calls. Its workers spent most of
the sampled time idle. The useful existing compiler evidence is the Cell query
and input layout, certified pure constructor/Unit tails, actual result slots,
and the Sieve's static child/parent guards. It already specifies which work a
completion can release; a new rule-apply history or runtime fact graph is not
needed for this scheduling change.

The discharged work is the separate post-query residual-sort pool phase,
whole-queue wait before starting RHS adoption, and each Sieve layer join.
Across Runs, the existing instance outputs still feed Shared Entries at their
source visibility boundary. This does not discover new cross-stage dominators
or prove a new Run can observe partially committed prior effects.

## Connected paths

* **Queries:** ordinary queries, owned Entry ranges and already matched
  instances return completion events. Each task releases only the rules it
  actually serves. Once a rule's inputs and preparation are complete, its
  existing candidate vectors move to a successor task in the same pool.
  Workers perform input/depth/source winner selection and residual ordering.
  Source-local Cursor ownership is sealed when that task returns; only the
  uncovered partial-coverage merge remains on the source. There is no second
  residual sorting invocation after all queries join. Tiny sorting jobs run
  inline, and rules without pending results get no empty successor task.
* **RHS:** the existing effect-result owner moves with the constructor job.
  Only its immutable plan changes from `Rc` to `Arc`; Cursor roots remain
  source-local. Workers may compute the same private candidate and write
  competing result slots. A ready source prefix immediately reattaches its
  original frames, validates/adopts actual rows, invalidates duplicate Unit
  candidates and continues the Cells. Larger ready prefixes retain table-owner
  classification/installation. Small prefixes use the existing exact path.
  Parent readers retain an immutable epoch while source writes use the existing
  overlay; no graph/binding copy is introduced.
* **Condition publication:** compiled child completion releases a parent as
  soon as its affected children are finished. Unrelated nodes in the same depth
  no longer block it. A multi-guard node observes all completed child summaries.
  Duplicate candidate routes use the original exact support insertion; Bloom
  hits do not establish equality. Empty released nodes propagate completion
  inline, without another pool job. The old layer output arrays are removed.

The completion queue reuses its buffers. Unordered query events do not allocate
a full result slot for every task. RHS order uses bounded slots for its at-most
64 owners. This is scheduling metadata over existing owners, not another copy
of bindings, facts or producer subscriptions.

## Live obligations and limits

* Worker arrival order cannot choose winners or errors. Query failures retain
  their original source key; all speculative effects remain private until the
  authorized effect boundary. A worker panic wakes the event receiver before
  scope unwinding, so a missing result cannot hang the coordinator.
* Delta ownership, actual foreign constructor witnesses, retirement,
  generation, delete/recreate behavior and Run visibility keep their original
  checks. Error paths discard uncommitted candidates and release Cursor owners.
* RHS adoption still follows the source prefix, including global Function-ID
  assignment and effects not yet proved independent. This change overlaps
  adoption with worker computation; it does **not** establish independent
  per-key commit order or remove every queue/Run boundary.
* Table/index publication still precedes Sieve observation. The removed
  barriers are the subsequent Sieve depth layers, not all table publication or
  repair fences. Ordinary repair, conflicting mutable effects, and next-Run
  visibility remain live work.
* Source dispatch, Cursor processing, partial winner merges, event wakeups,
  ready-prefix table registration and speculative empty condition closure all
  cost work. A lower barrier count alone is not evidence of acceleration.

## Measures and validation

`query_workers.stats.event_*` reports finalized rules before unrelated query
tasks return, source receive waits, event waves and payload capacity.
`cell_execution.runtime.stats.scheduler.event_*` does the same for RHS
prefix adoption. These waits time condition-variable waiting, not worker idle
time or whole-process CPU utilization. The old scheduler `wait_ns` now spans
worker execution **and overlapped source adoption**; it is not comparable to
an isolated old pool wait.

`sieve.publication.stats.event_*` charges affected nodes, static edges, empty
nodes, inline empty propagation and task headers. `pool_calls` counts Run
scopes, rather than old per-depth scopes. Normal-build capacity counters are
not complete allocator measurements. Existing query counts, duplicate
evaluations, Unit candidates/inserts/invalidations and table-registration costs
must be retained alongside event coverage.

Validation includes 145 runtime tests and 84 compiler/integration tests. New
handshake tests require a successor to execute before an unrelated producer can
finish; they would deadlock/timeout with the old whole-batch dependency. Tests
also cover source error order, panic wakeup, in-place candidate ownership,
multi-child condition completion and exact collision handling. Integration
tests compare every Run snapshot and ordered binding audit, including late
inputs, unions, deletion, recreation, mutable effects and speculative failures.
Forced hash/Bloom collisions pass. All-feature, sparse-only and legacy
no-default-feature builds and the README compile/run/bench commands pass.

Frozen workload checks compare exact final states, all ordered Run summaries
and logical-effect counters to the current branch. The native sum-bits final
contract is checked by the unchanged `choice_diagnosis.py`, using saved exports
whose CPU state hash must match the new execution. This does not extend the
native proof to Raytrace; its check is exact differential execution.

Reproduce with matching release features
`cell-absorption,view-ports,parallel-publication`, saved control/candidate
binaries and manifests under `out/cell-events`. Each manifest contains
`control1`, `candidate1`, `control4`, `candidate4`, the same frozen program, and:

```text
--repair-ports --entry-publications --cell-absorption
--query-workers N --parallel-residuals --parallel-publication
--cell-execution-grain 1
```

```sh
python3 benchmarks/witness-prefix/measure.py out/cell-events/sum-manifest.json out/cell-events/timing-sum --repeat 5 --warmups 1 --timeout 120
python3 benchmarks/witness-prefix/measure.py out/cell-events/ray-manifest.json out/cell-events/timing-ray --repeat 3 --warmups 1 --timeout 120
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-events/semantic-acceptance.json
python3 benchmarks/cell-completion-events/check.py out/cell-events benchmarks/cell-completion-events/results.json
```

All samples and warmups are kept. Timing starts only after compilation stops.
Intermediate work-count runs are retained separately and do not establish a
performance result. New event headers were reduced before the final comparison;
the earlier implementation's costs remain visible in the result artifact.
