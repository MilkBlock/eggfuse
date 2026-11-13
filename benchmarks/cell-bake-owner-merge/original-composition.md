# Learn logical composition on the original workload

The original 1,428-Run target and its receipt-omitted regeneration both have
2,174 final logical components, all single-frame, with **zero compiled ownership
transitions**. Both retain 8,930 signal slots, 7,320 bound. Their compact physical
owners do not establish cross-stage logical composition. Earlier four-case
pass3 catalogs belong to different artifacts; their admission results cannot
be credited to this original source.

`extend_observed_owners` now supports the implicit singleton catalog as a seed.
It first checks that the passive trace passed the saved Run audit and has the
same source digest. An absent fragment selection means an empty transition
language, not missing singleton templates. The helper chooses the matching
legacy/current address schema, retains existing selected paths, and lets the
typed loader check every added Entry substitution. It never imports instance
IDs or invents equality from observation frequency. Two selector tests pass,
including rejected unaudited/wrong-source traces and both address versions.

## First audited observation and batched selections

Job 286 runs the actual original Program against saved graph and ordered
RHS/write/resume hashes at every Run: all **1,428 checks pass**. It observes
1,159 one-hop candidates; 449 have repeated births and shared-input evidence.
There are 5,606 `transition_not_baked` anchor attempts. Alternatives overlap:
these are not 5,606 unique applications or saved effects.

Jobs 288–289 compile three catalog budgets from this one saved trace and run
them with the same frozen memory binary and completed-owner/port-domain/Cell-field
configuration. Source core remains identical in every candidate. All final
state digests match the original accepted execution.

| Selection | Live components | 1/2/3-frame components | Signal slots | Graph bytes |
| --- | ---: | --- | ---: | ---: |
| Original | 2,174 | 2,174 / 0 / 0 | 8,930 | 2,038,485 |
| 32 transitions | 1,830 | 1,449 / 381 / 0 | 8,495 | 2,061,377 |
| 128 transitions | 1,650 | 1,026 / 624 / 0 | 8,462 | 1,952,405 |
| 256 transitions, first trace | 1,596 | 906 / 690 / 0 | 8,408 | 1,958,325 |
| 256 transitions, two observations | 1,453 | 857 / 306 / 290 | 8,344 | 1,949,501 |

The 32-transition catalog loses memory despite reducing components. The
128-transition catalog saves 86,080 bytes; adding more first-trace candidates
does worse. This rejects component count and matched-input savings as sufficient
memory acceptance metrics. Against original, the 128 catalog's Cells field grows
51,032 bytes, while components fall 101,728, lifetime records 16,384, boundary
storage 17,976, and temporary ownership heap 1,024 bytes. Template constants and
resident Program are measured separately in `original-composition.json`.

## Learn again from actual composed execution

Job 291 observes the 128-transition candidate, again passing all 1,428 saved
Run graph/effect checks. There are 709 joined births, **671 cross-stage**.
Its 1,291 proposals include 541 two-hop paths that the singleton execution could
not expose. Job 292 adds 128 selected paths while retaining all seed transitions.
The loader verifies the old transition set is still a subset of the new set.

The resulting three-frame components demonstrate iterative learning and actual
cross-stage completion. However, they save only another **2,904 bytes**, for
88,984 bytes total against original. Smaller logical component counts do not
remove their retained source frames and facts. Relative to round one, the Cells
field falls 2,768 bytes, components grow 3,248, and boundaries fall 3,384. More
depth alone is therefore not an adequate route to the compression target.
Next work should remove redundant retained source state/maintenance within the
proved combined template rather than simply add another depth round. Unknown
external consumers, nontrivial union, source-sized restoration, visibility,
delta ownership and original effect ordering remain live obligations.

These catalogs retain diagnostic apply receipts. Their savings must not be
added to the receipt-omission measurement without running a combined artifact.
The original denominator and 30% target remain unchanged. The best observed
receipt-omitted Graph is still 1,925,591 bytes; no new overall best or completed
saturated RHS skip is claimed here.

## Reproduction and proof coverage

Build `runtime_catalog_trace` and `extend_observed_owners` with
`iterative-bake,sparse-cells,storage-metrics`, using the shared compute queue.
Use the frozen `runtime_storage_peak` configuration documented in
`application-receipts.md`. Exact operation sequence:

```sh
runtime_catalog_trace ORIGINAL SAVED_RUN_CHECKS TRACE
extend_observed_owners ORIGINAL TRACE 128 ROUND1
runtime_storage_peak ROUND1/program.json ROUND1/memory.json inherited-owners --port-domains-only --cell-fields --state-output ROUND1/state.json
runtime_catalog_trace ROUND1/program.json SAVED_RUN_CHECKS ROUND1/trace.json
extend_observed_owners ROUND1/program.json ROUND1/trace.json 128 ROUND2
runtime_storage_peak ROUND2/program.json ROUND2/memory.json inherited-owners --port-domains-only --cell-fields --state-output ROUND2/state.json
```

For the first-trace budget comparison repeat selection with 32 and 256 into
separate directories, using the same original trace. Full per-Run proof covers
the original and round-one catalog. Other candidates have final-state equality;
this is not a substitute for their own Run-boundary proof. No timing campaign or
new native workload contract is introduced. Generated artifacts and traces stay
under ignored `out/cell-original-composition`; hashes and measurements are saved
in `original-composition.json`.
