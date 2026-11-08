# Completed producer nodes and indexed compiler facts

This experiment extends `df4120de` on the **standalone Cell CPU runtime**. The
complete applications still use ordinary canonical repair. Native egglog runs
the focused source checks and the finite Cell registry; it is not the runtime
whose application performance is measured here.

## A producer does not need a matching entry

Full stage lowering could represent every observed consumer entry, but 102
observed Raytrace producer rules remained outside the leaf set. They supplied
255,276 outgoing winning consumer visits. These are visits, not distinct source
executions or committed mutations.

The opt-in `eggfuse-iterative/v2` catalog adds a typed completed-producer leaf.
It carries a rule and no pivot, and has no matching block. A fully executed
source may establish this state at RHS capture. It can be the left operand of
a continuation; using it as the right operand is rejected. A source is never
considered matched merely because its receipt node exists. The existing Run
barrier, source unions, table visibility and live-key receipt checks remain.

The compiler collects witnessed constructor facts from the source's full LHS
and RHS without pretending its query is executable from one anchor. During training, completed sources can
expose the first useful continuation. During normal execution, a source state
is initialized only when a compiled continuation demands receipts from it.
Producer nodes are also represented distinctly in the native finite Cell
registry. Old matching paths and result-switch certificates retain their
serialization; source-only entries encode a null pivot.

`iterate --producer-profile PROFILE --objective rhs-congruence` selects source
rules observed in a Spine trace of the exact input program. It checks the trace
hash and the publication/consumer table types before publishing any output.
The profile proposes admission; typed compiler reconstruction and actual source
execution provide the proof. The profile's visit counts never authorize a
mutation. Producer leaves count against the total catalog budget.

## Concrete learned congruence

[example.json](example.json) records an actual learned Raytrace path:

```text
Add-Gets(orig, Single(e), n)
    -> union Get(orig,n) = e
    -> consumer requests Single(Get(orig,n))
    -> reuse the source's existing Single(e) query receipt
```

The source has no complete single-anchor entry. Its completed-source node makes
this cross-Run proof available. The recorded unit is selected on 2,469 consumer
visits; that is not a count of successful receipt substitutions. Whole-program
successful substitutions are reported separately. The consumer still needs its
other constructor and its scheduled union, so this path does not complete its
entire RHS or eliminate canonical repair.

## Compiler cost

Admitting producers also exposes a large source: Raytrace's initialization rule
contains 27,414 RHS operations. With 2,048 candidate counters, the new catalog
learns successfully but prunes candidate counters. Increasing to 8,192 still
prunes them. A 131,072-counter audit records 17,909 candidates without pruning
in its first round, then spends over seven minutes without finishing the next
round. We interrupt that diagnostic run at 435.199 seconds, preserving its
first checkpoint and sampling the process before stopping it.

Of 1,665 main-thread samples, 1,521 stop directly in proof derivation. The former
implementation reverse-scanned all known facts for every constructor lookup.
The new compiler index keys facts by the complete canonical table/key tuple and
retains the latest donor, preserving the former reverse-scan choice. Appended
facts are indexed incrementally. An equality invalidates the index only if it
changes an already indexed key; deletions invalidate it explicitly. This is a
compiler lookup optimization, not a new equality theory or a runtime repair
algorithm. Congruence closure and delayed RHS union visibility are unchanged.

## Measured outcome

The indexed 131,072-counter audit completes in 326.071 seconds, with checkpoints
at 19.032, 157.722 and 296.416 seconds. It records 17,909 / 24,424 / 24,422
candidates with no counter pruning. Its initial catalog is byte-for-JSON equal
to the unindexed audit's saved initial catalog. The new runtime also reconstructs
an old linear-scan certificate and executes it to the unchanged final graph.
These are diagnostic end-to-end compiler durations, not an isolated speed ratio;
short tests/builds overlapped parts of both audit runs. The source entry selection,
proof semantics and runtime checks did not change with the fact index.

| Case / catalog | Source leaves | Final units | Reused constructor reads | Complete RHSs |
|---|---:|---:|---:|---:|
| sum-bits / staged reference | 0 | 108 | 274 | 165 |
| sum-bits / sources, 2,048 counters | 101 | 208 | 293 | 165 |
| Raytrace / staged reference | 0 | 149 | 31,811 | 18,016 |
| Raytrace / sources, 2,048 counters | 161 | 315 | 34,063 | 18,016 |
| Raytrace / sources, 8,192 counters | 161 | 314 | 34,061 | 18,016 |
| Raytrace / indexed sources, 131,072 counters | 161 | 316 | 34,063 | 18,016 |

The reference can already seed unique matching leaves as roots; the new source
leaves are independent of that matching-entry requirement. Every completed run
stops after two admission rounds, below the 512-unit limit.
The smaller Raytrace counter budgets prune counters (up to 12 / 3 sweeps per
round); the unpruned audit confirms that the current scoring rules find no
additional large win. Total successful reuse increases by 19 / 2,252 constructor
reads, with unchanged reused sets and complete RHS counts. [results.json](results.json)
contains complete rounds; [diagnostics.json](diagnostics.json) separates the
interrupted control, sampling evidence, completed audit and certificate checks.

Seven interleaved fresh-process samples per lane, after one warmup, compare the
same indexed executable with the staged reference and the learned source catalog.
All runs preserve the final graph and semantic schedule. [timings.json](timings.json)
retains the samples, binary/program hashes and complete counters. Inference
excludes setup and export; there are no concurrent builds or training runs.

| Case / catalog | Median inference | Median peak RSS through inference | Root state initializations |
|---|---:|---:|---:|
| sum-bits / staged | 21.257 ms | 153.156 MiB | 0 |
| sum-bits / sources | 21.444 ms | 167.516 MiB | 351 |
| Raytrace / staged | 7.902 s | 1,859.109 MiB | 3,763 |
| Raytrace / sources | 7.926 s | 1,868.312 MiB | 33,123 |

There is **no demonstrated application speedup**: median inference rises 0.88%
and 0.30%. Root states cost work and space even when a subsequent use does not
materialize. Raytrace's constructor requests fall from 2,064,892 to 2,062,640,
but dependency repairs remain 643,609 and effective unions remain 226,523. The
new abstraction and cheaper proof lookup are useful capabilities; source-node
admission alone has not removed rebuild as a performance obstacle. This stays
opt-in and does not replace the frozen default catalog.

## Validation and remaining scope

168 all-feature workspace tests pass, with four existing tests ignored. The
completed-producer fixture also passes with the non-sparse iterative backend.
It constructs a producer with disconnected query inputs and no complete anchor,
learns its first edge, and reuses two consumer RHSs without changing the final
graph. Invalid producer indices, duplicate roots, root-as-consumer joins and
schema relabeling are rejected. A mismatched profile fails before creating an
output directory. The fact-index differential test compares latest-donor choices
with the former reverse scan through appends, equalities and deletions.

Every completed learning round compares its graph, semantic schedule and ordered
RHS-input digest with its initial round and with the previous staged catalog.
Learning is bounded replay and recompilation; there is no in-process catalog
replacement, GPU executor or concurrent repair implementation.

## Reproduce

Start with a learned complete-stage program from the preceding experiment. Use
fresh output paths and preserve the input used to collect the profile.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,spine-shapes --bin eggfuse-cell-runtime
target/release/eggfuse-cell-runtime --program PROGRAM --output out/producer-profile
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --bin eggfuse-cell-compiler
target/release/eggfuse-cell-compiler iterate --program PROGRAM --producer-profile out/producer-profile/spine-shapes.json --output out/producer-learn --objective rhs-congruence --rounds 6 --max-depth 8 --max-nodes 16 --max-units 512 --new-per-round 16 --candidate-slots 131072 --min-support 2
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --features iterative-bake --test compiler completed_producer_receipt
```

The sum-bits run uses 2,048 counters. The unindexed compiler is retained locally
as the control; its interrupted unpruned audit is not reported as a completed
measurement or used as a final learned program.

`collect.py` accepts a JSON manifest of completed reference/variant directories
and rejects differing compiler semantic stamps. The interrupted audit is kept
only in the diagnostic record. Runtime samples use the preceding experiment's
`measure.py`, with `sparse-cells,view-ports,storage-metrics` and no `spine-shapes`.
