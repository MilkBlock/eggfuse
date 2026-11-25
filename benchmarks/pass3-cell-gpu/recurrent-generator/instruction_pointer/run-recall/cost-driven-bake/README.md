# Cost-driven Bake on independent EggCC executions

The baseline is the recursive B policy at `b33af382` with the existing GNN and `structure-rl.pt`. Every evaluation starts from the program's initial state, drives the native Rust Cell runtime through CCP v0.1, and runs to schedule end. Exact matching, witness probes, dependency tracing and oracle event lists run exclusively in the diagnostic arms or after an execution. The independent trajectories can diverge from the exact reference.

## Independent execution

The eight donor contracts preserve the baseline final graph and all audited Run boundaries on each evaluation program. On sum-divisors they eliminate 49,577,598 candidate visits with frozen weights. The baseline gate already selected the new contract on every eligible old-source event in all three programs. Continued RL reproduces essentially the same search savings. It changes some existing open actions, including saving four paid requests on loopfact. The reduction in searches happens before signing, so EPT changes little. Extra chooser tokens are visible in the neural column.

| Program | Arm | Derived Coverage | Actual candidate visits | Neural emissions | Oracle decisions | CCP requests | Effective ops | CCP EPT | EPS | Online seconds, median ± MAD |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | A | 764/1,120 | 6,959,543 | 350,496 | 0 | 297,797 | 1,094 | 0.003674 | 89.4 | 12.24 ± 0.01 |
| fact | B | 764/1,120 | 5,965,950 | 353,918 | 0 | 297,797 | 1,094 | 0.003674 | 96.7 | 11.31 ± 0.13 |
| fact | C | 764/1,120 | 5,965,950 | 353,922 | 0 | 297,797 | 1,094 | 0.003674 | 97.8 | 11.18 ± 0.08 |
| fact | D (oracle) | 764/1,120 | 5,965,950 | 350,496 | 3,422 | 297,797 | 1,094 | 0.003674 | 97.3 | 11.24 ± 0.08 |
| loopfact | A | 944/1,112 | 4,950,932 | 324,719 | 0 | 263,616 | 1,136 | 0.004309 | 100.7 | 11.28 ± 0.10 |
| loopfact | B | 944/1,112 | 3,087,318 | 330,528 | 0 | 263,616 | 1,136 | 0.004309 | 121.6 | 9.34 ± 0.08 |
| loopfact | C | 944/1,112 | 3,087,318 | 330,548 | 0 | 263,612 | 1,136 | 0.004309 | 123.6 | 9.19 ± 0.04 |
| loopfact | D (oracle) | 944/1,112 | 3,087,318 | 324,719 | 5,809 | 263,616 | 1,136 | 0.004309 | 123.8 | 9.18 ± 0.02 |
| sum-divisors | A | 3,085/8,018 | 89,402,426 | 5,216,242 | 0 | 4,930,893 | 4,321 | 0.000876 | 35.1 | 122.94 ± 0.14 |
| sum-divisors | B | 3,085/8,018 | 39,824,828 | 5,249,806 | 0 | 4,930,893 | 4,321 | 0.000876 | 60.2 | 71.73 ± 0.07 |
| sum-divisors | C | 3,085/8,018 | 39,824,827 | 5,249,823 | 0 | 4,930,893 | 4,321 | 0.000876 | 60.0 | 72.08 ± 0.26 |
| sum-divisors | D (oracle) | 3,085/8,018 | 39,824,828 | 5,216,242 | 33,564 | 4,930,893 | 4,321 | 0.000876 | 59.8 | 72.24 ± 0.41 |

| Program | Recursive prefixes expanded, A → B | Terminal candidate scores, A → B | Fresh index positions read | New option scores | Activate / pass under frozen weights |
| --- | ---: | ---: | ---: | ---: | ---: |
| fact | 499,173 → 490,032 | 2,247,642 → 1,265,442 | 1,878 | 6,844 | 3,422 / 0 |
| loopfact | 654,413 → 648,464 | 3,950,408 → 2,094,120 | 3,245 | 11,618 | 5,809 / 0 |
| sum-divisors | 4,178,778 → 3,809,634 | 83,661,495 → 34,652,774 | 16,965 | 67,128 | 33,564 / 0 |

All four paired blocks reached the three reference-derived fact counts shown above. These are full schedule completions with partial reference Coverage. The independent state hashes and native operation counts differ by workload. They match across A/B/C/D within each workload. For the last two paired blocks, the replay additionally verified the exact ordered RHS, writes, resumptions, events, schedule and effective-operation ledger across those four arms. The per-Run equality is stronger than a Coverage tie. [Measurement records](native-rollouts.json) · [Physical primitive work on the actual accepted tape](primitive-work.json)

## What the frozen policy spends

| Workload | Root events | Ordinary pointer scores | Events accounting for 50% / 80% / 95% | Scores with a provably old-only completion |
| --- | ---: | ---: | ---: | ---: |
| fact | 120,742 | 6,959,256 | 12 / 489 / 8,831 | 1,989,181 (28.58%) |
| loopfact | 134,377 | 4,950,282 | 526 / 7,112 / 25,899 | 3,786,753 (76.50%) |
| sum-divisors | 750,774 | 89,399,216 | 1,839 / 20,751 / 92,909 | 85.4% |

Rows in each ranked file identify the Run, rule, entry role, token, op, version, old-source wake flag, and batch. Taking the first indicated number of rows recovers the exact event set, including tied costs in original encounter order. Each row includes expanded prefixes, issued native requests, duplicates, committed winners, and origin-attributed effective operations. The full SSD ledger also stores every native status and every pointer depth for the complement of the 95% set. Per-role JSONL files aggregate those records across Runs. [fact ranks](fact-top95.csv.gz) · [loopfact ranks](loopfact-top95.csv.gz) · [sum-divisors ranks](sum-divisors-top95.csv.gz) · [search totals, native fork diagnostics and isolated regions](search-audit.json)

The concentration unit is one evaluated parent candidate. In a vectorized forward pass several events share one wall interval. We measured the entire dispatch wall and the elapsed pointer call, including its threshold comparison. We allocate that pointer time to events in proportion to their rows **within the same call**. The audit also gives concentration thresholds for these apportioned seconds and for directly timed dispatch batches. Individual event times obtained by splitting a batch are estimates. The paired online timings omit the profiler. All normal parent visits reconcile to the model's invocation counts. A separate frozen native run attributes every remaining visit to a concrete partner or boundary pointer call. They total 287, 650 and 3,210 across the three programs and reconcile exactly. The per-call ledgers include source, target role, elapsed time and the returned reference. [Auxiliary search reconciliation](auxiliary.json)

Forks replay the measured policy's actual prior publications, then ask the native engine for canonical bindings in that next Run. A second native probe checks each recovered tuple on the original state. Following the identical tuple through B's bucket and prefix scores identifies an observed miss, even when a different proof already signed the same input binding. One further native rejected-terminal probe per root with an available sample supplies lower bounds on missed legal paths. The data include events that issued nothing and events whose every issue was rejected. A native fork that emitted no new binding cannot certify that every alternative proof is impossible.

The two extraction rules 498 and 501 together account for 65,184,288 ordinary scores in sum-divisors. In Run 541, rule 498 role 4 fell from 404,643 scores to zero with the same issued results. fact has a different bottleneck. Its 12-role rule 0 accounts for 4,369,911 of 6,959,256 scores. Several TCPair roots in Run 455 each cost 292,792 scores with **zero** certified old scores. The exact fork emitted no new binding of that rule on that snapshot. That retrospective observation cannot justify dropping the event online. [fact rule/entry/depth](fact-roles.jsonl) · [loopfact](loopfact-roles.jsonl) · [sum-divisors](sum-divisors-roles.jsonl)

B spent 94.7% of fact ordinary pointer scores, 92.0% of loopfact scores and 87.1% of sum-divisors scores in events without an accepted or duplicate native reply. Of the high-cost native forks, we found 30, 53 and 264 distinct events, respectively, with a matched canonical proof that B would cut at an intermediate prefix. Alternate paths can already cover the same result. The machine results separate those cases from unissued legal signatures and terminal failures.

## What can be compiled

Every seminaive issue already requires at least one parent version at or above the rule's watermark. Waking an old source makes it worthwhile to ask **where the last remaining fresh witness could come from**. Recipe roles determine the search order. Ordered version summaries determine the last role with any fresh row. If all remaining roles are old, a selected root can close this attempt. At the last possible role, only a prefix still lacking a fresh parent uses the version-filtered view of B's existing posting. Fresh siblings, other allowed anchors, and unselected events keep their original search order. Later publications can wake the same source again. No key-value comparison, new proof lookup, or automatic rule expansion executes in the host.

The index construction charges every posting position it reads. The runtime reuses a view within a Run for the same posting and watermark. Measured costs include the decision to activate or pass, metadata checks, index and partner reads, CPU maintenance, neural inference, IPC, verification and publication. The optimization primarily eliminates **failed search** that would previously reach the final old-only check. It generates no mutation or positive reward on its own.

We ranked donor entries by actual old-only pointer scores on sum-bits, tested 16 contracts, and retained eight across the Bop and Concat extraction rules. A single measured donor occurrence had to save more scores than the largest participating published table plus one choice, even if a fresh-only posting had to be built cold. This is an admission criterion in units of inspected rows/choices. The cost of arithmetic, control, caches and relative wall time is tested by running the full independent arms. Local experiments put one treated occurrence per contract into the same execution, isolate each occurrence's actual delta in the ledger, and verify equality of all root identities and all issued status counts. The treatments can share a Run's index. The joint experiments re-execute the whole policy. [Donor decisions](sum-local-admission.json) · [Frozen eight-entry manifest](cost-book.json)

For the 95% set we walked signed parent ancestry, actual published RipSat members and named receipts of the frozen evidence regions, including a versioned optional independent input. Native Receipt Contracts give the available Computation Request frontier. Scalar functional dependencies yield values or uniqueness bounds. A successful external row must still have a concrete named witness. The audit records each measured event against the most economical **observed** proof, and assigns that event's pointer cost once. Events with failures keep their own cost. Witness attribution and the old-version certificate overlap. Finding one cheap proof cannot discharge all siblings.

The positive-region diagnostic reuses the donor's executable 48-region evidence catalog. It considers matched programs with actual named receipts on the independent tape, then ranks disjoint launches by the marginal terminal visits, unary roots and ordinary issues they could replace, charging every step, activation and independent partner choice. The offline oracle can identify a previously observed source and partner; submission still requires the current version, native guards, live signed inputs and actual publication. The complete online run includes failed launches, changed downstream opportunities and the existing residual search. This is an experiment over these executable interfaces and a greedy non-overlap selection. It does not establish a mathematical optimum over all subgraphs or all proofs.

In the three workloads, respectively, 114, 212 and 495 costly events had a witnessed completion with no external address beyond the named wiring. Those events consumed 13,389, 17,910 and 206,833 ordinary scores across all their branches. No such completion certified that the entire signature space for its event was exhausted. On sum-divisors the audit found 1,307 events whose cheapest examined witness needed one external reference and 3,857 needing more. This evidence describes the measured interface and the examined proofs. The portion intrinsically requiring learned addressing is unidentified.

Keeping source and external versions fixed in sum-divisors, the events that could share one independent binding across **different rules** accounted for 690 scores. Reuse across Runs touched events responsible for 35,124 scores. These are overlapping whole-event opportunity ceilings. Another 661 expensive events (103,111 scores) admitted some deterministic scalar computation in the Recipe frontier. Producing a scalar supplies no native evidence that the required external row exists.

## Oracle search limits

| Program | All-entry version Oracle visits | Share of original visits removed | Eight-entry frozen B share of that saving | Positive regions activated | Additional visits with positive regions alone | CCP requests saved by positive regions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fact | 4,970,362 | 28.58% | 49.95% | 7 | 106 | 5 |
| loopfact | 1,164,179 | 76.49% | 49.21% | 9 | 212 | 6 |
| sum-divisors | 13,034,665 | 85.42% | 64.92% | 39 | 1,629 | 29 |

On the eight-entry menu, frozen B realizes all of D's ordinary pointer savings on every program. The wider diagnostic allows the same compiler proof at all seminaive entries and gives it offline knowledge of which wakes reduce search. It claims no neural decision credit. On sum-divisors both wide runs ended at the same graph in 41.63 and 41.52 seconds. The wide audit's 76,367,761 removed visits match the ordinary baseline's measured old-certificate count; 192,105 positions were read to build version indexes. The remaining 13,034,665 visits have no established lower bound on the portion intrinsically requiring learned addressing.

For positive regions alone, a single best-ranked activation in fact, loopfact and sum-divisors saved one paid request each, but increased total visits by 16, 34 and 61. Activating all packed positive regions produced 13, 14 and 72 origin-attributed effective operations inside those regions, respectively. The ordinary policy otherwise recovers those results. On the donor, the joint positive-region rollout activated 22 regions, saved 15 CCP requests and increased visits by 1,059. This is the reason the new training actions are the version contracts. In the joint oracle with launch addresses fixed on the baseline tape, the three programs visited 6,081,314, 3,215,872 and 56,147,614 candidates. Earlier signed proofs can change later token addresses. The separately measured live-policy hybrid recomputes its eight-entry choices on its own stream. With the positive oracle still active it visits 5,966,056, 3,087,530 and 39,826,457 candidates. The same positive regions still cost 106, 212 and 1,629 additional visits relative to the frozen eight-entry arm. All six boundary hashes match each baseline. This joint execution verifies the interaction directly. Only A/B/C/D used four forward/reverse blocks; the wide diagnostic ran twice and other supplementary interventions once.

## Protocol, split and accounting

- A uses unchanged B. B exposes the eight entries to the frozen two-option scoring head. C uses the same entries and head after four mirrored on-policy perturbation pairs on the first 320 sum-bits Runs, seed 431 and sigma 0.06. Primitive, deferred, open and recursive actions remain available. The pre-existing coverage constraint, settled-operation credit, charged requests/controls and wall reward use the inherited training reference (the projected-entry rollout on those same 320 Runs). The independent comparison A uses the full frozen recursive B. No test event labels or test programs feed the optimizer or the donor catalog. All three evaluation programs have appeared in historical development. [Training returns](training.json) · [Nine donor episodes and learned parameter deltas](training-episodes.json) · [Trained checkpoint](cost-rl.pt)
- D uses the same eight contracts with offline launch labels and measures the achievable search saving within that menu. Additional diagnostics make the same certificate available at every seminaive entry, or use oracle-selected positive evidence regions alone or jointly with D. They all incur the actual costs of their own execution. Selection uses offline knowledge and has no claim to autonomous neural coverage.
- Coverage counts distinct reference derived facts found at schedule end. The native effective-operation ledger counts visible births, actual writes, effective unions and visibility changes. An accepted primitive application can perform multiple such operations or none. The historical EPT divides effective operations by all paid CCP requests. EPS divides the same numerator by independent online wall. The output separately records generated template tokens, ordinary concrete neural proof proposals, abstract/control selections, dynamic partner selections, native CCP traffic including lowered work, and actual primitive commits. Neural emissions count a predicted template, an ordinary proposal and an explicit control choice separately. Dynamic operand reads stay visible separately; one concrete request carries its named arguments. Oracle choices are separately labeled and charged.
- Apple M3 Max CPU, PyTorch single thread, native CCP v0.1. Each of four complete blocks runs A/B/C/D in forward or reverse order. Pairing is by workload and block. Individual samples, median, MAD, within-pair differences, choice and index build time, request/receipt costs, suppression, residual partner visits and all status counts are in the linked JSON. The main wall measures online execution from native process launch to close. Setup-inclusive times available on later blocks also cover baseline policy setup, native contract parsing, model/reader and oracle initialization. Offline audit, chart/report generation and creation of training labels are outside online EPS. These short samples characterize this machine. [Native runs and individual timings](native-rollouts.json)

## Reproduction

Use the native dataset and frozen primitive models from the recursive B experiment and run from `instruction_pointer`. The pinned checkpoint allows reproduction without repeating wall-sensitive RL training. Set DATA to the prepared data root and OUT to a writable path.

```bash
mkdir -p "$OUT"
cp run-recall/entry-first/entry/catalog.json run-recall/multi-entry/entry-contracts.json "$OUT/"
cp run-recall/entry-wiring/{wired,graph}.pt run-recall/structure-compose/{structure-book.json,structure-rl.pt} "$OUT/"
cp run-recall/evidence-regions/evidence-book.json "$OUT/"
for c in sum fact loopfact sum-divisors; do
  python cost_study.py "$DATA" "$OUT" "$c" profile
done
python cost_catalog.py "$DATA" "$OUT" sum --discover
python cost_study.py "$DATA" "$OUT" sum single
python cost_admission.py "$DATA" "$OUT"
for c in sum fact loopfact sum-divisors; do
  python cost_catalog.py "$DATA" "$OUT" "$c"
done
python cost_study.py "$DATA" "$OUT" sum train --limit 320
for c in fact loopfact sum-divisors; do
  python cost_study.py "$DATA" "$OUT" "$c" single
done
python cost_native_audit.py "$DATA" "$OUT" sum fact loopfact sum-divisors
python cost_dependencies.py "$DATA" "$OUT" sum fact loopfact sum-divisors
for rep in 0 1 2 3; do
  arms=(base frozen rl oracle)
  if ((rep % 2)); then arms=(oracle rl frozen base); fi
  for c in fact loopfact sum-divisors; do
    python cost_study.py "$DATA" "$OUT" "$c" "${arms[@]}" --rep "$rep"
  done
done
for c in sum fact loopfact sum-divisors; do
  python cost_study.py "$DATA" "$OUT" "$c" receipt-single receipt combined
done
for rep in 0 1; do
  cases=(fact loopfact sum-divisors)
  if ((rep)); then cases=(sum-divisors loopfact fact); fi
  for c in "${cases[@]}"; do python cost_study.py "$DATA" "$OUT" "$c" wide --rep "$rep"; done
done
for c in fact loopfact sum-divisors; do python cost_study.py "$DATA" "$OUT" "$c" aux receipt-with-b; done
python cost_results.py "$OUT" "$OUT/report" profile
python cost_results.py "$OUT" "$OUT/report" rollouts
# REPLAY is the study's native diagnostic example, built with cell-token-ept and spine-blocks.
python cost_results.py "$OUT" "$OUT/report" primitive --data "$DATA" --replay "$REPLAY"
python -m unittest discover -p 'test_*.py'
```

Input and checkpoint digests identify the exact programs, binary and learned weights. [Provenance](provenance.json)

90 instruction-pointer tests passed, including fresh publication after a previously closed old-root attempt, mixed selected and residual roots, and signed-row existence versus scalar uniqueness. The physical work report counts committed primitive rule applications and native constructor requests, reuse, function updates, merge executions, unions and repair dependencies. These counters overlap and are reported separately. They come from the existing native graph counters on a replay of the actual signed requests.

The project sum-bits acceptance entrypoint returned `pass` on the reviewed exports. Separate checks exercise the README Cargo compile, run and five-repeat bench on the minimum CPU path. The study additionally compares the independent intervention against its own same-program baseline, including ordered RHS, writes, resumptions, schedule, transient events, and settled ledger wherever hashes were recorded. [Reviewed semantic acceptance](semantic.json)
