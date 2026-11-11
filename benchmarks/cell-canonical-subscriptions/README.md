# Reuse the Cell's canonical Eq footprint for subscriptions

Control: `9ac332c4` (the later `2aef7545` records its timing only). Scope:
**standalone Cell CPU**. This is a serial-work reduction following the measured
[multithread checkpoint](../cell-parallel-current/README.md), not another
parallel backend or a claim that repair has disappeared.

## Opportunity and takeover

The last complete Raytrace execution made 1,879,948 subscription calls and
visited 6,000,001 values. The independent stack window included 121 samples in
`subscribe_edges`. The existing checked `repair_ports.key_eq_columns` already
identifies every Eq input of a scalar constructor and proves its output is Eq.
Ordinary constructor births and repaired Row views already provide canonical
fields. Inspecting their scalar fields and looking up their Eq representatives
again cannot change the resulting subscriptions.

Sparse execution now projects those existing Eq columns plus the output,
directly into the ordinary subscription difference. No new compiler artifact,
fact registry, binding copy, instance field or reverse index is introduced.
The same three-word inline temporary is used as before. The shared footprint
is read on each covered call; lookup, projection, sorting/deduplication and
the necessary reverse-edge operations still cost work.

A changed nonempty subscription set also replaces the existing witness's
directory value in place. It no longer removes and reinserts that directory
entry. This is one removed remove/reinsert pair per covered change, not fewer
dependencies, allocations or committed graph mutations.

## Proof boundary

The canonical fields are consumed synchronously with no intervening graph
effect. Debug builds assert the Eq roots at that boundary. This proof does
not survive an arbitrary union or a later source Run: a scheduled Cell switch
must still obtain its current legal Row view. No new Bake completion or
cross-Run reuse credit is awarded.

Empty/retired subscriptions and container or unsupported table layouts retain
the original collector. Raw local-completion fields also retain recursive
canonicalization. Absent footprints fall back, including manually constructed
test Programs. The first test run caught missing-footprint indexing in those
fixtures; the lookup now explicitly handles absence.

Old subscription IDs still resolve through current Parents before comparing
or removing reverse incidences. Union redirects those incidences as before.
Retirement still removes the directory entry, and the source Run publication
barrier is unchanged. All reverse insertion/removal, wake, collision and live
occupancy counts must match the control exactly.

Four global counters add 32 bytes per maintenance structure. They record
covered canonical calls, scalar fields skipped, root reads omitted in release
execution, and directory replacements. Debug validation itself still performs
the root checks. These counts must not be added together as one speed model.

## Acceptance and reproduction

[results.json](results.json) records the complete work delta, hashes and
semantic checks. The validator requires identical final states, all ordered
Runs, graph/lookup/filter/Entry/publication work, and the entire prior reverse
maintenance ledger except field visits. The field-visit reduction must equal
the actual scalar-fields-skipped counter. The reviewed sum-bits native contract
must return `pass` / exit 0. Raytrace is a relative regression check.

| Complete workload | sum-bits | Raytrace |
|---|---:|---:|
| Covered canonical subscription calls | 3,941 | 883,148 |
| Field visits before | 19,944 | 6,000,001 |
| Field visits after | 18,239 | 5,768,527 |
| Scalar visits removed | 1,705 | 231,474 |
| Repeated root reads removed | 10,803 | 2,610,094 |
| Directory remove/reinsert pairs removed | 638 | 315,421 |

Every prior reverse-maintenance counter agrees, including 3,807,774 Raytrace
edge insertions and 704,057 union wake visits. All 1,428 / 16,883 ordered Runs
and exact final states agree. The reviewed native sum-bits acceptance is
**pass / exit 0**. The new dispatch/projection and retained reverse maintenance
are not free, and these work counts do not establish an incremental speedup.

Validation: 108 runtime unit tests and 31 selected integration tests pass,
including container keys, delayed local completion, result-only equality,
deletion/recreation, same-Run read isolation and parallel publication. The
canonical projection also passed these integrations with debug root assertions
before the directory-update refinement. Minimal and all-feature checks pass.
README compile/run/bench commands are smoke checks (bench repeat 1), not timing
evidence. Disk exhaustion interrupted debug compilation; only this turn's
runtime/test incremental caches were removed, and final checks use the smaller
release artifacts. No semantic assertion was weakened.

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
cargo test --release --locked -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --test repair_ports --test parallel_residuals --test query_workers --test parallel_publication --test local_union_cells --test cell_absorption
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
# Freeze runtime. Execute each frozen sum/ray program into ROOT/sum and ROOT/ray:
ROOT/runtime --program PROGRAM --output OUTPUT --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-canonical-subscriptions/check.py ROOT PRIOR_ROOT RESULTS.json
```

Saved native proof inputs are reused with the new sum-bits export at
`ROOT/semantic/run-values/state.json`. Raw data remains ignored under
`out/cell-canonical-subscriptions`; the control is
`out/cell-run-column-preparation`. This change has work/semantic acceptance;
the preceding timing campaign does not measure its incremental speed.
