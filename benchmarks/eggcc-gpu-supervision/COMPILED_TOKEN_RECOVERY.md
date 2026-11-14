# Separating token recoverability from completion correctness

The synthetic-only head's GCD feedback run had 20 disagreements between its
selected Eq states and the historical learned decoder's token interpretation.
That count does not distinguish lost token information from insufficient decoder
coverage. This experiment audits the distinction without fitting on real data.

`audit_token_state_recovery.py CAPTURE OUTPUT` compiles all bounded type-compatible
states from each template (2, 15, 15). For each captured token it synthesizes the
candidate representations using that instance's actual scalar codes, computes
squared floating distances and chooses the nearest candidate. Labels and recorded
producer choices are not inputs to recovery. The latter are compared afterward;
independent CPU labels, when present, assess the recovered state's semantics.

The candidate-state enumeration is Bake-time work; this diagnostic's dynamic
candidate synthesis, distances and argmin run in NumPy and compiled MLX batches.
It is not installed as runtime inference, and its temporary candidate tensor is
not a demonstrated efficient replacement for ridge. It does not recover stable
IDs or replace exact connection/ownership metadata. Near ties or large residuals
fail the recovery audit rather than silently accepting a nearest guess.

All 41 actual GCD feedback tokens recover their producer's state, with maximum
squared residual 5.08e-14 and minimum squared-distance gap 0.08448. CPU/GPU choices
agree. Thus on these samples the old learned decoder's disagreements are not
representation collisions. The independent recovered-state semantic audit is
still only 20/41, with 45 false and 11 missed quotient Eq pairs. This does not
repair wrong predictions, establish a speedup or authorize learned unions.

The test additionally synthesizes every baked state at three scalar settings
(-1, 0, 7), 96 cases total, and checks GPU recovery and rejection of badly shifted
vectors through the residual. This bounded coverage is not a proof for arbitrary
scalars, templates, mixtures or evolving external equivalence relations.

Next model work should address the distribution of predicted-source inputs using
synthetic-only rollouts. Re-training the old decoder on real GCD errors would
both violate the training policy and fail to solve wrong completion choices.
The full multistage runtime and applied CPU correction remain open.
