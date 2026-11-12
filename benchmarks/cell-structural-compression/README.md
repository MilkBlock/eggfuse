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

## Program materialization and iteration peaks

The optional `bake-cell-ownership --materialize-markers false` flag omits the
redundant JSON copy of the typed ownership plan. Source Cell definitions and
checked ownership fragments still derive that plan. The default remains true
for existing artifact consumers. This does not remove logical `.egg` marker
facts, change the chosen fragments, or count as runtime instance compression.

`peak-results.json` compares single-lane allocator traces. These include Program,
Graph, Executor and a fixed 196,608-byte diagnostic buffer. They exclude parsing
high water and allocator padding; they are not RSS or Graph-exclusive peaks.

| Lane | Loaded program + process bytes | Execution/takeover peak bytes |
| --- | ---: | ---: |
| Fixed original f20c0fce | 113,734,400 | 124,720,514 |
| Current, materialized plan | 123,705,635 | 133,667,563 |
| Current, derived plan | 116,099,089 | 126,061,017 |

The current two lanes use the same runtime source and differ by optional JSON
materialization. Their initialization-relative peak growth is identical:
6,147,585 bytes. The materialization costs 7,606,546 bytes; even after removing
it the process peak remains 1,340,503 bytes above original. All 1,428 Runs are
sampled, including allocations between boundaries. Final graph digests match.
Cross-worktree shared Cargo caches reused an older runtime in an intermediate
comparison (detected by missing new census fields). Those results are discarded.
All three published lanes use independent worktree-local target directories.
The observer rejects takeover runs without the delegated-frame census.
No Graph-exclusive within-Run peak or 30% completion claim follows from these
numbers. The CLI plan equivalence and execution audit test passes as part of
all 28 ownership tests.

The isolated lean-program validation also reproduces the 3,080,829-byte
Graph-exclusive result, 1,863 delegated frames and 10,742 stored source slots.
All 1,428 graph and ordered RHS/write/resume hashes match the fixed original
trace. `choice_diagnosis.py` returns `pass` / exit 0 on that exported state.
`results.json` now references `lean-isolated-trace.json`; raw traces remain
under the ignored experiment output directory.

```sh
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- bake-cell-ownership --program out/structural-baked/program.json --materialize-markers false --output out/structural-lean
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,storage-metrics --example runtime_storage_peak -- out/structural-lean/program.json out/peak-lean.json takeover
python3 benchmarks/cell-structural-compression/compare_peaks.py ORIGINAL_PEAK MATERIALIZED_PEAK out/peak-lean.json out/peak-results.json
```

Use `CARGO_TARGET_DIR="$PWD/target"` in each worktree; do not share compiled
workspace crates between baseline and current lanes. The original lane uses
the same allocation observer built against f20c0fce,
with the original source artifact and `baseline` mode. The observer is not a
performance benchmark and serialization happens after peak observation.

Two rejected approaches guide the next structural change. Pruning slots from
future consumer `LocalRead` demands alone fails the surviving-source-frame
contract: component retirement can expose a still-observable source slot.
`retiring_shared_owner_restores_delegated_source_slots_before_gc` caught the
failure; that edit was reverted without weakening the test. Exact identical
binding-array sharing has only a 5,464-byte positive-group upper bound in the
saved final trace, before grouping overhead. Neither approach can replace
proper composed ownership of source instances, facts and indexes.

The saved allocator teardown also gives a useful impossibility bound for a
frame-only solution: `cells` releases 782,416 bytes and `ownership` releases
806,728 bytes. Even deleting both in their entirety, with zero replacement
cost, leaves 1,491,685 bytes, above the 1,193,811-byte goal. Real takeover must
therefore cover fact/field and index representation too. Next implementation
must preserve stable fact identity, source reads after component retirement,
visibility and worker read epochs while consolidating these owners. Merely
moving source bindings into an additional composition object cannot meet the
target. Field teardown charges shared allocations to their last owner; these
numbers are an optimistic bound, not achievable independent savings.
