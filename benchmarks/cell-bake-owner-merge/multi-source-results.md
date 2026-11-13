# Observe multi-source Cell completion at successful query Entries

The result-entry batch did not retire source instances. Inspection identifies a
structural limit: `ensure_composition_frame` chooses one existing component and
appends the newborn source. It cannot absorb several existing components connected
by a successful query, and it is not called for a birth-free application. Increasing
the single-parent fragment catalog cannot directly discharge those boundaries.

This observer runs only with explicit ownership catalog tracing. It records
immutable, visible, owned constructor receipts in successful query Entries.
Components receive local ordinals by first Entry occurrence, never by allocation
ID. A shared Eq query slot connects `(component ordinal, shared symbol)` sites;
current roots are checked for agreement but never stored. Pattern identity retains
rule, static shape/code positions, query Entry positions and source operations.
Scalar or unrelated variables do not establish a connection, even if their current
values happen to agree. Shape/code identity remains local to the compiled artifact.

| case | multi-component Entries | Entries with a shared Eq slot across components | patterns | two-component applications | participating source frames ≤16 |
|---|---:|---:|---:|---:|---:|
| fact | 900 | 809 | 629 | 617 | 807 |
| loopfact | 759 | 646 | 541 | 470 | 641 |
| sum-bits | 4,284 | 3,877 | 2,542 | 2,889 | 3,745 |
| dot-product | 3,441 | 3,002 | 2,064 | 1,911 | 2,794 |

All listed connected applications have at least one receipt from an earlier
epoch. Epoch is not source Run identity. The pattern may also contain unrelated
components: one shared slot does not prove the entire component set connected.
Counts overlap in runtime sources across applications, so they cannot be summed
as bindings saved, instances retired, or committed mutations. No catalog is
installed and no runtime state is compressed by this observation.

The unchanged seed's final sum-bits state has 6,761 bound signal slots but 2,193
different Eq roots; 784 repeated roots occur within a component. Most repeated
roots span component boundaries. This is motivation, not an admission proof:
components can have different future uses and cannot be merged just because their
roots currently agree. None of the four final states contains identical
shape/code/root component signatures in the exploratory census.

## Next executable boundary

Start with two matched components and derive one shared layout from their complete
static wiring plus the matched query-slot substitutions. A transition must return
maps for all old source ordinals and symbols, not just append a new source to one
parent. Its runtime admission must name the actual current components, verify the
matched receipts, and retain uncovered query conditions and source effect order.
This should be allowed at a successful application boundary even with no newborn
constructor. Compile and evaluate the source maps before changing ownership.

A successful takeover must replace old signal arrays, component headers and their
boundary routes, update the existing fact/source address mechanism, and retire the
old independent storage. Retaining children plus a new aggregate descriptor alone
is not compression. Charge the one-time address/routing updates and transient peak;
keep restoration source-local so later union/deletion does not expand every sibling.
No separate consumer lists or copied query bindings are permitted. Exported traces
provide candidate layouts, not equality, visibility or lifecycle certificates.

## Validation and reproduction

Runtime compile check passed. The focused fixture compares snapshots, binding
audits and final states with tracing off/on, then applies a nontrivial union. It
checks that different actual values share one pattern and that distinct query
variables remain disconnected despite a later union. On the merged worker-write
runtime, 47 execution, 62 ownership and 2 parallel-publication tests pass.
The four-case observer also passes 2,652 saved Run checks and four terminal checks;
no inconsistent slots or dropped patterns (limit 4,096) occurred. This is standalone
Cell CPU evidence, not native egglog acceptance or a timing campaign.

Use the existing four-case batch root. Copy each prefix-all candidate.json and
selection.json into multi-source-observation/CASE. Under the shared compute queue,
build/freeze batch_cell_learning with iterative-bake,sparse-cells,storage-metrics:

```sh
batch_cell_learning check-passive ROOT multi-source-observation witness-trace
python3 benchmarks/cell-bake-owner-merge/multi_source_results.py ROOT OUTPUT.json
```

The analyzer checks audited execution, trace completeness and final-state/program
identity against the saved same-runtime control census. It records an input digest
and bounded top patterns, with no instance IDs or values. Full observations remain
in the untracked batch output for subsequent compilation.
