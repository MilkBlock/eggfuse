# Certified f32 scalar columns fused into Cell projection

First working **standalone bench**, using the existing SubTuple rule (original
rule 138) and actual native Cell scalar-slot snapshots. This is not a production
engine takeover: `engine_primitive_executions_removed` remains zero. The bench
consumer uses GPU-produced scalar outputs instead of recomputing its two CPU
expressions. These are prepared values, not committed graph mutations.

## What is compiled

`rule.json` is the actual compiled recipe for:

```
SubTuple(expr, a, b), b > 1
  => ... SubTuple(expr, a + 1, b - 1) ...
```

The scalar destinations are existing SSA slots 8 and 9. Both depend only on
query-bound i64 slots 1 and 2. Constructor/effect instructions between them are
not moved or eliminated. A real integration must consume prepared outputs only
at the corresponding original RHS positions and preserve current instance
validity and ordered effects. The bench does not publish anything.

`compiler.py` derives affine integer coefficients directly from typed recipe
instructions. It supports add/subtract and multiplication by a compile-time
integer constant. It rejects division, variable multiplication, unsupported types,
unknown/effect-dependent inputs and overwritten slots. Typed i64 copies are
resolved as static aliases; general nonlinear primitives remain unsupported.

For every original scalar operation, it proves

```
sum(abs(coefficient[i]) * input_bound[i]) + abs(constant) <= 2^24
```

Constants and coefficients must also be exactly representable integers. This
bounds every individual product and any accumulation order. A later cancellation
cannot hide an unsafe earlier intermediate: every original operation is checked.
Runtime checks i64 input bounds **before** f32 conversion; the selected domain
is `abs(value) <= 2^20`. All layout scalar inputs also obey this finite bound,
so unused nonlinear feature columns cannot introduce `0 * NaN/Inf` into the
exact columns. Original `b > 1` matching semantics remain explicit.

The existing feature basis includes `v/4`. Exact scalar coefficients are scaled
by four and checked again, then appended to the same shared projection matrix:

```
features(slot_values) @ [Cell_projection | exact_scalar_columns]
                     + [Cell_bias       | exact_scalar_constants]
```

The first 472 columns feed the existing frozen ridge computation. The last two
are exact `a+1` and `b-1`, not learned predictions. Only 168 bytes of coefficients
are added for this layout. No new runtime graph, reverse index or binding copy is
introduced. GPU performs one fixed computation graph with float32 matrices and
pointwise features; no graph traversal, data-dependent branch or backpropagation.

## Correctness and fallback

The bench selects the most-shared layout with exactly one SubTuple entry, using
layout structure only. Eight original corpus instances share it; five satisfy
`b>1`. Scalars are read from the saved actual Graph.argument export and verified
against the corpus, not invented model inputs. No retraining is performed.

`scalar_fragment_reference.rs` calls the actual runtime `value::primitive` for
the guard and arithmetic. Across 1,014 native-oracle cases, including domain
edges, random values, guard rejection and i64 overflow:

- 496 eligible cases produce 992 GPU scalar results, all **exactly equal**;
- 514 cases reject the original guard;
- 4 cases take checked-i64 CPU fallback, including overflow returning failure;
- dispatch results from GPU/fallback/rejection exactly match the native oracle;
- existing ridge top-1 predictions remain unchanged on the admitted real rows.

`check_compiler.py` separately verifies rejection of unsafe intermediate
cancellation, inexact bounds, division, variable multiplication, wrong types and
unavailable dependencies, plus supported constant multiplication.

## Costs: no speedup established

20-repeat warm medians from `results.json`, milliseconds:

| Rows | CPU scalar + GPU state/ridge | Joint GPU scalar/state/ridge |
|---:|---:|---:|
| 5 | 0.528 | 0.532 |
| 640 | 0.614 | 0.618 |
| 5,120 | 0.820 | 0.875 |

Request timings include f32 packing and result materialization; joint requests
also include range/guard checks. Native slot extraction, source dispatch,
publication and real effect handling are excluded. Larger batches repeat the
five eligible rows of one compatible layout; they do not establish production
batch occupancy. CPU reference uses vectorized integer add/sub, not an artificially
slow interpreter. CPU baseline times assume the already-qualified cohort.

Two trivial scalar operations do not save enough work to demonstrate a latency
benefit; the larger joint batch is slower here. Resident GPU timings vary and
must not be used to hide host-side costs. This is a working representation and
correctness gate, not evidence of actual engine acceleration. Longer input-ready
scalar chains would need separate measured justification before takeover.

## Reproduce

Use the native slot export and compact-blend model from `../cell-fixed-state-gpu`:

```sh
cargo build --locked -p eggfuse-cell-compiler --example scalar_fragment_reference
out/cell-real-state/venv/bin/python benchmarks/cell-f32-scalar/check_compiler.py
out/cell-real-state/venv/bin/python benchmarks/cell-f32-scalar/run.py \
  --corpus out/cell-multi-entry-ridge/corpus.json \
  --slots out/cell-fixed-state-gpu/slot-inputs-addressed.json \
  --model out/cell-fixed-state-gpu/compact-blend/model.npz \
  --oracle target/debug/examples/scalar_fragment_reference \
  --output out/cell-f32-scalar
```

The recipe snapshot was obtained from `real_completion_dataset` with
`include_program: true` on a single existing input, selecting compiled recipe
rule 2. Its source text is checked against the saved original rule 138 on every
run; program and recipe fingerprints are retained. Binary outputs stay in out/.

## Shared scalar columns and explicit exports

The next compiler step shares identical affine result columns. Consumers read
through the template's static `output_columns` map; there is no per-instance
alias registry. By default every original scalar result remains exported.
An explicit `exports` contract may select fewer results, but the caller must
establish that omitted slots are unnecessary for consumers, history and later
stages. This prototype does not infer that global liveness proof. Every original
intermediate operation still receives its range proof before output pruning.

Two actual saved recipes in `shared-rules.json` exercise this:

| Recipe | Original scalar work | GPU result columns |
|---|---|---|
| 146 TupleRemoveAt | `idx+1`, `idx+1`, `len-(idx+1)` | Two columns; slots 7 and 8 share column 0 |
| 499 Top extraction cost | `1+c1`, `c2+c3`, sum of both | One column `1+c1+c2+c3` when only slot 21 is requested |

`shared-results.json` records 8,204 exported results checked exactly against
native runtime primitives on Metal. Inputs are synthetic bounded scalar values
applied to real recipe instructions, not successful rule-match traffic. Both
recipes also check an i64 overflow fallback case. In particular, the second
recipe must reject an overflowing intermediate even when later cancellation
would make the final mathematical result small. This is arithmetic validation,
not full rule/effect validation or a new speed measurement. No engine primitive
executions have been removed.

`catalog-results.json` surveys the saved full program's 582 **base recipes**:
50 contain RHS primitives, 37 pass the current affine subset at bound `2^20`,
and the largest RHS has three primitives. The query-side maximum is four.
These are static counts, not execution frequencies or an upper bound on
cross-stage composed Cells. Longer composed fragments need actual execution
and consumer-liveness evidence before claiming eliminated work. The census
keeps fingerprints of its source; it does not credit saved runtime operations.

Reproduce the additional checks and census:

```sh
out/cell-real-state/venv/bin/python benchmarks/cell-f32-scalar/check_shared.py \
  --oracle target/debug/examples/scalar_fragment_reference \
  --output out/cell-f32-scalar/shared-results.json
out/cell-real-state/venv/bin/python benchmarks/cell-f32-scalar/catalog.py \
  --program out/cell-execution-deferred/readme-compiled/program.json \
  --output out/cell-f32-scalar/catalog-results.json
```

The checked-in recipe snapshots make the arithmetic checks independent of the
saved full program. The full census requires that saved compiler artifact.
The original joint scalar/ridge regression also passes after these changes;
its earlier timings above remain the performance evidence.

## Actual next-Run scalar composition

`continuation.py` composes the scalar preparation of two real rules:

```
Concat(SubTuple(expr,a,b), SubTuple(expr,a+b,c))
  -> SubTuple(expr,a,b+c)
  -> Concat(Single(Get(expr,a)), SubTuple(expr,a+1,b+c-1))
```

The second rewrite still requires its ordinary successful match, including
`b+c > 1`. The compiler prepares its arithmetic early; it does **not** predict
or authorize that match, construction, union or publication.

`continuation-cases.json` retains 12 actual multi-entry source cases from the
existing corpus. The native Cell executor was rerun with audit enabled. For each
case, the collector selects one producer binding, finds its constructor key in
the completed Run's visible rows, and checks that the whole row (including its
actual result witness) is the next Run's consumer query binding. It does not
assume `(producer, operation)` is the returned constructor address. This is
observed continuation evidence, not a count of new mutations or a full apply log.
The example exporter now supports optional `include_bindings: true`.

The declared constructor schema supplies the port wiring. Mutable functions,
missing scalar inputs, incompatible interfaces and unsafe accumulation bounds
are rejected. Producer and consumer scalar instructions are composed before
matrix construction, preserving every original intermediate range obligation.
For `[a,b,c]` the result is:

```
[a b c] @ [[0,1,0], [1,0,1], [1,0,1]] + [0,1,-1]
       = [b+c, a+1, b+c-1]
```

There are 48 bytes of f32 coefficients and biases. The producer's slot 9 reads
column 0; consumer slots 8 and 9 read columns 1 and 2. Its input slot 2 can also
refer directly to column 0. These maps belong to the shared template. The GPU
uses one fixed matrix expression; no backpropagation or dynamic graph traversal
is added. This is an exact scalar block, not a newly trained ridge model.

The bench retains that one device result batch for both stages. It removes the
second GPU scalar submission and the consumer input `stack`; it does **not**
remove the intermediate `b+c` output, which is required by the observable
SubTuple construction. All three scalar outputs remain available to graph
effects and other consumers. No runtime binding registry or consumer list is
introduced.

`check_continuation.py` validates 6,186 scalar results against the native
primitive oracle: 12 observed bindings plus 2,050 synthetic arithmetic cases.
Synthetic cases are not asserted to satisfy the full rule queries. It also
checks mutable boundaries, unrelated constructors, late scalar inputs and
unsafe accumulated ranges are rejected. The original compiler checks pass.

Warm host request medians (20 repetitions), milliseconds:

| Rows | Two GPU stages | Joint GPU block | NumPy CPU arithmetic |
|---:|---:|---:|---:|
| 12 | 0.461 | 0.258 | 0.007 |
| 768 | 0.435 | 0.219 | 0.016 |
| 12,288 | 0.584 | 0.362 | 0.146 |

Larger batches repeat the 12 observed rows. Timings include range checking,
f32 input packing, evaluation and host result reads. The separate path waits
for producer completion before consumer preparation, representing two stage
submissions; the fused path prepares both at once. Run execution, graph slot
extraction, matching, publication, instance validation and the time/memory of
waiting for a real consumer are **not** included. These are scalar-only replay
measurements, not joint ridge timings or end-to-end engine speedups. CPU remains
faster for these three additions/subtractions. The useful result is removal of
an extra GPU boundary when arithmetic belongs in an already scheduled GPU Cell.

The remaining production obligations are explicit: retain the device batch only
for an appropriate instance lifetime; validate actual consumer inputs, guards,
generation and visibility; use prepared results at original effect positions;
account for speculative results never consumed and storage across Runs. The
current prototype has **zero engine operations removed**. It does not establish
that global history/publication maintenance can be deleted.

Reproduce arithmetic and GPU checks from the committed evidence:

```sh
cargo build --locked -p eggfuse-cell-compiler --example scalar_fragment_reference
out/cell-real-state/venv/bin/python benchmarks/cell-f32-scalar/check_continuation.py \
  --oracle target/debug/examples/scalar_fragment_reference \
  --output out/cell-f32-scalar/continuation-results.json
```

To regenerate actual execution evidence (each selected example is small):

```sh
python3 - <<'PY'
import json
from pathlib import Path
p = json.loads(Path('benchmarks/cell-f32-scalar/continuation-cases.json').read_text())
Path('out/cell-f32-scalar').mkdir(parents=True, exist_ok=True)
Path('out/cell-f32-scalar/continuation-input.json').write_text(json.dumps({'cases': [
    dict(id=r['id'], source=r['source'], include_program=True,
         include_bindings=True, verify_ruleset='always-run') for r in p['records']]}))
PY
cargo run --locked -p eggfuse-cell-compiler --example real_completion_dataset -- \
  out/cell-f32-scalar/continuation-input.json out/cell-f32-scalar/continuation-runtime.json
out/cell-real-state/venv/bin/python benchmarks/cell-f32-scalar/collect_continuations.py \
  --runtime out/cell-f32-scalar/continuation-runtime.json \
  --output out/cell-f32-scalar/continuation-cases.json
```
