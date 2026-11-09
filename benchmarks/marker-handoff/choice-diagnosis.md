# Why the saved native graphs differ

The sum-bits `TermAndCost` discrepancy reported in `6675043a` is an
order-sensitive equal-cost choice. This diagnosis uses the existing saved
exports; it performs no workload or timing rerun.

The [source](../../workloads/pass3/inputs/common-prefix.egg) defines:

```lisp
(function ExtractedExpr (Expr) TermAndCost :merge (Smaller old new))
; In terms-helpers-helpers:
(rule ((= lhs (Smaller (TCPair t1 cost1) (TCPair t2 cost2)))
       (= cost1 cost2))
      ((union lhs (TCPair t1 cost1))))
```

An equal-cost tie retains the left candidate, so changing encounter order can
change the selected term and the associated Smaller equalities. In the first
concrete difference, both candidates cost 5:

```text
(Arg[1] / Arg[2]) * 2
2 * (Arg[1] / Arg[2])
```

The source already contains both Add and Mul commutativity rewrites. The
diagnostic recursively uses only these identities; it does not assume that
equal cost implies equivalent computation, reorder subtraction/division, or
apply other algebraic identities.

| Saved-state comparison | Different selected terms | Cost differences | Different hoist choices |
|---|---:|---:|---:|
| Native unmarked → native legacy marker | 10 / 98 | 0 | 0 |
| Native legacy marker → standalone legacy | 10 / 98 | 0 | 1 |
| Native legacy marker → native values marker | 0 / 98 | 0 | 0 |
| Standalone legacy → standalone values | 0 / 98 | 0 | 0 |

For all four comparisons:

- All 98 selected results belong to the current candidate set and have its
  minimum cost. All selected terms agree after Add/Mul normalization.
- Each side has 192 raw PotentialExtractedExpr candidates. Normalizing only
  Add/Mul gives the same 185 distinct `(Expr, term, cost)` candidates.
- The non-term tables, excluding the separately checked `to-hoist` selector,
  have an exact typed graph bijection: 2,374 rows and 1,583 Eq values. This
  includes Expr equalities, scalar attributes and visibility.
- The `to-hoist` difference is another source-defined choice: `:merge new`
  selects among four eligible maximum-size candidates, all size 1. Both chosen
  rows satisfy the original `is-inv-Expr`, DoWhile, Base type and maximum-size
  conditions. This is a different legal optimization choice; the two chosen
  expressions are not claimed equal to each other.

The strict full-graph check is still unequal. Concrete selected term syntax,
Smaller structure, term-dependent caches, TermSubst rows and marker histories
are not required to be identical by this diagnostic. Their arbitrary omission
would not prove correctness; the separate positive obligations above explain
the observed choices and preserve exact checking of the non-term graph.

This establishes that these saved sum-bits states show equivalent extraction
choices and unchanged core equality, not a newly demonstrated program-semantics
bug. It does not prove that every workload or every intermediate Run permits
the same choices. ExtractedExpr is consumed by later optimization rules, so
general validation should check candidate legality, cost, supported semantic
equivalence and visible effects, while keeping deterministic-state checks as
a separate property.

Reproduce the read-only diagnosis:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py \
  out/marker-handoff out/marker-handoff/choice-diagnosis.json
```

[choice-diagnosis.json](choice-diagnosis.json) records input hashes and the
specific first difference. Negative checks rejected a changed selected cost,
a selection outside the candidate set, a division operand swap, and a changed
core visibility bit. The diagnostic is separate from [audit.py](audit.py) and
does not turn its failed strict comparison into a pass.
