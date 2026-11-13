# Admit storage from ordinary sources, not historical components

The saved sum-bits run at `9d61be39` records 1,387,355
`shared_owner_admission_source_probes` and 806,246
`shared_owner_settled_components_skipped`. The old transfer loop walked every
live composition component at every settled Run boundary, then probed its source
IDs until finding an ordinary Cell. An already completed large component still
paid one lookup for every old source merely to establish that no transfer was
needed. This repeated discovery works against larger cross-stage completions.

The existing ordinary Cell arena already contains the exact sources not held by
completed storage. Admission now visits that arena, resolves each source through
the existing composition directory, sorts and deduplicates component IDs, then
runs the unchanged eligibility and transfer logic for those components. It does
not maintain a new candidate queue, dirty flag or reverse dependency. Restoration
puts a source back into the ordinary arena, so it naturally becomes a candidate
again. Sources without a composition frame remain outside this transfer path.

This is the same candidate predicate as before:

```
component has any source in ordinary Cells
```

Resolving it in the opposite direction avoids traversing all completed history.
Sorting the component IDs preserves the original component iteration order and
therefore the existing physical pooling order. The temporary candidate vector
and sort are new costs; they contain ordinary sources, not all historical frames.
Incomplete ordinary sources may still be examined. There is no claim that all
admission work disappears.

`shared_owner_admission_source_probes` now charges actual ordinary-source
examinations. The historical `shared_owner_settled_components_skipped` field
remains readable but receives no artificial skipped-work credit: those components
are never visited. The existing cross-stage extension test now requires zero
source probes at a boundary where all four sources are already transferred,
while still checking no storage change, later suffix extension and both serial
and two-worker execution. Existing tests cover incomplete parents, foreign
results, restoration, later reads, union and deletion.

This removes a repeated discovery/maintenance path without changing fact or
instance representation. No new compression percentage or speed claim follows
from the loop removal, and the historical sum-bits counters are an opportunity
measurement, not a measured new work delta. Large runtime compression remains
unfinished. No additional large-workload or timing campaign was run for this edit.

Validation job 259: all 66 ownership integration tests pass.
