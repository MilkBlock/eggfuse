# Lower real Cell contracts to device entry plans

`lower_device_entries.py` connects the existing Cell compiler output to
`closed_entry_proposals`, replacing manually assembled query-coverage fields in
the integration tests. It uses the recipe and checked template facts, not saved
successful bindings. This is still a standalone GPU mechanism, not a complete
Eggcc execution or autonomous ownership-transfer result.

## Lowering and runtime obligations

The compiler recomputes source template completion, validates every query witness
and input projection, checks source/consumer slot sorts, and requires a matching
continuation contract. Cross-ruleset transitions are explicit boundaries until
the source Run controller exists. Stage numbers here name rulesets; they are not
source Run ordinals and do not authorize source schedule reordering.

Two layouts are available:

- Input-key-only: project checked source query inputs into the consumer key.
- Source slots: project inputs or the actual return slot of a completed constructor
  operation. The operation index locates a **slot containing the actual returned
  witness**; it does not become the returned identity. GPU checks per-slot presence.
  Missing witnesses produce a mark and block admission.

The consumer's input slots are initialized from this same projection. Other slots
remain absent. Literal encoding is still unsupported and marked, rather than
inventing an integer identity for a scalar. Real Eq root/forwarding updates,
scalar arithmetic, deletion and nontrivial witness visibility require subsequent
runtime integration; a slot-presence bit alone cannot certify those obligations.

Every consumer with any effects remains `settled=False`. In particular, a
successful match cannot silently complete union, set, copy or construction.
`needs_attention` now also checks active unsettled tokens, including those with
no outgoing compiled entry. This fixes a false-quiescence hole: zero new entries
is insufficient if an earlier admitted token still has effects to execute.

Transfer coverage remains **false for every compiled entry**. Query completeness
is not exclusive activation ownership, and these templates do not yet prove that
all future source responsibilities move into a successor. The low-level transfer
kernel is available, but the real lowering does not grant it unsupported authority.

## Real recipe coverage

Source: saved dot-product recipe, SHA256
`9cec5d6f16fc24db9863f84e704af0888ef2afc17aae041a2c00f57a20ba9b38`.
Only `recipe` is read to generate the catalog; traces are not execution inputs.

| Measure | Input-only | Actual source slots |
|---|---:|---:|
| Compiled catalog entries | 930 | 930 |
| Lowered entries | 106 | 157 |
| Consumers with pending effects | 106 | 157 |
| Consumers complete from query alone | 0 | 0 |
| Marked actual-result routes | 693 | 0 |
| Marked source Run boundaries | 767 | 767 |
| Marked literal routes | 162 | 162 |

Reasons overlap. The catalog itself has 151 unsupported effect boundaries;
single-source catalog coverage also excludes unknown multi-source/late matches.
The lowering counts do not measure actual matched instances, semantic correctness,
speed, or accepted transfers. Source slots add 51 same-ruleset entry layouts;
they do not remove the effect execution barrier.

Key width is 40 integer fields (template plus padded query inputs). The provisional
source-slot layout pads to 396 fields, the maximum template size in this recipe.
This is costly: slot IDs and validity arrays, candidate projections and duplicated
input-key storage all remain. They must be charged and later replaced by shared
family layouts/authoritative slot views. No compression or memory saving is claimed.
The pairwise duplicate kernel still has its previously documented bounded cost.

## GPU verification

19 tests pass across lowering, token admission and compiler contract modules.
Compiled recipe tests run directly through MLX Metal without host inspection
between rounds. They check:

- Exact source-input projection and duplicate suppression.
- Actual foreign result values: the same operation can yield 999 or 1234, and the
  successor key follows that value, never the operation index.
- Missing returned slots block admission and request attention.
- Corrupt contracts and cross-stage entries are rejected/marked.
- A matched consumer containing union stays unsettled; even a following round
  with no new admission cannot claim completion.

Float matrices in these fixtures are test transforms, not the trained ridge
completion adapter. The source state is seeded as a completed test Cell; no real
Eggcc effect executor has yet produced these slots on GPU. This is the next
integration requirement, together with current Eq witnesses and scalar values.

Reproduce using the NumPy/MLX environment:

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_lower_device_entries test_device_token_commit \
  test_continuation_contract test_cell_token_successors
$PYTHON benchmarks/eggcc-gpu-supervision/lower_device_entries.py TRACE OUTPUT.json
$PYTHON benchmarks/eggcc-gpu-supervision/lower_device_entries.py TRACE OUTPUT.json --source-slots
```

Reports: `device-entry-lowering-results.json` and
`device-result-entry-lowering-results.json`. Reference Bake branch remains
`731188d2`; no new branch merge or native benchmark was performed.
