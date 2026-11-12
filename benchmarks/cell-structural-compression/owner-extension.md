# Seed-preserving extension from passive execution: rejected as a compression configuration

## Opportunity and obligations

The last actual trace contains uncovered owned births where a larger composed
state lacks a transition even though a local pair can be reused. This batch
selects 32 observed additions from that saved trace, without another exploratory
training execution. Scoring uses proposed shared inputs per static instruction
handle only as a ranking heuristic, never as measured savings. Only one
alternative per observed source shape/consumer rule is selected because Entry
alternatives overlap.

The source recipe digest must match the audited trace. The trace comes from the
saved closure-existing catalog; the candidate extends domain-classes-derived,
which has the same source and physical fragment seed with derived query classes.
All candidate substitutions are revalidated by the actual Program loader.

The first attempt exposed the 256-fragment budget. Of the 256 existing selected
paths, 101 are strict prefixes of another selected path. Loading a longer path
already compiles every prefix. Keeping 155 maximal paths therefore retains the
seed's full transition language, leaving room for the additions without raising
the fragment budget. The example additionally compares checked source-shape,
hop and target-shape triples, verifying every seed transition survives regardless
of renumbering. It does not treat equal shape IDs across catalogs as evidence.

The result contains 187 selected paths, 649 checked shapes and 291 transitions,
versus 617 shapes and 259 transitions. The extent is eight frames. All old
transitions survive, but changed runtime composition choices still require
execution admission. The source Run schedule, typed wiring, external bindings,
receipt lifetime and original publication ordering remain authoritative.

## Actual result

| Metric | Current branch configuration | Candidate |
| --- | ---: | ---: |
| Live components | 1,392 | 1,345 |
| Live source frames, ordinary plus transferred | 2,385 | 2,385 |
| Completed transferred frames | 787 | 832 |
| Explicit Cell slots | 7,482 | 7,440 |
| Live fact-record bytes | 208,440 | 208,440 |
| Complete Graph requested heap | 2,659,437 B | 2,655,541 B |
| Complete retained Program heap | 117,318,509 B | 117,380,922 B |
| Execution/takeover process peak | 125,443,265 B | 125,496,318 B |

Graph saves only 3,896 B, while Program grows 62,413 B: net retained storage
**increases 58,517 B**. The candidate is rejected as the new compression baseline.
The complete Program charge includes selection provenance and compiled plans.

This identifies the missing structural step: 45 more frames move into completed
owners, but **no source frame identity or live fact record disappears**. Only 42
explicit slots disappear. Component storage itself grows by 912 B and boundary
storage by 1,800 B, offsetting some source-storage savings. Fewer components is
therefore insufficient as a Bake credit metric.

The next takeover must remove per-source retained state and its maintenance,
not merely move its arrays into a larger owner. Actual result capture is also
not the main remaining denominator: the previous capture audit counted only
302 immediate capture allocations, mostly already shared with publication.
Do not claim this batch approaches the requested 30% whole-egraph target.

## Validation and reproduction

Actual standalone Cell runtime, not native egglog. All 1,428 saved Run graph and
ordered RHS/write/resume checks pass. The final graph exactly matches the saved
semantic input and choice diagnosis passes. The selector regression checks
maximal-prefix preservation, exclusion of overlapping alternatives, and rejection
of unaudited input. This is an allocation/structure experiment, not a timing run.
Raw generated programs remain untracked; the reproducible selector, selection
report and relevant text results are tracked.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example extend_observed_owners -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/capture-history.json 32 out/cell-structural-compression/observed-owners-32
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example extend_observed_owners
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/observed-owners-32/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/observed-owners-32-audit.json --natural --shared-owners --parent-takeover --port-domains-only
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/observed-owners-32/program.json out/cell-structural-compression/observed-owners-32-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_owner_extension.py out/cell-structural-compression/completed-live-audit.json out/cell-structural-compression/observed-owners-32-audit.json out/cell-structural-compression/completed-live-heap.json out/cell-structural-compression/observed-owners-32-heap.json benchmarks/cell-structural-compression/owner-extension-results.json
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/owner-extension-semantic.json
```
