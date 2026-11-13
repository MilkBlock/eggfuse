# Direct publication of completed scalar roots

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
