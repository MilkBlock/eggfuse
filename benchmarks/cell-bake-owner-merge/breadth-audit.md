# Broader passive Bake does not provide structural compression

This iteration learns from the four installed catalogs' saved successful Entry
observations together. No trace input is retrained and no runtime representation
is changed. The selector now accepts explicit budgets in 1..4096, retaining its
old 64/256 defaults. Budget 4096 removes the previous small selection cap; actual
finite input filtering admits 552 new paths, yielding 726 maximal paths after
prefix deduplication. All original compiled transitions remain present.

The pool canonicalizes static rule definitions and port programs, not eclass IDs.
It sees 3,017 proposals, 1,368 portable to all inputs; repeated-use/shared-input
filters and one alternative per source history/consumer reduce this to 552.
The new paths have 1--12 hops (63 one-hop, 241 two-hop). This is a breadth
experiment over observed histories, not a newly generalized suffix matcher.
Types, source order, mutable effects, foreign result identities and restoration
boundaries remain authoritative. Observed opportunities are not saved work.

## Validation and result

All four compilers verify typed transitions and preservation of the seed graph.
All 2,652 saved per-Run graph/RHS/write checks and four terminal checks pass.
Five selector tests pass. These are standalone Cell runtime checks, not native
egglog semantic acceptance or a timing result. Concurrent query-worker edits in
the shared worktree were not built into the frozen binaries or committed here.

Storage uses the same frozen `runtime_storage_peak` binary for each seed and
candidate, with `inherited-owners --port-domains-only`. The report verifies program
identity, full Graph teardown accounting, final states and audited Run counts.
The diagnostic observer and storage runner are separate: tracing allocations
are not included as compression costs. The retained Program is reported separately
and also added to Graph bytes; it is runtime-resident, not purely offline cost.

| case | Graph bytes before | Graph bytes after | change | ordinary source records | shared completed frames |
| --- | ---: | ---: | ---: | --- | --- |
| fact | 705,175 | 700,103 | -0.72% | 362 → 326 | 391 → 427 |
| loopfact | 616,289 | 612,865 | -0.56% | 358 → 330 | 333 → 361 |
| sum-bits | 1,830,387 | 1,806,979 | -1.28% | 881 → 729 | 1,299 → 1,451 |
| dot-product | 1,798,019 | 1,776,883 | -1.18% | 975 → 864 | 1,161 → 1,272 |

Every reduction in ordinary source record count has an equal increase in shared
completed frame count in these snapshots. Total composition frame counts change
778→782, 707→706, 2,371→2,396 and 2,268→2,266. More frames enter the compact store,
but the number of independent source identities is effectively unchanged.
Components decrease, yet their allocation footprint grows slightly; the shared
shape directory adds 4,296 Graph bytes in every case. This confirms that the
current takeover moves records more effectively than it eliminates them.

Retained Program grows about 2.285 MB per input, exceeding Graph savings; total
Graph-plus-Program heap and measured execution peak increase. Dot-product's
maximum takeover temporary allocation also increases from 22,968 to 26,664 bytes.
**Do not enable this larger catalog as a successful runtime compression result.**
No speed claim is made. The target of reducing runtime egraph to 30% is unmet.

The new admission trace confirms higher cross-stage join counts (328/271/1274/1076),
but many subsequent transitions remain absent. Full-history keys can change when
an earlier composition succeeds; this is a possible explanation, not established
by these aggregated counters. Further learning needs actual missing transition
keys, not more increases to the catalog budget alone.

The structural next step is to identify which source-frame metadata and fact
identities the existing shared shape can supply, retaining small restoration
slices and live external references. Deleting a source record while creating an
equivalent completed-frame record must not count as eliminated instance state.
A completed saturated region may skip subsequent work only under its typed
conditions and source Run/effect boundaries; neither a large Cell nor a root-tuple
match is such a certificate.

## Reproduction

Interfaces copied from the saved four-case learning batch are checked against
the current rules/tables and source digest by the pooling tool. Keep inputs and
outputs under `out/`; generated programs/binaries are not committed.

```sh
python3 benchmarks/cell-batched-learning/passive.py out/cell-bake-owner-merge/batch 4096
target/debug/examples/batch_cell_learning apply-passive out/cell-bake-owner-merge/batch passive/budget4096
target/debug/examples/batch_cell_learning check-passive out/cell-bake-owner-merge/batch passive/budget4096 witness-trace
python3 benchmarks/cell-bake-owner-merge/admission_results.py out/cell-bake-owner-merge/batch/passive/budget4096 benchmarks/cell-bake-owner-merge/breadth-admissions.json
```

For each case, run the frozen storage binary on the seed `CASE/candidate.json`
and `passive/budget4096/CASE/candidate.json`, writing `CASE-seed.json` and
`CASE-breadth.json` under `out/cell-bake-breadth`. The committed storage report
records the frozen binary digest from that directory's `binary.json`.

```sh
python3 benchmarks/cell-bake-owner-merge/breadth_results.py out/cell-bake-breadth out/cell-bake-owner-merge/batch benchmarks/cell-bake-owner-merge/breadth-results.json
```
