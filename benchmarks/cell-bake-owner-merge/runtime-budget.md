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
