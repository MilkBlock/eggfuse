# Consume prepared witnesses before Cell queue maintenance

Control: `64f022a8`, after the complete structural Bake refresh. Measurements
use the actual standalone Cell CPU and the same frozen programs, catalogs and
four-worker flags. Native egglog acceptance is limited to the reviewed sum-bits
contract; Raytrace remains a differential runtime check.

## Execution evidence and proof

The preceding catalog's actual Raytrace execution validates 249,772 prepared
constructor certificates, accepting 248,685 without reading their key fields.
Nevertheless, the batch admission path can first reconstruct that constructor's
key for a root-conflict fence or pending-input scan, then enter the generic RHS
boundary to consume its witness. Sum-bits has 1,704 accepted certificates.
These are existing checked matches, not evidence that an unseen Cell route is
complete. No new training or marker materialization is needed for this takeover.

The compiler already identifies the selected source operation and proves that
its key comes from immutable captured inputs and completed scalar operations.
Its original source-Run union certificate, current table readiness and the
actual witness's incarnation/visibility still decide whether direct reuse is
legal. The shortcut accepts only a foreign witness from that read view, with no
active local-birth window, pending repair, static alias or higher-priority
history transfer at this position. Unknown cases keep their existing path.

A cross-Run switch can reuse a completed constructor only under those existing
entry and lifetime proofs. This change consumes that supplied result once at
its original source position. It neither moves effects across Runs nor proves
new closed regions. Wider learned Cells can supply more such witnesses later;
their own residual, delta, visibility and retirement obligations remain live.

## Work removed

An accepted certificate writes the actual result and demanded receipt directly
into the existing Cell storage, advances its instruction position, and continues
admission. It removes the corresponding root-conflict/key preparation, pending
dependency scan, generic boundary call and local-birth window probe. The result
is already public immutable input; unfinished peer births cannot supply its key.
This remains coordinator-side validation, not newly parallel graph mutation.

If the snapshot certificate fails, its witness changes from `Snapshot` to `Key`.
The original forwarding/liveness/exact-field fallback still executes at the
source boundary, but it does not repeat the same certificate. This replaces
the existing optional witness with an equally sized tagged state; it adds no
binding copy, result cache or maintained dependency graph.

A fully completed constructor-only Cell with no new facts, mutable/union
effects or publication Cursor can release its existing state immediately.
There is no receipt/Entry publication to order behind earlier worker tails.
Cells with publication responsibilities or effects still use the ordered queue.
Original Cell ID reservation, source error prefixes and Run visibility remain
unchanged. The optional projection observer receives the actual returned
witness even when no consumer demands a runtime receipt.

## Costs and metrics

Three scheduler counters charge accepted direct resumptions, certificate-to-key
fallbacks and completed instances released while the queue is nonempty:
`prepared_resumptions`, `prepared_key_fallbacks`, `completed_without_queue`.
They add 24 bytes to the aggregate scheduler, not to each Cell or worker result.
The normal admission loop adds a witness-state/eligibility check; rejected
certificates retain the original full key fallback cost.

The proof check itself still exists. A new resumption and a removed generic
boundary describe the same constructor operation and must not be added as two
saved constructors. Report certificate/result reads, exact queries, argument
preparation, queues, temporary capacities and worker work together. Fewer queued
owners may also change batch formation; reduced counters alone do not prove a
speedup or full CPU utilization.

## Frozen work result

| Work, control → candidate | sum-bits | Raytrace |
| --- | ---: | ---: |
| Direct prepared resumptions | 0 → 711 | 0 → 71,777 |
| Completed instances released beside queued work | 0 → 18 | 0 → 4,863 |
| Root conflict probes | 451 → 193 | 61,326 → 33,568 |
| Counted admission/preparation operand fields | 4,132 → 3,557 | 605,964 → 561,509 |
| Generic constructor boundaries | 5,362 → 4,651 | 1,045,071 → 973,955 |
| RHS context suspend/resume pairs | 1,439 → 1,421 | 264,984 → 261,045 |
| Generic execution instances | 5,195 → 5,195 | 1,024,723 → 1,025,396 |
| Ordinary key lookups | 12,910 → 12,910 | 3,825,298 → 3,824,859 |
| RHS dispatch batches | 135 → 135 | 6,602 → 6,550 |
| Cumulative queue capacity bytes | 2,704,272 → 2,659,808 | 200,742,168 → 198,942,712 |
| Cumulative event capacity bytes | 1,036,176 → 1,026,840 | 192,306,024 → 192,482,888 |

Certificate counts, accepted result reads and logical constructor effects are
unchanged. Both workloads observe zero `prepared_key_fallbacks`; deletion,
hidden-provider and union tests separately exercise failure handling.
Immediate releases are not identical to the net reduction in suspend pairs:
batch changes also alter later source preparation. Raytrace adds 673 generic
execution instances and 278 lifecycle holds, all released, while event capacity
increases slightly. The capacities are cumulative work charges, not peak heap.
The operand counter covers admission/preparation, not every Graph field read.

These single frozen executions establish removed work and semantic agreement,
not a latency benefit. The authorized periodic timing uses the frozen current
control, previous `8df9de2a` checkpoint and historical `8335929d` baseline at
one and four workers, with separate quiet stack profiles.

## Periodic timing: no new speedup admitted

Implementation `c7874855` is the fifth implementation/merge since the previous
timing checkpoint. The immediate control is `64f022a8`; the older periodic
checkpoint is `8df9de2a`, and the retained historical baseline is `8335929d`.
All use the same source programs and runtime flags, with worker count changed
only between 1 and 4. Each lane has one warmup, then five sum-bits or three
Raytrace samples, interleaved in the saved seeded order. Every sample passes
the state, ordered Run-summary and logical-effect checks.

| Four-worker inference median | sum-bits | Raytrace |
| --- | ---: | ---: |
| Historical `8335929d` | 22.2995 ms | 5.923304 s |
| Previous checkpoint `8df9de2a` | 26.0190 ms | 5.384932 s |
| Current control `64f022a8` | 25.2148 ms | 5.138190 s |
| Candidate `c7874855` | 25.8943 ms | 5.152187 s |
| Candidate change against current control | +2.69% | +0.27% |

The current-control paired medians are +0.80% / -0.68%, so Raytrace's direction
is mixed while sum-bits regresses in both summaries. The gate requiring both
workloads to improve against the current control fails. The work reduction
above is real, but **this change is not admitted as a speedup**. The combined
window is directionally lower than the older checkpoint (-0.48% / -4.32%),
which must not be attributed to this last change alone.

Variation remains material: current-control Raytrace spans 5.136–6.087 s and
candidate spans 5.103–5.210 s; sum-bits spans 24.424–29.330 / 25.051–29.563 ms.
No samples are discarded. Sixty-two ambient process snapshots find no compiler
process, but cannot rule out other or shorter background activity.

Candidate one-worker medians are 18.8342 ms / 5.944242 s. Four workers are slower
on sum-bits and only 1.154× as fast on Raytrace. Whole-process CPU/wall is about
1.34 cores for four-worker Raytrace, but includes parsing/export/teardown and
must not be converted into an inference-only utilization percentage.

Separate quiet 3-second Raytrace samples contain 878 main-thread inference
samples in each lane. Main condition-wait samples are 192 → 205 (21.9% → 23.3%).
The candidate's wait contexts are query 95, publication 68, scalar RHS writes
26, other 16. Worker condition waits span 72.1%–79.7%, mostly thread-pool idle;
only 13 worker samples are classified as waiting inside a job. These are partial
sampled wall residence, not exact full-run wait time or CPU utilization.

The candidate main stack also includes query preparation/matching, query-result
completion, publication and repair. Those inclusive counts overlap and must not
be added. The sample does not prove a causal regression in synchronization, but
it gives no evidence that this cleanup fixed the synchronization problem. The
next priority is deleting the remaining query-to-execution/ publication handoff
and letting workers continue useful Cell work, rather than widening an admission
shortcut based only on its counters.

## Validation and reproduction

`results.json` records the frozen work executions, exact final-state hashes,
all ordered Run summaries, logical effects, reverse occupancy, iterative
evidence and balanced suspension/slot lifetimes. The saved native sum-bits
choice proof must return `pass` and match the fresh CPU export hash.

The integration fixture keeps unrelated constructor tails pending while another
Cell consumes existing results. It also deletes or hides those providers before
source execution: neither case may reuse stale identity or check a certificate
twice. Unit coverage includes union invalidation and the unchanged witness-state
size. Existing source-error, late-union, publication and forced-collision checks
remain required, including the optional projection observer.
203 runtime tests and 136 integration tests pass, with separate collision and
storage-observer runs. All-features, sparse-only and legacy builds compile.
Final exports, all 1,428 / 16,883 ordered Run summaries, logical effects,
reverse occupancy and existing iterative evidence match the control. The
reviewed native sum-bits choice validator returns `pass`.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-prepared-continuation/run.py out/cell-bake-refresh FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-prepared-continuation/check.py out/cell-bake-refresh FRESH_OUTPUT RESULTS.json
```

Run the exact successful validation/README commands retained in `results.json`
and save their status in `validation.json` / `readme-checks.json`. Generated
programs, binaries, full exports and caches remain under ignored local output.
The one-repeat README bench is a smoke check, not throughput evidence.

After committing the implementation and freezing the validated binary, run
`python3 benchmarks/cell-prepared-continuation/run_timing.py ARTIFACT_ROOT`.
The harness verifies the historical binary hashes, interleaves all samples,
checks every sample's final state/Run summary, records ambient compiler activity,
and validates separate 3-second inference stack windows. Retain all samples and
warmups; do not present sampled wall residence or whole-process CPU/wall as
inference-only CPU utilization.

The initial timing launcher stopped before any sample because macOS `ps`
returned a truncated non-UTF-8 process name. The ambient observer now decodes
such diagnostic text with replacement. Only benchmark/docs edits are permitted
after the frozen implementation commit; historical and candidate binary hashes
are checked before starting. The successful run and all warmups are retained in
`timing-results.json`; a successful verifier is semantic/evidence validation,
not a successful speed gate.
