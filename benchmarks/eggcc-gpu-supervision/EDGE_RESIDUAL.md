# Ordered floating edge residual: rejected runtime candidate

This experiment is a standalone MLX GPU prototype on eight synthetic `canon`
rules, not a native Eggcc benchmark or complete multi-stage runtime.

`--edge-residual` adds a zero-initialized linear map from masked, ordered floating
edge features to the existing 128-dimensional token. For this compiled layout it
adds 131,072 f32 weights (524,288 bytes) and 131,072 multiply-adds per candidate.
The existing token encoder and exact matching interface remain frozen; backprop
updates the residual and Eq readout. Default execution is unchanged. No speedup
has been measured.

The bounded two-step domain improves to 4,253/4,258 exact Eq states, with five
false-negative pairs and no false-positive pairs. A previously almost invisible
edge distinction becomes a token difference of about 0.054 rather than 9e-8.
However, independent CPU auditing of a full sealed Run passes only 41/61 synthetic
cases. This candidate is rejected as a runtime replacement. Two-step fitting is
not evidence that generated tokens remain usable at later transitions.

`test_edge_encoding_parity.py` compares the training and GPU edge formulas on 32
identical-source fixtures, including aliases, repeated sources and padding. These
agree. This does not establish that the runtime selects the same semantic owner
or encounters the same source-token distribution as training. Those questions
remain open; neither coverage nor numerical drift is yet an established sole
cause of the regression.

Reproduce with the MLX Python environment, the compiler recipe trace, and the
previous finite combined checkpoint:

```sh
python train_finite_completion.py TRACE PARENT.safetensors RESULT.json --edge-residual --steps 3000
python audit_neural_gpu_rhs.py TRACE RESULT.transition.safetensors AUDIT.json --ruleset canon --include-uncovered-transfers --interface-only --follow --sealed-run-attempts 8 --eq-readout RESULT.eq.safetensors --limit 64 --witness-context-depth 1 --edge-residual
python -m unittest discover -s . -p 'test_edge*.py'
```

Text evidence: `edge-residual-results.json`. Large artifacts are archived outside
Git in `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/edge-residual-v35`.

## Stable identity versus latent invalidation

The current `install` in `device_neural_speculation.py` marks existing rows dirty
when any valid stored root changes after an accepted proposal. This is a
conservative root-change guard, not a numerical latent-error detector. Likewise,
`device_eq_completion.close` invalidates on changed roots. Neither flag establishes
that the stable token identity changed or that a model prediction was wrong.

The added encoding test establishes that class-balanced local encoding is exactly
invariant under representative renaming that preserves its partition. Merging
local classes changes this encoding. Separately, merging with an external Cell
can change cross-Cell edge features while leaving the local partition unchanged.
Thus a local-partition comparison alone cannot authorize arbitrary latent reuse.
The current learned latent can also depend on upstream sources, beyond the local
encoding checked here. No dirty guard has been removed by this experiment.

Rechecked Bake branch `codex/cell-parallel-admission` at `f3321a3a`, containing
`56e28b89`. Its history-ownership report requires actual returned Fact witnesses,
not logical cursor-parent addresses, and retains current Eq/lifetime checks. A
future GPU takeover must compile that dependency scope and distinguish local
state updates from boundary incidence; source-token history alone is not proof
that the present physical owner or latent is valid.
