# Own-symbol token interface versus unconstrained continuous recurrence

The two-round frozen models and the 2–4 round continuous fine-tuning are preserved
as negative depth evidence. Four-round training still reaches zero cumulative
correct graphs by round 11/12, including its source training domain. We will not
call the earlier two-round result sustained inference.

This controlled experiment changes the emitted token representation. A continuous
model emits its raw 64-float state. A typed model emits the one-hot encoding of
its OWN four predicted interface symbols (40 floats) plus 24 zero padding floats.
The same neural pointer/field decoder is still responsible for every decision.
The tokenizer receives no source facts, target values or teacher states and cannot
correct a wrong symbol. A straight-through surrogate supplies gradients; forward
execution uses exact predicted symbols. The metadata parent references remain.
This is a typed/generated-symbol baseline, not an unconstrained continuous latent
or a claim that a vocabulary of 16 keys represents arbitrary egraph identities.

Before fitting, freeze these conditions:

- Both representations start from scratch with seeds 1703 and 1709. Same parameter
  dimensions and within-row query mixing, with full prior-memory access.
- Same 4,096 training graphs: 512 short-cycle and 512 random functional graphs for
  each layout (2,3),(3,2),(2,4),(4,2). Training sizes remain 6/8.
- Same 6,000 Adam steps at 0.001, batch 64; training depths cycle 2,3,4.
- Final checkpoint only. No teacher intermediate states enter the next step.
- Fresh acceptance has 256 graphs per panel: (8,2) two long tails, seed 41817;
  (3,4) a tail into a 2-cycle, seed 41818. Check exact unlabeled functional-graph
  signatures against training and previously inspected graph panels before fitting.
- Roll out 12 generated rounds without resets; report per-round and cumulative
  exact acceptance, including round 8 and 12. Wrong ancestry is never forgiven
  because a later endpoint happens to look correct.

The canonical format guarantees only identical interface codes for identical
PREDICTED symbol tuples. It does not establish correct symbols, whole-graph
canonicalization, arbitrary keys, union, free output allocation or ownership.
Compression is not the goal. Do not compare this as an architecture-only ablation
against the earlier different-data fine-tuning; use the matched scratch controls.
