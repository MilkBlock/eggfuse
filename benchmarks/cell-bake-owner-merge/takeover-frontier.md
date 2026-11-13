# State replacement frontier after matched takeover

Analysis of saved actual standalone Cell CPU executions; no new workload run or
timing. The prior dual-source experiment proved safe local aliasing but increased
total retained heap. This audit asks whether expanding the same mechanism could
plausibly reach the runtime compression target before paying for another catalog.

| case | Graph bytes | all repeated roots | impossible free binding payload saving | Graph left after deleting ALL Cell storage |
|---|---:|---:|---:|---:|
| fact | 638,751 | 1,154 | 18,464 (2.89%) | 516,559 |
| loopfact | 565,101 | 1,103 | 17,648 (3.12%) | 453,369 |
| sum-bits | 1,695,443 | 4,568 | 73,088 (4.31%) | 1,316,251 |
| dot-product | 1,641,667 | 3,903 | 62,448 (3.80%) | 1,288,267 |

These are deliberately unattainable component bounds, not proposed deletion or
full savings estimates. Duplicate binding payload excludes associated boundary
entries, capacities and any replacement lookup/address cost. Counting root
coincidence as equivalence of entire Cells would be invalid. Even perfect removal
of duplicate binding values cannot explain a 70% reduction. Removing Cell records
alone also cannot do it. This rejects expansion of the current pairwise alias
catalog as the principal compression strategy, not all possible use of aliasing.

## Replacement scope

The sum-bits control retains 2,177 completed positioned source records plus 194
positions whose original source storage is already gone. All 2,895 owned facts
still have logical identities; 75 are hidden and remain congruence obligations.
There are 1,825 scalar-free facts, of which 1,465 currently share both lifecycle
epochs with their source. Those are observations, not static lifetime proofs.
Scalar-free stable-record projection and inherited lifecycle compression already
exist: their savings must not be credited again to a new combined Cell.

The next representation must make the existing Cell instance the authoritative
source for field projection, lifecycle and component position, then remove the
corresponding old directories and maintenance. Merely nesting existing source
records under a larger component retains these costs. The largest sum-bits fields
are Cell storage (379,192 bytes), components (280,192), stable fields (224,118),
boundaries (215,144), and the source-position directory (163,584).

Required proof before deleting a path:

- Preserve actual foreign result identities, source Run visibility and Entry/delta
  eligibility. A matched producer operation is not necessarily the result owner.
- Compile static port/operator positions from the same Cell definitions. A dead
  source can still provide the type/code origin for a surviving symbol; absent
  source storage does not authorize erasing that position.
- Separate remaining dynamic scalar slots and lifecycle exceptions from facts
  reconstructable by template projection. Hidden facts are not dead facts.
- Preserve source-sized restoration under unexpected union or deletion. Physical
  owner sharing must not make a scalar exception expand a whole enclosing Cell.
- Validate the removed maintenance and complete retained heap, not just bindings.
  Final snapshots cannot establish peak compression or skipped RHS execution.

The audit validates source uniqueness and complete symbol/frame wiring and records
input hashes. Four tests cover repeated roots, unbound slots, missing sources,
hidden/retained facts, lifecycle changes, scalar fields and malformed layouts.
Reproduce without executing workloads:

```sh
python3 benchmarks/cell-bake-owner-merge/takeover_frontier.py out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/takeover-frontier.json
python3 -m unittest discover -s benchmarks/cell-bake-owner-merge -p test_takeover_frontier.py
```

No runtime state was removed by this analysis. Large egraph compression and fast
stage-switch RHS generation remain unachieved.
