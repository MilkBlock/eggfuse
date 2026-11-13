# Worker completion of absorbed Cell writes

The previous point-query experiment was withdrawn in `98f1efc2`: it transferred
only five Entries. The restored control is runtime `483e379b`, frozen in
`out/cell-unit-projection`. Its actual Raytrace execution gives a larger target:
rule 153 has 461,370 residual Entries and 748,054 row visits. The residual worker
compiler excludes its absorption capability, keeping Entry admission, query
enumeration and min-write completion on the source.

The typed Cell already proves that its only effect copies an attribute into a
permanent min function. For a matching constructor older than the current
watermark, a current output no greater than the input proves that the binding,
RHS and publication are unnecessary. The same proof consumes actual results
across Runs; it does not make current-Run writes visible to matching queries.

This change carries the existing capability into the residual worker read
plan. It reuses Entry ranges, the sealed graph, ordinary query instructions and
source-ordered winner selection. The source neighborhood and worker paths share
one exact row proof. An absorbed row generates no successful Instance, receipt
or publication record. The worker returns only aggregate proof accounting;
the source reserves the same unused identity positions at the original rule
boundary. Logical matches include absorbed Cells, but committed mutations do
not. The runtime collects late worker credit before pruning empty rule groups.

The permanent-min compiler proof, exact input equality, current output row,
constructor freshness, delta owner, source order, visibility and lifecycle
obligations remain live. Missing outputs and fresh constructors retain ordinary
matching. Deletable outputs and ordered merges receive no absorption proof.
All additional attribute tables are included in read-view admission.

Mixed Entry ranges resolve coverage after the same domain/delta admission as
source Free Join. Previously they counted Sieve acceptance before domain
rejection, conservatively disabling direct origins even when all residual
Entries were rejected. Keep both counts: pre-domain admission still charges
worker inputs, while supported Entries decide coverage. Scalar-guard rejection
or absorption after that boundary never proves complete coverage. The initial
trial preserved exact states/effects but lost 3 sum / 58 Raytrace direct origins;
its artifacts remain under `out/cell-worker-absorption/pre-coverage-fix`.

The new path removes source Free Join/Seed work and source neighborhood cache
maintenance in its coverage. It retains per-row absorption rather than moving
the old whole-domain bound cache to workers. That can require more output
probes and row reads, even though the same bindings/RHSs are omitted. Charge
these probes, query/merge allocations, compiled plans and aggregate-counter
storage; do not use thread occupancy or transferred Entry counts as a speed
claim. `worker` counters include inline execution of the same path;
`thread_absorbed` and `inline_absorbed` split actual execution ownership.

## Reproduce

This is the actual standalone Cell CPU, not native egglog. Run the relevant
tests and README Cargo compile/run/bench smoke commands recorded in
`results.json`. The small-case tests compare every Run state, actual binding
order, logical matches, executed bindings, effects and reserved identities
under one, two and four workers; forced hash collisions retain exact checks.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-worker-absorption/run.py out/cell-unit-projection FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-worker-absorption/check.py out/cell-unit-projection FRESH_OUTPUT RESULTS.json
```

The native sum validator must pass and match the fresh CPU export. Raytrace
keeps exact final-state, source Run-summary, effect, catalog/application/trace
evidence and reverse-occupancy comparison. Direct-origin work counters may
increase after proven domain rejection, and must never decrease; this; this does not extend the native sum contract.

After committing the tested runtime, execute the quick checkpoint:

```sh
python3 benchmarks/raytrace-parallel/quick.py out/cell-unit-projection FRESH_OUTPUT FRESH_TIMING_OUTPUT benchmarks/cell-worker-absorption/timing-results.json
```

Finish all control workloads before any candidate workload. No compilation,
test or sampling runs alongside timing. Retain interrupted trials and every
sample; do not interleave lanes or combine favorable fragments.

## Work checkpoint

`results.json` records the frozen input/binary hashes, commands and both failed
collector attempts. The final comparison passes for all 1,428 sum / 16,883
Raytrace source Run summaries, exact states/effects and the unchanged native
sum contract. The related integration checks cover source reservations,
winners, continuation origins, missing/fresh results, union, retirement and
ordered effects. Sieve-only and combined Sieve/key collisions both pass.

| Raytrace work | Restored control | Candidate |
|---|---:|---:|
| Source Free Join probes | 2,427,588 | 1,307,153 |
| Absorbed logical matches | 704,026 | 704,026 |
| Absorptions on actual worker threads | 0 | 702,826 |
| Absorption output hash probes | 790,659 | 954,783 |
| Residual worker answers | 1,303,337 | 1,554,547 |
| Answer capacity bytes, accumulated | 302,383,200 | 363,177,024 |
| Merge capacity bytes, accumulated | 339,625,088 | 404,538,816 |
| Direct origins | 480,297 | 481,357 |

The candidate additionally charges 622,848 accumulated bytes of absorption
counter-vector capacity. It removes source neighborhood bound/rejection-cache
work, including 100,816 direct rejection-row reads; those are not hash probes.
The transferred raw Entries include candidates rejected by worker admission,
so their count cannot be compared directly with the control's post-Free-Join
461,370 Entries. The 704,026 omitted bindings/effects were already omitted by
the control: this change moves their proof, not a second saving of those RHSs.
These allocation totals are accumulated capacities, not peak live memory.

Sum moves only 72 absorptions (38 threaded, 34 inline), and 151 source probes.
Its small coverage is a material limit. Timing is recorded separately after
committing the validated runtime.
