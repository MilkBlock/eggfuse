# Proven output-equality projection

This tests an exact necessary output constraint instead of another learned
feature. For the supported conditional Cell teacher, a successful match followed
by a direct union of known input ports establishes that those output ports are
equal. Its boundary encoding therefore assigns them identical vectors. Existing
`bake_stop_features.plan` follows matched input aliases and copies, and emits only
union pairs whose endpoints remain known existing ports. Fresh-result endpoints,
unknown boundaries and arbitrary native effects remain outside this coverage.

Before inference, combine overlapping pairs into disjoint groups. For each group,
replace output channel vectors by their mean. This is a fixed linear projection
onto the equal-channel subspace. It is idempotent and nonexpansive in Euclidean
boundary distance. Every teacher completed state is checked to be invariant under
the projection. The body vector is unchanged; averaging cannot reconstruct its
correct merged semantics or prove a complete token.

The device implementation uses compiled gather/reduction/scatter arrays, not a
dynamic union-find or reverse consumer lists. Only participating output slots are
projected. Batch padding uses distinct untouched slots with identity operations,
so it cannot overwrite a real projected slot via a duplicate scatter destination.
Projection applies to a candidate only when the unchanged emission gate accepts
it. The ablation rejects combining it with half-step updates, which would not in
general preserve the asserted equality. It is not ownership-transfer permission.

## Result: necessary relation satisfied, no new correct completion

On the same moments model and 850 fixed-binding inputs, 29 inputs contain a
recognized direct union pair. This count includes already-shared endpoints; it
is not a count of new logical unions or committed mutations. Sixteen free GPU
rounds give:

| Metric | No projection | Eq projection |
|---|---:|---:|
| Exact target and stopped | 808 | 808 |
| Final active requests | 4 | 1 |
| Aggregate body RMSE | 0.5807 | 0.5713 |
| Backend coordinates outside tolerance | 7634 | 6810 |
| Numerical audit | fail | fail |

All three newly stopped inputs are still wrong according to the same catalog
contract. Thus improved stopping is not a correctness gain. Fulfilling the local
boundary equality is insufficient when the independently predicted body remains
wrong. This points to a consistency obligation between body, boundary and stop
state; it does not prove the invariant projection itself is invalid. The whole
experiment is rejected as a reliable runtime improvement. No native executor
change, full ruleset saturation or throughput claim is made.

The remaining active input identity is retained in `eq-projection-results.json`,
as are the three changed stopping outcomes and the complete failed audit. There
are no backend emission disagreements or f64 decoder disagreements, but these do
not waive the failed continuous-state audit.

## Reproduce

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/corpus_repeat_probe.py MANIFEST MOMENTS.npz PROBE.json --rounds 16 --project-eq --case-output CASES.json
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_cell_eq_projection
```

Tests cover transitive group merging, unchanged body/uncovered rows, idempotence,
distinct padding destinations and NumPy/Metal agreement. The 49-test related
suite passes. All template proof assumptions remain those of the conditional
teacher, not arbitrary runtime histories with deletion or visibility changes.
