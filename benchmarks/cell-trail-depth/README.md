# Retained Cell ancestry

Run `python3 benchmarks/cell-trail-depth/analyze.py HISTORY CATALOG PROGRAM OUTPUT`.
Use `cell-history.json` and `catalog.json` from the same iterative Bake round;
PROGRAM supplies rule metadata and must have the same recipe checksum.
The caller must supply a matching history/catalog pair. The script checks recipe
identity for metadata, parent ordering, and resolves active units in the catalog.

`sum-retained.json` analyzes the saved actual Cell runtime training export from
`out/history-coverage-sum-latest/round-0` in the 7c16 worktree, using recipe metadata
from the unified worktree's `out/ripsat-cell-completion/final-checks/sum-baked/program.json`.
It is a historical observation, not a current-branch performance measurement,
a native egglog semantic comparison, or a distribution of all candidate winners.
The raw history contains 2,048 events, drops 380, and lacks full ancestry for 524.
Retained chain length is not Cursor.depth. The round has ZERO composition joins:
all active units have size one, so this data cannot measure trained catalog hits.

## Evidence and optimization opportunities

Of 723 retained edges, 690 stay in one ruleset; 662 are always-run -> always-run.
358 of 374 events at retained depth >=3 belong to always-run. Only 37 events
exceed the catalog's composition depth limit of four; raising that limit alone
is not supported as a broad remedy by this sample.

The most common edge is rule 143 output 2 -> rule 137 (196 occurrences):
`Get expr i -> union(Single(Get expr i), SubTuple expr i 1)` followed by
`SubTuple expr x 1 -> Single(Get expr x)`. These are actual executed paths to
prioritize for typed completion analysis. Another 96 events repeat a rule from
their retained ancestry. Neither repetition nor inverse-looking rules prove
that instances, ports, or completion states are equal.

Priority is to recognize repeated completion states and retain the smallest
sufficient result interface, rather than increasing allowed history length.
A scheduled switch could reuse already established constructors across Runs,
provided the source operations prove equal input ports and valid returned
results. Unions, visibility, deletion, mutable reads, and delta ownership remain
live obligations. A loop can consume new values even when its rule IDs repeat.
Do not collapse it based on IDs or digest alone.

Cursor.depth currently increments on every successful continuation independently
of the baked switch state. It is consequently unsuitable as a measure of reusable
results. Before changing winner order, collect candidate min/max/selected depth
per equal-input group, alongside active completion state and retained layout.
Compare shallow/deep alternatives under the same valid completion contract.
For a trained round, split resets into absent edges versus successful compiled
transitions, then separately count result-validation failures. The present trace
cannot establish any of those rates or the causal effect of winner ordering.

This change adds only an offline analysis and saved text results. It neither
changes runtime winner selection nor claims reduced runtime work or speedup.
