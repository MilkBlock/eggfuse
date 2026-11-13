# Budget for structural runtime takeover on the unified branch

This is an offline analysis of the existing four same-binary pooled-owner
snapshots. It creates no new execution/timing result. The analyzer verifies that
all teardown fields plus unlisted bytes equal the full Graph-owned heap, groups
each field exactly once and records the input digest. Retained Program, allocator
metadata and process RSS remain outside this measurement.

| case | Graph bytes | source instances | composition addressing | boundary routes | stable fields |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 658,935 | 135,192 | 119,040 | 70,040 | 107,526 |
| loopfact | 585,105 | 124,552 | 114,816 | 68,264 | 56,438 |
| sum-bits | 1,773,131 | 449,696 | 460,160 | 215,144 | 224,118 |
| dot-product | 1,720,731 | 425,280 | 447,408 | 197,792 | 217,702 |

`instances` includes the entire Cells allocation, not just field arrays. Even
hypothetically deleting that whole category leaves 74.6–79.5% of these heaps.
Thus another round of completed-fact row packing cannot produce a large overall
reduction. The JSON also computes a 30%-of-current-snapshot budget as a sensitivity
bound; it does not replace the user's original-baseline target. None of these
whole-category deletions is legal or a measured saving.

## A rejected duplicate-state hypothesis

Scalar-bearing stable nodes are not generally duplicate copies of retained
instance inputs. `retire_completed_inputs` calls `delegate_completed_scalars`;
the latter removes a value only after its current stable-field provider agrees.
`completed_scalar_slot` subsequently reads that provider. Redirecting stable
fields back to instance slots without changing this ownership protocol creates
a read cycle or a missing value. `preserve_completed_scalars` materializes only
bindings losing their last provider, with source-sized restoration. Retain this
boundary when changing representation; do not expand an enclosing large Cell.

## What the next takeover must remove

The existing composition shape contains static operation uses and port wiring,
but each application still retains a source ID in `Component.frames` and a
reverse `Frames` entry `(component, ordinal, code)`. Completed storage has its own
source-address directory. `code` cannot simply be replaced by the port-program
ID: different operators may have the same port layout. A template-derived source
location must preserve the checked operator selection, source fact identities,
absent-source ordinals, ordered publication and worker read-epoch visibility.
Any design must count its new address directory against the old directories it
actually removes. Replacing an ordinary Cell with a completed frame alone has
not eliminated this addressing state.

Boundary routing is another distinct obligation. A runtime equality class maps
to component signals; those signals enumerate shared static uses. Equal current
roots alone do not prove the signals interchangeable: subsequent stage suffixes
may have different uses. A batched learned closure may eliminate a route only
when its shared wiring still enumerates all live constructor/query uses, including
late and union-enabled matches. Unknown external connections remain boundaries.
No per-producer consumer list should be introduced as a replacement.

Consequently, the next structural experiment should target one **source-location
representation shared by completed storage and composed execution**, with
source-sized exception/restoration records. Its gate is removal of an existing
address directory and its updates, not just admitting more large templates.
Worker snapshots and actual foreign constructor results are explicit live
obligations. This audit does not claim that such takeover is implemented.

Reproduce (saved snapshots only):

```sh
python3 benchmarks/cell-bake-owner-merge/runtime_budget.py out/cell-pooled-owners-final benchmarks/cell-bake-owner-merge/runtime-budget.json
```

## Lifetime join: directory fusion alone is not the next compression experiment

The initial recommendation above is now constrained by a join of the actual
source lifecycle inventory and composition frame identities in the same frozen
snapshots. The analyzer rejects duplicate identities in either inventory.

| case | both storage and wiring | wiring only | storage only | both, externally retained |
| --- | ---: | ---: | ---: | ---: |
| fact | 752 | 26 | 1 | 13 |
| loopfact | 689 | 18 | 2 | 13 |
| sum-bits | 2,177 | 194 | 3 | 37 |
| dot-product | 2,122 | 146 | 14 | 58 |

All records in the intersection are already completed and in completed storage.
Every storage-only source has an external retainer. The wiring-only records are
not a leak proven by this inventory: signal origins and shared operations still
use their ordinal/operator code after source storage disappears. Conversely,
component retirement must restore source slots for remaining external readers.
These are independently live obligations; a unified source record needs both
states and cannot simply reuse one lifetime bit for the other.

The existing source-position array itself is only 8,192/8,192/32,768/32,768 bytes,
**1.24–1.90% of Graph heap**. This is not a bound on every possible arena redesign;
it bounds deleting this specific array even if its replacement cost were zero.
An intrusive redesign that merely merges address arrays while keeping all
per-application metadata would therefore optimize the wrong unit. Do not equate
the previous 38% sum-bits addressing/routing group with removable duplicate maps.

The more consequential next proof is whether a completed source's *facts and
necessary results* can be represented by a shared template region plus actual
exceptions, while old fact handles still resolve and local retirement remains
possible. The 13/13/37/58 retained intersections need explicit external-reader
handling. The other sources are not automatically disposable: constructor
indexes, queries and publication may still refer to their facts. Parent-retainer
count alone is never permission to delete an instance or skip an RHS.

This rejects directory-only fusion as the next invasive implementation, rather
than adding shared mutable directories and synchronization to the worker path.
No runtime representation changed and no new compression is claimed.
