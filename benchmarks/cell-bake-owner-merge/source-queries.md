# Remove query-marker materialization on the same original source

The completed-parent path already leaves zero parent links in the measured
round-two Graph. Further parent-chain detachment cannot explain the remaining
storage. Function records still include query-marker rows, origins and indexes:
`CellSpineView8`, `CellSpineView28` and `CellSpineView9` alone hold 455 rows.
These are maintained materializations of positive queries, not constructor
facts made smaller by combining ownership templates.

This experiment uses the **same reconstructed structural-key source** from the
receipt experiment. That experiment's marked regeneration has exactly the
original artifact's typed core and recipe. The existing `emit_cell_source`
example lowers its `source_sk.egg` directly through the ordinary Cell compiler,
without marker selection, marker publication or apply receipts. The emitted
source is byte-identical to that input. No facts are deleted from a running graph
by a table-name prefix. Ordinary source queries and effects remain authoritative;
there is no new hidden fact graph or parallel binding representation.

The current seed has no learned ownership transitions. Reusing prior catalog
IDs would be unsafe after changing query/effect coordinates. Its actual execution
must supply future training. This experiment tests whether eliminating the
materialization itself can remove significant storage before adding more Bake
templates; it does not establish saturated query skipping or a new default.

## Actual retained memory and semantic acceptance

Job 299 emits and runs the plain source. Job 300 uses the unchanged
`choice_diagnosis.py`; all four comparisons pass. Native references are the
reviewed saved exports, `cpu_legacy` is the original marked execution, and
`cpu_values` is this direct-query execution. Those are validator input labels;
no new values-handoff or native omitted lane is claimed.

Job 301 uses one frozen runtime to observe both artifacts with completed owners,
port domains and Cell fields:

| Mode | Runs | Graph bytes | Retained Program bytes | Live function rows |
| --- | ---: | ---: | ---: | ---: |
| Original marked | 1,428 | 2,038,485 | 115,168,530 | 1,150 |
| Direct source queries | 882 | 1,545,531 | 150,970,020 | 311 |

Graph saves **492,954 bytes (24.18%)** against the current original artifact,
or 380,060 bytes against the receipt-only omission candidate. Functions save
234,624 bytes, reverse uses 92,040, Cells 61,960, function keys 42,268, with
smaller changes recorded in `source-queries.json`. The plain candidate's Graph
is 38.84% of the historical 3,979,373-byte original denominator, still 351,720
bytes above the 30% target. This is a candidate with the proof limits below,
not an assertion that the full cross-stage goal is achieved.

Crucially, **resident Program grows by 35,801,490 bytes**. Process requested-heap
high-water also grows, from 122,484,796 to 157,093,655 bytes. Removing markers
exposes larger compiled source queries. These resident plans cannot be dismissed
as offline compiler memory. This is therefore **not** a total runtime-memory
improvement or a reason to disable markers by default. No speed was measured.

## Account for the different Run count

The memory observer now records each executed ruleset, loop-iteration tuple,
match/binding counts and changed flag after measurements. It does not add
observation work inside the measured execution. `source_query_audit.py` aligns
ruleset names and actual work counts, allowing only deletion of the exact
reserved `cell-spine-complete` ruleset and zero-work unchanged source Runs.
Using work counts in the alignment avoids confusing an active saturation
iteration with its trailing idle iteration. Three tests check this ambiguity,
rejected live-Run removal, changed work and inserted source Runs (job 303).

The 546-Run difference consists of 543 generated completion Runs and three
idle source Runs (`drop`, `terms-helpers`, `terms-helpers-helpers`). All 882
remaining source Runs align with identical match and executed-binding counts:
6,532 total each. One `non-weakly-linear` changed flag goes from true to false.
This is work/schedule evidence, **not per-Run graph-state equivalence**, and loop
iteration paths are not asserted equal. Final-state acceptance cannot replace
the remaining Run-boundary graph checks for a production policy change.

The older 882-Run pass3 artifacts have different typed cores and recipes from
this freshly emitted source. Their memory results and learned catalogs remain
separate. The equal Run count does not authorize substituting their measurements.

## Reproduce

Use the source reconstruction from `application-receipts.md`, then run under
the shared compute queue:

```sh
emit_cell_source MATERIALIZED/source_sk.egg PLAIN
runtime_storage_peak ORIGINAL MARKED_MEMORY inherited-owners --port-domains-only --cell-fields
runtime_storage_peak PLAIN/program.json PLAIN_MEMORY inherited-owners --port-domains-only --cell-fields --state-output PLAIN_STATE
python3 benchmarks/cell-bake-owner-merge/source_query_audit.py MARKED_MEMORY PLAIN_MEMORY ALIGNMENT
python3 benchmarks/marker-handoff/choice_diagnosis.py SEMANTIC_BUNDLE SEMANTIC_RESULT
```

Build both examples with `iterative-bake,sparse-cells,storage-metrics`. Preserve
the original program in the semantic bundle's `sum-legacy/program.json` slot;
the supported source-contract hash is unchanged. Saved native exports and the
documented CPU lane mapping form the rest of that bundle. All generated programs,
states and detailed memory observations remain under `out/cell-source-query`.
The committed report records input, executable and result hashes.
