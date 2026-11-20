# Repairing learned root subscriptions when a key or its equality class changes

In the reverse request issuer, a function input or output signature selects a bucket of candidate root addresses. The immutable control stores source-frame offsets, which can shift on every insertion or removal. The stable representation stores the typed fact/function dependency and resolves its current offset only when its bucket is read. It maintains one map from dependency to signature and canonical Eq class, one from signature to subscribers, and one from canonical class to subscribers. Unary Eq and i64 ports qualify.

After a successful native immutable-frame update, the old/new table generations and the exact changed addresses are chained into a pending set. A gap forces the next reader to reconstruct the index. A store can carry pending edits across Runs until a rule requests that column. When union awareness is enabled the graph retains a ring of its 16,384 most recent displaced canonical classes in source commit order. Each reader consults the segment since its previous view. If an old class had subscribers, their addresses join the pending set. The patch removes each address's former signature/class entries and re-inserts its current value and signature if the source still exists. Checking every displaced class since the prior view also covers successive unions before the next read. A missing history forces full reconstruction. An index holds at most 32,768 rows, all retained indexes at most 65,536 rows. A row limit measures entries, not RSS.

The controls are immutable frame offsets, stable addresses with reconstruction, frame-delta patches within one global union generation, and patches that consume displaced-class history. The lost-history control enables patching with the union log unavailable. During audit every materialized directory is compared with independent canonical field projections, every issued receipt is checked against a real function read, and original raw tuples, neural winners, physical Cell identities and all source events are checked. Compact inference timing does not include the detailed audit. A separate native instrument measures the directory preparation interval nested inside reverse activation.

## Paired charged execution

| Program | Vanilla | Original joint CPU | Reverse offsets | Stable rebuild | Stable delta | Stable delta + union, ms | Full build rows → build + patched addresses |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.61 | 32.62 | 32.59 | 32.97 | 33.67 | 31.65 | 10,162 → 228 + 549 |
| conjugate-gradient | 359.85 | 644.88 | 649.29 | 669.36 | 654.92 | 641.63 | 161,348 → 4,373 + 4,644 |
| 3mm | 892.73 | 2,000.89 | 1,947.98 | 1,937.51 | 1,970.10 | 1,865.65 | 551,695 → 10,326 + 10,365 |

Four rotated measurements follow a warmup at seed 1703. Stable signatures and table deltas alone still required 511,344 build rows on 3mm. Union-aware repair consulted 68,216 displaced-class entries across active indexes and found 787 with subscribers. Binary searching the current source frame and maintaining the stable-address maps are charged to the full inference. Full build row counts and patched addresses describe different operations; they do not directly measure time or retained bytes.

In a separate instrumented pass the median 3mm directory interval was 27.90 ms with frame offsets, 49.81 ms rebuilding stable addresses, 44.60 ms using table deltas, and 3.18 ms with displaced-class repair. Total reverse activation, inclusive of that interval, was respectively 31.30, 53.78, 48.50 and 7.36 ms. On conjugate-gradient the directory interval fell from 7.09 to 1.17 ms. These clocks were disabled for the primary full-pass samples. The lost-history control rebuilt after 112 gaps on sum-bits and reproduced the complete original raw stream. [Matched native observations](results.json) · [Profile samples](phases.json) · [Lost-history control](lost-log.json)

```sh
d=benchmarks/pass3-cell-gpu/incremental-request-ports
python "$d/build.py" "$EXP/subscriptions"
python "$d/study.py" "$EXP" "$EXP/subscriptions/session" "$EXP/subscriptions-study"
python "$d/study.py" "$EXP" "$EXP/subscriptions/session" "$EXP/subscriptions-transfer" --cases deriche --transfer-only
python "$d/study.py" "$EXP" "$EXP/subscriptions/session" "$EXP/subscriptions-lost" --cases sum-bits --lost-log
python "$d/phases.py" "$EXP" "$EXP/subscriptions/session" "$EXP/subscriptions-phases"
python "$d/fixture.py" "$EXP" "$EXP/subscriptions/session" "$EXP/subscriptions-fixture"
python "$d/verify.py"
```

The independent large transfer used Deriche with frozen settings and no refit. Vanilla, original joint CPU, immutable reverse offsets and union-aware subscriptions measured **1,483.97 / 3,451.84 / 3,488.20 / 3,319.68 ms** respectively. All four paired samples improved over immutable offsets. Their 961,779 directory-build rows became 27,287 full-build rows and 13,823 repaired addresses. The provider still performed 15,100 direct function reads. The 635,818 source RHS and 450,414 directly recipe-allocated Cells out of 452,913 fresh agree with the original audited ledger. [Deriche data](deriche.json)

A compiled seven-Run source fixture adds a missing function result in Run 2, adds a new target in Run 4 and unions two distinct values in Run 6. Its neural connected rule issues the original winning bindings in Runs 1, 3, 5 and 7 respectively. The reverse provider transfers three checked physical function addresses and preserves each ordered original tuple and physical Cell ID. The real larger programs additionally exercise subscribers attached to displaced classes. [Source](activation.egg) · [Native fixture and controls](fixture.json)
