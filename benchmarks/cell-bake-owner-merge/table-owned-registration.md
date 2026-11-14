# Table-owned constructor continuation during admission

The preceding actual Raytrace execution registered 190,981 ownership rows on
workers, but only 6,288 were registered directly by the producer continuation.
The other rows still returned to source and entered a second worker dispatch.
The whole constructor directory had to leave Graph, so this fused path could
not accompany ongoing source admission. That is an ownership boundary wider
than the Cell's typed operations require.

The existing constructor instruction plans already identify all written tables,
the terminal cone, allowed aliases and actual result slots. No additional Bake
catalog or runtime fact representation is needed to use that information.
Canonical hash storage is now partitioned by authoritative table, preserving
ordered exact-key candidates within each table. Workers lease only the written
table indexes, member sets and deferred changes. Unrelated tables stay attached
to Graph. A leased index is explicitly unavailable; neither an empty bucket nor
the nullary member shortcut may misinterpret it as proof of absence.

Canonical ownership's background Cell producer can now continue straight from
construction into physical registration, using the existing completion slot and
source-ordered directory owner. Source acceptance consumes the returned original
fact slots and publication certificate. This deletes the second registration
dispatch, its flattened row input and registration-event queue for the covered
region. Source admission can continue through pure calculations, valid prepared
witnesses and operations on other tables. An unresolved access to a leased table
waits for that table owner to return. No new per-producer consumer list is built.

The shared constructor directory still has one mutating owner at a time within
each continued wave. This does not make arbitrary same-table writes concurrent.
Port binding and component selection remain source ordered, and later waves can
still wait on the existing bounded queue. The change replaces a whole-directory
restriction with explicit table ownership; it does not claim full utilization.

Open-admission takeover requires canonical ownership, original empty fact frames,
covered operations, pure terminal constructor tails and valid parent order. Old
fact prefixes must remain readable during admission. Unit tails and other storage
backends retain their existing path. Actual foreign results are checked at source
adoption before ownership binding; source errors restore every original owner,
then invalidate only the unadopted suffix. Source Run visibility, equality epochs,
mutable effects and all exact key checks outside existing proofs remain live.

The cost includes per-table index headers, directory fragments and table wait
checks. Existing storage accounting includes the new headers. New counters record
background fused regions/Cells and encounters with a leased table; they measure
coverage and boundary encounters, not CPU utilization or time spent waiting.
The full-workload comparison must charge them together with event/registry bytes,
source work and inference time.

Validation includes a deliberately paused producer: while it retains one table,
source constructs and reads another table before that producer is released.
Only one earlier Cell is then adopted, all later rows are invalidated, and a
subsequent cross-input union/repair retains correct lookup. Equal hash values
in different tables also retain independent order and retirement. Existing
ownership integration tests require the new background path to run, while still
comparing every fixture Run graph, ordered bindings, foreign returns, learned
composition choices, deletion/recreation and first-error behavior.

Job 469 passes 220 runtime tests and 119 compiler/runtime integration tests.
Job 470 passes the final 220 runtime tests, 76 ownership tests with storage
instrumentation, 100 default-backend runtime tests and a no-default-feature
compile. Complete workload checks follow separately. Reproduce
workload validation with `owner_workers.py`, reusing the verified `62c5f984`
control. Time the entire original control, the entire `5bb451e3` registration
candidate and the entire current candidate under one lease with
`prepared_timing.py --include-ordinary --previous-experiment PREVIOUS`.

## Full workload result and admission

Implementation `843c1ca0` passes job 471. Native sum-bits choice acceptance is
`pass`; original sum-bits and Raytrace preserve final state, all 1,428 / 16,883
Run summaries and logical effect counts. The unchanged 408-recipe sum-bits
catalog also preserves final state, all 1,428 Run summaries and effects. The
Raytrace and learned-catalog checks are differential checks, not native proofs
or full-program per-Run graph comparisons. The integration fixtures separately
cover exact Run snapshots, actual foreign results and error/retirement ordering.

Job 474 measures the actual standalone Cell CPU runtime with four workers and
canonical ownership. It finishes the entire original control, then the entire
preceding registration experiment, then the entire candidate under one timing
lease. Each case has one warmup followed by five measured sum-bits samples or
three Raytrace samples. All 114 process-boundary guards are clear.

| Inference median | Control `62c5f984` | Previous `5bb451e3` | Candidate `843c1ca0` | vs. previous |
| --- | ---: | ---: | ---: | ---: |
| Sum-bits | 24.712 ms | 31.354 ms | 31.132 ms | -0.71% |
| Raytrace | 4.576019 s | 5.012209 s | 5.059122 s | +0.94% |
| Existing sum-bits catalog | 22.346 ms | 30.752 ms | 31.691 ms | +3.05% |

Versus the original control, inference is 25.98%, 10.56% and 41.82% slower.
**Speed admission fails; keep this experiment unmerged.** The Raytrace control
samples are 6.839207, 4.571424 and 4.576019 seconds; the outlier is retained.
Boundary guards do not exclude thermal/order effects or all OS activity. Small
differences against the preceding experiment are not precise stable code-effect
estimates. Absolute times from older timing leases are not reused.

The work reports show substantial takeover without an overall speedup:

| Raytrace work | Previous | Candidate |
| --- | ---: | ---: |
| Constructor rows registered on workers | 190,981 | 233,271 |
| Rows registered within the producer continuation | 6,288 | 102,359 |
| Cells registered within the producer continuation | 5,433 | 97,102 |
| Cells using background construction plus registration | 0 | 91,637 |
| Background construction plus registration regions | 0 | 1,567 |
| Unresolved accesses waiting for a leased table | 0 | 1,552 |
| Constructor registry bytes | 15,345,112 | 12,733,032 |
| Returned frame bytes | 14,821,144 | 20,267,536 |
| Registry event bytes | 5,903,872 | 4,318,080 |
| Source instances admitted while a producer is outstanding | 64,905 | 24,196 |
| Scheduler jobs | 216,390 | 216,434 |
| Ownership signal bindings created | 2,151,665 | 2,151,665 |

Byte counters are cumulative structural charges, not peak heap. The frame-byte
increase offsets the decrease in registry input bytes; removing one handoff did
not eliminate its entire storage cost. Table waits count encounters, not elapsed
waiting or idle-core percentage. There are almost as many wait encounters as
background regions, and fewer source instances overlap producers. This is
evidence that table ownership is still too broad for this workload, not a
measurement of its isolated time cost. Event grouping can also change counts.

Neither sum-bits variant enters the new background fused path. Their timing
changes cannot establish a benefit from it. Table index partitioning and
background fusion changed together, so this experiment cannot attribute either
workload's time difference solely to the removed second dispatch. Existing
source port binding remains serial and all 216,434 short scheduler jobs remain.

The requested Bake lineage is `codex/cell-result-routing`, containing
`d0d8ee33` and ending at `98540661`; control `62c5f984` already includes it.
Its activation-bounded catalog shows how to reuse compiled Entries and actual
result witnesses without activating another population of runtime records.
The next structural opportunity is to extend that actual-result coverage across
construction and registration, so a source read does not require taking back an
entire table. It must discharge an existing lookup or handoff with typed evidence
and live results, rather than add another speculative route before the same
fallback. Birth-time port binding, exact foreign result identity, unresolved
same-table conflicts, source error order and Run visibility remain obligations.

Exact samples, binary/input hashes, validation and work reports are indexed in
`table-owned-registration.json`. This evidence does not justify promoting the
worker experiment into the already-merged Bake branch.
