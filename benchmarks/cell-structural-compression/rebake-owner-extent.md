# Preserve physical Cell extent across completion Bake iterations

`completion_bake::restore_ownership` reconstructed the ownership fragment
configuration after recompiling the logical execution catalog, but omitted an
explicit `max_frames`. That restored the default limit of four. Previously valid
fragments with four or more hops then failed with
`invalid ownership fragment root or extent`; shorter catalogs silently lost their
configured future extent. This prevented carrying larger physical Cell layouts
through iterative completion compilation.

The compiler now preserves the explicit validated bound when restoring the same
fragments. An absent bound remains absent, preserving the default and avoiding an
unrequested increase. Every fragment/substitution and query-class plan is still
re-derived and checked against the new program. No runtime field or index was
added, and existing four-frame artifacts have no new runtime behavior.

The regression trains a small six-Run constructor chain with an eight-frame
limit, verifies it contains a fragment beyond the default extent, then runs three
completion compilations, including the LazyUnion variant. It checks identical
selected fragments, the bound and derived query-class request. Original and
rebaked executors have identical graphs and source Run counters at all six
boundaries; the actual resulting component still exceeds four frames.

Before the fix this regression reaches completion rebaking and fails with the
invalid-extent error. After the fix the complete `ripsat_completion` suite passes
23 tests. A second test confirms that two successful RHS applications reusing
pre-existing `Mid` constructors still enter completion history despite zero new
facts; the birth-driven limitation concerns physical composition only.

This is a compiler correctness fix in the actual standalone Cell pipeline,
not a measured memory or speed improvement. No sum-bits performance campaign was
run, and it does not establish the requested large runtime compression.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test ripsat_completion
```
