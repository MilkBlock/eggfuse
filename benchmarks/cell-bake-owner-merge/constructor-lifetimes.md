# Explain missing owned operations using actual constructor outcomes

The final membership census could not distinguish a reused constructor from a
locally created fact retired by later work. The existing bounded receipt archive
now records successful generic constructor outcomes: source `(Cell, operation)`,
actual returned receipt, created/reused, visibility and source Run. It uses the
existing retirement events. No runtime reuse index or retained binding map is
added. The new constructor hooks compile only with `storage-metrics`; default
builds incur none of these calls.

The observer covers generic RHS lookup, compiled/immediately compared witness
admission, snapshot witness admission and `insert_constructor` births. Native
aliases eliminated by compilation and other fast publication paths are not
covered. Archive completeness means no event drops within this coverage; it does
not mean every nominal operation was observed. Missing observations remain
unknown. Hidden results remain distinct from visible ones.

## Actual standalone runtime batch

The four seed catalogs were replayed with the current pooled-owner path and a
65,536-event bound per workload. All archives have zero drops. All **2,652 saved
Run graph/ordered-effect checks and four terminal checks pass**. This is Cell CPU
differential validation, not native egglog acceptance or a timing measurement.

Final absent owned positions in completed sources:

| case | absent positions | last result elsewhere | local birth then retirement | unobserved |
| --- | ---: | ---: | ---: | ---: |
| fact | 413 | 213 | 19 | 181 |
| loopfact | 352 | 175 | 24 | 153 |
| sum-bits | 1,466 | 788 | 123 | 555 |
| dot-product | 1,331 | 666 | 79 | 586 |

No position with a last observed local result remains unexplained by retirement.
The categories use the **last observed outcome** at the source operation. They
are not an assertion that the site never created anything earlier. For all
observed generic operations (not just these final sources), the counts are:

| case | reuses | target born in an observed earlier Run | observed births later retired |
| --- | ---: | ---: | ---: |
| fact | 869 | 714 | 51 |
| loopfact | 632 | 508 | 38 |
| sum-bits | 4,469 | 3,714 | 508 |
| dot-product | 3,239 | 2,652 | 286 |

Sum-bits includes 18 reuses of another operation in the same source and 92 hidden
results. Earlier-Run birth is evidence of an actual cross-stage result, not proof
that its current result/visibility may be reused without checking. A missing
retirement event is not final liveness proof. Sources retired before the final
snapshot are excluded from the first table but contribute to event totals.

## Consequence for compression and RHS completion

Most explained holes represent actual returned results owned elsewhere, not
mass retirement of the region's own facts. A template specialization should
therefore describe **local fact membership plus actual-result projection**, not
fill all nominal constructor positions or reserve local result addresses for
reused facts. Keep a local source-sized exception for later ownership changes.

The earlier-Run result counts help prioritize producer/consumer transitions for
Bake, but they are not saved operations. Current event addresses alone do not
recover every retired source's template/wiring, and the unobserved positions
still need coverage analysis. Cross-stage takeover must connect actual witnesses
to the existing shared Entry or continuation, preserve Run visibility and ordered
effects, and remove the replaced lookup/publication work. This change performs
observation only; no new compression or speedup is claimed.

## Validation and reproduction

The integration fixture creates a fact in Run 1, reuses a foreign constructor,
and retires the created fact in Run 2. The trace identifies the exact retired
receipt. Traced/control exports, snapshots and binding audits agree. All 57 ownership integration tests and the default runtime Cargo check pass.
Four offline tests cover prior-Run reuse, retirement/rebirth, unknown births, absent-membership
classification, lost archives, old observer formats and invalid birth addresses.

To repeat the batch, copy `candidate.json` and `selection.json` for each of the
four cases from the saved `pooled-audit` variant to a fresh
`receipt-membership-audit` variant. Then:

```sh
~/.local/bin/eggfuse-job run --kind compute -- env CARGO_INCREMENTAL=0 cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit --example batch_cell_learning -- check-passive out/cell-bake-owner-merge/batch receipt-membership-audit receipt-trace
python3 benchmarks/cell-bake-owner-merge/constructor_lifetimes.py out/cell-bake-owner-merge/batch/receipt-membership-audit/checked.json benchmarks/cell-bake-owner-merge/constructor-lifetimes.json
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/test_constructor_lifetimes.py
```
