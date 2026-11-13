# Canonical ownership continues constructor Cells on workers

The preceding activation-bounded Raytrace catalog saved 2,974 of 4,332,972
queries, without expanding worker mutation scope. The installed catalog already
provides source Entry wiring, component symbols and actual-result demands.
The next opportunity is to execute the existing fresh-cone instruction plan
under canonical ownership, preserving those proofs through worker suspension.
Adding more recipe IDs does not remove the ownership backend rejection.

This change gives both ordinary execution and batch admission the same Entry
setup. Suspension moves that Entry with the original Cell; adoption restores it
before births and clears it on success or error. Exact root hits and prepared
resumptions supply their actual returned witnesses. A shared worker cone retains
only foreign returns before its first local birth, and only while an active
Entry still needs result evidence. These transient candidates are validated in
source order before the first birth; no bindings, consumers or retained history
are duplicated. Candidate count and allocated bytes are charged separately.

The worker fills actual row storage and resolves duplicate pure roots through
the existing peer result slots. Source adoption still calls `activate_fields`,
which installs ownership and binds the compiled ports exactly once. It no longer
replays constructor lookup/key preparation for the completed cone. The old
registration fast path still assumes `owned:false` and reverse subscriptions;
it remains ineligible for ownership rows. Unit table registration can retain
its independent eligibility. Stable-port, digest and local-union backends keep
their existing birth-time constraints.

This is a worker construction takeover, not parallel ownership registration or
complete removal of serial publication. No claim that all threads are full is
made. Source/effect/error order, union epochs, actual foreign result identity,
Run visibility, deletion/recreation and residual queries remain authoritative.
The newly possible in-flight source observation is `pending_completion`, not a
proof of a saturated RHS. Tests still require exact graphs/bindings and exact
source-ordered composition proposals; they no longer require serial and
parallel saturation diagnostics to have identical pending populations.

Job 423 passes 119 compiler/runtime integration tests, including three new
ownership worker cases. Job 426 passes 217 runtime unit tests and 76 ownership
tests with storage instrumentation, plus the no-default-feature compile.
Workload validation and timing follow as a separate experiment; these tests
alone do not establish a speedup. Comparisons use entire control then candidate.

Root absence also requires the ownership completion queue to be settled.
Owned keys can remain pending after equality is committed while the ordinary
dirty queues are empty. Job 434 proves this exact case rejects worker admission
before repair and returns the existing constructor after repair.


## Complete workloads and grouped timing

Compare `62c5f984` with `cf65e4b1`, using frozen release binaries with
`cell-absorption,view-ports,parallel-publication`. Both use four query workers,
parallel residuals/publication, execution grain 1, repair ports and canonical
Cell ownership. Stable ports are not enabled. This is the actual standalone
Cell runtime, not upstream egglog or a measurement of worker utilization.

Job 436 preserves final state, all 1,428 sum-bits / 16,883 Raytrace Run summaries
and logical effects. Native sum-bits choice acceptance is `pass`. The unchanged
408-recipe sum-bits catalog also preserves state, Run summaries and effects.
Raytrace and the learned catalog are differential checks, not native semantic
proofs or whole-program per-Run graph equality. The integration fixtures separately
check every Run graph and ordered bindings across union, deletion and errors.

Job 428 had already exported both control workloads when native acceptance
returned `inconclusive`: the new checkout had no saved reference directory yet.
After restoring that path, job 432 verified the saved exports and native proof,
without replaying those workloads. Job 436 reuses the verified control binary.
No inconclusive result is counted as acceptance.

| Quantity | Control | Candidate |
| --- | ---: | ---: |
| Raytrace key queries | 4,332,972 | 3,974,644 |
| Raytrace worker constructor operations | 0 | 329,913 |
| Raytrace local births / local reuses | 0 / 0 | 352,978 / 5,350 |
| Raytrace queued jobs / batches | 0 / 0 | 216,383 / 6,554 |
| Raytrace local directory checks | 0 | 3,152,891 |
| Raytrace cumulative queue bytes | 0 | 200,400,456 |
| Raytrace cumulative event bytes | 0 | 201,990,352 |
| Raytrace owned births | 820,311 | 820,311 |
| Raytrace ownership signal bindings created | 2,151,665 | 2,151,665 |
| Sum-bits key queries | 14,653 | 12,984 |
| Sum-bits worker constructor operations | 0 | 1,502 |

The byte counters charge cumulative allocations/capacities, not peak retained
heap. Constructor operations include reuse and are not counts of new committed
mutations. Root admission still prepares/hashes keys; an omitted query counter
is not automatically an omitted hash or the removal of all query work.
The plain Programs need no foreign Entry-result array. The learned sum-bits
catalog exercises four worker result candidates and keeps all 709 baked joins.

Job 438 runs the entire control lane before the entire candidate lane, under
one timing lease; all 76 boundary guards pass. There is one warmup per case,
five measured runs for each sum-bits configuration and three for Raytrace.

| Inference median | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| Sum-bits | 27.117 ms | 33.479 ms | +23.46% |
| Raytrace | 5.580270 s | 6.081302 s | +8.98% |
| Existing Bake catalog, sum-bits | 27.197 ms | 35.002 ms | +28.70% |

**Performance admission fails.** This remains on `codex/owned-worker-births`;
it is not merged into the default execution branch. Exact source identities,
retained samples and counters are in `owned-worker-births.json` and its indexed
artifacts. Neither the workload migration nor the query decrease is a speedup.

The next structural target is the very short job and its source adoption:
216,383 jobs move 329,913 worker constructor operations, while all ownership
births and port binding still require ordered source work. The measurements
identify new work worth removing, but do not isolate one cost as the sole cause
of regression. Keep the compiled constructor coverage; combine computation,
owned registration and publication in the same execution unit instead of
claiming success from a smaller task packet or reduced query count alone.

Reproduce with the shared compute queue:

```sh
python3 benchmarks/cell-bake-owner-merge/owner_workers.py ACCEPTED_NONOWNER TARGET CONTROL_CHECKOUT OUTPUT \
  --learned-program ORIGINAL_WITNESS_PROGRAM
```

Then submit the whole comparison with `--kind timing`:

```sh
python3 benchmarks/cell-bake-owner-merge/prepared_timing.py OUTPUT ORIGINAL_WITNESS_PROGRAM TIMING_OUTPUT \
  --repeats 5 --include-ordinary
```

`--include-ordinary` selects the original sum-bits/Raytrace Programs in addition
to the learned Program; all three lanes here still enable canonical ownership.
