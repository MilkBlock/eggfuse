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

## Variable-capacity prerequisite audit

`capacity.py` inspects all 551 saved cases and 3,548 actual snapshots. It is a
materialized-state reference, **not** a proposed one-node/one-token encoding.
It keeps repeated scalar occurrences distinct: equal values do not prove aliasing.
Eq references remain separate exact identities and are not floating features.
Only integer scalar payloads in the exact f32 domain are accepted by this audit.

Across 2,997 transitions there are 1,323 increases in scalar occurrences, but
only 249 transitions introduce previously unseen numeric values within that
execution. Neither count measures independent information or entropy. Most
structural growth cannot simply be billed as new dynamic scalar information.

| Scalar block width | Observed blocks per snapshot | Block growth events | Padding fraction |
|---:|---:|---:|---:|
| 8 | 1–4 | 831 | 19.61% |
| 16 | 1–2 | 320 | 36.43% |
| 32 | 1 | 0 | 54.58% |

These counts exclude structure, references, validity metadata and learned hidden
state. The corpus has 119,050 reference occurrences across snapshots; silently
omitting their storage/resolution would hide a major part of the representation.
The 32-slot result demonstrates that this corpus is too small to establish
scalable scalar-token growth. Reducing width merely to obtain growth is not a
scalability result. This audit does not implement dynamic GPU token storage.

```
python capacity.py --runtime SAVED_RUNTIME_NATIVE.json \
  --width 32 --output out/token-rollout/capacity-full.json
```

`capacity-results.json` keeps summaries at widths 8, 16 and 32; full per-snapshot
records are reproducible output, not committed duplicates of the dataset.
Next dataset work must introduce genuinely larger interacting multi-entry
regions, preserve short-case execution limits, and separately account for
compiled structure versus necessary dynamic state. A variable-capacity runtime
must not use future teacher snapshots to allocate or route its instances.
