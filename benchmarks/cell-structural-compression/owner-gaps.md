# Why existing completion donors remain disconnected

Offline analysis of the audited `rhs-owner-audit.json`; no workload rerun.
`inspect_owner_catalog` parses the exact source artifact and derives the checked
ownership catalog, exposing Entry-to-query coordinates and compiled transitions.
The analyzer rejects a catalog with a different program checksum.

The 810 cross-Run boundaries without an observed same-component donor divide
into these mutually exclusive categories. Capacity refers to **source** owners,
not donor size. Counts are boundaries, not distinct instances or mutations.

| Observed eligible source | Boundaries | In completed Cells with zero new facts |
| --- | ---: | ---: |
| Unbaked transition with capacity | 479 | 392 |
| Installed transition with capacity | 99 | 72 |
| All observed sources at capacity | 80 | 80 |
| No observed owned Entry | 152 | 146 |
| Total | 810 | **690** |

544 boundaries have every compiler-eligible Entry receipt observed and owned.
267 do not have an active ownership Entry. Missing query captures remain unknown;
not all ordinary query atoms are ownership-eligible Entries. Donor sizes are one
frame:373, two:155, three:166, four:116, but these sizes cannot diagnose source
capacity by themselves.

An installed transition merely permits appending the **new** Cell to a source
component. It does not bring a separately owned existing result into that
component, prove the RHS key, or establish that the transition was selected.
Source-frame ordering is another unchecked obligation. In particular, adding
more catalog fragments cannot alone establish the missing donor connection.

## Change required in the completion mechanism

`ensure_composition_frame` runs in the fact-initialization path. A successful
constructor request that reuses existing results need not create a new frame or
advance a component. That mismatch is relevant to 690 observed boundaries in
completed Cells with no births, including 72 with an installed transition and
available source capacity. This is evidence against treating more birth-driven
catalog entries as the complete fix; it does not prove every one of the 690
would be eligible for a new transition.

This finding concerns physical ownership composition, not absence of a logical
completion path. `stage_spine::complete` already records successful applications,
seeds admitted roots and captures actual results without requiring births. The
regression `successful_zero_birth_rhs_already_advances_completion_history` confirms
two executed zero-birth applications still enter that existing history. Do not
introduce a second completion log to fix an ownership connectivity problem.

The next mechanism must use that existing completion/result state to drive
physical takeover, including results owned by other Cells. It must project
inputs from existing instance/Entry slots and describe the resulting completed
state without allocating another ordinary producer frame just to remember
success. Subsequent stage switches still need full-key, liveness, visibility and
residual/delta proofs. Charge retained result references against source state
and maintenance actually removed; a cache of all successful applications would
not meet the compression goal.

## Coordinate correction

Ownership Entry indexes address `cell_ownership.entries[rule]`, not the original
query atom array. The previous observer named its Entry ordinal `atom`. Counts
and same-component comparisons were correct, but using that field as a query
atom for compilation would be wrong. New snapshots emit both `entry` and the
mapped `atom`. Existing archives are decoded using the checked catalog. The
owner-pattern report now calls the field `source_index`: Entry ordinal for
`source_kind=entry`, query atom for `source_kind=query`. No historic execution
trace is modified and no runtime execution behavior changes.

Validation: compiler catalog export succeeds; three gap-analysis tests cover
nonidentity Entry mapping, source capacity, exact transition matching and missing
query evidence; four prior owner-analysis tests pass. Existing audited state and
semantic acceptance are reused because only diagnostic coordinates and offline
analysis changed. No compression or speedup is claimed.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example inspect_owner_catalog -- out/cell-structural-compression/domain-classes-derived/program.json out/cell-structural-compression/owner-catalog.json
python3 benchmarks/cell-structural-compression/analyze_owner_gaps.py out/cell-structural-compression/owner-catalog.json out/cell-structural-compression/rhs-owner-audit.json benchmarks/cell-structural-compression/owner-gap-results.json
python3 benchmarks/cell-structural-compression/test_owner_gaps.py
```
