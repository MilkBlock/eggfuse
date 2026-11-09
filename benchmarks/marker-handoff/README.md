# Forward results through the generated .egg marker

This is an opt-in source compiler experiment on the standalone Cell CPU, based
on `7725da71`. Use `--marker-handoff values`; `legacy` remains the default and
reproduces the frozen sum-bits recipe hash. See [design.md](design.md) for the
opportunity and proof obligations recorded before implementation.

The marker already contains the correlated constructor outputs. The old emitter
removed their original LHS atoms but left nested constructor calls in the RHS.
The new emitter uses the bound outputs directly. Schematically:

```lisp
; Marker proves f = F(x), g = G(f).
(rule ((CellSpineView0 f x g) (Edge x n))
      ((Out g n)) :ruleset consume)
```

The old RHS was `(Out (G (F x)) n)`. Production likewise publishes the actual
returned `f` and `g` variables, even when construction reused existing nodes.
The frontend lowers these ordinary variables into existing parameter slots.
There is no producer-address guess, extra receipt capture, marker field or
runtime reverse list. Marker identity plus the consumer rule selects the
residual continuation; the original schedule still decides when it runs.

The pass excludes deletable/subsumable constructors, keeps residual mutable
reads and numeric guards, preserves evaluation order, and renames generated
bindings hygienically. Completion rules remain necessary for initial facts and
new union-enabled bindings. This does **not** remove all completion, Pending
publication or parallel preparation paths.

## Short workload evidence

One diagnostic execution per mode, using the same frozen runtime executable,
with `--local-congruence`. Both programs were compiled from the same sum-bits
source and training input **without a learned catalog**. The old catalog is
bound to the old recipe and cannot be copied into the rewritten program.

| Actual work | Legacy .egg | Forwarded .egg |
|---|---:|---:|
| Key lookups | 19,674 | 19,118 |
| Execute allocation calls | 197,325 | 196,308 |
| Execute reallocation calls | 21,167 | 21,167 |
| Execute requested bytes | 35,542,954 | 35,459,690 |
| Setup allocation calls | 106,205 | 103,298 |
| Setup requested bytes | 11,073,761 | 10,817,378 |
| Fragment Pending writes | 5,505 | 5,264 |
| Fragment Pending reads | 4,533 | 4,531 |
| Publication slot probes | 7,134 | 6,893 |

The lookup decrease is 556 (2.83%). This is removed work, **not an end-to-end
speedup measurement**. It is not directly comparable to the prior 19,222-lookup
run with a learned catalog. No Raytrace or timing campaign was run here.
Allocation counts exclude program parsing; requested bytes are not RSS.

Static diagnostics report 126 rewritten rules, 50 substitutions in original
RHS actions, 107 in generated publication actions, and 200 captured constructor
results. These count source occurrences, not runtime savings or mutations.

## Verification and an inherited discrepancy

The two standalone variants have equal ordered Run fields and exactly
isomorphic states; raw Eq IDs change with the recipe. The comparator propagates
a bijection through complete keys, then checks every typed row, scalar,
visibility bit and initial anchor. It fails on unresolved graphs. Native
egglog also produces equivalent final states for the two marked sources.

The stricter independent whole-graph controls **do not all pass**. Follow-up
diagnosis identifies order-sensitive choices in the saved sum-bits states,
rather than evidence of a changed program computation. `ExtractedExpr` merges
with `Smaller(old, new)`, whose equal-cost rule selects its left operand. The
source's `to-hoist` function similarly uses `:merge new` among maximum-size
legal candidates. See [choice-diagnosis.md](choice-diagnosis.md).

Across native unmarked/marked and native marked/standalone, all 98 extraction
costs agree. Each selected term is a current minimum-cost candidate. The 10
different selected terms in each comparison agree under the existing source
Add/Mul commutativity rules; their candidate sets agree under those same rules.
The non-term graph has an exact bijection over 2,374 rows, including Expr
equalities and visibility. Native versus standalone also chooses a different
legal size-1 hoisting candidate. The new values emitter changes none of these
choices relative to its legacy counterpart.

`full_native_validation: false` remains the result of the **strict** historical
whole-graph check; it is not a program-semantics failure verdict. The diagnostic
does not erase or relabel that check as passed. It proves the stated final-state
properties, not complete cross-engine Run histories or generated-code execution.
The change remains experimental and still needs catalog/performance acceptance.

The five new small regressions check native original/marked projection,
native/standalone agreement, and per-Run structural equivalence. They cover
existing results, residual expansion, union, late activation, deletable and
subsumable tables, mutable conditions, and RHS alias forwarding. The compiler
all-features suite passes 214 tests; the five new tests also pass without
sparse-cells. See [comparison.json](comparison.json) and
[validation.json](validation.json) for exact scope and provenance.

## Reproduce

Reconstruct `sum-bits.egg` from its `parts` in `workloads/pass3/suite.json`, and
`training.egg` from the suite's `bake.parts`. For each `MODE` (`legacy`, `values`):

```sh
cargo cell-compile --source out/marker-handoff/sum-bits.egg \
  --bake-source out/marker-handoff/training.egg --marker-handoff MODE \
  --output out/marker-handoff/sum-MODE
```

Build the runtime **alone**, with
`sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes,allocation-metrics`.
Run both artifacts with `--local-congruence` into `run-MODE`. Repeat separately
with `--audit-stages` into `stages-MODE`; do not use audited allocation counts
as the diagnostic counters above. Build the compiler's `marker_reference`
example and run it on the unmarked `source_sk.egg` and both `source_sk_mk.egg`
files, writing `native-source.json`, `native-legacy.json`, `native-values.json`.

```sh
python3 benchmarks/marker-handoff/audit.py out/marker-handoff
```

The audit streams large stage snapshots and retains compact proof counts.
Generated sources, binaries and full snapshots stay under ignored `out/`.
