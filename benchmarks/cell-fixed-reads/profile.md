# The next Cell target: mutable attribute propagation

The initial `CELL_CPU_PROFILE=1` report exported only the four rules belonging
to selected view blocks, despite already timing ordinary queries. The diagnostic
now exports those existing aggregates for every visited rule as
`query_rule_profile`; the original view projection remains available. Profiling
is still explicit, and ordinary execution exports null. No new per-match graph,
execution history or timing counter is maintained.

A fresh standalone serial Raytrace diagnostic covers all 582 rules. Its exact
final graph and all 16,883 ordered Run records agree with the frozen throughput
checkpoint. Its 3,785,196 reported bindings and 4,490,637 residual visits equal
the corresponding whole-execution counters. The ordinary short sum-bits run also
preserves its accepted graph and ordered Run records with profiling disabled.

This is one instrumented attribution run, not another throughput result.
`search_s` times `matches`; it excludes RHS, repair, most Run preparation, and
worker completion/merging. The diagnostic uses workers off. Existing profiling
also visits normally skipped clean rules. Aggregate rule timers total 2.836 s
versus 2.858 s in the enclosing search phases; do not add the two times.

## Observed concentration

| Rule | Query structure | Search seconds | Successful bindings |
|---|---|---:|---:|
| 153 | Get + child Expr-size | 0.272 | 966,545 |
| 155 | Single + child Expr-size | 0.254 | 306,775 |
| 154 | Concat + two child Expr-size reads + addition | 0.253 | 334,264 |
| 507 | extraction candidate + current result + cost guard | 0.200 | 42,713 |
| 151 | Bop + two child Expr-size reads + addition | 0.171 | 221,686 |
| 148 | Function + output Expr-size | 0.143 | 1,458 |

Fifteen rules write `Expr-size`, whose typed merge is `min old new`. Together
they account for 1.249 s / 44.05% of measured query time, 1,940,065 / 51.25% of
bindings and 1,977,575 residual visits. Bindings are successful rule matches,
not committed changes; none of these totals proves that all the work is
redundant. For example, rule 148 has few successful bindings but substantial
search time, so ranking only successful applies would miss its rejected work.

This is a stronger next target than fixed-key sharing: small constructor
relations connect changing scalar attributes, and the same typed Cell includes
both the read and the min update. The concentration supports investigating
computational locality here; it does not prove that the complete egraph is
sparse or that a local completion can replace every external read.

## Next takeover and live obligations

Audit the actual paths of Get/Single/Concat size propagation first. A compiled
Cell should carry the necessary constructor result and child scalar values
through query completion and the ordered scalar write, using its existing
instance/Entry layout. Determine which generic binding assembly, repeated
projection and publication work still occurs before proposing its removal.
Do not describe already eliminated single-write RHS frames as new savings.

The min merge provides a typed idempotence/ordering fact. It does **not** make a
previous child size valid forever. A child size can decrease, a newly equivalent
constructor can become a match, and a union can move function keys. Preserve
both constructor-driven and attribute-driven entries, late inputs, delta
ownership, source-Run visibility, actual result witnesses and existing ordered
updates. Any dominance shortcut must prove the current inequality or rely on
a valid completed operation with explicit remaining obligations. It cannot
skip a smaller later candidate merely because this Cell ran earlier.

Use the next bounded work check to separate these cases: expensive failed
matches; repeated successful bindings; min writes that change a value; and
writes already absorbed by min. Existing global unchanged-merge counts cannot
be attributed to this family without evidence. If a scheduled block switch
can delete matching plus handoff inside this coverage, test that takeover; if
most work is necessary boundary enumeration, change the partition or host.

## Reproduce

The subsequent [dense input storage experiment](../cell-dense-inputs/README.md)
kept the same owned Cell instance through query and RHS, but traded fewer
requested bytes for more allocator events. Its kernel change was rejected;
it removed no queries or publication work. The attribute-propagation takeover
and its cross-Run validity obligations above remain open.

Build the runtime with the same features as the checkpoint and freeze its
Cargo-reported executable. Use a separate output and never treat this run as
a timing sample:

```sh
CELL_CPU_PROFILE=1 RUNTIME --program RAY_PROGRAM --output FRESH --repair-ports --entry-publications
python3 benchmarks/cell-fixed-reads/profile.py out/cell-fixed-reads benchmarks/cell-fixed-reads/profile.json
```

The saved report, source/runtime/input hashes, top rule instructions, all rule
aggregates and semantic checks are recorded in profile.json. The collector
launches no workloads. The normal executable and the diagnostic executable
are separately frozen; the throughput table refers to `c00c8233`, before this
report-only addition.
