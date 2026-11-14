# Synthetic-only Cell training

This implements the first rule-derived synthetic input path, not full Eggcc or
learned equality authority. No real Run bindings, rows, constants or labels are
sampled. `synthetic-context-recipe.json` contains compiler rule definitions and
constructor schemas for the existing three-rule context family (original rule
IDs 283, 290, 293, local IDs 0, 1, 2). Definitions were extracted from the compiler
recipe; the snapshot and execution history are not part of this fixture.

## What actually executes

`synthetic_cell_inputs.py` composes four randomly selected query fragments.
Query slots are typed; a new Eq slot either allocates an identity or reuses a
same-sort identity with probability .35. i64 values are drawn from a fixed,
program-independent small set. Repeated query slots remain shared. Unsupported
primitives, literals and scalar sorts fail explicitly. Initial constructor key
collisions are closed before exporting the canonical visible seed.

This is a rule-valid open local egraph. It is not proven reachable from an Eggcc
source program, and it need not be acyclic. Whole-program invariants remain an
important distribution question.

The GPU runner imports these seeds through the existing Cell importer, then
executes query completion, construction, union, congruence and ownership transfer
until the selected family saturates. It retains the same per-Run full-graph,
complete-match enumeration, lowering and final-graph audits as real snapshots.
Synthetic input mode verifies hashes and replays seed generation, rather than
claiming a native Run audit. Reports and capture sidecars must have different
paths; the runner now rejects collisions before execution.

`label_composed_witnesses.py --synthetic-input` labels the actual accepted GPU
witnesses against independent original-rule CPU saturation. Labels are computed
after execution. Dynamic current inputs, generated-source tokens, actual owner
witnesses and boundary features are captured by the existing path. Stable IDs
remain connectivity, never float embeddings. The corpus positional argument is
unused in this explicit mode (pass `/dev/null`).

## Results and limitations

Seeds 20261120 through 20261131, four fragments each: 11 reached the oracle fixed
point; seed 20261123 exhausted the 64-Run budget and remains explicitly rejected.
This is not proof of divergence. Its labels are not accepted as completed states.
All 11 accepted inputs passed actual GPU audits, producing 94 samples, 91 after
exact input/target deduplication within each input. Whole-state coverage is 2/2,
5/15 and 5/15 for the three templates. These counts are not exhaustive reachability.

The first three interaction-heavy inputs gave GCD 16/41 and LCM 33/99 exact
completion states. Including all 11 completed random inputs gave 21/41 and 45/99.
Direct-source results are 14/26 and 35/78; generated-source results 7/15 and 10/21.
False Eq merges remain numerous (98 and 207 expanded pair errors). This candidate
is not promoted. The random generator's sharing distribution, missing negative
entry coverage and limited neighborhoods need controlled experiments; merely
adding more samples from the same distribution is not established as a remedy.

All new head coefficients were fitted from synthetic labels only, by closed-form
ridge with alpha 10; no backpropagation. Existing fixed random feature weights are
reused. Historical learned predictor coefficients appear only in baseline
comparison, and the historical decoder only in a representation audit: neither
fits or selects the new state head. The new head is evaluated with actual MLX GPU
matrix operations, maximum score discrepancy 1.61e-6 and token discrepancy 1.20e-7.
These are offline exact-source readout results, not predicted-token closed-loop
accuracy or a speedup. Exact GPU generation/audits above are a separate result.

The trainer defaults to rejecting real-Run training. The explicit
`--allow-historical-real-training` switch exists only to reproduce prior reports.
GCD/LCM remain development evaluations, not untouched test data. Future evaluation
needs new real programs. Current input hashes are not graph-isomorphism canonical
keys, so different seeds must not be claimed independent structural holdouts.

## Reproduction

Use the local MLX Python environment. Large NPZ captures stay on the artifact disk.

```
python synthetic_cell_inputs.py synthetic-context-recipe.json ARTIFACTS \
  --rules 0,1,2 --seed 20261120 --count 12 --fragments 4
python audit_construct_union_family.py ARTIFACTS/20261120.json BASE_MODEL \
  ARTIFACTS/gpu-20261120.json --synthetic-input --rules 0,1,2 \
  --snapshot-run 0 --capacity 32 --ticks 20 --flush-every 1 \
  --order-queries --boundary-context --capture ARTIFACTS/20261120.capture.npz
python label_composed_witnesses.py ARTIFACTS/20261120.capture.npz \
  ARTIFACTS/20261120.json BASE_MODEL /dev/null ARTIFACTS/20261120.labeled.npz \
  ARTIFACTS/20261120.labels.json --synthetic-input --snapshot-run 0
```

Repeat only for manifest entries marked complete; preserve rejected entries.
The classifier uses the existing five positional model/source-model/decoder/
decoder-report/output arguments, one `--train` per synthetic labeled archive and
unchanged real `--validation` captures. There is no real training archive.

Bake branch `codex/cell-parallel-admission` remains at b066509b on inspection.
Its matched-result terminal Set takeover remains a guide, not a newly ported
GPU feature. Uncovered stages, mutable effects, correction integration and
complete GPU-dominant Eggcc execution remain outstanding.
