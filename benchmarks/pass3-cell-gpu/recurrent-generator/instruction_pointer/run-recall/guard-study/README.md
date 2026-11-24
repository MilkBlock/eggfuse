# Where the exclusive Cell Stream spends its work

**Neural Execution · exclusive · actual native Cell runtime.** CYK801 completed 43 source Runs. All 1,067,222 rejected requests failed the same span adjacency condition. Changing how the model reads Cell memory preserved the reference endpoint and reduced decoder time. Training an additional validity head on the available fields barely reduced paid requests at full coverage. These are two separate costs.

## Why Run 1 looks different

| CYK801 | Paid | Accepted proofs | Rejected at the native primitive result |
|---|---:|---:|---:|
| Run 1 | 1,445 | 1,445 | 0 |
| Runs 2–43 | 1,070,768 | 3,546 | 1,067,222 |

The lexical rule reads a terminal and a string position sharing a field. The two recursive source rules construct a span and its parse tree. Each additionally requires the second child's start to equal the first child's start plus length. Native checking had already resolved every named parent, bound the table atoms and checked the rule watermark. Query instruction 2 computed a defined sum, then failed to bind that sum to the selected right child's start. Rules 1 and 2 accounted for **533,611 failures each**. Run 2 alone accounted for 232,114. No exact join or primitive outcome was supplied to the online policy.

The audit compared reference execution with a replay of only the learner's accepted requests. All Run boundaries had byte-identical visible row change histories, schedules, ordered RHS, writes and endpoint hash. The bad proposals were present even on this reference-equivalent trajectory. The stream retained its neural threshold at each prefix. Dropping the output cap exposed how many incompatible spans cleared it.

Before issuance, the policy has the three operand fields as port hashes, their learned vectors and Bake's argument positions. The recurrent stream scores direct shared fields and pools port keys. It receives no integer magnitude, computed span endpoint or primitive verdict. Hash identity supports repeated values; there is no supplied arithmetic relation between the hashes of three different values. This measures observability and the behavior of these weights. It does not establish a general impossibility of learning this distribution. [Native attribution by Run and rule](guard-attribution.json)

## Independent CYK801 rollouts

| Policy | Derived facts / 6,567 | Paid | EPT | EPS, single run |
|---|---:|---:|---:|---:|
| Complete Stream | 6,567 | 1,072,213 | .006125 | 169 |
| Joint head, validation minimum | 6,567 | 1,072,074 | .006126 | 162 |
| Joint head, validation 5th percentile | 6,434 | 1,040,198 | .006185 | 162 |
| Separate query/key projections, 8 bits | 4,096 | 564,311 | .007258 | 927 |
| Shared projection, 8 bits | 6,567 | 1,072,213 | .006125 | 523 |
| Shared projection, 8 bits, delta-aware postings | 6,567 | 1,072,213 | .006125 | 637 |

The four alternating pairs for the complete stream and the shared 8-bit stream returned identical final SHAs, signed operations and paid counts. Median wall times were **40.90 s and 12.39 s**, a 3.30× ratio in favor of the shared projection in all four pairs. This is 161 and 530 signed operations/s using the median walls. The native exact control took 0.143 s and the native teacher replay took 0.057 s. The shared stream still took 86× the time of native exact execution. The delta-aware variant has a single timing observation. In the paired runs native named verification took about 0.62–0.66 s, included in roughly 3.6–3.9 s of request transport plus verification. Remaining online wall includes memory, decoder, scheduling and commits. Exact residual search during neural execution is zero. Native controls include process startup, as do the neural runs; offline semantic alignment and checkpoint loading are excluded. The machine was shared with other experiment jobs. [Four paired observations](pairs.json)

**Candidate discovery.** Bake supplies a shared role/field link. The sparse stream addresses a bucket of the learned field projection, then runs the frozen recurrent scorer on each returned port. Many distinct values share a bucket. It never tests raw field equality, calculates the primitive, or seeks a missing parent in the verifier. Roles without a shared link retain typed traversal. Tied query/key projection makes equal encoded fields address the same bucket. Separate projections can send a valid partner to an unread bucket. Delta-aware postings select the new-version sublist only if the final partner must supply the seminaive delta. This test uses the consumer's watermark and already chosen parents.

| Measured CYK801 access | Complete | Shared buckets | Shared, delta-aware |
|---|---:|---:|---:|
| Prefix/candidate positions traversed, before watermark filtering | 500,366,386 | 40,288,809 | 1,240,039 |
| Positions scored by the recurrent model | 18,019,020 | 1,240,039 | 1,240,039 |
| Typed interface entries read into rule-local banks | 529,814 | 529,814 | 529,814 |
| Index entries prepared (stored codes and source queries) | 0 | 496,886 | 504,123 |
| Bucket probes | 0 | 167,579 | 167,579 |
| Postings returned | 0 | 40,287,364 | 1,238,594 |

Positions, scores and returned postings are successive touches and overlap. The earlier visit metric sums scored positions and interface reads. It conceals the large traversal before freshness filtering. Index counters here cover rule-local reading, sorting and posting construction on top of the existing incremental field index. Their construction and the underlying index updates are included in wall time. All three arms still sent the same 1,067,222 invalid span proofs. [Access-counter replay](access.json)

**Hard-negative training.** Freeze Compose and the field encoder. A joint MLP reads two pooled Cell contexts, three ordered primitive-argument channels and four counts from the schema. When several primitive instructions contribute to a channel their field vectors are averaged. Train full-proposal validity on 4,510 accepted requests and 4,879 hard negatives (3,611 guard and 1,268 binding). Skip 6,832 duplicate receipts. Empty-parent requests bypass this readout. Training used the first 100 source Runs from the four EggCC programs and the four training grammars. They are in-domain evaluation for EggCC. Grammar 17122 alone supplied the two score thresholds. CYK801 rejects were reserved for analysis. The previous Compose training used token renaming; this readout has no owner-address input. Training used 300 balanced AdamW steps on Metal. Online reads and inference used single-threaded CPU PyTorch with native Rust verification. The frozen model and thresholds are provided. [Training and validation counts](training.json) · [Weights](joint.pt) · [Executable, model and program digests](provenance.json)

On validation the conservative threshold retained all 76 valid requests and all 272 invalid ones. The tighter threshold retained 72/76 valid and 266/272 invalid ones. On CYK801 the conservative threshold saved only 139 paid requests. On the held-out layout it lost 24 of 151 reference facts. The added head provides little evidence for adopting a learned signature-time filter with this observation contract.

## Multiple workloads

| Workload | Complete Stream, derived | Shared 8-bit stream, derived | Paid, complete → shared |
|---|---:|---:|---:|
| Newly generated grammar 4691132 | 79/79 | 79/79 | 195 → 195 |
| Grammar 72102993 | 182/182 | 182/182 | 538 → 538 |
| Held-out rule layout 832749 | 151/151 | 151/151 | 611 → 611 |
| fact | 363/1,120 | 363/1,120 | 10,851 → 9,947 |
| loopfact | 449/1,112 | 449/1,112 | 18,075 → 16,629 |
| sum-divisors | 1,404/8,018 | 1,404/8,018 | 413,570 → 376,781 |
| jacobi-1d | 1,677/20,275 at 60 s | 1,884/20,275 at schedule end | 1,124,226 → 1,477,962 |

All four CYK programs matched their reference SHAs with the shared projection. The new grammar was generated after fitting and its teacher tape independently replayed. No EggCC arm reached the reference SHA. fact, loopfact and sum-divisors ended their schedules. Jacobi's shared stream ended after 713 Runs; its complete stream reached the time budget. The separately projected 8- and 4-bit readers instead reached a native source assertion at Runs 63 and 76. Partial coverage at an assertion or deadline is reported for the last sealed graph, with costs including work already attempted. A schedule end alone is not a verified fixed point.

Coverage counts derived final reference facts after aligning named constructor witnesses. EPT counts signed effective native operations per *all* paid requests, including rejected and duplicate requests. EPS uses the same numerator and inclusive online wall. Divergent graphs can earn signed operations outside the reference. Use coverage beside EPS. Run curves report committed boundaries and an endpoint with attempts in a possibly unfinished Run. Full Stream remains the coverage control. No Higher Cell or new operation-credit convention was introduced. [Coverage curves](coverage.svg) · [Per-Run CSV](runs.csv) · [All policy results, costs, verdicts and termination reasons](results.json)

The observed nondominated policies use all three axes (Coverage, EPT and EPS) within a workload, restricted to schedule-complete trajectories. Single-trial differences on small grammars should be treated as timing noise. [Measured operating points](frontier.json)

## Reproduction

Use the original recursive training artifact root and its native release build with cell-token-ept. From instruction_pointer run the following. The joint readout inputs can be regenerated by fit or supplied using the checked-in weights and training.json. Use the same host and a single Torch CPU thread for rollout. The asymmetric 8-bit arm originally had a 90 s safety budget; all its trajectories stopped before 6 s.

```bash
python recursive_corpus.py "$ROOT" "$ROOT/recursive-agent" --extra-blind 4691132
python guard_study.py "$ROOT" fit
cases=(cyk801 grammar-4691132 grammar-72102993 grammar-layout-832749 fact loopfact sum-divisors jacobi)
for arm in control joint-recall joint-balanced s8 s4 s4-recall p8 p8-delta; do
    python guard_study.py "$ROOT" "$arm" "${cases[@]}" --seconds 60
done
python guard_study.py "$ROOT" p4 grammar-4691132 --seconds 60
python guard_timing.py "$ROOT" run-recall/guard-study/pairs.json
python guard_report.py "$ROOT" run-recall/guard-study
python plot_guard_study.py
```

The work uses the native replay and delta coverage controls from the earlier Cell Stream experiment. The release runtime library passed 86 tests, the decoder suite passed 31, and the documented sum-bits semantic acceptance returned pass using the reviewed saved inputs.
