# GPU matching selector

This standalone Metal prototype selects Entry tuples before the existing Cell
effect executor. It reuses compiler equal-slot constraints, existing Entry
projections, canonical identity handles, lifetime checks and source Run execution.
It introduces no learned token semantics or new Bake catalog.

The learned prefix selector previously reported complete whenever its bounded
output did not overflow. Negative model scores could silently remove legal
matches. It now reports completeness only when no eligible choice was discarded
and no overflow or nonfinite score occurred. Proposal enumeration has a separate
status. A learned rejection alone cannot establish saturation.

The new --exact-prefix mode checks repeated variables within each atom and
shared variables with preceding atoms on GPU before expanding the prefix.
It materializes a bounded set of surviving prefixes rather than the full
Cartesian product. Intermediate overflow remains an explicit incomplete result,
even when later atoms would eliminate every retained prefix.

This mode uses no learned pruning. It supplies a correctness baseline for
learning query orders or proposing work with an exhaustive residual path.
Such learned scheduling and residual execution are future work. Scalar guards,
visibility and effect legality remain the existing executor's responsibility.
The synthetic fixture uses slot-only constructor queries; this is not coverage
of arbitrary eggcc rules or a speedup in the native egglog runtime.

## Checks

Run with a Python environment containing NumPy and MLX:

```sh
python -m unittest discover -s benchmarks/eggcc-gpu-supervision -p 'test_device*prefix*.py'
python benchmarks/eggcc-gpu-supervision/audit_current_cell.py \
  TRACE.json CURRENT_MODEL.safetensors OUTPUT.json \
  --template-only --exact-prefix --candidate-capacity 32 --runs 3
```

The audit still loads the existing model checkpoint for the surrounding effect
audit interface and verifies its recipe hash. Exact prefix selection does not
use its scores. Every audited Run compares complete query-binding sets and
the resulting graph to the independent CPU reference. A three-Run budget is
not a saturation guarantee.

A unit fixture with three 16-row pools sharing one variable has 4,096 Cartesian
tuples. The selector examines 528 active prefix extensions, schedules 768 padded
extension lanes, and returns all 16 matches. These are different work units:
528 does not count all field comparisons, sorting or Entry preparation.
No end-to-end timing benefit has been established.

The saved audit in exact-prefix-results.json covers 61 synthetic template pairs
and 88 Runs. Every Run passes both complete query-set and graph comparison.
There are zero reported query overflows. Fifty-nine cases reach a verified fixed
point within three Runs; two remain active at the budget. The previous learned
failure pair (6, 7) passes all three audited Runs with exact selection. CPU audit
time in the JSON excludes GPU execution and is not inference performance.

