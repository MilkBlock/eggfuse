# Attribute propagation: match and write attribution

This extends `CELL_CPU_PROFILE=1` with snapshots of existing counters at each
ordered rule-batch boundary. Ordinary execution allocates no RHS profile
array and records no snapshots. No per-instance trace, binding copy or table
query is added. The report's `query_rule_profile[].rhs` distinguishes matched
bindings, single-write attempts, unchanged writes and actual function updates.
RHS times include ordered application and Cell completion, not final repair or
Entry publication. With scoped completion enabled, any completion work performed
inside application belongs to that batch; it is not an independent source effect.

These are standalone Cell CPU diagnostics, not native egglog throughput. The
complete Raytrace run is one attribution run, not another speed campaign.

## What actually happens

| Rule | Matched bindings | Changed function writes | Unchanged single writes |
|---|---:|---:|---:|
| Get size (153) | 966,545 | 250,442 | 716,103 |
| Single size (155) | 306,775 | 302,321 | 4,454 |
| Concat size (154) | 334,264 | 290,251 | 44,013 |
| Bop size (151) | 221,686 | 208,698 | 12,988 |
| Function size (148) | 1,458 | 1,458 | 0 |

All fifteen `Expr-size` writers together produce 1,940,065 matched bindings,
1,128,542 actual function updates and 811,523 unchanged single writes. Five
bindings use the ordinary write path, so single writes total 1,940,060. Every
binding also completes a Cell step. Its possible publication and historical
evidence cannot be discarded merely because the min write is unchanged.

This rules out treating this whole family as redundant: 98.55% of Single's
successful matches and 94.14% of Bop's update the function. Get is different:
74.09% of its writes do not change the current value. Those are candidates for
a conditional dominance proof, not proof that the entire query can be skipped.
The family spends about 0.325 instrumented seconds in RHS application; matching
remains the larger cost. These attribution times are not a speedup measurement.

There is also expensive unsuccessful work. Single has 1,132,388 Spine entries
but 306,775 successful bindings; these counts motivate examining admission,
not assuming every unsuccessful entry means an absent key. Function has few
successful matches but substantial query time. The next candidate uses the
typed Cell query's first constructor key and existing column support to reject
impossible Entries before Cursor expansion. It must retain exact checks for
positive fingerprint hits, late insertions, unions and visibility changes.
No new reverse index or maintained candidate graph is needed.

The [implemented Entry support gate](../cell-point-support/README.md) now
performs this rejection using only already-built current columns. Its short
checks show fewer actual queries and allocations; full speedup is unproven.

## Coverage and validation

The first 128 Raytrace Runs never execute this family. The 1,280-Run prefix
includes its first 51 source stages but is not representative of all later
work: Get has 8,025 matches / 5,256 unchanged writes there, whereas the complete
workload reaches the counts above. The full run agrees exactly with the prior
full export and all 16,883 ordered Run records. The prefix agrees with a frozen
unmodified runtime. Per-rule single writes, unchanged writes and applied
bindings reconcile exactly to the existing global counters.

Normal sum-bits and profiled sum-bits have the same graph and ordered Run
records. Native sum-bits choice acceptance passes. Runtime unit tests and the
query-worker / Entry-publication Run-boundary fixtures pass; all-feature
compilation checks the unchanged effect-loop ordering in research modes too.

Use the frozen cell-fixed-reads programs and the existing helper:

```sh
CELL_CPU_PROFILE=1 RUNTIME --program SUM_PROGRAM --output FRESH_SUM --repair-ports --entry-publications
CELL_CPU_PROFILE=1 PREFIX RAY_PROGRAM FRESH_PREFIX 1280 0 64 canonical
CELL_CPU_PROFILE=1 RUNTIME --program RAY_PROGRAM --output FRESH_RAY --repair-ports --entry-publications
python3 benchmarks/cell-attribute-profile/collect.py out/cell-attribute-profile benchmarks/cell-attribute-profile/results.json
```

The collector launches no workloads and requires saved semantic acceptance.
Results retain binary/input/report hashes. No sparsity proof or 2× speedup has
been established by this attribution.
