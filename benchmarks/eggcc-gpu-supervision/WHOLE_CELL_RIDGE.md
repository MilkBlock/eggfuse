# Learned completion of the supported Cell body

This changes the GPU model's prediction target, not the executor's storage.
The preceding generated-flow prototype produced consumer frames from a static
plan. That does not make the output responsible for the source Cell's information.
This experiment instead predicts a code for the **entire supported dominator
body**, containing the inherited constructor facts and the new completion.

“Supported body” is deliberately narrower than a complete executable Cell:
mutable functions, scalar computations, visibility, lifecycle and source Run
obligations are not covered by this constructor/equality teacher. Nor is a single
consumer completion a proof of ruleset saturation. Those parts of the intended
runtime remain unfinished; this experiment must not redefine them away.

## Semantic teacher and model

`dominator_completion.py` takes template facts and a Bake entry substitution.
It checks every consumer premise, executes supported immutable constructor/union
effects, computes congruence, and supplies an explicit quotient map from old
ports to target ports. Every source fact must remain in the target under that
map, including facts the consumer did not read. Unsupported effects are marked.
Repeated effects that add neither a fact nor equality are negative novelty cases.
The source template's matched assumptions must already be established; this
teacher does not establish them from a live egraph.

On the full sum-bits recipe's 781 entries it produces 676 supported targets:
635 add information and 41 do not. Another 88 mutable sets and 17 subsumes remain
marked. Across targets, 15,850 source fact occurrences are retained and 991 new
fact occurrences are added. These are offline template occurrences, not committed
runtime mutations or distinct program facts.

The latent code pools dense operation/port-role messages for the whole body.
It is invariant under opaque local renaming and repeated identical facts. Literal
codes retain their literal-specific features. The code is lossy; structural
invariance is not an injectivity or semantic-equivalence proof.

The request code uses compiler operation descriptions and boundary-sharing
patterns, not the target closure or its novelty label. Inputs are the current
Cell code and a candidate completion request. Fixed nonlinear random features
feed a closed-form multi-output ridge solve. Outputs are a residual whole-body
code and an emission score. No backpropagation is used.

On GPU:

```text
current Cell code + request code
    -> dense floating features -> ridge
    -> proposed dominator code + emission decision
    -> next request consumes that predicted code
```

No correct intermediate state is substituted into the device recurrence. Requests
are still supplied by the bounded Bake catalog; discovery of arbitrary runtime
interactions between independently arriving tokens is not implemented.

## Evidence and limitations

Producer families are kept together: IDs modulo five select train (2–4),
validation (1), and test (0). This is a finite template-family experiment on an
already inspected program, **not a fresh workload holdout**. Identity requests
are added as explicit no-output controls.

The test partition has 296 requests, including 140 novel completions. The model
emits 137 proposals, including 2 false emissions, and misses 5 completions.
**These are emission decisions, not correct-completion counts.** Test whole-body
latent RMSE is 0.07968; leaving the state unchanged gives 0.12089.

For the first 64 admissible two-step cases from eight test producer families,
61 emit at the first step and 56 at the second. The second step consumes the
first predicted code on GPU. Final RMSE is 0.18163 versus 0.22131 for leaving the
initial state unchanged. GPU and NumPy execution of the same learned recurrence
agree numerically; no intermediate CPU reads or teacher-state refills occur.

These errors are substantial. There is no exact semantic decoder for the latent
code, so RMSE cannot tell us how many source facts survived a prediction. In
particular **the model does not yet authorize ownership transfer or retiring an
old token**. The exact offline target retains source facts; the student's lossy
prediction has not proved that obligation. No source Run, global saturation,
scalar computation or GPU speedup claim follows from this result.

This is the next correctness gap: obtain a verifiable output interface for the
predicted dominator, then test whether it can actually replace the old token's
inference responsibilities. Storage consolidation is not the gate.

## Reproduction

```sh
python3 benchmarks/eggcc-gpu-supervision/dominator_completion.py PROGRAM TARGETS
$PYTHON benchmarks/eggcc-gpu-supervision/whole_cell_ridge.py PROGRAM TARGETS RESULTS
python3 -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_dominator_completion.py
$PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_whole_cell_ridge.py
```

The tests cover preservation of unused source facts, explicit equality quotient,
no-op novelty, missing premises, duplicate/renaming invariance and independence
from ruleset labels. `whole-cell-ridge-results.json` records the actual Metal run.
Large targets are reproducible artifacts under ignored `out/`, not tracked data.
No native runtime code or executor ownership optimization is included here.
