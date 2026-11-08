# Component-lifetime signal slots

This experiment starts at `5ffdec1d` and changes the **standalone Cell CPU**.
It does not change or measure the native egglog runtime. The selected sum-bits
and Raytrace repair fragments are held fixed across the before/after comparison.

The baked shape already contains each signal's field-use program, and the graph
already records which facts exist. Previously, publishing and retiring each
field additionally looked up `HashMap<Signal, Binding>` and incremented or
decremented `live_ports`. The opportunity is to remove this duplicate use count,
without adding another reverse index or per-field liveness table.

## Implementation and remaining obligations

Each live component owns a vector of optional equality roots indexed by the
shape's symbolic signal ordinal. A shape continuation only appends new symbols,
so existing slot addresses remain valid as the vector grows. A slot initializes
on an actual owned-field publication; template positions that never publish
remain empty. Publication still visits each real equality field and checks its
binding. This change does not claim to remove all publication work.

Individual fact retirement no longer traverses its fields or updates signal
reference counts. Signal values survive until the component's last live fact
retires; that event scans its slots and removes external boundary routes once.
No membership or liveness list is added: repair and candidate enumeration use
the existing `cells[cell].facts[op].owned` checks. Retained slots with no live
consumer still receive equality updates so they do not become stale. Source
frame addresses remain retained by the existing component lifetime.

This deliberately trades earlier cleanup for potentially empty notifications.
The inventory reports active bindings separately from retained inactive slots.
`signal_bindings_live` now means initialized slots retained by live components,
so it must not be compared directly with the old active-binding gauge as if its
meaning were unchanged. Boundary counts include retained inactive routes.

Candidate planning previously read `live_ports`. It now derives the same exact
count from the shared slice and existing facts only when a domain is requested.
These additional scans are charged by `domain_planning_slice_steps`; candidate
enumeration still filters nonexistent facts. Training also checks that an actual
producer is live before crediting shared input reuse: a retained empty slot is
not an observation of useful sharing.

`signal_binding_reads` continues to count attach/detach accesses only, not all
hash lookups. Current accesses are direct slot reads. The removal of detach work
is separately visible in `signal_port_detaches = 0`, while component cleanup is
charged by `component_signal_retire_visits`, including uninitialized slots. Union
ordering, exact congruence checks, result publication, and external alias routing
remain unchanged obligations. No repair descriptors are added by this change.

## Correctness and structural result

The workspace passes **222 tests**, with four preexisting ignored tests. The
ownership suite passes all **26 tests** in sparse and non-sparse configurations,
and the runtime passes its no-default-features compile check. New cases exercise
inactive routes after independent deletion and late union, complete component
cleanup, and candidate completeness without returning deleted facts. Existing
cases cover aliases, partial RHS effects, constructor reuse, cross-stage origin
deletion, and unbaked continuations.

Both workloads match `5ffdec1d` in exact state, ordered RHS, effective writes,
resumes, schedule, and Spine hashes. The ordinary backend also matches each
candidate execution. These are executed-effect audits; logical rule matches are
not counted as committed mutations.

| Operation / retained state | sum-bits before | sum-bits slots | Raytrace before | Raytrace slots |
| --- | ---: | ---: | ---: | ---: |
| Attach/detach binding accesses | 12,430 | 10,122 | 2,863,219 | 2,412,255 |
| Per-field detach operations | 2,308 | 0 | 450,964 | 0 |
| Component cleanup slot visits | 0 | 1,240 | 0 | 292,166 |
| Inactive repair steps visited | 690 | 1,064 | 115,370 | 196,519 |
| Active bindings at end | 6,070 | 6,070 | 1,649,342 | 1,649,342 |
| Retained inactive bindings | 0 | 715 | 0 | 93,502 |
| External boundary routes | 4,016 | 4,726 | 1,128,198 | 1,220,022 |

The exact candidate-count scan is not invoked by either measured catalog; its
cost and correctness are exercised in the targeted tests. It remains a possible
regression for other query workloads. The component vectors also reserve space
for unpublished symbols: final capacities are 10,300 and 2,623,556 slots.

Execute allocation calls rise from 129,207 to 130,771 on sum-bits and from
30,534,702 to 30,983,872 on Raytrace. Requested bytes decrease from 28,276,462 to
28,135,278 and from 8,843,615,580 to 8,793,019,020 respectively. Per-component
vectors introduce allocations even though the global signal hash map disappears.
Allocation diagnostics are separate from normal timing and do not measure RSS.

## Performance admission

The criterion is exact semantics plus an upper 95% paired-bootstrap ratio below
one for **both inference and whole-process time on both workloads**, relative to
`5ffdec1d`. A separate comparison reports the ordinary fast baseline `8fffff65`;
beating a slower experiment alone is not an overall acceleration claim.

The normal builds use one warmup and 31 interleaved fresh processes per lane for
sum-bits, and one warmup and seven per lane for Raytrace. Executable/input paths
are equal-length symlinks and output paths use numeric lane IDs, following the
loading-sensitivity finding in the previous experiment. Whole-process time
includes load, validation, setup, execution, export and routine diagnostics.
Profiling and Bake are offline costs shared by the before/after lanes.

The change **passes the two-workload gate against `5ffdec1d`**, but **does not
beat the ordinary fast baseline**. Inference / whole-process medians:

| Workload | Ordinary fast baseline | Before `5ffdec1d` | Component slots |
| --- | ---: | ---: | ---: |
| sum-bits | 21.296 / 144.063 ms | 22.349 / 186.944 ms | 21.942 / 183.894 ms |
| Raytrace | 7.681 / 10.277 s | 7.942 / 16.689 s | 7.821 / 14.467 s |

Relative to the previous implementation, sum-bits improves **1.82% in inference
and 1.63% in whole-process time**, with 95% paired-bootstrap ratio intervals
`[0.9723, 0.9893]` and `[0.9758, 0.9947]`. Raytrace improves **1.53% and 13.31%**,
with intervals `[0.9605, 0.9892]` and `[0.8558, 0.8733]`. These are small-sample
results on the two fixed catalogs, not a general performance guarantee.

Against ordinary fast execution, sum-bits remains **3.03% slower in inference
and 27.65% slower end to end**; Raytrace remains **1.82% and 40.77% slower**.
This is an improvement to the experimental ownership path, not admission of that
path as an overall acceleration.

Most of Raytrace's whole-process reduction occurs outside timed inference.
Load/setup/export medians are similar; the remaining process interval includes
routine report validation, serialization, teardown and process overhead. The
global signal-map checks in reporting also change with this implementation.
Those phases do not have separate clocks here, so the 13.31% wall improvement
must not be described as an inference or repair speedup. Normal inference itself
improves only 1.53%.

See `admission.json` for the decision and confidence intervals, `timings-*.json`
for every sample, `monitor.json` for operation/state accounting, and
`allocations.json` for the separate allocation measurements.

## Reproduction

Retain the previous worktree's untracked frozen artifacts and archived binaries.
Use fresh output directories. All modified code lives in this independent
experiment worktree; the baseline artifacts are read-only inputs.

```sh
mkdir -p out/signal-lifetime
ln -s /private/tmp/eggfuse-union-digest/out out/baseline
cp out/baseline/ownership-fragments/runtime-final out/signal-lifetime/baseline-runtime
cp out/baseline/ownership-fragments/audit-runtime-final out/signal-lifetime/baseline-audit-runtime
cp out/baseline/ownership-fragments/allocation-runtime-final out/signal-lifetime/baseline-allocation-runtime
cp out/baseline/local-unions/runtime out/signal-lifetime/fast-runtime
out/baseline/ownership-fragments/compiler-final profile-cell-ownership --program out/baseline/producer-receipts/indexed-audit-learn-raytrace/program.json --output out/signal-lifetime/profile-raytrace
out/baseline/ownership-fragments/compiler-final bake-cell-ownership --program out/baseline/producer-receipts/indexed-audit-learn-raytrace/program.json --profile out/signal-lifetime/profile-raytrace/profile.json --output out/signal-lifetime/baked-raytrace
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked --workspace --all-features -j 2 > out/signal-lifetime/workspace-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test cell_ownership -j 2 -- --nocapture > out/signal-lifetime/focused-final.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_TEST_DEBUG=0 CARGO_INCREMENTAL=0 cargo test --locked -p eggfuse-cell-compiler --features iterative-bake --test cell_ownership -j 2 > out/signal-lifetime/non-sparse-tests.log 2>&1
CARGO_PROFILE_DEV_DEBUG=0 CARGO_INCREMENTAL=0 cargo check --locked -p eggfuse-cell-runtime --no-default-features -j 2 > out/signal-lifetime/no-default-check.log 2>&1
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,slot-transfer-audit,spine-shapes -j 2
cp target/release/eggfuse-cell-runtime out/signal-lifetime/audit-runtime
python3 benchmarks/result-port-repair/audit.py out/signal-lifetime/audit-runtime benchmarks/signal-lifetime/audit-manifest.json out/signal-lifetime/audit
python3 benchmarks/result-port-repair/audit.py out/signal-lifetime/baseline-audit-runtime benchmarks/signal-lifetime/baseline-audit-manifest.json out/signal-lifetime/audit-before
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics -j 2
cp target/release/eggfuse-cell-runtime out/signal-lifetime/runtime
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics -j 2
cp target/release/eggfuse-cell-runtime out/signal-lifetime/allocation-runtime
out/signal-lifetime/baseline-allocation-runtime --program out/baseline/ownership-fragments/baked-sum-final/program.json --output out/signal-lifetime/allocation-sum-bits-before --cell-ownership
out/signal-lifetime/allocation-runtime --program out/baseline/ownership-fragments/baked-sum-final/program.json --output out/signal-lifetime/allocation-sum-bits-slots --cell-ownership
out/signal-lifetime/baseline-allocation-runtime --program out/signal-lifetime/baked-raytrace/program.json --output out/signal-lifetime/allocation-raytrace-before --cell-ownership
out/signal-lifetime/allocation-runtime --program out/signal-lifetime/baked-raytrace/program.json --output out/signal-lifetime/allocation-raytrace-slots --cell-ownership
python3 benchmarks/leaf-completion/measure.py benchmarks/signal-lifetime/timing-sum-bits-manifest.json out/signal-lifetime/timing-sum-bits --repeat 31 --normalize-paths
python3 benchmarks/leaf-completion/measure.py benchmarks/signal-lifetime/timing-raytrace-manifest.json out/signal-lifetime/timing-raytrace --repeat 7 --normalize-paths
python3 benchmarks/signal-lifetime/collect.py out/signal-lifetime benchmarks/signal-lifetime
```

Compiler and runtime builds remain separate to avoid Cargo feature unification
changing the exported JSON key order. Source catalog hashes and executable hashes
are retained with the results. No published site or remote branch is updated.
