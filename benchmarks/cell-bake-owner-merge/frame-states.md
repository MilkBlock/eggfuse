# What must replace the per-application frame

The broader catalog changed physical storage, not the count of source identities.
This follow-up joins the saved composition frames to the authoritative fact
lifecycle snapshot by actual Cell ID. It validates each component's live-fact
count; it does not infer storage liveness from the match-history length.

| case | composition frames | still backed by source records | absent source records | live facts | default lifecycle | already stage-inherited | remaining default lifecycle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 778 | 752 | 26 | 948 | 878 | 458 | 420 |
| loopfact | 707 | 689 | 18 | 892 | 818 | 430 | 388 |
| sum-bits | 2,371 | 2,177 | 194 | 2,895 | 2,311 | 1,395 | 916 |
| dot-product | 2,268 | 2,122 | 146 | 2,825 | 2,466 | 1,407 | 1,059 |

All backed source records in these component snapshots are completed, have at
least one live fact, and have no parent link. Further parent-chain garbage
collection therefore does not remove this storage. Conversely, 26--194 component
frame identities survive without a source record: their ordinals/code can still
be needed by shared wiring and signal origins. Deleting the independent frame
directory without supporting these cases is incorrect.

`default lifecycle` requires an owned, visible fact with no Entry, no local-union
ownership or decoded cache, and birth/current epochs equal to its completed
source frame. It does **not** imply a fixed actual value, equivalent result, or
unused hash. Stage-inherited rows already capture part of this pattern; the
last column avoids counting that existing optimization again. None of these
counts is a byte saving or a legal rule-skip count.

There are only 157/168/244/191 distinct `(template, present operation numbers)`
patterns among the backed frames. Respectively 685/602/2,086/2,058 frames share
one of these patterns with another instance. The full reproducible pattern
histogram is in `frame-states.json`. These are actual storage outcomes, not
compiler assumptions: foreign constructor reuse and deletion can remove a
nominal RHS operation from the owned set.

## Required representation change

A meaningful takeover must replace per-fact default lifecycle and repeated
operation membership with the existing template's operations plus instance
presence/exception state. Keep actual scalar values and returned result ports
in their authoritative storage. Preserve source fact identity for live queries,
foreign users and ordered publication. Retain source-sized restoration slices;
a union must not force expansion of an enclosing template DAG.

The current `Facts` implementation already inherits stage epochs, but still
stores one operation/hash/exception row per fact. A next implementation must
prove when operation membership and hash storage are derivable or unnecessary;
it cannot zero them indiscriminately. `complete_canonical_cell`, constructor
hint removal, stable-field consistency checks and later representation fallback
still read those fields in some modes. Hashless storage, if used, must be tied
to the irreversible port-domain-only contract and validated through union,
hide/delete and restoration. Simple type packing or copying metadata into a
second registry does not accomplish the takeover.

This is an offline audit of the four frozen seed snapshots from the preceding
same-binary experiment. It introduces no runtime index, changes no execution,
and makes no new correctness/performance claim. It narrows the next implementation
to fact membership/default state rather than another round of larger catalogs.

```sh
python3 benchmarks/cell-bake-owner-merge/frame_states.py out/cell-bake-breadth benchmarks/cell-bake-owner-merge/frame-states.json
```
