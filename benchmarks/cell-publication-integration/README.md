# Publication integration on the current runtime

This experiment measures the actual standalone Cell CPU with four workers,
not native egglog. Control `03065edb` includes the current shared witness
dispatch and sparse completed-source membership. Both lanes retain those
changes. The candidate merges the entire `codex/table-entry-admission` branch:
independent index/Entry completion (`e97ebde4`) and small-batch admission
(`0dfdfb2a`). It does not include the rejected Entry refresh experiment.

The timing build uses `cell-absorption,view-ports,parallel-publication` plus
defaults. The completed-owner sparse-membership representation remains gated
by `storage-metrics`; its code is present in both source trees but that opt-in
storage takeover is not active in these timing lanes. This comparison must not
be presented as a performance test of that representation.

## Opportunity and obligations

The last catalog execution showed 666 single-table batches that could not use
the original pool path. Index readers unnecessarily waited for independent
Entry updates. Existing compiler table partitions and Sieve dependencies prove
that those readers require completed indexes, not completed Entry owners.
The integration releases them at that boundary, while retaining original
storage and allowing the charged duplicate Graph reads in the Entry task.

A new Bake catalog cannot prove mutable values or retirement unchanged across
Runs. No scheduled block switch may skip those reads without such evidence.
The current witness-sharing and membership changes reduce other maintenance;
they do not subsume the index/Entry dependency split. The same immutable Graph
borrow, source Run visibility, exact owner readiness, delta ownership and error
ordering remain authoritative. Late Entry failure invalidates speculative
conditions before returning. No additional fact graph or consumer subscriptions
are introduced. Small-batch admission uses existing change-map lengths as an
upper bound and counts both its new visits and removed owner evaluations.

The earlier measurements and identical-binary diagnostic are preserved in
`../cell-table-entry-events`. They demonstrated variation and do not establish
this integration's speed against the current branch. This trial freezes new
control and candidate binaries; no old timing sample is reused.

## Reproduction

Use a clean control checkout and a candidate checkout at the same commit with
the experiment branch merged using `--no-commit`. The working diff must contain
only the three publication runtime files and their existing integration test.
Submit `prepare.py CONTROL CANDIDATE CONFIG ACCEPTED OUTPUT TARGET` through
`eggfuse-job run --kind compute -- python3.14 ...`. It builds and freezes the
control before the candidate build can replace the shared target binary, checks
fresh states, source Run summaries and logical effects, runs the relevant test
suite and README commands, and freezes the candidate. It verifies that both
checkout sources remain unchanged throughout preparation.

The release freeze now uses `tools/freeze_runtime.py`: within the same queue
lease, clean only the `eggfuse-cell-runtime` release package, build the requested
features and copy the binary immediately. Dependency and debug caches remain.
Record the clean/build commands, features and binary digest. The preparation
also requires different control/candidate digests and actual nonzero admission
and split-Entry coverage. A successful semantic comparison alone cannot prove
that the intended candidate executable ran.

The unchanged native sum acceptance validator must pass and its CPU-export hash
must match the fresh sum state. Raytrace uses exact state/Run/effect comparison;
this does not extend the native semantic contract to Raytrace.

After preparation passes, commit the merge in the isolated checkout. Run
`../cell-table-entry-events/check.py CONTROL_EXPORT CANDIDATE_EXPORT CHECKS
RESULT.json` through the compute queue. Submit the entire `quick.py` comparison
as one timing job, from the clean candidate checkout. Fix counts at 15 sum and
7 Raytrace samples per lane, one warmup each. Complete all control workloads
before starting any candidate workload. Do not interleave lanes or managed
builds, and do not repeat a completed trial merely to obtain favorable medians.

The final report must distinguish removed dependency edges, added reads and
dispatch/storage costs from whole-inference timing. Worker row counts and
overlapping task residence times do not establish CPU utilization.

## Rejected preparation

Job 72 exposed stale shared-target output before any performance measurement.
The candidate's final release command reported completion in 0.04 seconds and
the frozen binary was byte-identical to the freshly built control
(`81aec993e830745acc7abd3c76dcfc144f5fc2189b4ef15644ea636ef4a04052`).
Its report lacked both split-Entry and admission counters and executed the old
783 pooled publication calls. The source merge and feature-specific integration
tests were correct, but the shared target launcher was wrong for that source.

Those initial exports remain under `out/cell-publication-integration`; its
preparation record is explicitly marked invalid. They are not timing inputs.
The corrected preparation uses a new `fresh` directory and rebuilds both
runtime packages. Existing older trials are not reclassified merely from this
failure: their distinct binary hashes and observed candidate paths remain
separate evidence.

## Verified integration and work

Corrected preparation job 76 rebuilt the control to the same `81aec993…` hash
and the candidate to `cafb189c…`. Both fresh exports preserve exact terminal
states, all 1,428 sum and 16,883 Raytrace Run summaries, and logical effects.
The unchanged native sum validator passes and its CPU hash matches the new
export. The 211 runtime tests, 111 integration tests, legacy/all-feature checks
and three README commands pass. Candidate `50e3822a` is the checked merge on
`codex/table-entry-integration`; it is not adopted into the active runtime.

`results.json` records accounting job 79. Entry updates, predicates, retirements
and Sieve logical work agree. Raytrace still processes 2,155,707 publication
rows, but pooled calls rise from 783 to 1,449 and inline publication rows fall
from 771,570 to zero. Its 1,896 split tasks add 1,764,849 current-row reads;
total parallel row reads rise from 1,996,513 to 3,761,362. Accumulated task
capacity rises from 4,365,680 to 4,618,240 bytes. The 1,277 ready-flag observations
sample Entry completion before the index callback, not measured CPU overlap.

Admission removes 1,311 sum and 12,339 Raytrace table-owner evaluations, while
adding 1,311 and 15,158 change-map length visits. Sum executes no split task or
parallel publication batch. These are work/representation changes, not a speed
acceptance result.

## Fixed sequential timing: not adopted

Job 81 completed 15 sum and 7 Raytrace samples per lane, plus one warmup each,
using only the corrected frozen executables. All control workloads finished
before any candidate workload began. All 104 boundary guards were clear; every
measured state, Run summary and logical effect passed its reference checks.
`timing.json` retains every sample, independent phase medians and the full
observation archive checksum.

| Inference median | Control `03065edb` | Integration `50e3822a` | Change |
|---|---:|---:|---:|
| sum-bits | 26.026 ms | 27.763 ms | +6.67% |
| Raytrace | 5.501 s | 5.396 s | -1.91% |

The two-workload speed gate fails. No slow sample is discarded, and there is
no repeat-until-green trial. Sum ranges from 25.265–27.801 ms in the control
and 25.430–62.319 ms in the candidate. That variation does not establish an OS,
thermal, scheduler or algorithmic cause. Likewise, the small Raytrace median
improvement is not a stable speedup claim in light of the earlier A/A evidence.
The dependency split remains a validated experiment rather than the new active
runtime baseline. The shared-target build fix is retained independently.

The next diagnosis needs inference-scoped CPU time and actual wait accounting,
so elapsed stalls can be distinguished from extra computation. Existing whole-
process user/system counters include setup and export; they cannot answer that
question for the inference interval. Worker row counts and phase wall medians
are not substitutes for this missing evidence.
