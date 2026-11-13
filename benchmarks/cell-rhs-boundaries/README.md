# Entry maintenance after Cell completion

This experiment measures the actual standalone Cell CPU, not native egglog.
The frozen current-branch reference is `704d1c0e`, with four query workers,
Cell absorption, repair ports, parallel residuals and parallel publication.
The preceding query-fragment experiment was speed-neutral; its reduction in
coordinator row routing is not counted as a whole-pipeline speedup.

## Observed opportunity and remaining obligations

A separate four-second macOS stack sample captured 1,210 main-thread samples,
1,209 under inference and 317 under `publish_finished_tables`. These are bounded
wall-residence observations, not CPU percentages; inclusive stacks overlap.
Table owners already trigger dependent Sieve conditions within their worker
scope, so adding that mechanism again would not remove an existing barrier.

The reference Raytrace execution performs 1,950,525 Entry updates in table-owner
tasks. Existing packets are removed from their witness map and epoch index,
then reinserted even when the witness remains valid. Row-allocation reuse
(1,374,605 occurrences across Entry paths) does **not** prove unchanged values
or epochs. The candidate measures those distinct cases rather than inferring
them from this allocation counter.

The compiled Entry identifies its table, predicates and witness-keyed storage.
After the current row passes those predicates, its existing map position can
be updated directly. An unchanged epoch also retains its existing delta index
membership. Worker updates and warm single-Entry serial refreshes use the same
operation. Cold enumeration and shared decoding among multiple Entry nodes
retain their existing paths. Existing publication handles stay with the packet.

This uses executions of the current catalog to delete maintenance on already
known Entries; a new Bake iteration cannot prove current mutable values or
retirement from historical observations. Across Runs, only the established
witness/epoch membership is retained. Current values are still read, template
predicates still checked, and changed epochs still move delta membership.
Hidden, retired or rejected rows are removed. Borrowed seeds keep their prior
immutable snapshots. No source Run becomes visible early, no residual query
is skipped and no runtime fact graph or consumer subscription is added.

New counters distinguish retained map positions and retained epoch membership.
They count actual updates, not logical matches or committed graph mutations.
There is no new per-instance storage or dispatch; the additional epoch comparison
and counters remain part of measured runtime cost. The final performance verdict
must come from the sequential timing trial, not from these counters.

## Reproduction

All commands that execute workloads, builds or tests run inside the shared
`eggfuse-job` queue. A frozen reference is created with `reference.py CONFIG
OUTPUT BINARY ACCEPTED COMMIT`; CONFIG and ACCEPTED are existing work artifact
roots. The script checks exact states, all 1,428 sum-bits and 16,883 Raytrace Run
summaries and logical effects. It also invokes the unchanged native sum contract
validator and binds its CPU-export hash to the new sum state. Raytrace remains
a differential check, not an extension of that native semantic contract.

`profile.py REFERENCE OUTPUT --delay 1.2 --duration 4` runs a separate diagnostic
with the same state/Run/effect checks. `profile.json` is its compact result;
full stacks and exports remain under `out/cell-rhs-boundaries/profile`.
Sampling is never combined with performance measurement.

Build the candidate in the isolated reference checkout, then use `reference.py`
again with the frozen reference as ACCEPTED. Run the entire control/candidate
comparison through `benchmarks/raytrace-parallel/quick.py` as one timing job.
All control samples precede every candidate sample. Neither lanes nor samples
are interleaved with other managed work.

The historical per-worker Sieve counters truncate when an inline publication
resizes their arrays to one element; this experiment does not use those counters
to estimate worker load or utilization. The sampled worker stacks are retained
as observations only.

## Verified work change

Candidate `9b107d45` passes 211 runtime unit tests, 110 compiler integration
tests, legacy/all-feature compilation and all three README Cargo commands.
The existing filtered-Entry regression formerly demanded allocation reuse even
for a row that no longer matched. It now requires retirement; its native result,
every-Run snapshot and binding/effect-order comparisons remain unchanged.
Unit tests independently exercise immutable old readers, in-place valid updates,
same-epoch value changes, publication handles, epoch counts, literal equality
after union, hiding and retirement/reinsertion.

Both workloads pass the fresh state/Run/effect checks and the native sum contract.
Accepted Entry updates, predicate checks, seed deliveries and retirements are
unchanged. The measured work deltas are:

| Removed maintenance | sum-bits | Raytrace |
|---|---:|---:|
| Existing packet map removal/reinsertion pairs | 586 | 1,375,425 |
| Epoch removal/reinsertion pairs | 0 | 0 |
| Writes to subsequently rejected packets | 0 | 1,112 |

Every covered existing packet changes epoch in these workloads. Therefore the
unchanged-epoch branch saves **no observed work** here; it is not speedup credit.
Row reuse still preserves borrowed snapshots. New counters add two words to the
existing statistics structure, including task-local copies; no new packet or
per-instance record is allocated. Full metrics and executable/source hashes are
in `results.json` and `provenance.json`. The work-run phase timings are diagnostic
and are not used as the performance acceptance result.

## Timing decision: not adopted

The entire comparison ran as shared timing job 32. All 48 sample/group boundary
guards were clear, and every timed state, Run summary and logical effect matched
its frozen reference. Sum has five measured samples and Raytrace three, each
after one warmup per lane; all control workloads ran before all candidate ones.
An earlier submission (job 31) was rejected before sampling because the shared
main worktree contained unrelated edits. Job 32 used the committed clean checkout
and the same frozen binaries, without borrowing any earlier samples.

| Inference median | Control `704d1c0e` | Candidate `9b107d45` | Change |
|---|---:|---:|---:|
| sum-bits | 25.868 ms | 26.529 ms | +2.56% |
| Raytrace | 5.246 s | 5.237 s | -0.18% |

This does **not** establish end-to-end acceleration or meet the requirement that
both workloads improve. Grouped timing and the observed spread cannot isolate
a stable causal speedup. No samples were discarded or retried to obtain a better
median. Candidate code is retained on `codex/entry-refresh-trial`, not merged into
the active runtime branch. `timing-results.json` retains individual samples and
the checksum/location of the full boundary observations.

The next structural opportunity is table-owner granularity. `Expr-size` alone
accounts for 1,057,016 of 2,155,707 owner-publication rows in the reference. A task
updates its columns and Entry states sequentially before releasing dependent
conditions. The conditions need the completed columns, not the Entry update.
Separate ownership of those existing structures can expose parallel work and
release conditions earlier. Any implementation must still finish all required
Entries at the Run visibility fence, preserve row/table error ordering, and
charge duplicate decoding and task preparation. This is a proposed next step,
not an implemented takeover or speedup claim.
