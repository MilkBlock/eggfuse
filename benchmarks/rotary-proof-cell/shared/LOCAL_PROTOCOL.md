# Stabilizing fitting with offline primitive-rule supervision

The initial end-to-end-only models are preserved at commit f7687c01. One seed
passed all panels while two failed training-domain tasks. This follow-up changes
the training objective, not the generated-state ABI, inference architecture,
source checker or output acceptance. It is not an architecture-only comparison.

Use the same 32,768 training examples, seeds 1703/1709/1721, Adam 0.002, batch 128,
6,000 steps and final checkpoint. Add explicit OFFLINE local labels for:

- all 256 binary feature configurations of the declared relation primitive:
  prior relation OR reflexivity OR requested union OR a two-hop witness OR matching
  constructors with equal required arguments. Negative examples receive weight 16.
- the seven single adjacent swaps already present in the training corpus, and
  insertion at slot 4; no held-out composed mapping is a local target.
- activation of a query with input equality score 0 or 1.

These are manually specified labels from the example's rule semantics, not labels
extracted by an implemented Bake compiler. The runtime imports none of them. It
still generates all equality, pointer and activation scores using learned heads.
GPU inference has no exact closure or target-permutation fallback. Report both
the first end-to-end-only runs and this objective, not only the better result.

The first 16 fresh shapes have now been inspected and are development diagnostics.
Before this new training, freeze another 16 shapes using seed 91917, excluding all
10 old shapes and all 16 inspected shapes modulo leaf renaming. Evaluate distinct
2,048-case final-shape and final-joint panels, generated with seeds 92917/92918.
No final-panel result selects checkpoints or extends fitting. Every original
panel is retained unchanged. Failure remains failure.
