# Wider catalogs do not yet retire source state

The actual 81-extension catalog was observed with completed-owner takeover and
prefix retirement. All 882 saved Run graph and ordered effect digests match
(job 391). Its 1,464 proposals include 421 four-hop paths. At the old capacity,
340 otherwise eligible proposals were rejected. The loader already supports an
explicit `max_fragments` up to 4,096, but the incremental selector hardcoded 256.

The selector now honors the seed's capacity and accepts an optional explicit
capacity after the output directory. It validates source binding before changing
the artifact, rejects capacities below the existing seed size and outside the
loader's supported interval, and still checks preservation of every seed
transition through the loader. The three selector tests pass, including wider
admission, inherited capacity, and rejection of a narrowed or excessive limit.
The batch driver accepts the same optional capacity.

## Actual batch result: reject all new catalogs

The existing selected graph is 1,242,855 bytes. The same frozen runtime and
storage flags measure all variants. The following values are Graph requested
heap bytes, not runtime speed, RSS or upstream egglog measurements.

| Selection budget | Capacity 256, deeper paths | Capacity 512 | Capacity 1,024 |
| --- | ---: | ---: | ---: |
| 32 | 1,246,523 | 1,246,671 | 1,246,671 |
| 128 | 1,254,095 | 1,251,591 | 1,251,591 |
| 256 | 1,254,095 | 1,252,975 | 1,252,975 |

Capacity 512 and 1,024 choose the same paths for these budgets, so increasing
the bound further is not useful here. Every variant has the same final graph
digest and source Run sequence. None is admitted: no additional per-Run or
native semantic campaign is needed for rejected candidates. Current selected
Program and its earlier full acceptance remain unchanged.

The depth-128 result reduces components from 1,280 to 1,223 but raises signal
extent from 7,555 to 7,608 and component storage from 218,240 to 224,288 bytes.
The width-256 result has 1,241 components and 7,617 signals. All retain 2,177
completed source records. Group count alone is therefore a misleading measure:
these transitions merge directories while retaining source interfaces, extra
signal extent and allocation slack. Resident Program also grows (see JSON).

## Next structural opportunity, not an implemented saving

Join the saved completed-region source metadata by existing physical owner.
There are 2,177 source frames in 307 owners, but only 352 distinct owner/stage
pairs, where stage means the exact `(started_epoch, recipe_depth)` tuple.
Only 39 owners mix stages. Choosing each owner's most common stage leaves 80
source exceptions. Thus source-stage metadata is mostly duplicate state in
existing owners; it does not require speculative static equality assumptions.

A future takeover can retain the common stage once in the existing owner and
preserve differing sources explicitly. It must handle mixed-stage extension,
independent source deletion, restoration and stable FactRef lifecycles, charge
exception storage and lookup costs, and avoid a new consumer dependency graph.
This census is not a claim that source records can simply be deleted, nor that
stage inheritance has already been implemented. It is preferable to another
blind depth expansion. Saturated RHS skip remains unfinished.

## Reproduction

Use the shared compute queue and build `extend_observed_owners` with
`iterative-bake,sparse-cells,storage-metrics`. Run `runtime_catalog_trace` on the
selected `out/cell-takeover-trace/budget128/program.json`, against its saved
`checked.json`, with `--completed-owners --retired-prefixes`.

For each capacity 512 and 1024, create a fresh output root with `trace.json`
pointing to that audited trace, then run:

```sh
python3 benchmarks/cell-bake-owner-merge/takeover_trace_batch.py OUTPUT_ROOT out/cell-takeover-trace/budget128/program.json out/cell-takeover-trace/budget128/memory.json /private/tmp/eggfuse-dual-local-target/debug/examples/extend_observed_owners out/cell-component-reuse/runtime_storage_peak CAPACITY
```

Omit CAPACITY for the existing 256-path control. Jobs 393 and 398 contain the
batches; the adjacent JSON records their output and the next-state census.
