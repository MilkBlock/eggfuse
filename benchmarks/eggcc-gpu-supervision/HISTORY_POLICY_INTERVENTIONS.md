# Source-policy interventions on validation workloads

A standalone diagnostic using the five existing validation traces, frozen token
models, one frozen Eq decoder (previously validation-selected MSE alpha 100),
and a fixed 0.5 threshold. No training, threshold search, or test evaluation is
performed here. GPU readout versus CPU arithmetic passed numeric tolerances with
zero threshold disagreements in all 20 workload/intervention combinations.

The two previously fitted Eq decoder archives have elementwise identical `w`,
`coef`, and `alphas`; their training inputs are identical oracle class-balanced
states. This audit nevertheless explicitly uses only the latest-source archive.
Only token-model weights and incoming routes vary.

## Four combinations

All totals use 26,637 complete states, 26,142 with Eq queries. Counts below are
pooled diagnostic counts, not a new model-selection objective. Previous selection
uses workload macro metrics and remains unchanged.

| Routes | Token weights | Exact partitions | False pair merges | Missed equalities |
|---|---|---:|---:|---:|
| latest | latest | 19,977 | 1,514 | 11,229 |
| latest | earliest | 19,930 | 1,471 | 11,351 |
| earliest | latest | 19,832 | 1,497 | 11,517 |
| earliest | earliest | 19,938 | 1,376 | 11,386 |

Swapping routes under frozen latest weights loses 168 formerly correct instances
and repairs 23, for a net loss of 145. Of that net loss, 132 occurs in instances
whose incoming source wiring changes, and 13 in descendants whose own wiring
stays fixed. Unchanged components have no exact-partition changes.

Refitting for earliest context recovers much of this mismatch. The complete
refitted alternative loses 132 formerly correct instances and repairs 93 (net
loss 39); false pair merges decrease by 138, while missed equalities increase by
157. Direct-source instances account for net loss 27, descendants for net loss 12.

This supports investigating the information at the consumer interface. It does
**not** establish that the missing information is inherently unavailable from old
sources: swapping routes changes the distribution seen by fitted weights, and a
limited ridge feature map may not represent both distributions well. It also
shows why fewer layers and lower token RMSE were insufficient acceptance criteria.

## Consequence for the next experiment

Do not immediately add every latest Cell token alongside the retained earliest
source: that would restore the long dependency chains we just removed. First
identify which consumer-visible local facts distinguish lost and gained cases,
using the training/validation traces and typed template interface. A small change
representation must be derived from current inputs or already completed producer
state; consumer RHS labels cannot be used as its inputs. Charge its construction,
retention and numerical inference, and keep the original validation selection.
No ownership/lifetime proof or autonomous saturation protocol is supplied here.

## Reproduce

`audit_history_policy.py VALIDATION_MANIFEST BASELINE.npz CANDIDATE.npz READOUT.npz OUTPUT.json`

Use `rhs-validation-expanded-20261114/manifest.json`, `class-history-fallback.npz`,
`class-history-earliest.npz`, and `class-history-fallback-selection.npz` under
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee`. Adjacent `.json` reports are required
and artifact hashes are checked. The output is committed as
`history-policy-validation-results.json`; per-workload, per-rule and per-route
contingencies remain available there, rather than selecting anecdotes from test.

11 focused tests passed (`test_history_policy`, `test_historical_sources`,
`test_history_refresh`). The full audit also checks population identity and
causality. This is neither native runtime semantic acceptance nor a timing result.
