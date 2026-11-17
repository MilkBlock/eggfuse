# Shared-head / structure-preservation protocol

Frozen before training/evaluation. Keep the old structural experiment and all its
verdicts unchanged. Train three new models (seeds 1703, 1709, 1721) on the exact
same 32,768 cases, Adam 0.002, batch 128, 6,000 steps, final checkpoint only. No
held-out or fresh evaluation selects weights or extends training.

Use the exact previous panels and positions for paired comparisons. Freeze 16
new non-isomorphic F/H plans with generator seed 90417, rejecting every old shape
modulo leaf renaming. Evaluate two fresh 2,048-case panels: new shapes with seen
union/mapping factors; new shapes with the previously held-out union/mapping
factors. They contain no training cases. Baseline checkpoints also run on these
fresh inputs, without fitting. This acceptance remains bounded to eight old
members and one conditional new member.

The model is an intentionally structured neural executor. The 279-float token
contains 64 learned relation probabilities, 72 learned pointer probabilities,
139 protected input floats, three Run flags and one learned activation score.
The previous model used 128 floats. This is not a compression improvement.

One shared 8->32->1 relation MLP sees prior relation, identity, union request,
operator agreement, unary flag, two argument-relation features and a two-hop
relation feature. Eight recurrent neural sweeps per Run 1/2 propose new relations;
max with the old relation preserves existing votes. No exact closure executor is
present in GPU inference. Features and reductions are engineered GPU dataflow,
not learned from raw arbitrary graphs.

One shared 8->32->1 pointer MLP scores source/target pairs using relative slot and
command features. Two learned swap matrices and a learned insertion matrix are
composed with the prior pointer matrix. There are no endpoint-specific learned
output weights or exact target-permutation table. A shared scalar activation MLP
reads the generated equality at the requested LHS pair.

Protected inputs are copied by GPU concatenation, not predicted. Source schedule,
initial identity addressing and static proof-macro binding are fixed operations.
The network generates the equality, pointer and activation state; a claim that
all structure or proof semantics were learned would be false. Each advance reads
only the previous token plus schedule/address metadata. No initial-input re-read
or teacher latent is supplied between Runs. CPU checks saved tokens after all
inference. Invalid outputs are failures; no fallback or repair.

Report exact all-Run acceptance, active-union and required-transfer subsets,
structure retention, first failing Run, CPU/GPU decode agreement, poisoned old
payload reads, direct latent recurrence and learned-head corruption controls.
Read old panels as development diagnostics. The new shapes are one frozen final
acceptance sample, not a proof of unbounded generalization.
