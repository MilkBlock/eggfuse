# Continuous ridge denoising

Standalone finite-teacher research, not native execution or a GPU measurement.
The transition is frozen from cell-ridge-enhanced/anchored.py (study.py) or
cell-ridge-kernel/study.py (kernel.py). A learned continuous residual denoiser
runs after every transition. No decoded bits, nearest-state lookup or symbolic
repair feed execution.

The denoiser uses all 496 training-state latent vectors as radial feature
centers, concatenated with the current real state. Its dense ridge weights
predict a correction. Training inputs combine clean training vectors, the
frozen transition's predictions on strictly admitted training edges, and eight
Gaussian perturbations per training vector. All labels are training latents.
Validation chooses among fixed noise levels .05/.2, radial widths 8/32, ridge
penalties .01/1, strengths .25/1 and one/two iterations. Test scores do not select
models. Different base representations are separate adaptive experiments.

The 32-dimensional baseline selects noise .05, width32, penalty1, strength1,
two passes: validation whole-trajectory 55.52%, test single-step 83.33%, original
12-step test whole-trajectory 331/624. Independent sequences yield 340/624 and
344/624 at12 steps,358/624 at48 steps. The rare boundary-feedback test still fails.

The 35-dimensional kernel baseline selects noise .05,width32,penalty.01,
strength1,two passes: validation56.66%, test single-step83.48%, original12-step
whole-trajectory343/624. Neither model achieves90% or semantic takeover.

This adds two expensive radial dense projections/readouts per action (528 or
531 features). The centers are weighted together continuously, not selected as
stored successors. Improvements do not establish an efficiency improvement.
The35-dimensional experiment retains FP32 recurrent state, while the32-dimensional
experiment rounds state toFP16. Both denoiser fits use the existing FP16-rounded
ridge coefficient convention. Numerical differences are not hardware tests.

Reproduce with NumPy from cell-real-state requirements, fresh output paths:

```sh
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-attractor/study.py --output out/cell-ridge-attractor/first
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 out/cell-real-state/venv/bin/python benchmarks/cell-ridge-attractor/kernel.py --output out/cell-ridge-attractor/kernel
```

Generate the upstream baseline models first. Saved adapters reference those
local base model paths; they are not self-contained deployment artifacts.
`load_adapter` supplies encode,step,decode to cell-real-evaluation/evaluate.py.
NPZ files stay ignored. Text results include source hashes and frozen evaluation.

## Compact-state follow-up

`compact.py` applies the same fixed denoiser grid to the parent experiment's
17-dimensional boundary-state ridge and uses its nonlinear readout only for
scoring. No readout feeds the recurrence. It selects noise .05,width32,penalty.01,
strength.25,two passes: validation78.73%,test single93.665%,test12-step504/624
(80.769%, kernel.score seed17). This is another improvement but not90%.
Its saved base path is `out/cell-ridge-kernel/compact/model.npz`; freeze this file
while evaluating the denoiser. Reproduce with the same command pattern and
`compact.py --output out/cell-ridge-attractor/compact`. The result source hashes
refer to each separate script; baseline model hashes should be recorded by the
integrating evaluator because the saved denoiser depends on its base NPZ.

## Polynomial and clean-only follow-ups

Two fixed polynomial grids failed to improve the compact radial denoiser.
`polynomial.py` replaces Gaussian features by (1+zC^T/17)^degree, screening
2/3/4 degrees,32 Gaussian perturbations/state,noise .05/.15,penalty .1/10,
strength .25/.5,and one/two passes. Best validation75.81%,test74.52%.
`polynomial32.py` uses full FP32 coefficients,64 perturbations,degree3/4,
noise .01/.05/.15 and the same remaining grid. Best validation76.14%,test76.92%.
The failure is therefore not explained only by coefficient quantization.

`clean.py` excludes transition-error training samples and fits only clean/noisy
training-state pairs (64 perturbations,noise .05/.15,width8/32,penalty .01/1,
strength .25/.5/1,passes1/2). Best validation78.73%,test79.81%. This nearly ties
the radial model but does not beat it. None of these test scores selected a
checkpoint. Each new grid followed the preceding experiment's findings, so the
collection is adaptive research, not a preregistered whole-study benchmark.
Reproduction uses each named script and a matching fresh ignored output path.

## Per-action specialized transition

`specialized.py` uses the frozen model from
`out/cell-ridge-shared/specialized/model.npz`. Its encoder was checked exactly
equal on every finite state to the compact encoder. Transferring the existing
compact denoiser without refitting gave validation77.92% (test not inspected).
Refitting the original32-combination Gaussian grid on specialized training-edge
errors selected noise.05,width32,penalty1,strength.25,two passes: validation76.62%,
test single94.04%,test12-step78.69%. This does not improve the compact model's
continuous recurrence despite higher single-step correctness. Reproduce with
`specialized.py --output out/cell-ridge-attractor/specialized` and a fresh path.

## Staged-supervision and smooth-gate follow-ups

The strongest new base is `cell-ridge-shared/staged.py`, trained with additional
unclosed-apply intermediate supervision. These results must be reported
separately from the original final-state-only training setting. Compact and
staged encoders' columns,mean,basis,scale were checked exactly equal.

`staged.py` repeats the original Gaussian denoiser grid on this frozen staged
base and selects noise.05,width32,penalty.01,strength1,two passes: validation85.06%,
test85.74%. `gated.py` tests the earlier compact base with a smooth final
residual gate; validation79.87%,test81.41%.

The gate has no branch or threshold: for proposal difference delta,
`g = 1-exp(-(norm(delta)^2 / scale^2)^power)`, then `z + g*delta`.
`staged_gated.py` selects scale1.57997 from fixed fractions of training nonzero
change median and fixed absolute scales, power1: validation86.20%,test88.30%.
Its independent12/12/48-step sequences give547/552/556 out of624, and the rare
boundary-feedback case now passes1/1. `staged_wide_gate.py` expands scale to
median times.4/.45/.5/.6/.8, with no further gain.

`staged_shape_gate.py` fixes scale fractions.25/.4/.5 and powers.5/2/3; selected
scale1.57997,power3 gives validation87.175%,test88.94%.
`action_gate.py` instead uses per-action training nonzero-change medians and
fixed union/flag scale factors,26 combinations. Best validation86.85%,test88.62%,
so action-specific scales did not help. `settled_gate.py` freezes the shape gate
and tests2/3/4/6 denoiser passes with strength.5/1. Validation trace ties87.175%;
single-step tie-break chooses3 passes,strength1,test89.10%. None reaches90%.

All these are adaptive sequential experiments, each checkpoint selected only
with validation. Each script reproduces with `--output` pointing to a fresh
ignored directory of the corresponding hyphenated name. Each model depends on
its frozen upstream NPZ paths; preserve those files when evaluating. Increased
passes cost additional dense computation. No GPU efficiency claim is made.
