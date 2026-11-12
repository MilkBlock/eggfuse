# Independent evaluation of dense real Cell states

These are standalone NumPy experiments on the unchanged finite teacher in
`../cell-real-state`. They do not execute egglog, commit mutations, or measure
GPU speed. No model passes even this finite-domain correctness gate.

## Representation and execution

Both new candidates carry 32 signed, fractional latent coordinates. Symbolic
observations enter an encoder once. Subsequent events consume the preceding
predicted real state directly; decoded observations are used only for scoring.
There is no symbolic repair, nearest-state lookup, or teacher correction in
the autonomous recurrence.

- Joint model: learned encoder; dense 16-dimensional event code concatenated
  with state; 128-unit tanh layer; residual projection and tanh next state.
  Encoder, transition and readout are trained together through three steps.
- Algebra-augmented ridge: train-only PCA encoder; action-selected dense
  quadratic ridge residual, followed by coordinate clipping. Training uses
  the model's predicted intermediate states for repetition and composition.
  The bounds depend only on training states, not on a symbolic-state lookup.

The latter expands 32 coordinates into 560 linear/quadratic features and uses
17 weight banks (305,184 transition weights and biases). Its small persistent
state does not imply a cheap transition. Grouping by event, temporary feature
traffic and end-to-end encoding/readout still need accounting before a GPU
efficiency claim. The joint model has 12,902 trained parameters but lower
correctness. Neither is merely a Boolean adjacency matrix cast to floating
point; both remain approximate models of the finite teacher.

## Frozen-checkpoint results

Checkpoints were selected by each training experiment's validation split.
This evaluator performs no training or model selection. It checks 156 held-out
initial states, all 2,652 single events and all 45,084 ordered event pairs.
An exact row must match all 155 observations; nonfinite predictions fail.

| Model | Single event | Two events | New 12-step seed A | New 12-step seed B | New 48-step seed |
|---|---:|---:|---:|---:|---:|
| Prior fixed-encoder tanh | 643/2652 | 2953/45084 | 0/624 | 0/624 | 0/624 |
| Joint model, FP32 | 1694/2652 | 24293/45084 | 54/624 | 50/624 | 0/624 |
| Augmented ridge, FP16 rounding | 2040/2652 | 29775/45084 | 173/624 | 183/624 | 155/624 |

Sequence counts require every predicted step to be correct, not just the final
state. Seeds are 20261112, 104729 and 65537; they did not select checkpoints.
Each trajectory forces both rule-enable events and a repeated event. Two-event
and repetition checks assess autonomous composition without decoding feedback.

Removing activation rounding from the ridge model (same quantized weights)
gives 154/624 rather than 155/624 on 48 steps. Rounding the joint model's weights,
event codes, hidden activations and states gives the same sequence counts and
24,288/45,084 two-event successes. These are CPU numerical simulations with
FP32 matrix accumulation, not actual hardware FP16 validation. The present
failure cannot plausibly be explained solely by half-precision rounding.

Teacher-forced diagnostic inputs give the ridge model 293/624, 309/624 and
309/624 all-step successes on the same sequences, compared with autonomous
173, 183 and 155. This separate diagnostic never feeds the autonomous run;
it shows both accumulated state error and remaining one-step errors.

## What the improvement does and does not establish

The fixed four-arm ablation in `../cell-real-algebra/ablation-results.json`
gives original ridge 0/624 without clipping and 4/624 with clipping; augmented
ridge gives 0/624 without clipping and 180/624 with clipping on its original
12-step test seed. The improvement depends on their interaction. It is not
evidence that algebraic training alone solves recurrence.

Both new candidates fail the sole held-out rule-enable event that causes a
boundary merge (0/1). Its target is a training state. Starting with classes
{a,c,f} and {b,d,e}, the new rule establishes a constructor equality, which
enables an already active rule to merge c=e, then closes congruence. See
`../cell-real-audit/feedback.json` for the full derivation and split counts.
This crucial failure must remain visible alongside aggregate improvements.

The teacher has only six boundary ports, twelve fixed constructors and two
positive rule groups. It excludes fresh-term growth, deletion, mutable reads
and general ordered effects. All-event commutativity and idempotence hold for
this teacher, not for arbitrary egglog actions. All `finite_checks_pass` flags
are false; native semantic acceptance and runtime takeover are also false.

Next research priority is preserving the evidence for conditional feedback
under real-valued composition, with this failure slice retained. Test a
structured continuous transition against the frozen models before increasing
width or moving an incorrect model to GPU. Any data enrichment needs a
separately declared contract and unseen feedback cases; never move this test
case into training and report the resulting score as generalization.

## Reproduction

Use NumPy from `../cell-real-state/requirements.txt`. Generate models with the
commands in `../cell-real-joint/README.md` and `../cell-real-algebra/README.md`.
The prior model comes from `../cell-real-state`. For example:

```sh
OPENBLAS_NUM_THREADS=1 VECLIB_MAXIMUM_THREADS=2 PYTHONDONTWRITEBYTECODE=1 \
  out/cell-real-state/venv/bin/python benchmarks/cell-real-evaluation/evaluate.py \
  --adapter benchmarks/cell-real-algebra/study.py \
  --weights out/cell-real-algebra/reproduced/model.npz --precision fp16 \
  --output out/cell-real-evaluation/algebra-half.json
```

Use `joint_adapter.py` with `fp32` or `fp16activations`, or `prior_adapter.py`
without a precision argument, for the other models. `results.json` collects
the five independent runs, including hashes of source, corpus and weights.
Binary models stay in ignored output directories. The evaluator exits normally
when it finishes, including when models fail: consumers must inspect
`finite_checks_pass`. This is unrelated to the native `choice_diagnosis.py`
acceptance contract, which is unchanged.
