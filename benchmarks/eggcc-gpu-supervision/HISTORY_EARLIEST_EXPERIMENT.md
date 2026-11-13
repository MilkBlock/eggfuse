# Earliest observed Cell context: actual numerical experiment

This is a standalone observed-route GPU prototype, not autonomous Eggfuse or
native egglog execution. No backpropagation. Successful matches, exact connection
identities and Run boundaries are supplied by audited CPU captures.

`class-history-earliest` extends the fallback-only history model: a consumer with
any adjacent source keeps its existing routes; other consumers use all complete
constructor observations from the **first** prior Run for each typed identity.
Sources are recorded after reading that Run's inputs, so same-Run results cannot
become inputs. Existing current-input interface encoding is preserved. This is
an experimental context choice, not a constructor ownership or lifetime proof.

## Fitting and evaluation

Same expanded training corpus (10 workloads), original token-validation corpus
(euler), four role channels, fixed random features and ridge candidates as the
latest-source baseline. Model selection uses validation only. The separate Eq
readout is fitted from training oracle states and selected using the existing
five-workload validation corpus. Numeric threshold instability disqualifies a
candidate on validation; test remains strict. No thresholds were tuned.

On dot-product, 5,553 complete states are evaluated, including 5,454 with Eq
queries. All 382 incomplete states remain excluded from semantic metrics. No
incomplete CPU boundary token is consumed by either model's continuation edges.

| Measurement | Latest fallback | Earliest fallback |
|---|---:|---:|
| Dependency layers | 91 | 45 |
| Actual context edges | 50,424 | 43,377 |
| Predicted-input token RMSE | 0.037059 | 0.036672 |
| MSE-selected exact partitions | 4,242 | 4,231 |
| MSE-selected false pair merges | 423 | 460 |
| MSE-selected missed equalities | 2,019 | 2,043 |
| Partition-selected exact partitions | 4,427 | 4,395 |
| Partition-selected false pair merges | 836 | 798 |
| Partition-selected missed equalities | 1,824 | 1,833 |

Both select alpha 100 under MSE and alpha 0.1 under partition accuracy. Results
show a tradeoff, not an accuracy improvement. Lower token RMSE again does not
imply better equality decisions. The cheaper adjacent-only class-interface
comparison previously gave 4,415 exact partitions / 883 false pairs under the
partition policy. No history variant is adopted as a semantic replacement.

## Paired replay cost

`compare_history_replay.py` checks model/trace fingerprints and identical target
populations, uses the existing two-group packed executor, then alternates model
order for six warm executions in one process. GPU evaluation is synchronized;
final CPU transfer is outside warm timing. CPU/GPU numeric comparisons passed
for both models. This is a narrow repeatable comparison, not an end-to-end benchmark.

| Cost | Latest | Earliest |
|---|---:|---:|
| Warm GPU median | 9.720 ms | 5.732 ms |
| CPU NumPy numerical execution, one call | 22.576 ms | 19.702 ms |
| CPU context encoding | 974.946 ms | 887.487 ms |
| CPU plan preparation | 54.332 ms | 49.441 ms |
| GPU setup | 16.850 ms | 13.403 ms |
| Cold GPU execution | 41.893 ms | 16.503 ms |
| Padded coefficient bytes | 39,885,120 | 40,262,112 |
| Padded edges | 75,540 | 76,254 |

The prepared replay median ratio is 1.696x. This is **not** an application speedup:
input preparation dominates, semantic Eq readout/audit is additional, and the
models have different accuracy. Even though real edges decreased, larger layer
batches changed padding, so allocated coefficients increased slightly.

## Decision

Keep earliest history experimental. The evidence supports separating stable
source context from newly observed changes instead of always replacing it with
a newer whole Cell. It does not support suppressing updates solely because a
constructor identity/root repeats. Next, inspect validation failures that differ
between source policies to identify what additional context a compact update
must retain. Any proposed update must avoid recreating a full per-node consumer
index, preserve numerical validation, and charge preparation and transfer costs.

## Reproduction

Artifacts are under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee` (ROOT):

1. Run `multi_entry_ridge.py` with training `rhs-training-expanded-20261114/manifest.json`,
   validation `rhs-validation-20261114/manifest.json`, test
   `observed-corpus-20261113/rhs-dot-product.json`, output
   `class-history-earliest.npz` / `.json`, `--channels 4 --encoding class-history-earliest`
   and `--corpus-manifest ROOT/observed-corpus-20261113/manifest.json`.
2. Run `select_eq_readout.py` with the same training/test/model, expanded validation
   `rhs-validation-expanded-20261114/manifest.json`, output weights/report/marks,
   and `--reject-unstable-candidates`.
3. Run `compare_history_replay.py TRACE ROOT/class-history-fallback.npz
   ROOT/class-history-earliest.npz OUTPUT.json`. Each model's adjacent `.json`
   report is required. Use the existing NumPy/MLX virtual environment.

Committed text reports preserve model, corpus and trace hashes. Binary models
and raw captures stay on the external disk. 32 focused tests passed covering
history selection, causal dependencies, encoding, routing and Eq readout.
