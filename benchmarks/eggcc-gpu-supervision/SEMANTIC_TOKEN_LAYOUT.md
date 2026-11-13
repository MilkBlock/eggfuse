# Keep Cell tokens semantic across effect lowering

The composed-family audit uncovered a representation bug: lowering constructor
`set` into construct + union added a temporary slot and changed operand roles,
neighborhood roles, template request codes and completed token aggregation.
The same source Cell therefore acquired a different floating representation
because of an execution implementation choice. More training alone would mask
that instability rather than preserve the intended Cell-token interface.

## Implemented correction

`lower_constructor_sets.py` now retains the original semantic slots/query/effects
and a static runtime-slot projection. `device_semantic_template.py` checks that:

- original slots and queries remain unchanged;
- temporary slots have the correct type and an explicit union alias;
- the complete effect stream is exactly the supported set lowering, with no
  extra effects hidden behind a semantic header.

Input and source-role compilation use original semantic roles. A temporary
constructor result projects the role of its original supplied-result slot. The
completed token excludes temporary slots from aggregation. All temporary slots
still participate in exact constructor execution, typed union, effect PCs,
ownership, availability and settlement checks. This does not make an unfinished
union complete or allow speculative tokens to authorize effects.

Both joint matching and the older single-source transition compiler use the same
projection. No additional GPU branch, launch, feature column or persistent fact
structure is added. The projection is baked into existing constant role arrays
and validity masks. Temporary runtime slot/ID allocation from the earlier lowering
still exists; this change does not claim to remove it.

## Real GPU execution and comparable accuracy

The three-rule Pascals context family was rerun with the frozen model weights.
It again generates 40 Cells, consumes generated sources in four instances,
releases 34 physical owner rows and saturates in four Runs. Every completed
Run's graph and per-rule match counts pass the independent unlowered CPU oracle.

`label_composed_witnesses.py` reconstructs final targets from that independent
CPU saturation, using actual returned stable identities mapped through observed
constructor facts. It rejects missing/contradictory identities. Scalars retain
their actual imported values. Source features use only the captured pre-consumption
inputs; future CPU equivalence is used solely for labels. There are 15 distinct
inputs, 13 distinct target vectors, 175 dynamic Eq comparisons and 59 positives.

For a fair before/after comparison, **both** captures are evaluated on the same
original semantic slots and CPU target tokens. The old capture's historical
raw-temporary-slot score is a different contract and is not the baseline here.
`compare_semantic_tokens.py` verifies identical source/model/decoder hashes,
identical CPU targets/partitions and all 528 captured integer/boolean arrays.

| Frozen prediction on semantic slots | Before | After |
|---|---:|---:|
| Exact partitions | 11 / 40 | 17 / 40 |
| False pair merges after closure | 146 | 8 |
| Missed pair equalities | 15 | 31 |
| Nontransitive predictions | 0 | 0 |

There is a substantial reduction in false merges, but recall regresses and overall
accuracy remains insufficient. This is a training-program representation ablation,
not unseen-program generalization or a speedup. No gradient descent or retraining
was used. Exact kernels remain responsible for semantic completion.

Separating the decoder from the predictor also matters: CPU-correct semantic
tokens decode to 35/40 exact partitions, with zero false merges and five missed
equalities. All five failures are in the Single rule 293. Prediction errors thus
include a **decoder calibration gap**, not just incomplete source features.
Generated-source predictions remain 1/4 exact; their CPU-correct target tokens
decode 4/4. Direct sources are 16/36 exact. Both deficiencies remain live.

## Artifacts, tests and next work

`semantic-token-execution.json` records execution and label evidence;
`semantic-token-comparison.json` records the like-for-like audit. Binary captures
and supervised arrays remain under `/Volumes/Extreme SSD/eggfuse-artifacts/21ee`.
The new `device-joint-witness/v3` schema explicitly carries `semantic_recipe`:
label slots refer to the original Cell interface, not compiler temporaries.
Existing v2-only training tools reject it until explicitly extended. The readout
checker supports both and requires the semantic definition for v3.

Thirty relevant tests pass. They cover exact input-role/request invariance,
completed GPU token invariance, alias/effect-proof rejection, independently mapped
foreign result IDs, existing joins, input encoding, ordered union and takeover.
The executable mode on the earlier JSON result was also corrected.

Reproduction:

```
python audit_construct_union_family.py TRACE MODEL EXECUTION --rules 283,290,293 --snapshot-run 466 --capture RAW.npz
python label_composed_witnesses.py RAW.npz TRACE MODEL CORPUS LABELED.npz LABEL_REPORT --snapshot-run 466
python audit_device_match_readout.py LABELED.npz DECODER DECODER_REPORT READOUT
```

Run from `benchmarks/eggcc-gpu-supervision`. Add `--semantic-targets` when labeling
an older raw capture for the same-semantic-interface comparison. Then run
`compare_semantic_tokens.py BEFORE AFTER BEFORE_READOUT AFTER_READOUT OUTPUT`.

Next: separately calibrate the semantic Eq decoder on CPU-correct states and
train completion on this larger set of actual source modes, with program-separated
validation. Full original initialization/stages, broader primitive/mutable support,
CPU correction integration and learned closed-loop execution remain incomplete.
The latest inspected Bake reference remains `0e3a5152`; external witness presence
continues to be distinct from local coverage proof. No native CPU executor code
was modified in this iteration.
