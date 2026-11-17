# Longer generated-state recurrence

The two-round prototype did not establish repeated execution. The homogeneous
keyed-Cell interface is now given a recursive interpretation: after creating one
edge Cell from A/B, Compose(L,R) is legal when L.next=R.key and returns a new Cell
with L.key, R.next, L.value and R.aux. Parent references remain part of the token
record. Each frontier composes equal-length paths, so path length doubles.
This is an explicit synthetic source-contract extension, not a claim that the
original two-rule program already ran arbitrary rounds or that all egraph rules
are covered. It is not saturation; the requested round count is explicit.

A frozen-weight probe calls the same learned Compose block on its own outputs
for eight rounds. No original source encoding or teacher intermediate state is
available after the first round. CPU reference path following happens afterwards.
All four two-round checkpoints fail cumulatively by rounds 5/6, even on the seen
input distribution. Keep the negative result under results/frozen.

Next experiment, fixed before fitting:

- Keep model architecture and parameters dimensions unchanged.
- Start from each of the four recorded two-round checkpoints.
- Fine-tune all parameters on the original 4,096 short-cycle training graphs only.
- 3,000 Adam steps, learning rate 0.0003, batch 64. Cycle training rollout depths
  2, 3, 4; backpropagate through every generated state, no teacher forcing.
- Use final checkpoint only. Keep both modes and both seeds.
- Old seen/long-cycle/fan-in panels become diagnostics, not final test selection.
- Freeze fresh acceptance before fitting: eight rows x two tokens, 256 graphs,
  generator seed 31817; three rows x four tokens, seed 31818. Each source graph
  is one long chain into a self-loop, with no other incoming edges. Such a map
  is non-bijective and has a tail of N-1, absent from training permutations.
- Evaluate round counts 8 and 12 by running one 12-round trajectory and reporting
  exact per-round and cumulative results. Do not restart from a correct reference
  at round 4 or 8.

The network still has fixed source-anchor output placement, a finite key alphabet
and no union or ownership coordination. The full architecture goal stays open.
