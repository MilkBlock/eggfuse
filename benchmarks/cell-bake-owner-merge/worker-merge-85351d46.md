# Unify worker witness preparation with the compressed owner runtime

Merge the worker branch through `230b221a` into the compression branch at
`85351d46`. This preserves the completed-owner stage inheritance, passive prefix
retirement and selectable catalog capacity. The compiler conflict is resolved
by supporting both `[MAX_FRAGMENTS]` and `[--reuse-activation]`; a combined test
requires the larger capacity without expanding the seed's activation boundary.

The imported runtime lets worker constructor preparation consult the same
checked witness routes as source execution. A validated prepared result can
feed the existing Cell Entry before allocation of a source instance; it does
not invent `(producer, operation)` result addresses. Typed immutable key proofs
avoid reconstructing proved keys, while unproved keys, current visibility,
forwarding and source identity remain checked. Result capture and observation
reconcile preparation plans rather than repeatedly preparing unusable work.
Catalog source validation is shared, and the audited witness Bake tool can
reuse existing rule Entry/result-capture activation.

## Selected configuration: compression preserved

The same selected sum-bits Program and storage flags give:

| Quantity | Before merge | After merge |
| --- | ---: | ---: |
| Graph requested heap | 1,233,775 | 1,233,775 |
| Resident Program | 107,935,263 | 107,939,647 |
| Execution/takeover process heap peak | 113,744,261 | 113,748,647 |
| Maximum extra takeover allocation | 17,776 | 17,776 |

Source region layouts, lifecycles and logical ownership are identical. All 882
saved Run graph/effect digests and the native semantic contract pass. These are
standalone Cell runtime measurements; no new speed or upstream egglog claim is
made. The selected Program remains unchanged and Graph is still 39,964 bytes
above the historical 30% threshold. The historical denominator remains a
working-tree observation, not an isolated immutable baseline binary.

The new passive trace also passes all 882 saved checks and has the same final
ownership inventory as unobserved execution. It contains 1,484 continuation
proposals and 720 witness recipes. Observation is diagnostic, not measured
production work. Its preparation reconciliation is not evidence that observer
counters or execution costs equal unobserved costs.

## Witness batch: not admitted as an optimization

Compile two catalogs from that one audited trace, using the imported
`bake_observed_witnesses`, with and without `--reuse-activation`. Run both with
the same frozen storage binary. Their final graph digests and Run sequences
match, but neither receives a candidate per-Run or speed admission here.

| Quantity | Seed | All observed routes | Existing activation only |
| --- | ---: | ---: | ---: |
| Witness recipes | 0 | 720 | 567 |
| Graph bytes | 1,233,775 | 1,233,775 | 1,233,775 |
| Resident Program bytes | 107,939,647 | 109,912,023 | 109,505,621 |
| Candidate-domain queries | 11,424 | 11,015 | 11,038 |
| Domain signal visits | 149,672 | 143,673 | 144,380 |
| Route address checks | 0 | 4,195 | 4,153 |
| Accepted route witnesses | 0 | 428 | 404 |
| Created source Cells | 2,688 | 2,688 | 2,688 |
| Result publication writes | 1,166 | 1,166 | 1,166 |
| Transient writes | 137 | 137 | 137 |

The bounded variant avoids activating 153 recipes, but adds thousands of
address checks to remove 386 candidate-domain queries. Only 27 host admissions
prove keys statically. Query counts do not establish elapsed-time improvement,
and neither catalog reduces source instances or publication work. Do not count
accepted witnesses as skipped rules or removed committed mutations. Neither
experimental catalog replaces the selected configuration. Whole completed-Cell
handoff, rather than more per-constructor attempts, remains the missing step;
saturated RHS skipping is unfinished.

## Validation and reproduction

Job 410 passes four incremental selector tests and two witness Bake tests.
Job 411 passes 236 runtime tests, ownership/compiler/witness/query-worker/
parallel-publication/Cell-execution suites, and the no-default-feature check.
It freezes examples in `out/cell-worker-merge`. Job 413 runs the 882-boundary
comparison, generates the audited trace, and passes all four native comparisons.
Job 414 measures the witness batch; the JSON records exact artifact hashes and
work counts. All jobs use the shared compute queue. Raytrace performance is not
remeasured by this merge validation.

Build examples with `iterative-bake,sparse-cells,storage-metrics`. Under the
shared compute queue, reproduce the selected comparison and trace as follows:

```sh
runtime_storage_comparison out/cell-takeover-trace/budget128/program.json CHECKS --completed-owners --retired-prefixes
runtime_catalog_trace out/cell-takeover-trace/budget128/program.json CHECKS TRACE --completed-owners --retired-prefixes
bake_observed_witnesses out/cell-takeover-trace/budget128/program.json TRACE ALL_DIR
bake_observed_witnesses out/cell-takeover-trace/budget128/program.json TRACE ACTIVE_DIR --reuse-activation
```

For each output Program use `runtime_storage_peak` with `inherited-owners`,
`--port-domains-only --cell-fields --retired-prefixes --state-output STATE`.
Native acceptance uses the existing `choice_diagnosis.py` contract and saved
native/source/legacy exports. No proof exclusions are broadened.
