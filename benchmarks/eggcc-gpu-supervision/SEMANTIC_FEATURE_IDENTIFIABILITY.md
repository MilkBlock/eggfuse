# Observable context before more ridge fitting

This measures a standalone GPU prototype on real Eggcc snapshots, not the full
native runtime. The selected immutable context family is rules 283, 290 and 293.
No gradient descent is used. Exact GPU kernels still authorize effects; learned
completion is not yet authoritative and recursive predicted-source rollout is
not established.

## Additional real execution

GCD validation starts at snapshot Run 437, with 181 seed facts. It generates 41
Cells, consumes generated sources in 15 instances, and releases 30 owner rows.
All three completed Run graphs and per-rule application counts agree with an
independent CPU interpreter of the original, unlowered rules. Run changes are
true, true, false. This is one selected family, not full multi-stage Eggcc.

The original atom order overflowed capacity 128 and correctly refused completion.
A static initialization-cardinality order [0,1], [1,0], [1,0] avoids that overflow.
Original witness ordinals and preferred input origins are preserved. This order
is fixed across Runs; it is not a runtime CPU matching service. Eight scheduler
ticks did not reach the terminal control state, so acceptance still failed;
twelve ticks finish. Capacity and termination checks were not relaxed.

Static host evaluation flushes bound lazy GPU graph growth. They do not read
intermediate values or choose control flow from CPU results. They do introduce
host scheduling/synchronization overhead. The accepted run takes 38.697 seconds
including compilation/upload/execution; CPU reference plus audit takes 0.294
seconds. These are diagnostic timings, not a speedup or a controlled comparison
against an earlier flush configuration.

## Independent predictor and decoder calibration

Train: 40 Pascals samples. Validation: 41 GCD samples. Closed-form residual ridge
uses fixed alpha 10; the Eq threshold stays 0.5. The decoder trains on correct
training tokens, independently of predicted tokens. Both corrections fold into
existing matrices. No extra model layer is installed in the runtime.

| GCD validation | Exact partitions | False pair merges | Missed pairs |
| --- | ---: | ---: | ---: |
| Correct token, resident decoder | 40/41 | 0 | 1 |
| Correct token, calibrated decoder | 41/41 | 0 | 0 |
| Resident predictor and decoder | 10/41 | 61 | 9 |
| Calibrated predictor and decoder | 13/41 | 74 | 2 |

The last candidate is rejected: false merges worsen. Its direct-source subset is
3/26 exact with 59 false merges; generated-source subset is 10/15 with 15 false
merges. GPU/CPU numerical comparisons have no threshold disagreements. Decoder
calibration alone does not solve the predictor's missing information.

## Identical inputs, conflicting completion labels

Groups are constructed without labels; labels only score each group's largest
compatible target count. Target partitions come from final CPU family saturation.
The empirical maximum for any deterministic predictor of exactly these inputs is:

| Available input | Pascals | GCD | Combined |
| --- | ---: | ---: | ---: |
| Exact floating feature vector | 35/40 | 38/41 | 69/81 |
| Plus 128 input-relation features | 35/40 | 38/41 | 69/81 |
| Full selected-source structural context | 35/40 | 38/41 | 69/81 |

The last diagnostic includes all selected sources' semantic slots, current typed
Eq relations, scalar values, source sharing and selected records. It canonicalizes
IDs and excludes compiler temporaries. It is an offline signature, not a new GPU
encoder. Combined, 9 conflicting groups contain 44 samples. These ceilings apply
only to this empirical dataset and these observables, not to all possible models.

Thus loss in compressed source vectors is not the sole explanation. The current
selected witnesses do not determine final family completion. More copies of the
same inputs cannot repair contradictory targets. Do not insert future CPU roots,
program IDs or final outcomes into features to conceal this problem.

## Next feature obligation

Capture other *currently available* Cell interfaces sharing the selected boundary
Eq classes, beyond the chosen query witnesses. Bake should provide typed role and
projection masks. Aggregate this context once per reusable boundary/Cell group,
then feed fixed floating arrays into the same matrix pipeline. First measure
whether that observable context separates the conflicting groups, then fit ridge
and validate on the held-out program. Charge grouping, encoding, GPU consumption
and lifecycle costs. Do not add per-producer consumer lists or CPU future matches.

The inspected Bake reference is `ca3345e7` on `codex/cell-parallel-admission`:
static external result provenance distinguishes query-available key columns from
an actual result receipt. Repeated source patterns do not prove instance identity
or completed effects. The GPU path must likewise retain actual ownership,
generation, visibility and Run boundaries; similarity is not takeover proof.

## Reproduction and evidence

Use the project MLX Python environment. Binary inputs remain under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee` (ROOT below):

```
python audit_construct_union_family.py ROOT/union-corpus/validation-016-gcd.trace.json ROOT/class-history-neighborhood-input.npz ROOT/gcd-semantic-execution.json --rules 283,290,293 --snapshot-run 437 --ticks 12 --flush-every 1 --order-queries --capture ROOT/gcd-semantic-witnesses.npz
python label_composed_witnesses.py ROOT/gcd-semantic-witnesses.npz ROOT/union-corpus/validation-016-gcd.trace.json ROOT/class-history-neighborhood-input.npz ROOT/observed-corpus-20261113/manifest.json ROOT/gcd-semantic-labeled.npz ROOT/gcd-semantic-labels.json --snapshot-run 437
python audit_feature_identifiability.py ROOT/semantic-feature-identifiability.json ROOT/context-semantic-labeled.npz ROOT/gcd-semantic-labeled.npz
python calibrate_semantic_family.py --help
```

Checked-in JSON reports retain model/capture hashes and full calibration metrics.
Native final-state acceptance rules are unchanged. No native Rust modifications
or unrelated experimental work is included in this change.
