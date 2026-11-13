# Actual eggcc GPU supervision benchmark: first shadow-replay version

This benchmark uses successful bindings from a **full actual sum-bits eggcc
Pass 3 execution**, not generated tuple fragments. The current GPU region is
certified input-ready i64 affine scalar computation represented in f32. It is
not a learned whole-Cell completion model or a live GPU graph writer.

The saved program is c9ce3a6fe289a86fe681592664e3148eec55b06b3c4d53bd8725de7ced3b949a,
from the existing compiled sum-bits artifact. Its source.egg SHA256 is
29b8396e56c0a08bc11ca9e5d52afdc25c138e5e4731d2780484bb004b3686d1, matching the
repository's workloads/pass3/suite.json sum-bits entry. The program includes its
previously compiled markers/catalog. The current worktree executes it through
Program::parse and Executor; the audited final export equals a separate ordinary
CPU execution exactly. No input/source rewrite or graph mutation is applied by
the GPU test. This equality is an audit-invariance check, not a new independent
native semantic acceptance claim. Live scheduling/publication changes will still
require the repository's Run and sum-bits choice-diagnosis acceptance contracts.

## Local marks and denominators

Each mark identifies `(Run ordinal, binding index within that Run, rule)`; a CPU
numeric mismatch also identifies the affected output slots. Full records go to
`OUTPUT.marks.json`; the committed summary keeps reason counts and artifact paths.

- `cpu_only`: outside the compiled numeric region, or an unsupported scalar rule.
  Ordinary actual CPU execution supplies this work. This is not a prediction error.
- `preflight_mark`: input violates the exact f32 domain, detected before dispatch.
  It is a host admission failure, not falsely attributed to the GPU.
- `gpu_mark`: device detects a nonfinite result and returns an explicit flag.
- `cpu_detected`: exhaustive independent native primitive recomputation disagrees
  with a GPU output. Silent errors are those without a device mark.

Every admitted GPU result is checked, not sampled. The supervisor replaces bad
numeric positions with CPU reference values in the replay result and verifies
exact equality afterward. CPU-only/marked regions retain the exact CPU baseline;
there is no live asynchronous correction/retirement protocol yet.

Coverage is measured against both all successful bindings and scalar bindings.
Natural silent error rate uses all CPU-checked GPU bindings as denominator.
CPU-only discovery share uses the union of device marks and silent errors;
when no issues occur the share is **null**, not a fabricated zero-percent recall.
Unknown unexamined graph errors are not included in the numerical denominator.
Logical bindings, marks and output corrections are not committed mutations.

## First result

- 1,428 actual Runs; 7,265 successful bindings.
- 634 scalar bindings, all admitted by the exact affine subset; 19 GPU batches.
- Numeric coverage: 634/634 scalar bindings, **634/7,265 = 8.73% overall**.
- 6,631 bindings outside the numeric region get CPU-only local marks.
- Natural device marks, CPU-detected mismatches and silent numeric errors: zero.
- 57 separate host-side output/flag fault controls all detected and corrected:
  19 proactively marked wrong outputs, 19 silent wrong outputs, 19 silent NaNs.
  These are controlled supervisor tests, not 57 natural GPU faults or a measured
  real-world detection probability. Injected rates never enter natural rates.

CPU diagnostic timings for 634 checked bindings:

| Phase | Time |
|---|---:|
| Native primitive reference execution | 4.867 ms |
| Exact comparison | 0.607 ms |
| Correction-buffer copies/control | 0.270 ms |
| Oracle process/JSON round trips, inclusive of native reference | 117.891 ms |
| Entry routing | 10.386 ms |

Reference plus comparison throughput is about **115,811 bindings/s**, or
**8.635 microseconds/binding**. Process time overlaps the reference time and must
not be added to it twice. Oracle parsing/startup and input packing are not
silently hidden. The Rust oracle is a debug build and uses per-case scalar maps;
this is not the optimized CPU ceiling. First GPU requests total 0.847 s, including
compilation, dispatch and materialization; this is not steady-state GPU time.
No overall speedup is claimed.

The full audit collector took 60.47 s versus about 0.644 s for ordinary CPU
execution. Although it discards snapshots after each Run to bound memory, it
still constructs them. Therefore it is an **offline diagnostic collector** and
must not be installed in the runtime hot path. Supervision timings above replay
its saved bindings and do not hide that collection cost.

## Reproduction

Build the two current-worktree examples:

```
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false \
  cargo build --locked -p eggfuse-cell-compiler \
  --example gpu_supervision_trace --example gpu_supervision_oracle
```

For a fresh source artifact, use the repository's normal
`cargo cell-compile --case sum-bits --output out/sum-bits` command. The frozen
result above uses the identified prior sum-bits artifact; catalog changes can
change binding counts. Collect and replay from the repository root:

```
target/debug/examples/gpu_supervision_trace PROGRAM.json out/eggcc-gpu-supervision/sum-bits.json
python benchmarks/eggcc-gpu-supervision/run.py \
  --trace out/eggcc-gpu-supervision/sum-bits.json \
  --compiler AFFINE_COMPILER.py --oracle target/debug/examples/gpu_supervision_oracle \
  --output out/eggcc-gpu-supervision/sum-bits-results.json
```

Use the NumPy/MLX environment on Metal. AFFINE_COMPILER.py is the preserved
`benchmarks/cell-f32-scalar/compiler.py` at commit a24876d6; its hash is recorded.
It can be extracted with git show into an ignored output directory. The proof
checks each original intermediate, not just final cancellation, and rejects
unsupported primitives/types or unready dependencies. Binary artifacts, raw
trace exports and full local mark files remain under out/.

Next integration requirements: a lightweight live Cell-instance hook instead of
full Run snapshots; precise device status and instance lifetime handling; CPU
correction before dependent effects are visible; real learned Cell-region
coverage; optimized CPU-only checking baselines; complete live semantic and
end-to-end performance gates. This benchmark establishes the supervision and
reporting contract, not completion of those runtime requirements.

## Lightweight live Cell observation

`Executor::binding_observer` is an optional read-only callback on the finalized
source-Run patch, after matching/ownership selection and before RHS execution.
It receives `(Run, binding ordinal, rule, borrowed Slots)` with a rule filter.
No callback can mutate the borrowed bindings through this API, and no result is
accepted as a graph effect. The normal executor leaves the observer unset.
The instance remains the sole runtime binding representation; this observer
creates no maintained reverse graph or alternate fact store.

`gpu_supervision_live_trace` disables full audit and copies only scalar-rule
slot values into the diagnostic output. Other bindings retain their local IDs
for CPU-only marks. This avoids every Run graph export and the full all-rule
binding serialization. It still creates JSON records in its callback; those
costs are measured and are not the intended final device ABI.

One debug-build diagnostic pair on the frozen sum-bits program:

- Observed execution: 223.577 ms; ordinary execution: 188.674 ms.
- Callback time: 31.246 ms; no full snapshots or ordinary binding-audit records.
- All 634 scalar bindings exactly match the earlier full-audit trace, including
  Run, local ordinal, rule and typed values. All 7,265 locations are retained.
- Final graph, Run counts, ruleset order, change flags and executed-binding counts
  match the ordinary reference. This is not a multi-repeat performance estimate.
- GPU replay on this new trace again checks 634 bindings and passes the separate
  fault controls; its timings are recorded independently in sum-bits-live-results.

The focused Cargo test exercises finite Run boundaries, union-enabled matching
and enabled/empty observer filters, comparing every graph snapshot and complete
binding audit against the observer-free execution. It passes. No GPU result
writeback, scheduling change or semantic substitution has been introduced.
The historical native choice-diagnosis inputs were not present in the available
worktree output directories, so no new choice-diagnosis pass is claimed. The
observer's exact reference comparisons and Run-boundary test establish its
read-only invariance, not independent native correctness of the entire program.

```
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false \
  cargo build --locked -p eggfuse-cell-compiler --example gpu_supervision_live_trace
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false \
  cargo test --locked -p eggfuse-cell-compiler --test cell_binding_observer
target/debug/examples/gpu_supervision_live_trace PROGRAM.json \
  out/eggcc-gpu-supervision/sum-bits-live.json
```

Replay this output with the existing run.py command. The next required step is
batch device exchange plus validated RHS result consumption, with local CPU
fallback before any dependent effect. A live read-only observer alone does not
complete that takeover and does not establish an engine speedup.
