# Cross-stage routes reuse Cell definitions

The same-source no-marker experiment grew retained Program by 35.8 MB. Field
accounting showed ordinary Cell query storage actually decreased slightly.
Growth was concentrated in `artifact` JSON and `multi_stage`: repeated route
annotations and repeatedly copied producer operands. This corrects the broad
earlier attribution to larger compiled queries.

Three changes remove redundant representations without a new packed format:

1. The compiler no longer emits each route's `residual` array. The consumer
   query minus the checked anchor and steps defines exactly that set.
2. It no longer emits each step's `assignments`. These follow from the original
   producer Site operands and consumer pivot. Runtime matching already binds
   through the common Cell query; its retained assignment vectors had no reader
   and are now removed too.
3. Local reads of the same `(producer, Site)` share an immutable operand vector.
   A temporary loading dictionary interns these definitions and is then dropped;
   no per-instance subscription, binding store or permanent lookup map is added.

Existing artifacts remain accepted. Explicit old `assignments` and `residual`
annotations are still derived and checked during loading. A forged slot or
incorrect residual still fails. New artifacts do not allocate those temporary
vectors when the annotation is absent. All typed relation binding, alias proof,
actual-returned-receipt checks, residual enumeration, stage gates and visibility
checks remain unchanged. No source Run or logical RHS effect is skipped.

## Measured retained memory

The direct-query artifact differs from its prior generation **only** by removing
those derived annotations and updating the digest. All 11,113 routes remain.
One current runtime binary runs this candidate and the unchanged original marked
artifact under completed owners, port domains and Cell fields.

| Artifact | Program before | Program after | Saving |
| --- | ---: | ---: | ---: |
| Direct query, newly emitted wire | 150,970,020 | 105,884,383 | 45,085,637 |
| Original marked, old wire retained | 115,168,530 | 113,576,794 | 1,591,736 |

For the direct-query lane, `artifact` saves 41,094,069 bytes and `multi_stage`
saves 3,991,568. Graph fields are exactly unchanged, as are actual Run sequences,
match/binding counts, logical ownership and ownership query work. Final export
files are byte-identical to the previously accepted states. These are actual
standalone runtime allocations, not a standalone serialization prototype.
Process requested-heap peak in that lane falls from 157,093,655 to 112,008,121.

## Equally compact marker control

Comparing new compact wire against old marked wire would overstate the benefit
of removing markers. The existing `recompile_cell_routes` helper also recompiles
the regenerated materialized marker artifact. It checks every other compiler
component unchanged and validates the resulting Program. All 6,825 marked routes
remain. The same runtime binary then measures both compact-wire configurations:

| Mode | Graph bytes | Program bytes | Process requested-heap peak |
| --- | ---: | ---: | ---: |
| Marked, compact routes | 2,040,453 | 104,176,676 | 111,469,561 |
| Direct queries, compact routes | 1,545,531 | 105,884,383 | 112,008,121 |

Direct queries retain 1,707,707 additional Program bytes while saving 494,922
Graph bytes. They still do **not** win total retained memory or process peak in
this fair comparison. Default marker emission remains unchanged. The compact
marker control has no historical admission/Bake attachment, matching the
direct-query generation; it is distinct from the original frozen artifact.

The large obsolete-plan cost is removed, but cross-stage routes still dominate
the remaining plan difference. Future selection/sharing must preserve the full
ordinary-query fallback and be justified by actual route use, not mere possible
connectivity. Program savings do not count toward the 30% Graph target.

## Validation and reproduction

18 compiler library tests, 19 compiler integration tests, 13 witness tests and
four offline route-analyzer tests pass (jobs 305, 309, 311, 312). New tests cover
valid legacy residual annotations, rejected forged residual/slot annotations,
and actual pointer sharing across two consumers of the same producer Site.
The pointer-sharing fixture initially had no repeated route source; a second
consumer was added so the test verifies sharing rather than passing vacuously.
The offline RHS route analyzer now derives residuals from consumer queries when
the redundant array is absent; it does not treat absence as full coverage.

Full-workload per-Run graph equivalence has not been rerun. Final states are
byte-identical to the existing semantic acceptance inputs, and recorded Run
sequences/work agree; those checks are reported at their actual scope. No speed
claim is made. The Graph compression and saturated-stage RHS goal remains open.

Rebuild `emit_cell_source` and `runtime_storage_peak` with the documented
`iterative-bake,sparse-cells,storage-metrics` configuration. Re-emit the exact
`source_sk.egg` from the preceding experiment. For the fair marked control:

```sh
recompile_cell_routes MATERIALIZED_PROGRAM MARKED_COMPACT ROUTE_AUDIT
runtime_storage_peak MARKED_COMPACT MEMORY inherited-owners --port-domains-only --cell-fields --state-output STATE
```

All builds/runs use the shared compute queue. Detailed outputs stay under
`out/cell-route-definitions`; `route-definitions.json` records hashes, checks,
field deltas and both comparison scopes.
