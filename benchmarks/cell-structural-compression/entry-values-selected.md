# Re-lower the selected catalog after Entry value specialization

The opt-in compiler transformation now has a source acceptance checker: it
recomputes the all-writer proofs from the original Program and requires exact
agreement with the optimized source core and recorded projections. This is a
narrow, explicit extension for constructor-Let-to-Copy specialization. It does
not relax the existing semantic comparison exclusions or equational rules.

`Catalog::relower_selected` regenerates RHS/capture/completion plans from selected
paths with the same proof policy. It does not search for additional paths and
commits no partial plan when validation fails. The migration example requires
identical rule, query and slot coordinates; unsupported remapping is rejected.

## Keep the selected routes fixed

A first regenerated artifact preserved all 32 iterative joins but inadvertently
changed ordinary multi-stage query routes from 6,325 to 6,792. It passed all 1,428
Run graph/RHS/write/resume comparisons, but Graph grew by 320 bytes. Removed
consumer bindings were offset by 120 newly retained producer bindings. This
comparison was confounded by re-running the ordinary route selection.

The final migration keeps the original ordinary routes and drops only routes
whose anchor or source step requires one of the four removed constructor
operations. 6,286 ordinary routes and all 32 iterative joins remain. Each kept
route and all re-lowered joins pass the target Program's typed checks. Existing
ownership fragments are experimental selections, not new runtime observations;
source preparation rechecks their substitutions. Their transition wiring remains
equal, while some shared shapes change with the new instructions.

## Validation and accounting

See `entry-values-selected-results.json` for the measured source, graph and work
counts, and `entry-values-selected-semantic.json` for the semantic gate. These
measure the actual standalone Cell runtime, not native egglog performance. The
Graph teardown measurement excludes retained Program and Executor allocations;
those are charged separately. No elapsed-time speedup is claimed.

The final candidate passes all 1,428 graph/RHS/write boundaries, with zero
resume-audit changes. Its final export exactly equals the saved CPU semantic
input, and the standard choice-diagnosis gate returns pass.

| Metric | Baseline | Specialized selection |
|---|---:|---:|
| Key lookups | 12,106 | 12,002 |
| Explicit Cell slots | 5,740 | 5,636 |
| History allocations | 302 | 302 |
| Decoded rows | 2,922 | 3,168 |
| Graph-owned teardown bytes | 2,617,317 | 2,614,757 |
| Retained Program bytes | 117,318,509 | 119,765,150 |

The 104 eliminated slots belong to rules 250 (2) and 507 (102). Created Cells,
logical facts and parent links are unchanged. Graph savings are only 0.098%;
newly generated Program plans outweigh them, and 246 extra row decodes remain.
This is therefore NOT admitted as a total-memory or speed improvement. Keep the
previous artifact as the baseline. The contribution is a proven way to remove
constructor work and its result storage without extra history, plus a controlled
catalog migration; it does not achieve large egraph compression.

Tests cover ordinary/late matches, mutable guards, unsupported writers,
constructor hiding, forged proof/source inputs, unchanged selected-path lowering,
and rejection of invalid publication positions without mutating the plan.

The remaining structural opportunity is the 839 live Unit/old function rows in
30 tables (575 View rows and 264 Applied rows). They retain function storage in
addition to Cell origins. Investigate representing these facts through existing
Cell storage before adding further value-only specializations. Any conversion
must preserve exact duplicate detection, deletion/visibility, union repair,
source ordering and Run convergence; the row count is not a byte saving estimate.

## Reproduce

Use `CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target` and features
`sparse-cells,iterative-bake,storage-metrics` for Cargo examples.

```sh
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example relower_entry_values -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/entry-values-selected.json
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example audit_matched_handoffs -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/entry-values-selected.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/entry-values-selected-audit.json
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/entry-values-selected.json out/cell-structural-compression/entry-values-selected-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_entry_values.py out/cell-structural-compression/entry-values-selected-audit.json out/cell-structural-compression/completed-symbolic-heap.json out/cell-structural-compression/entry-values-selected-heap.json benchmarks/cell-structural-compression/entry-values-selected-results.json
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/entry-values-selected-semantic.json
```

Before reusing the saved semantic inputs, require the new audit's `final_state`
to equal `run-legacy/state.json` under that artifact root exactly. The Run audit
revalidates the source specialization before executing the candidate. Generated
programs and raw trace/heap artifacts remain untracked.
