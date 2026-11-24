# Exact field joins, neural ranking, and Higher Cell catalog selection

**Tracks and scope.** A and B are Symbolic Execution. C is a hybrid control on the Symbolic Execution track. D is Neural Execution under B2. The Higher Cell study supplies offline heuristic controls for Neural Compilation. The generators are Python/PyTorch CPU prototypes with the native Rust receiver. The independent trials execute real requests in the native graph. The catalog study counts opportunities on a recorded trace.

## Frozen Runs

Reuse the 120 stratified snapshots of the structured retrieval study (32 productive and eight empty per program). There are 1,954 distinct teacher commits, including 1,505 with one or two named owners in their recorded proof. A request can use an alternative proof of the same binding. Every unique teacher commit earns at most one hit. Valid requests in excess of the unique count are duplicates. The teacher drives the entire graph in shadow mode. Native replay checks the schedule, RHS, writes, resumes, events and graph digest. These are committed teacher bindings. They do not count enode births or signed effective operations.

| Arm | Candidates before payment | Paid | Unique / 1,954 | One or two owners / 1,505 | Unseen pair / 76 | Duplicates | Guard rejects | Binding rejects |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A · exact field join, issue all | 23,271 | 23,271 | 1,609 | 1,505 | 76 | 18,660 | 2,967 | 35 |
| B · same join, seeded random ranking | 23,271 | 9,376 | 1,349 | 1,259 | 71 | 6,765 | 1,247 | 15 |
| C · same join, frozen Compose ranking | 23,271 | 9,376 | 1,206 | 1,151 | 53 | 6,231 | 1,910 | 29 |
| D · field ANN, same frozen Compose ranking | 200,754 | 9,376 | 1,367 | 1,337 | 66 | 6,512 | 806 | 691 |

Each symbolic read enforces the shared variable equalities across the whole named tuple using the snapshot's field hashes. Native checks cover actual values, guards, literals, visibility, versions and duplicate bindings. The receiver never searches for a missing parent. A issues every equality-compatible proposal in the tested one/two-owner generator. A is narrower than the complete exact engine. D reads typed visible ports, probes the neural field index and ranks projections of the returned owners. It never reads the symbolic postings. All arms maintain their own index. Frozen code and weight digests are in the shadow files.

Freeze the proposal ceiling from the previous ANN study and cap it at the smallest number available to B/C/D in each workload. The three budgets are 1,260, 1,600 and 6,516. In shadow, each policy ranks its offers across the entire 40-Run sample of that workload. This is an offline budget diagnostic. An online controller could not see the future score distribution. One uniform random seed was used, with no hyperparameter search. There is no per-event allocation based on exact match availability. The three schemes pay equally for signed requests. D spends additional reads and scores. A/B/C saw exactly the same candidates. The seen producers/unseen pairing definition and program sample are frozen from the preceding study; this is a development comparison.

The frozen ranker delivers 143 fewer distinct commits than random on the identical symbolic candidates. It trades 534 fewer duplicates for 677 more rejects. D gains 18 distinct commits over B but loses five unseen-pair targets and evaluates 200,754 combinations. These results do not estimate the value of learning new policies or compiling new templates.

## Work and CPU wall time

A/B/C each visited 1,570,572 local ports while forming owner projections and 30,600 cross-owner postings over 11,329 index lookups. A/B performed zero Compose scores. C scored 23,271 combinations. D tested 2,337,443 typed positions, visited 214,205 bucket postings, scored 389,728 field vectors and 200,754 combinations. The implementations count different units of work, shown in the per-arm JSON.

Each index inserted 154,321 field keys and removed 17,042 over the three complete teacher histories. On the 155 frames immediately following one or more union events, the counters record 57,356 insertions and 14,709 removals. Changes from RHS and repair can share a boundary. These figures measure associated work and do not isolate a counterfactual union cost.

Four single-threaded CPU rounds rotated arm order, with fresh native reference and teacher replay processes checked against the reference digest every round. Shadow includes the Python generator, full memory-file read, index maintenance, selection, and a separate native teacher/probe replay. The two native controls run the whole program without Python or probes. Stage timers overlap the end-to-end wall. The final timing series partially overlapped an evaluation job. Treat the observations as implementation costs.

| Program | Exact native, s | Teacher replay, s | A, s | B, s | C, s | D, s |
|---|---:|---:|---:|---:|---:|---:|
| fact | 0.148 | 0.151 | 0.616 | 0.591 | 0.986 | 1.264 |
| loopfact | 0.147 | 0.150 | 0.558 | 0.577 | 0.839 | 1.047 |
| sum-divisors | 0.263 | 0.264 | 3.114 | 2.977 | 6.622 | 9.352 |

Median over four rounds of the sum across programs, seconds per phase:

| Arm | Field index | Index on frames after union | Projections and encoding | Retrieval | Final scores and local rank | Native teacher + probe verification | Generation + audited replay |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 0.055 | 0.024 | 2.689 | 0.112 | 0.002 | 0.022 | 4.287 |
| B | 0.055 | 0.024 | 2.766 | 0.217 | 0.004 | 0.017 | 4.152 |
| C | 0.055 | 0.024 | 7.065 | 0.121 | 0.036 | 0.017 | 8.467 |
| D | 1.046 | 0.382 | 7.575 | 1.087 | 0.138 | 0.017 | 11.663 |

## Independent execution

The native online receiver advances its own source schedule. One- and two-owner generators read only the actual preceding snapshot. Bootstraps cover scheduled zero-table rules. No residual search runs. B/C/D select up to eight offers per delta event and spend their program allowance in event order. The matched budget is one request per reference commit, set at the program level. A has no quota. All budgeted arms completed their own schedules. None reproduced the reference state. The exact-only native controls and the full teacher-token oracle reproduced it.

| Program | Reference Runs | Runs reached A / B / C / D | First divergent Run, all arms | B/C/D budget each | Traceable teacher commits A / B / C / D |
|---|---:|---|---:|---:|---|
| fact | 634 | 424 / 342 / 342 / 303 | 9 | 1,668 | 155 / 156 / 158 / 120 |
| loopfact | 618 | 411 / 349 / 349 / 299 | 10 | 1,419 | 106 / 109 / 110 / 90 |
| sum-divisors | 1,644 | 452 / 448 / 441 / 322 | 14 | 17,341 | 426 / 429 / 439 / 432 |

The last column is a **lower bound**. After divergence, the counter aligns source schedule coordinates, rule, ordered named parents recursively, op, field hashes and version-origin coordinates. Alternate proofs without aligned ancestry, unaligned repair tokens and final receipts lacking a next frame earn no credit. Each exclusive JSON includes cumulative-recall inputs by Run, first common-prefix length, raw native accepts, duplicates, rejected reasons, time, graph digest and a final equality flag. An accept on a divergent trajectory alone cannot establish teacher recall.

In supplementary trials removing the program quota, B/C still failed to reproduce all three final states. D completed fact with 17,981 requests and a different digest. On loopfact Run 200 and sum-divisors Run 241 it hit the explicit 250,000 typed-projection resource limit before neural retrieval, after 17,019 and 106,631 requests respectively. The natural JSON records the failed attempt separately from the faithfully rerun preceding prefix. These two runs did not reach saturation. The symbolic generator applies shared field constraints as it constructs within-owner projections, which avoided the same expansion in A/B/C. Moving that pruning into D would change the Neural Execution contract.

## Offline Higher Cell packaging

Train layout selection on sum-bits and dot-product only, at maximum depth ten. Freeze the catalog before reading the three evaluation programs. The benchmark uses the 1,074 fixed IDs previously certified to have no available one/two-owner proof in the original domain. No neural compiler was trained. A catalog proposes structure. All strategies use the same recorded ready, scheduled, non-overlapping group selection, earliest finish then larger group. A producer package can act as a shared owner only after its last source Run. All needed internal ports are assumed exportable. This tests the historical opportunity for takeovers. There is no runtime execution or EPT claim.

The downstream metric counts original submissions whose named inputs can be read from at most two owners after packaging. The package-boundary metric counts cases where the entire unit containing that submission has at most two external owners. They measure different things. Frequency counts training occurrences. Greedy maximizes marginal training reductions in the external owner count of high-arity consumers, then fills unused capacity by frequency. Training had 8,276 distinct connected layouts, including 1,784 pure chains. Only 185 greedy additions gave positive marginal training benefit.

| Selected catalog | Size | Downstream ≤2 / 1,074 | Unit boundary ≤2 / 1,074 | External references saved | Distinct layouts used in fact / loopfact / sum-divisors |
|---|---:|---:|---:|---:|---|
| Existing frozen catalog | 4,096 | 55 | 49 | 66 | 111 / 124 / 324 |
| Frequent chains | 64 | 1 | 1 | 1 | 27 / 30 / 39 |
| Frequent connected groups | 64 | 0 | 0 | 0 | 27 / 30 / 36 |
| Greedy owner reduction | 64 | 83 | 83 | 100 | 8 / 11 / 23 |
| All observed training chains | 1,784 | 2 | 24 | 11 | 98 / 118 / 296 |
| Frequent connected groups | 4,096 | 51 | 52 | 62 | 140 / 153 / 485 |
| Greedy, filled by frequency | 4,096 | 52 | 53 | 64 | 140 / 153 / 486 |

Greedy-64 made 6, 5 and 72 downstream targets low-arity across the three programs. The larger catalogs admit overlapping packages that compete in the same deterministic packer, so adding catalog entries does not guarantee monotone coverage. Catalog sizes are separate diagnostic points. Picking a size using these results would require fresh program validation.

## Reproduce

Run in the instruction_pointer directory. Use the same captured workspace, reference memory and tape, weights and release receiver as the structured retrieval study. Each timing round asserts the same accepted set counts and payment as its baseline. The separate reviewed sum-bits final-state contract passed on the saved exports.

```sh
root=/Volumes/EggFuseWorkspace/experiments/actor-eggcctraining-20261123
py=/Volumes/EggFuseWorkspace/envs/eggfuse-ml/bin/python
for case in fact loopfact sum-divisors
do
  for mode in shadow exclusive natural timing
  do
    "$py" track_diagnostic.py "$mode" "$root" "$case"
  done
done
"$py" compile_owner_study.py "$root" "$root/track-diagnostic/higher.json"
"$py" -m unittest discover
python3 ../../../../benchmarks/marker-handoff/choice_diagnosis.py /Volumes/EggFuseWorkspace/experiments/pass3-atlas-integration-20261120/semantic-sum "$root/track-diagnostic/semantic.json"
```
