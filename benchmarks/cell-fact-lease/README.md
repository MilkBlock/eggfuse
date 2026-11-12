# Keep the Cell in place during constructor registration

This is the actual standalone Cell CPU, not native egglog performance. Work
checks compare with `0ef4a130` using the same frozen programs, catalog, release
features and arguments. This is implementation five after timing checkpoint
`2166a3fb`; the separate periodic timing gate determines speed acceptance.

## Opportunity and ownership

The preceding catalog execution returned 32,433 Cell frames through registration
events. It paid for removing/reinserting each entire Cell in the dense arena,
which can relocate another physical record, although the worker only writes
that Cell's fact slots. It also retained an `Installed` record for every Cell
and scanned the complete successful prefix after all owners returned.

The compiled terminal instruction region supplies the existing proof: no
intervening union, mutable read, fallible suffix or other Function allocation;
sealed Eq inputs; fresh constructor slots; exact old/new Unit merge; and no
pending dirty/union work. Parents in a leased region precede children. The
registration owner does not write input values, parent links, execution position
or lifecycle state. Those parts of the same Cell can remain where they are.

Only the original fact-slot container now moves to the worker and back in its
completion buffer. The Cell stays in its existing arena position. The worker
continues to install the actual facts and original shared indexes; the source
attaches those slots once before completing the Cell. The source then consumes
publication certificates directly from that same event buffer. There is no
second all-Cell certificate vector.

The source/error protocol permits an additional deletion: it completes each
offered Cell before offering the next, and stops offering on error while still
draining every owner. Therefore only the last offered Cell and the untouched
suffix need rollback certificates. An error after taking a certificate but
before committing that Cell must retain the last certificate. Success no longer
scans every completed Cell after the registration scope.

These are representations of the same existing Cell, not another fact graph,
binding copy, marker relation or per-producer subscription list. Existing actual
returned witnesses and compiled Shared Entry projections remain authoritative
across Runs. The catalog already repeatedly exercises this terminal shape;
this change deletes its handoff/retirement work without adding a new catalog or
claiming extra query elimination. The Run visibility fence, source order and
exclusive shared-index owners remain live obligations.

## Work evidence and remaining cost

| Raytrace observation | `0ef4a130` | Candidate |
| --- | ---: | ---: |
| Event payload per Cell | 200 bytes | 104 bytes |
| Cells passing through constructor registration | 32,433 | 32,815 |
| Success retirement checks | 32,433 (old full scan) | 988 |
| Constructor metadata capacity, cumulative bytes | 6,435,208 | 4,019,120 |
| Cell/fact event capacity, cumulative bytes | 6,486,600 | 3,412,760 |
| All six recorded registration/handoff capacity counters | 28,937,456 | 23,741,032 |
| Cells completed with registration work still pending | 16,535 | 16,441 |
| Unit subscriptions handled by the existing worker owner | 64,866 | 65,630 |

The payload is 48% smaller, and cumulative recorded capacity falls by 5,196,424
bytes (18.0%). The old retirement-check count follows its exact per-frame loop;
the candidate counts actual checks, one last-offered check per successful
constructor region. The pointer/layout test verifies that leasing and returning
facts never changes the Cell arena order or physical positions.

Capacity counters are not peak memory or total allocator traffic. Original fact
payloads and slot values are not deep-copied. Event arrival changes region sizes,
coverage and some counter totals; these are not counts of logical effects
removed. The existing early-completion counter includes queued followups and
does not establish CPU utilization or time saved. Reserved invalid Function
slots and all real reverse incidences remain costs.

Sum-bits has no eligible registration region; this takeover does not directly
improve its four-worker path. Work-count reductions alone do not establish an
end-to-end speedup for either workload.

## Validation

170 runtime tests and 87 relevant integration tests pass, along with forced
hash/Bloom collision checks, 20 repeated blocking handshakes, all-feature,
sparse-only and legacy builds. Constructor tests now exercise the production
ownership path rather than a separate borrowed-owner helper. They check errors
both before and after taking an uncommitted publication certificate, actual
row-allocation identity, retained changes/subscriptions, and a subsequent
union/repair against ordinary source execution. The handshake still blocks
constructor directories and subscriptions until an earlier Cell prefix commits.

Exact final exports, 1,428 / 16,883 ordered Run summaries, logical effects,
queries, reverse-edge work/occupancy, Sieve counts and iterative Bake evidence
agree with the control. Omitted root-read counts can change with eligible region
coverage; all other maintenance counters must agree. This is work accounting,
not a change to the semantic contract. Integration fixtures cover Run-boundary
visibility, deletion/recreation, late union and actual returned aliases; final
exports and Run summaries alone do not prove every intermediate state.

The unchanged native sum-bits choice validator passes and is linked to the
fresh CPU export hash. Raytrace remains exact differential validation. README
compile/run/one-repeat bench commands pass as smoke checks, not timing evidence.
See [results.json](results.json) for commands, counts and hashes.

Release features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

Use fresh output paths when reproducing the commands recorded in
`out/cell-fact-lease/manifest.json`:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-fact-lease/semantic-acceptance.json
python3 benchmarks/cell-fact-lease/check.py out/cell-local-registration out/cell-fact-lease benchmarks/cell-fact-lease/results.json
cargo cell-compile --case sum-bits --output out/cell-fact-lease/readme-program
cargo cell-run --program out/cell-fact-lease/readme-program/program.json --output out/cell-fact-lease/readme-run
cargo cell-bench --program out/cell-fact-lease/readme-program/program.json --repeat 1
```

## Periodic timing checkpoint

Runtime `916ebf7c` is frozen before this campaign. Four revisions are remeasured
with the same programs, catalogs, normal release features and flags, using both
one and four workers. Each lane has one warmup followed by five sum-bits or three
Raytrace samples in a recorded shuffled order. All 80 executions have exact
final hashes, ordered Run-summary hashes and logical effects; no sample is
discarded or replaced. The separate stack profiles are not timing samples.

| Inference median | Historical `8335929d`, 1 / 4 workers | Pre-regression `c27cbcf1`, 1 / 4 | Last checkpoint `7b13f259`, 1 / 4 | Current `916ebf7c`, 1 / 4 |
| --- | ---: | ---: | ---: | ---: |
| sum-bits, ms | 18.409 / 22.222 | 19.709 / 22.356 | 18.988 / 23.451 | 19.304 / 22.207 |
| Raytrace, s | 5.705 / 5.153 | 5.745 / 5.092 | 5.884 / 4.933 | 5.870 / 4.888 |

Current four-worker Raytrace is 4.01% faster than the pre-regression control in
this campaign; all three iteration-paired comparisons improve (paired median
-4.06%). Against the last five-change checkpoint its median improves only
0.93%, while the paired median is **0.35% slower** and two of three pairs are
slower. Thus this campaign does not establish a stable additional speedup from
these five registration changes, or isolate the effect of the final fact lease.

sum-bits has a 0.67% lower four-worker median than the pre-regression control,
but its paired median is **2.66% slower**, with four of five pairs slower. Its
current samples span 21.144–26.523 ms, versus 21.632–23.166 ms for that control.
The apparent median advantage is below the variation. Against the historical
configuration the medians differ by only 0.07%, while the paired median is 4.70%
slower. **A stable two-workload speed improvement remains unproven.** Do not
compare prior campaigns' quoted 24.77 ms / 5.389 s with this campaign's current
numbers to claim a larger recovery.

Current Raytrace scales only 1.201x from one to four workers, versus 1.128x for
the pre-regression control and 1.193x at the last checkpoint. Current one-worker
Raytrace is 2.19% slower than the pre-regression control. sum-bits remains slower
with four workers than with one. Four-worker Raytrace process CPU/wall averages
about 1.25 cores versus control 1.21; this includes load/export and is not an
inference-only utilization measurement.

| Four-worker Raytrace phase median, seconds | Pre-regression | Last checkpoint | Current |
| --- | ---: | ---: | ---: |
| Search | 1.818 | 1.704 | 1.709 |
| Query-index update / publication | 1.039 | 0.994 | 0.996 |
| RHS | 1.741 | 1.753 | 1.706 |
| Repair | 0.471 | 0.461 | 0.471 |

The RHS phase median decreases about 2.6% against the last checkpoint; other
major phase medians do not improve. Phase medians need not sum to median total
time and do not isolate synchronization overhead. This is limited evidence,
not proof that event counts, buffer savings or more workers caused each change.

## Remaining waits and next scope

Separate three-second, two-millisecond-interval samples cover inference with
progress logging disabled. The candidate has 901 main-thread inference samples;
the control has 900. Inclusive stack counts overlap and the partial windows are
not CPU-utilization measurements.

| Sampled main-thread residence | Pre-regression | Current |
| --- | ---: | ---: |
| Condition waits | 18.4% | 22.2% |
| Entry batch scheduling, including callbacks | 10.9% | 8.1% |
| Query finishing, including waits | 14.0% | 14.1% |
| Finished-table publication, including waits | 21.7% | 21.3% |
| Repair | 12.7% | 12.3% |

Worker condition-wait fractions remain 75.8%–82.2%, predominantly pool-idle
contexts, versus control 78.8%–82.7%. Candidate source waits include 84 query,
92 publication, 12 scalar-write and 12 other samples. The remaining waits and
source work still leave most workers idle. More early-completion events have
not demonstrated that this broad problem is solved.

`start_cell_execution`, ordinary constructor insertion, subscription maintenance
and collision repair remain visible on the source. The frozen work execution
creates 820,439 logical facts, while this registration path installs 65,630 of
them (about 8%). It covers only a minority of the remaining source graph writes.
Making its fragment buffers smaller again is not a sufficient strategy for the
1.706-second RHS phase.

The next structural scope should move the first actual constructor-result
decision and its continuation into a Cell owner where the compiled snapshot/
effect proof permits it. A worker should keep using that Cell's actual slots,
validate the winning result, invalidate duplicate private work, and continue
without returning each constructor to `resolve_cell_boundary`. This requires
explicit ownership of the relevant exact constructor index and proof of when
its Eq inputs remain valid. Shared effects, source error order, actual aliases
and original Run visibility remain mandatory. This checkpoint does not claim
that takeover is implemented. Small Runs also still require dispatch costs to
be matched to real compiled work.

The campaign's 66 separate process snapshots found no compiler process. Other
desktop activity and shorter unsampled work remain possible. Raw samples,
execution order, comparisons, profile data and hashes are retained in
[timing-results.json](timing-results.json). Profile state exports were losslessly
gzipped only after their exact hashes were verified, to limit local disk usage.

```sh
python3 benchmarks/cell-fact-lease/campaign.py ARTIFACT_ROOT
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-fact-lease/ray-manifest.json out/cell-fact-lease/timing-ray/samples.json out/cell-fact-lease/profile-control4 --lane control4 --duration 3 --interval-ms 2 --start-delay 0.5
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/cell-fact-lease/ray-manifest.json out/cell-fact-lease/timing-ray/samples.json out/cell-fact-lease/profile-candidate4 --lane candidate4 --duration 3 --interval-ms 2 --start-delay 0.5
python3 benchmarks/cell-fact-lease/timing_check.py out/cell-fact-lease benchmarks/cell-fact-lease/timing-results.json
```
