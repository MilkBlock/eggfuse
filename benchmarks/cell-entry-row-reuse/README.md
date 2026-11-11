# Refresh private Cell Entries in their existing row storage

Control: `4ebea808`. This is the standalone Cell CPU executor, not native
egglog. The measurements below count allocations in bounded executions; they
do not establish a speedup, a 2x result, or general egraph sparsity.

## Opportunity and compiler evidence

The last complete catalog execution recorded 2,052,570 private Entry row reads.
Its `Expr-size` family dominates query time, but semi-naive ownership already
rejects matches without a relevant delta. A changed input can legitimately
produce an unchanged minimum, so input memoization alone does not remove those
matches. The previous publication study also showed why unchanged writes cannot
simply discard their continuation responsibility.

Entry refresh had a separate cost: it decoded a current row and allocated a
new `Rc<Row>`, even when the old Entry row had no remaining reader. The compiler
already identifies tables with one Entry node and gives that node's complete
literal/repeated-column predicates. Another Bake iteration is unnecessary to
recover these facts; runtime exclusivity still requires a lifetime check.

For these private nodes, refresh now moves the old packet and checks
`Rc::get_mut`. A unique owner replaces the row in its existing allocation.
An outstanding strong or weak reference takes the old allocation path, keeping
snapshots immutable. New and recreated Entries still allocate. Tables with
multiple Entry nodes retain their shared row cache.

This is the **outer Entry row**, not the graph's shared `Arc<[Value]>` decoded
fields. Those fields keep their existing ownership and immutability. There is
no new binding copy, fact graph, invalidation table or subscription list.

Sparse Entries also no longer compare the whole old and new row to decide
whether to reuse a parameter vector: they already project the row directly.
They evaluate only the compiled Entry predicates. Identity Entries have none;
filtered Entries still check the current required columns. The legacy
`parameter_packets_reused` counter remains for the nonsparse implementation;
it is zero in the sparse path. `row_reuses` now counts actual allocation reuse.

## Costs and live obligations

Every eligible existing row pays one reference-ownership check. A shared owner
still pays the allocation. Three executor-wide counters add 24 bytes; no
per-Entry layout grows. Filtered Entries no longer have a whole-row equality
shortcut and always execute their compiled predicates. Decode, current epoch,
visibility, pending-row processing, forwarding, retirement and all consumer
watermarks remain live. No query, source effect, publication or Run is skipped.

This reuses storage across Runs but does not establish a scheduled block-switch
proof for skipping computation. Its evidence concerns Entry ownership locality,
not the fanout of semantic changes through the egraph.

## Bounded allocation results

One allocator-instrumented execution per lane uses the same frozen program,
repair ports, Entry publication and four query workers. Exact final graphs,
ordered Run records, graph effect counts, table queries, publication/history
counts and all Entry counters except the obsolete parameter-reuse proxy agree.

| Work, before → after | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Allocation calls | 81,619 → 81,033 | 2,327,985 → 2,325,463 |
| Reallocation calls | 13,474 → 13,474 | 343,478 → 343,478 |
| Cumulative requested bytes | 19,617,059 → 19,574,867 | 961,068,812 → 960,887,228 |
| Successful row reuse | 586 | 2,522 |
| Reuse blocked by shared ownership | 0 | 0 |
| Table queries | 12,085 → 12,085 | 578,591 → 578,591 |

Each observed reuse reconciles with one fewer allocation and 72 fewer requested
bytes in these samples. Cumulative requests are not live or peak memory. Fresh
rows dominate the short Raytrace prefix; it does not represent the late repeated
attribute updates in the full profile. Do not extrapolate these counts to full
Raytrace or use instrumented inference time as a throughput result.

## Validation and reproduction

97 runtime unit tests and 47 integration tests pass. New tests cover outstanding
row readers, shared decoded fields, weak references, and a changed filtered
Entry that must stop matching. Existing tests cover source-order/resume audits,
worker snapshots, union forwarding, deletion/recreation and scoped publication.
The reviewed sum-bits acceptance passes without changing its proof rules.
Raytrace has a bounded relative comparison, not a new native proof. Minimal and
all-feature checks and README compile/run/bench repeat 1 pass; the bench is only
a smoke check.

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,allocation-metrics --example query_prefix
PREFIX out/cell-fixed-reads/sum-program.json ROOT/sum 2000 4 64 canonical --repair-ports --entry-publications
PREFIX out/cell-fixed-reads/ray-program.json ROOT/ray1280 1280 4 64 canonical --repair-ports --entry-publications
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-entry-row-reuse/collect.py ROOT benchmarks/cell-entry-row-reuse/results.json
```

Build and save the control helper as `ROOT/before-prefix` and its exports as
`ROOT/sum-before` and `ROOT/ray1280-before`; save the candidate as `ROOT/prefix`.
Use fresh output directories. The semantic directory reuses the reviewed native
artifacts and points `run-values` at the candidate sum-bits output. All binaries,
full exports and build logs stay in ignored `out/`; the collector launches no
workload and records the relevant hashes with compact results.
