# An Entry reuses its selected source address

The compiled constructor-witness group already collects several RHS operations
under one matched Entry. Its runtime selection cache previously reused the
catalog lookup but still resolved the source Cell directory and rebuilt the
shape/ordinal/code key before every operation.

The same coordinator scratch now also retains the anchor FactRef and component
ID. Reuse checks the actual anchor, current component shape, and the source ID
at the saved ordinal. A changed suffix, relocated source or retired component
falls back to ordinary source resolution and catalog selection. Source operator
codes are immutable for a logical source ID. No component ID or source ID is
recycled by this runtime. These properties are necessary for the address check;
a future recycling allocator must supply its generation here.

This removes the source-directory lookup and catalog-key reconstruction on
address hits. It does not remove the component read. The existing static-key
cache still serves different instances of the same shape. There is no per-Entry
allocation, extra binding array, reverse dependency or mutation-time invalidation.
The one coordinator selection gains one optional `(FactRef, component ID)`;
these are addresses, not saved result values or equality/visibility proofs.

Source liveness for static key proof, target code/ownership, current-key checks
for unproved routes, dirty tables, forwarding and final result admission remain
unchanged. The proof applies only to immediate address selection. It does not
allow carrying a checked value across mutation or skipping uncovered RHS effects.

`constructor_cell_route_address_checks` charges selection attempts;
`constructor_cell_route_address_reuses` is an outcome only. Actual source-directory
reads stay in `constructor_cell_route_anchor_reads`. Bake credit now includes
route probes, directory reads, operation selection, candidate comparisons and
source checks. For historical reports, the prior selection-check count is derived
from successful anchor reads, since the old cache was checked after resolution.
Reports declaring `checked-component/v1` must supply the new counters. Cache hits
and avoided comparisons earn no separate credit, and equal-weight work credit
remains a proxy rather than a latency measurement.

Validation: 64 ownership integration tests, the focused source-address lifecycle
test and six work-credit tests pass. The multi-result Entry fixture requires
actual address reuse and compares final exports, Run snapshots and binding audit
against its control. Lifecycle coverage explicitly rejects changed shape, a
different source in the same ordinal, changed fact operation and retirement.
The credit tests charge an added address check or directory read once, reject
missing counters, and give extra hit counts no reward.

This is a small standalone Cell CPU RHS dispatch change. There is no new timing
campaign, large-workload speed claim, native egglog acceptance, Graph compression
claim or additional skipped-rule claim. Large runtime egraph compression and
complete cross-stage state-switch execution remain unfinished.
