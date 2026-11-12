# Constructor ownership without a Unit-tail prerequisite

This measures actual standalone Cell CPU work against frozen `68fb07a4`, not
native egglog performance. Inputs, catalogs, release features and flags are
unchanged. This is implementation **three** after timing checkpoint `83ac944b`.
No new timing campaign or speedup claim is made.

## Opportunity and proof

The previous Raytrace execution completed 347,655 local constructor births.
Workers registered 103,774 of them; the source registered the other 243,881.
The local total includes inline local execution, not only worker computation.
The existing owner region required at least 32 Unit candidates spread across
multiple Unit tables. A complete constructor Cell without that tail could not
use the fact/index/subscription owners, despite already having the necessary
terminal-region proof and actual row allocations.

`prepare_cell_registration` now admits a proven constructor region independently
of that Unit condition. It requires at least 32 actual constructor plus Unit
rows to amortize owner dispatch. Pure Unit-only regions retain their old gate.
The compiler's completed terminal suffix, current parent epoch, supported local
storage, ordered Cell identities/parents, unused fact slots and typed repair-key
columns remain required. Pending union/dirty work or unproved coverage retains
ordinary execution. No Bloom/hash match substitutes for exact equality.

The existing actual row and slot allocations pass to the existing owners:

```text
completed Cell rows
    -> fact slots + constructor index/membership/change owner
    -> reverse subscription owner
    -> each Cell's ready fact slots permit source completion
    -> original Run boundary opens successor queries
```

Workers perform the actual index insertion, membership/change preparation and
subscription work. Source adoption consumes publication counts and actual
slots instead of repeating `activate_fields` and subscription installation.
There is no second graph or binding copy. The constructor index is still a
single owner within a region; this does not claim table-sharded constructor
concurrency.

For a pure constructor region, Function arrays stay in Graph. There is no
Function reservation, structure-ready dependency or structure completion event.
With Unit rows, the existing reservation and exact winner/invalidation path
still applies. Source effect/error order and publication order are preserved.
Shared directories and subscriptions must return before their readers resume.

Across Runs, Shared Entry still projects the original instance's actual results.
The existing Bake evidence is checked unchanged. This change discharges source
registration of already-proved local regions; it establishes no new cross-Run
visibility or equality proof.

## Lifecycle correction found by the real workload

An initial Raytrace execution exposed an old registration assumption: an
all-reuse Cell can complete and release its empty frame, but the final offered
certificate still attempted to read that frame during rollback checking. The
initial failed run and logs are preserved under
`out/cell-independent-registration-before-retirement`; they are not accepted
validation or timing samples.

Only Cells that actually prepared fresh constructor facts now retain that
rollback obligation. The existing publication fragment supplies the evidence;
no new liveness hold or per-Cell flag is needed. All-reuse Cells retire normally.
Unaccepted fresh rows still lose their index entries, memberships, changes and
subscriptions. The final workload and an explicit duplicate-root/retirement
test verify this path, including aborted prefixes and subsequent repair.

## Actual work and additional costs

| Observation | sum-bits control / candidate | Raytrace control / candidate |
| --- | ---: | ---: |
| Local constructor births | 1,474 / 1,474 | 347,655 / 347,655 |
| Constructor rows registered by workers | 0 / 134 | 103,774 / 181,166 |
| Local constructor rows registered on source | 1,474 / 1,340 | 243,881 / 166,489 |
| Rows admitted independently of the old Unit gate | 0 / 134 | 0 / 77,021 |
| Registration regions / pool invocations | 0 / 7 | 1,024 / 2,939 |
| Regions with no Function reservation | 0 / 1 | 0 / 1,327 |
| Source execution frames | 5,176 / 5,176 | 1,020,600 / 1,020,600 |
| Ordinary key lookups | 13,028 / 13,028 | 3,830,075 / 3,830,075 |
| Constructor registration capacity, cumulative bytes | 0 / 14,024 | 8,876,752 / 15,132,872 |
| Fact-slot return capacity, cumulative bytes | 0 / 7,904 | 3,852,992 / 10,190,128 |
| Common/Unit registration capacity, cumulative bytes | 0 / 19,640 | 9,871,328 / 13,091,080 |
| Registration-event capacity, cumulative bytes | 0 / 15,808 | 2,522,624 / 6,198,400 |
| Candidate Function slots reserved | 0 / 132 | 109,908 / 124,678 |
| Unit rows installed/subscribed by workers | 0 / 73 | 70,411 / 80,283 |

The local path's source registration falls 9.1% / 31.7%. Raytrace workers register
52.1% of local births, up from 29.8%; the whole workload still has 820,439 logical
fact births. This coverage is not overall parallel utilization. Net additional
worker registration (77,392 rows) differs slightly from independent-gate rows
(77,021), because completion arrival changes the remaining region sizes.

The new path pays for constructor-row admission checks, more owner dispatches,
fact-slot events and retained buffers. Existing `unit_registry_*` counters name
the shared registration machinery and now also count constructor-only regions;
the new constructor counters distinguish their coverage. Capacity is not peak
memory or a complete allocation trace. The number of top-level RHS dispatch
regions is essentially unchanged (9,063 / 9,061). Source frames and queries are
unchanged. More worker registration does not establish lower wall time: the
extra owner regions must remain part of the next timing gate.

The next structural opportunity is to combine producer completion with ownership
of its registration work, reducing the second dispatch and source preparation.
The current global directory lease, source error order and actual key/result
dependencies remain live constraints; this change does not claim that fusion.

## Validation and reproduction

179 runtime tests and 89 relevant integration tests pass, plus forced hash/Bloom
collision checks and all-feature, sparse-only and legacy builds. Tests now cover
zero/one/two Unit tables, unchanged Function-array allocation for constructor-only
regions, rejected small/unproved regions, prefix completion while index and
subscription owners are blocked, and all-reuse Cell retirement. The native-backed
integration fixture compares every Run through same-Run reads, deletion,
recreation and late union with one/four-worker execution. README compile/run/
single-repeat bench smoke checks pass.

Frozen final exports, all 1,428 / 16,883 ordered Run summaries, logical effects,
reverse-index occupancy and iterative Bake evidence exactly match the control.
The unchanged native sum-bits choice contract returns `pass`, linked by the
fresh CPU export hash. Raytrace remains differential validation only. Final-state
agreement does not replace the tests' intermediate Run snapshots.

Features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-independent-registration/run.py out/cell-worker-runs FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-independent-registration/check.py out/cell-worker-runs FRESH_OUTPUT RESULTS.json
```

The checker requires successful validation/README records using the commands in
[results.json](results.json), with fresh output paths. The manifest records input
paths, flags and the frozen binary hash. Raytrace exports were losslessly gzipped
after SHA-256 verification; the checker accepts both forms. Only generated test
executables from completed recorded checks were removed to free local disk space;
their sources and validation logs remain.
