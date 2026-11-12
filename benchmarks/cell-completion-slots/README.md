# One completion slot through producer registration

This measures the actual standalone Cell CPU, not native egglog. The work-count
control is frozen `076a923a`; programs, catalogs, release features and arguments
are unchanged. This is the fifth implementation after timing checkpoint
`83ac944b`, following `c0dd0034`, `68fb07a4`, `4516c4a7` and `076a923a`.

## Opportunity from actual executions

The preceding Raytrace execution used fused producer registration for 12,204
Cells and 17,011 constructor rows. Each completed computation entered a prefix
slot array, then moved into a separate array after registration. The first
array alone accumulated 6,053,184 bytes of capacity; sum-bits accumulated
36,208 bytes. The compiled terminal constructor plan already proves the needed
dependency/effect boundary. A second copy of the queue's slot storage supplies
no additional proof or value.

The same original result now occupies one slot with three states: empty,
computed, and registered. A producer takes the existing directory owner and
continues the ready prefix outside the mutex. While it installs one Cell,
other workers may deposit computed inputs, and the source may consume earlier
registered outputs. A computed input never satisfies source readiness. Returning
ownership and testing the next computed input happen under the same mutex,
preventing a lost handoff. No second prefix array or second event mutex remains
in this covered path.

The result's bindings, actual reused witnesses, row allocations and fact slots
retain their original owners. This changes the completion store, not the Cell
facts or compiler representation. Shared Entry and iterative Bake still use
original instance slots across the original Run boundary. Catalog evidence is
compared unchanged; this does not invent a new cross-Run proof.

## Costs and live boundaries

The source's temporary ready vector remains; this change does not claim to
eliminate every result move. Registration still has one mutable directory owner
and still returns that owner before its readers resume. The fixed Run visibility
boundary, error/effect order, exact key checks, duplicate aliases, retirement
and failure-suffix invalidation are unchanged. Background admission and Unit
tails keep their existing handling. The implementation neither expands the
admitted region nor delays ongoing queries to obtain ownership.

Ordinary background completion has an uninhabited computed-state type. Tests
verify its actual Cell slot layout is unchanged. Continued completion uses a
tagged slot large enough for either the computed result or registered result;
its actual size is recorded, including the tag. Shared control/header capacity
and the source ready vector are still charged to event bytes. The historical
`constructor_fused_staging_bytes` field stays present and must be zero here.

Work counts and all added/removed capacity are retained in `results.json`.
Capacity is cumulative allocation capacity, not peak memory or an allocation
trace. No coverage, queue byte or early-completion counter establishes a speedup.

| Observation | sum-bits control / candidate | Raytrace control / candidate |
| --- | ---: | ---: |
| Separate computed-prefix capacity, bytes | 36,208 / 0 | 6,053,184 / 0 |
| Total completion events plus that prefix, bytes | 1,060,536 / 1,024,040 | 193,037,352 / 189,394,560 |
| Cells through fused registration | 73 / 73 | 12,204 / 12,216 |
| Actual rows through fused registration | 91 / 91 | 17,011 / 17,035 |
| RHS dispatch regions | 247 / 247 | 9,064 / 9,062 |
| Second registration pool calls | 4 / 5 | 2,683 / 2,775 |
| All constructor rows registered by workers | 152 / 181 | 188,028 / 193,676 |
| Ordinary key lookups | 13,028 / 13,028 | 3,830,073 / 3,830,073 |
| Source execution frames | 5,176 / 5,176 | 1,020,600 / 1,020,600 |

The new slot is 600 bytes, the same as the old completed slot; it replaces that
slot plus a separate 496-byte computed slot. Across the entire execution,
combined completion capacity falls 3.44% / 1.89%. Raytrace's net reduction is
3,642,792 bytes, rather than the entire old prefix capacity, because event
arrival changes other event-buffer growth. Registration grouping also changes:
there are more second registration calls and registered rows in this execution.
Those counts and their additional capacities remain in the evidence, not hidden
behind the deleted-prefix metric. The eligibility proof itself is unchanged.

## Validation and reproduction

185 runtime tests and 89 relevant integration tests pass, plus forced hash/Bloom
collisions and all-feature, sparse-only and legacy checks. New tests hold the
first registration open while a later producer deposits its result, verify
that neither result is prematurely visible, then release the same source
prefix. Empty regions, producer/registration panics and reader lifetimes are
covered. Existing native-backed fixtures retain source Run snapshots through
same-Run reads, deletion, recreation and late union, for both foreground and
background admission. Prefix rollback and reused actual results remain covered.

README compile/run/one-repeat bench commands are smoke checks. Native sum-bits
acceptance returns `pass` and matches the fresh CPU export hash. Whole-state,
all 1,428 / 16,883 ordered Run summaries, logical effects, reverse occupancy and
Bake evidence match the preceding runtime; Raytrace remains differential
validation only.

Use fresh output directories. The checker requires successful validation and
README records using the commands in `results.json`. Local disk space is bounded
by running integration binaries sequentially and removing only generated test
executables after their successful recorded checks; sources and logs remain.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-completion-slots/run.py out/cell-fused-registration FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-completion-slots/check.py out/cell-fused-registration FRESH_OUTPUT RESULTS.json
```

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

The periodic comparison uses the existing shuffled harness, including every
warmup and sample. The immediate control isolates this completion-store change;
the preceding checkpoint charges the five cumulative implementations. Separate
stack samples are diagnostics, never timing samples.

```sh
python3 benchmarks/cell-completion-slots/prepare_timing.py ARTIFACT_ROOT
python3 benchmarks/cell-completion-slots/campaign.py ARTIFACT_ROOT
python3 benchmarks/raytrace-thread-bottlenecks/profile.py ARTIFACT_ROOT/ray-manifest.json ARTIFACT_ROOT/timing-ray/samples.json ARTIFACT_ROOT/profile-control4 --lane control4 --duration 3 --interval-ms 2 --start-delay 0.6
python3 benchmarks/raytrace-thread-bottlenecks/profile.py ARTIFACT_ROOT/ray-manifest.json ARTIFACT_ROOT/timing-ray/samples.json ARTIFACT_ROOT/profile-candidate4 --lane candidate4 --duration 3 --interval-ms 2 --start-delay 0.6
python3 benchmarks/cell-completion-slots/timing_check.py ARTIFACT_ROOT TIMING_RESULTS.json
```
