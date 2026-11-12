# Write completion events transfer the lifecycle owner

This checkpoint covers the actual standalone Cell CPU, not native egglog. The
work-count control is `c27cbcf1`; frozen programs and catalogs are unchanged.
The periodic whole-runtime timing comparison is recorded separately below when
complete. Work counters alone do not establish a speedup.

## Opportunity and compiler proof

The preceding Raytrace execution had 793,538 distinct scalar write targets and
755,389 changed rows. Their inputs and actual writes already ran on workers,
but every target returned through a full `Finished` vector before the source
thread retired writers, retained parents, installed producer-directory entries,
updated membership/subscriptions and recorded table changes.

The existing Eq-to-i64 Cell `PortWrite` plan, old/min/max merge proof, immutable
constructor-parent restriction and input-ready/checked-arithmetic boundary make
this region independent of mutable reads and union. Original source ordinal
still determines same-key winners. Target-index order determines lifecycle
retirement exactly as before, including releases that affect a later retained
writer. These typed compiler facts permit the existing table owner to finish
the region; no new runtime fact graph, bindings or producer-consumer lists are
created. Across Runs, the same Cell switch and Shared Entry projections consume
the final rows at their original visibility boundary.

## Connected path

The existing target array owns original mutable Function/decoded-row references
and candidate slices. Workers compute blocks of up to 64 targets and leave
completion metadata in that same array. A completed block transfers its original
slice to the ready-prefix slots. Any worker can take the single lifecycle owner
and consume the ready target prefix while other blocks continue computing.

The event mutex protects only publication and transfer of those original owners.
Retirement, parent-reference updates, writer-directory installation, membership,
ordinary subscription replacement and change notifications run **outside** that
mutex. Other producers can publish and continue while the owner is active. The
owner is returned and readiness checked under the same lock, preventing lost
handoffs. There is no waiting receiver or condition-variable barrier, including
with one worker. Fatal worker/consumer panics still join other jobs and unwind;
this is not a general rollback promise for panics.

The old full `Finished` vector and source per-target maintenance loop are gone.
Ordinary Graph retirement and worker retirement use one shared implementation
over the same directory, Cell storage, parent counts and garbage set. Likewise,
both paths use the same subscription replacement algorithm. For a new typed
scalar row, the Eq input is already canonical in this epoch; inspecting the
i64 output and rereading the row through Graph are unnecessary. Its real Eq
reverse subscription remains present.

Lifecycle work on shared maps remains ordered under one owner. It is overlapped
with row computation, not declared independently parallel. Cell publication,
Cursor processing, constructor-index adoption, ordered effects and the original
Run visibility fence remain outside this takeover. The pool still joins before
returning to source publication; this does not eliminate every batch boundary.

## Work and cost

Features and flags match the preceding checkpoint:

```text
features: cell-absorption,view-ports,parallel-publication
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

| Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Target rows whose lifecycle/notifications finish on workers | 0 | 793,538 |
| Actual changed rows | 755,389 | 755,389 |
| Worker completion blocks | 0 | 14,067 |
| Blocks fully retired with other write blocks unfinished | 0 | 4,746 |
| Write pool calls | 3,660 | 3,660 |
| All scalar-write payload capacity, cumulative bytes | 197,995,912 | 181,969,416 |
| Event task/slot payload capacity, cumulative bytes | 0 | 450,144 |
| New scalar subscriptions | 4,385 | 4,385 |
| Global query lookups | 4,027,756 | 4,027,756 |

The new event payload is included in total temporary capacity. The 16,026,496
byte reduction is cumulative capacity, not peak memory or a complete allocation
trace. A single target allocation replaces independently grown target and
completion arrays; original row payloads and successful input slots are reused.
Scheduling and short mutex acquisitions add work. The overlap counter checks
actual unfinished computations **after** retiring a block, not queued callbacks;
it is neither CPU utilization nor saved elapsed time.

Typed subscription completion omits 4,385 scalar field visits and root rereads;
subscription calls, reverse-edge occupancy and all reverse-index operations
remain exact. Duplicate candidates, invalidations, final writes, logical
improvements, writer reuse and extra new-key probes also remain exact. sum-bits
has no eligible scalar write batches and retains 14,012 global lookups.

`execution_ns` now includes event retirement, while `boundary_ns` contains only
source setup. Their old and new subdivisions are not directly comparable and
are not isolated wait measurements. The complete timing campaign must determine
whether this and the preceding changes repay their dispatch/storage costs.

## Validation

158 runtime tests and 85 relevant integration tests pass, plus forced hash/Bloom
collision checks, all-feature, sparse-only and legacy builds. A handshake test
blocks a later producer until an earlier prefix retires; whole-batch retirement
would time out. Tests cover empty/single-worker work, reordered completion,
producer and consumer panic, retained writer promotion, later garbage collection,
membership and subscription consistency. Existing min/max/old fixtures compare
source effect digests, duplicate writes, union and downstream Run snapshots.
The checked-arithmetic failure path still preserves the original effect prefix.

Frozen sum-bits/Raytrace final exports, all 1,428 / 16,883 ordered Run summaries
and logical effects match `c27cbcf1`. Run summaries are not whole-graph snapshots;
the small integration fixtures cover those boundaries. Native sum-bits acceptance
is `pass`, with its saved CPU export hash checked against this execution.
Raytrace remains an exact differential check, not an extended native proof.
The README compile/run/single-repeat bench smoke commands also pass.

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-write-completion/semantic-acceptance.json
python3 benchmarks/cell-write-completion/check.py out/cell-write-owner out/cell-write-completion benchmarks/cell-write-completion/results.json
cargo cell-compile --case sum-bits --output out/cell-write-completion/readme-program
cargo cell-run --program out/cell-write-completion/readme-program/program.json --output out/cell-write-completion/readme-run
cargo cell-bench --program out/cell-write-completion/readme-program/program.json --repeat 1
```

Use fresh output directories for the Cargo smoke commands. Historical timings
are not used as an apples-to-apples claim about this runtime.
