# Boundary audit of the 49,577,598 visits

**Finding.** Withdraw this reduction from Neural Execution. Frozen B selects a two-way action. Host code answers a different question on its behalf: can any still-unbound role supply the required fresh witness? It closes roots and constructs restricted candidate windows before the parent pointer runs. This is symbolic search optimization under neural dispatch. Less work really runs, and some work moves into host indexes. No equivalence join discovering a new proof was found in the added watermark code.

The audited source is `0e480c54`. The governing AGENT-RULES.md has SHA-256 `5f2c1790e48044441ed4eb366df79792b44097faf95c914dbd31e19147f692e8`. B2 explicitly forbids host prefiltering by combinations of freshness. S1 authorizes a specified delta anchor and other visible ports. B3 concerns training known finite predicates. The observed two-action selector was trained on returns, not on an enumerated freshness truth table. The B2 finding alone removes the gain from Neural Execution. The frozen selector chose Bake on **every** eligible wake. This experiment gives no evidence of neural discrimination between productive and unproductive regions.

## Where the information comes from

1. The Rust scheduler prepares the scheduled rule watermarks from per-rule state and, when enabled, readiness state. It passes the rule and watermark to the snapshot boundary. Native `observe` walks the return address map, resolves forwarding, reads witness rows, excludes hidden/unpublished rows, hashes their fields and saves row epochs. It compares today's visible map against the previous publication and emits typed changes and retirements. The observer itself scans history even when few updates are exported. [Scheduler](../../../../../../engine/cell-runtime/src/runtime.rs) · [Publication and named-parent verification](../../../../../../engine/cell-runtime/src/cell_tokens.rs)
2. `execute → memory_frame → update_memory` reads native buffers, validates types, updates visible rows, owner/port and table maps, detaches retired postings and advances a per-table invalidation generation. A row's epoch, the rule's watermark and the table's generation serve different purposes. `FieldIndex.advance_rows` compares old column hashes, encodes changed fields, projects to eight signs and maintains table/column/bucket memberships. [Transaction driver](../../transaction_native.py) · [Port updates](../../cell_transaction.py) · [Field index](../../field_retrieval.py)
3. `Directory.bank` rebuilds a table on first demand after its generation changes. `Bank` iterates the **entire live table**, builds its address→position map, copies token/op/version triples and field codes, computes neural key means, stably sorts version positions and gathers the sorted version vector. Looking at its last element is cheap only once these costs have been paid. Column postings get a separate lazy sort, histogram and 257 bucket boundaries. `Directory.window` uses the first statically shared field, reads a source bucket code, then gathers destination offsets. Collisions and false positives remain possible. This inherited host lookup precedes parent scoring. [Banks, postings and pages](../../event_addresses.py)
4. `EventGenerator.wake` scans waiting rule/role keys. For scheduled, nonempty keys it compares a tuple of residual table generations. On change it scans saved roots, checks address existence and generation of the named row, removes stale opportunities, and pages old roots below the rule watermark. `expand → CostBake.choose` considers the eight catalogued signatures/entry roles only on seminaive wakes. The chooser receives the source embedding and two descriptors derived from the rule; the Bake descriptor changes its last two fields to arity/8 and 1. It emits an action for each root, without specifying a proof of the negative claim. [Wake and expansion](../../event_generator.py) · [Action and proof implementation](../../cost_bake.py)
5. For a page containing selected roots, the CPU follows the static role order in reverse, **including repeated tables**, testing each table's maximum version against the watermark. It stops at the furthest role which could supply freshness. With no such role, `roots` removes the selected old roots from this attempt. Otherwise `window` gathers the versions of already-bound roles for every prefix. When all are old at the last potentially fresh role, it scans the full role posting/table, tests row versions, materializes a fresh sublisting and prefix counts. Using two rank reads per queried interval, it narrows the existing bucket **before** `pages → CellStream.logits`. Mixed pages keep unrestricted windows for other prefixes. The view is cached by bank identity, posting identity and rule watermark, with cache clearing on the next eligible Run. This acts as a rule-conditioned search index even though it is not a persistent index named after rule 498. No run-time field-equality join or fresh external fact is needed to compute this negative feasibility test. [Exact loops](../../cost_bake.py) · [Pointer](../../cell_stream.py)
6. B's original `emit` gathers all named parents of each completed tuple and checks if any version reaches the watermark before sending. The new code moves reasoning about this relation into discovery. In both arms the open Compose partner path also filters `recent` with a distinct owner and `max(partner.version, source.version) >= watermark` **before** pointer scoring. This inherited cross-role filter is an independent B2 failure of the proposed “legal A”. The learned-field bucket lookup also needs its own explicit neural retrieval accounting. A type mask, a read of an already named port, an approximate bucket retrieval and a cross-role answer computed by the host are four distinct operations. [Partner filter](../../structure_runtime.py)

## Complete native executions

Two fresh independent, observation-instrumented executions ran all 723 Runs. Each matched its archived arm on graph SHA, statuses, issued requests, effective ops, candidate scores/visits and generated proofs. Both ended at `e2c26acf0b06fb922c75e656e39534a7b1cd8cea1866e23bc7dac0ce4dfed67c`. These measurements concern the native Rust Cell runtime and real Python/PyTorch driver. The following software counts use sizes of arrays actually operated on. An element read names a logical access; it does not specify cache hits, Python hash-table collision probes or a DRAM transaction. Sort input lengths do not establish the number of implementation-internal comparisons. [Baseline counters](observed-base.json) · [Optimized counters](observed-frozen.json)

| sum-divisors, entire execution | Baseline | Frozen + watermark |
|---|---:|---:|
| Candidate visits / CPU parent pointer scores | 89,402,426 / 89,399,216 | 39,824,828 / 39,821,618 |
| GPU scores | 0 | 0 |
| Complete candidate scores | 83,661,495 | 34,652,774 |
| Prefixes expanded / complete paths formed | 4,178,778 / 53,468,346 | 3,809,634 / 22,588,893 |
| Parent versions compared at issuance | 226,488,471 | 72,091,206 |
| Child path int64 elements written by column stacking | 378,280,813 | 131,108,621 |
| Posting address gathers / bucket-offset reads | 89,392,449 / 12,532,878 | 39,814,851 / 11,425,446 |
| Bank generation lookups / rebuilds | 1,467,251 / 808 | 597,158 / 808 |
| Live ports copied and version-sorted / posting sort inputs | 182,155 / 333,233 | 182,155 / 333,233 |
| Posting cache probes / postings built | 34,216 / 1,045 | 31,749 / 1,045 |
| Waiting keys examined / pending entries scanned | 452,642 / 647,747 | 452,642 / 647,747 |
| Field hash comparisons / field index writes / removes | 2,668 / 46,360 / 2,560 | 2,668 / 46,360 / 2,560 |
| Additional max comparisons / prior-role comparisons | 0 / 0 | 278 / 3,137,104 |
| Fresh-view probes / builds / version tests building views | 0 / 0 / 0 | 6,955 / 11 / 16,965 |
| Additional root-mask / rank reads | 0 / 0 | 1,053,254 / 1,981,494 |
| Neural template outputs / ordinary generated proofs | 106,210 / 4,930,065 | 106,210 / 4,930,065 |
| Higher-level two-option scores / added control outputs | 0 / 0 | 67,128 / 33,564 |
| All neural emissions / paid CCP requests | 5,216,242 / 4,930,893 | 5,249,806 / 4,930,893 |
| Native accepted / duplicate / other rejected | 4,623 / 4,647,918 / 278,352 | 4,623 / 4,647,918 / 278,352 |
| Reference coverage / effective ops | 3,085 of 8,018 / 4,321 | 3,085 of 8,018 / 4,321 |
| Native verifier seconds in instrumented run | 3.274 | 3.248 |
| Instrumented online wall seconds / collection barriers | 126.74 / 37,601 | 73.58 / 36,128 |
| Earlier uninstrumented median online seconds / EPS | 122.94 / 35.1 | 71.73 / 60.2 |

3,210 other candidate visits in each arm are 3,157 partner scores and 53 boundary scores. The restricted windows removed 36,627,789 positions at the point of filtering. Total pointer score difference is 49,577,598. The residual 12,949,809 is a net difference at other stages, including descendant expansions and 3,843 closed roots; it cannot be assigned wholly to one mechanism. The new indexes alone wrote 17,827 concatenated listing positions and 16,976 rank elements. Their recorded build time was 0.42 ms; this narrow timer excludes the 3.14 million prefix comparisons, existing banks and subsequent gathers. The historical EPS remains an end-to-end **hybrid system** measurement. [Paired timings](../cost-driven-bake/native-rollouts.json)

## Rule 498, Run 541

Entry role 4, ExtractedExpr, was a woken named port `(883892, op 2, epoch 303)`. The rule watermark was 489. The baseline visited roles 4 → 0 → 2 → 1 → 3. For the last four roles, the incoming prefix counts were 1, 3, 18 and 612. Pointer scores were respectively 3, 18, 702 and 403,920. Score thresholding rejected 0, 0, 90 and 400,860 of those children. The resulting 3,060 completed tuples all failed terminal freshness. The event produced zero concrete proof requests, zero Computation Requests and zero native operations.

On the optimized run this root occupied offset 171 in a page of 256. Its CPU neural logits were 6.725813 and 7.561748. It chose Bake. The host scanned the following roles for the entire page.

| Role | Table | Visible ports | Cached maximum epoch |
|---:|---|---:|---:|
| 3 | TCPair | 2,343 | 476 |
| 1 | TCPair | 2,343 | 476 |
| 2 | ExtractedExpr | 360 | 482 |
| 0 | Bop | 101 | 422 |

The network named no row from those four scans. The host supplied the table-wide knowledge, compared four maxima with 489 and closed all 256 roots before recursive scoring. The 404,643 reduction belongs to the **one named event**, not to a sum for this page. At this event the earlier and later systems both sent zero requests to Rust. A separate native fork of the measured prefix at Run 540 returned zero named proofs at the next Run. A second fork using native exact execution reported zero executed bindings and no state change. This establishes a snapshot-local opportunity label along with the exhaustive watermark argument; it offers no negative label for later versions. [Matched event, exact fork and hardware measurements](root-evidence.json)

For the named root we also ran the original pointer decoder on the restored snapshot in isolation. Xcode Instruments sampled Apple M3 Max CPU counters after warm-up. Baseline reproduced exactly 404,643 scores on every iteration; the optimized arm reproduced zero. Per replayed root the sampled retired load/store instruction counts were approximately **1.188 billion vs 249,633**. Load-unit and store-unit micro-ops are recorded separately. Five baseline and 30,000 optimized repetitions provide measurable intervals for each path. We excluded initialization and trimmed one millisecond at both endpoints. These figures include the diagnostic call into the decoder and Python/PyTorch bookkeeping; they do not give DRAM transactions or a per-root charge for shared table construction. No full-trajectory hardware load/store total is claimed: the full Instruments traces did not finalize with a readable template. Complete-run resource usage from the observation processes is separately recorded, including retired instructions and peak footprint. [Baseline process resources](base-rusage.txt) · [Optimized process resources](frozen-rusage.txt)

## Fixed entry, growing memory

Using the real 541 snapshot and frozen chooser, hold the single source reference fixed. Publish controlled extra typed ports through the normal host memory update routine in cumulative steps 0, 256, 1,024, 4,096 and 16,384. Use three independent restorations per condition. Synthetic rows test host complexity only; they do not constitute new native executions or evidence of task coverage. For the remaining-role fresh case a fixed all-old prefix selects a different LSH bucket from every added port. [Individual times and counts](growth.json)

| Condition at +16,384 | Rows read to rebuild bank / posting / fresh view on next query | First proof, ms (median) | Warm proof, µs (median) |
|---|---|---:|---:|
| Unused table, fresh publications | 0 / 0 / 0 | 0.194 | 36.9 |
| TCPair, old and irrelevant | 18,727 / 0 / 0 | 93.5 | 39.7 |
| TCPair, fresh, different field bucket | 18,727 / 18,727 / 18,727 | 95.6 | 49.9 |

From 4,096 to 16,384 distractors the last increment publishes 12,288 three-field ports and writes **36,864** keys in all three conditions. Median host publication times for this increment were 164.8, 156.6 and 253.5 ms respectively. Even a globally irrelevant update incurs field-index maintenance. In a used table a change invalidates the entire bank. With all old rows the whole root closes. With fresh distractors in another bucket the global maximum forces the root to stay open; the tested restricted window then returns zero. Each measured warm invocation reuses indexes. CPU proof cost depends on table changes, table size, prefix depth and cache reuse; the number of entry references alone does not bound it.

## Reproduce

From `instruction_pointer` use the data root, native binary, frozen checkpoints, issued tape, memory export and event ledger of the [pinned experiment](../cost-driven-bake/README.md). OUT is its store. The diagnostic scripts restore or observe the same model. They make no catalog, runtime or policy changes. For hardware counters use the macOS CPU Counters template and the included recording options.

```sh
mkdir -p "$OUT/boundary"
for arm in base frozen; do
  /usr/bin/time -l python cost_boundary_audit.py "$DATA" "$OUT" "$arm"
done
python cost_boundary_growth.py "$DATA" "$OUT"
for arm in base frozen; do
  trace="$OUT/boundary/root-$arm.trace"
  xcrun xctrace record --template 'CPU Counters' --recording-options run-recall/cost-boundary-audit/load-store-options.json --output "$trace" --launch -- "$(command -v python)" -c 'import os,sys,runpy; os.chdir(sys.argv.pop(1)); sys.argv[0]="cost_boundary_event.py"; runpy.run_path(sys.argv[0],run_name="__main__")' "$PWD" "$DATA" "$OUT" "$arm"
  xcrun xctrace export --input "$trace" --toc > "$OUT/boundary/root-$arm-toc.xml"
  xcrun xctrace export --input "$trace" --xpath '/trace-toc/run/data/table[@schema="counters-profile"]' > "$OUT/boundary/root-$arm.xml"
done
python cost_boundary_results.py "$DATA" "$OUT"
```
