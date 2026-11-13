# Completed does not imply full fact membership

The next proposed representation derives facts from the shared template and
keeps actual values and lifecycle exceptions. Before changing the runtime, this
census checks the premise against the four final pooled-owner snapshots. It joins
actual source IDs to their shared operation layouts, checks exact template
consistency and owned-fact invariants, and reconciles the source count to the
completed storage report. It does not execute a new workload.

| case | completed sources | partial membership sources | actual facts | nominal positions | default lifecycle | lifecycle exceptions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 752 | 244 | 948 | 1,361 | 878 | 70 |
| loopfact | 689 | 224 | 892 | 1,244 | 818 | 74 |
| sum-bits | 2,177 | 915 | 2,895 | 4,361 | 2,311 | 584 |
| dot-product | 2,122 | 827 | 2,825 | 4,156 | 2,466 | 359 |

Allocating every nominal position increases position count by 39–51%, before
charging exception storage. This rejects the simplest dense-template replacement
for the existing sparse rows. An absent owned operation is not proof that its
RHS was never executed: it can have returned a foreign constructor or its owned
fact can have retired later. These snapshots do not distinguish the causes.

There are 157/168/244/191 distinct `(template, actual operation membership)`
patterns. This corroborates the earlier seed census on the newer pooled-owner
snapshots. The report retains the twelve largest partial patterns per workload
for selecting an actual-result/retirement trace, rather than copying a new full
catalog of masks into runtime. Membership variants describe existing instances;
they do not authorize skipping an apply or assuming a witness is still visible.

For implementation, derive the default operation layout from the template but
admit a compressed region only after checking actual ownership and returned
results. Keep presence independently from the stage-default lifecycle, support
source-sized removal, and resolve old FactRefs to the same actual fact. A layout
specialization may describe membership; it must not turn every absent owned
operation into a new fact. Hashes, scalar values and foreign results cannot be
inferred from this census. Existing stage-inherited lifecycle savings are already
present and must not be credited again.

```sh
python3 benchmarks/cell-bake-owner-merge/fact_regions.py out/cell-pooled-owners-final benchmarks/cell-bake-owner-merge/fact-regions.json
```

This is an observation result, with no new runtime compression, native semantic
acceptance, or speed measurement. The large-compression and saturated-stage RHS
objectives remain open.
