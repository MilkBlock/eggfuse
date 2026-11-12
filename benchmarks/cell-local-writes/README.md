# Rejected: prepare local constructors across scalar writes

**Rejected experiment; the runtime remains at the `877ff5d2` implementation.**
Scope: standalone Cell CPU runtime, not native egglog performance. The experiment
is reproduced by applying [rejected.patch](rejected.patch) to `877ff5d2`; it is
not an enabled optimization or a completed independent scheduler.

## Hypothesis and implementation tested

The preceding actual execution built 139,448 Raytrace constructor rows in
76,904 synchronous worker pieces. A scalar function write whose checked merge
contains only primitives cannot create Eq identities or change equivalence.
It might therefore be possible to build a longer local constructor region in
one worker invocation, then register rows and execute the original writes in
source order.

The patch derives this permission from the typed table and reconstructed merge
instructions. Constructor/equality outputs and any merge table call retain their
boundary. Source constructors keep their actual row allocations and actual reuse
witnesses. The original instruction sequence orders registration and Set effects;
it is not replaced by a generated effect log. A failing Set leaves prior rows
committed and discards future prepared rows. Existing handoff positions still
stop preparation. Pending rows, commit steps and code references are charged.

## Evidence and rejection

[results.json](results.json) and [check.py](check.py) record/verify the frozen
candidate and control hashes, exact final states and all 1,428 / 16,883 source
Run summaries. Graph effects, query totals, repair and publication work match.
The unchanged native sum-bits validator reports `pass`.

| Result | sum-bits | Raytrace |
|---|---:|---:|
| Scalar writes crossed by the new path | **0** | **0** |
| Global lookups, unchanged | 14,054 | 4,037,109 |
| Worker pieces, unchanged | 299 | 76,904 |
| Local rows, unchanged | 525 | 139,448 |
| New commit-loop steps | 634 | 153,295 |
| New shared-code references | 598 | 153,808 |
| Net saved equally weighted work | -1,202 | -307,017 |

The slightly lower plan-check count comes from consuming static gaps, not from
crossing scalar writes. Zero workload coverage with added work does not justify
retaining this takeover. There is **no speedup claim** and no new timing campaign.
The implementation was removed from the working runtime after the comparison.

Verification passed 133 runtime tests, 105 compiler/integration tests with forced
hash/Sieve collisions, and all-features/no-default-features checks. The additional
fixtures verify a source-position scalar merge failure and a scalar-output merge
that secretly constructs a node. The latter must retain its original boundary.
An initial fixture used a function without merge syntax, which this frontend
rejects; it was corrected to a legal fallible merge before the final checks.

Raw evidence, frozen executables and saved native exports are under ignored
`out/cell-local-writes`. The unchanged control's README compile/run/bench checks
remain the runtime validation; documentation-only rejection does not require a
new performance run. Reproduction uses the same programs, flags and native
exports as [the control](../cell-local-births/README.md), with the added patch:

```sh
git apply benchmarks/cell-local-writes/rejected.patch
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
# Freeze this feature executable as ROOT/runtime before other Cargo builds.
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-local-writes/check.py ROOT PRIOR RESULTS.json
```

## Required next structural work

The unresolved constraint is public-frame storage and independent scheduling.
`Cell.values` is both the unique mutable execution array and the backing source
for retained parent projections. `Graph::fact_column` reconstructs those reads
through the producer's recipe and `slot`; moving out the array would invalidate
them even when a decoded row happens to exist. A Set's proposed recipe value
also need not equal the final merged function value, so substituting an arbitrary
current function row is not a valid general solution.

The next ownership change must keep established projections readable while an
owned worker continuation modifies only its unfinished portion. It must avoid
rebuilding bindings or a second maintained fact graph, preserve generation and
retirement semantics, and stop borrowing the mutable Graph for the lifetime of
the worker task. Parents/equality validation is a separate read dependency that
also needs a stable contract. Only then can several ready instances advance
without the current per-piece `pool.install` wait.

Acceptance remains actual concurrent progress of multiple Cells, workers released
by parked boundaries, source-equivalent commit/publication and measured useful
throughput. More worker-operation counts, a new job wrapper, or a narrow unit
fixture alone do not meet that requirement.
