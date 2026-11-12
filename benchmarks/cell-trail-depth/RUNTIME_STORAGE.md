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
