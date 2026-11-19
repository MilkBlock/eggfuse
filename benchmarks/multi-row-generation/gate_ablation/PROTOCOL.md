# Figure 06: learned per-round GPU row admission

Keep the best tested two-row supervised actors from Fig. 05 (both prescribed
seeds 1703/1709, final checkpoints). Compare their published frozen weights.
The gate operates per graph, Run, row and time before the expensive actor body.
Both rows can close; future rounds still execute and can reopen a row. Packed
addresses of all 8 slots remain fixed. A closed slot and its next recurrent
history contain zeros, distinct from an ordinary open actor slot choosing null.
No CPU reads the decisions to dispatch a reduced set of actors.

Use 2x4 in both Runs, exact same actor and trained template encoder, and two
separate trainable 713-parameter gates, one per Run, shared across positions.
Freeze ALL actor parameters. The primary fixed-width reference directly runs
the Figure 05 supervised actor without a gating module. Also run the gated
code at all-open, all-closed and the following learned choices. Each learned
policy is evaluated with dense-compute/late mask and with actual device
early-return; compare identical decisions and generated witnesses. As a control
for context dependence, run a static per-stage slot mask matched on the
calibration panel's *mean* open budget. Ordinary gate-open null outputs do not
count as closed. Training/validation cost and fixed-template preparation are
measured separately from production inference.

Gate training: initialize readout weights to zero and bias +1 (all open).
Gate Adam lr 0.002, batch 32, 1024 updates, grad clip 1. From identical raw
training graphs (Fig. 20 7168, balanced by template, paired sample stream), pick
one of the 16 gate sites uniformly per graph. Generate TWO complete trajectories,
force the sampled decision open versus closed and let all earlier/later slots
use the current learned gate at threshold .5. Neither branch receives source
targets. Afterwards compute U = R_figure05 - price*(total_open_slots/16).
Compare gate_p0 (price=0) and gate_p25 (price=.25), same loss, budgets and
initialization. Train first branch's pre-action gate logit on sign(U_open-U_closed),
weight BCE by abs(delta)+1/64; ties prefer open. Only the gates take gradients.
Every update costs 64 complete source graph trajectories; total 65536 per fit.
This supervised counterfactual gate fit uses training labels to score rollout
utility; this is not policy-gradient RL. Save first and last actual branch
outputs, slot indices, rewards and utility for independent replay.

Calibrate before reading held-out results: 7 training templates in 5 families, fresh group IDs 2304..2311, each
8 states/variants. Test thresholds .05,.15,.30,.50,.70,.85,.95 plus all open.
Select the fewest open slots among thresholds with at least the ungated
complete nonempty count on the entire calibration set; ties prefer higher
coverage then lower threshold. The all-open fallback qualifies. Report .5
separately, and disclose if calibration gains do not transfer. Fixed positional
control uses actual per-stage open frequencies of the calibrated policy;
open k most frequently used slots, k is the rounded mean open count for that
stage. No labels or test statistics select the static mask or threshold.

Held-out groups 2160..2191, exact overlap checks against training and all past
evaluations; 3 previously held rules (134,135,143 in 2 structural families), 768 new nonempty graphs. Score complete/ready coverage, early or
illegal decisions, repeats, misses, gate reopenings, source obligations vs
parents-ready obligations, realized live-row histograms, and correct graphs/s.
No stopped row can discard earlier witnesses or claim saturation. Timed
batch=1 MPS plus Metal, matched 32 selected inputs per rule, equal warmup,
rotating order, raw inputs to synchronized complete stage outputs and Pair
token. Primary compute-path contrast: same actor+gates+mask+backend, only
dense versus GPU predication changes. Report total time versus the original
ungated PyTorch implementation as a separate system comparison: kernel fusion
changes that comparison too. No estimate of saved FLOPs is a measured speedup.
