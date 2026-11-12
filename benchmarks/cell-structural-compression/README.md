# Runtime Cell state takeover

The target is at most 30% of the original 3,979,373-byte Graph-exclusive heap
(1,193,811 bytes), with unchanged source semantics. This work does not yet meet
that target. It is an actual standalone Cell runtime experiment, not a native
egglog runtime change or standalone simulated compression model.

The source program has 2,174 live ownership components, no baked ownership
transitions, and **zero retained Cell parent links**. Therefore parent chains
are not the dominant storage explanation for this workload. Actual ownership
training observes 646 candidates; the existing checked selector retains 259
transitions. Stage ordering and incomplete-domain fallback remain unchanged.

Implemented changes:

- Shared Cell wiring describes stable equality field locations. A fact keeps
  dynamic scalars and its component identity instead of repeating every PortRef.
  Fields reference the existing PortProgram and shape port map; there is no
  additional compiled field-layout representation.
- Completed instances delegate proven-equal bindings to existing component
  symbols. Typed original recipe aliases/native identities can reconstruct
  additional slots without a second runtime alias table. Required actual
  constructor results that differ from the implicit native identity remain stored.
- A complete parent projection can detach its old reference. Values not covered
  by a bound symbol are retained explicitly and charged. Before retiring a
  component, delegated source slots are restored for any surviving source frames.
  This path matters for lifecycle correctness but adds no savings in this source,
  whose parent-link count is already zero.
- The ownership frame directory stores live records densely with stable logical
  IDs. Retiring a record relocates at most one live record and adjusts its index;
  public Cell/Fact identities are never renamed or recycled.

Binding takeover and capacity reclamation are currently explicitly invoked by
`compact_retained_capacity` under `storage-metrics` at idle source Run boundaries.
They are not yet a default online completion policy. Stable field wiring and the
live frame directory are ordinary runtime representations. Per-boundary sweeps
are a diagnostic implementation, not a claimed fast scheduling strategy.

## Reproduction

Use the reviewed sum-bits artifact as `$PROGRAM`. Keep complete raw traces in
ignored output directories; the analysis can be repeated without another run.

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- profile-cell-ownership --program "$PROGRAM" --output out/structural-profile
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- bake-cell-ownership --program "$PROGRAM" --profile out/structural-profile/profile.json --output out/structural-baked
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_comparison -- "$PROGRAM" out/structural-final.json out/structural-baked/program.json
python3 benchmarks/cell-structural-compression/analyze.py ORIGINAL_BASELINE_TRACE out/structural-final.json out/structural-summary.json
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,storage-metrics,iterative-bake --lib
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --test stable_ports --test cell_ownership
```

The fixed original trace uses f20c0fce's runtime plus the example's per-Run
checksums (no representation changes). Preserve it; do not reset the baseline
as optimizations accumulate. The example compares an unbaked/uncompacted lane
and a baked/takeover lane on all 1,428 source Runs. Original baseline checksums
also guard against a bug shared by both new lanes. No performance measurement
is inferred from this debug allocator/export diagnostic.

Graph heap is measured by actual System allocation bytes released at teardown,
keeping both Programs alive and first dropping Executor caches. Any new shared field
layout storage is separately charged even though Program-retained allocations
are excluded from Graph-exclusive bytes. The final representation adds none;
its two shared handles per fact are included in Graph-owned record storage. The boundary capacity subtotal is not
complete heap and does not bound within-Run peak or temporary takeover storage.
The 30% target cannot be declared reached from that subtotal.

The next structural gap is still the complete source Cell/fact/index owner:
removing duplicate bindings does not yet replace every dominated source frame
with a combined Cell owner. Use `instance_trace` and `function_trace` to derive
future slot demands and explain remaining fact-free frame retention before
adding more Bake shapes or another runtime registry.

## Verified checkpoint

`results.json` records the final representation, with zero added field-layout
storage. Original Graph-exclusive heap: 3,979,373 B. Final: 3,080,829 B
(**77.42% remaining**, 22.58% reduction). The 30% target is **not met**.
The source has 1,863 delegated frames and 10,742 explicit slots (down from
14,755); physical source Cells and the remaining fact/index representation
still exist. There are 211 fact-free frames with 2,097 slots and 387 live
function-origin references. Dropping only these frames cannot reach the target.

Validation: all 1,428 original graph and ordered RHS/write/resume digests match;
135 runtime unit tests, 27 ownership integration tests and 14 stable-port tests
passed, including delegated slots across late unions and materialization before
component retirement. Runtime all-features compilation passed. The semantic
acceptance report uses the optimized final graph and the existing reviewed
native exports. Exact source Run equality is checked separately from legal
native extraction-choice equivalence. No timing or within-Run heap-peak claim.

Raw inputs/outputs are retained locally under `out/cell-structural-compression/`:
`original-baseline.json`, `profile.json`, `baked-program.json`, `final-trace.json`.
The original baseline is preserved across subsequent iterations. The sources,
summary and semantic proof are versioned; generated programs/raw traces are not.
