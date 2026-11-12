# Preserve closure results through their existing output delivery

Bake already compiles consumer-driven `supply`, result exports, slot projections
and `keep_history`. The last executed directory's failures showed expired actual
RHS receipts, not a missing parallel lifetime catalog. This change uses that
existing wiring so later closed transitions can retain their evidence across
source Runs.

## Takeover

Output delivery already reads a result slot and resolves its receipt through the
current Run's same-key forwarding map. When that lookup returns a new location,
it now writes the resolved receipt back through the existing compiled slot
projection. All sibling Cells sharing that physical slot see the new location.
No constructor key, Eq search, extra graph, reverse subscriber list, result
frame copy or extra forwarding-map lookup is introduced.

The slots use `Cell<Option<Dependency>>` from their initial effect allocation
through retained history. `EffectWriter` still holds exclusive mutable storage;
publication and shared history remain coordinator-owned `Rc` data. There is no
conversion loop or second slot array at handoff. Tests check allocation identity
and aliases through permuted/repeated projections. This does not authorize
concurrent mutation of retained histories by workers.

Only relocation/same-key coalescence from the existing map may update a slot.
Arbitrary equal result classes do not establish a receipt. Compiled closure
proofs, current visibility, original queued-union order and source Run boundaries
remain authoritative. Unpublished slots and unavailable routes retain ordinary
checks/fallback. The existing unique-owner sealing path remains for fields not
covered by output delivery; no shared-history sweep is installed.

## Actual sum-bits work

| Work | Previous v5 | Shared scan trial | Existing delivery |
| --- | ---: | ---: | ---: |
| Direct completions | 165 | 183 | 183 |
| Witness fallbacks | 44 | 26 | 26 |
| Key lookups | 12,124 | 12,106 | 12,106 |
| Constructor requests | 8,023 | 8,014 | 8,014 |
| Union requests | 2,434 | 2,425 | 2,425 |
| History allocations | 320 | 302 | 302 |
| Effect frames | 4,207 | 4,189 | 4,189 |
| Effect slots initialized | 7,561 | 7,507 | 7,507 |
| Completion-frame result writes | 35 | 26 | 26 |
| Sealing reads | 284 | 464 | 272 |
| New publication slot probes / writes | 0 / 0 | 0 / 0 | 12 / 12 |

The shared-scan trial updates slots in place but adds 180 reads. The selected
implementation removes that added sweep and writes only already-delivered
forwarded results. Neither creates new result owners, headers or backing arrays.
The final published-history census is identical in all three lanes: 133 owners,
8,512 payload bytes, 6,336 array bytes, 256 layout bytes and 2,160 estimated Rc
header bytes. This is a partial census, not egraph memory or a peak measurement.

Twelve slot updates enable eighteen more direct completions through shared
aliases. This is not eighteen skipped rule matches. Full matching is unchanged.
Extra successful completions also incur more output validation, boundary reads
and union operand reads; the text results report them, and work credit charges
the new slot accesses/writes without charging the already existing forwarding
lookup again. No latency speedup or full net work score is claimed. The previous
lane did not save a complete work-credit snapshot; the observer now saves all
515 counters to avoid that gap for future iterations.

## Validation and remaining obligations

All lanes pass 1,428 saved Run graph and ordered RHS/write/resume checks, and
final states agree exactly. The selected implementation passes native-choice
semantic acceptance. Runtime unit tests: 140 passed; ripsat integration tests:
17 passed; work-credit validation passed; the `parallel-residuals` configuration
compiles. This is actual standalone Cell runtime work, not native runtime
performance or a multithreaded speed measurement. The earlier borrowed-layout
working-tree changes are common to all lanes and excluded from this change.

Twenty-six retired witnesses remain. Their lifetime is not proved by current
output delivery, so the runtime still falls back. Broader closure selection,
matching elimination, residual internal RHS completion and end-to-end latency
remain outside this measured takeover; the overall saturated-transition goal
is not complete.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/closure-forwarded-work.json
python3 benchmarks/cell-structural-compression/analyze_publication_forwarding.py out/cell-structural-compression/closure-diagnosis-work.json out/cell-structural-compression/closure-shared-work.json out/cell-structural-compression/closure-forwarded-work.json benchmarks/cell-structural-compression/publication-forwarding-results.json
```

The rejected shared-scan raw trial stays in ignored `out/`; it is not a runtime
mode. The analyzer checks complete saved acceptance and final equality before
extracting counters, and omits timing fields.
