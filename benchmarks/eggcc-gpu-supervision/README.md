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

## Full-program multistage contract (current main direction)

The benchmark entry point now accepts the complete compiled eggcc recipe. Do
not select the SubTuple family as the runtime's supported-program definition.
`gpu_supervision_live_trace PROGRAM OUTPUT --all-slots` executes the unchanged
whole program and captures all typed inputs for every finalized Cell binding,
plus every Run (including Runs with zero bindings), source paths, iteration
indices and actual change flags. It compares final state and Run controls with
an ordinary execution. Equality references retain their typed identities; this
export does not silently convert them to float embeddings.

`full_program.py TRACE OUTPUT_DIR` retains all rule queries, effects, layouts,
tables and ruleset membership in a plan, and lowers the entire nested control
into Run/epoch/counter instructions. Saturation tests changes across the entire
body, including nested sequences. Repeat is bounded but also stops on an
unchanged body, matching the current runtime. Unknown control extensions fail
explicitly. Replaying actual CPU change flags checks the plan against every
Run; those flags are reference evidence, not a GPU prediction or completion.

```
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false \
  cargo build --locked -p eggfuse-cell-compiler --example gpu_supervision_live_trace

target/debug/examples/gpu_supervision_live_trace PROGRAM.json \
  out/eggcc-gpu-multistage/sum-bits.json --all-slots
python3 benchmarks/eggcc-gpu-supervision/full_program.py \
  out/eggcc-gpu-multistage/sum-bits.json out/eggcc-gpu-multistage/plan
python3 -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_full_program.py
```

The full sum-bits artifact has 582 rules and 31 rulesets. Actual execution gives
1,428 Runs, 7,265 finalized bindings across 214 active rules, and 38,709 captured
slot values. The lowered plan has 577 control instructions and 189 registers;
4,169 control steps reproduce the entire Run sequence. Seven focused tests
cover nested saturation, body-wide change, bounded/early-stopping Repeat, empty
bodies and rejected traces/extensions. These are matches/bindings, not counts
of committed mutations. `full-program-results.json` includes every ruleset,
including inactive ones. Biggest observed binding counts are always-run 3,250,
type-analysis 820, context 774 and cell-spine-complete 733.

GPU-completed bindings are explicitly **zero** at this integration layer. All
current execution is CPU reference; preserving 582 rule definitions is not
implementing them on GPU. Subsequent lowering must use these shared typed Cell
layouts and the complete source schedule, report actual GPU work and CPU marks
per ruleset, and preserve nested saturation and generation boundaries. Subsume
is excluded from intended GPU support, but remains executed by the reference;
its rules are marked, never silently deleted from correctness comparisons.
The next semantic work includes query joins, constructors, Eq/union and mutable
function merge, rather than further tuning the scalar-family demonstration.
No new native sum-bits semantic acceptance is claimed by a same-runtime trace
comparison, and no end-to-end speedup is claimed.

## Whole-recipe RHS port wiring and numeric backend

`rhs_tokens.py TRACE OUTPUT_DIR` compiles all 582 RHS definitions into shared
ordered operation wiring. Copies become aliases in this plan. Input identities
remain exact typed references; a constructor's result is an unresolved returned
port, not a guessed producer address. Set/union reference these ports, and
subsume/delete/panic retain their original positions with CPU marks. Unknown
operations fail compilation. All 7,265 actual bindings instantiate the plan.
The observed ordered instructions comprise 12,292 construct, 5,055 set, 869
compute, 689 union and 75 subsume instructions. These are instructions attached
to successful bindings, not proof that every instruction committed a mutation.
1,091 static copies (6,903 observed instances) are aliases in the plan; the
actual CPU runtime has not removed those operations because this is not yet
its execution representation.

`rhs_numeric.py TRACE OUTPUT.json` executes all available input-ready scalar
nodes from those plans as fixed compiled Metal dataflows. It handles +, -, *,
truncating /, min/max, bool-< and boolean and/or. Unresolved table-result ports
are never converted to numbers; dependent numeric operations remain uncovered.
Integer inputs are bounded before float conversion, and invalid or out-of-range
results get marks. Division remains approximate and requires exact comparison.
An independent bounded Python integer reference checks outputs; this is not a
new native primitive semantic proof. The actual sum-bits trace exercises 19
numeric kernels and 869 operations (720 additions and 149 subtractions), all
accepted. The other operators are exercised by synthetic tests, not this trace.

```
python3 benchmarks/eggcc-gpu-supervision/rhs_tokens.py TRACE OUTPUT_DIR
MLX_PYTHON benchmarks/eggcc-gpu-supervision/rhs_numeric.py TRACE OUTPUT.json
MLX_PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p 'test_rhs_*.py'
```

Seven RHS tests check exact identity preservation, actual-result placeholders,
copy aliases, unsupported/undefined operations, arithmetic/boolean kernels,
division failure, overflow marks and unresolved scalar table reads. Together
with the seven control tests they pass. Saved summaries are
`rhs-token-results.json` and `rhs-numeric-results.json`.

The numerical experiment batches saved CPU matches across Runs solely for
replay. It does not authorize effect reordering or supply autonomous GPU query
completion. GPU-completed bindings and runtime operations removed remain zero.
In particular, ordinary constructor/set/union operations are compiled ports,
not yet device-executed graph semantics. The numeric interpreter is a broad
exact-reference backend for the whole-program design, not the learned token
completion model and not evidence of most-ruleset GPU support.

## Stable identity versus local relation state

The read-only binding observer now receives `&Graph`. Running the live collector
with `--relations` captures each Eq input's stable identity and current root at
the finalized match boundary, then resolves that identity after its source Run.
Original Run controls and final graph still match ordinary execution. The Rust
observer test confirms roots can change while references survive. This optional
collector adds no relation graph to normal execution.

`relation_tokens.py TRACE OUTPUT.json` normalizes Eq partitions by first local
port occurrence, preserving sorts. Bijective renaming to IDs above 2^100 leaves
the partition unchanged. Fixed dense floating codes for local representatives,
a dense projection and tanh encode the partitions on Metal; NumPy agrees.
This is a fixed-weight representation diagnostic, not trained ridge completion.

Actual full sum-bits results (`relation-token-results.json`):

- 7,265 bindings; 735 observe root changes, but only 457 see their local input
  partition change. Representative changes alone are not new equality.
- Predicting every partition unchanged already scores 93.71%. Overall 90%
  accuracy is therefore an inadequate completion acceptance criterion here.
- Within individual Runs, 38 groups have the same rule, local partition and
  exact non-Eq inputs, but different post-Run partitions. Across the dataset,
  any deterministic predictor on this signature disagrees on at least 110
  bindings. This is empirical input ambiguity, not a test-set error estimate.
- Adding pre-Run shared-root incidence counts by neighboring rule and input slot
  reduces same-Run ambiguous groups to 3 and minimum disagreements to 3. These
  features contain no post-Run information. One-hop context is still incomplete.
- Context collection registers 30,736 Eq-port occurrences in a temporary CPU
  index. Normalization, indexing and audit cost about 103 ms in this sample.
  This is not free Bake wiring, nor a persistent reverse-index proposal. The
  floating encoder above still encodes local partitions; context aggregation
  has not moved onto GPU.

The target includes other bindings' effects and congruence in the same Run,
not just the observed Cell's own RHS. New result ports and unseen external
nodes remain outside this observation. Seventeen Python tests and the Rust
observer boundary test pass. This establishes representation evidence across
the full program, not GPU ruleset coverage or new native semantic acceptance.

## GPU context messages and ridge Eq prediction: negative result

`context_ridge.py RELATION_TRACE OUTPUT.json` sends pre-Run routing and scalar
features to Metal once. Global IDs serve only to prepare dense routing indices;
no identifier magnitude enters a float. Each input-port occurrence emits a
fixed nonlinear dense vector. Device scatter-add aggregates vectors both within
the Cell's local Eq groups and across Cells sharing a root in the same Run.
Dense projections/tanh form port states and a pooled Cell token. Pair readouts
consume the Cell state and the two endpoint states. Each pair is an output head
of a Cell, not an independently dispatched graph node. All observed rulesets
share the numerical implementation; no SubTuple selection occurs.

Ridge is fitted without backpropagation on the first 60% of source Runs, with
regularizer and threshold chosen only on the next 20%. The final 20% are test.
Positive training labels have fixed weight 20. Both a local-only ablation and
cross-Cell context model use the same pipeline. Post-Run roots enter labels
only. Tests verify label changes cannot affect input arrays, identical IDs in
separate Runs cannot communicate, large-i64 low bits survive input encoding,
and a test without positives never reports perfect recall. Integers use sign-log
and four exactly representable 16-bit input limbs; strings use fixed hashed
features. These are representations, not replacement arithmetic or equality
proofs; the dense encoding remains lossy. No unsupported scalar pairs occur in
this observed trace. Twenty-one Python tests pass.

The full trace supplies 7,265 Cells, 30,736 Eq ports and 17,526 candidate input
pairs, of which 518 become equal. Existing Eq pairs are excluded from prediction.
The final encoding includes local Eq-group aggregation even in the ablation.
Results in `context-ridge-results.json`:

| Model | Validation true / missed / false Eq | Test true / missed / false Eq |
|---|---|---|
| Local only | 120 / 195 / 989 | 6 / 0 / 312 |
| With shared-root context | 201 / 114 / 1,754 | 6 / 0 / 617 |

This model is not usable for authorizing unions. Context improves validation
recall (38.1% to 63.8%) but has too many false positives, and does not improve the
held-out false-positive count. Test contains only six positive pairs, so 100%
recall is weak evidence. The earlier exact-context ambiguity audit does not
imply that this dense random compression preserves its useful distinctions.
The report also records exact feature overlap with training and per-ruleset
held-out counts. These are one-program chronology results, not cross-program
or unseen-structure generalization.

GPU feature encoding agrees with independent NumPy evaluation. A fused GPU
encoding-plus-ridge expression also agrees with the staged device version,
with zero classification differences in this run. Offline training reads back
features; the fused inference path needs no intermediate host read. CPU routing
and scalar preparation took about 77 ms, with 702,088 routing bytes. Cold device
timings include compilation and are not evidence of runtime speedup. GPU query
completion, constructor/union commitment and autonomous whole-program execution
remain absent; GPU-completed bindings remain zero. This result shows that the current pooled encoder and ridge readout are not
reliable enough for completion. It does not disprove other ridge representations.

## Separate known Cell effects from learned Eq proposals

`proven_unions.py RELATION_TRACE OUTPUT_DIR` is a conservative CPU proof-coverage
oracle over the complete recipe. It compiles exact input-port unions, resolves
RHS constructor calls already witnessed in the successful query, and preserves
unresolved results as symbolic local ports. Primitive evaluation and mutable
reads/updates are barriers. A `set` to a **constructor** is different: it adds
`F(args) = supplied_result`, so constructor congruence can establish Eq. This
covers real TCPair/Context rules that explicit-union-only analysis misses.

The audit closes only known constructor relationships and symbolic constructor
prefixes. It runs once without history and once retaining earlier Run evidence.
Stable identities are related to current roots only from pre-Run observations;
post-Run roots are comparison targets. Source-order barriers remain, and any
Run containing subsume/delete discards retained evidence and is excluded from
the proof path. A generated result port is a symbolic term reference, not an
assumed actual object address. Constructor reuse is represented by congruence
with an existing witnessed term. No second fact graph is added to the runtime:
this standalone oracle intentionally materializes proof facts to measure what
shared Cell wiring would need to explain.

Full sum-bits observation:

| Evidence | New Eq pairs explained / observed |
|---|---:|
| Compiled input unions and their transitive closure | 230 / 518 |
| Add current-Run constructor calls and assignments | 333 / 518 |
| Retain earlier-Run constructor evidence | 512 / 518 |

There are zero observed false derived pairs among 17,526 candidate input pairs.
This is **proof coverage of an observed trace**, not learned prediction accuracy
or full graph correctness. `context` accounts for 297 changes and all 297 are
explained with history; terms-helpers-helpers accounts for 103, of which 102 are
explained. Six residual examples retain exact Run/rule/slot locations for CPU
investigation. New RHS nodes and non-Eq graph changes are not counted as covered
merely because these input-port comparisons pass.

Cost matters: the history variant retains up to 6,747 facts, reads 1,387,822
historical facts and performs 4,165,432 constructor-key checks, versus 46,237
checks without history. CPU audit took 4.104 s versus 0.143 s without history in
this diagnostic. These are not native-runtime benchmark timings. No runtime
operations have been removed and no GPU binding has completed. The oracle is
not a candidate GPU execution algorithm; reproducing its dynamic index on GPU
would preserve the wrong work.

The measured opportunity for Bake is the 179 additional Eq observations made
provable by cross-Run constructor evidence. Templates must retain actual result
ports and establish legal visibility/lifetime before replacing historical
search with static connections. The previous pooled ridge should not be asked
to rediscover all these known operations. The intended destination remains
GPU-resident Cell state and compiled connections, with CPU checking uncovered
boundaries, not CPU execution of the proven majority.

Five added tests cover constructor witnesses, ordered barriers, multi-input
congruence, cross-stage constructor assignments, history invalidation and
rejection when post-Run observations contradict a derived result. All 26 Python
tests pass. Saved counts and residual examples are in `proven-union-results.json`.

[Native Cell Eq supervisor](NATIVE_AUDIT.md): actual runtime boundary audit and Metal proposal replay; CPU execution and additional audit costs reported separately.

[Calibrated structural ridge](CALIBRATED_RIDGE.md): template alias normalization and floating pair interactions reduce false Eq proposals; stage coverage and recall remain limiting.

[Whole-workload ridge holdout](MULTITRACE_RIDGE.md): full sum-bits/loopfact training, gcd calibration and preselected dot-product testing, with native auditing of every GPU pair prediction.
