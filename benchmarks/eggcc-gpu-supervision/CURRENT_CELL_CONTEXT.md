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
