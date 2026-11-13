# No-backprop token continuation: first falsification test

Standalone numerical diagnostic, not an integrated GPU runtime. The goal is to
check whether ridge outputs can feed subsequent stages without graph decoding,
teacher substitution or backpropagation. It does not establish correct effects,
CPU residual completion, token sufficiency or end-to-end acceleration.

The saved actual five-rule Cell executions supply initial graphs and every Run
boundary. The existing 272/95/102 entry split is retained. Initial and teacher
states use the prior fixed 105-dimensional structural encoder. This encoder is
recursive CPU work, not the proposed fixed shared-slot GPU entry interface.
The transition uses fixed random tanh features (256 dimensions) plus the token,
and ridge fits a residual. Three regularizers are selected by validation-only
8-step rollout error; test results do not select weights or stopping depth.
Metal executes one compiled eight-step expression; intermediate predicted tokens
stay on GPU. Only initial input and final output cross the host boundary.

Results in results.json:

- 1,498 training transitions and 595 test transitions.
- Single-step standardized MSE 0.0431, versus 0.3422 for unchanged tokens.
- Exit-only nearest known completion diagnostic: 48/102 at step 1, 83/102 at
  step 2, 86/102 at step 4, then **80/102 at step 8**. Step 4 is descriptive,
  not a newly selected test-optimal stopping policy.
- GPU and CPU eight-step outputs pass numerical closeness checks; largest
  absolute deviation approximately 0.000107. Both diagnose 80/102 completions.
- Exact final teacher tokens distinguish all 102 endpoints in the training
  completion catalog. This is a representation sanity check, not rollout success.
- No contradictory next graph for identical graph/ruleset was observed here.
  That does not prove watermark/delta can be omitted for general execution.
- **450/595 test input states occur in training trajectories**. Entry splitting
  does not provide transition-disjoint evaluation. Unseen-state error/count are
  recorded separately. All test completion classes are known in training.

The result supports feasibility of fixed GPU token chaining without gradient
descent, but contradicts any claim that this particular representation/model
already gives stable exact completion. Continued evolution drifts. Nearest-label
recognition neither proves derivability nor supplies precise output parameters.
No CPU work is removed. Runtime/semantic acceptance has not been claimed and
no CPU kernel was changed; the relevant check is numerical rollout equivalence.

## Reproduction

Use Python with NumPy and MLX on Metal. `--reference-dir` contains the unchanged
`dataset.py` and `train.py` from commit `a24876d6`, under
`benchmarks/cell-multi-entry-ridge`. Both dependency hashes and dataset hashes
are recorded. They can be extracted into an ignored output directory with
`git show a24876d6:benchmarks/cell-multi-entry-ridge/dataset.py` and the analogous
command for `train.py`; no checkout or branch merge is required.

```
python run.py --reference-dir REFERENCE_DIR \
  --runtime SAVED_RUNTIME_NATIVE.json --corpus SAVED_CORPUS.json \
  --output out/token-rollout/results.json
```

These saved artifacts are the earlier real multi-entry corpus, not newly
synthesized transitions. Regenerating them requires the collectors at the cited
commit. Binary datasets/weights and Python caches are not committed.

Next requirements remain: transition-disjoint evaluation; fixed-point stability;
comparison with direct-to-completion prediction; exact boundary payload and
validated partial acceptance; real CPU residual work and full cost accounting.
The goal is still active, not satisfied by this diagnostic.
