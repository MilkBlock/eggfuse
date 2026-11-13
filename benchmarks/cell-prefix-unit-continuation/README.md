# Continue existing constructor results into Unit storage

The previous installed catalog's Raytrace execution already completed 308,162
constructor prefixes in query workers, while Unit preparation was restricted
to rules with no constructor. The two representations were mutually exclusive.
This change lets a Cell continue from its actual constructor results into its
terminal Unit row allocations in the same worker invocation.

## Proof and removed work

The existing typed constructor prefix proves permanent constructors, ordered
scalar prerequisites and actual returned result slots. A terminal Unit plan
may use those slots only after the entire constructor prefix succeeds. A
single-constructor prefix is enabled when it has such a tail; ordinary single
constructor probes keep their previous representation. All Unit writes must
retain the existing total old/new merge and supported storage contract.

The source consumes the original result layout and adopts each actual Unit row.
Within accepted coverage it no longer reconstructs the Unit key/fields or
replays its Set. Exact interning, winner selection, origin assignment and Run
publication remain on their existing source path. A duplicate private row is
dropped, not inserted into the graph and repaired later.

The original snapshot certificate still governs the constructor results.
Rejection clears both speculative Eq slots and the dependent Unit rows. A
pending, uncommitted union may leave the constructor identities valid while
forcing Unit adoption to fall back. Missing constructor results, failed scalars,
mutable reads, unsupported effects/storage and invisible or retired providers
retain their ordinary handling. Input identity still excludes prepared RHS slots.

This uses the existing Cell values and demanded result layout, not another
binding array, runtime fact graph, operation log or internal consumer directory.
The scheduled cross-Run Entry projection and its visibility boundary remain
authoritative. This is private continuation within that execution; it does not
claim a new cross-Run takeover or concurrent shared-index mutation.

## Work and costs against `adfd0170`

One execution each with the same frozen four-worker inputs:

| Work | sum-bits control → candidate | Raytrace control → candidate |
| --- | ---: | ---: |
| Unit rows prepared by query workers | 54 → 74 | 138,593 → 149,817 |
| Prepared Unit rows consumed at source | 54 → 70 | 138,593 → 149,532 |
| Duplicate Unit candidates invalidated | 20 → 28 | 89,350 → 99,988 |
| Prepared Unit generation fallbacks | 0 → 4 | 0 → 285 |
| Constructor prefix operations consumed | 2,466 → 2,478 | 534,859 → 535,532 |
| Ordinary key lookups | 12,910 → 12,910 | 3,824,824 → 3,824,833 |
| Generic execution instances | 5,195 → 5,195 | 1,025,397 → 1,025,395 |

Both programs compile 28 eligible mixed tails. Actual coverage is only 20
sum-bits and 4,793 Raytrace instances, producing 20 and 11,224 rows. This is much
smaller than the total existing-prefix population. Small scheduler count changes
can depend on worker completion order; the overall lookup count has not improved.

The ordinary Instance remains 160 bytes, its inline preparation evidence 32,
and the source Execution 512. Only a successfully prepared mixed tail allocates
a 48-byte holder for its existing result buffer and Unit row vector. Cumulative
holder allocation is 960 / 230,064 bytes. Unit field/vector capacity rises by
2,688 / 2,069,568 bytes. These are requested capacities, not a complete allocator
traffic or peak-memory measurement; temporary key allocations remain. Compiled
payload grows by 16,592 bytes per program, plus the optional tail pointer in
each compiled constructor plan. Query task counters grow 744→768 bytes.

The additional consumed rows are predominantly duplicate writes. This identifies
the next useful takeover: reuse an exact existing Unit witness from the worker
snapshot, avoiding both a private duplicate row and source key lookup, while
retaining lifecycle/generation checks. Merely broadening the current candidate
allocation path would amplify its cost.

## Validation

This is the actual standalone Cell CPU, not native egglog. All 1,428 sum-bits
and 16,883 Raytrace ordered Run summaries, final exports, logical effects,
existing iterative evidence and live reverse occupancy match the control.
The reviewed native sum-bits choice gate returns pass, tied to the fresh CPU
export by its hash. Raytrace remains a differential check, not a new native
semantic contract.

203 runtime and 95 integration tests pass, plus forced-collision reruns,
storage-enabled continuation/trace checks and all-features, sparse and legacy
compilation. README compile, run and one-repeat bench smoke checks pass.
The initial new union fixture expected an already committed union; its executor
actually deferred that union. Its semantic comparison passed, but the coverage
assertion failed. The final integration test explicitly requires pending-union
rejection, and the runtime test separately verifies committed-union/deletion
invalidation clears both slots and dependent rows. The failed attempt is retained.

```sh
CARGO_INCREMENTAL=0 CARGO_BUILD_JOBS=1 cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
python3 benchmarks/cell-prefix-unit-continuation/run.py out/cell-bake-owner-merge FRESH_OUTPUT target/release/eggfuse-cell-runtime
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-entry-owned/semantic FRESH_OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-prefix-unit-continuation/check.py out/cell-bake-owner-merge FRESH_OUTPUT RESULTS.json
```

Run the validation commands recorded in `results.json`, saving exit codes to
`validation.json` and `readme-checks.json`; retain failed attempts separately.
Builds, binaries and full exports remain untracked. Lossless gzipped exports
are hashed after decompression.

The user now authorizes a quick checkpoint after each change and prohibits
interleaving. After validation and committing the runtime, use:

```sh
python3 benchmarks/raytrace-parallel/quick.py out/cell-bake-owner-merge out/cell-prefix-unit-continuation FRESH_TIMING_OUTPUT benchmarks/cell-prefix-unit-continuation/timing-results.json
```

This finishes all control workloads before any candidate workload. Each group
has one warmup, then five sum-bits or three Raytrace samples. All groups run
sequentially, with no concurrent compilation, tests or profiler from this task.
Every sample checks its state, source Run order and logical effects. Grouped
timing still permits thermal/background drift; it is not an interleaved or
statistical-significance result.
