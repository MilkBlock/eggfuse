# Figure 05: learning to allocate two simultaneous rows

For each original seed 1703/1709 start from the exact frozen Figure 04 single-row
checkpoint. Both make and finish now run 2x4. The greedy executable stays the
same: rows share weights and global inputs, previous generated state is local to
each row, and finish reads the actual generated make tensor. No training arm may
filter outputs, force uniqueness, reorder semantic targets during inference, or
consult the CPU to complete an answer.

Arms frozen before fitting:
- zero: copy the parent, zero updates.
- supervised: 1024 additional Adam updates on unordered set labels using the same
  Figure 04 activation/reference, semantic, and training-only field losses.
- team: on-policy rollouts with a shared terminal graph reward and a centralized
  state-value baseline from a learned low-rank joint-action Q critic.
- counterfactual: same actor, critic, data, reward, sampling and budget as team;
  change only the detached baseline. Hold the other row's actual current action
  fixed and marginalize over the actor's own action law. Exact finite expectation
  includes active/null and both pointer choices even when a null token is emitted.
  These choices influence subsequent history. This is a counterfactual baseline
  for a Monte Carlo return, not an implementation claim about the full COMA paper.

All updated arms train on 1024 x 32 graphs. Cycle the same seven source templates
and same per-seed graph indices. Use actor Adam lr 0.0003 and clip gradient norm
at 1. RL: factorwise epsilon=0.04 uniform exploration with temperature 1; gamma=1
terminal return at both stages, entropy bonus 0.003 per joint row action; average
policy loss over both rows, both Runs and four timesteps. No warm-up, no advantage
normalization, no supervised actor loss. Both RL arms train the same critic on
squared error to the realized terminal return, using Adam lr .001, grad clip 1.
No critic or stochastic action is deployed at greedy evaluation. Retain first
and last sampled batches for independent audit. Comparing supervised to RL also
changes supervision, exploration, and training compute. Only the two RL arms are
a matched credit-assignment intervention.

R = (C1 + 2*C2 + P + E2 - W1 - W2 - 1)/4. C = unique semantically exact bindings
/ source obligations per stage; P = distinct required parents consumed correctly /
required parents; E2 = exact nonempty finish; W = (active outputs - unique exact
bindings)/8. An all-empty trajectory earns -0.25 and a perfect one earns 1.
Training reward uses labels only AFTER a complete device rollout, never as an
action mask or token correction.

Primary evaluation = 768 nonempty graphs (three held-out source rules in two
families), group IDs 1440..1471, four dynamic states x two origin variants.
Frozen input hashes, blind/targeted splits and overlap controls are in the input
manifest. Report exact whole-graph coverage, valid duplicate and same-round
collision counts, wrong parent, omissions, invalid/abstaining behavior, common
parent-ready subsets and complete graphs/second. 32 matched single-graph times
per template/arm/seed, rotated order, raw input upload through synchronized
decoded GPU output/token. Additional frozen 1x8 parent and post-training 1x8
retention are diagnostics. Report training wall time separately; no held-out
selection of coefficients, duration, or checkpoint. No learned stopping rules
or claims of native eggcc speed from this bounded two-Run experiment.

After the primary result, add a training-width sensitivity: continue both single-
row parents for exactly the same 1024 supervised updates at 1x8. Compare each
supervised checkpoint at BOTH 1x8 and 2x4 on the unchanged samples. This tests
whether gains over the zero-update parent can be attributed purely to extra
labelled optimization. It is a secondary analysis on already inspected inputs.
