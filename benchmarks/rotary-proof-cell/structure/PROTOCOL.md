# Frozen structural generalization protocol

Defined before the first structural model is trained. This tests the same
128-dimensional recurrent MLP family as the preceding prototype, with a larger
input/output ABI. The old checkpoint has no fields for these structures and
cannot be evaluated as-is. We train new weights; we do not call the old 20-case
result structural generalization.

- Three initialization seeds: 1703, 1709, 1721. Same dataset for all three.
- 32,768 distinct training examples. Adam 0.002, batch 128, 12,000 steps.
- Use the final fixed-step checkpoint. No held-out evaluation for early stopping,
  architecture tuning, checkpoint selection or extending the training budget.
- Six panels of 2,048 examples each: training replay; unseen combinations of seen
  factors; held-out shape only; held-out union position only; held-out transfer
  mapping only; all three structural factors held out simultaneously.
- Shape split: 8 train, 2 held out. Union split: 10 train unordered endpoint pairs,
  2 held out. Mapping split: 24 train, 4 held out, after deduplicating the full
  resulting permutations of two adjacent swaps plus insertion at port 4.
- Every individual held-out opcode, argument-position feature, union endpoint and
  swap-position feature occurs in training. No whole-shape/union/mapping ID is a
  model input. Disjointness is checked on structure/mapping content, not labels.
- Shape identity removes leaf renaming; ordered constructor arguments remain
  meaningful. This is not a test of arbitrary graph canonicalization.
- Inputs contain four leaves, a plan for four ordered F/H constructors, a union
  request and enable bit, a repeated-variable query, two swap commands and an
  opaque four-bit annotation. Network outputs carry these structural facts too.
- Run 1 builds the plan; Run 2 applies the optional union plus congruence; Run 3
  adds G(query-left) and transfers ownership iff query-left=query-right. Deferred
  work stays pending. Static trusted rule semantics are the same across shapes.
- The network must compose the swap commands; the target permutation and alias
  table are not fed as features. GPU routing uses its decoded alias table.
- Each Run consumes the generated previous latent. CPU teacher is offline only.
  Every inference trajectory finishes before the independent CPU audit begins.
- Exact full-trace acceptance is primary. Report each Run, decoded structural
  field, unauthorized/missed equality, false/missed transfer, alias correctness,
  and cases requiring derived congruence. A low loss or mean bit accuracy is not
  semantic acceptance. Failures stay failures; there is no exact fallback.
- Save all test inputs, generated checkpoints, decoder parameters and source/
  model hashes outside Git. Reports and reproducible source are tracked.
- Semantic failures return exit 1; the experiment still records its complete
  results. This is an expected outcome of the research test, not permission to
  relax the checker or change the split.

Limits: fixed-size synthetic structures and three Runs, manually defined proof
macros, no learned arbitrary matching, no automatic Bake and no performance claim.
