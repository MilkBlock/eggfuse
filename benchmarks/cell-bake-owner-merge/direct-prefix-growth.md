# Allow an installed Cell path to grow at catalog capacity

The selected direct-source catalog contains 256 one-hop paths. Its audited
execution (`out/cell-direct-joins/trace.json`) contains 457 repeated two-hop
extension proposals covering 108 distinct installed prefixes. Previously,
`extend_observed_owners` stopped as soon as the directory held 256 paths. It
could not replace a short path with a longer path that already includes it.

Selection now checks capacity after removing prefixes subsumed by the proposed
path. A higher-ranked unrelated path that does not fit is skipped, rather than
ending the whole selection. Exact source and installed-catalog digests and
nonempty audited Runs are required. The typed Program loader still checks all
selected wiring, and the compiler verifies that every seed transition remains
in the resulting language. No runtime proof is inferred from frequency.

Three selector tests pass (job 356), including a full 256-path directory, an
unrelated higher-ranked candidate, legal replacement by a longer path, and
preservation of all old paths. The same job selects and runs all three budgets
from one saved trace, without retraining between measurements.

| Extension budget | Accepted replacements | Final components | Three-frame components | Graph bytes | Resident Program bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Control | 0 | 1,558 | 0 | 1,392,459 | 107,450,586 |
| 32 | 32 | 1,454 | 151 | 1,390,243 | 107,045,958 |
| 128 | 108 | 1,364 | 283 | 1,386,283 | 107,599,014 |
| 256 | 108 | 1,364 | 283 | 1,386,283 | 107,599,014 |

The directory still contains 256 maximal paths. Budgets 128 and 256 produce
the same selected path set and observed state. All lanes preserve the exact
final export and Run sequence. These are actual standalone Cell runtime
requested-heap observations, not timing or upstream native egglog measurements.

This fixes an iteration barrier, but does **not** establish large compression.
At 108 replacements, symbol slots fall from 7,978 to 7,685 and compiled appends
rise from 820 to 1,084. Graph savings are only 6,176 bytes: ownership component
storage grows 2,304 bytes while boundary storage shrinks 7,392 bytes and Cells
storage shrinks 1,088 bytes. There are still exactly 2,177 completed source
records and 26,924 bytes of live fact records, unchanged from control. Larger
logical Cells have not removed these per-source records or directories.

Resident Program costs remain charged. The lower 32-path Program total is
largely a 494,684-byte reduction in retained artifact JSON; executable/shared
plan storage actually grows by 90,056 bytes. At 108 paths, plan storage grows
329,464 bytes and artifact JSON shrinks 181,036 bytes. Neither artifact change
is evidence of better egraph compression.

Exact artifact hashes, final-state checks and the larger candidate's Run-level
validation status are recorded in `direct-prefix-growth.json`. Untested
intermediate-state coverage must not be inferred for the other lanes. The
best observed Graph is still above the historical 30% target, and this path
extension does not implement saturated RHS skipping.

Reproduce under the shared compute queue with
`iterative-bake,sparse-cells,storage-metrics`:

```sh
extend_observed_owners SEED_PROGRAM AUDITED_TRACE BUDGET NEW_DIR
runtime_storage_peak NEW_DIR/program.json MEMORY inherited-owners --port-domains-only --cell-fields --retired-prefixes --state-output STATE
runtime_storage_comparison SEED_PROGRAM CHECKS NEW_DIR/program.json --completed-owners --retired-prefixes
```

Frozen compiler, selected Programs and full reports are in
`out/cell-direct-prefix-growth`. The runtime binary is the event-driven build in
`out/cell-retired-prefix-events`. This experiment learns from actual execution;
it retains residual queries, visibility, lifecycle, native Eq addressing and
original Run/effect ordering as runtime obligations.
