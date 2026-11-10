# Match bounded diagnostics to the main runtime configuration

Runtime baseline: `a1f3dcb2`. This changes the standalone Cell CPU's diagnostic
example, not its execution engine or native egglog. It establishes no new
throughput improvement and no general graph sparsity result.

## Correction

The historical `query_prefix ... canonical` command selected `Graph::new` and
did not enable Entry publication ownership. Main throughput runs used
`--repair-ports --entry-publications`. Consequently, the bounded Raytrace
comparisons in cell-point-support, cell-collision-delta and
cell-attribute-locality measured consistent before/after configurations, but
their publication and repair costs did not describe that main configuration.
Their saved results remain unchanged; the sum-bits main-CLI lanes were already
configured correctly. Stable mode has separate automatic ownership setup.

The helper now accepts both flags explicitly and records the requested backend,
flags, Run limit, worker count and grain. Existing positional invocations retain
their behavior. Effective repair configuration and actual Entry use are also
checked from the existing runtime report, rather than inferred from flags.

## What the corrected short execution shows

Both columns below run the same `a1f3dcb2` engine and frozen Raytrace program for
1,280 Runs with four workers and grain 64. This is an existing-feature
configuration comparison, **not a new optimization**.

| Work | Legacy canonical helper | Main configuration |
|---|---:|---:|
| Table queries | 578,591 | 578,591 |
| Shared Entry references | 0 | 88,181 |
| Legacy Entry references | 126,640 | 38,459 |
| History capture reads / writes | 91,617 | 7,729 |
| Shared history slots | 0 | 83,888 |
| History allocations | 40,929 | 40,929 |
| Legacy Entry writes | 295,161 | 111,187 |
| Output registrations | 444,049 | 206,385 |
| Repaired dependencies | 50,374 | 24,519 |

This reuse still costs work: the main configuration records 296,507 Cell output
slot writes and reads, 238,952 output spans, and 205,685 span seals. These counts
are not interchangeable latency units or proof that publication is the current
dominant cost. History allocations do not fall with capture reads. The prefix
does not represent the entire Raytrace execution distribution.

The aligned sum-bits helper has exactly the saved main-CLI final graph, all
1,428 ordered Run records, query/effect counts, repair-port report and selected
history/publication counters. The legacy Raytrace invocation reproduces its
saved graph and ordered Run records. Both Raytrace configurations have the same
final graph, all 1,280 ordered Run records, query counts and actual effects.
These are final graphs and per-Run records, not per-Run graph snapshots.
Sum-bits native choice diagnosis passes unchanged. README compile/run/bench
repeat 1 and the minimal example compile pass; repeat 1 is only a smoke check.

## Consequence for the next optimization

Actual executions already demonstrate reusable history and Entry state. The
large legacy capture count is not an opportunity still open in the main lane.
Likewise, fewer representation operations do not establish sparse dependencies
or guarantee a speedup: the remaining queries and new storage/dispatch must be
included. The last full timing checkpoint predates subsequent runtime changes.

The next candidate should be one observed successful attribute-propagation
fragment: matched constructor/attribute reads, actual update, then the next
scheduled Entry. A combined Cell is useful only if its typed matched inputs,
completed effects and returned witnesses permit removal of an existing query,
handoff or publication within that fragment. Mutable-read validity, late inputs,
delta ownership, retirement and source Run visibility remain live obligations.
An unchanged merge alone does not prove the whole query redundant.

Judge that fragment by the cost of operations it can actually delete, less
boundary checks, storage and dispatch. If most necessary work crosses its
boundary, reconsider the Cell selection. If deletion is small relative to total
execution, it cannot establish a 2x result even with perfect local execution.
Neither outcome proves that all egraphs are intrinsically dense. No new takeover
or cost attribution is claimed by this diagnostic correction.

## Reproduction

Build the runtime and example with `sparse-cells,view-ports,storage-metrics`,
then freeze both binaries before running. Use the cell-fixed-reads frozen input
programs and fresh output directories:

```sh
PREFIX SUM_PROGRAM OUT/sum 2000 4 64 canonical --repair-ports --entry-publications
PREFIX RAY_PROGRAM OUT/ray1280 1280 4 64 canonical --repair-ports --entry-publications
PREFIX RAY_PROGRAM OUT/ray1280-legacy 1280 4 64 canonical
python3 benchmarks/marker-handoff/choice_diagnosis.py OUT/semantic OUT/semantic-acceptance.json
python3 benchmarks/cell-prefix-configuration/collect.py OUT benchmarks/cell-prefix-configuration/results.json
```

The semantic directory uses the reviewed saved native/source exports and the
new sum-bits state as `run-values`. The collector expects the saved
cell-attribute-locality sibling directory. It checks exports without launching
workloads and records input, executable and output hashes.
