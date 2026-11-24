# Recursive Cell proposals and pending computations

Neural Execution, exclusive mode, native EggFuse Cell CPU runtime. The learned decoder runs on the CPU and was trained on Metal. Each issued request fully names its parent tokens, instruction positions and versions. The native verifier can check those references and apply effects. It has no search fallback. The actor sees its own accepted tokens, repair events, retirements and version updates at the next legal source boundary. Teacher snapshots and reference graph comparisons are offline.

## What changed

One recurrent cell consumes a Bake role and a retrieved parent Cell port at a time. The compiled shared-variable pattern chooses which fields to read. A frozen neural index retrieves by field vectors. The same GRU updates the temporary combination for every arity. The decoder can name a parent multiple times at different op positions. A scheduled rule with no table inputs has a zero-parent action. Rule priority and retry priority are learned. No symbol names have trainable embeddings. The decoder shares weights and structure across rules. Its present expansion granularity is one unresolved table role, including when two roles can use the same Cell.

The matched two-owner arm caps the number of distinct parent Cells. The free arm removes that restriction. The pending arm uses the same parameters and preserves named, versioned partial bindings across source Runs. The fourth arm, legacy, reuses the frozen field ANN plus Compose two-owner generator. Its architecture and resource limits differ from the matched ablation.

The pending pool is keyed by rule and ordered versioned references. The first reference identifies the source. It stores tried versioned continuations, attempts, last Run and a learned retry priority. New evidence notifies records subscribed to its missing table. Selection within a rule takes at most one such record from a bounded shortlist. A learned retry can wake one additional record per Run, and a rotating fairness probe runs every seventh Run. A continued prefix can stay pending after a successful emission. Updates and retirement invalidate dependent partial proofs before resume. A forwarded source must be discovered under its current address. The tried set survives four-attempt dormancy in a bounded tombstone cache. Active and dormant records each have a 512-record limit. An evicted record can lose work. Empty prefixes and pruned root branches have no persistent obligation. No global historical recovery sweep runs.

The reference's source schedule, watermark and stage transitions still apply. At least one named port must satisfy a seminaive rule's current delta condition. A saved old prefix can consume new evidence. A missed proof whose entire witness has aged out cannot be backdated. An empty source Run can advance the stage while obligations remain. Primary comparisons use 96 prefix expansions, four children per expansion, six surviving paths, 128 shortlisted ports per read and 64 issued requests per Run. The 128 limit applies after neural bucket retrieval. Visits before shortlisting are counted. The three recursive arms share these limits. Total wall time and number of reached Runs can differ.

## Supervision and split

Training used fact, loopfact, sum-divisors, jacobi-1d, and four generated CYK grammars. Teacher supervision includes sampled alternative addresses accepted by native replay. The learner rolled out its own first 32 Runs at most. An offline bounded expert proposed complete bindings on those snapshots and checked them against a replay of the same learner tape. Of 1,633 valid labels, 982 were absent from the learner's proposals. The teacher phase ran 260 updates on MPS, followed by 140 updates on the aggregated data. A second Metal training run with renamed owners throughout the port store, neural index and training labels reproduced all 5,419 parameters exactly in both training phases. The comparison preserves evidence pages and perturbs names and candidate presentation. The address-based page order at inference can still affect results under a different allocation order. The three recursive arms share this checkpoint, so retraining differences cannot explain their comparison. The expert is sampled and the positive labels are incomplete. Later divergent states have much less supervision.

The EggCC programs are in-domain diagnostics, including the 1,074-target stratum. Grammar seed 17122 is validation. Seed 91627433 is a separate held-out input. Seed 72102993 is the locked blind program. Its native program and frozen weight hashes are in lock.json. That file records the implementation before final formatting and accounting instrumentation. After the weights were frozen, a separate template holdout, grammar-layout-832749, introduced two unseen CYK rule layouts requiring an additional four-field production certificate. All four arms issued zero requests for either new layout, against 50 reference commits across the two layouts. No held-out capture supplies a label during online evaluation.

## Results

Each cell in the table is the count of derived reference final rows present at the independent endpoint. Input rows are excluded. The last column is the number of times a reference-derived row was first observed overdue and subsequently recovered in the pending arm, divided by observed overdue rows.

| Program | Legacy | Matched two | Recursive | Recursive + pending | Derived reference rows | Recovered |
|---|---:|---:|---:|---:|---:|---:|
| fact | 147 | 179 | 169 | 178 | 1120 | 4/946 |
| loopfact | 198 | 172 | 168 | 176 | 1112 | 0/936 |
| sum-divisors | 299 | 255 | 292 | 310 | 8018 | 6/3944 |
| jacobi | 378 | 288 | 290 | 285 | 20275 | 2/19992 |
| cyk801 | 132 | 14 | 14 | 14 | 6567 | 0/3524 |
| grammar-17122 | 60 | 15 | 18 | 18 | 129 | 0/102 |
| grammar-91627433 | 111 | 15 | 15 | 15 | 207 | 0/165 |
| grammar-72102993 | 106 | 15 | 15 | 15 | 182 | 0/137 |
| grammar-layout-832749 | 81 | 15 | 15 | 15 | 151 | 0/115 |

All 36 native comparisons missed the reference endpoint. The recurring two-owner restriction found 0/28 first-divergence three-parent targets and 0/1,074 confirmed high-owner targets on reference snapshots. Free recursion found 12/28 and 94/1,074. Persistence found 12/28 and 67/1,074. The first cohort is included in the second. Across the 1,074, the original-witness funnel for free recursion was 573 at rule selection, 494 at first-role retrieval, 131 at subsequent-prefix retrieval, 93 complete tuples scored and 72 original tuples issued. Alternative validated proofs bring the distinct count to 94. For pending the corresponding counts were 602, 505, 92, 53, 46, and 67. Shared per-Run budgets let retries displace other paths.

On CYK801 the native teacher committed 1,445 bindings for a single rule in the first Run. Each recursive arm issued six acceptable requests and finished after two Runs. The pending arm made three resumptions and still ended with 12 pending records. EPT was 14/6 even though only 14/6,567 derived final rows were present. On the four EggCC programs the pending pool reached its 512-record capacity in every case. It ended at 500, 512, 511 and 512 records respectively. There were 1,341, 1,679, 766 and 5,701 evictions. These measurements do not establish a sustained coverage advantage per second.

On sum-divisors the pending arm encountered a native source panic in Run 177. Its final rows and operations describe its last completed prefix. Paid proposals, visits and time include the failed attempt. Three legacy executions reached the pre-existing per-layout projection guard (loopfact, sum-divisors and jacobi). A source panic, a resource bound or a quiescent neural schedule is not a verified fixed point.

| Program, pending arm | Paid | Signed ops | EPT | EPS | Visits per signed op | Peak / final pool |
|---|---:|---:|---:|---:|---:|---:|
| fact | 530 | 275 | 0.519 | 263.8 | 252.8 | 512 / 500 |
| loopfact | 444 | 217 | 0.489 | 257.7 | 206.1 | 512 / 512 |
| sum-divisors | 725 | 465 | 0.641 | 596.3 | 128.7 | 512 / 511 |
| jacobi | 501 | 806 | 1.609 | 291.5 | 415.9 | 512 / 512 |
| cyk801 | 6 | 14 | 2.333 | 374.2 | 87.9 | 12 / 12 |
| grammar-17122 | 24 | 18 | 0.750 | 738.0 | 21.9 | 31 / 31 |
| grammar-91627433 | 6 | 15 | 2.500 | 693.0 | 16.8 | 14 / 14 |
| grammar-72102993 | 8 | 15 | 1.875 | 750.8 | 16.8 | 16 / 16 |
| grammar-layout-832749 | 6 | 15 | 2.500 | 726.2 | 33.5 | 48 / 48 |

## Accounting

* Frozen proof coverage uses native verifier winner identity and counts each target at most once, including alternative proofs. Online per-Run coverage uses only visible reference-final facts whose source coordinate has been reached. Each first omission is counted once. Recovery requires observing that fact later. Unreached source coordinates count against final coverage and are excluded from observed recovery opportunities.
* Final coverage compares reference rows using finite grounded constructor witnesses, table, values and visibility, independent of local eclass numbering. Inconsistent alignments are excluded. This conservative witness test can miss a different equivalent representation. Teacher self-comparison covers every reference row. Full endpoint identity is tested separately with native state_sha.
* EPT is the number of distinct native effective operations attributed to named tokens, divided by all paid external tokens. The numerator counts newly visible rows, effective writes, unions and visibility changes. Uncredited operations are shown separately. Rejected and duplicate tokens are paid. Internal retries that issue no token cost visits and wall time. EPS divides the same numerator by actual online wall time. On divergent states, these numerators can include operations on a different legal trajectory. The certified_prefix_ops field gives a conservative count over the exact common reference prefix. These measurements do not establish an end-to-end speedup.
* Online wall time includes native startup, snapshot delivery, incremental store and key maintenance, Python CPU inference, retries, native checking, commits and final export. Model loading, teaching, offline graph comparisons and plotting are excluded. These are single wall observations. Frontier is the distinct owner count entering the decoder in a Run, including owners whose typed projections were prepared by the legacy decoder. Candidate visits charge typed positions and retrieval bucket entries. Partial-state evictions and active pool occupancy are separate from global Cell Memory. The plot has a separately scaled time and coverage axis per program. Dots mark the last measured state.

[Coverage over time](coverage.svg) · [Every reached Run](runs.csv) · [Proof funnel, costs and terminations](results.json) · [Frozen weights](dagger.pt)

## Reproduction

Run inside the instruction_pointer directory with the previous experiments' artifact root as ROOT. It must supply the three original captures, frozen native Jacobi plan, structured-retrieval/field.pt, relation-experiment/train/model.pt, the oracle-survey CYK lowering, the existing high-order cohort exports and release binaries in unified-scale/build. Build the native cell_token_replay example with feature cell-token-ept. Python needs Torch and NumPy. Matplotlib is needed only for the figure. The checked-in checkpoint reproduces evaluation independently of training caches.

```sh
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent"
python recursive_train.py "$ROOT" teacher
python recursive_rollout.py "$ROOT" expert
python recursive_train.py "$ROOT" dagger
python recursive_rollout.py "$ROOT" online --arms legacy two free pending
python recursive_rollout.py "$ROOT" frozen fact loopfact sum-divisors
python recursive_coverage.py "$ROOT" fact loopfact sum-divisors jacobi cyk801 grammar-17122 grammar-91627433 grammar-72102993 grammar-layout-832749
python recursive_results.py "$ROOT" run-recall/recursive-agent
python plot_recursive_coverage.py
```

Existing sum-bits semantic acceptance on its saved exports returned pass. It is an independent regression check for that contract.
