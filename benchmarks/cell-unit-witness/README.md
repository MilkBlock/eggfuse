# Reuse actual Unit witnesses inside worker Cells

The last installed catalog (`b9b93023`, runtime `149f7ff9`) prepared 149,817
Raytrace Unit rows in query workers. The source consumed 149,532 and discarded
99,988 as duplicate writes. More candidate construction would amplify this cost.
The useful next step is to carry an already existing actual result, instead of
allocating another row and hashing its key again on the source thread.

The compiler already proves the eligible Unit writes, old/new total merges,
input/scalar dependencies, permanent constructor prefixes and storage contract.
Workers use the existing sealed query view and exact functional index to find
the actual row. Their Cell instance retains its table, index and epoch. A miss
keeps the existing private candidate-row path; duplicate misses remain legal.
No new index, runtime fact graph, binding copy or consumer subscription is added.

At the original source effect, the Run union generation, absence of pending
unions, row liveness, table, epoch, canonical representation and Unit value
must still agree. A valid witness skips duplicate allocation and source key
lookup. The original merge accounting, result receipt and publication are
preserved. Rejection executes the ordinary write. Constructor-prefix rejection
also discards its dependent Unit rows and witnesses, counted separately.

Deletion/recreation cannot redirect an old row witness to a newer row. Owned
Unit storage, failed scalar prerequisites and missing constructor results keep
their existing fallback. Source ordering, residual/delta ownership and Run
visibility remain unchanged. Cross-Run Entry projection consumes the same
actual result slots; this change does not bypass its visibility fence or claim
a new cross-Run takeover. Shared registration/publication is still outstanding.

Charge worker exact probes, accepted source lookup skips, rejected witnesses,
physical row allocations, vector/field capacity and temporary key spills
separately. Historical `key_lookup_calls` excludes direct `commit_unit_row`
interning; worker probes are now included in that counter. Thus its change
alone is not the net lookup change. Instance and source execution headers must
not grow. Allocation counters describe requested capacities, not full allocator
traffic or peak RSS.

## Observed work against `b9b93023`

One execution per frozen four-worker input:

| Work | sum-bits control → candidate | Raytrace control → candidate |
| --- | ---: | ---: |
| Physical Unit rows prepared | 74 → 42 | 149,817 → 49,622 |
| Prepared rows consumed at source | 70 → 42 | 149,532 → 49,622 |
| Duplicate candidate rows invalidated | 28 → 0 | 99,988 → 78 |
| Worker exact Unit probes added | 74 | 149,817 |
| Existing witnesses found | 32 | 100,195 |
| Source exact lookups skipped | 28 | 99,910 |
| Generation/pending-union fallback | 4 → 4 | 285 → 285 |
| Unit field/vector requested bytes | 14,208 → 11,840 | 28,783,152 → 19,231,152 |

Within this coverage, total exact lookup work increases by 46 / 49,907 while
the source loses 28 / 99,910 serial probes. The remaining duplicate rows were
not available in the frozen query snapshot. This is deliberate extra parallel
computation to remove serial lookup and row allocation; it is not less total
computation, concurrent graph mutation or full worker utilization.

The Instance stays 160 bytes, inline preparation evidence 32 and source
Execution 512. The mixed-prefix holder allocation is unchanged. Compiled
payload is unchanged; query task counters grow 768→800 bytes. Keys up to four
values use inline temporary storage. Larger keys requested 6,528 / 18,940,416
spill bytes. These are newly observed temporary capacities, **not** an increase
against zero: the previous code allocated a temporary Vec for every key and
did not count it. Do not add the entire new counter as incremental cost.

The ordinary global lookup counter is 12,910→12,984 / 3,824,833→3,974,640.
It now includes the worker Unit probes but still excludes source direct Unit
interning. Other scheduling-dependent lookup counts can vary slightly; use
the explicit covered probes/skips above to assess this takeover.

## Validation

All 1,428 sum-bits and 16,883 Raytrace ordered Run summaries, exact final exports,
logical effects, merge counts, existing iterative evidence and live reverse
occupancy match the frozen control. The native sum-bits acceptance is `pass`,
with its input hash checked against the fresh CPU export.

204 runtime and 96 integration tests pass, with forced hash/Bloom collision
reruns, storage-enabled checks, all-features/sparse/legacy compilation and the
README compile/run/one-repeat-bench smoke checks. New tests cover source deletion,
recreation, pending and committed unions, epoch changes and stale representations.
They exercise both single-write and constructor-prefix continuations and compare
Run snapshots, binding ownership, source results and merge accounting.

Two initial test-development failures are retained: borrowed-key test callers
needed updating, and the new hand-built Program fixture needed its existing
merge interpreter enabled because it supplied no compiled merge program.
Neither failure was accepted or excluded from the final test suite.

## Reproduce

This measures the actual standalone Cell CPU, not native egglog. Sum-bits uses
the reviewed native choice gate tied to the fresh export by hash. Raytrace uses
exact frozen-state and ordered Run-summary comparison, not a new native contract.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-unit-witness/run.py out/cell-prefix-unit-continuation FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-unit-witness/check.py out/cell-prefix-unit-continuation FRESH_OUTPUT RESULTS.json
```

Run validation commands recorded in `results.json`, retaining their exit codes
in `validation.json` and `readme-checks.json` and failed attempts separately.
Builds, binaries and full exports remain untracked. Lossless gzip exports are
hashed after decompression.

After checks and the runtime commit, use the sequential quick timer:

```sh
python3 benchmarks/raytrace-parallel/quick.py out/cell-prefix-unit-continuation FRESH_OUTPUT FRESH_TIMING_OUTPUT benchmarks/cell-unit-witness/timing-results.json
```

Finish all control sum-bits and Raytrace samples before starting any candidate
samples. Each group has one warmup, then five sum-bits or three Raytrace runs.
No interleaving or concurrent compilation, tests or profiler from this task.
Every export, Run order and logical effect is checked. Retain all durations;
grouped timing still allows thermal/background drift and is not a significance
or full worker-utilization result.

## Timing guard correction

The first grouped trial is retained in `timing-contaminated.json` and must not
be used as performance acceptance. Its raw boundaries show another workspace's
`batch_cell_learning` consuming a CPU during candidate measurements. The old
macOS `ps` format truncated the executable column, so even its
`compiler_observed: false` was not a reliable exclusion of competing work.

The timer now uses a full-width, final executable column and checks compilers
and known Cell workloads before and after **every sample**, outside the timed
process interval. On detection it saves the evidence, retains completed samples
and stops; it does not retry or cherry-pick within the group. Full process lists
are retained at group boundaries; sample boundaries retain active processes and
all guarded executables. Three lightweight harness tests verify long paths,
concurrent-work rejection and retention of an interrupted sample. They use a
synthetic process, not a Cell performance measurement.

The runtime remains `bc3e2d19`. A later clean attempt uses a fresh directory;
the contaminated numbers and their raw samples are not erased or pooled with it.
Boundary checks cannot detect work that starts and finishes wholly between
checks, nor eliminate unrelated system load or grouped-order drift.

A second attempt was interrupted by the corrected guard at the last candidate
Raytrace sample boundary when a Cargo process appeared. `timing-interrupted.json`
retains its observations, every duration and raw-sample hashes. It is not used
for performance acceptance, and boundary evidence does not locate that work
within inference, export or report construction.

## Completed guarded checkpoint

The third attempt, using the same binaries, flags, group order and sample
counts, completed with no compiler or other Cell workload detected at its
48 sample/group boundaries. All 20 warmup and measured executions match the
frozen final states, source Run summaries and logical effects; native sum
acceptance remains tied to the fresh export. `timing-results.json` contains all
individual durations and observations. No within-group samples were discarded.

| Four-worker inference median | Control `b9b93023` | Unit witnesses | Change |
| --- | ---: | ---: | ---: |
| sum-bits, five samples | 25.081 ms | 26.002 ms | +3.67% |
| Raytrace, three samples | 5.364695 s | 5.332909 s | −0.59% |

Raytrace is effectively unchanged in this short grouped checkpoint and sum-bits
regresses. This does **not** establish a speedup despite the eliminated source
lookups and allocations. The added parallel probes, witness storage and dispatch
costs remain charged; the measurements do not isolate which cost explains the
small-workload regression. Further work should reduce these costs before
expanding coverage. The implementation is `bc3e2d19`; harness correction
`c24cd9f8` changes no runtime code. This result establishes neither full worker
utilization nor removal of the remaining shared-index/publication boundaries.
