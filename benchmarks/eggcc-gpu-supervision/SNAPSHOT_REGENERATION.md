# Generate fresh constructors from incomplete real-snapshot inputs

The previous snapshot experiment reused every constructor result. This controlled
extension removes tables written by a rule's RHS but not read by its query.
Queries and original rule operations are unchanged. GPU matching, ridge token
admission, ordered exact effects, token refresh and physical takeover then run
on the incomplete input. No missing output value or future successful binding
is supplied to the GPU.

Selection uses the same nine original rules and the original full-snapshot
source-row budget, before removal, so it does not select easier cases based on
generated results. Tables used by both query and RHS remain present. The modified
graph is an explicit experimental input, **not** the original program's initial
state or a claim of equivalence to its final export.

## Identity-independent CPU audit

The CPU builds a reference constructor map from only the retained seed facts.
Each seed identity is an opaque exact atom. It interprets the original copies
and constructor operations, constructing symbolic terms for missing results.
Returned GPU IDs must map bijectively to those fresh terms:

- Existing constructor results must reuse their exact seed identity.
- Repeated new constructor keys must share a result identity.
- Different new terms must not alias the same identity.
- Copy results, query bindings and valid/root fields must agree.
- Every allocated new ID must be explained by an observed constructed result.

Allocation order is intentionally irrelevant. The audit does not use the GPU
matcher, resolver or allocation ordering as its reference. It rejects overwritten
effect slots, unsupported effects and conflicting seed constructors rather than
silently inventing evidence. This is a restricted immutable-constructor audit,
not native proof replay, union equivalence or mutable-effect correctness.

## Results

The frozen model and trace hashes are recorded in snapshot-regeneration-results.json.
At 32 candidate slots and the original 32-source-row selection budget:

| Measure | Result |
|---|---:|
| Original rules tested | 9 |
| Expected / generated matches | 26 / 26 |
| Completed / pending Cells | 26 / 0 |
| Executed copy/constructor operations | 56 |
| Fresh constructor identities | 19 |
| Fresh structural terms independently explained | 19 |
| Wrong / unknown completed results | 0 / 0 |
| Corrupted retained sources | 0 |
| Released physical rows | 22 |
| Rejected takeovers | 4 |

Rule 50 generates five distinct results across two matches, exercising sharing
inside its three-constructor RHS. Rules 54, 244, 245, 534, 535 and 536 generate
the remaining 14. Rules 246 and 537 retain their queried RHS table and generate
no fresh identity in this control. All four takeover rejections remain uncovered
aliases in rule 245. No guard was weakened to turn these into successes.

The GPU phase takes about 20.87 seconds across independent compilations; CPU
reference matching, structural checking, output readback and source preservation
checks take about .015 seconds. These are different scopes with cache and compile
costs included, not a speedup claim or native audit throughput measurement.

## Scope and next step

The new evidence is actual fresh-result allocation and sharing followed by
takeover on real rule bodies. Completion still uses exact GPU operations; the
ridge token alone does not authorize effects or establish accuracy. This remains
a set of isolated rule executions on modified final-snapshot inputs. It does not
yet show real families repeatedly consuming newly generated Cells until saturation
and advancing the original full multi-stage schedule.

The next useful real family is the type-analysis closure around TNil/TCons,
PureTypeList and PureType: generated predicates can feed other original rules
without needing unsupported mutable effects. A family test must preserve the
same frozen-Run query boundary and account for repeated/late matches, new IDs,
owner aliases and candidate capacity rather than loading captured continuations.

The tracked Bake branch is now fba15b23. Its source-directory audit shows that
structural shape does not uniquely determine physical layout or creation epoch,
and most components share physical storage with outside sources. Accordingly,
this experiment retains logical sources, generation metadata and checked owner
projections. Releasing a physical row is not deleting the source directory or
proving that all its routing obligations ended.

## Reproduce

Run audit_snapshot_completion.py with rhs-dot-product.json, the frozen
class-history-neighborhood-input.npz, an output path and --regenerate. The usual
snapshot-reuse mode remains the default. Inputs and logs are on
/Volumes/Extreme SSD/eggfuse-artifacts/21ee. Negative tests cover incorrect reuse,
aliasing different terms, duplicate fresh identities, missing results and
unexplained allocations; query-table removal is prohibited.
Twenty-three relevant tests pass.
