# Runtime egraph compression: baseline, not a proof of compression

The compile-time stage sharing result does not establish runtime compression.
This census executes the actual Cell runtime and samples graph-owned storage
at every source Run boundary. Arc/Rc-backed arrays are counted once by owner
address. Counters are retained capacities, not accumulated allocation traffic.
It does not mutate representation or claim savings.

Reproduce:

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_census -- PROGRAM OUTPUT
```

The recorded run used `out/cell-local-writes/semantic/sum-legacy/program.json`,
local-congruence Graph construction, serial Executor, and 1,428 Runs. The source
artifact identity is saved in `runtime-storage-baseline.json`. This is a
working-tree observation with concurrent runtime changes, not an isolated
performance baseline. It makes no native egglog semantic acceptance claim.

Final graph-reachable Cell/function storage counted 1,664,560 bytes:

| Component | Bytes |
|---|---:|
| Cell arena records | 491,520 |
| Cell ID positions | 32,768 |
| Cell slot arrays/shared frame owners | 473,472 |
| Fact record capacities | 292,752 |
| Unique decoded row arrays | 102,384 |
| Function records | 163,840 |
| Function key arrays | 75,056 |
| Function decoded directory | 32,768 |

The separate published-history report totals 17,248 bytes in owners, result
arrays and Rc headers. Even removing all of that reported payload saves only
about 1% relative to the counted graph storage. Compile-time stage sharing
cannot justify a claim of comparable runtime savings. The live graph has 2,385
Cells, of which 1,747 have one fact; 211 have no facts but may retain necessary
parent/writer dependencies. Neither category can simply be deleted.

The census explicitly excludes allocator overhead, Value-owned data, graph
indexes, union-find, removal BTree nodes, ID outlier maps, function writers,
ownership backends, and executor storage. Its subtotal is NOT total egraph
heap or RSS. A significant subtotal reduction would still not by itself prove
significant whole-runtime compression. No such reduction has been implemented
or measured in this change.

Required next evidence: extend the same census to the excluded graph indexes
and retained writers, measure their overlap/ownership, and compare a real
instance/index representation change on identical source Runs. Preserve
constructor existence, mutable values, source effects, visibility and current
minimum-cost extraction; prove reduced retained or peak storage with the same
semantic contract. Do not substitute fewer exports or compiler descriptors.

## Actual heap comparison and limits (2026-11-12)

`runtime_storage_comparison` runs two actual Cell Graphs from the same Program.
One lane reclaims Vec capacity at each idle Run boundary; it does not discard
facts, substitute templates, invalidate instances or alter indexes. Shared
prefixes are compacted only with unique ownership (`Arc::get_mut`); shared
allocations are never cloned merely to shrink them. This is an opt-in
storage-metrics diagnostic, not a new default runtime policy.

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_comparison -- out/cell-local-writes/semantic/sum-legacy/program.json out/runtime-storage-comparison.json
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,storage-metrics --lib slots::frame::tests
```

The allocator counts requested live heap bytes. Both Executors are dropped
while retaining their Graphs, then both source Programs are retained while the
Graphs' other fields are dropped. This includes Graph-owned union-find,
indexes, writers and ownership backends. It excludes source Programs,
Executor caches, stack storage and allocator padding/RSS. It measures retained
final heap, not the within-Run high-water mark. Per-field release attribution
charges a shared allocation to its last owner in the stated drop order.

| Measurement | Baseline bytes | Compacted bytes | Reduction |
|---|---:|---:|---:|
| Graph-exclusive requested final heap | 3,979,373 | 3,484,765 | 12.4% |
| Counted array capacities, boundary peak | 1,902,336 | 1,407,728 | 26.0% |

All 1,428 source Run boundaries retain exact exported graph equality and
ordered RHS/write/resume audit equality, including continued execution after
compaction. The shared-prefix mutation/reattachment unit tests also pass.
This is a same-source representation check, not native egglog acceptance or
a performance benchmark. The branch has concurrent unrelated runtime edits;
both lanes use the same binary. No speedup claim follows from this run.

The actual field-release diagnostic identifies 1,013,984 bytes in ownership
and 390,022 bytes in stable ports, unchanged by capacity reclamation. These
are not all redundant: they include instance bindings, indexes, static shared
code ownership and diagnostic history. Their totals alone do not authorize
removal. Cell storage releases 1,290,512 vs 878,728 bytes; function storage
releases 364,120 vs 293,264 bytes. Shared decoded owners may be attributed to
later fields, so these are ordered release measurements, not independent sums
of every field's reachable storage.

## Structural takeover is the next obligation, not an achieved result

The user-requested compression is different: use observed matched history to
select a compiled dominating Cell, transfer the dominated instance's live
state, and retire the old owner. Capacity reclamation above is only a control.
Current `Graph::new_cell`/`store_cell` projections retain a parent reference;
`slot_fields` reads parent facts and `retire_empty` only removes an unreferenced,
fact-free frame. Iterative dispatch/results inheritance therefore does not
establish takeover of Graph-owned instance/fact/index storage.

A bounded takeover must derive from the same checked Cell operations:

- Compile which live old facts, actual constructor results and slots the new
  Cell covers; distinguish slots already available from new suffix slots.
- Preserve old public fact/result identities. Constructor outputs can be
  implicit functions of the old Cell ID; simply swapping template/ID is wrong.
- Move or reuse uniquely owned slot storage. Branches with other live readers
  need shared ownership or a residual old owner, not unconditional invalidation.
- Preserve pending effects, source Run visibility, mutable reads, retirement
  and generations. A match history proves how we arrived, not that all old
  external uses disappeared.
- Remove the old instance's covered storage/maintenance only after takeover.
  Charge any surviving address projection, residual instance, extra index or
  handoff to the new representation; do not credit just a new dispatch hit.

The relevant target is reduced simultaneous owners/slots/fact metadata during
iteration, including ownership/stable-port state and peak overlap while the
new Cell is installed. Saving a short result-history chain alone cannot prove
large egraph compression. No structural takeover is implemented by this patch.
