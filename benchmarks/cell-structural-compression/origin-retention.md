# Cross-stage handoff retention census

This measures the actual standalone Cell runtime, not native egglog. It adds
an offline, final-boundary attribution of functional rows to retained origins
and inline writers. No execution, scheduling, publication or retirement path
changes. The per-table source sets exist only while producing the diagnostic.
They are not runtime dependency lists.

On the accepted completed-symbolic program, 1,428 Runs produce the same final
state digest as the control. Graph-owned requested teardown heap remains
2,617,317 bytes. This is an observation change, not a compression result. This
run did not repeat the ordered per-Run audit or semantic validator; it compares
its final digest to the previously audited control. No speed claim.

## What changes the next action

Typed query atoms, RHS `let` calls, compiled merge operations and control calls
identify 264 retained Unit/merge-old rows with no source-program read. All are
`CellSpineApplied*`. They retain 264 origins, including 22 inline writers.
However, 175 of their 264 distinct source Cells also serve another table's
origin. Removing these references cannot release all 264 Cells; even the other
89 can still own facts or have child readers. This is not a byte-saving bound.

Consequently, unread receipt origin suppression is not sufficient as the main
large-compression strategy. Retaining the table row still matters: a fresh Set
can affect change reporting, saturation termination and equality repair. Public
Graph API consumers also fall outside this closed source-program read census.

The remaining 575 live `CellSpineView*` rows are materialized query handoffs.
The report records their writer and consumer rule IDs and rulesets:

| View | Live rows | Relevant handoff |
| --- | ---: | --- |
| CellSpineView8 | 192 | terms / cell-spine-complete → terms-helpers |
| CellSpineView28 | 160 | terms / helper stages / cell-spine-complete → cicm |
| CellSpineView9 | 103 | completion / helper stages → terms-helpers-helpers |
| CellSpineView16 | 77 | many sources → switch_rewrite and other consumers |

The first three hold 455 rows. View8 has six writer rules and two consumer
rules, making it the smallest high-volume coverage problem in this census.
Next trace analysis should group its actual bindings and witness lifetimes
across Runs: can the consumers enumerate directly from a composed instance,
including completion-rule production and later union-enabled matches? A Bake
replacement must preserve delta ownership, changed signals, mutable reads,
visibility and residual enumeration before removing the table or its indexes.
Ruleset connectivity alone is not a closed component or saturation proof.

## Reproduce

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/origin-census-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_origin_retention.py out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/origin-census-heap.json out/cell-structural-compression/completed-symbolic-heap.json benchmarks/cell-structural-compression/origin-retention-results.json
python3 -m unittest discover -s benchmarks/cell-structural-compression -p test_origin_retention.py
```

The analyzer requires matching program identity, Run count and final digest.
The reader regression covers a RHS-only read and a merge-only read so neither
is mistaken for an unread relation. Repeated query-reader entries in the report
represent multiple atoms in one rule, not multiple rules.
