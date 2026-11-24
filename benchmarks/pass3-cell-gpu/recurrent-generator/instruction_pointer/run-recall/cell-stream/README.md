# Sustained Cell generation on a frozen Run

Neural Execution, exclusive native EggFuse Cell runtime. CPU policy inference is single-threaded. The actor reads typed, visible ports from the current sealed snapshot and proposes every parent address and version. It consumes no teacher bindings, symbolic join results or validator-selected partners during inference. Exact forks, replay and teacher scoring are offline measurements.

## Output capacity

The previous recursive policy has a 64-request limit and 96 prefix expansions per Run, keeps at most four extensions per prefix, and retains six combined paths per depth. The once-through policy generates at most six requests from a multi-role rule in one Run, even with thousands of valid completions. The per-Run bound in [capacity.csv](capacity.csv) sums the rule limits and accounts for empty interfaces and available typed ports. The actual maximum can be lower under the shared expansion budget. A bounded persistent pool has the same 64-request global limit and can start multiple continuations for a rule.

There are 4,958 reference Runs and 67,114 teacher commits across the nine programs. At least 34,981 commits exceed the 64-packet cap in their own Runs. Including the once-through per-rule fanout and beam gives a lower bound of 38,322 inaccessible commits. These bounds overlap. The disjoint first loss on the original named witness was rule unvisited in 15,074 cases, root outside the read domain in 33,901, later partner outside the domain in 373, fanout cutoff in 15,895, beam cutoff in 212 and selected branch left unexpanded in 17. The remaining 1,642 original tuples were issued. Among the fanout and beam losses, 6,019 and 167 respectively occurred at the final role. A different proof can still satisfy the same target. The native recall columns credit these alternatives. Removing the 512-record cap in a separate frozen counterfactual recovered 45 distinct targets and lost 28; this comparison includes the scheduling changes induced by occupancy.

CYK Run 1 had one productive rule, 1,445 commits and an attainable once-through ceiling of six. It used 15 prefix expansions. The original witnesses of 1,409 commits were lost to local fanout, six to the final beam and 24 at partner retrieval. Six were issued and accepted. The whole-Run 64-token cap never fired.

## Weights and decoders

The frozen DAgger model was continued for 140 Metal optimizer updates. On each sampled training Run the label set includes every recorded teacher winner. Training also reuses native-verified alternatives on learner snapshots. At each sampled prefix the loss sums independent positive and background logistic terms, normalizing each group separately. Multiple positive continuations can all receive high scores. Supervision is incomplete where unrecorded equivalent proofs exist; sampled background need not be provably negative. Training uses the preceding split and randomized token addresses. The two CYK held-out input seeds and the held-out certificate layout do not enter fitting. Threshold zero (sigmoid 0.5) was fixed across programs and depths. No layers were added. [Training records](multi-training.json) · [Weights](multi.pt)

* **Fixed** uses the previous recurrent decoder and caps with the new weights.
* **Dynamic** uses the learned rule priorities and independently accepts all above-threshold siblings. It works through a single depth-first, score-ordered batch under the previous per-Run budgets and neural shortlist. It discards unfinished traversal when the Run closes.
* **Dense** visits the complete typed Cartesian domain of each scheduled rule in bounded tensor blocks. It scores every legal terminal tuple, including tuples with a low-scoring earlier prefix. It signs if every role clears the threshold. Seminaive freshness is checked at the tuple boundary. There is no per-rule or per-Run output limit, prefix beam or ANN shortlist.
* **Stream** implements the same signed-set predicate. A below-threshold prefix cannot satisfy the final conjunction of the neural role decisions. The iterator skips its descendants and saves the outer block, next root, parent positions and recurrent state across yields. This pruning is exact for the specified model predicate. A successful prefix keeps every qualifying child. Thresholds can still miss legal proofs. Each wave submits up to 256 complete requests to the existing native wave receiver. Receipts do not introduce new facts into that Run. The source watermark advances only after the iterator finishes. Resumability here covers successive waves in a living process.

This is a new signed-set predicate for the recursive model. The historical 1,451/1,505 figure used a different frozen one/two-owner candidate domain with a final top-eight boundary. It is not a full-saturation result for this experiment.

On CYK Run 1, keeping the old weights gives 1,445 verified commits from 2,220 dense requests. With multi-result training it gives 1,445 from 1,445. Under fixed Top-K both checkpoints give six from six. Thus widening the decoder was sufficient to recover all 1,445 on that Run. Training affected precision. [Crossed first-Run control](cyk-first.json)

## Independent execution

The table counts visible derived reference final rows. Initial facts are excluded. The first four columns have the same 20-second workload wall allowance. A completed source schedule can still end on a divergent graph. A timeout keeps the last fully committed Run as its endpoint, charges all visits, paid tokens and wall time, and discards the unfinished Run's uncommitted receipts. The extension uses a 240-second workload allowance on the three censored stream cases.

| Workload | Fixed | Dynamic | Dense | Stream | Extended stream | Reference |
|---|---:|---:|---:|---:|---:|---:|
| fact | 140 | 138 | 282 | 363 | — | 1120 |
| loopfact | 174 | 261 | 353 | 449 | — | 1112 |
| sum-divisors | 286 | 340 | 623 | 1398 | 1404 | 8018 |
| jacobi | 270 | 335 | 300 | 1469 | 1879 | 20275 |
| cyk801 | 15 | 129 | 2901 | 6005 | 6567 | 6567 |
| grammar-17122 | 18 | 77 | 129 | 129 | — | 129 |
| grammar-91627433 | 15 | 116 | 207 | 207 | — | 207 |
| grammar-72102993 | 14 | 112 | 182 | 182 | — | 182 |
| grammar-layout-832749 | 15 | 95 | 151 | 151 | — | 151 |

All four small CYK inputs reproduced the exact native reference SHA in both dense and stream mode. On the locked unseen grammar input (72102993), both issued 538 packets and closed with 182/182 derived rows; stream used 52,854 visits. Equality of complete signed sets under chunking is also checked with a synthetic multi-parent test. CYK801 stream reproduced the exact SHA after 43 Runs, costing 1,072,213 packets, 18,548,834 visits and 39.78 seconds. It committed 4,991 packets; the other 1,067,222 failed native guards. Signed EPT was 0.00612 and EPS was 165.1. The exact native reference had a 0.164-second median across three separate invocations on the same compiled program. Timing is not a paired speedup benchmark. [Exact reference timings](exact-times.json)

None of the four EggCC programs reproduced the reference SHA. The extended sum-divisors stream finished its source schedule after 547 Runs (26.47 seconds) with 1,404/8,018 derived facts. Jacobi reached 394 committed Runs in 240 seconds with 1,879/20,275. The full dense Cartesian traversal on the four EggCC programs and CYK801 was censored by wall time. Its measured prefix is not its unrestricted final coverage. On the small completed workloads, streaming reduced visits while preserving the issued count. It does not itself reduce the number of wrong packets for the same decision predicate.

Coverage aligns constructor witnesses and visible typed rows independently of allocated eclass numbers. The final SHA is checked independently. EPT counts native signed effective operations divided by every issued packet. EPS uses inclusive wall time including incremental memory, retrieval, network, scheduling, transport, native verification and commits. A divergent trajectory can earn native operations that do not cover reference output. Candidate visits include materializing typed interfaces and scoring candidate positions (fixed/dynamic charge retrieval bucket/typed visits). Wall includes native process startup and final report, excludes checkpoint loading and offline comparison. Verification IPC includes moving proposals and receiving verdicts. Wall observations are single trials and can vary with machine load.

[Coverage vs wall time](elapsed.svg) · [Coverage vs paid tokens](paid.svg) · [Coverage vs candidate visits](visits.svg) · [Per-Run curves](runs.csv) · [Primary costs and reject reasons](results.json) · [Extended results](extended/results.json) · [Extended curves](extended/runs.csv)

## EggCC recognition, generation and stopping

The 28 first-divergence targets are a subset of the 1,074 confirmed high-order targets. They are in-domain EggCC strata. Fixed and dynamic got 11/28 and 28/28, and 93/1,074 and 90/1,074, counting verified alternate proofs. As an offline recognition probe, scoring each original teacher proof with the deployed multi-result predicate gave 28/28 and 886/1,074. For actual generation on the frozen target-bearing rule/Run pairs, the stream traversed the typed domain without target hints. It generated and natively verified 28/28 and 854/1,074 original proofs. Five of 221 rule/Run traversals reached the 2-second diagnostic wall guard. In these strata only original witnesses are counted for the stream; alternatives were not exhaustively audited. The separate recognition ceiling is for original witnesses only. Native checking of matching generated tuples happens offline and does not feed retrieval. [Direct and streamed strata](strata.json) · [Fixed and dynamic strata](bounded-strata.json)

Watermark, guard, binding and duplicate verdicts are charged separately when observed. To diagnose stopping, we forked the exact engine from the same learner prefix for selected empty source Runs. Eleven of 55 checks executed a state-changing computation; 44 found no change on that next Run. The sample selects the first empty Run where the matching teacher coordinate had work, if present, and the last empty Run. It does not estimate the frequency over all empty Runs. On CYK801 the fixed decoder's empty Run 2 also produced no change in the exact fork. The missing Run 1 witnesses had already aged out. In contrast, on loopfact dynamic Run 13 the exact fork changed the graph with 18 bindings. These have different causes even though both look silent. [Exact forks](empty-runs.json)

## The sum-divisors source assertion

The old pending arm's Run 176 snapshot contains a Mul expectation with Base(IntT) and a HasType for the same expression with Base(TypeList-ith(list,3)). The two types are still in distinct classes. In a separate process, ordinary native exact search starting on this same snapshot raised the same source assertion at Run 177, rule 351, instruction 0. One of three named requests independently reproduces it. The source program requires this failure. The runtime now identifies the failing instruction and rule, and the recorder preserves the complete failing batch as well as the last committed prefix. The regression checks both the exact fork and isolated named replays. The new stream completed the sum-divisors source schedule on a different trajectory. It did not establish that all future model trajectories avoid this source assertion. [Regression evidence](panic.json)

## Reproduction

Use the previous recursive experiment's artifact root and release binary. Run from instruction_pointer with single-threaded CPU policy inference. Source files and raw-tape conventions are documented in [the previous report](../recursive-agent/README.md).

```sh
python stream_panic_regression.py "$ROOT"
python stream_capacity.py "$ROOT" run-recall/cell-stream/capacity.csv
python recursive_train.py "$ROOT" multi
python stream_native.py "$ROOT" fixed
python stream_native.py "$ROOT" dynamic
python stream_native.py "$ROOT" dense
python stream_native.py "$ROOT" stream
python stream_native.py "$ROOT" stream cyk801 sum-divisors jacobi --seconds 240 --series cell-stream-long
python stream_native.py "$ROOT" dense cyk801 --phase dagger --limit 1
python stream_strata.py "$ROOT" run-recall/cell-stream/strata.json
python stream_strata.py "$ROOT" run-recall/cell-stream/bounded-strata.json --bounded
python stream_report.py "$ROOT" run-recall/cell-stream
python stream_report.py "$ROOT" run-recall/cell-stream/extended --series cell-stream-long --cases cyk801 sum-divisors jacobi --arms stream
python stream_stop_audit.py "$ROOT" run-recall/cell-stream/empty-runs.json
python plot_cell_stream.py
```
