# Coverage supervision, unchanged inference architecture

Freeze before fitting. Compare the previous four final SetGenerator checkpoints
(joint/within-row, seeds 1703/1709) to four newly trained paired models. Same
initialization seeds, 4,096 training graphs (seed 51900), batches, layouts, Adam
0.001, 4,000 steps and final-checkpoint selection. The original network and its
inference code are imported unchanged. No allocation, repair or post-filter is
added at inference. The previous final checkpoints remain controls; evaluate all
four on the new panels without tuning or retraining them.

Only change the training loss. In addition to the existing Hungarian-aligned
active/pointer/field cross-entropies, form a soft joint claim for output slot s:

  C[i,j] = sum_s P_s(active) P_s(left=i) P_s(right=j).

Y is the offline target binding set as a 0/1 matrix. Add

  mean_graph sum_ij (C-Y)^2 / max(1, target_count)
    + 0.25 * mean_graph (sum_s P_s(active)-target_count)^2 / 8.

These are temporary TRAINING loss tensors; they are not per-instance graph state,
not model inputs, and not an exact matcher used to fill neural outputs. Hungarian
assignment remains CPU training-only. Equal soft coverage does not guarantee
correct hard decoding: two half-active duplicate claims can match total mass.
Keep that counterexample in tests and report soft versus hard diagnostics.

Final acceptance is frozen before fitting, 256 inputs each:
- double_triple: seed 61918, both A and B have a key repeated three times,
  at most eight legal obligations. Feasible counts 0/1/3/6, five unlabeled
  multiplicity shapes. The nine-match shared-triple case exceeds this existing
  task capacity and is explicitly outside this panel, not silently truncated.
- four_left: seed 61919, all four A share one key, B multiplicity at most two,
  feasible counts 0/4/8. These shapes are absent from both previous train and
  previously inspected multiplicity panels.

Verify shape disjointness against actual old arrays before fitting. The old IID
and A-triple panels become diagnostics. Also evaluate 256 training-replay inputs
separately to expose underfitting. Evaluate both layouts 4x2 and 2x4 on identical
inputs; layouts are not additional independent graphs. Fresh panel results never
select checkpoints, coefficients, seed or training duration.

Keep failed models. Report full graph and nonempty graph acceptance, missing and
repeated bindings, wrong fields, count error, soft coverage error and active
entropy. Verify source hashes and saved outputs with independent CPU replay.
Speed claims require the same completeness; one-stage success would still not
establish cross-stage recurrence, union/ownership or full egraph inference.
