# Source guards before the remaining learned parent choices

A complete typed binding must satisfy each table atom in its compiler plan. A suffix atom whose key uses only constants can be read once at an immutable Run boundary. If its output is also present in a selected parent's row, the expected output can reject that parent immediately. Likewise, if the complete key can be projected from one selected parent, that address can be checked once and the verdict shared by every partial tuple reaching that same parent row. This scope covers plans with three or more independent sources. The two-parent generator keeps its existing delta and correlated guards.

## Example from the compiled loop-strength-reduction rule

Rule 10 has seven learned parent addresses. In order these come from `DoWhile`, `ContextOf`, `lsr-inv`, `Bop`, a second `lsr-inv`, `CellSpineView11`, and `TupleT`. Its suffix asks for the nullary constructors `Add()`, `Mul()` and `DUMMYCTX()`. The verifier can read `Add()` once for the occurrence. Once the model has selected the fourth parent, its `Bop` operation port must equal the known `Add()` value. If they differ, every completion of this prefix would fail the original verifier. The first parent supplies the key `inputs` for the suffix atom `tuple-length(inputs)`, so its absence can stop a branch after only one parent selection. The other suffix predicates still run in full for surviving tuples.

On the frozen Jacobi source this criterion finds 131 read-only requests in 79 rules with at least three independent parents. In 72 of those rules at least one guard can immediately constrain an individual parent. These are static opportunities.

The compiler extracts the owner and the source column of each guard operand from each loaded rule and its ordered plan. A constant key can also contain literals. Each guard records source atom, table, owner and optional expected output. Under a single frozen source borrow, the receipt binds the correct rule, table and table generation. A stale or misaddressed receipt abstains. A required hidden or missing row supplies valid negative evidence. The queried payload never supplies a new parent port, template, learned answer, or later table mutation. Parent identity stays the original neural address. The bitmap of per-parent outcomes lives for one rule occurrence, expires before the source can change and indexes immutable snapshot rows. Positive results still pass through the complete ordered source verifier and the ordinary physical allocator.

## Measurements

The three forward modes use the same tied packed embeddings, native row delta handling, checked-slot root layout and the single-parent shared-score frontier prefilter. The original two-parent delta freshness and correlation treatments each receive their own paired comparison. The constants arm checks constant-key reads including their output against any chosen owning parent. The local arm also checks table keys projected from one independent parent. Two negative controls supply stale or foreign receipt identity, require identical raw traces to the off arm, and run against the full ordinary source verifier.

The raw tuple count measures complete neural packets actually sealed. The verified-parent count measures packets that passed exact parent unification and reached the suffix. An early probe is an additional native table read. The per-atom failure counts count first-time rejections. A later partial tuple can reuse that result and increment rejected prefixes without another probe.

The Rust session links these components into the actual Cell CPU graph runtime executing complete Pass 3 schedules. Timing starts at resident execution and includes graph reads, initialization of guard state per rule occurrence, neural candidate issuance, verification, graph update, rebuild and Spine. Independent default-feature CPU source replay checks ordered RHS, effective writes, unions, Spine resumes, Run schedule and final graph. The offline catalog checker independently resolves each guard against the original compiled query. The runtime audit compares physical ids and source ordinals after omitting provisional packet serial numbers, which can change when an earlier rejected packet disappears. The larger Jacobi and conjugate-gradient inputs and all evaluation programs are absent from the previously frozen scoring-policy training set.

## Four complete Pass 3 schedules

Each value is the median of five resident forward passes after warmup on seed 1703. The left-to-right order in the raw-packet and inference columns is guard off, constant-key broadcast, then broadcast plus individual-parent checks. Identical source commits across all three modes permit a direct comparison of the number of rejected packets actually eliminated.

| Workload | Existing two-parent strategy | Raw packets | Complete inference (ms) | Vanilla (ms) |
|---|---|---:|---:|---:|
| sum-bits | pair | 10,121 / 9,956 / 9,941 | 38.83 / 40.22 / 39.78 | 21.58 |
| dot-product | pair | 15,020 / 12,099 / 11,990 | 39.66 / 39.36 / 38.64 | 19.53 |
| jacobi-1d | pair | 142,365 / 122,523 / 119,349 | 319.17 / 291.39 / 294.76 | 118.76 |
| conjugate-gradient | pair | 914,791 / 765,670 / 744,050 | 1,451.83 / 1,452.79 / 1,402.18 | 377.66 |
| sum-bits | correlated | 7,530 / 7,365 / 7,350 | 40.56 / 40.01 / 42.26 | 23.63 |
| dot-product | correlated | 11,973 / 9,052 / 8,943 | 41.05 / 39.30 / 38.74 | 19.71 |
| jacobi-1d | correlated | 117,544 / 97,702 / 94,528 | 293.57 / 288.06 / 306.75 | 117.06 |
| conjugate-gradient | correlated | 839,188 / 690,067 / 668,447 | 1,452.74 / 1,422.47 / 1,410.94 | 365.67 |

On Jacobi, the guaranteed `Add()` port rejects 24 distinct candidate owners in rule 10. It removes 17,220 of 30,340 raw packets, lowers later learned signature visits from 113,136 to 45,568 and lowers suffix-verifier entries from 16,400 to 6,560. On conjugate-gradient, 28 distinct `Bop` parents fail that same check. Rule 10 falls from 187,440 to 49,984 raw packets, from 614,240 to 176,880 signature visits and from 13,916 to 5,964 entries into full suffix verification. Both numbers are measured at source execution, including duplicates of a partial path. The other rule-10 early requests never supplied a first-time rejection on either large program.

The marginal single-parent lookup has a different cost. Across all rules in Jacobi it raises early native table reads from 588 to 39,095. Adding those reads to constant broadcasts saves 3,174 raw packets. With the correlated two-parent generator, complete inference rises from 288.06 to 306.75 ms. On conjugate-gradient, early reads rise from 1,007 to 316,774 and a further 21,620 packets disappear. Complete inference there drops from 1,422.47 to 1,410.94 ms. Each cost includes immediate native reads and the ordinary verifier still running on every survivor. A decision to enable keyed reads should account for prevented fan-out and actual probe work.

Independent stale and wrong-source receipts preserve all baseline raw hashes and work counts on all four programs. All active modes retain 100% of the source RHS and the same directly allocated fresh physical IDs: 5,867/5,868, 5,666/5,682, 32,721/32,819 and 97,026/97,139 in workload order. Sum-bits has no stable wall-time gain. These data span one frozen policy seed and one machine; the best measured neural route on every program remains slower than the corresponding vanilla CPU run. The [compact measurements](results.json) include all wall samples and per-Run/source audit results, and the [Jacobi guard catalog](catalog.json) identifies the concrete owners and tables.

## Reproduction

Run with the EggFuse environment and external artifact root `e`. Use separate fresh output directories for the two families.

```sh
d=benchmarks/pass3-cell-gpu/transaction-guards
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-guard-build"
python "$d/measure.py" "$e/NEW-guard-build/session" "$e/compact-vanilla-20261121" "$e/compact-holdouts-20261121-v1" "$e/baked-port-packed-study-v1" "$e/NEW-guard-pair" --controls --repeats 5
python "$d/measure.py" "$e/NEW-guard-build/session" "$e/compact-vanilla-20261121" "$e/compact-holdouts-20261121-v1" "$e/baked-port-packed-study-v1" "$e/NEW-guard-corr" --pair corr --repeats 5
python "$d/verify.py" "$e/NEW-guard-pair/results.json" --controls
python "$d/verify.py" "$e/NEW-guard-corr/results.json"
```
