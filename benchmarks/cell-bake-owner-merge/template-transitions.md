# Cross-stage reuse keeps the actual source template

The previous constructor outcome archive recorded actual `(Cell, operation)`
addresses, but retired sources could no longer be associated with their template
from a final storage snapshot. Composition frame codes are not template IDs.
This lost precisely the short-lived applications needed for reusable closure
learning. Generic constructor outcome events now also record the actual current
RHS source template. Missing frames produce an explicit null, never a guessed
identity. This is behind `storage-metrics` and the existing bounded observer;
normal execution does not consult or retain the archive.

The offline analyzer groups observed visible reuse as:
`(producer template, producer operation, consumer template, consumer operation,
table, same/cross Run)`. Actual IDs join events only; they are not part of the
shared transition key. It retains a birth in the analysis only until an observed
retirement. Hidden results, unknown live births and unknown templates are charged
separately. A table mismatch fails analysis. Forwarding and unsupported fast
publication paths do not acquire invented provenance. These counts are observed
reuse opportunities, not skipped RHS operations or a saturation certificate.

The existing receipt-observer integration test checks traced/untraced snapshots,
ordered binding audits, final state, and that each recorded operation really
belongs to the stated source template and table. It passes; the runtime also
passes a no-default-features compile check. Seven offline tests cover live-birth
reuse, retirement, missing templates, schema/coverage loss and wrong tables.

For the batch, copy each `prefix-all/CASE/{candidate,selection}.json` to the fresh
`template-source-audit/CASE` directory under `out/cell-bake-owner-merge/batch`.
Run once through the shared compute queue:

```sh
cargo build --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit --example batch_cell_learning
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch template-source-audit receipt-trace
python3 benchmarks/cell-bake-owner-merge/constructor_lifetimes.py out/cell-bake-owner-merge/batch/template-source-audit/checked.json benchmarks/cell-bake-owner-merge/template-transitions.json
```

The batch compares every saved Run and the terminal state before emitting its
report. The result records the exact archive hash and each Program digest.
This measures the actual standalone Cell CPU with diagnostic observation, not
native egglog acceptance or performance. A missing new identity schema cannot
support this experiment, even if an older lifetime-only report can still parse.

## Audited batch and next executable target

All 2,652 saved Run checks and four terminal checks pass; no archive dropped
events. Every case contains the new template identity analysis.

| case | cross-Run uses | distinct template-operation transitions | unknown live birth | hidden result |
| --- | ---: | ---: | ---: | ---: |
| fact | 714 | 173 | 98 | 0 |
| loopfact | 508 | 152 | 74 | 0 |
| sum-bits | 3622 | 388 | 453 | 92 |
| dot-product | 2652 | 361 | 291 | 0 |

In all four exact artifacts the highest-frequency family is template 472,
`terms-helpers`, which builds `NoTerm()` then `TCPair(NoTerm(), 10^16)` before
writing `ExtractedExpr(expr)`. Each of its two constructor operations reuses an
observed earlier-Run result 35/43/186/179 times in fact/loopfact/sum-bits/dot-product.
These template numbers are artifact-local, not cross-artifact canonical IDs.
The typed source confirms this prefix is independent of match inputs. Its later
mutable Set is not covered by that fact and cannot be skipped. The useful next
lowering is shared prefix result acquisition with present-value/lifetime checks,
not retaining every prior application as a history owner. Snapshot/worker
preparation already exists and must not be counted again as a new saving.

Other high-frequency paths depend on query inputs (for example AddContext and
Add-Gets). They need parameterized Entry/closure proofs; the observation alone
cannot turn them into input-independent constants. No trace frequency authorizes
skipping queries, unions, retirement or publications. No runtime memory or timing
improvement is claimed by this observer change.
