# Keep compatible Cell owners through one source Run

This experiment uses the actual standalone Cell CPU, not native egglog. Its
control is runtime `8df9de2a`; branch HEAD `684d289d` only changes experiment
documentation/checking. Programs, catalogs, release flags and worker count stay
unchanged. This is implementation 1 after the failed five-change timing gate;
this iteration collects work and semantics, not another timing campaign.

## Opportunity from execution

The preceding checkpoint increased Raytrace RHS dispatch regions from 3,406 to
9,062 while source execution frames stayed near 1.02 million. Its RHS median
grew from 1.762 to 1.934 seconds. Sum-bits showed the same direction. These
observations identify added overhead, not an isolated timing attribution. The
separate historical 22.547 to 24.771 ms / 5.166 to 5.389 s comparison belongs
to `c27cbcf1` versus `79e6fe0f`; see
[that campaign](../cell-write-completion/README.md). Neither performance gate
passed. More worker coverage and less slot storage did not establish a speedup.

The concrete redundant boundary was rule-local queue ownership. Every
`apply_cell_batch` allocated new owner/pending buffers and drained at rule end,
even when the next matched rule could continue under the same sealed inputs.
The existing Cell instances already carry their rule, compiled operation layout,
values, actual witnesses, generation, Cursor and outstanding execution position.
No additional binding or runtime fact graph is required to preserve them.

## Takeover and remaining obligations

`Executor::run` now owns one bounded queue through its original RHS stage.
Compatible rule groups append their existing instances. A singleton may join an
already open queue. Absorption-only groups reserve their original source IDs
without forcing a drain. Existing terminal waves may continue while later groups
are admitted. Queue capacity and the limit on simultaneous waves are unchanged.

The compiler's existing `batch_rule` and terminal-region proofs remain
authoritative: potentially failing operations, unresolved values, shared effects,
budget limits and conflicting roots retain their original completion checks.
Scalar write ownership and ordinary fallback RHS drain earlier owners before
executing. Errors finish only the already-required source prefix. The original
Run end still completes the queue before repair/publication and later queries.
These changes remove a rule boundary, not a Run visibility boundary.

Different templates may now occupy one dispatch. Shared candidate resolution
uses each producer's own compiled operation/slot layout and compares the table
and actual input values. A plan pointer or equal operation number never proves
result identity. Bloom/hash collisions only add candidate checks. The existing
same-plan restriction on dependent lineage admission remains: region numbers
alone do not establish a relation between different templates.

Cross-Run work still uses the existing completed Cell slots, Entry projection
and Bake evidence. This iteration does not invent a new cross-Run proof or
expand that coverage. It removes a redundant handoff before the already-proved
Run boundary; unknown dependencies remain live.

## Costs and evidence

`rule_group_carries` counts groups entering a nonempty queue, including a flying
wave; it is not a count of saved dispatches. `mixed_rule_batches` counts actual
dispatches containing jobs from multiple rules. Outside-rule, Run-end and error
fences are recorded separately. Mixed-rule detection adds a bounded scan of the
existing owner buffer without allocation. Longer queue lifetime can change
early-completion eligibility, candidate comparisons, frames and registration
grouping. All of those costs must be charged along with dispatches and bytes.

`results.json` records the actual control/candidate work. The checker requires
fewer dispatch regions in both workloads, exact final states, all ordered Run
summaries, logical effects, reverse-index occupancy and iterative Bake evidence.
These checks do not establish an elapsed-time improvement.

| Actual work, control / candidate | sum-bits | Raytrace |
| --- | ---: | ---: |
| RHS dispatch regions | 247 / 135 | 9,062 / 6,599 |
| Local jobs | 984 / 1,101 | 210,835 / 215,870 |
| Source execution frames | 5,176 / 5,195 | 1,020,600 / 1,024,706 |
| Ordinary key lookups | 13,028 / 12,910 | 3,830,073 / 3,825,375 |
| Queue capacity, bytes | 2,252,384 / 2,704,272 | 247,557,680 / 200,679,896 |
| Completion-event capacity, bytes | 1,024,040 / 1,036,576 | 189,394,560 / 192,827,936 |
| Shared result capacity, bytes | 84,632 / 274,144 | 16,450,008 / 18,222,968 |
| Worker constructor registrations | 181 / 299 | 193,676 / 190,550 |

Dispatches decrease 45.3% / 27.2%. There are 253 / 4,587 groups continuing an
open queue and 73 / 1,835 actual mixed-rule dispatches. Outside-rule fences are
37 / 415, Run-end fences 74 / 1,356, with zero source errors in these workloads.
These counts are not additive saved operations; required internal dependency,
effect and capacity boundaries still apply. Capacities are cumulative allocation
capacities, not peak memory.

The cost is visible: there are 19 / 4,106 more source frames, and the root path
handles more jobs. A subsequent merge audit corrected the original attribution
to direct/iterative completion: matched completion and closed handoff counts are
unchanged, and Ripsat direct completion is zero in both frozen workloads.
`defer_constructor_prefix` also disables ordinary constructor reuse while a
queue is pending; this is the concrete next path to investigate. These counters
alone do not prove the cause of every additional frame.
Registration grouping changes as well. Sum-bits queue storage grows despite
fewer dispatches; Raytrace completion and shared-result storage grow while queue
storage falls. This removes a real redundant handoff but does not yet eliminate
source preparation or establish recovery from the measured slowdown. The next
opportunity is to preserve already-proved completed instances through the queue
without constructing another execution frame, while retaining effect order.

## Validation and reproduction

185 runtime tests and 91 integration tests pass, including heterogeneous templates with different
operation positions, duplicate roots, singleton joins, background waves,
same-Run reads, deletion/recreation, an actual scalar-writer ownership change
and errors after an earlier queued rule.
Each source Run and binding audit matches the serial control, at one/four
workers. Existing fixtures cover late union and cross-stage activation. Forced
hash/Bloom collisions, all-feature, sparse-only and legacy checks also run.

README compile/run/one-repeat bench are smoke checks. Native sum-bits acceptance
uses the reviewed choice validator and must match the fresh CPU export hash.
Raytrace remains differential validation, not a native semantic proof. Saved
exports can be losslessly gzipped to bound local disk use; the checker hashes
their decompressed content. Generated test executables are removed only after
their successful check; sources, logs and frozen runtimes are retained.
All 1,428 / 16,883 ordered Run summaries, final exports, logical effects and
iterative Bake evidence exactly match the control; native sum acceptance is
`pass` with the same CPU export hash.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-run-queue/run.py out/cell-completion-slots FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-run-queue/check.py out/cell-completion-slots FRESH_OUTPUT RESULTS.json
```

Use fresh output directories and successful `validation.json` /
`readme-checks.json` records with the exact commands retained in `results.json`.
No phase time from these work runs is a speed comparison. Throughput still has
to pass the next agreed timing checkpoint.
