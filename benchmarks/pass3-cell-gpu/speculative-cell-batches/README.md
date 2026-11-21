# Private physical Cell batches before source verification

The native CPU backend accepts a vector of forecast counts for the compiler-selected rule templates. At a Run boundary, the source scheduler has already selected its active rule set and advanced the epoch. Before even one new parent is checked, the native forecast evaluates every active rule with the same weights. If their integer predictions exceed the global cap, largest-remainder apportionment distributes that cap across the whole vector; source order resolves ties. One contiguous private buffer holds those template-specific record slots. A separate page-timed control forecasts once the neural issuer has frozen that page's original addresses/versions and before it verifies any member. Page grants use the remaining Run budget. It cannot foresee later pages.

A capacity-only grant reserves record-sized slots without constructing a Cell before verification. A pooled grant constructs each actual Rust Cell in the slab with its real linked template, source epoch, input/fact maps and a reserved fact-state buffer (one to four entries, from template width). A named grant further attaches particular records to serials and lanes of immutable pages of already-issued neural parents. Run-level forecasts have no names at the initial reservation. Their names are assigned in source order to offers when each page is sealed. Page-level named reservations are allocated and assigned together. These dispatchers use the existing learned parent issuer; count prediction and choosing an individual parent are separate responsibilities.

No private slot obtains a source Cell ID, owns a live e-class or appears in the source query/rebuild indexes. When the original verifier accepts an address, the scheduler still controls deduplication and commit. Only the original certified primary allocation branch can claim a private record. A named claim also compares the source epoch, serial, origin, linked layout, rule, template and ordered physical address/version list of the retained lane to the already bound source proof. A missing, expired, wrong or unbudgeted record takes the ordinary source allocation path, charged explicitly. It never supplies a missing binding or consumes a different named record. Ordinary non-primary allocations keep their original source and order.

On the direct root path the staged record is initialized with the verifier's delivered instance slots and original parent. On first-miss promotion or a changed scalar write, the original code has already computed a transient frame. Its values and fact states are transferred into the staged record before publication. This path retains that transient work. The final ordinary membership map owns the moved Rust Cell by value; the slab header address need not stay fixed. Each preconstructed record has already reserved a nonempty physical buffer for its fact state. At publication, the auditor checks the stored Cell's buffer address against the original private allocation. Private record headers are contiguous. The per-record payload buffers are separate allocations. All unused records, retained page references and slot metadata are dropped at the end of ordered RHS execution before rebuild, including in the last Run.

## Causal inputs, output and accounting

The count head is shared. In this order it consumes a constant 1, log1p of the preceding activation's offer, committed-root and fresh-root counts, preceding fresh divided by max(1, offers), log1p of query atoms, log1p of linked effect operations and log1p of current page offers. History is keyed by source ruleset and rule. The eighth input is zero in the Run-wide head. Only completed source Runs update the history. The CPU predicts a log count, applies expm1, rounds to the nearest nonnegative integer and bounds the result by the cap. Fixed-count, historical and zero-issue controls share the allocator. The number of roots that actually get a physical Cell in the current Run is an after-the-fact target.

Use a request such as `"spec_cells":{"timing":"run","storage":"named","policy":"score","cap":1024,"weights":[...eight coefficients...]}`. For label capture use `policy:"capture"`. `capture:true` also records samples for a frozen policy. The report's seven fields per sample are source epoch, rule, template, eight inputs, actual offers, actual committed roots and actual fresh primary allocations. Page samples correspond to one immutable page, and Run samples correspond to one active rule. Detailed per-rule `grants` contain epoch, rule, pre-global-cap forecast, granted record count, committed and fresh. `counts` separates predicted/unrealized demand, constructed records, capacity-only slots, accepted recorded roots, ordinary fallback, unused and misnamed reservations, payload-identity checks, largest simultaneous slot budget and charged header/payload capacities. The private capacity figure excludes allocator metadata, page-reference handles, and forecasting book-keeping. It is not whole-process RSS.

## Fixed-budget native controls

These complete, independent Pass 3 executions use six predicted records per active rule or issued page and the same cap of 37 slots per Run. The two boundaries produce different numbers of forecast sites, so the effective granted totals differ. Each accepted row below preserves the exact root-bound source address and the staged payload buffer. Capacity-only uses the same grants as pooled but has no early-initialized payload.

| Program | Timing and ownership | Granted over pass | Committed from staged records | Unused | Ordinary fallbacks | Direct / previously evaluated scratch | Peak charged private bytes |
|---|---|---:|---:|---:|---:|---:|---:|
| sum-bits | run/pooled | 46,582 | 1,603 | 44,979 | 4,161 | 1,440 / 163 | 14,208 |
| sum-bits | run/named | 46,582 | 1,514 | 45,068 | 4,250 | 1,362 / 152 | 14,208 |
| sum-bits | page/pooled | 10,182 | 2,898 | 7,284 | 2,866 | 2,470 / 428 | 13,824 |
| sum-bits | page/named | 10,182 | 2,813 | 7,369 | 2,951 | 2,395 / 418 | 13,824 |
| dot-product | run/pooled | 49,913 | 1,346 | 48,567 | 4,192 | 1,185 / 161 | 14,208 |
| dot-product | run/named | 49,913 | 1,216 | 48,697 | 4,322 | 1,074 / 142 | 14,208 |
| dot-product | page/pooled | 10,212 | 2,644 | 7,568 | 2,894 | 1,970 / 674 | 14,208 |
| dot-product | page/named | 10,212 | 2,422 | 7,790 | 3,116 | 1,837 / 585 | 14,208 |

In the zero-grant control all 5,764 / 5,538 fresh primary allocations on sum-bits / dot-product followed the normal path. Deliberately generous Run forecasts at cap 4,096 initialized 3,194,768 / 3,415,796 private records cumulatively but supplied only 5,646 / 5,334 committed allocations. A withheld or stale name prevented 2,025 / 2,200 prospective claims respectively on the two programs, with zero borrowed names and an intact source execution. The fixed cap, independent Run-wide apportionment, per-page labels, source Run/writes/Spine/union/final graph, every winning proof and all physical Cell IDs passed the archived controls. These are structural controls. Timing and held-out accuracy require the separately frozen count policy. [Detailed native evidence](controls.json)

When linked with the separate whole-Run issuer, the optional verifier-boundary observer counts sealed offers and reserved record slots before and after the first actual nonempty parent verification of each Run. It observes the singleton verification loop and the packed multi-parent verifier. By itself this storage module moves allocation earlier; the separate wave scheduler determines whether all independent parent choices are made together.

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/speculative-cell-batches
python "$d/build.py" "$EXP/spec-batch"
python "$d/contract.py" "$EXP" "$EXP/spec-batch/session" "$EXP/spec-controls"
python "$d/verify.py" "$EXP/spec-controls"
```
