# Constructor producers keep registration ownership

This is actual standalone Cell CPU work, not native egglog performance. The
control is frozen `4516c4a7`, with identical programs, catalogs and arguments.
It is implementation four after timing checkpoint `83ac944b`. No timing
campaign or speedup claim is made here.

## Opportunity and remaining proof obligations

The preceding Raytrace execution performed 2,939 registration pool calls after
producer completion. Moving 181,166 constructor installations to workers did
not remove the source's collection, admission and second dispatch. Its ordinary
key lookups and source execution frames remained unchanged. This is concrete
extra handoff work, not evidence that the egraph is insufficiently sparse.

For a closed admission region, the existing typed constructor plan can prove a
complete, pure suffix with no pending union/dirty work, no Unit tail, unused
fact slots and supported Eq key columns. Its actual execution block must end
there too. Every intervening no-job Cell must already be complete or stopped.
Original Cell order, parent dependencies and exact duplicate-result sharing
remain authoritative. At least two jobs and 32 planned constructor operations
are required; planned operations are not committed mutations.

Such a region now passes its original index, membership, change and subscription
owners to the producer scope. A worker holding the ready-prefix owner registers
the next completed Cell, then returns its actual results, original fact slots
and publication certificate together. Source adoption consumes that certificate
without a second registration dispatch or flattened row buffer. The next ready
Cell can complete before the rest of the producers finish.

The prefix mutex only protects result publication and owner transfer. Index
insertion and subscription installation run outside it. The directory still
has one mutable owner: this overlaps maintenance with other producers, rather
than independently parallelizing every insertion. Final source effect/error
order, exact aliases, retirement and original Run visibility remain live.
An unaccepted suffix returns all original owners before invalidating its rows.

Background admission still needs the constructor index for source queries and
therefore retains its current path. Unit tails retain their Function identity
and ordered-effect handling. Fusion does not add a global admission stall to
increase coverage. No runtime fact graph, copied binding layout or per-producer
consumer lists are introduced.

Across Runs, Shared Entry and iterative Bake continue using original instance
slots and actual witnesses. This implementation consumes existing compiler
proofs; it does not infer new cross-Run visibility from an observed execution.
The actual catalog evidence is compared unchanged.

## Cost accounting

The removed work is covered source row collection and a second registration
scope. New costs include preflight, a worker prefix mutex, its staging slots,
leased fact-slot headers and larger combined completion events. The source
still accepts each Cell and eventually regains the shared directories. A fused
region is not automatically one saved pool call: some previously ran ordinary
source registration, and completion arrival changes old registration grouping.
Compare actual dispatch counts, not the number of newly eligible regions.

`results.json` retains both workloads' complete work counts. Cumulative capacity
is neither peak memory nor an allocation trace. Event overlap and migrated row
counts do not establish CPU utilization, reduced waiting or a speedup.

| Observation | sum-bits control / candidate | Raytrace control / candidate |
| --- | ---: | ---: |
| Second registration pool calls | 7 / 4 | 2,939 / 2,683 |
| Fused producer regions | 0 / 2 | 0 / 303 |
| Cells completed through fusion | 0 / 73 | 0 / 12,204 |
| Actual constructor rows registered through fusion | 0 / 91 | 0 / 17,011 |
| All constructor rows registered by workers | 134 / 152 | 181,166 / 188,028 |
| Local constructor rows registered on source | 1,340 / 1,322 | 166,489 / 159,627 |
| RHS dispatch regions | 247 / 247 | 9,061 / 9,064 |
| Ordinary key lookups | 13,028 / 13,028 | 3,830,075 / 3,830,073 |
| Source execution frames | 5,176 / 5,176 | 1,020,600 / 1,020,600 |
| Completion-event capacity, cumulative bytes | 1,021,760 / 1,024,328 | 188,972,880 / 186,984,168 |
| Added producer-prefix staging, cumulative bytes | 0 / 36,208 | 0 / 6,053,184 |
| Constructor registration capacity, cumulative bytes | 14,024 / 8,160 | 15,132,872 / 14,519,288 |
| Fact-slot return capacity, cumulative bytes | 7,904 / 10,400 | 10,190,128 / 10,801,752 |
| Common/Unit registration capacity, cumulative bytes | 19,640 / 11,584 | 13,091,080 / 12,757,128 |
| Registration-event capacity, cumulative bytes | 15,808 / 8,320 | 6,198,400 / 5,655,104 |

The combined result is 600 bytes versus the original `Completed`'s 496 bytes.
Its prefix staging and completed-event slots are still separate allocations.
Raytrace removes 256 second pool calls in this execution, not 303. Net worker
registration rises by 6,862 rows, not 17,011, because some fused rows previously
used the old worker registration. Unit worker installs fall 80,283 to 79,403 as
completion arrival changes old region eligibility; their ordinary source
fallback remains exact. Arrival timing also changes two absence probes; there
is no material decrease in query work, and source frame counts are unchanged.
This is a completed ownership takeover with additional storage cost, not a
passed throughput gate. Consolidating the two completion stores remains live
work before claiming that fusion has removed all handoff overhead.

## The reported historical regression

The quoted 22.547 to 24.771 ms / 5.166 to 5.389 s comparison is the `79e6fe0f`
[write-completion campaign](../cell-write-completion/README.md). Its four-worker
performance gate failed. Main-thread Raytrace condition-wait sampling rose
17.64% to 20.33%; workers still mostly sampled as waiting. These overlapping
stack counts do not isolate synchronization cost. sum-bits had zero coverage
in that new scalar path, and Raytrace's three paired samples had substantial
variation. The data do not establish a precise cause for either median delta.
Subsequent campaigns must not be compared across dates to claim recovery.

## Validation and reproduction

182 runtime tests and 89 relevant integration tests pass, with forced hash/Bloom
collisions and all-feature, sparse-only and legacy checks. New tests cover
duplicate roots, actual reused results, partial-prefix failure before/after an
offered certificate, retirement, later union/repair, rejection without leasing,
and a single-worker handshake that blocks the second completion until the
source accepts the first. Native-backed boundary fixtures exercise both closed
48-Cell and background 192-Cell cases through same-Run reads, deletion,
recreation and late union. README compile/run/one-repeat bench are smoke checks.

Final exports, all 1,428 / 16,883 ordered Run summaries, logical effects,
reverse occupancy and Bake evidence exactly match the control. The unchanged
native sum-bits choice validator returns `pass` and its CPU export hash matches
the fresh candidate. Raytrace remains
differential validation; final summaries do not replace boundary tests.

An initial parallel test link exhausted local disk. The failed log is retained;
the successful retry uses `CARGO_BUILD_JOBS=1`. Only generated executables from
completed checks were removed. Build failures are not accepted test results.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-fused-registration/run.py out/cell-independent-registration FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-fused-registration/check.py out/cell-independent-registration FRESH_OUTPUT RESULTS.json
```

Use the successful validation/README commands in `results.json`, with fresh
output paths. The frozen manifest records binary hashes, input paths and flags.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```
