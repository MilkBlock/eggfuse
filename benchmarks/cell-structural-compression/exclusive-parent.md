# Exclusive factless-parent takeover: locally valid, no measured workload saving

## Hypothesis

A completed child currently keeps its parent when a required parent column
cannot be read from a shared Eq port. The proposed path copies only the required
residual columns into the child's existing slot array when the parent has no
facts and exactly one retaining reference. It then releases that reference and
lets ordinary source-Run GC retire the parent. It adds no reverse consumer list,
new binding registry, result cache or packed format.

The compiler's retained parent-column plan was extended to include scalar
columns. Runtime admitted a column if it was already local, available through
an equal existing symbolic port, or could be copied from that exclusive factless
source. Shared sources retained the conservative symbolic/local admission rule.
All values were prepared before changing the child, and GC stayed at the normal
boundary.

## Validation and negative evidence

A low-level runtime regression constructs a retained, factless source with two
scalar slots and a child that needs only one. With two parent users, admission
leaves the child unchanged. With one user, one slot transfers, the parent record
is removed by ordinary GC, and the child can still read the value. This tests
storage/lifetime mechanics, not compilation of a new source program. All 39
existing ownership integration tests also passed with the patch applied.

That local result did **not** translate into whole-workload storage savings:

| Actual standalone Cell runtime metric | Current implementation | Experiment |
| --- | ---: | ---: |
| Complete Graph requested heap | 2,617,317 B | 2,617,317 B |
| Complete retained Program heap | 117,318,509 B | 117,318,989 B |
| Ordinary source records | 1,598 | 1,598 |
| Execution/takeover process peak | 125,400,997 B | 125,401,475 B |
| Growth above setup | 5,570,091 B | 5,570,091 B |

All measured Graph field teardown values are unchanged. Final graph digests
match after 1,428 Runs. This is the allocation lane; a new full ordered
Run-boundary audit was not run for the rejected patch, and final equality is not
reported as a substitute. There is no timing claim. Unchanged final storage does
not establish that the candidate was never entered during execution.

The extra compiler layouts cost 480 B and the experiment gives no measured
compression. The runtime changes were therefore removed; the current branch
keeps `25b79d1e` behavior. `exclusive-parent.patch` preserves the implementation
and regression for reproduction, not as an enabled optimization.

The result rules out treating exclusive scalar-parent copying as the principal
compression fix on this catalog. Further work needs actual retained-source read
coverage, including shared references and fact lifetime, before choosing a
source-record retirement policy. Merely demonstrating that one artificially
exclusive source can retire is insufficient.

## Reproduction

Apply the tracked patch to the restored runtime before running these commands:

```sh
git apply --check benchmarks/cell-structural-compression/exclusive-parent.patch
git apply benchmarks/cell-structural-compression/exclusive-parent.patch
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,iterative-bake,storage-metrics --lib exclusive_factless_source
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test cell_ownership
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/exclusive-parent-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_exclusive_parent.py out/cell-structural-compression/completed-symbolic-heap.json out/cell-structural-compression/exclusive-parent-heap.json benchmarks/cell-structural-compression/exclusive-parent-results.json
git apply -R benchmarks/cell-structural-compression/exclusive-parent.patch
```
