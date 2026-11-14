# Scalar-conditioned boundary features and direct-source support

This is an offline feature experiment on verified actual GPU captures, not a new
installed runtime or native Eggcc benchmark. The five-program training set remains
129 instances. GCD and LCM remain development validation programs. Ridge alpha 10,
the frozen five-program decoder, and threshold 0.5 are unchanged. No gradients,
threshold search, alpha sweep, or new graph execution are used.

## Implemented scalar-conditioned messages

For the current small family, Get consumers and neighboring Get Cells each have
one actual numeric index. `device_scalar_context.py` compiles their scalar slots
and type compatibility from semantic templates. Its kernel weights the existing
dense floating neighbor messages by

```
exp(-0.5 * (consumer_number - source_number)^2)
```

It then pools messages into the consumer's typed boundary ports. Floating scalar
closeness is never a scalar equality proof. Stable IDs only locate current values;
scalar identity numbers are not embedded as float values. Unknown/non-numeric or
multi-scalar layouts are explicitly outside this prototype. Cells without a scalar
get zero extra columns, not invented numeric inputs. Hidden, incompatible and
invalid scalar sources are masked before the floating message multiplication.

The encoder adds 256 columns (1024 bytes per candidate), taking 2177 input columns
to 2433. Predictor coefficients occupy 1,245,696 bytes, an extra 131,072 bytes.
Weighted connectivity scratch, numeric gathers, lifecycle checks and message
construction still cost work. This offline capture adapter recovers actual scalar
values from verified input identities; the resident runtime already has scalar
payload slots, but this candidate has not been wired into that runtime.

A fixed synthetic fixture distinguishes different relative scalar contexts while
the previous marginal pooling is unchanged. Tests also cover common scalar shifts,
stable ID renaming, ineligible NaNs, scalar sort compatibility, layout rejection
and compiled GPU parity. First real scalar-bearing capture blocks from all seven
programs are replayed on GPU. Maximum feature/count discrepancy is 4.77e-7; maximum
CPU/GPU predictor discrepancy is 2.93e-6.

## No validation improvement: candidate rejected

| Metric | Existing boundary model | Scalar-conditioned model |
| --- | ---: | ---: |
| GCD complete partitions | 35/41 | 35/41 |
| GCD direct-source complete | 23/26 | 23/26 |
| GCD expanded closure false merges | 0 | 0 |
| LCM complete partitions | 82/99 | 82/99 |
| LCM direct-source complete | 71/78 | 71/78 |
| LCM expanded closure false merges | 13 | 13 |

Training Euclid improves from 32/35 to 33/35, removing its two expanded false
merges. That is training fit, not evidence of generalization. Validation misses
are also unchanged: GCD 16 and LCM 35. The candidate is **not adopted** and does
not justify another expensive full GPU rollout. These comparisons precede the
separately installed whole-state output projection; do not attribute that path's
83/99 LCM result to this new input encoder.

## Direct-source support audit

`audit_direct_support.py` uses the frozen five-program model and the same captures.
For each failing direct-source validation instance it selects nearest same-template
training inputs by raw RMS feature distance, without consulting labels. Labels
are used only afterward to describe whether selected neighbors share the target.
It separately examines the full input, seed/query, source pool/interactions, and
boundary columns. It does not install nearest-neighbor inference or fit distances.

Among 104 direct-source validation instances, 10 fail (3 GCD, 7 LCM), all from rule
290. Every failure's complete target Eq state already occurs in 41 of the 77
same-template training examples. Eight failures have a nearest full-input neighbor
with that target. Thus absence of that output class is not an explanation, and
raw nearest distance often preserves relevant support. This is not a theorem
about semantic similarity or about sufficient training coverage.

Several failures also have wrong-target training examples with zero distance in
both seed/query and selected-source pooling. Boundary information distinguishes
these cases. Full-feature and boundary-only nearest neighbors can disagree, and
the nearest same-target and other-target distances can be close. The JSON retains
each failure's scores and neighbors rather than declaring a new accuracy ceiling.

There is a concrete architectural asymmetry to investigate next: the existing
random tanh projection covers the original raw features, while the later-added
512 boundary columns are appended **after** that projection. They currently enter
the final ridge primarily linearly. Scalar conditioning, shared-neighbor products
and static consumer gates have not fixed this. A controlled fixed nonlinear map
jointly involving original input and boundary features is the next hypothesis;
no improvement from it is implemented or claimed here. More features alone are
not established as the cause or remedy.

## Reproduction and provenance

Use project MLX Python. `fit_scalar_context.py MODEL CAPTURE_MODEL DECODER
DECODER_REPORT OUTPUT` takes repeated `--train` and `--validation` paths.
`audit_direct_support.py MODEL DECODER DECODER_REPORT OUTPUT` takes the same paths,
with `--source-model` for historical captures from the original feature basis.
Both check archive hashes, semantic families, distinct program partitions and
explicitly verified model feature bases. No validation sample enters the ridge fit.

Artifacts under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`:

- original model `class-history-neighborhood-input.npz`;
- frozen five-program model and decoder `five-program-boundary-*`;
- training `pascals-boundary-labeled.npz`, `euclid-boundary-labeled.npz`, plus
  `boundary-training/049-dead-branch.labeled.npz`, `033-sum-check.labeled.npz`,
  and `035-sum-sq-diff.labeled.npz`;
- validation `gcd-live-boundary-labeled.npz`, `lcm-live-boundary-labeled.npz`;
- output `scalar-conditioned-boundary.json/.npz` and `direct-source-support.json`.

Only sources and text results are committed. The active resident completion-state
feedback path, CPU executor, exact ownership proof and stage ordering are unchanged.
