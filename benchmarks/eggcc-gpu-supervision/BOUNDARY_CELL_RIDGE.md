# Persistent boundary state in the GPU Cell recurrence

This standalone Metal experiment addresses the demonstrated loss of request
attachment in `whole_cell_ridge.py`. It changes the prediction representation;
it does not modify the CPU executor or authorize ownership transfer.

## Representation and execution

A row is one Cell: a 64-float body code plus 16 floating channels for each
original boundary port. Role and adjacent-role features initialize those channels.
They do not encode physical node IDs. Original boundary addresses persist through
a quotient: merged ports have the same target channel values but keep their
addresses for compiled consumers. These channels are lossy features, not exact Eq
proofs. Opaque renaming with a consistent layout preserves the representation.

Bake supplies a fixed dense projection from these boundary channels to a 64-float
request attachment. Different query input slots have different dense weights.
The projection uses the **current** channels, including predictions from the
previous step. Concatenated body, request, interaction and attachment features
feed a fixed nonlinear random projection and closed-form ridge readout. No
backpropagation is used. Ridge predicts residuals for both the whole body and the
boundary channels, plus an emission score.

The two-step Metal function keeps the first predicted body and boundary channels
on device and feeds both to the next step. No correct intermediate channels are
injected. NumPy evaluates the same learned recurrence for numerical checking.
The bootstrap and training targets still come from offline semantic completion.
Bake chooses requests and wiring: arbitrary interacting-token match discovery
remains absent. This is not the full GPU inference loop.

Only original boundary ports are represented. A second request involving a new
unrepresented port is explicitly excluded. The bounded search picks the first
64 admissible test-family chains; it encountered zero such exclusions before
filling that limit, which does not establish general new-port coverage. New
ports, ownership responsibility, lifecycle and source Run legality remain open.

## Results and cost

The same producer-family split and known-catalog exact-body decoder as the prior
experiment were used. Test exact-target selections increased from 95 to 98 out of
140 novel targets; validation decreased from 96 to 94 out of 214. Test wrong or
spurious emissions were 41 and missed emissions 4. Alternative alpha-equivalent
catalog targets are still conservatively counted as different. The decoder reads
only the predicted body, not boundary channels; it does not certify the learned
boundary state. It is a post-hoc audit with host export/reload, separate from the
resident two-step recurrence.

Test body RMSE increased from 0.07968 to 0.08130. The 64-chain two-step body RMSE
was 0.18063, compared with 0.18163 in the preceding experiment. These small mixed
changes do not establish a reliable accuracy improvement. Boundary RMSE in the
JSON is calculated only over live ports, excluding padding. Neither RMSE nor
emission counts establish semantic correctness.

The current padded layout uses 104 ports, or **1,728 f32 values per Cell**, versus
64 previously. Each fully materialized request projection has **106,496 f32
weights**. This deliberately explicit prototype is too expensive to justify as
an efficient runtime representation. No timing or speedup claim is made, and it
must not be presented as replacing CPU execution. Training validation loss also
averages heterogeneous output channels; loss balancing is not yet studied.

The five tests demonstrate attachment discrimination, use of predicted channels
by the next step, renaming invariance, inherited port addresses after union and
explicit rejection of unrepresented ports. They do not prove the encoding
injective. Fixing the demonstrated collision is necessary but not sufficient.

The next representation must retain source-relative attachment while sharing or
compressing these boundary channels and request projections; otherwise state and
bandwidth growth overwhelms the small measured benefit. It must also represent
new boundary outputs, not silently restrict the intended runtime to this subset.

## Reproduction

Use the same PROGRAM and TARGETS as `WHOLE_CELL_RIDGE.md`, and a Python with
NumPy and MLX on Apple Metal:

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/boundary_cell_ridge.py PROGRAM TARGETS RESULTS --predictions PREDICTIONS
$PYTHON benchmarks/eggcc-gpu-supervision/decode_cell_completion.py TARGETS PREDICTIONS AUDIT
$PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_boundary_cell_ridge.py
```

`boundary-cell-ridge-results.json` records the numerical and exact-body audit.
This is not the sum-bits native semantic acceptance contract.

## Rank-64 compression experiment: not accepted as an improvement

`--boundary-rank 64` fits an uncentered SVD basis U using **only training-family
source and target boundary states**. Validation/test values do not fit the basis.
The rank was fixed at 64 for this experiment. No backpropagation is introduced.

For a row boundary b and request matrix P:

```
z = b U                           # initial encoding / training targets
P_compressed = transpose(U) P      # offline Bake projection
attachment = tanh(z P_compressed)  # GPU, no reconstructed port array
```

The ridge predicts the next compressed z as well as the body. Both are consumed
by the second step on device. Only the post-execution CPU audit reconstructs
boundary channels. Tests establish equivalence of the folded projection to the
reconstructed projected state, independence from held-out training values, and
identity-basis equivalence. They do not prove lossy projection preserves facts.

Storage falls from 1,728 to **128 floats per Cell**, and the explicit request
projection falls from 106,496 to **4,096 floats**. The shared basis has 106,496
floats offline; it is not transferred as part of the recurrent GPU step. These
are representation counts, not measured speedups. Offline construction still
materializes the uncompressed training arrays and projections.

Accuracy regresses under the same known-catalog body audit:

| Metric | Full boundary | Rank 64 |
|---|---:|---:|
| Test exact target, out of 140 novel requests | 98 | 87 |
| Test missed emissions | 4 | 11 |
| Validation exact target, out of 214 | 94 | 93 |
| Validation false emissions (novelty head) | 1 | 119 |

The boundary reconstruction diagnostic separates compression error from the
learned update. Merely projecting the correct target into the rank-64 basis and
back gives live-channel RMSE **0.15131** on test and **0.21503** on validation.
The complete learned predictor gives **0.15246** and **0.21535**, respectively.
These are errors over live channels; padding is excluded. The reconstruction
numbers are not a lower-bound proof for that masked metric, but they demonstrate
that this projection already loses substantial held-out boundary information
without a learned transition. The increased emission error is measured separately;
this experiment does not establish that all emission errors have the same cause.

The global basis is over padded layout coordinates whose semantic roles vary
between producer families. This makes shared role/layout alignment an important
next hypothesis, not an established explanation for every failure. Do not replace
the full representation with this variant based on size alone. Any replacement
must preserve request-observable distinctions and newly generated boundary ports.
The existing new-port, lifecycle, ownership and Run-order gaps remain unchanged.

Reproduce with the earlier commands, adding `--boundary-rank 64` to the model
command. `boundary-rank64-results.json` includes model and exact-body audit
results. The first 64 eligible chains still run entirely on Metal between steps;
this remains an offline standalone prototype, not the complete eggcc GPU runtime.
