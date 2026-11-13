# Replace scalar-free stable records with existing Cell projections

`Graph::use_template_stable_fields` is an explicit experimental mode. It removes
existing scalar-free stable node records, then stops inserting them on later
births. Scalar-bearing nodes retain their existing storage. A missing map record
is not by itself a live fact: projection checks authoritative Cell fact state,
owned representation, the composition frame, and all-Eq template field wiring.
The short returned descriptor contains no copied field array and is not retained.
Visibility/epoch checks stay with existing callers; hidden facts remain valid
congruence peers. Deleted facts cannot be reconstructed from static wiring alone.

This is a physical record takeover, not logical fact elimination. It reuses the
existing lifecycle and instance directories without adding another membership
set, binding graph, per-producer use list, or per-instance projection cache.
FactRef identities, source-frame restoration boundaries and Run order stay intact.
The map is compacted once on explicit admission, not on every stage transition.

| case | Graph before | Graph after | saved | node records removed |
|---|---:|---:|---:|---:|
| fact | 705175 | 629911 | 10.67% | 653 |
| loopfact | 616289 | 591201 | 4.07% | 633 |
| sum-bits | 1830387 | 1730035 | 5.48% | 1825 |
| dot-product | 1798019 | 1647491 | 8.37% | 2023 |

All other Graph teardown fields are exactly equal to the static-type seed. Final
fact lifecycle snapshots, source frame identities, state digests and restoration
cost counters are equal. These measurements include the worktree's existing
borrowed field-layout implementation on **both** sides; that prerequisite's earlier
savings are not credited again. The implementation integrates those previously
uncommitted shared-layout source dependencies so the new mode is reproducible.

Marked sum-bits decreases from 2222254 to 2121902 Graph-owned bytes. Its actual
execution digest matches the reviewed saved semantic exports and choice diagnosis
passes with exit 0. The four other cases use same-source standalone Cell checks,
not an extended native semantic contract.

## Reads and worker support

Ordinary borrowed workers can share the sparse Cell lifecycle: its RowFields and
FrameSlots use Arc. The prior analysis incorrectly generalized the non-sparse Rc
representation to this path; template-payload.md is corrected. Guard jobs now
resolve their FactRef on the worker, instead of retaining a potentially larger
projected node descriptor in each queued job. The live-node result is retained
only as a boolean for coordinator accounting. Actual speculative work still counts.

Overlapping coordinator mutation still needs an independent frozen lifecycle
view. Completion batches and template projection reject each other in either
configuration order. The frozen-reader entry also asserts that projection is off.
This mode therefore does **not** establish overlap compatibility or eliminate
repair stalls. It never silently builds a whole-graph snapshot as a fallback.

Projection costs an authoritative fact lookup plus template/instance addressing
on each projected read; the current path also tries the residual map first.
`template_node_projections` charges successful projections, including folded worker
work. Reports use unmetered lookup so asking for a report does not change counters.
No speedup is claimed. Process peaks include the much larger Program and Executor;
do not describe the Graph percentage as a process-memory percentage.

## Validation and reproduction

54 ownership tests, 11 completion-batch tests, 4 existing parallel-guard tests and
2 borrowed-read tests pass. An additional projected-field parallel-guard test runs
real worker rounds through cascading unions, deletion and recreation. The takeover
test covers activation before execution and after existing facts, source-owner
transfer, five Run boundaries and two query workers. Runtime unit tests (162) and
the default runtime compile also pass. All 2652 saved source Run checks and all
four terminal checks pass with the explicit template-fields mode.

```
runtime_storage_peak PROGRAM OUTPUT inherited-owners --port-domains-only --template-fields
batch_cell_learning check-passive out/cell-batched-learning stage-inherited template-fields
python3 benchmarks/cell-batched-learning/template_field_results.py out/cell-batched-learning benchmarks/cell-batched-learning/template-field-results.json
```

The next required replacement is the frozen lifetime view, followed by the
scalar-bearing residuals where template evidence proves their source. Whole-graph
compression to 30% and stage-state-only RHS generation remain unachieved.
