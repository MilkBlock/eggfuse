# History-selected finite closure transfers

This iteration adds a typed compiler prerequisite for jumping to a saturated
Cell, not an executable skip policy. Existing `extension` only proves completed
fact inclusion and still requires consumer matching. The stronger transfer
classifies additional assumptions, inherited-port restrictions, new facts and
ordered union obligations. It references ordinary Cell definitions and canonical
compile-time structures; runtime facts/bindings are not duplicated.

`saturated` means no new constructor facts, entry assumptions, strengthened
prefix ports or pending unions for this selected finite extension.
`internal_completion` needs no external assumptions but has new constructor
facts or source-ordered unions. `guarded` retains external facts, new equalities
between old ports or stronger type/literal constraints. Unsupported source
operations remain unsupported. These are application/state classifications,
not permanent global rule categories or whole-program saturation.

The ordinary proof leaves unions pending. A separate conditional proof settles
each prefix stage **after its source Run and repair**, then computes congruence
before the next stage. It does not apply a union early inside its own RHS. The
last stage's new unions remain ordered obligations. Runtime use will require
that explicit boundary precondition, actual result receipts, liveness,
visibility and delta ownership. No flag alone establishes saturation.

## Evidence from actual sum-bits history

The observer records 1,428 completed Cursor events, no dropped events; 983 are
roots and 445 have a retained multi-stage path. All 1,428 saved per-Run graph and
ordered RHS/write/resume checks pass, as does specified semantic acceptance.
These are actual standalone Cell-runtime observations, not native egglog
measurements or committed mutation counts.

Without settling prefix unions the compiler recognizes only 3 internally
completable events, 14 guarded events and 428 unsupported events. Offline
rechecking **the same trace**, with every prefix boundary checked against the
actual ancestry's strictly increasing Run indices, yields:

| Conditional transfer | Completed events |
| --- | ---: |
| Saturated finite extension | 209 |
| Internal completion | 57 |
| Additional guards required | 127 |
| Unsupported | 52 |

The dominant missed route (162 events) first establishes
`Single(Get(expr,i)) = SubTuple(expr,i,1)`, then applies the inverse constructor
rule. The earlier compiler left the prefix union pending indefinitely. This is
why simply lengthening histories did not reveal the completed state.

The 57 internal completions carry 57 symbolic new-fact opportunities and 41
ordered-union obligations; these are not allocations or mutation measurements.
The original RHS observer's 373 covered applications contain 888 source ops,
but 500 are lazy Copy operations and none are static aliases. The remaining
388 effects are only an upper bound: dynamic direct completion may already
remove some. They must not be booked as new savings.

## Reproduction and remaining runtime work

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_catalog_trace -- out/cell-structural-compression/baked-lean/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/closure-history.json --closure-history
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example recheck_closure_history -- out/cell-structural-compression/baked-lean/program.json out/cell-structural-compression/closure-history.json out/cell-structural-compression/closure-history-settled.json
python3 benchmarks/cell-structural-compression/analyze_closure_history.py out/cell-structural-compression/closure-history-settled.json benchmarks/cell-structural-compression/closure-history-results.json
```

Rechecking validates the exact Program identity and recompiles proofs from
source paths; historical counts never authorize equality. Pair samples overlap
events and are reported separately. Existing normalized-contract serialization
is unchanged, preserving prior artifacts. Tests cover new entry facts,
strengthened literals/equalities, pending unions, actual completed chains, and
the settled-union inverse rule. The ripsat integration suite passes 16 tests.

Next lower eligible transfers into the existing direct-completion/result layout
and Entry dispatch, retaining original Run boundaries. Replace covered matching
and intermediate execution, then measure actual query probes, RHS boundary
calls, result projections, publications and new guard/storage costs. This commit
does not yet skip or inject RHS and claims no speedup or compression.

The measured working tree also contains the previously validated, uncommitted
borrowed-field-layout experiment. That unrelated storage change is excluded
from this commit and from all benefit claims here.
