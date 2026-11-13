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

Freeze with `prepare.py ACCEPTED TARGET OUTPUT`, through a compute lease.
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
