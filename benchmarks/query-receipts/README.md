# Query receipts across completed stages

This experiment extends `425681a1` on the **standalone Cell CPU runtime**.
The complete applications retain ordinary ordered repair, with the preceding
experiment's optional constructor result-port propagation enabled in the final
runtime comparison. Native egglog supplies focused semantic checks and the
finite Cell registry; it is not the runtime timed here.

## A row location is weaker than a result equality

The preceding Raytrace catalog reused 34,063 RHS constructor reads but still
performed 1,574,999 stage port refreshes. This change allows the next scheduled
stage to consume a row receipt acquired by a completed earlier stage. A receipt
is a table/key location, not a promise that its result or visibility never changes.

The opt-in `stage-congruence` objective emits `eggfuse-result-switch/v3`. Each
query certificate identifies the consumer atom, the source rule and query/effect
position, and its distance in the bounded stage history. Compiler reconstruction
checks the entire certificate on load. Existing v1/v2 certificates retain their
serialization and semantics.

Constructor functionality can prove equality of results at source boundaries.
For a query proof, the compiler walks the validated stage entry in execution
order: only the pivot and previously completed ports may supply equalities.
Full-LHS constraints remain available for the subsequent RHS proof. A later
condition cannot justify skipping an earlier port.

Mutable function receipts prove only where to read. They never equate a current
query result with an earlier function result. For example, if a source observed
`value(x)=a` and constructed `F(a)`, a later `value(x)=b` may use the same row
location; it cannot use the old `F(a)` receipt to satisfy `F(b)`. Each attempted
reuse reads the current row and checks liveness, visibility, table and the full
canonical key. Result constraints, primitive guards and watermark checks remain.
Retired or missing receipts fall back to the original query path.

Only demanded receipts are captured, including query witnesses of mutable
functions and the actual write receipt of a single-write producer. The same
bounded history serves query and RHS programs. No speculative query publishes
an effect, no logical match counts as a committed mutation, and the original
Run publication barrier remains in force.

## Resume actual execution evidence

`iterate --resume-catalog PATH` validates the old catalog against the current
recipe and leaf set before creating output. It preserves the existing joins,
producer roots and limits unless limits are explicitly overridden. The new
objective can therefore learn from the previous 208 / 316 units rather than
discarding them. Fresh producer-profile selection and catalog resume are
mutually exclusive.

Candidate ranking now includes additional query receipts as well as RHS
receipts. This remains a cost estimate. A query receipt can replace an existing
local cache read, so receipt hits are not counts of global key lookups avoided.
Actual application counters and runtime measurements determine the outcome.

Learning still uses bounded replay and recompilation from the same initial
graph. There is no in-process catalog replacement or parallel/GPU executor.
Every completed checkpoint compares its final graph, semantic schedule and
ordered RHS inputs against the original catalog.

## Learned coverage and actual work

Both final runs stop with no further profitable candidate under the current
score, below the 512-unit limit. Neither run prunes candidate counters.
[results.json](results.json) records every completed checkpoint, including the
validated prefix of the interrupted Raytrace learning segment. The resumed
segment finishes at 412 units; sum-bits finishes at 236.

| Case | Prior / final units | Query receipt hits | Function-row hits | Stale fallbacks | Port refreshes, prior / final |
|---|---:|---:|---:|---:|---:|
| sum-bits | 208 / 236 | 162 | 110 | 5 | 3,869 / 3,838 |
| Raytrace | 316 / 412 | 15,402 | 10,694 | 143 | 1,574,999 / 1,572,989 |

There are no missing-history fallbacks in either final execution. These counts
measure attempted matching work and successful checked receipt reads, not
committed mutations. Query hits may occur before a later guard rejects a
candidate. The complete application audits preserve graph exports, ordered
RHS inputs, effective writes, resumes and the normalized Spine traces.
[audit.json](audit.json) retains the hashes and counters.

The distinction between receipt hits and global lookup savings matters here.
Raytrace bypasses 13,402 existing context-cache reads and 2,010 port refreshes.
Its total key lookup calls fall from 4,420,726 to 4,418,715, including one extra
reused RHS constructor. Successful RHS constructor reuse rises only from
34,063 to 34,064; complete RHSs stay at 18,016. Sum-bits saves 31 total key
lookups and keeps its 293 reused constructors and 165 complete RHSs.
Dependency repairs remain 1,496 / 479,589 with result ports enabled.

Receipts also cost work: source-root initializations rise from 351 to 409 for
sum-bits and from 33,123 to 57,604 for Raytrace. Raytrace performs 2,143 extra
row decodes under the existing instrumentation. The current score cannot
distinguish an avoided global lookup from an avoided context-cache read, or
fully price source captures that are never consumed. Extra cells and proofs
alone therefore do not establish an application speedup.

One actual learned self-continuation is `Add-All-Gets`: it advances `pos` while
keeping `something` unchanged. The consumer can read `tuple-length(something)`
through the producer query's receipt, then evaluates its current `pos < length`
guard. It never freezes the earlier length value. The recorded Raytrace unit
317 is applied on 4,060 visits; the sum-bits counterpart is applied on 51.
Those per-unit visits are separate from aggregate receipt-hit counts. The
collected example includes the source and consumer recipes and certificate.

## Runtime measurement

The same new executable compares the prior catalog (`control`) and the learned
query catalog (`queries`). `parent` uses the archived `425681a1` executable and
prior catalog. Every lane enables `--repair-ports`, uses fresh processes and
preserves the final graph and semantic schedule. After one warmup per lane,
sum-bits has 31 interleaved samples and Raytrace has seven. No compiler, audit
or training job overlaps the timing run. Background load on the shared
workstation is uncontrolled and the sample ranges overlap.

| Case / lane | Median inference | Median peak RSS through inference |
|---|---:|---:|
| sum-bits / parent | 20.289 ms | 167.469 MiB |
| sum-bits / control | 20.325 ms | 167.500 MiB |
| sum-bits / queries | 20.500 ms | 167.859 MiB |
| Raytrace / parent | 7.725 s | 1,868.250 MiB |
| Raytrace / control | 7.773 s | 1,876.328 MiB |
| Raytrace / queries | 7.834 s | 1,869.656 MiB |

There is **no demonstrated application speedup**. Query/control median inference
increases 0.86% / 0.79%; the median paired changes are +1.80% / +0.43%.
Default control/parent medians differ by +0.18% / +0.61%. Raytrace's control
range is 7.377–7.937 s and its query range is 7.408–7.911 s.
[timings-sum.json](timings-sum.json) and [timings-raytrace.json](timings-raytrace.json)
retain every sample, binary/program hashes, flags and invariant counters.

Raytrace's median Spine capture time rises from 0.078 to 0.089 s and publication
from 0.404 to 0.422 s; its query time remains about 0.452 / 0.453 s. The new
proofs and mutable-row receipts are usable capabilities, but this catalog's
global lookup savings are too small to establish a throughput gain. The result
stays opt-in and does not replace the frozen default catalog. Further admission
work needs actual lookup-tier and capture-cost evidence, not just static proof
counts. Repair and Run publication have not been removed.

## Compiler closure

A diagnostic sample found candidate proof construction repeatedly scanning all
constructor facts for congruence closure. The compiler now tracks a conservative
footprint of symbol roots used in keys, including the last fact not yet indexed.
Only an equality that changes such a root requires a closure scan. A newly
queried constructor's duplicate key is already reconciled by the exact fact
index. Hiding a table clears the lookup index but retains the conservative key
footprint, because later queued unions can still affect surviving facts.

The scan itself retains its former semantics and refreshes the canonical key
footprint. Mutable rows never participate in constructor congruence closure.
A randomized differential test compares the conditional algorithm with the
former full scan through appended facts, pending unions and hides. Reconstructing
the saved 348-unit Raytrace certificate produces the identical program hash;
graph, schedule, ordered RHS and completion counters also match. Learning then
continues from the last completed 364-unit checkpoint with this implementation.
The interrupted process's completed checkpoints remain evidence; it is not
reported as a completed learning run.
[diagnostics.json](diagnostics.json) records the matching certificate and
execution stamps, the sampled candidate-selection hotspot and the explicit
handover to the new compiler. Its resumed segment takes 437.392 s including
eight replay/checkpoint rounds; this is diagnostic elapsed time with short
builds overlapping part of the run, not an isolated compiler speed ratio.

## Validation and reproduction

178 all-feature workspace tests pass, with four existing tests ignored. Six
focused query-receipt tests cover source congruence, ordered query prefixes,
retired receipts, changing mutable results, single-write producers, certificate
corruption and resume validation. The focused suite also runs on the non-sparse
backend. The complete application audit checks byte-identical graph exports,
ordered RHS/write/resume digests, semantic schedules and Spine shape traces
(excluding only the differing program hash).

Use the preceding completed-producer artifacts and fresh output directories:

```sh
cargo build --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --bin eggfuse-cell-compiler
target/release/eggfuse-cell-compiler iterate --program PREVIOUS_PROGRAM --resume-catalog PREVIOUS_CATALOG --output out/query-learning --objective stage-congruence --rounds 12
cargo test --release --locked --workspace --all-features
cargo test --release --locked -p eggfuse-cell-compiler --features iterative-bake --test query_receipts
```

The previous limits are retained: 512 units, depth 8, 16 new units per round,
and 2,048 / 131,072 candidate counters for sum-bits / Raytrace. `collect.py`
accepts completed checkpoint segments and rejects divergent semantic stamps.
Its final segment must contain a completed program. Applied example-unit visits
are reported separately from actual receipt hits.

Build the runtime audit executable with
`sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes` and use
the preceding experiment's `audit.py`. Its manifest may map each case to
`{lane: {program: PATH, args: ["--repair-ports"]}}`. Build timing executables
with `sparse-cells,view-ports,storage-metrics` only. The preceding `measure.py`
interleaves fresh processes; `result-port-repair/collect.py` preserves all timing
samples and stores identical counters once per lane after checking them.
Keep compiler and training jobs out of timing runs.
