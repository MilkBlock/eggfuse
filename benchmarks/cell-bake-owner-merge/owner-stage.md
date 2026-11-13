# Inherit source stage metadata from the existing completed owner

The last selected catalog's actual execution retained 2,177 completed source
records in 307 physical owners. Most sources in an owner have exactly the same
`(started_epoch, recipe_depth)`. Further catalog depth/width experiments retained
those records and increased memory, so the next change removes their repeated
stage state instead of growing another catalog.

A completed source record no longer stores its own epoch and recipe depth.
The existing owner carries the most common exact stage selected when the group
is transferred or extended. Different sources use one sparse exception map keyed
by their stable source IDs. A per-owner exception count lets common owners read
directly without probing that map. The common value is a runtime storage choice,
not a template invariant or inferred equivalence. It is not recomputed merely
because one source retires.

Transfer and extension inspect existing metadata once to choose the common
stage. Extension can change which source inherits and which needs an exception;
it preserves each source's exact values before replacing owner headers. Source
retirement removes its exception. Independent restoration reads the inherited
or exceptional metadata before removing the source. Logical source IDs, native
routes, slot/fact ranges and the existing shared membership layouts remain
unchanged. No consumer subscriptions or new fact graph are introduced.

Fact lifecycle remains independently mutable. An owner's common source epoch
does not overwrite a fact's born epoch, last update or hidden flag. The new
regression merges owners with different common stages, changes one fact's
visibility/update epoch, then deletes and restores individual sources. It
requires both directions of exception conversion and checks the restored
source and fact lifecycles.

## Actual standalone Cell runtime result

The selected `out/cell-takeover-trace/budget128/program.json` and all storage
flags are unchanged. Frozen examples are under `out/cell-owner-stage`.
These are requested-heap measurements, not RSS, timing or upstream egglog.

| Quantity | Before | After |
| --- | ---: | ---: |
| Source record bytes | 80 | 72 |
| Owner record bytes | 80 | 96 |
| Graph bytes | 1,242,855 | 1,233,775 |
| Resident Program bytes | 107,935,263 | 107,935,263 |
| Execution/takeover process heap peak | 113,752,343 | 113,744,261 |
| Maximum extra takeover allocation | 19,568 | 17,776 |

The 9,080-byte net saving includes larger owner headers and exception storage.
There are 81 live stage exceptions in 40 owners (capacity 111), versus the saved
final inventory's theoretical 80-exception optimum: the implementation does not
rebalance groups after retirement. Grouping adds 2,492 metadata reads and 89
exception writes during execution. Common-owner reads use their owner header;
mixed-owner metadata/fact reads also perform an exception lookup. No speedup or
zero-overhead claim is made.

Source frame count, every exported source layout/offset/epoch/depth, physical
owner inventory, routing inventory, logical components and fact lifecycles are
identical to the previous result. This removes repeated stage fields, not live
source identities or fact records. It is a modest Graph reduction, not the full
structural target. Graph remains 39,964 bytes above the historical 30% threshold;
the 3,979,373-byte historical denominator is a working-tree observation, not an
isolated immutable baseline executable. Saturated RHS skipping is unfinished.

## Validation and reproduction

Build examples with `iterative-bake,sparse-cells,storage-metrics`; use the shared
compute queue for all builds, tests and execution. Job 403 passes 218 runtime
unit tests; job 404 passes 69 ownership tests and builds/measures the frozen
examples. Initial compilation jobs 401/402 failed on a missing trait import;
the successful jobs use the corrected source. Final boundary/native/worker
checks are recorded in the adjacent JSON report.

```sh
runtime_storage_peak out/cell-takeover-trace/budget128/program.json MEMORY inherited-owners --port-domains-only --cell-fields --retired-prefixes --state-output STATE
runtime_storage_comparison out/cell-takeover-trace/budget128/program.json CHECKS --completed-owners --retired-prefixes
python3 benchmarks/marker-handoff/choice_diagnosis.py ARTIFACT_ROOT OUTPUT.json
```

The artifact root reuses the previously accepted sum-bits native/source/legacy
exports and sets `run-values/state.json` to the new frozen execution's state.
No semantic exclusions or proof rules were changed.

Final validation: job 405 passes all 882 graph and ordered effect checks, exactly
matching the previous saved checks. Job 407 passes all four native comparisons
with overall `status: pass`, the no-default-feature check, and ownership,
compiler and witness suites under the parallel/storage feature configuration.
Job 408 also passes Cell execution, parallel publication and query-worker tests.
