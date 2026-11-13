# Restore the original compression denominator

The original runtime compression request followed the capacity-only comparison
in `benchmarks/cell-trail-depth/runtime-storage-comparison.json`. That comparison
used Program `795f5d438ffd69517efd58bae3f534811892141135f5f40ecdf63618e90345e1`,
1,428 source Runs and `out/cell-local-writes/semantic/sum-legacy/program.json`.
Its Graph-owned requested heap before capacity reclamation was 3,979,373 bytes.
The original report explicitly describes a working-tree observation, not an
isolated immutable binary baseline. This qualification still applies.

Recent four-workload pass3 measurements use a different sum-bits artifact and
882 Runs. Those measurements support their own before/after changes, but cannot
be substituted for the original denominator. The goal budget is therefore
1,193,811 whole bytes (floor of 30% of 3,979,373), not 30% of the latest pass3
snapshot and not 30% of a selected storage subtotal.

## Current original-source observation

The current runtime at `2232ef9b` executes the unchanged original artifact with
completed owners, port-domain-only matching and Cell fields. Its final Graph
heap is **2,038,485 bytes**, or **51.23%** of the original observation. The remaining
gap to the retained-memory target is **844,674 bytes**. This is cumulative progress,
not a claim that the last edit saved the difference. Program and Executor memory,
RSS and allocator overhead remain excluded. Fast saturated-stage RHS generation
is a separate unfinished requirement; passing a byte threshold would not prove it.

The original-source field sizes now include Cells 379,982, components 372,256,
functions 334,920, boundaries 242,264 and source positions 163,584 bytes. Function
records are substantially larger than in the recent pass3 snapshot. Thus the
next optimization priorities must include this original workload rather than
extrapolate from the smaller artifact.

## Validation and reproduction

`runtime_storage_comparison` now accepts a final `--completed-owners` argument.
The default capacity-only comparison is preserved. In the new mode it compares
the ordinary local-congruence runtime against completed owners with port domains
and Cell fields, checking graph exports and ordered RHS/write/resume digests at
every Run and on terminal execution. It keeps the original Run/effect checks;
there is no additional ignored table or weakened equality condition.

The separate one-lane `runtime_storage_peak` observation supplies the current
retained heap and process high-water measurements. The paired comparison supplies
Run-by-Run evidence. Process high-water includes Program memory and is not a
Graph-only peak. This is actual standalone Cell runtime validation, not native
egglog acceptance or a speed test.

Build these examples with `iterative-bake,sparse-cells,storage-metrics,eggfuse-cell-runtime/slot-transfer-audit`.
All builds and executions use the shared compute queue. The exact invocations are:

```sh
runtime_storage_peak out/cell-local-writes/semantic/sum-legacy/program.json out/cell-original-target/candidate.json inherited-owners --port-domains-only --cell-fields
runtime_storage_comparison out/cell-local-writes/semantic/sum-legacy/program.json out/cell-original-target/checked.json --completed-owners
python3 benchmarks/cell-bake-owner-merge/original_target.py benchmarks/cell-trail-depth/runtime-storage-comparison.json out/cell-original-target/candidate.json out/cell-original-target/checked.json benchmarks/cell-bake-owner-merge/original-target.json
```

The summarizer rejects different Program identities, Run counts and incomplete
Run comparisons. It does not silently substitute a newer baseline denominator.

## Next compiler opportunity from this source

The typed source core declares 107 `CellSpineApplied*` tables. References in its
rules occur only in heads (130 occurrences), with no body references. At the end,
18 such tables hold 264 function rows and 264 retained origins. These are old
apply-receipt materializations, rather than constructor payloads. These counts
alone do not authorize deletion: compiler provenance, reads in initial/schedule/
merge/assertion contexts and observable effects must be checked. Name prefixes
alone are not proof. The existing semantic contract treats internal marker
history separately, but its acceptance rules must not be broadened for this edit.

A useful next compiler change should prove which diagnostic writes have no
consumer and remove their publication and retained state, rather than converting
them to another fact representation that retains all the same obligations. The
previous generic Unit-fact conversion already lost its memory gate; it should
not be repeated without removing work.

Job 264 completed: all 1,428 Run checks plus terminal execution agree. In the
same current binary, ordinary Graph storage is 3,272,085 bytes and completed-owner
storage is 2,038,485 bytes; the latter exactly matches the separate one-lane
measurement. Three denominator/completeness tests pass (job 265).
