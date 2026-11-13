# No-backprop token continuation: first falsification test

Standalone numerical diagnostic, not an integrated GPU runtime. The goal is to
check whether ridge outputs can feed subsequent stages without graph decoding,
teacher substitution or backpropagation. It does not establish correct effects,
CPU residual completion, token sufficiency or end-to-end acceleration.

The saved actual five-rule Cell executions supply initial graphs and every Run
boundary. The existing 272/95/102 entry split is retained. Initial and teacher
states use the prior fixed 105-dimensional structural encoder. This encoder is
recursive CPU work, not the proposed fixed shared-slot GPU entry interface.
The transition uses fixed random tanh features (256 dimensions) plus the token,
and ridge fits a residual. Three regularizers are selected by validation-only
8-step rollout error; test results do not select weights or stopping depth.
Metal executes one compiled eight-step expression; intermediate predicted tokens
stay on GPU. Only initial input and final output cross the host boundary.

Results in results.json:

- 1,498 training transitions and 595 test transitions.
- Single-step standardized MSE 0.0431, versus 0.3422 for unchanged tokens.
- Exit-only nearest known completion diagnostic: 48/102 at step 1, 83/102 at
  step 2, 86/102 at step 4, then **80/102 at step 8**. Step 4 is descriptive,
  not a newly selected test-optimal stopping policy.
- GPU and CPU eight-step outputs pass numerical closeness checks; largest
  absolute deviation approximately 0.000107. Both diagnose 80/102 completions.
- Exact final teacher tokens distinguish all 102 endpoints in the training
  completion catalog. This is a representation sanity check, not rollout success.
- No contradictory next graph for identical graph/ruleset was observed here.
  That does not prove watermark/delta can be omitted for general execution.
- **450/595 test input states occur in training trajectories**. Entry splitting
  does not provide transition-disjoint evaluation. Unseen-state error/count are
  recorded separately. All test completion classes are known in training.

The result supports feasibility of fixed GPU token chaining without gradient
descent, but contradicts any claim that this particular representation/model
already gives stable exact completion. Continued evolution drifts. Nearest-label
recognition neither proves derivability nor supplies precise output parameters.
No CPU work is removed. Runtime/semantic acceptance has not been claimed and
no CPU kernel was changed; the relevant check is numerical rollout equivalence.

## Reproduction

Use Python with NumPy and MLX on Metal. `--reference-dir` contains the unchanged
`dataset.py` and `train.py` from commit `a24876d6`, under
`benchmarks/cell-multi-entry-ridge`. Both dependency hashes and dataset hashes
are recorded. They can be extracted into an ignored output directory with
`git show a24876d6:benchmarks/cell-multi-entry-ridge/dataset.py` and the analogous
command for `train.py`; no checkout or branch merge is required.

```
python run.py --reference-dir REFERENCE_DIR \
  --runtime SAVED_RUNTIME_NATIVE.json --corpus SAVED_CORPUS.json \
  --output out/token-rollout/results.json
```

These saved artifacts are the earlier real multi-entry corpus, not newly
synthesized transitions. Regenerating them requires the collectors at the cited
commit. Binary datasets/weights and Python caches are not committed.

Next requirements remain: transition-disjoint evaluation; fixed-point stability;
comparison with direct-to-completion prediction; exact boundary payload and
validated partial acceptance; real CPU residual work and full cost accounting.
The goal is still active, not satisfied by this diagnostic.

## Variable-capacity prerequisite audit

`capacity.py` inspects all 551 saved cases and 3,548 actual snapshots. It is a
materialized-state reference, **not** a proposed one-node/one-token encoding.
It keeps repeated scalar occurrences distinct: equal values do not prove aliasing.
Eq references remain separate exact identities and are not floating features.
Only integer scalar payloads in the exact f32 domain are accepted by this audit.

Across 2,997 transitions there are 1,323 increases in scalar occurrences, but
only 249 transitions introduce previously unseen numeric values within that
execution. Neither count measures independent information or entropy. Most
structural growth cannot simply be billed as new dynamic scalar information.

| Scalar block width | Observed blocks per snapshot | Block growth events | Padding fraction |
|---:|---:|---:|---:|
| 8 | 1–4 | 831 | 19.61% |
| 16 | 1–2 | 320 | 36.43% |
| 32 | 1 | 0 | 54.58% |

These counts exclude structure, references, validity metadata and learned hidden
state. The corpus has 119,050 reference occurrences across snapshots; silently
omitting their storage/resolution would hide a major part of the representation.
The 32-slot result demonstrates that this corpus is too small to establish
scalable scalar-token growth. Reducing width merely to obtain growth is not a
scalability result. This audit does not implement dynamic GPU token storage.

```
python capacity.py --runtime SAVED_RUNTIME_NATIVE.json \
  --width 32 --output out/token-rollout/capacity-full.json
```

`capacity-results.json` keeps summaries at widths 8, 16 and 32; full per-snapshot
records are reproducible output, not committed duplicates of the dataset.
Next dataset work must introduce genuinely larger interacting multi-entry
regions, preserve short-case execution limits, and separately account for
compiled structure versus necessary dynamic state. A variable-capacity runtime
must not use future teacher snapshots to allocate or route its instances.

## Larger interacting regions

`larger.py` generates 12 connected entry forests at interval lengths 6, 8, 12
and 16. Each has two different associations of the same tuple interval, an
overlapping interior interval, and an additional existing whole interval,
Single/Get, or prefix. All roots share Input 0. Three variants also vary scalar
starts. These are overlapping real-rule inputs, not repeated independent rows.
`source-rules.json` preserves the five original recipe rules and provenance from
commit a24876d6. The newly imported `real_completion_dataset` Cargo example
executes the current worktree's compiler/runtime with boundary snapshots and an
independent native egglog final export; no runtime kernel is changed.

All 12 requested cases passed the 1-second subprocess limit, the two unchanged
fixed-point Runs, and exact canonical final DAG equality with native egglog.
The supported contract remains the five positive constructor rules, no hidden
rows or unsupported tables; canonicalization rejects cycles and missing producers.
This does not independently prove each intermediate Run equals native execution.
The first cold case took 0.793 s; others 0.065–0.178 s. These times enforce the
user's short-test budget and are not benchmark speed claims.

| Interval length | Final physical rows | Maximum 32-scalar blocks |
|---:|---:|---:|
| 6 | 57 | 2 |
| 8 | 78 | 3 |
| 12 | 133 | 4 |
| 16 | 180 | 5 |

Full per-case outcomes, including every requested attempt, are retained in
`larger-results.json`. Block counts still exclude identities, structure and
learned hidden state, and are reference materialization costs. No GPU token
allocation or no-publication execution is claimed. This dataset makes capacity
growth testable without reducing token width to manufacture growth.

```
CARGO_PROFILE_DEV_DEBUG=0 CARGO_PROFILE_DEV_INCREMENTAL=false \
  cargo build --locked -p eggfuse-cell-compiler --example real_completion_dataset
python larger.py --runner ../../target/debug/examples/real_completion_dataset \
  --reference-dir REFERENCE_DIR --output ../../out/cell-token-rollout/larger
```

Run the Python command from this directory. The reference directory is the same
pinned canonicalizer dependency described above. The command preserves inputs,
full runtime exports and results under the output directory. Timeouts and errors
remain explicit and cannot establish a pass. Debug information/incremental build
were disabled after the first build exhausted local disk space; only this
worktree's newly generated target cache was removed before rebuilding.

The next numerical experiment must use input/Bake-derived capacity, never future
teacher layouts, and keep the token block directly consumable by its successor.
These larger endpoints extend beyond the previous known completion catalog;
reusing the old 24-class readout cannot establish successful larger completion.

## Growing GPU token blocks: first executable continuation

`growing.py` executes a bounded SubTuple family on Metal. Each initial SubTuple
is a Cell entrance, not a GPU task per graph node. The batch contains 5–6
entrance Cells per larger case. The compiled fanout produces suffix Cell tokens;
the next numeric stage consumes those tokens directly within the same compiled
GPU graph. There is no intermediate graph decode, host read, table lookup or
teacher substitution. CPU setup reads initial slots once. Output capacity is
`entrances * max(initial length)`, bounded by the declared length limit 16;
future graphs are inspected only after inference for validation.

Token width is 32: two scaled numeric parameters plus 30 fixed nonlinear encoded
channels. Dense random tanh features and ridge produce the successor tokens;
ridge is fit by a linear solve, without backpropagation. The training data yields
only **14 distinct scalar entrances / 30 suffix targets**, despite having 551
source cases. Lengths are 1–4 and starts 0–4. This is an intentionally limited
first arithmetic-token experiment, not a learned representation of arbitrary
Eq/topology. Sharing and boundary identities remain outside this numerical ABI.

The 12 larger cases produce 291 active successor tokens (10–46 per case), using
626 allocated token positions: **335 padding positions**. Padding is computed,
not free; active counts do not equal graph mutations. Overlapping entrance
outputs are not deduplicated by this GPU path.

| Path | Correct rounded parameter triples / 291 |
|---|---:|
| Learned token generation and learned consumer | 188 |
| Exact first two parameter channels, learned consumer | 189 |
| Compiled exact parameter generation and consumption | 291 |

Each triple is `(suffix start, suffix length, interval end)`. All exact expected
suffixes are present in the actual completed native-checked graph. Learned GPU
outputs also match an independent NumPy computation within stated tolerances.
Rounded predictions are scored but **never treated as proofs**. The exact path
is checked with array equality, not a tolerance. Its arithmetic uses bounded
integers and powers-of-two scaling, keeping these operations exact in f32.

This reveals a concrete problem: preserving exact parameters in the first token
does not help enough if the next learned stage reconstructs them approximately.
The compiler-known channel must remain authoritative through the whole chain.
The third row is a numeric compiler control: because it does not consume learned
hidden channels, the GPU compiler may eliminate those unused calculations. It
is not evidence that a hybrid learned semantic state is sufficient or faster.
No token count/capacity evidence here establishes new independent information;
these suffix parameters are derivable from their entrance and template.

The current output replaces only numeric prototype stages. Actual CPU residual
completion, cross-entry join/union, lifecycle handling and graph work replacement
remain unimplemented; engine operations removed remains zero. Final-state
membership is an arithmetic evidence check, not a substitute for validating
arbitrary model-proposed effects. No performance claim is made.

```
python growing.py --training SAVED_RUNTIME_NATIVE.json \
  --heldout ../../out/cell-token-rollout/larger/runtime.json \
  --reference-dir REFERENCE_DIR --output ../../out/cell-token-rollout/growing.json
```

The larger examples are development evaluation cases, not a future blind test.
Regularization was fixed before this run; no test-result search was performed.
The next step needs a semantic token target beyond these known scalar parameters,
a larger training domain, and actual CPU residual acceptance. Merely making more
suffix tokens or passing this arithmetic control does not finish the runtime goal.

## GPU-completed region with actual CPU residual execution

`residual.py` now checks the completion/CPU boundary, not just numerical labels.
For each existing initial SubTuple Cell, a fixed GPU program prepares every
suffix token and its successor parameters. Input-length-derived ragged wiring
packs all 291 active tokens without the previous 335 padding positions. The
wiring arrays are constructed once on CPU; their allocation/gather costs are
not claimed to be free. The GPU does no graph lookup, union, per-node dispatch,
intermediate host read or dynamic allocation. This path uses compiled exact
bounded arithmetic, not ridge-authorized semantic facts.

At exit the legacy CPU adapter materializes a completed region using the actual
original rewrite consequences. Suffix length >1 gives the original rule 138
union; length 1 gives rule 137's union. Each consequence follows by induction
from its initial SubTuple and earlier suffixes. The bounded arithmetic result is
checked exactly before source actions are constructed. Identity stays as the
same exact `(Input 0)` expression; it is not approximated by floating features.
No guessed `(producer, operation)` result address is used.

The CPU residual ruleset **omits rule 138 entirely** and retains associativity,
unit-length expansion, Get/Single equivalence and adjacent interval merge. After
residual saturation, the test enables the complete original ruleset. Acceptance
requires ALL of:

1. Residual endpoint equals the original Cell endpoint under exact supported DAG
   canonicalization, with all five tables and visibility preserved.
2. It also equals the independent original native egglog endpoint.
3. Every subsequent full-rule audit Run reports no change.
4. Two additional complete-rule Runs satisfy the exporter's fixed-point check.

All 12 cases pass. A negative control omits the GPU-completed region: the residual
endpoint is then rejected and full rules change the graph in three Runs. Merely
running the full rules afterward and comparing final graphs would conceal this
failure; the test deliberately checks the endpoint BEFORE that audit.

| Work across 12 cases | Original | CPU residual |
|---|---:|---:|
| Executed bindings | 2,049 | 1,666 |
| Saturation Runs, excluding verification Runs | 105 | 75 |

The adapter additionally executes **291 boundary action requests**. Those are not
291 new mutations and cannot be ignored when interpreting the 383 fewer rule
bindings. This is the first measured replacement of CPU matching in this
restricted experiment, not an overall speedup or a production feature.

Scope matters: this is an explicit source transformation for the positive,
unbounded saturation endpoint of these tuple cases. It changes when derived
facts become visible, and **does not preserve arbitrary finite Run semantics**.
There are no mutable functions, deletion or hidden rows in this contract. No
exclusions or extra equivalence rules were added to make comparisons pass.
Generalizing the omission of rule 138 requires a closure argument for every
admitted entry, not just these tests; arbitrary programs are not admitted.

The completion stays off the graph during GPU execution. The CPU boundary still
uses source actions to materialize a completed region in the existing runtime.
Thus this is not yet a native token-only runtime or the elimination of all
publication/repair costs. Compiler/frontend/startup and full-rule verification
are included in recorded process times; those are timeout diagnostics, not fair
end-to-end speed measurements. Each CPU invocation stays under one second.

```
python residual.py --runtime ../../out/cell-token-rollout/larger/runtime.json \
  --runner ../../target/debug/examples/real_completion_dataset \
  --reference-dir REFERENCE_DIR --output ../../out/cell-token-rollout/residual
```

The program exits nonzero on a failed requested case. Exact numeric acceptance,
actual CPU residual execution, original native comparison and the negative
control are the relevant checks for this isolated experiment. The sum-bits
contract is neither invoked nor silently extended to these tuple programs.

## Expanded training domain and learned-token CPU acceptance

The first learned fanout was trained on only 14 numeric entrances. To separate
capacity failure from missing training support, `larger.py --grid train` now
collects 49 connected cases: lengths 4,6,8,10,12,14,16 and starts
-12,-8,-4,0,4,8,12. `--grid fresh` collects 36 new cases: lengths 5,7,9,11,13,15
and starts -10,-6,-2,2,6,10, with the same deterministic three entrance variants.
All 85 cases independently pass native canonical endpoint checks, fixed-point
checks and the one-second execution limit. The grids and model settings were
fixed before evaluating the new GPU outputs. This remains a bounded development
study; topology/general Eq representation is not tested by scalar accuracy.

Training yields 180 distinct scalar entrances and 933 suffix targets. The model,
random seed and regularizer remain unchanged. The new evaluation has 822 tokens;
570 originate from exact scalar entrance pairs absent from training. Both fully
learned and exact-first-channel/learned-consumer variants get 822/822 rounded
parameter triples correct, including 570/570 novel-entrance tokens. Maximum
fully learned error is approximately 0.00149. These are integers after explicit
exit rounding and exact validation; raw ridge outputs are not exact arithmetic.
This supports training-domain insufficiency as a substantial cause of the prior
failure, not a claim that the token representation handles arbitrary semantics.

`growing.py --proposals PATH` retains the actual unrounded GPU output and hashes
its input runtime. `residual.py --proposals PATH` reads that artifact, checks the
hash, exact shape, finiteness and integer parameter identities, and corrects
rejected outputs using the exact CPU reference. It then feeds accepted values
into the same completed-region boundary and actual residual execution. It does
not rerun the exact GPU control and falsely label those values learned outputs.
The JSON artifact is an experimental handoff, not a native zero-copy ABI.

All 36 learned-proposal cases pass residual endpoint equality against both
original Cell execution and native egglog; enabling full rules makes no change.
No token needed numeric correction. Omitting the completed region is rejected
by the negative control, with two changing full-rule audit Runs.

| Work, 36 new cases | Count |
|---|---:|
| Original executed bindings | 5,556 |
| Residual executed bindings | 4,462 |
| Boundary action requests | 822 |
| Rejected learned parameter tokens | 0 |

Exact validation computes the reference parameters for every proposal. Zero
rejections does not eliminate validation cost. The CPU adapter also computes
successor parameters and materializes source actions; all of that still costs
work. No end-to-end speedup is established. The semantic contract remains the
restricted positive saturation endpoint, not arbitrary finite-Run visibility.

Reproduction, from this directory, with the same runner/reference dependencies:

```
python larger.py --grid train --runner ../../target/debug/examples/real_completion_dataset \
  --reference-dir REFERENCE_DIR --output ../../out/cell-token-rollout/train-grid
python larger.py --grid fresh --runner ../../target/debug/examples/real_completion_dataset \
  --reference-dir REFERENCE_DIR --output ../../out/cell-token-rollout/fresh-grid
python growing.py --training ../../out/cell-token-rollout/train-grid/runtime.json \
  --heldout ../../out/cell-token-rollout/fresh-grid/runtime.json \
  --reference-dir REFERENCE_DIR --output ../../out/cell-token-rollout/growing-expanded.json \
  --proposals ../../out/cell-token-rollout/fresh-proposals.json
python residual.py --runtime ../../out/cell-token-rollout/fresh-grid/runtime.json \
  --runner ../../target/debug/examples/real_completion_dataset \
  --reference-dir REFERENCE_DIR --proposals ../../out/cell-token-rollout/fresh-proposals.json \
  --output ../../out/cell-token-rollout/learned-residual
```

Raw snapshots/proposals stay under ignored output paths. Committed collection,
numeric and residual summaries retain provenance. Full cost accounting and a
semantic state representation beyond known tuple parameters remain open.

## Device-controlled stage completion

`growing.py --device-stages` adds a Metal stage-control experiment, using the
same learned floating-point completion and downstream ridge readout. It is a
standalone bounded SubTuple-family experiment, not the complete eggcc runtime.
`device_stages.py` maintains stage, immutable slot occupancy, token state and
consumer output on device. Six statically compiled ticks use masks and reductions;
there is no host read to choose a stage. Empty delta advances the device stage.
The first stage proposes its entire bounded completion; this is **not** an
iterative model of arbitrary rule application. Duplicate proposals to the same
compiler-assigned slot are idempotent. Cross-entrance aliases are still separate;
changing Eq or mutable slot values is not supported by this occupancy protocol.
Both stage expressions remain in the fixed dataflow; masked work need not be
skipped physically. No throughput benefit is claimed.

Reproduce with the training/fresh runtime files generated above:

```
python growing.py --training out/cell-token-rollout/train-grid/runtime.json \
  --heldout out/cell-token-rollout/fresh-grid/runtime.json \
  --reference-dir REFERENCE_DIR --device-stages \
  --output out/cell-token-rollout/device-stages.json
```

The 36 fresh cases produced 822 correctly rounded parameter triples. The CPU
checker derives expected occupancy independently from input lengths and checks
both missing and incorrect outputs. Normal device traces establish completion
in four ticks (produce, quiesce, consume, quiesce). Truncation at one tick is
explicitly exhausted, never complete. Silently suppressing the last slot of
each entrance removes 204 tokens: all 36 device executions still report finished,
but all 36 CPU checks reject. Checking only emitted values would miss every one
of these omissions. These are injected controls, not observed natural failures.

`device-stages-results.json` records summaries. Normal CPU array comparison took
0.735 ms total in this run; expected-value construction, native graph validation,
GPU execution, compilation and transfer are outside that comparison timer. It
must not be reported as full semantic-check speed. Timing is a diagnostic sample.

The three variant computations are asynchronously submitted before exit checks.
This does **not** yet implement CPU supervision concurrent with subsequent
stages of the same execution, correction injection, checkpoint invalidation or
replay. Nor does the device's finished flag prove complete ruleset saturation.
Those remain necessary for the intended GPU-driven runtime. No engine operation
has been removed by this experiment, and no gradient descent is used.
