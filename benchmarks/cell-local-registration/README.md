# Return completed Cell frames before shared directories

This measures the actual standalone Cell CPU, not native egglog performance.
The control is `d62f83d1`, using the same frozen programs, catalog, release
features and arguments. This is implementation four after timing checkpoint
`2166a3fb`. These are work and semantic checks, not a timing campaign or an
accepted speedup. Compilation may overlap the work runs.

## Opportunity and compiler obligations

The previous Raytrace catalog execution accepted 34,704 Cells through Unit
registration, but only 32 finished while registration work remained. Whole-region
constructor ownership still held the original Cell arena, parent directory,
reverse subscriptions and changes until the last constructor was installed.
More Unit decision events could not release a Cell that still needed its frame.

The existing terminal Cell proof supplies a narrower dependency: completed
operations and actual result slots suffice for source completion and Shared
Entry sealing. Neither needs constructor hash directories. The compiler's typed
Eq footprint, sealed input epoch, exact old/new Unit merge, and terminal
instruction boundary exclude intervening union, mutable reads, fallible suffixes
and other Function allocation. There must be no pending dirty/union work.
Existing parents remain in the graph; parents in the same leased region must
precede their children in source order. Unproved regions use the existing path.

The existing catalog already repeatedly executes these terminal shapes. This
iteration discharges their registration handoff without adding another catalog,
runtime fact graph, binding copy or per-producer subscriber list. Shared Entry
continues to project the same actual results at the original Run boundary;
there is no new cross-Run early visibility or claim of extra query elimination.

## Ownership and deleted work

Only the executing Cell frames leave the arena. They move directly into bounded
event buffers of at most 16 frames. The constructor owner installs each fragment
using the original index and membership containers, fills its publication
certificates in place, and emits that same buffer. It can continue installing
later Cells while the source restores and completes the ready prefix. Actual
returned aliases retain their identities; logical producer/operation is not
used as a universal result address.

The source retains parent lookup and the original change activation order and
counts. Prepared constructor row maps return later. An exact first-row
certificate permits source-ordered table activation without inspecting a map
that is still leased. Index registration does not publish an Entry to a later
Run; normal completion and visibility boundaries still do that.

Fresh Unit rows no longer call `subscribe_edges` on the source. The original
subscription owner handles both constructor and Unit incidences. A completed
table transfers its actual added-row records to that owner as a followup task
in the same pool scope. No second scope, copied reverse index or per-row wakeup
list is introduced. Fresh reserved addresses have no previous incidences, and
their values are canonical in this sealed epoch, so this path also omits root
lookups. Existing/replaced witnesses retain ordinary subscription maintenance.

A source error stops adoption but does not discard events. All original owners
return; exact unadopted rows, keys, memberships, changes and now-prepared reverse
incidences are removed before ordinary execution resumes. Duplicate Unit
candidates are invalidated as before. Bloom/hash collisions never prove equality.

This removes two prerequisites for a terminal Cell's completion: whole-region
constructor directory return and Unit subscription completion. It does not
remove the Run fence, source/error order, stable Function storage reservation,
or exclusive ownership of the shared constructor and reverse-index maps. The
source still performs lifecycle completion; worker subscription tasks share
one owner and are not concurrent writes to that map.

## Observed work and costs

| Raytrace observation | `d62f83d1` | Candidate |
| --- | ---: | ---: |
| Registered source Cells | 34,704 | 34,571 |
| Cells completed with registration work still pending | 32 | 16,535 |
| Cells completed before constructor directory return | 0 | 12,937 |
| Original frames returned by fragment | 0 | 32,433 |
| Fresh Unit subscriptions moved off source | 0 | 64,866 |
| Additional root reads omitted | 0 | 227,031 |
| Pool scopes | 1,026 | 1,022 |
| Followup subscription tasks | 0 | 1,045 |
| Unit metadata capacity, cumulative bytes | 9,317,088 | 9,245,088 |
| Constructor metadata capacity, cumulative bytes | 7,172,552 | 6,435,208 |
| Decision capacity, cumulative bytes | 3,299,392 | 3,289,472 |
| Event queue capacity, cumulative bytes | 2,016,000 | 2,611,648 |
| Original frame event buffers, cumulative bytes | 0 | 6,486,600 |
| Subscription handoff buffers, cumulative bytes | 0 | 869,440 |
| Sum of these capacity counters | 21,805,032 | 28,937,456 |

Coverage improves, but these capacity counters increase by 7,132,424 bytes
(32.7%). They are cumulative buffer capacity, not peak memory or a complete
allocation trace: container internals and allocator overhead are not included.
Original slot and row payloads are moved/shared rather than deep-copied.
Reserved invalid Function slots from the previous implementation also remain.
Changes in eligible region/row counts depend on event arrival and do not imply
different logical effects or counts of eliminated operations.

The first connected version allocated both an outgoing frame vector and a
return-event vector. Reusing the same event buffers removes that redundant
vector and its moves. Its intermediate work export is saved under
`out/cell-local-registration/initial`; it is not a timing sample or an isolated
performance comparison. The final figures above include the retained buffers.

`unit_registry_early_cells` checks unfinished registration work after source
completion; a final owner is marked finished before enqueueing its return.
Pending work includes queued followups, so this is not CPU utilization or even
a guarantee of simultaneous CPU activity. `constructor_registry_pre_return_cells`
only records that directory return has not been processed: the worker could
already have emitted it. The blocking handshake, rather than this latter
counter, proves a Cell can finish while its constructor owner is still working.
Neither counter measures time saved. Event receive wait is only diagnostic.

Sum-bits has no eligible registration region and all these counters remain zero.
This change does not resolve its existing four-worker regression. A future
same-campaign timing comparison must charge the additional buffers, owner
handoffs and source frame restoration before claiming an end-to-end benefit.

## Validation and reproduction

The handshake deliberately blocks both constructor directory completion and
subscription work until the first 16 source Cells advance. Several source-error
prefixes validate exact retained rows, changes, visibility and reverse edges;
a subsequent union/repair agrees with ordinary sequential execution. Event
transport tests cover inline and one-worker followups, followups that release
an unrelated blocked initial task, and followup panics.

Runtime, compiler integration, forced hash/Bloom collision and feature-matrix
checks are recorded in [results.json](results.json). Integration fixtures
preserve Run snapshots, late union, deletion/recreation, ordered effects and
actual result aliases. The frozen workload checks compare exact final states,
ordered Run summaries, logical effects, queries, reverse-edge work/occupancy,
Sieve work and iterative Bake observations. The only changed maintenance
counter allowed by the checker is additional omitted root reads; this is an
operation-accounting difference, not a semantic exclusion. Run summaries alone
are not full intermediate-state proofs.

Native sum-bits acceptance uses the unchanged reviewed choice contract and is
linked to the fresh CPU export hash. Raytrace remains exact differential
validation, not a newly established native contract. README compile/run/bench
commands are smoke checks (one bench repetition), not performance evidence.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

The frozen runtime and command hashes are in
`out/cell-local-registration/manifest.json`. Use fresh output paths for reruns:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-local-registration/semantic-acceptance.json
python3 benchmarks/cell-local-registration/check.py out/cell-registration-events out/cell-local-registration benchmarks/cell-local-registration/results.json
cargo cell-compile --case sum-bits --output out/cell-local-registration/readme-program
cargo cell-run --program out/cell-local-registration/readme-program/program.json --output out/cell-local-registration/readme-run
cargo cell-bench --program out/cell-local-registration/readme-program/program.json --repeat 1
```
