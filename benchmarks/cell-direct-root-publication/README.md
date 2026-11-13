# Direct publication of completed scalar roots

Changed-root direct publication is opt-in (`--direct-changed-roots`). The
ordinary and same-binary trials did not establish stable improvement on both
workloads; the default retains the original changed-root publication decision.

This experiment concerns the actual standalone Cell CPU runtime, not native
egglog or a scheduling simulator. The committed control is `58057ef1`; its
engine is identical to the previously frozen `e21acfa1` candidate.

The last ordinary Raytrace execution recorded 1,171,692 inline function receipt
writes and reads, 1,914,263 captured completion contexts, and 130,690 absorbed
root completions. Its publication scope took 258 ms and scalar source completion
78 ms in that reference run. These are attribution clues, not timing acceptance
or pure synchronization measurements.

The same compiled single-write plan already names the only exported operation.
For a permanent table with an owned Entry and no required root history, a
completed write supplies its actual Function witness whether it created a row,
changed one, or reused its value. The old `!changed` gate unnecessarily retained
Completion and inline-receipt delivery for the first two cases. Both the serial
and worker write paths now use the existing final Entry slot directly.

This removes pending completion and receipt capture/read within that proof. It
retains the existing staged-root forwarding record (24 bytes on this machine),
Entry insertion, source-order comparison and repair visibility check. Every
staged attempt is charged even if a later writer replaces it; a larger direct
path may perform more Entry writes than reverse-order deferred publication.

No effect moves across a Run. Roots with Bake state or training responsibilities,
live histories, multi-output Cells, query-sourced exports, deletable tables,
visibility changes, receipt auditing and scoped completion keep their ordinary
paths. The actual witness can forward after union. Entry readers remain behind
the existing completed-table boundary. Serial writer-input retirement still runs
when the direct path returns early.

A future catalog can use actual surviving publications to choose larger shared
Cells. This change uses current typed facts and performs no new catalog search,
per-producer consumer registration or runtime binding copy.

## Validation

The single-output test covers direct root publication and retains a separate
live-history variant for inline receipt forwarding. The worker regression runs
old/min/max merges with two and four workers, duplicate writes, new rows, changed
rows, Eq-key forwarding and late reads. It compares independent schedule prefixes
with the old publication path so every Run boundary is checked with auditing
disabled (auditing otherwise disables the optimized path). When built with the
compiler's `iterative-bake` feature, ordered RHS/write/resume digests are also
compared. Existing deletion/recreation and matched-handoff tests remain required.

Check out the implementation commit `41c48c4d` in a clean worktree, then freeze
with `prepare.py ACCEPTED TARGET OUTPUT`, through a compute lease.
`ACCEPTED` is the borrowed-instance artifact root, including its validation and
frozen candidate. The helper checks that the reused control's engine matches the
current committed base, freezes the distinct candidate, and validates unchanged
sum-bits/Raytrace states, source Run summaries and effects. The reviewed sum-bits
semantic contract uses the existing saved exports and checks their CPU hash
against this fresh result. Raytrace is differential, not a new native proof.

Timing uses a single exclusive lease: five sum-bits and three Raytrace samples
per lane, one warmup each, all control samples before all candidate samples.
No repeat count is adapted after seeing a result. Frozen executables and reports
stay on the internal disk; the Cargo cache may live on the external SSD.

Queue job 163 passed 47 Cell execution, 15 Entry publication, 5 matched-handoff
and 2 parallel-publication tests (69 total), including ordered transfer audits.
Broader feature checks and performance acceptance are recorded after completion.

## Measured outcome

Implementation `41c48c4d` passed job 166: 212 runtime unit tests, the 15 Entry
publication tests with storage metrics, and all-feature/no-default-feature
compilation. Job 169 froze the ordinary candidate; exact states, source Run
summaries, effect counts, continuation counts and the reviewed native sum-bits
contract passed. These checks cover this implementation, not later merged code.

| Raytrace work | Control | Candidate |
| --- | ---: | ---: |
| Captured completion contexts | 1,914,263 | 1,054,574 |
| Inline receipt writes and reads (each) | 1,171,692 | 312,003 |
| Roots staged directly into Entry | 130,690 | 990,379 |
| Final Entry slot writes | 1,879,484 | 1,902,758 |
| Staged-root capacity bytes | 49,152 | 196,608 |

The 859,689 eliminated pending completions are not counted again as a separate
Cell takeover. Existing forwarding records replace them; 23,274 additional Entry
slot writes and the extra record capacity remain charged. sum-bits eliminates
231 pending completions but adds four Entry writes and one forwarding event.

Job 171 ran the predeclared non-interleaved trial. All 48 guards were clear and
all samples retained the accepted state, source Runs and logical effects.

| Inference median | Control | Candidate | Change |
| --- | ---: | ---: | ---: |
| sum-bits (5 samples) | 24.791 ms | 27.488 ms | +10.88% |
| Raytrace (3 samples) | 5.253 s | 5.114 s | -2.66% |

The two-workload improvement gate failed. No extra samples were added and no
outliers removed. Candidate sum-bits samples were 32.453, 27.488, 26.063, 28.272
and 25.200 ms. Its phase medians increased in search (+1.265 ms), RHS (+0.715 ms)
and query update (+0.355 ms), as well as smaller phases. Phase medians need not
sum to the total median. These observations do not establish that extra Entry
writes, synchronization, executable layout or background drift caused the
regression. Lower pending-work counters are insufficient for speed acceptance.

Concurrent integration nevertheless merged this implementation with the
independent dual-source Bake work in `9aeb7e3b`. That is repository integration,
not this experiment passing its speed gate. The timing binary is still exactly
`41c48c4d`; neither the other Bake changes nor the merged tree are covered by this
comparison. The frozen control remains available. Do not reset others' work or
reinterpret these timings as a merged-branch result.

`results.json` retains all timing samples, binary hashes, raw-record hashes and
charged work. Removing further coordinator work remains an open objective;
this change does not establish worker saturation.

## Same-binary changed-root control

`--defer-changed-roots` restores the old deferred path only for writes that
changed a row. Unchanged root publications, worker writes, query workers and
Entry ownership remain enabled. It can be configured only before the first Run;
the report exposes `stage_spine.direct_changed_roots`. This diagnostic adds no
per-Cell clocks, trace records or second instance representation.

The standalone runtime's existing `inference-cpu` feature captures process and
coordinator CPU only at inference boundaries. The off/on trial uses one frozen
binary from the current merged kernel, so executable layout and the integrated
Bake code are identical. It tests the direct-publication decision in that kernel;
it cannot retroactively prove that executable layout or background activity
caused the earlier two-binary regression. The branch adds a small configuration
check; this is a diagnostic, not a zero-overhead subtraction or speed acceptance.

The selected path must reproduce the previous frozen experiment's exact pending
completion/receipt counts in both modes before timing. The usual state, source
Run, logical effect and reviewed sum-bits proofs remain required. Regression
coverage includes serial and four-worker execution at each schedule prefix,
unchanged writes remaining direct, key forwarding and rejection of configuration
after execution begins.

Predeclared trial at diagnostic commit `9680e1be`: 15 sum-bits and 3 Raytrace samples per mode, one warmup each,
all control groups before all candidate groups. `ACCEPTED` is the previous
`out/cell-direct-root-publication`; `DIAG` must be new.

```sh
eggfuse-job run --kind compute -- python3.14 benchmarks/cell-direct-root-publication/same_binary.py ACCEPTED TARGET DIAG
eggfuse-job run --kind timing -- python3.14 benchmarks/raytrace-parallel/quick.py --sum-repeats 15 --ray-repeats 3 --same-runtime-control-flag=--defer-changed-roots DIAG/control DIAG/candidate DIAG/timing DIAG/timing.json
python3.14 benchmarks/cell-inference-cpu/run.py summarize DIAG DIAG/timing DIAG/cpu-results.json
```

Use process CPU/wall as mean consumed cores, not a percentage of workers filled.
Coordinator off-CPU includes scheduling and blocking. Existing event/scope times
can overlap and are not pure synchronization costs.

## Diagnostic outcome and default

The diagnostic implementation is `9680e1be`. Job 173 passed 16 Entry publication
and 5 matched-handoff tests, plus all-feature/no-default-feature checks. Job 174
froze one CPU-instrumented binary and verified that both configurations reproduce
the corresponding old/new pending-work counts, exact states, source Runs,
logical effects and the reviewed sum-bits semantic contract.

Job 175 was interrupted by the guard after candidate Raytrace sample 1: an
unmanaged `capture_rhs_results` from another worktree was using 99.2% CPU. Its
partial trial is retained and excluded from conclusions. Only after that
process exited did job 176 rerun the entire predeclared trial in a fresh
artifact directory, with no sample stitching or repeat-count changes. All 88
guards in job 176 were clear; every measured sample matched its frozen reference.

| Same-binary inference median | Changed roots deferred | Changed roots direct |
| --- | ---: | ---: |
| sum-bits, 15 samples | 29.054 ms | 28.027 ms |
| Raytrace, 3 samples | 5.266 s | 5.564 s |
| Raytrace process CPU | 9.438 s | 9.923 s |
| Raytrace coordinator CPU | 3.958 s | 4.155 s |
| Raytrace mean process cores | 1.792 | 1.784 |

The direct mode did not reproduce the earlier sum-bits regression, but Raytrace
wall time increased 5.65%, process CPU 5.13% and coordinator CPU 4.97%. This is
not a pure-wait increase. The worker-write source-completion span grew from
85.947 to 108.715 ms; search, RHS and query-update medians also increased. These
scope times overlap other measurements and do not isolate a cause for all
297 ms of median inference increase. Neither executable layout nor group-order
drift is established as the explanation for the two trials' opposing results.

Mean process cores is not worker occupancy. The current evidence does not prove
stable speedup or saturation, and this diagnostic does not supersede the failed
ordinary two-workload gate. All samples, including the 44.439 ms sum-bits sample,
are retained in `control-results.json` and the referenced raw artifacts.

Changed-root direct publication is therefore now **opt-in** via
`--direct-changed-roots` / `use_direct_changed_roots()`. The default restores
changed writes' pending completion, while unchanged roots remain direct. This
restores the old publication decision; it is not a measurement of the new
binary's ordinary speed. `--defer-changed-roots` overrides the experimental flag
for same-binary diagnostics. The current `same_binary.py` explicitly enables
the experiment for both lanes before adding the control override; reproducing
the original diagnostic binary requires checking out `9680e1be`.

Job 181 validated the opt-in default: 47 Cell execution, 16 Entry publication,
5 matched-handoff and 2 parallel-publication tests (70 total), 212 runtime unit
tests, and all-feature/no-default-feature compilation. The regression explicitly
checks the default is deferred, enables direct publication for its existing
coverage, and checks that neither configuration can change after the first Run.
