# Current Cell context instead of recurrent latent memory

`device_current_cell_inputs.current_inputs` reads the explicit current Cell set
through the existing ownership slot interface on GPU. It includes completed
non-seed Cells and all compiled slots, rather than truncating generated Cells to
the seed-query width. It returns floating role/scalar/equality-context fields,
visibility/lifetime masks and a completeness flag. Stable IDs are used only for
incidence, not embedded numerically. Historical predicted latents are not read.

`current_candidates` encodes these fields into ephemeral 128-float embeddings and
feeds them into the existing exact source/ownership query route. The original
state is unchanged. It rejects unsupported block-token layouts explicitly.

Tests poison all historical latents with NaN and verify identical finite query
features and bindings after a physical ownership transfer. Unsettled visible
Cells prevent completeness; hidden Cells contribute zero fields. Dirty historical
latents do not invalidate the explicit feature reader, but this does not remove
the old admission guard or authorize unverified effects.

This is a standalone input-path implementation, not a trained runtime takeover.
The encoder in the test is randomly initialized. The old recurrent checkpoints
must not be presented as validated for this representation. Current limitations:

- No training or full Run audit of the new representation yet.
- Existing bounded Cartesian query routing remains; not full-set attention or
  proven complete scalable context selection.
- Full-width per-Cell encoding is charged work and has no demonstrated speedup.
- New matching/effect heads must consume these transient embeddings; old Run
  scheduling and ownership checks remain authoritative in the interim.
- Exact selected source projections still matter: a logical producer is not
  necessarily the physical owner of a reused result (Bake branch f3321a3a).

Next integration must train from current synthetic explicit states, validate
multi-Run generation, and only then retire recurrent-latent invalidation within
proven coverage. It must not substitute an unvalidated encoder for old weights.

## Synthetic current-state training

`neural_third_step.py --current-state --include-uncovered-transfers` now generates
features from exact completed synthetic Cells after ownership transfer. It uses
resolved semantic source addresses, drops recurrent parent/consumer replay arrays,
and pads to the actual maximum observed full layout. It does not assume twice the
base template width bounds the composed layout. CPU exact application supplies
labels; no real Run bindings train this experiment.

`train_current_cell.py` trains a fresh encoder, transient transition and Eq head
with backprop. Only explicit `x`, edges, masks, source role tags, requests and
incidence enter the model. There is no token-target regression or recurrent
latent input. The dataset hash and current-state manifest are checked.

The first canon run uses 61 template pairs, 717 candidates, 233 legal matches and
600 training steps. Matching errors fall to zero; 207/233 legal states have exact
Eq outputs, with 18 false-positive and 11 false-negative pairs. This is training
fit, not independent validation or a full Run audit. It is not enabled by default.
The 5,376-float padded source input also requires efficiency work. This uses the
existing selected query context, not yet all-context generation or scalable
Bake-directed routing. Evidence is in `current-cell-results.json`; large artifacts
are outside Git under `current-cell-v36`.

```sh
python neural_third_step.py TRACE DATA.npz --ruleset canon --current-state --include-uncovered-transfers --count 1 --per-pair 1
python train_current_cell.py DATA.npz FIT.json --steps 600
```
