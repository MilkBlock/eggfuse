# Actual explicit-parent composition with two returned physical facts

This native Cell CPU study tests **one** static producer→consumer template in the frozen ordinary filtered/packed Pass 3. The donor audit recorded a producer that creates both of the consumer's required physical parents. The program signs that variant into the original model-selected producer packet before RHS execution and removes the selected consumer pivot from ordinary external generation. The independent reference runs the full original schedule. This implements a narrow subset of the [offline composition audit](../strict-composition-opportunities/README.md).

The layout is frozen from dot-product and jacobi-1d before running sum-bits or 3mm. Among recurring shapes present in *both* donors with two distinct typed output operations, short +1 Run release and the child using the later output as its first atom, the most frequent shape uses rule 501's op 6 PotentialExtractedExpr and op 5 TCPair for the two atoms of rule 286. Its donor support was 26 / 174. The native loader identifies source definitions by their full portable fingerprints. It rederives the two operation kinds, tables, shared operand/result, distinct slots, source dedup-key coverage and original release offset from the program. The high template bit signs the variant before verification of each raw producer proposal. The causal choice is the ordinary frozen model's **specific full parent binding** with this compiled template. There is no additional neural head trained for these two rules. Failed producer proposals remain in the denominator.

**Actual return contract.** Only a source-committed, fully named producer can open the variant. A primary source-allocation event binds its real Cell ID. Hooks on actual constructor activation capture precisely the two specified physical output references when freshly installed on that Cell. No address is inferred from the parent serial. Dynamic/nested or previously interned returns cannot satisfy this deliberately fresh-only variant. At the next original Run, two addressed row reads check type, visibility, version, shared value and watermark. The residual rule has exactly two atoms; it needs no suffix point query, subsequent rule choice or otherwise unnamed independent witness.

**Safe partition of the ordinary issuer.** A shared TermAndCost value can in general be produced by several TCPair nodes. A real matching row does not alone authorize disabling the entire PotentialExtractedExpr pivot. The runtime maintains an integer upper bound by public result class for *all* TCPair facts, starting before graph initialization. Birth increments the bound; union merges the old root counts, saturating at two. Retired/hidden facts are never subtracted, which can conservatively reject an eligible candidate. The directory contains counts only. A bound of one plus the verified visible addressed TCPair proves that every source match of that left pivot must use it. The compiled original dedup key also retains all key columns of both relations. A different binding from another pivot cannot stand in for this pair. Cardinality maintenance, including unions, is fully charged.

The verifier independently prepares the pair before any paired source walk. The issuer bypasses the independently authorized left anchor in both its ordinary score/lookup loop and its reverse-delta candidate loop. It directly places the already verified pair into the original order; a known protected pivot is added even when the ordinary sparse active list would omit it. Complete source validation of that internal root reads the same two named rows. Other pivots keep the original search. Shared table-level score preparation can still encode rows for residual rules. The verifier never scans a candidate table or fetches a missing parent by key. The detailed audit separately checks every actually emitted external lane of this consumer against the protected pivot set and fails on any duplicate. A changed signed version or a forced non-unique upper bound restores the original external path.

## Held-out results

| Workload | Retained original constructor identities | External packets, ordinary → composed | Strict FEPT, ordinary → composed | Independently prepared and committed child bindings | Internal child's own new final-visible constructors |
|---|---:|---:|---:|---:|---:|
| sum-bits | 2,691 | 12,662 → 12,633 | 0.212526 → 0.213014 | 29 | 0 |
| 3mm | 92,658 | 558,074 → 557,146 | 0.166032 → 0.166308 | 928 | 0 |

All 29 / 928 committed internal children replaced one **actual original external multi-parent packet**. No selected nested packet was removed from accounting; the counts were 191 / 2,508 in both arms. On 3mm 1,456 producer proposals carried the variant; 1,446 committed, 2,143 specified fresh-return events were observed, and 928 producers met the two-return condition. The remaining signatures still cost their full ordinary packet. The transaction performed 1,856 direct row reads and 928 integer upper-bound reads. It skipped 928 ordinary anchor branches and 1,025 potential reverse partners before scoring. An audit checked all 3,194 external lanes still issued for this consumer and found no covered pivot among them. On sum-bits the corresponding counts were 58 direct reads, 29 upper-bound reads, 29 skipped anchors and 29 reverse bypasses. There was exactly one winning ordinary binding with the same ordered references and source position for every internal commit. Final-visible totals are unchanged: the direct gain from this auxiliary rule is saved explicit decisions.

Both faults were exercised on both workloads. Withholding a matching current version or forcing the degree proof to be non-unique caused zero admissions and restored the reference denominator, physical origins and final graph. The integrated degree ledger recorded 160 / 2,318 TCPair activations. Neither workload exercised a union that moved a tracked TCPair result count; the ambiguity fault exercises rejection at the proof boundary. The original program-wide union ledger remains aligned. [Source, physical and fault receipts](results.json) · [Frozen donor variant](template.json)

| Workload | Resident inference median, ms | Common RSS growth target | First sampled crossing, ordinary → composed | Median observed peak, ordinary → composed |
|---|---:|---:|---:|---:|
| sum-bits | 34.40 → 34.71 | +9.28 MiB | 26.23 → 27.83 ms | 270.70 → 274.37 MiB |
| 3mm | 1,760.72 → 1,821.90 | +264.14 MiB | 1,284.05 → 1,357.76 ms | 695.77 → 698.62 MiB |

Four resident timing samples follow warmup; source audits and export are outside inference. The RSS experiment uses three separate default CPU calibrations followed by four fresh sampled/unsampled process pairs for each native arm. Thresholds use the [existing OS inference-window protocol](../verified-wave-rss/README.md). All four observed growth crossings were reached on each arm. Loading/revalidating the public program fingerprints and allocating the native model occur before inference. The native clock and OS readings show a cost for the small verified packet saving. [Individual RSS curves, thresholds and control timings](rss.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/strict-dual-return
python "$d/freeze.py"
python "$d/build.py" "$EXP/strict-dual-build"
python "$d/study.py" "$EXP" "$EXP/strict-dual-build/session" "$EXP/strict-dual-study"
python "$d/rss.py" "$EXP" "$EXP/strict-dual-build/session" "$EXP/strict-dual-rss"
python "$d/verify.py"
```
