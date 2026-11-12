# Peer result slots and repeatable Cell evaluation

Scope: standalone Cell CPU runtime, not native egglog. Immediate control:
`00d64fa5`, the bounded ready scheduler. The observed opportunity is 1,277 Raytrace
queue drains for unresolved source roots, despite only 2,736 queued jobs. Those
waits are not inherent dependencies on graph publication: the remaining pure
constructor calculations can resolve actual outputs within a batch.

## Takeover

A source constructor creates a genuinely fresh root. The compiler derives which
input slots prove that every remaining constructor key stays in that root's cone.
An instance that reuses a parked root can join its producer's batch. Admission
checks the actual returned root, source operation, current root equivalence,
shared rule/region, complete suffix coverage and materialization boundary.
Matching the producer Cell ID alone is insufficient. The same typed operation
plan remains authoritative; no per-producer subscriber lists or second bindings
are installed. Unknown roots and uncovered effects retain the source path.
The producer address selects its parked owner by binary search in the existing
source-ordered queue; the actual root proof still decides admission. Dynamic
duplicates within a single fresh cone also use these slots. Mutually helping
work is bounded to 256 constructor operations and at most 64 parked owners.

Each queued operation has a shared result slot. A worker reads an already
published result or evaluates the pure operation itself. Evaluation is outside
the slot's publication lock, so two workers may compute the same operation. They
publish the same exact result, determined by the earliest source constructor with
the same operator and canonical inputs, rather than the fastest worker. Candidates
are the shared template's operator positions, restricted to captured prefixes
and earlier queued operations. Recursion only follows earlier source positions.

Downstream keys read these actual results before construction. A losing duplicate
allocation stays private and is dropped; no provisional duplicate identity is
installed in the public graph. Aliases store the actual foreign value/witness.
Workers communicate by shared slots, without coordinator messages for each edge.
The owner still records its logical operation exactly once. Row allocations are
shared temporarily with the result slots and adopted by source registration.

A per-instance Bloom filter covers the computed suffix keys. A negative skips
that suffix only after an acquire read proves **all** its slots complete. An
unfinished suffix is not represented completely and cannot be excluded by a
negative. Captured source-prefix rows remain separately checked. Hits always
require exact key comparison; forced hash collisions must preserve results.
Known prefix and first-boundary keys are indexed once per batch by hash and source
position. This directory stores only locators, and avoids visiting unrelated
instances. Unknown later keys use the shared template's operator positions.
Both candidate ranges merge in source order. The collision diagnostic disables
the hash rejection and collapses Bloom signatures, retaining exact comparisons.

Shared effects, union submission, repair and Entry publication retain their
source ordering and Run boundaries. This is not concurrent public-graph mutation
or a completed full-core scheduler. Unsupported histories, callbacks, deletion,
failure and incomplete structural coverage keep the existing source executor.

## Costs and acceptance

New costs are reported: result-slot storage, physical evaluations, competing
publication losses, slot reads/hits, Bloom operations, row/frame handles, proof
checks, directory construction/search, temporary vectors and key spills. Logical births/reuses, committed rows
and physical evaluations are separate. Duplicate work and cache-hit subsets are
not counted twice in the work ledger. Independent batches retain the cheaper
existing executor and do not allocate peer result slots.

Use the frozen sum-bits/Raytrace programs and flags from
[the immediate control](../cell-ready-scheduler/README.md). Reuse saved native
sum-bits exports with only the candidate CPU state replaced, then run the unchanged
`choice_diagnosis.py` acceptance entrypoint. Compare every ordered Run summary,
logical effects and final state with the control. Integration checks compare
actual Run snapshots and effective-write source ordinals, including foreign
reuse, differing scalar keys, union/repair and subsequent Entry publication.
This work measurement is not a throughput benchmark.

| Work, control → candidate | sum-bits | Raytrace |
| --- | ---: | ---: |
| Dependency-triggered queue drains | 4 → 0 | 1,277 → 0 |
| Queued jobs | 86 → 87 | 2,736 → 14,880 |
| Ready batches | 27 → 24 | 1,362 → 342 |
| All local worker invocations | 240 → 237 | 75,530 → 74,510 |
| Global key queries | 14,054 → 14,050 | 4,037,109 → 4,024,864 |
| Net saved equal-weight work (negative = added work) | −564 | −881,877 |

The final diagnostic Raytrace run has 13,768 shared result slots, 13,858 physical
evaluations (90 competing duplicates), 2,762 Bloom checks and 264,903 directory
comparisons. Shared temporary storage adds 6,133,024 cumulative bytes, not peak
live memory. An initial draft had 12,487 duplicate evaluations, 795,712 Bloom
checks and 938,026 source-proof probes; direct owner lookup and the known-key
directory remove most of that overhead. Remaining source-proof probes are
213,035. Scheduling and allocation costs remain and are charged. These counters
alone do not establish a speedup, and 74,510 local pool invocations still remain.

139 normal runtime unit tests, 8 targeted Cell collision tests and 104
compiler/integration collision tests pass. Running the
*entire* runtime suite with zero-bit query fingerprints also exposed an unchanged
query-snapshot test that expects a changed fingerprint notification; that test
assumption does not hold with all fingerprints equal. No production behavior or
acceptance rule was changed to accommodate that diagnostic. Native sum-bits
acceptance is `pass`, and both complete workload exports and ordered Run summaries
match the frozen control.

The shared Cargo target was removed externally during one test compilation;
remaining checks rebuild in `/private/tmp/eggfuse-3063-peer-target`. The measured
runtime is the independently frozen executable identified in `results.json`.
Other sessions committed research and the independent `0e7970d6` Bake duplicate
fold while this validation was running. The frozen comparison isolates this
feature against `00d64fa5`; it does not attribute those later changes to peer slots.

## Five-commit timing checkpoint

README compile/run/repeat-one bench and minimal/all-feature checks pass. After
compilation finished, fresh processes were interleaved across four lanes, with
one warmup per lane, five sum-bits samples and three Raytrace samples. All final
states and ordered Run signatures match. Full samples and hashes are retained in
[timing.json](timing.json). The serial lane uses one query worker and the same
Cell execution option, so it has no worker pool. The archived lane uses the
previous `cell-run-column-preparation` binary and its original parallel flags.

| Inference median | sum-bits | Raytrace |
| --- | ---: | ---: |
| Frozen ready-queue control, 4 workers | 24.51 ms | 6.221 s |
| Peer slots, 4 workers | 24.87 ms | 6.289 s |
| Current serial execution | 16.93 ms | 5.427 s |
| Archived parallel configuration | 19.03 ms | 5.686 s |

There is **no demonstrated speedup**: the peer path's point estimates are 1.45%
and 1.09% slower than the immediate control; three Raytrace samples vary
substantially. Four-worker Raytrace is 15.9% slower than the current serial lane.
The eliminated dependency drains are a real takeover, but cover too little of
total execution to offset the additional scheduling/storage work. Keep this as
an explicitly enabled Cell execution experiment, not evidence of full utilization
or a faster default. Future admission must be based on end-to-end benefit, not a
target of zero dependency flushes. The next useful scope is larger owned execution
segments and the still-serial matching/commit work, rather than further tuning
these now-rare duplicate evaluations.

The first timing invocation used an invalid serial CLI combination and stopped
before that lane ran. Its aborted warmup is retained under ignored
`timing-invalid-serial-args`; no measured samples from a completed run were removed.

```sh
python3 benchmarks/cell-peer-results/measure.py CURRENT CONTROL ARCHIVED SUM_PROGRAM RAY_PROGRAM FRESH_OUTPUT benchmarks/cell-peer-results/timing.json
```

Commands follow the control's README with output root `out/cell-peer-results` and
control root `out/cell-ready-scheduler`. The reproducible ledger checker is
[check.py](check.py); its text result is [results.json](results.json).
