# Independent audit of the dense real-state experiment

Read-only audit of `benchmarks/cell-real-state/study.py`. No split, teacher,
model, or runtime was changed. This is a finite-model diagnostic, not native
egglog semantic acceptance.

```sh
OPENBLAS_NUM_THREADS=1 out/cell-real-state/venv/bin/python benchmarks/cell-real-audit/audit.py
```

The source checksum and reproducible counts are in `results.json`.

Findings:

- No clear parameter-alias or BPTT equation bug was found. Finite differences
  of the copied three-step equations, including observation loss, check every
  parameter of a small float64 network. This does not validate optimization
  quality or quantify training-versus-FP16 inference differences.
- Training disallows both held sources and held destinations. In addition to
  held sources, this excludes 2,208 edges from training sources. The fully
  boundary-merged state with flags=2 belongs to validation and receives 333
  transitions across the complete domain; it never appears as a training
  target. This is a legitimate strong generalization contract, but harder
  than merely holding out input states. Do not alter it to improve scores.
- Each union action has 342–385 training edges, of which 228–248 change state.
  The two rule-enable actions have 392/395 edges but only 149/146 changes.
  Thus ordinary supervised edge training is not dominated by union no-ops;
  multi-step trajectories will become more concentrated near closed states.
- Of 203 initial boundary partitions, 116 change some equality when both
  rule groups are enabled, but only 5 change boundary equality. The teacher
  has real nontrivial feedback, but this case is rare and needs a separate
  slice in evaluation before broad claims about repair generalization.
- The 645-dimensional diagnostic concerns joint invariance with linear
  observables and action operators over the FULL finite state domain. It is
  not a bound for nonlinear latent models or held-out learning. The existing
  wording already distinguishes this.

Recommended diagnostics under the unchanged split:

1. Report fit on the exact admitted training edges, alongside validation/test.
   This distinguishes underfitting from held-target extrapolation.
2. Separate held-source transitions to training versus held destination states,
   and the five boundary-feedback partitions.
3. Compare the same frozen checkpoint in FP32 and FP16 to isolate numerical
   rollout drift; do not compare different trained models for this question.
4. Measure free rollout against teacher-forced inputs with the same event
   sequences, while keeping teacher forcing diagnostic-only.
5. Validate any new end-to-end model with fresh complete sequences, not only
   terminal accuracy, which is inflated by late convergence to merged states.

## Rule-enable feedback slice

`feedback.py` independently enumerates action 15/16 transitions that alter the
boundary partition. `feedback.json` records every example and full before/after
partitions. Counts by SOURCE split are train=5, validation=4, test=1. All five
training examples have training destinations, so all are admitted. Only one
training example uses action 15; the other four use action 16.

The sole test transition is state **258**, action **15**, target **1** (a training
state). It is not an unseen-target extrapolation case. Name ports 0..5 as
`a,b,c,d,e,f`. Initially:

```
{a,c,f}, {b,d,e}; flags=2
```

Action 15 enables the first rule group, making flags=3. The second group was
already enabled. Its derivation is:

1. Initially `c=f`, so the newly enabled Pair(c,f) condition merges
   `F(c)` (node 8) with `G(b,f)` (node 11).
2. Initially `a=c`, so congruence already gives `F(a)=F(c)` (nodes 6 and 8).
   Therefore `F(a)=G(b,f)` becomes true.
3. Initially `b=d`. Together with step 2, the already enabled feedback rule
   merges `c=e`, joining the two boundary classes.
4. All six boundary ports become equal. Constructor congruence and the other
   positive rules finish their closure; the final state is state 1.

There is also a simultaneous newly enabled `b=e` condition merging F(b) with
G(a,e), but it is not needed for the short causal explanation above.

Thus the held test contains only one direct rule-enable feedback example.
Overall accuracy improvements cannot establish learned repair behavior unless
this slice is reported separately. This audit does not itself score either new
model; it records the teacher examples for their evaluator.
