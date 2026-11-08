# Persistent cross-stage Cell maintenance

This extends `8fffff65` in the standalone Cell CPU runtime. Native egglog is a
semantic oracle in the focused tests. The application results do not measure
native egglog. The 208/316-unit source catalogs are kept frozen.

## Compiler, entry and lifetime

`bake-cell-ownership` emits typed ownership markers without executing the input
workload. A marker contains a direct body mask and the original union positions.
Shared publication-table routes connect those bodies to scheduled query entry
ports. The recipe and entry-schedule digests bind the descriptor to its source;
loading independently reconstructs every field. Templates without any union
are included. This is a compiled descriptor attached to existing Entry/Template
wiring, not an additional runtime marker table.

At an already checked source binding, the entry's actual witness supplies its
maintenance owner. The next source frame inherits that owner; the constructor
body uses a direct compiled mask, with no template-selection set or operation
map search. Ordinary fact state holds the authoritative owner handle, so existing
shared Entries and producer receipts reference the same live state. Ownership
does not depend on the lifetime of a transient matching cursor. In sparse builds
the executor also enables existing shared Entry publication ownership.

Existing scalar constructor rows are adopted when the mode is enabled. Newly
created scalar bodies skip `uses` and `dependencies` installation. A source can
continue extending the same owner across Runs. The owner retains a forward body
list and survives publication barriers; its members do not resubscribe merely
because a Run or local repair has completed. Deletion removes the member, and
an empty owner releases its boundary memberships.

Owners have at most 256 facts. A large RHS or continuation splits at that bound,
making references to another owner explicit boundaries. This is a structural
work bound, not an empirically fitted optimum or a proof that larger owners are
unprofitable. `capacity_splits` counts both refused continuations into full owners
and actual body splits; it is not a count of allocated owners. `owners_created`
records allocations. Mutable functions, Unit relations and container
constructors retain their existing implementation.

## Equality, matching and publication

The representation already encodes a native constructor result's source Cell and
slot. This address locates its owner directly; its numeric ordering is never an
ownership or equality proof. Imported, foreign, aliased and deleted-result roots
use an explicit root-to-owner boundary directory. There is no root-to-internal-
fact reverse index. Boundary incidences remain reverse routing at owner granularity
and are reported separately from the legacy per-row index.

An actual committed union enters the native owner and any boundary owners on the
displaced side. Their bounded forward bodies project affected scalar ports.
Result-only singleton updates publish directly. Key-changing bodies enter a
dedicated owned completion queue, merged in witness order with residual repair.
They use their maintained body and the common exact-key collision/retirement
terminal. Successful completion preserves ownership and skips resubscription;
it does not fall through to legacy fact repair. Exact-key interning, committed
connectivity and original source publication barriers remain authoritative.

Alias boundary forwarding happens immediately, before the next union in a batch.
After ordered completion, only changed owners recompute their external ports.
Retiring an origin preserves a boundary for its still-used result identity, so
collecting the old source Cell cannot lose a later external union notification.

The same boundary directory supplies complete candidate domains for equality-
bound queries: candidate owners plus the residual legacy incidence set. The
runtime inspects their forward bodies and leaves ordinary predicates to the
existing matcher. It does not respond to an unsubscribed row by scanning its
entire table. Queries without equality constraints still use ordinary table
membership, as the baseline does. Shared Entry matching and publication continue
at their original Run; source guards and future union effects are never assumed.

## Monitoring gates

| Link | Recorded evidence |
|---|---|
| Bake/marker | Typed body/table/entry coverage; descriptor validation; marker entry and anchor reads |
| Cross-stage inheritance | Continuations across epochs, live owners/bodies at every publication barrier |
| Internal ownership | Eligible live facts, owned live facts, live internal equality ports; physical absence from legacy dependencies |
| Boundary propagation | Boundary insertions, physical live incidences, native/boundary routes, owner/body/port visits |
| Completion/publication | Owned key completions, result publications, retirements, pending keys; original ordered traces |
| Matching | Owner-domain queries, visited owners/bodies, residual-index visits, returned candidates; separate unbound membership enumeration |
| Remaining work | Unsupported live rows, capacity splits, remaining legacy edges and complete operation ledger |

Final reports assert that every owned body is canonical, every foreign equality
port has a boundary, no owned fact appears in legacy dependencies, and physical
edge/body counts agree with gauges. The report's internal/boundary port counts
count field incidences; `boundary_live` counts deduplicated root-to-owner edges.
`carried_facts` is a sum of live facts at barriers, not distinct surviving nodes.
`cross_stage_live_facts` counts current bodies born before the current epoch.

The old “retired before subscribing” metric is not the coverage objective.
Live bodies must remain unsubscribed across stages. Operation credit charges
marker reads, boundary work, local traversal/completion and candidate-domain work,
in addition to existing matching/publication costs. Occupancy is not rewarded
again. The ledger remains an equal-weight, non-exhaustive operation model.
Static marker emission makes no positive performance-admission claim.

Seven focused tests cover persistent no-union bodies, late congruence cascades,
deletion and mutable merges, several native/foreign result alias patterns,
bounded owner splits, complete equality candidate domains, and corrupted Bake
descriptors. Each semantic fixture compares every Run's graph, bindings and
schedule with the baseline and also runs in native egglog. Sparse and non-sparse
variants are checked before application evaluation.

The final workspace check passed **199 tests, with four preexisting ignored**;
the seven focused tests also passed without `sparse-cells`. The runtime passed
`cargo check --no-default-features`.

## Final application evaluation

Implementation was developed with structural counters and small correctness
fixtures. The final application phase uses the same two frozen catalogs, full
ordered audits, and one timing campaign after the structural gates pass.
Control and parent both enable result-port repair and shared Entry publication;
the owned lane enables `--cell-ownership`, which includes shared publication.
Parent is the archived `8fffff65` normal executable in `out/local-unions/runtime`.
Every timed invocation compares graph and semantic schedule. Audit executables
also compare ordered RHS, effective writes, resumes and normalized Spine traces.
Builds and audits finish before timing begins.

Both application audits and structural gates pass:

| Structural result | sum-bits | Raytrace |
|---|---:|---:|
| Eligible live constructor bodies / persistently owned | 2,895 / 2,895 | 658,670 / 658,670 |
| Live internal equality field incidences | 4,223 | 910,782 |
| Live boundary equality field incidences | 3,591 | 1,050,509 |
| Live deduplicated owner boundary edges | 1,500 | 600,341 |
| Legacy reverse edges, control → owned | 10,262 → 2,885 | 2,796,816 → 949,165 |
| Legacy repaired dependencies, control → owned | 1,496 → 450 | 479,589 → 255,111 |
| Key completions transferred into owners | 1,046 | 224,478 |
| Cross-epoch continuation events | 1,807 | 328,303 |
| Owned forward-body visits | 113,962 | 32,365,517 |
| Owned equality-port checks | 306,860 | 90,122,372 |
| Boundary body reads during refresh | 20,339 | 7,142,646 |

All eligible surviving bodies remain owned; this is no longer limited to the
90 rows that retired before subscribing in the preceding experiment. The old
per-row reverse index is actually absent for these bodies. Boundary membership
is new maintained state and must be counted: adding it to the remaining legacy
memberships gives 4,385 / 1,549,506, rather than claiming that all reverse routing
has disappeared. These counts are not byte-size estimates.

The exact-key probe count remains 1,046 / 224,478. That work has moved to owned
completion with canonical cached bodies; it has not vanished. Both applications
use the existing shared Entry/query routes without invoking the new graph-level
candidate-domain fallback. The latter is covered by a focused completeness test.

The monitoring also exposes the new cost: a boundary event currently traverses
its owner's bounded forward body, then changed owners refresh their boundary
sets. Many inspected ports are unaffected. Typed ownership coverage is complete
for this scalar family, but this executor does not yet compile each boundary
event into the smallest affected expression slice or fuse repeated owner visits
across a union batch. The final timing includes this cost.

Measured on 2026-11-08, Apple M3 Max / arm64, Rust 1.94.0, release builds.
One warmup per lane is excluded; sum-bits has 31 samples per lane and Raytrace
has seven. Lane order is deterministically shuffled within each repetition.
Times below are medians of
inference only, excluding setup and export; RSS is the process peak through
inference, including setup. All raw samples are retained in the text artifacts.

| Final measurement | sum-bits | Raytrace |
|---|---:|---:|
| Parent `8fffff65` inference | 21.512 ms | 7.643 s |
| Current binary, ownership disabled | 21.617 ms | 7.763 s |
| Current binary, ownership enabled | 27.164 ms | 11.845 s |
| Enabled / disabled time change | **+25.7%** | **+52.6%** |
| Enabled / parent time change | +26.3% | +55.0% |
| Repair phase, disabled → enabled | 1.398 → 6.000 ms | 0.546 → 4.247 s |
| RHS phase, disabled → enabled | 5.348 → 6.020 ms | 2.116 → 2.321 s |
| Peak RSS, disabled → enabled | 168.75 → 171.14 MiB | 1,868.48 → 1,768.25 MiB |

The median paired enabled/disabled time changes are +26.4% and +52.4%.
Phase medians are computed separately and need not sum to the total median.
The disabled binary's medians are +0.5% / +1.6% above the archived parent;
this campaign does not isolate the cause of those smaller differences.

**This is a structural coverage success and a CPU performance regression.**
Persistent ownership removes the old internal subscriptions, but coarse owner
traversal and boundary refresh cost more than the displaced maintenance. Most
of Raytrace's extra time appears in repair, consistent with the 32.4 million
body visits and 90.1 million port checks. The reduced Raytrace RSS does not
compensate for that throughput loss; the backend remains explicitly opt-in.
These results do not establish insufficient egraph sparsity. The next unresolved
compiler task is to express the affected port slices as shared local programs
and combine repeated union propagation within an owner without changing ordered
collision/publication semantics. Increasing coverage or owner size alone would
not address the measured traversal amplification.

See `monitor.json` for the structural gates, `audit.json` for trace digests,
`bake.json` for compiler-only coverage and `timings-*.json` for every sample.
These files are produced by the commands below; output directories must be new.

```sh
mkdir -p out/cell-ownership
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
cp target/release/eggfuse-cell-runtime out/cell-ownership/runtime
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes
cp target/release/eggfuse-cell-runtime out/cell-ownership/audit-runtime
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake
cp target/release/eggfuse-cell-compiler out/cell-ownership/compiler
out/cell-ownership/compiler bake-cell-ownership --program out/producer-receipts/learn-sum-bits/program.json --output out/cell-ownership/baked-sum
out/cell-ownership/compiler bake-cell-ownership --program out/producer-receipts/indexed-audit-learn-raytrace/program.json --output out/cell-ownership/baked-raytrace
python3 benchmarks/result-port-repair/audit.py out/cell-ownership/audit-runtime benchmarks/cell-ownership/audit-manifest.json out/cell-ownership/audit
python3 benchmarks/leaf-completion/measure.py benchmarks/cell-ownership/timing-sum-manifest.json out/cell-ownership/timing-sum --repeat 31
python3 benchmarks/leaf-completion/measure.py benchmarks/cell-ownership/timing-raytrace-manifest.json out/cell-ownership/timing-raytrace --repeat 7
python3 benchmarks/cell-ownership/collect.py out/cell-ownership benchmarks/cell-ownership
```
