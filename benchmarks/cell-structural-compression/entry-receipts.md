# Actual donor availability behind Cell Entry proofs

The all-writer proof now records the original `Site` that supplies each
constructor result. Copies and duplicate constructors preserve that site.
A query site that reads the View itself is an inductive proof source, not a
constructor receipt; the consumer must not reinterpret its function-row handle.
These are shared compiler descriptors only. No new instance storage or lookup
path is enabled.

A diagnostic execution checks the current standalone Cell runtime using the
same natural/shared-owner/parent-takeover/domains-only lane as the accepted
completed-symbolic control. At the final boundary it reads each proven View
row, finds its actual writer context, and checks a direct effect donor by
visibility, table and ALL projected fields including the output. It performs
no hash-lookup fallback and never treats a synthesized address as proof.

## View8 results

| Proven constructor | Resident original fact | Query receipt required | Actual returned receipt required |
| --- | ---: | ---: | ---: |
| PotentialExtractedExpr | 127 | 65 | 0 |
| TCPair | 94 | 65 | 33 |

All 192 View8 rows have recognized source contexts. For TCPair, 98 of them
cannot supply a physical fact through the original producer operation alone.
The 33 absent effect facts require actual returned receipts, because a
constructor operation may reuse another instance's fact. They are not evidence
that the promised constructor does not exist. This diagnostic does not search
for it to mask the missing retained reference.

Across all 41 proven relations, the census counts 230 resident original
constructors, 147 query-receipt obligations, 42 actual-result obligations and
103 inductive-query sources. These are 522 relation/row obligations over 318
View/function rows, not 522 distinct allocations. They must not be summed as
saved fields, queries or bytes.

## Consequence for implementation

Existing consumer matching must retain the relevant Entry receipt before
producer context can be used. The saved View8 matches have partial continuation
but no parent binding and no direct token; final donor availability does not
mean the consumer already has it. Producer query donors and foreign result
donors need their actual references in the existing result layout. Inherited
View donors need the earlier proven export, not a fabricated constructor
FactRef. The compiler must wire these sources into shared result layouts and
remove the replaced field/packet storage rather than maintain both indefinitely.

This narrows the required retention to proven live exports. It is not yet the
runtime takeover or large-compression result. Mutable reads, Run visibility,
residual enumeration and generation/retirement checks remain authoritative.

## Validation

154 runtime library tests pass. Existing induction and duplicate-constructor
tests now also check that donor sites remain the original query/effect position.
The census executes 1,428 Runs and checks its exact final export against the
previously audited control. It does not repeat per-Run ordered auditing or
measure speed/heap; no execution semantics changed.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,iterative-bake,storage-metrics --lib
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example entry_receipt_census -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/completed-symbolic-audit.json out/cell-structural-compression/entry-receipt-census.json
```

The generated census is copied to `entry-receipt-results.json`. The original
proof-report reproduction remains in `entry-constructor-proofs.md`; writer
records now include the donor site as well as rule and Set position.
