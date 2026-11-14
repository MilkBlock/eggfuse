# Current boundary neighbors for semantic Cell completion

This is a standalone real-snapshot GPU experiment, not full native Eggcc execution
or an autonomous learned runtime. It follows the previous exact-input ambiguity
audit. Cell generation, saturation and owner transfer remain on the existing GPU
path; learned outputs still do not authorize unions or replace exact completion.

## Implemented input representation

`device_boundary_context.py` compiles semantic port roles, typed Eq sort indices
and fixed random floating projection matrices. At query capture it reads actual
slots through the existing owner projection, masks invisible, unfinished, dirty
or stale-owner Cells, and forms current typed boundary connections. No future
CPU root, numerical ID embedding, program ID, or target label enters a feature.

For every eligible neighboring Cell port:

```
h = tanh(cell_token @ W_token + static_port_role @ W_role)
```

For each consumer input port, sum connected messages, normalize by square root of
count and apply tanh. Separate channels retain all neighbors and neighbors not
selected as query witnesses. Semantic port positions project into the shared
padded family layout: 512 new floats, extending the ridge input 1665 -> 2177.
Compiler-only temporary ports are excluded. The encoder runs in the actual GPU
capture path and is independently reconstructed with NumPy. The largest observed
feature discrepancy is 2.98e-7.

This currently builds a dense connectivity mask. It is not the desired final
shared boundary implementation. No persistent reverse-dependency lists or second
runtime fact graph are introduced, but capture mode records full current boundary
payloads for post-execution diagnosis. That diagnostic storage must not be treated
as a production requirement or free overhead. Production mode without the option
retains the old behavior.

## Real source execution and labels

All cases use original rules 283, 290, 293, independently interpreted by the CPU
oracle. Lowered GPU constructor/set/union execution is checked at every completed
Run, including per-rule application counts and final graph classes/facts.

| Program | Partition | Snapshot | Generated Cells | Generated-source consumers | Released owner rows | Runs |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Pascals | train | 466 | 40 | 4 | 34 | 4 |
| Euclid | train | 507 | 35 | 1 | 18 | 2 |
| GCD | validation | 437 | 41 | 15 | 30 | 3 |

All execution gates pass. These counts are Cell instances and owner releases, not
claims that every logical match is a unique committed graph mutation. The
selected family is not the full original multi-stage program. Fixed query orders
and flush windows are recorded in the commands below. The CPU provides the
initial snapshot and labels after execution, not future matches during these Runs.

The independent one-hop structural signature also separates the former ambiguous
inputs. Across 116 samples, resident inputs have 10 conflicting groups and an
empirical deterministic ceiling 99/116. Both extended floating input and the
one-hop signature have 113 distinct inputs with no conflicting labels. This is
an information diagnostic, **not 100% prediction accuracy**. The structural
signature does not canonicalize sharing among non-boundary neighbor ports.

## Program-separated fixed-alpha ridge results

Alpha stays 10 and Eq threshold stays 0.5. No gradient descent. GCD never enters
either predictor or decoder fit. The decoder is calibrated on CPU-correct training
tokens independently of the predictor. With Pascals alone, new features yield
14/41 exact GCD predictions, 69 false pairs and 0 missed pairs: still unacceptable.

The controlled comparison below trains on the same 75 Pascals + Euclid samples
and uses the same calibrated decoder. Only boundary columns differ:

| GCD validation | Without boundary | With boundary |
| --- | ---: | ---: |
| All exact partitions | 13/41 | 20/41 |
| All false pair merges (also after closure) | 69 | 42 |
| All missed equalities | 2 | 6 |
| Direct-source exact | 3/26 | 14/26 |
| Direct-source false merges | 57 | 26 |
| Generated-source exact | 10/15 | 6/15 |
| Generated-source false merges | 12 | 16 |

Direct-source evidence improves, but generated sources regress. Five generated
training instances versus fifteen generated validation instances remain a clear
coverage limitation, not proof of the sole cause. The candidate is **not installed**.
Using the resident decoder instead gives different tradeoffs; the complete JSON
records both and does not cherry-pick one gate. No threshold disagreement occurred
in CPU/GPU inference comparisons. Source tokens still come from exact completed
states; recursive predicted-source execution remains unverified.

## Accounted costs

End-to-end diagnostic compile/upload/execute times are Pascals 22.229 s, Euclid
29.596 s, GCD 34.536 s. Independent CPU reference plus graph audit takes 0.102,
0.061 and 0.166 s respectively. These include capture and exact kernels and are
not comparable to a warmed production model or a speedup over previous settings.

A bounded replay of the first accepted GCD block per rule records:

- 128 padded lanes, 309 Cell rows, 8 slots, 4 Eq input ports;
- 1,265,664 connectivity elements per batch;
- 262,144 output bytes per batch, 37,088 static plan bytes;
- 183,237 captured boundary bytes per block (diagnostic only);
- CPU encoder 4.79–5.38 ms; GPU warmed encoder 1.24–1.61 ms;
- upload, first compilation/execution and readback separately in `boundary-cost.json`.

The micro-audit starts after owner projection; it excludes its gather/lifecycle
work, which is included in the end-to-end run. These are bounded diagnostics,
not a broad performance campaign. Before enabling the feature in production,
reuse aggregation across consumers of the same typed boundary instead of building
this dense mask for each query block, and measure total cost including maintenance.

## Bake reference and remaining work

The latest inspected `codex/cell-parallel-admission` is `ca3345e7`: actual external
result provenance and query-key availability are distinct. Here similarly, a
neighbor role is contextual evidence, never proof of receipt ownership or Eq.
Existing visibility, generation, effect order and completion checks remain live.
The useful next data is more *generated-source* contexts from independent training
programs and later legal boundaries, not repeated copies of the first match.
Keep direct/generated validation separate and preserve a held-out test partition.

## Reproduction

Run scripts in this directory using the project MLX Python. ROOT below is
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee`; binaries stay outside Git.

```
python audit_construct_union_family.py ROOT/union-corpus/validation-016-gcd.trace.json ROOT/class-history-neighborhood-input.npz ROOT/gcd-boundary-execution.json --rules 283,290,293 --snapshot-run 437 --ticks 12 --flush-every 1 --order-queries --boundary-context --capture ROOT/gcd-boundary-witnesses.npz
```

Pascals uses `pascals-union-boundaries.json`, snapshot 466, ticks 16; Euclid uses
`union-corpus/train-011-euclid.trace.json`, snapshot 507, ticks 16. Both retain all
other options. Label each capture with `label_composed_witnesses.py` and the
matching trace/snapshot, model and `observed-corpus-20261113/manifest.json`.

```
python audit_boundary_context.py ROOT/boundary-expanded-identifiability.json ROOT/pascals-boundary-labeled.npz ROOT/euclid-boundary-labeled.npz ROOT/gcd-boundary-labeled.npz
python calibrate_semantic_family.py ROOT/pascals-boundary-labeled.npz ROOT/gcd-boundary-labeled.npz ROOT/class-history-neighborhood-input.npz ROOT/port-quadratics-direct-training.npz ROOT/port-quadratics-direct-training.json ROOT/boundary-expanded-model.npz ROOT/boundary-expanded-decoder.npz ROOT/boundary-expanded-calibration.json --boundary-context --extra-training ROOT/euclid-boundary-labeled.npz
python audit_boundary_cost.py ROOT/gcd-boundary-labeled.npz ROOT/boundary-cost.json
```

Repeat calibration without `--boundary-context` for the controlled ablation.
All JSON reports retain source/model hashes. Tests cover real-valued unselected
neighbor contribution, typed connectivity, ID-renaming invariance, owner layout
invariance, stale/hidden/dirty exclusions, NaN padding and compiled GPU agreement.
Native final-state acceptance contracts are unchanged.
