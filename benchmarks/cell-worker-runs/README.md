# Continuous worker execution with per-Cell completion events

This compares actual standalone Cell CPU work against frozen runtime
`c0dd0034`. It is not native egglog performance or a timing campaign. Programs,
catalogs, features and arguments are unchanged. This is implementation **two**
after timing checkpoint `83ac944b`; a stable two-workload speedup is still unproven.

## Opportunity from the preceding execution

Worker-root admission increased Raytrace coverage, but the preceding execution
carried 210,835 local jobs through 9,062 dispatch regions and accumulated
387,020,504 bytes of completion-event capacity. Every completed Cell carried
all 71 execution counters (568 bytes), even though source adoption only needed
its logical constructor births/reuses. Returning the full counters also caused
a full aggregation at each source adoption. The existing rule-local ready queue
already groups the same template's instances, yet dispatched them individually.

The original typed Cell plans identify the admitted constructor region and its
optional Unit tail. Their instruction counts can bound a short worker loop
without a new graph, copied bindings or per-producer consumer lists. Existing
terminal-region, parent-snapshot and duplicate-result proofs remain authoritative.

Across Runs, the existing instance slots and actual returned witnesses continue
to supply Shared Entry and the Bake catalog. Grouping does not establish an
additional cross-Run proof and discharges no extra visibility boundary. The
iterative Bake evidence is checked unchanged; this change amortizes execution
of existing compiled regions instead of inventing another catalog.

## Removed work and live obligations

Workers now consume contiguous runs of admitted instances from the original
owned input vector. The grain heuristic targets at least two runs per worker,
caps a run at eight Cells and uses the widest compiled constructor/Unit region
to target at most 32 instructions per run. A single large Cell is not split by
this heuristic. These bounds are scheduling choices, not measured time weights.
Rayon may steal runs. No chunk vector or second binding array is created.

Each Cell publishes its actual result immediately, before the next Cell and
before statistics reduction. Source order and early prefix adoption remain in
force. A worker accumulates diagnostics across its run; only two logical counts
(16 bytes) accompany each Cell. Actual graph mutation counters are updated only
on adoption. Diagnostic work includes private results later discarded after a
source error; those results do not become logical mutations.

Both foreground event delivery and background admission use this execution.
Ordinary query/followup event callers retain their original direct dispatch,
with a zero-sized accumulator. The new foreground grouped producer has a scope
guard for initializer, worker and reducer panics so an abandoned source slot
cannot leave the receiver asleep forever.

The change deletes per-Cell diagnostic packets and moves their accumulation to
worker runs. It removes per-Cell foreground task spawning in covered runs. The
source still uses the existing `Counts` return for logical commit accounting;
this does not claim to delete every per-Cell counter construction or addition.
It retains one
completion notification per Cell, exact duplicate checks, result aliases,
ordered effects, retirement, parent-epoch joins and original Run visibility.
It does not make all graph registration concurrent or eliminate all waits.

New costs include one bounded grain scan over admitted jobs, worker reductions,
one final foreground metadata handoff and a 576-byte accumulator per worker
run (the former counter fields plus the run counter). `execution_groups` counts
nonempty accumulator runs, including inline execution; it is not an exact count
of Rayon's internal tasks. Reduction temporaries and thread stacks are not
included in event heap capacity. The counter size and group count expose their
cost separately; no per-Cell statistics heap allocation is introduced.

## Work comparison

| Observation | sum-bits control / candidate | Raytrace control / candidate |
| --- | ---: | ---: |
| Admitted local Cell jobs | 984 / 984 | 210,835 / 210,834 |
| Candidate worker/inline execution runs | — / 910 | — / 61,644 |
| Completed logical local births | 1,474 / 1,474 | 347,655 / 347,655 |
| Constructor operations on workers, including reuse | 1,335 / 1,335 | 324,431 / 324,429 |
| Ordinary key lookups | 13,028 / 13,028 | 3,830,073 / 3,830,075 |
| Source execution frames | 5,176 / 5,176 | 1,020,600 / 1,020,600 |
| Dispatch regions | 247 / 247 | 9,062 / 9,063 |
| Queue capacity, cumulative bytes | 2,252,384 / 2,252,384 | 247,559,152 / 247,567,920 |
| Completion-event capacity, cumulative bytes | 1,882,208 / 1,026,720 | 387,020,504 / 187,999,200 |
| Peer-sharing capacity, cumulative bytes | 86,192 / 86,192 | 16,544,024 / 16,483,768 |
| Source adoption while other jobs remain | 48 / 24 | 26,050 / 30,403 |

The candidate `Completed` value is 496 bytes. Its per-Cell counters shrink by
552 bytes; all actual result owners remain. Event capacity falls 45.45% / 51.42%.
Capacity is neither peak memory nor a full allocation trace. Small-job grouping
is limited on sum-bits. Source adoption and dispatch-region counts do not
materially decrease. Scheduling changes the timing of absence probes and ready
prefix registration: Raytrace has one fewer root admission, two more ordinary
lookups and slightly different registration coverage. Final graph effects are
exact. Neither the early-completion counts nor these byte savings establish
CPU utilization, reduced waiting time or a speedup.

The earlier quoted 22.547 → 24.771 ms and 5.166 → 5.389 s belong to the
`79e6fe0f` campaign in [cell-write-completion](../cell-write-completion/README.md).
That four-worker performance gate failed. Its Raytrace main-thread condition
wait samples rose from 17.64% to 20.33%; inclusive samples and noisy three-pair
timings do not isolate a cause. This implementation removes a concrete current
handoff cost; it does not retroactively explain all that regression or claim
to have recovered it without a new timing checkpoint.

## Validation and reproduction

176 runtime and 88 relevant integration tests pass. New handshake coverage makes
a second Cell in the same single-worker run wait until the source consumes the
first Cell; an end-of-group barrier would fail. Other tests cover empty/inline/
single-worker execution, source errors with discarded private suffixes, and
initializer/worker/reducer/consumer panics. Forced hash/Bloom collisions,
all-feature, sparse-only and legacy checks pass. README compile/run/one-repeat
bench commands pass as smoke checks, not performance samples.

Frozen final exports, all 1,428 / 16,883 ordered Run summaries, logical effects,
reverse-index occupancy and iterative Bake evidence match the control. Boundary
fixtures additionally cover deletion, recreation, late union and visibility;
final exports alone do not prove those. Native sum-bits choice diagnosis is
`pass`, linked to the candidate's CPU export hash. Raytrace remains differential
validation, not an extension of the native proof.

Features: `cell-absorption,view-ports,parallel-publication`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

```sh
CARGO_INCREMENTAL=0 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-worker-runs/run.py out/cell-root-births FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-worker-runs/check.py out/cell-root-births FRESH_OUTPUT RESULTS.json
```

The checker requires successful `validation.json` and `readme-checks.json` records
using the commands in [results.json](results.json), with fresh output paths.
It accepts losslessly gzipped predecessor exports. Input paths, flags and the
frozen binary hash are recorded in `out/cell-worker-runs/manifest.json`.
