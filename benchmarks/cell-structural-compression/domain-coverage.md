# Complete Cell domains and compact cross-stage query classes

The preceding domains-only execution still paid 50,851 legacy reverse-index
visits. The installed owned-row count already proves that every live row of a
fully covered table occurs in Cell wiring. Those visits cannot contribute any
candidate. Domain planning and enumeration now exclude that residual path when
coverage is complete; partial tables retain it. No new per-instance certificate,
subscription or cached binding is added. Choosing the domain without unrelated
legacy uses changes the heuristic, so its extra exact candidates are charged.

The actual program also lacked the existing cross-stage query-class plan.
Classes conservatively close possible operators over every allowed Entry
substitution, so old ports keep their class when later stages activate. They
filter groups before visiting instances; they do not prove equality or visibility.
All exact comparisons, pending collision ordering and live-state checks remain.

Simply enabling materialized classes added 784,667 bytes of retained Program
storage. The non-materialized ownership compiler now emits `query_classes: true`
instead of another copy of the certificate arrays. This requests derivation from
authoritative typed Cell definitions during preparation, using the same existing
fixed point. It is not an unchecked assertion about candidate coverage. Explicit
materialized certificates still use the existing validator. Iterative completion
preserves this derivation option instead of expanding it back into JSON.

## Actual standalone runtime results

| Work | Prior domains-only | Complete coverage | Coverage + classes |
| --- | ---: | ---: | ---: |
| Legacy reverse visits | 50,851 | 0 | 0 |
| Signal visits | 147,071 | 146,302 | 35,920 |
| Template slice steps | 156,012 | 157,395 | 65,064 |
| Exact candidate checks | 16,972 | 17,656 | 17,656 |
| Class probes | 0 | 0 | 96,073 |
| Whole class range jumps | 0 | 0 | 67,943 |

The exact-candidate increase comes from domain selection, not class filtering.
Filtering preserves the selected domain's 22,165 candidate results. Do not count
all these logical candidates as committed mutations or skipped rule applications.
There is no timing claim; fewer instance accesses do not erase class-probe costs.

| Requested heap | No classes | Materialized classes | Derived classes |
| --- | ---: | ---: | ---: |
| Graph | 2,684,181 | 2,682,261 | 2,682,261 |
| Retained Program | 117,230,752 | 118,015,419 | 117,310,933 |
| Execution/transfer process peak | 125,379,947 | 126,162,687 | 125,458,209 |

Derivation removes 704,486 bytes compared with materialized class metadata.
Against no classes it still costs 80,181 Program bytes and saves only 1,920 Graph
bytes: net **78,261 additional bytes**. This is an optional query-work tradeoff,
not a new large compression win. Combining classes with the preceding deletion
of birth indexes still saves 22,539 Graph+Program bytes against hints without
classes, but its timing remains unmeasured. The default does not force classes.

All 1,428 saved Run graph and ordered RHS/write/resume hashes pass in both new
execution configurations; final exports exactly match and semantic acceptance
passes using the equal saved export. The materialized-class lane has a final-state
heap observation, not another full boundary audit. The source comparison verifies
that only optional class representation changed. Tests: 37 ownership and 21
ripsat completion tests; default runtime Cargo check. The ownership test compares
materialized and derived plans and Run/binding audits; the ripsat test ensures
iterative completion preserves derivation and still rejects invalid type proofs.

## Reproduction

Run the prior domains-only audit with current code to
`out/cell-structural-compression/domain-coverage-audit.json`. Compile classes with:

```sh
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics -- bake-cell-ownership --program out/cell-structural-compression/closure-existing/program.json --query-classes true --materialize-markers false --output out/cell-structural-compression/domain-classes-derived
```

Use its `program.json` in the same audited runtime and heap commands from
`domain-only.md`, naming outputs `domain-classes-derived-audit.json` and
`domain-classes-derived-heap.json`. The materialized historical lane was compiled
before this change, when non-materialized markers still retained class JSON.
To reproduce that representation with current code, first run
`bake-cell-ownership --query-classes true --materialize-markers true` into a
temporary output directory. Feed that program to a second
`bake-cell-ownership --materialize-markers false` invocation, omitting the
`--query-classes` option; this preserves its materialized class object while
removing marker JSON.
Finally:

```sh
python3 benchmarks/cell-structural-compression/analyze_domain_coverage.py out/cell-structural-compression benchmarks/cell-structural-compression/domain-coverage-results.json
```
