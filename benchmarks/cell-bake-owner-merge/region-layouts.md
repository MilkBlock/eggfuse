# Region layouts: membership sharing with separate lifecycle obligations

This joins the four saved final snapshots from the complete dispatch memory run.
It does not execute another workload or claim a speedup. The analyzer reconciles
actual facts against each component's live count, rejects duplicate identities,
and verifies that each owned operation exists in its shared static layout.

| case | stored sources in regions | regions | membership layouts | regions in repeated layouts | cross-epoch regions | lifecycle exceptions | external retained sources |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 752 | 492 | 177 | 389 | 129 | 70 | 13 |
| loopfact | 689 | 464 | 194 | 332 | 108 | 74 | 13 |
| sum-bits | 2,177 | 1,344 | 382 | 1,132 | 427 | 584 | 37 |
| dot-product | 2,122 | 1,308 | 297 | 1,169 | 335 | 359 | 58 |

A membership layout is `(shape, checked source codes, per-source actual fact
operations)`. IDs, actual values and epochs are not part of this layout. Shape
IDs are artifact-local; this does not canonicalize layouts across workloads.
An absent source is distinguished from a present source with no facts. There
are 26/18/194/146 absent-storage sources whose wiring identities remain live.
Different started epochs do not by themselves identify different source Runs.
All stored sources counted here are completed; storage-only externally retained
sources outside components are not included in these region counts.

## Concrete next representation boundary

`Completed::Frame` currently repeats metadata plus slot/fact ranges per source;
`Component.frames` and the inverse composition directory preserve logical source
addresses independently. Existing pooled owners merge physical arrays, but do
not replace those per-source records with a shared region layout.

A region layout can describe sparse membership and ordered operation positions
without reserving every nominal RHS result. A region instance would retain actual
values/hashes, a source-stage mapping and lifecycle exceptions. Stable FactRefs
still need to resolve through the existing source identity machinery. A foreign
returned constructor is a reference to another fact, never a fabricated local
member. The admission gate must match actual completed sources and their sparse
membership; trace frequency alone supplies no proof.

Replacing source headers with one region header has a sensitivity count of
260/225/833/814 fewer headers, before charging the source-stage mapping, address
resolution and lifecycle exceptions. This is not a byte saving or a legal
elimination proof. Most components are still single-source, so header replacement
alone cannot meet the large-compression goal. The useful takeover must also derive
fact operation membership and offsets from shared layouts, removing the old
per-source fact-position/range records rather than retaining both representations.

Unexpected union or retirement must detach only the affected source's fields
and facts. External readers and wiring-only ordinals remain live independently.
The template should stay immutable, with a local source exception or restoration;
rebuilding every sibling of a large region is not acceptable. Existing source-
sized restoration is an invariant to preserve, not a cost to reintroduce.

A source's completed epoch cannot be collapsed into one region-wide epoch:
427 sum-bits regions contain different source epochs and 584 facts already differ
from their source-default lifecycle. Those are runtime obligations, even when
membership is identical. Likewise, repeated layout membership does not establish
current Eq, query visibility, or permission to skip effects. Stage-switch RHS
execution still requires the checked Entry/actual-result handoff.

## Reproduce

```sh
python3 benchmarks/cell-bake-owner-merge/region_layouts.py out/cell-dispatch-storage benchmarks/cell-bake-owner-merge/region-layouts.json
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/test_region_layouts.py
```

Three tests cover address/epoch-independent grouping, distinct source operator
codes, missing storage, duplicate identities and inconsistent live-fact counts.
This is evidence for choosing a runtime representation, not an implemented
structural takeover or new semantic acceptance result.
