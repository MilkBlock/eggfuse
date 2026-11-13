# Rejected eager parent detachment and the missing lifetime projection

The previous catalog's actual Get completion history suggested moving diagnostic
parent detachment into normal Cell completion. The attached experiment performs
an all-or-nothing check: every parent projection must already equal an existing
component symbol. It releases the reference after completion and defers ancestor
retirement to existing source-Run GC. It does not copy fields or create a fact graph.

Actual standalone Cell runtime results: 413 candidates, 762 slot checks, one
successful detachment covering three slots. All 1,428 saved Run graph and ordered
effect hashes pass, as does semantic acceptance. Tests pass: 147 runtime, 32
ownership (including serial/two-worker detachment), 21 ripsat. This is not a speed
or memory improvement. The automatic invocation was removed; the reproducible
patch is retained as a rejected experiment, not enabled runtime functionality.

## Offline explanation

`inspect_parent_layouts` reads typed compiler definitions and the existing audited
entry-parent history without running the workload. All 755 observed parented
completions lack at least one parent-column symbol. This cohort includes transient
frames and differs from the 413 registered runtime candidates; do not conflate
these denominators or explain the single detachment from this sample alone.

Template 58 (220 observations) inherits x, integer i and the Get output, but only
x appears in an operation operand. Template 143 (206 observations) reads x and i;
its query-result slot is unused. Template 55 (70 observations) likewise inherits an
unused query-result slot. Across the cohort, 326 observations have all operation-read
parent inputs mapped, with uncovered columns used by no template operation.

This identifies a compiler obligation rather than a new runtime search: distinguish
matched query bindings from state required after successful completion. Unused
query-result columns should not force whole-parent retention. Scalar i in 143
still needs a real retained value or checked shared source; equality signals alone
cannot supply it. Before eliminating a slot, also cover actual-result captures,
external Entry projections, writer origins, aliases and Run-boundary lifecycle.
Operation-operand absence alone is not the completed lifetime proof.

A scheduled cross-stage replacement should compile that retained-state projection,
inherit it from the actual Get Entry, then discharge the small frame's ownership.
It must preserve visible fact identities and external consumers. This experiment
neither merges the persistent 58/143 fact owners nor skips their RHS instructions.
No substantial whole-egraph compression has yet been established.

## Reproduction

Apply `completed-parent-experiment.patch` at commit 5fd3cc5c to reproduce the
rejected runtime experiment with `runtime_closure_work` and the existing
closure-existing program / original-baseline Run checks. Revert it afterward.
The saved output is summarized in completed-parent-results.json; semantic pass
is recorded in completed-parent-semantic.json.

Offline analysis (no new trace execution):

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example inspect_parent_layouts -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/entry-parent-history.json benchmarks/cell-structural-compression/parent-layout-results.json
```
