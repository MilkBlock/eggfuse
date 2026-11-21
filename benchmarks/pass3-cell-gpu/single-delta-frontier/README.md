# Cross-Run batch frontier for exact scalar function keys

The previous issuer performed the same exact scalar certificate independently for each scored singleton candidate, even when multiple Cell port columns named the same function key. This optional native Pass 3 experiment retains the mapping from a physical pivot to an ordered vector of scalar-key slots. A shared slot stores a canonical key, function table generation, current source row address on a hit, and visible epoch. All rules whose compiler plan binds that exact table/key can read the same slot.

After the existing approximate seminaive/signature filters, the new path computes a batch mask in the existing source address order. It resolves a new key through the real function index. An unchanged table generation can reuse an exact absence or positive epoch. Across a changed generation a known positive address is opened directly and must still have the same live table and complete canonical key. Its current epoch is read afresh. An older absence, retired address or mismatched key requires another directory lookup. For each pivot, one missing mandatory key suppresses the lane. Otherwise the greatest source or required scalar epoch must reach the current Run watermark. An old pivot remains eligible whenever a matching function result is fresh.

The publication hook consumes the graph's repaired ChangeBatch. For tracked pivot tables, a contiguous one-event-per-generation batch evicts changed physical owners. Coalesced or uncovered versions clear the affected table's pivot caches. A union count change clears all canonical-key and pivot mappings before reuse; this trades potential reuse for exact union semantics. A working-set cap bounds the number of live cache entries across all keys and projected pivots; map allocation capacities can remain larger after clears. Unavailable compiler plans keep the ordinary singleton path. An alternate source representation without the native exact-function directory uses the existing per-lane certificate.

The mask supplies a deterministic coverage proof to the learned issuer. The network still scores its original complete bank and advances with all original inputs, including lanes that turn out to be impossible. No source RHS, expected answers or post-verification winners enter the mask. A separate audit rematches every omitted candidate, reopens and compares each retained pivot projection, and independently recomputes each scalar epoch read from the frontier. Filter-only and frontier arms must agree on rejected categories for each rule and on every raw sealed receipt, parent, version, replayed Run, ordered write, union, Spine resume, physical allocation and final graph.

## Held-out full Pass 3 results

| Six rotated samples after warmup | CG | 3mm |
|---|---:|---:|
| Independent default CPU inference, ms | 349.14 | 894.27 |
| Learned original / scalar filter / delta frontier, ms | 659.34 / 642.53 / 624.27 | 1,989.45 / 1,815.21 / 1,822.78 |
| Resident request wall, filter → frontier, ms | 759.28 → 734.69 | 2,080.26 → 2,076.03 |
| Search time, filter → frontier, ms | 442.67 → 432.68 | 1,312.65 → 1,305.68 |
| Pivot source row reads, filter → frontier | 159,196 → 29,347 | 604,303 → 86,927 |
| Exact keyed scalar lookups, filter → frontier | 238,637 → 26,432 | 888,666 → 70,935 |
| Reads of unchanged scalar slot / direct address refreshes after a version change | 102,651 / 109,554 | 396,681 / 421,050 |
| Old pivot with a fresh scalar port retained | 45,456 | 84,551 |
| Batch masks / peak live key-plus-pivot cache entries | 3,369 / 5,220 | 5,204 / 13,547 |
| Cache resets on unions | 193 | 306 |
| Separately profiled mask generation / publication, ms | 12.60 / 0.40 | 35.97 / 0.71 |

On CG, full inference improves 2.84% against the per-lane filter and wins four of six pairs. On 3mm, the 92.0% reduction in true keyed lookup count produces a 0.42% higher inference median, winning three of six pairs. There are still 888,666 scalar slot observations on 3mm, including 421,050 direct physical row inspections after version changes. Each of 604,303 incoming lanes also needs an owner-cache lookup and mask entry. The sub-millisecond publication hook was a minor cost. Separate clocked trials include the entire mask build; uninstrumented trials charge every lookup, reset and notification in full inference time.

Each program preserves the same rejected lanes per rule, with 109,818 / 510,574 omissions independently rematched against the native source checker. All 129,849 / 517,376 retained pivot projections were checked against the actual current row; all 238,637 / 888,666 observed scalar epochs or absences matched fresh exact-key reads. Unchanged-generation scalar slots were reused within a single batch 76,363 / 304,112 times. The publication hook saw only 2 / 0 cached changed pivot owners on these workloads. Many more entries were cleared at union boundaries. Neither source exercised overflow or the incomplete-journal guard. These measurements establish that slot sharing and direct address refresh remove hash lookups. The latency evidence supports retaining the previous post-score filter as the default of these two variants. [Individual samples and full source/physical checks](results.json) · [Pinned inputs and native binary](manifest.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/single-delta-frontier
python "$d/build.py" "$EXP/scalar-delta-build"
python "$d/study.py" "$EXP" "$EXP/scalar-delta-build/session" "$EXP/scalar-delta-results"
python "$d/verify.py"
```
