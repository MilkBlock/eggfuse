# Actual Entry inheritance at the Cell handoff

The latest completed-history catalog identifies 72 cross-stage Get closure
bundles. Their 58/143 consumers already have typed single-table parent_columns,
but Shared Entry matching omitted the actual parent FactRef. Consequently each
RHS frame repeated those inputs. Restore that projection in serial completion and
in coordinator acceptance of worker results. Reuse the existing permanent-table
analysis, parent reference lifecycle and runtime visibility check; no second fact
graph or producer subscriber list is introduced. Expansion queries remain unchanged.

Across the same 72 bundles, rule 58 frame-slot observations decrease from 262 to
46 and rule 143 from 288 to 72. Both now inherit the actual Entry fact. These are
snapshots at completion, not peak unique allocation bytes. All existing facts,
constructor operations and source Run scheduling remain authoritative. This is
input inheritance, not a saturated-stage execution bypass or instance takeover.

Final counted source storage in the audited diagnostic changes from 1,198,632 to
1,195,488 bytes (3,144 fewer writer bytes). All other reported source-storage fields,
including final parent links, explicit slots, facts and indexes, are unchanged.
The harness compacts after every Run, including existing parent-link/slot takeover;
therefore this does not measure un-compacted runtime peaks or rule out transient
parent retention. It is not evidence of substantial whole-egraph compression.

## Remaining structural work

The next iteration can learn the shared actual Get Entry and 58/143 fork from the
same completed history. A scheduled completion should attach their suffix facts to
one replacement Cell, preserve fact identities and external readers, and retire the
independent frames. It must retain original stage ordering, delta ownership,
visibility, result lifetimes, guards and uncovered consumers (61/145/317). Rule 137
already has no frame in these bundles; do not count its removal again. Parent input
inheritance alone leaves these obligations and independent fact/index maintenance.

## Validation and reproduction

147 runtime tests including parallel-residuals; 21 compiler integration tests,
including a serial versus two-worker comparison at every Run through deletion.
The sum-bits trace preserves all 1,428 saved graph and ordered effect hashes and the
exact earlier final export. The semantic choice validator reports pass. This is the
actual standalone Cell runtime, not native egglog; no speed claim.

The full audit used an equivalent local permanent-table scan; the final code reuses
Programs.permanent and passes both test suites after that refactor.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_catalog_trace -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/entry-parent-history.json --closure-history 8192
python3 benchmarks/cell-structural-compression/analyze_cross_stage_closures.py out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/entry-parent-history.json out/cell-structural-compression/entry-parent-candidates.json
python3 benchmarks/cell-structural-compression/analyze_cross_stage_storage.py out/cell-structural-compression/entry-parent-history.json out/cell-structural-compression/entry-parent-candidates.json benchmarks/cell-structural-compression/entry-parent-physical-results.json
python3 benchmarks/marker-handoff/choice_diagnosis.py /private/tmp/eggfuse-structural-semantic benchmarks/cell-structural-compression/entry-parent-semantic.json
```
