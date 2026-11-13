# Common failures of bounded Cell readouts

This joins the two 16-round held-out case audits from
`DIRECT_BOUNDED_CELL.md` to the frozen corpus training partition. It is diagnosis
only: no test input is added to training and no native semantic claim is made.
Both source case audits must pass their numerical audit, have matching manifest
hashes, identical rounds and exact case coverage, with no duplicate identities.

## What the 55 common failures contain

| Training coverage | Common failures | All test inputs |
|---|---:|---:|
| Exact input already in training | 41 | 711 |
| New input, known conservative template family | 12 | 122 |
| Uncovered family | 2 | 17 |

| Outcome in tanh / projected readout | Count |
|---|---:|
| Missed initial emission / missed initial emission | 11 |
| Still active / still active | 4 |
| Still active / wrong target but stopped | 1 |
| Wrong target but stopped / wrong target but stopped | 39 |

Of the 41 exact-seen failures, 33 stop at a wrong target in both models, seven
miss the initial emission, and one remains active in tanh but stops incorrectly
in the projected model. The fixed emission head accounts for those shared misses;
changing only the state map cannot rescue a discarded proposal.

These results do not support attributing most common failures to unseen inputs.
They also do not prove inadequate representation: regularized fitting, feature
capacity, unequal target importance, near collisions and recurrent distribution
shift remain possible explanations. Logical rule success is not committed graph
mutation. Exact training identity here is the collector's family/source/binding
key, not a guarantee of full-program equivalence.

## Exact initial-feature conflict audit

`audit_initial_features.py` constructs the actual f32 normalized feature rows of
the bounded state readout for train/test initial inputs. It groups byte-identical
rows and compares their normalized numerical target digests. Across 1,998 distinct
feature rows there are zero groups with conflicting targets. Validation records
are excluded from this diagnostic. This rules out only exact conflicts in the
observed initial features; it does not establish injectivity, sufficient separation,
linear separability, or compatibility for predicted/recurrent inputs. It does not
prove the 55 failures can be fixed by merely increasing the projection width.

The next fit investigation should measure training reconstruction and the effect
of feature capacity/loss allocation without changing holdouts. Retain separate
emission, target and recurrent numerical acceptance checks.

## Reproduction

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/audit_common_failures.py MANIFEST TANH_CASES.json CLIP_CASES.json COMMON.json
$PYTHON benchmarks/eggcc-gpu-supervision/audit_initial_features.py MANIFEST CLIP_MODEL.npz CONFLICTS.json
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest test_common_failure_audit
```

`common-failure-results.json` records all 55 input identities, coverage and effect
kinds. `initial-feature-conflicts.json` records the exact-collision check and model
fingerprint. Large models and case audits remain on the external SSD. The related
46-test suite passes; this adds no native CPU executor changes or speed claims.
