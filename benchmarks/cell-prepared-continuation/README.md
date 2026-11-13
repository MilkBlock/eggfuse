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
