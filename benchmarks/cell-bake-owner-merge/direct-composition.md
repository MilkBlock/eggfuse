# Compose the direct-source workload from its own executions

This continues the direct-source experiment after route definitions were shared
in `55f5fd9a`. The typed source and source Runs are unchanged. No marker is added,
and no default execution policy changes. These measurements run the actual
standalone Cell CPU, not native egglog or a layout-only prototype.

## Observation before selection

Job 316 compares ordinary storage with completed owners, port domains and Cell
fields at all 882 Runs. Exported graphs and ordered RHS/write/resume audits agree
at every boundary. Its final export equals the previously accepted direct-source
export. This proves the storage takeover on this source; it does not establish
per-Run equivalence between the differently scheduled marked and direct sources.

One subsequent passive observation is checked against those saved boundaries.
It provides 1,193 ownership proposals, 464 with repeated births and shared-input
evidence. Alternative anchors overlap: their birth counts are not additive
savings. All 2,177 final logical components in the seed are single-frame.

The same observation exposes two different notions of history:

- Cursor history contains 3,241 events, all uncompiled roots, with no parent
  edges and no dropped events. This artifact has neither `spine_blocks` nor
  `iterative_bake`; the absence of cursor ancestry cannot establish absence of
  cross-stage data reuse. It is not a useful deep-history training set yet.
- Successful immutable-constructor matches expose 4,021 connected multi-source
  applications. Of these, 3,024 involve two components and 810 involve three.
  Those are actual matched relationships, with typed query slots available to
  prove aliases. They do not prove that all involved facts can be retired.

Pre-apply observation finds only 254 fully covered RHS applications out of 6,532:
222 covered by inputs and 32 by a local component. The dominant failure is
`missing_local_constructor` (4,772), followed by writes (931), unsupported
primitive proofs (341), nontrivial unions (157) and visibility effects (75).
These categories describe the current local observer, not global impossibility.
Installing only already-full local cases cannot cover the dominant workload.

## Batched selection from that one trace

Job 318 selects budgets 32, 128 and 256 without rerunning training between them.
The existing loader re-proves every Entry substitution. The same frozen memory
binary and flags measure all three; their final exports are exactly equal.
Job 321 additionally checks the 128-path candidate with completed-owner takeover
against the direct-source control: all 882 Run graphs and ordered audits pass.

| Selected paths | Live components | Signal slots | Graph bytes | Graph saving |
| --- | ---: | ---: | ---: | ---: |
| 0 | 2,177 | 8,830 | 1,545,531 | — |
| 32 | 1,839 | 8,437 | 1,569,727 | -24,196 |
| 128 | 1,643 | 8,359 | 1,448,995 | 96,536 |
| 256 | 1,584 | 8,273 | 1,457,431 | 88,100 |

The 128-path candidate saves 6.25% of the current Graph. Relative to the historical
3,979,373-byte denominator it retains 36.4%, still 255,184 bytes above the
1,193,811-byte target. That historical denominator remains a working-tree
observation rather than an isolated immutable-binary control.

Its components field saves 102,336 bytes; lifetime records save 16,384 and boundary
storage 16,968. The Cells field **grows 40,176 bytes**. More paths reduce component
count further but do not improve total Graph storage. This again rejects
component count or depth alone as an acceptance metric.

The Cells regression has a concrete cause: physical storage owners grow from
306 to 768 and their records from 166,748 to 210,080 bytes, although stored scalar
slots and retired entries decrease. `transfer_completed_storage` pools newly
completed short components, but an already transferred prefix takes the extension
path. If that prefix shares an owner with unrelated siblings, flattening correctly
refuses to copy those siblings. `extend_completed_segments` then creates a separate
owner for each new suffix. Logical composition therefore defeats batching of the
newly completed suffixes. The next bounded change can pool those suffixes across
components while retaining the existing source directory and untouched prefix
slices; it must not introduce nested owner records or move unrelated siblings.

Retained Program grows from 105,884,383 to 106,675,058 bytes. Thus total retained
Graph + Program grows 694,139 bytes despite the Graph saving. No total-memory or
speed improvement is claimed. New selection probes, migration, peak allocation
and still-required source records remain charged by the existing runtime tools.

The next structural target is the source-frame and boundary state retained inside
combined components, including jointly matched sources outside one producer
chain. Further depth alone is not justified by these measurements. Typed source
facts, live actual results, residual guards, mutable reads, delta ownership,
source Run ordering, generation checks and source-sized union restoration must
survive any elimination. Cursor-history seeding must use the already observed
successful Entries, not fictional apply paths inferred from equal values.

## Reproduction and acceptance scope

Use the exact compact direct-source Program and frozen examples in
`out/cell-route-definitions` / `out/cell-direct-composition`. All commands run
under the shared compute lease; these are not timing measurements.

```sh
runtime_storage_comparison PROGRAM checked.json --completed-owners
runtime_catalog_trace PROGRAM checked.json trace.json --closure-history 100000
extend_observed_owners PROGRAM trace.json BUDGET budgetBUDGET
runtime_storage_peak budgetBUDGET/program.json budgetBUDGET/memory.json inherited-owners --port-domains-only --cell-fields --state-output budgetBUDGET/state.json
runtime_storage_comparison PROGRAM budget128/checked.json budget128/program.json --completed-owners
python3 benchmarks/cell-bake-owner-merge/direct_composition.py out/cell-direct-composition out/cell-route-definitions/plain-memory.json out/cell-route-definitions/plain/program.json benchmarks/cell-bake-owner-merge/direct-composition.json
```

The generated summary checks source/recipe identity, exact final state and trace
completeness. Its per-candidate audit flag distinguishes completed Run checks
from final-state-only evidence. The frozen command for job 321 binds the
128-path check to its candidate: the older comparison report itself records
the control digest, not a separate optimized Program digest. The 32/256-path candidates have no
fresh full per-Run audit. No semantic exclusions or proof rules are changed.
