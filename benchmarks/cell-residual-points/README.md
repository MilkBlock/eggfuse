# Complete residual point Cells in the existing worker Run

The current catalog (`f0fb1443`, runtime `483e379b`) spends roughly 1.71 s in
search and 1.85 s in RHS in the last short Raytrace checkpoint. These are wall
intervals including parallel work and waits. A separate three-second sample
of that frozen runtime finds source Entry admission, RHS boundaries and
publication alongside idle workers. Sampling is diagnostic, not a speed test.

The residual worker compiler previously required an expansion step even when
the entire point-query Cell was already executable by the same interpreter.
The source therefore retained Entry filtering and query execution for those
uncovered point Cells. The existing template proves the operand projection,
point reads, scalar checks and result/input slots. No new marker, fact graph,
subscription list or binding copy is needed.

The residual plan now makes its optional expansion explicit. Eligible point
Cells use the existing Entry range, sealed read snapshot, exact admission,
delta ownership and source-ordered winner selection. Successful Instances
continue through existing pure RHS/constructor preparation. This replaces
their source query execution instead of adding another speculative attempt.
Point Cells retain their instruction-order exact reads without Free Join
domain admission or its probe-only columns, as the source point kernel did.
Special routes, absorption, incomplete read coverage and visibility boundaries
retain the established path. This is query takeover, not concurrent arbitrary
RHS mutation or a new cross-Run visibility rule. A scheduled switch can reuse
the resulting Instance and existing Entry proof; new reads of mutable tables
still require the next Run's snapshot.

Charge the added compiled point plans, prepared columns, answer storage,
winner merging and query preparation as well as source work removed. Two
counters identify actual point entries/answers within the residual executor;
they increase its task bookkeeping by 16 bytes. CPU utilization and total
speedup cannot be inferred from transferred Entry counts.

## Reproduce

Run relevant integration and collision checks listed in `results.json`, plus
the README Cargo compile/run/bench smoke commands. Then execute the workloads
once for semantics/work, independently of timing:

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-residual-points/run.py out/cell-unit-projection FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-residual-points/check.py out/cell-unit-projection FRESH_OUTPUT RESULTS.json
```

The fresh CPU sum export must match the saved proof input. Raytrace retains
exact final-state, ordered Run-summary and effect comparison; this does not
extend the native sum contract to Raytrace. Tests also check every small-case
Run state, ordered bindings, late inputs, deletion/recreation and union under
one, two and four workers.

After committing the tested runtime, run the guarded quick checkpoint:

```sh
python3 benchmarks/raytrace-parallel/quick.py out/cell-unit-projection FRESH_OUTPUT FRESH_TIMING_OUTPUT benchmarks/cell-residual-points/timing-results.json
```

All control sum/Ray runs finish before any candidate runs. No sampler, test,
compiler or other workload runs alongside timing. Preserve interrupted
attempts; do not pool fragments or interleave lanes.

## Coverage result: insufficient for retention

Both workloads compile 177 additional point entries, but each executes only
five of them and returns two answers. Raytrace's source Free Join probes stay
at 2,427,588. Residual plan capacity grows from 273,312 to 291,432 bytes,
and per-task counters from 136 to 152 bytes. Moving five queries is not evidence
that the sampled source hotspot has been taken over. This trial will be
withdrawn after the short sequential checkpoint; preserve the evidence rather
than retaining an unused default mechanism.

All 1,428 sum-bits and 16,883 Raytrace Run summaries, final states, logical
effects, merge counts, iterative evidence and live reverse occupancy match
the frozen control. The unchanged native sum validator passes against the
fresh CPU export. 94 integration tests, 21 collision reruns, all-features
compilation and README smoke pass. The ENOSPC validation-launch failure is
recorded separately; no failing test was accepted.
