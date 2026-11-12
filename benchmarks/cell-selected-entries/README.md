# Workers borrow selected Cell Entry ranges

This is the actual standalone Cell CPU executor, not native egglog performance.
The control is `f90011bc`, with unchanged frozen programs, catalogs, flags and
four workers. This is implementation three since the last full speed campaign.
It verifies work and semantics, without claiming the prior regression is fixed.

## Opportunity and live obligations

The preceding Raytrace execution routed 1,131,289 uncovered Entries from rules
that also had live Spine continuations. Source admission had already checked
Sieve and Cursor ownership, but then cloned each shared row reference, made a
`CellQuery`, looked up its physical Cell, linked a Cell task and later made
another borrowed query header. The worker finally executed the residual query.
The resulting 1,396,673 total row task headers and 1,354,443 physical-Cell probes
were a concrete remaining source cost, despite parallel query execution.

The last catalog's existing compiled Cell query, Entry membership and independent
consumer watermark already prove the read layout and source positions. A sealed
Run cannot publish, retire or change these rows while query workers borrow them.
No new learned history, runtime fact graph or producer subscription is needed.
The resulting Instance continues through the existing local RHS preparation,
winner selection and source effects. Across Runs, the existing Entry projection
and visibility boundary remain authoritative.

Mixed-rule admission still needs the exact accepted residual count before
choosing complete or partial cross-stage dispatch. Sending raw mixed ranges to
workers and assuming complete coverage would be incorrect. This change retains
that source filter and ownership decision. Moving it requires a later coverage
completion dependency and dispatch of eligible successful Cursors after that
dependency resolves; this checkpoint does not claim that takeover.

## Connected execution

An accepted residual Entry now contributes only its existing witness address to
a reusable Run arena. A range descriptor supplies the scheduler node, compiled
query, watermark, source ordinal and arena slice. Only contiguous source
intervals can extend the same descriptor. The old row reference clone, CellQuery,
physical-Cell lookup/link and borrowed query header are removed for this path.
The compiled index layout activates once for each participating pivot.

Workers read the original Entry rows. The earlier whole-membership range path
uses this same borrowed row view, eliminating its graph row reconstruction.
These are still exact point/expansion queries, with the original delta ownership,
filter decisions, guards, actual witnesses and binding slots. Accepted selected
rows do not repeat their source Sieve check. Whole ranges perform their original
filter on the worker. Missing or unexpectedly invisible sealed rows fail.

Small range fragments share one worker frame and completion event up to the
existing grain. A fragment remains intact when it crosses that target, as in
the existing Cell grouping. A completed answer span names its compiled query;
successful instances do not acquire another per-answer code wrapper. Each rule
is released only when all tasks containing its queries finish. The source
restores the compiled residual insertion position and original ordinal before
the existing exact winner selection. Errors retain their earliest source key.
The Run read fence, mutable effects, Cursor ownership and publication remain.

## Work and added costs

| Frozen Raytrace observation | Control | Candidate |
| --- | ---: | ---: |
| Per-row CellQuery / borrowed query headers | 1,396,673 | 265,384 |
| Physical-Cell grouping probes | 1,354,443 | 235,089 |
| Physical-Cell task records | 908,325 | 59,910 |
| Residual queued row owners | 1,337,128 | 205,839 |
| Query task chunks / frame borrows | 94,016 | 78,130 |
| Answer buffer allocation/growth events | 217,261 | 196,365 |
| Query completion event capacity, cumulative bytes | 230,346,512 | 202,589,000 |
| Borrowed query-header capacity, cumulative bytes | 67,040,304 | 12,738,432 |
| Range-fragment capacity, cumulative bytes | 3,183,488 | 7,726,176 |
| Residual answer capacity, cumulative bytes | 299,362,728 | 303,684,864 |
| Global query lookups | 4,027,756 | 4,027,756 |

The 1,131,289 selected addresses use 23,078 descriptors. The reusable address
arena grows 12 times, adding 131,072 bytes of payload capacity. Its reported
657,776,832 cumulative capacity bytes repeatedly count that same retained buffer
across Runs; they are not allocated anew. Range descriptors report 19,190,304
cumulative bytes. These descriptors include the old whole-range path as well
as the new selections; the old version did not expose this counter separately.
No capacity number is an allocation trace or peak live process memory.

There are 74,368 range fragments, coalesced into 48,073 worker tasks. Their answer
spans report 3,147,072 cumulative capacity bytes; the inline part is already in
event storage. Only 140,672 bytes of heap spill are an additional payload charge.
Result capacity grows slightly even though buffer growth events decrease. The
layout trades physical-Cell grouping for contiguous Entries running the same
compiled query, with short fragments sharing a task. Cache and elapsed-time
effects remain for the periodic timing gate.

The first implementation created one task per range fragment. It increased
Raytrace tasks to 104,425 and sum-bits tasks to 1,391. Those binary/log/export
artifacts remain under `initial/`; the checker validates them too. Coalescing
and arena reuse are part of the final implementation, not favorable resampling.
Final sum-bits task chunks decrease from 1,063 to 888, with 1,381 row task headers
removed and unchanged 14,012 lookups. Both are work runs, not timing runs.

All query entries, answers, steps, guards, point reads, expansion rows, necessary
Sieve checks and pool invocation counts remain exact. `mixed_runs` now recognizes
selected ranges, so it also counts previously missed mixed rules whose Spine
queries finished on the source. Its increase is diagnostic coverage, not added
queries. Event-wave and overlap counts vary with scheduling.

## Validation and reproduction

163 runtime tests and 86 relevant integration tests pass. A new small-range
fixture checks multiple rules sharing a task without mixing their results,
including later mutable values. Existing mixed-rule tests compare every Run
graph, ordered binding, actual effect digest and selected continuation origin
through unions, deletion and recreation. Nineteen forced hash/Bloom-collision
tests pass, as do all-feature, sparse-only and legacy builds. The README
compile/run/single-repeat bench smoke passes; its timing is not comparative.

Frozen sum-bits / Raytrace final exports and all 1,428 / 16,883 ordered Run
summaries match the control, as do logical effects and all Sieve counters.
Run summaries do not replace the intermediate graph checks in integration
fixtures. The unchanged native sum-bits acceptance is `pass`, linked to the
new CPU export by hash. Raytrace remains an exact differential check without
extending the native proof contract.

Release features: `cell-absorption,view-ports,parallel-publication`. Runtime and
program paths are retained in `out/cell-selected-entries/manifest.json`.

```text
--repair-ports --entry-publications --cell-absorption --query-workers 4
--parallel-residuals --parallel-publication --cell-execution-grain 1
```

Use fresh output directories:

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic out/cell-selected-entries/semantic-acceptance.json
python3 benchmarks/cell-selected-entries/check.py out/cell-condition-borrows out/cell-selected-entries benchmarks/cell-selected-entries/results.json
cargo cell-compile --case sum-bits --output out/cell-selected-entries/readme-program
cargo cell-run --program out/cell-selected-entries/readme-program/program.json --output out/cell-selected-entries/readme-run
cargo cell-bench --program out/cell-selected-entries/readme-program/program.json --repeat 1
```

Source enumeration/filtering for mixed routes, Cursor sealing, shared constructor
adoption, ordinary repair and source Run visibility still constrain execution.
This removes measured query-preparation work; it does not establish saturated
workers or a net speedup.
