# Direct source-consumption features

This is an input-feature experiment for the standalone GPU Cell prototype,
not an egglog runtime speedup or an accuracy improvement. The resident model
and Run/fixed-point/stage controller are unchanged. No backpropagation is used.

The existing role-weighted token pool can obscure which inputs share a logical
source, share its port, or are equal only through current typed equivalence.
`device_input_relations.py` extracts four separate relation channels from the
actual selected joint witness. Source generations participate in identity;
physical owner addresses do not. Typed root equality uses the current input
snapshot, never the consumer's completed outputs. Integer IDs are not encoded
as floating magnitudes.

For each port, a fixed 128-by-32 projection computes
`h = tanh((source_token * edge_role) @ W)`. For each relation, a masked matrix
product and pairwise floating products yield 32 columns, totaling 128 f32
columns per candidate. There is no dynamic GPU branch, host lookup, gradient,
or per-node scheduling inside this feature operation. Pair-mask work is
quadratic in input-port count and must be charged; this does not eliminate
existing matching or ownership checks. The experiment allocates its output;
production fusion into the ridge input is not implemented.

Validation:

- Tests distinguish source sharing from typed equality, reject accidental
  generation reuse, and check ID-renaming and padding invariance.
- A compiled Metal replay agrees with NumPy.
- `audit_input_relations.py` verifies archive provenance and each actual joint
  witness before measuring input-only features. It never fits from this data.
- `input-relations-results.json` replays the saved Pascals cross-ruleset capture:
  26 accepted Cells, 107 same-source pairs, zero same-port or equal-input pairs.
  Consequently these samples cannot validate the extra Eq channels. The new
  features are **not installed**, and no accuracy improvement is claimed.
- Timings are single warm diagnostic launches excluding upload/compilation,
  not an end-to-end speed comparison. At this small batch they do not establish
  a GPU advantage.

Reproduction (Python with NumPy and MLX):

```
python -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_device_input_relations.py
python benchmarks/eggcc-gpu-supervision/audit_input_relations.py CAPTURE.npz OUTPUT.json
```

The saved `pascals-boundaries.json` execution evidence identifies rule 283
(context, first Run 467, 9 applications) and rule 538 (type-helpers, first Run
22, 6 applications) with slot-only supported queries, copy/union effects, and
union operands different in their pre-Run observations. These counts are
candidate observations, not committed novel union counts. Before training,
capture their pre-Run boundaries and support typed union/congruence in the
independent CPU reference. Keep program-separated validation and report direct
source consumption separately from rollout, including false merges after
closure. Target-token RMSE alone is not the acceptance metric.
