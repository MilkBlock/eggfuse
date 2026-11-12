# Bound the same-component multi-anchor opportunity before changing representation

The current physical composition transition substitutes ports from one matched
Entry. A proposed extension would use several matched Entries in the same owner
to substitute more child symbols. Such an extension needs additional static
coordinates and runtime applicability checks; do not add those costs merely
because more relationships are visible.

Using the existing audited reuse trace and checked compiler symbol projections,
select the first visible-result-reuse boundary of each Cell. Group retained Entry
witnesses by their current component, map their equality columns to child
symbols, and compare the union with the best single Entry in that same component.
Do not combine different components, duplicate child symbols, or repeated
boundaries of the same Cell. Scalar columns are not equality substitutions.

Across **1,405 distinct Cells**, only **25** have any additional observed child
symbol, and each has one. Rule counts: 538:12, 540:9, 523:4. This is a potential
relative to the *best single* anchor, not a measured improvement over the anchor
actually selected. It is also not a census of creation-time Entries: the sample
contains already-visible RHS reuse and only the query receipts already retained.

Decision: do not add a multi-anchor Hop format, larger runtime transition keys,
or additional guards based on this evidence. It does not support a major storage
win in the current targeted reuse path. The result does not rule out a different
multi-anchor opportunity in newly born Cells or a future workload. Cross-component
completion coverage and physical source retirement remain the larger unresolved
issues; the 25 symbols are not 25 facts or 25 retireable instances.

The compiler inspection utility now exports the existing source projection and
port-field arrays for offline analysis. It does not execute the workload or
change any program/instance representation. Three tests cover duplicate symbols,
separate components and empty evidence. The original 1,428-Run audited trace is
reused; there is no new runtime mutation or performance measurement.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example inspect_owner_catalog -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/owner-catalog.json
python3 benchmarks/cell-structural-compression/analyze_joint_anchors.py out/cell-structural-compression/owner-catalog.json out/cell-structural-compression/rhs-owner-audit.json benchmarks/cell-structural-compression/joint-anchor-results.json
python3 benchmarks/cell-structural-compression/test_joint_anchors.py
```
