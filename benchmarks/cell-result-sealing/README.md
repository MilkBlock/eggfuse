# Seal actual Cell results at their first publication

Control: `6fe472f4`. Scope: **standalone Cell CPU**, not native egglog. This is
a short work/semantic comparison, not a throughput campaign or a 2x result.
The historical fastest control remains `8fffff65`.

## Evidence and takeover

The preceding [union-port experiment](../lazy-union-ports/README.md) compiled
three union states but exercised none in sum-bits. A temporary diagnostic on
that exact v5 program separated missing slots from invalid receipts: all 14 new
failed attempts had a populated result slot for `Single`, but its fact had been
retired and no longer had a forwarding entry. They were not absent captures.

The lifecycle mismatch was concrete: repair records same-key receipt forwarding;
publication uses it to install the surviving Entry; the Cell history still
contains its pre-repair references; then the Run's forwarding map is cleared.
A later valid Cell transition therefore falls back to constructor lookup even
though its producer had already established the result.

The first winning publication now seals its current, exclusively owned result
frame before sharing the Cursor:

1. The original source Run completes repair as before.
2. If this Cell retains results and the existing forwarding map is nonempty,
   inspect its current local slots once and replace relocated receipts.
3. Publish the same owner through the existing Entry/history projection.
4. Continue clearing the ordinary forwarding map at its original boundary.

`Rc::get_mut` proves exclusive ownership. The code does not allocate or clone a
result array, scan earlier history, update other consumers, create a subscriber
index or retain a permanent forwarding table. A projected/shared owner declines
sealing. Mixed frames update only their own local slots. A discarded publication
does not materialize a Cursor merely to perform sealing.

The typed compiler's existing result sources and same-key repair forwarding
supply the proof. Equality of result classes alone cannot redirect a receipt.
The original rule match, actual constructor witnesses, visibility, retirement,
delta ownership and Run/effect order remain authoritative. A later Run can still
retire a previously published result; this change does not solve that separate
lifetime problem. Such misses retain their ordinary validated fallback.

Within this coverage, a scheduled Cell transition can now bypass the repeated
constructor lookup/handoff and temporary RHS/history work it previously fell
back to. No new template or assumption is admitted.

## Actual work and remaining cost

Both lanes use the same v5 program, four query workers, grain 64, canonical
storage, repair ports, Entry publication and absorption. See
[results.json](results.json) for binary/program hashes and all retained counters.

| Complete sum-bits | Before | After |
|---|---:|---:|
| Actual union Cell completions | 0 | 5 |
| All direct Cell completions | 155 | 165 |
| Point queries | 12,085 | 12,070 |
| Handoff attempts | 156 | 136 |
| Direct witness fallbacks | 54 | 44 |
| Temporary effect slots initialized | 7,591 | 7,561 |
| History allocations | 330 | 320 |
| Sealing checks | 0 | 172 |
| Sealing slot reads | 0 | 284 |
| Sealing slot updates | 0 | 65 |

Sixty of the sealing checks decline an already shared/projected owner. Empty
histories and empty forwarding maps are excluded before this ownership check.

Union Cells and direct completions are coverage, not independent saved-operation
credits. The new `history_seal_checks`, `history_seal_reads` and
`history_seal_writes` are charged in Bake Work; shared-owner declines are
included in checks. Missing new-version counters fail credit parsing, while
historical reports have zero sealing work. Hash-chain traversal and elapsed cost
are not isolated by these slot counters. This work does not establish a net
latency improvement from the selected reductions.

Constructor requests fall 8,033→8,023 and union requests 2,439→2,434. Those are
execution work, not committed mutations: created facts, committed unions and
function updates remain equal. The collector keeps request changes visible and
requires equality of the final state, all 1,428 source Run records and committed
effect counts. The regression tests additionally compare every Run's state and
ordered input/write/resume digests.

The first 128 Raytrace Runs do not enter sealing. Point queries remain 74,265;
states and source Run records match. This does not characterize later Raytrace
coverage. No full speed comparison was run; the five-implementation timing
cadence remains in force.

Five successful union completions cannot establish the 2x objective. The next
decision must consider a high-volume surviving reuse opportunity and its
proof-acquisition cost. Merely adding more Cell states, or retaining every old
receipt indefinitely, is not justified by this small coverage gain.

## Validation and reproduction

102 runtime unit tests and 76 relevant compiler/unit/integration tests pass,
including Entry publication, query receipts, scoped/staged completion and state
inheritance. The unchanged sum-bits choice validator returns `pass` / exit 0.
The no-default-feature compile and README compile/run/bench commands pass;
bench repeat 1 is only a command smoke check, not throughput evidence.

The runtime unit test proves that sealing preserves the owner allocation,
updates only current unique slots, leaves shared/earlier frames untouched and
skips empty stages. The new integration fixture unions producer inputs in its
own source Run, causing constructor retirement before publication, then checks
that a later consumer directly completes through the repaired actual results.
Existing deletion, pending-union and phase-boundary tests retain their checks.

Use the v5 inputs produced by the preceding union-port experiment and frozen
normal `query_prefix` binaries. Generated exports and executables remain under
`out/lazy-union-witness`, outside Git. The collector performs short actual
executions and invokes the unchanged sum-bits semantic acceptance entrypoint:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports --example query_prefix
python3 benchmarks/cell-result-sealing/check.py BEFORE_QUERY_PREFIX AFTER_QUERY_PREFIX V5_PROGRAM_ROOT SAVED_SEMANTIC NEW_OUTPUT
```

`V5_PROGRAM_ROOT` contains `sum-v5-baked/program.json` and
`ray128-v5-baked/program.json`. Reproduce the prior compiler/emitter steps as
documented in the linked experiment. Run without Python `-O`.
