# Constructor facts inherited through Cell query rows

The View8 trace identified actual cross-Run producers, but observations cannot
establish a universal invariant for a materialized handoff. This change adds a
compiler-only all-writer induction checker over typed Cell query/effect definitions.
It reuses the existing `Construction` environment for copies and repeated
constructor results. No runtime fact graph, consumer list, per-instance binding,
or dispatch path is added.

A candidate maps a constructor's inputs and output onto a Unit/merge-old
function's key columns. The checker requires an empty initial relation, matching
types, no deletion or hiding of the constructor anywhere, and checks every
source writer at the actual Set position. Matched constructors and earlier
constructor effects establish facts. A query of the same handoff may assume
the candidate invariant; every writer must preserve it. Empty initial state is
the induction base. A future construction, mutable read or queued union cannot
supply missing evidence. This is scoped to a closed source Program; arbitrary
external insertion through Graph APIs is not certified.

## Findings on the current typed program

- 41 constructor relations are established across 26 function relations.
- Those functions have 318 final live rows in the previously audited runtime.
- All key columns are covered for functions containing 208 of those rows.
- Four RHS positions can obtain their result value through a query slot:
  rules 250, 449, 452 and 507. This is not four eliminated lookups yet.

For View8, all six writers preserve both:

```
PotentialExtractedExpr(column 1, column 2) = column 0
TCPair(column 3, column 4) = column 2
```

For rule 507 operation 2, query atom 3 slot 7 is therefore the actual result
value of `TCPair(slot 8, slot 4)`. This proof includes the completion writer,
the untraced rule 503 and recursive rule 507; it does not assume observed paths
are exhaustive. Its mutable `ExtractedExpr` read and comparison remain live.

## Execution boundary still to implement

A value slot is not a constructor `FactRef`. Existing `static_sources` entries
identify actual query/effect receipts, so using the View's query site there
would mislabel a functional row as a constructor fact. No such plan is enabled.
The next execution change must distinguish value-only use from outputs that
publish or retain an actual constructor receipt, reusing the producer's real
receipt where available. It must preserve boundary enumeration and source Run
visibility before eliminating intermediate rows/indexes. Complete column
coverage alone does not establish those obligations or a smaller layout.

These results guide compression but do not demonstrate it. There is no new
runtime heap or speed result and no new semantic behavior. Existing semantic
results are not presented as validation of a future takeover.

## Checks and reproduction

All 154 runtime library tests pass with sparse-cells, iterative-bake and
storage-metrics. Five new tests cover all-writer/self-forwarding induction,
unproved initial rows, deletion, future construction, repeated constructors,
queued union rejection, deletion of an input constructor between query and RHS,
and discovery without manufacturing a receipt.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,iterative-bake,storage-metrics --lib
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example entry_constructor_proofs -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/entry-constructor-proofs.json
python3 benchmarks/cell-structural-compression/analyze_entry_constructor_proofs.py out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/entry-constructor-proofs.json out/cell-structural-compression/completed-symbolic-audit.json benchmarks/cell-structural-compression/entry-constructor-proof-results.json
```
