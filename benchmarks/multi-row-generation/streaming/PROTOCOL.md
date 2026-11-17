# Multi-row causal emission with generated-token history

Standalone neural task, not a complete egraph engine. Freeze before fitting.
Keep the same unanchored equality-join task: 4 A and 4 B instance inputs, at most
8 obligations, 8 output slots in layouts 4x2 or 2x4. Emit one token per row per
round. No slot receives a source anchor, candidate list or assigned target.

A generated token is the current 64-float latent plus the model's own predicted
active / left-pointer / right-pointer / key / two value symbols (26 one-hot
floats). Forward symbols are hard argmax; straight-through gradients are an
explicit training surrogate. Later rounds consume these actual 90-float tokens,
with two-axis rotary row/position addresses. Original source inputs remain
available because these are emission rounds within ONE semantic stage, not a
claim of cross-Run completion. Null output is a blank slot, not an EOS that
silently drops later obligations.

Each round has three decoder blocks. Source K/V is cached once per block; each
new history token is projected into each history K/V cache once. Joint current
queries may communicate. Future emitted tokens are unavailable. Final output
storage is restored to row-major layout using a fixed index permutation only.
There is no inference Hungarian assignment, sorting by semantics, deduplication,
exact-match masking, CPU matching, teacher history or answer repair.

Two arms, seeds 1703/1709, same parameter shapes, initialization, steps, data,
query grouping, K/V operations and optimizer:
- feedback: history contains actual emitted latent and own symbol decisions;
- blind: the same history slots and operations receive zero token payloads.
The blind arm is trained separately, not just a test-time intervention.
Also erase history or restrict history to the same row at evaluation of feedback
models; intervention results never choose model/seed/checkpoint.

Train from scratch for 4,000 Adam steps, lr 0.001, batch 32. Same 4,096 original
training graphs (seed 51900), alternate layouts. Use Hungarian set supervision
plus the previously frozen coverage/count auxiliary losses, unchanged weights.
No target order is supervised; assignments occur only during training.

Before fitting freeze two new 256-sample final families:
- triple_right seed 71918: transpose a newly generated A-triple/B-at-most-double
  family into A-at-most-double/B-triple; all nonempty.
- four_right seed 71919: transpose newly generated A-four/B-at-most-double
  inputs into A-at-most-double/B-four.
Recompute all fields and bindings after transposition. Verify actual signatures
and labeled inputs against all previously examined allocation/coverage panels.
Left/right ports are ordered, so this is a directed multiplicity holdout; it is
not a wholly new operator or proof of arbitrary graph-size generalization.

Retain training replay and all four prior semantic panels as diagnostics. Strict
model acceptance requires every non-intervened panel, including old difficult
panels, to be completely correct. Final panels never select training duration,
coefficients or checkpoints. Keep all failed models. Report nonempty/full graph
acceptance, omissions/duplicates, within-round versus cross-round repeats,
count/field errors, actual-history intervention effects, and elapsed time with
read-only verification. Architecture feasibility remains open even if this
bounded task passes: union, ownership, true cross-stage execution, scalability
and strong representation contracts still require their own evidence.
