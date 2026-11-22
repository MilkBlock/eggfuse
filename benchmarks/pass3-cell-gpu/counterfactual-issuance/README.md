# Counterfactual credit at signed Cell issuance

The native CPU issuer chooses between a leaf and its licensed compound completion. For training, the Rust overlay allows one actual issuance decision to be flipped. The two executions start from the same generated input and seed, verify the preceding decision prefix, and check source effects, endpoint identities and semantic roots in both outcomes. Later sampled actions can diverge. Their consequences contribute to the episode return. The learner uses the existing three decision features and differentiates the expected paired reward with respect to the issuer logits.

```sh
D=benchmarks/pass3-cell-gpu/counterfactual-issuance
python "$D/build.py" "$OUT"
python "$D/train.py" "$EXP" "$OUT/session" "$OUT/policy.json" --episodes 128 --device cpu
python "$D/evaluate.py" "$EXP" "$OUT/session" "$OUT/policy.json" "$OUT" --cases sum-bits 3mm
```

Training uses random generated inputs. Evaluation runs native EggCC workloads. Reward uses leaf minus full paid proposals plus one eighth of the difference in root header checks, capture reads and block admissions. The weighting is an experimental operation proxy. `checked_internal` counts the signed verifier's direct internal binds. Greedy evaluation uses CPU inference. Training used CPU for this experiment.

In 128 paired decisions the completion had positive reward 57 times and negative reward 71 times. Sixteen of the nineteen distinct observed feature vectors occurred with both signs. This is evidence of observational ambiguity in this dataset. It does not identify which additional input will resolve it. The trained policy, the earlier policy and always issuing the compound performed identically on both real workloads. Gains over leaf-only execution come from the existing block admission and verification path. This experiment provides no evidence that the new RL policy saved additional work. Results and feature-group counts are in `results.json`.

## Paid proposals as the sole training return

catalog_credit.py refits the three-feature issuance head on the saved paired, randomly generated decisions using only leaf paid packets minus full paid packets. Prefix checks and equality of both native outcomes were enforced when the pairs were captured. Among 128 forks, 57 saved two packets, 71 saved zero, and none lost a packet. Thus a fixed-full policy already maximizes the observed paired return, regardless of network width. Later sampled actions may differ after a forced action, so these are paired episode outcomes.

The frozen actor runs on complete sum-bits and 3mm. At load time, the compiler supplies the applicable Let paths and the separately checked Set route. The widest catalog enumerates one- and two-edge paths through seminaive, sole constructor atoms with distinct variable slots; the native loader rechecks eligibility. Eligibility and static wiring are compiled. The trained actor decides whether to sign the typed continuation on eligible roots; it does not dynamically choose one among thousands of distinct paths. All external singleton and multi-parent proposals and selected independent children are paid. Only actually committed internal source ordinals count as savings. Each arm checks against the independent native reference and preserves the leaf arm's physical identities, source commit and ordinal accounting, and constructor birth and endpoint digests.

Reproduce with the native counterfactual session and the paired training artifact from train.py:

```sh
python catalog_credit.py EXP NATIVE_SESSION PAIRED_POLICY_JSON OUTPUT
```

The frozen combined catalog saves 419 and 10,758 external proposals relative to leaf issuance. Compared with the full two-edge Let catalog alone, the net reductions are much smaller. The Set path can compete for a source occurrence already covered by another template, so terminal Set commits cannot simply be added to Let savings. The fixed-full control matches the learned head. This experiment exercises the existing filtered CPU issuer and direct internal verification. It neither times the alternatives nor establishes a general autonomous neural search rate.

## Interchangeable owners of the same successor

owner_forks.py replays four interventions with the same program, generated initial rows and native issuance page. Both named roots are offered before any result feedback. The trace must agree through the last address on that page. None, only A, only B, or both may sign the existing 143 → 55 → 143 template; every other root in the episode takes the leaf action. All four must agree on source execution, endpoints and semantic root bindings. The script separately runs exact matching on the same generated program and checks the leaf trajectory against it. Saved proposals must equal distinct internally committed source ordinals. Source ordinals, rather than serials allocated by the proposer, identify common successors across interventions.

The shared-result generator makes two distinct Get keys return the same Expr e-class. Both source RHSs therefore request Single on the same operand. Half of the episodes also start with an existing Single for that operand. The native scope is four always-run iterations with the real EggCC rules. It is separate from execution of a full EggCC input. A/B assignment is shuffled; the earlier source execution owns the fresh result in the original implementation. Distinct address choices and asymmetric returns alone do not establish that two owners compete for the same successor.

The optional reuse_returns capability licenses the existing typed first edge on a signed block when the constructor actually returns a visible fact. It records the executing producer cell and instruction separately from the returned fact and version. At the original Run, release checks the current member, physical witness, version and returned address. A previously registered witness is retained. Only the first licensed registration can supply a given successor; the option grants no additional constructor birth. Corrupting the recorded release address must fail even when the physical operation index differs from the signed instruction.

Build this directory's native overlay. Run owner_forks.py EXP SESSION OUT with EGGFUSE_GENERATED_GET_EPISODES=1, passing --shared-result in both arms and --reuse-returns in the treatment. Use distinct output directories. Run catalog_credit.py with --reuse-returns for the complete sum-bits and 3mm comparison. paired-owner-results.json contains the aggregated same-page interventions and the full-workload paired arms.

## Can the generator observe when a signed completion pays off?

Build the counterfactual session, then run `EGGFUSE_GENERATED_GET_EPISODES=1 python context_credit.py EXP SESSION OUTPUT`. Training uses 32 randomly generated pairs with the dot-product program; evaluation uses 32 fresh pairs with the sum-bits program. Each episode substitutes the generated inputs and executes four iterations of the EggCC always-run rules. The experiment controls the first issuance of the 143 → 55 → 143 family; other roots take the leaf action. The pair changes one Single input between an unrelated value and the Get output. The generator shuffles token order, adds unrelated rows and sometimes places the subject value in a distractor's output port.

Native leaf and signed executions supply the regression target in paid external proposals. Both agree on the strict source trace and semantic roots, and savings reconcile to uniquely committed signed children. The old count/age inputs, a manually joined context bit and a learned pooling read over all initial token rows use the same paired data. The learned read receives row type and exact port comparisons to the subject, trains with backpropagation on CPU, and pools without position encodings. The live test computes the frozen score in Python from the source input before invoking Rust. Rust applies it to the first eligible issuance without an oracle serial. Every resulting trajectory is checked against exact execution and the corresponding paired token count.

In the held-out episodes the 73-parameter reader selected 32 of 64 possible signings and retained all 64 saved external proposals. Always signing the first root attained the same paid count. The read distinguishes productive signings; this experiment changes neither the available library nor the best attainable FEPT. The generated single-root setting and supplied address comparisons limit what can be inferred about autonomous parent selection and full workload execution.

## Two continuations from the same Get

Rule 143 constructs both Single(Get(expr,i)) and SubTuple(expr,i,1). The first continuation can supply rule 55 and its subsequent Set. The second can supply rule 137 from the named SubTuple result. The receiver now accepts licensed single-atom consumers containing i64 literals and distinct slots. At release it checks each literal against the visible, versioned physical row before projecting slots. The sender may restrict a signed root to a subset of the compiled first edges. Unknown selections fail session configuration.

Build the native session and run `EGGFUSE_GENERATED_GET_EPISODES=1 python route_credit.py EXP SESSION OUTPUT`. Each random quartet varies whether the initial facts already contain either constructor key. Training uses the dot-product program and evaluation uses the sum-bits program, with synthetic inputs and four always-run iterations in both. Native interventions measure leaf, Single, SubTuple and combined issuance at the first eligible root. Every gain must equal the number of distinct signed commits, and the baseline and interventions must preserve the strict source execution. A CPU neural readout trains on paid differences by backpropagation. Its input is the initial token multiset with row types and typed equality to the Get subject's ports. It chooses the first action before native execution. Additional capacity, update and dataset ablations replay the four checked counterfactuals. The one-route control restricts the output vocabulary for comparison.

Run `catalog_credit.py EXP SESSION PAIRED_POLICY_JSON OUTPUT --reuse-returns --literal` separately for complete EggCC programs. This experiment retains the previous actor and widens the catalog, first with the single SubTuple continuation, then with all eligible typed one- and two-edge Let paths. Statically conflicting producer literals are excluded. Dynamic arguments still require a check at the receiver. These complete-program gains measure catalog coverage. The context-dependent route selector was evaluated only on the generated episodes.

The held-out policy paid 1,895 tokens in 64 episodes, equal to always allowing both continuations. It requested both in 16 episodes. The best policy constrained to one continuation paid 1,911, compared with 1,927 for always choosing Single. Eight optimizer updates gave the same paid count despite failing to predict all three action gains correctly on any episode. With four balanced training quartets the model predicted all gains correctly in 64 episodes. Compare the two quantities separately. On complete sum-bits and 3mm, the expanded catalog saved a further 154 and 4,000 proposals against the previous wide catalog with reused returns. Surviving births and all checked source traces agree. [Paired results and workload audits](route-results.json)

## Repeated neural route decisions on complete programs

Build this directory's overlay. Run `EGGFUSE_GENERATED_GET_EPISODES=1 python catalog_credit.py EXP SESSION PAIRED_POLICY_JSON OUTPUT --recurrent`. The leaf and fixed wide-catalog controls and the neural arms execute the entire original workload schedule. The reader controls the two compiled first edges of externally signed Get roots. Other catalog edges, internal proof checks and source scheduling keep their existing behavior.

The issuer reads visible Get, Single and SubTuple rows on the current page and compares their typed fields with the named Get subject. These 15 binary inputs have the same layout as the generated training examples. Repeated feature patterns share their encoder result. Max pooling and a three-output head run on CPU with frozen weights. Each lane carries its own selection in the existing tag word; the signed root consults it when registering the compiled first edges. The verifier continues to validate named rows and actual execution. Context collection and inference are part of this prototype; these experiments measure paid proposals without a timing claim.

The first reader uses the 64 generated first-decision examples from route_credit.py. A second training generator shuffles multiple Get roots and optional existing constructor keys. From each nonempty decision Run it samples an issuance and forces four alternatives at its serial, keeping every other route open. It checks the common predecision observations, original source trace, endpoint identities and net internally committed proposals. With seed 194700 and 48 episodes it obtains 48 first-Run and 33 later-Run counterfactuals. The controls add either the 48 first-Run rows, an equal-sized mixture of 15 first-Run and 33 later rows, or all 81 rows to the original training set. Every arm uses the same architecture, optimizer and update count. These splits distinguish additional context diversity from the mere inclusion of later decisions.

Use `--expected` to compare rounding predicted conditional mean gains to integral proposal counts with using their continuous values directly; both policies consume the same frozen weights. Reference comparisons check every original Run and the physical constructor birth and endpoint digests. Results apply to these two controllable routes. The broader catalog still supplies most of the complete-program savings.

On complete sum-bits and 3mm the first-decision network paid 12,097 and 543,519 proposals. The broader generated training set with rounded scores paid 12,089 and 543,422. Using the continuous conditional mean with the same weights reached 12,089 and 543,316, matching fixed admission of both compiled edges on each workload. The reader executed in 22 and 34 distinct Runs. The equally sized mixture of initial and later counterfactuals underperformed the extra initial-only set on both programs. These data support context diversity and preserving fractional expected gains; they do not establish an advantage for later-Run sampling alone. [Action counts, sample distributions and strict audits](live-route-results.json)

## Depth and constructor Set results

A signed root may now authorize a bounded sequence of actual constructor returns. The first edge and every adjacent pair must occur in its compiled catalog. The native receiver verifies the actual named row at each consumer Run. An internal child inherits the original root and depth limit; the existing specially certified two-step Set receipt still terminates its own chain. The runtime retains the traversed path for ownership and auditing. The pair catalog avoids enumerating every long path in advance.

Constructor Sets can contribute either a newly activated physical row or the actual returned witness for an existing visible key. The producer stages the result until RHS success. Existing ownership and the separately certified Set receipt have priority. The current consumer proof covers one constructor atom with distinct slot bindings and supported literals. Uncovered bindings continue through the existing issuance path. This implementation does not license arbitrary mutable functions or joins from a Set output.

Use the native builder and the complete-program commands below. TRAINING is the saved paired policy input used by catalog_credit.py. MODEL is recurrent-model.json produced by its --expected study; these weights are frozen across complete-program arms.

~~~sh
python catalog_credit.py EXP SESSION TRAINING OUT_WALK --walk
python catalog_credit.py EXP SESSION TRAINING OUT_SET --set-reader MODEL
EGGFUSE_GENERATED_GET_EPISODES=1 python depth_credit.py EXP SESSION OUT_DEPTH --device cpu
~~~

walk_credit.py resolves each signed prefix to its actual committed source, verifies the physical birth or reused return and checks that the consumer cites the correct version. The separate certified-terminal audit remains active. The workload comparison reconciles all paid reductions to distinct internal commits while checking ordered RHS, physical identities, schedules, unions and endpoint state. Comparing depths requires counting displaced proposals as well as newly internalized ones.

The depth-policy experiment generates one initial rule-138 subject per episode and verifies that exactly one root received its requested cap. It branches between two and eight edges with the same other roots and runs the actual source schedule in both arms. The network trains by backpropagation on the external proposal difference, with MPS as the default device. Frozen CPU weights select the action. Its live test selects the cap before executing the generated input. The extra features connect equal Expr ports between input tokens; the smaller encoder sees each token only relative to the subject. The held-out samples use different seeds and the sum-bits rule bundle with generated initial data and four always-run iterations. On the complete unmodified workloads the previous Get policy still selects its two local edges; the depth bound in those arms is fixed.

The frozen Get reader with a depth-eight catalog paid 11,950 on sum-bits and 539,418 on 3mm. Depth two with the same Set edges paid 11,974 and 540,603. Depth 32 with fixed admission gave the same outcome as depth eight. On 3mm the depth-eight trajectory contained 1,185 three-hop and 28 four-hop commits, and displaced 28 one-hop commits compared with depth two. No longer commits were observed. The rules generating the deep roots differed from the Get roots on which the previous route reader was trained.

In the generated depth experiment the linked-input network chose a deeper cap for 52 of 64 subjects and paid 1,464, equal to always choosing depth eight. The subject-only encoder paid 1,469 with either 64 or 256 training examples, including when widened to 1,145 parameters. The linked encoder used 1,121 parameters. These scope-limited results use CPU training and inference. MPS training and a separate MLX probe could not reach the host Metal compiler service. [Workload and training results](depth-results.json)

## Online depth selection

An external rule-138 root now carries its own two- or eight-hop decision in its signed page lane. At issuance the CPU reader takes the SubTuple subject from the lane and reads the visible Get, Single and SubTuple tokens. It computes the same 68 typed features used in depth_credit.py, including neighbor port occurrences with self-contributions subtracted. The max model may pool preactivations before applying tanh because tanh is monotone. The attention variant uses a learned score and normalizes over the visible rows. The anchored max variant pools rows sharing any Expr port with the subject; its port messages still describe the full current context. These variants change issuer computation. The receiver inherits the signed limit and checks every released edge through the existing path. The audit reconciles actual committed root serials with their signed limits and rejects any over-depth commitment.

The four baseline controls are the previous frozen Get route policy, forced shallowness on rule 138, forced depth on rule 138 and the original depth network trained on clean synthetic episodes. All other eligible roots retain their existing eight-hop limit. The table comparisons count committed depth decisions using the native Run schedule. No latency result follows from these scans or neural choices.

To reproduce, build the native session in this directory. Run `depth_credit.py EXP SESSION TRAIN --device cpu --clutter --check-native` with EGGFUSE_GENERATED_GET_EPISODES=1. Mixed training replaces half of 256 generated examples with inputs containing extra Get, Single and optional unit-length SubTuple rows. It retains the same parameter and optimizer settings for each individual architecture. The parity check re-executes the generated episodes and compares Python and Rust choices at the unique original rule-138 subject. Then run `catalog_credit.py EXP SESSION PAIRED_POLICY_JSON OUTPUT --set-reader GET_MODEL --depth-model TRAIN/clean_max.json --depth-variants TRAIN`, using the frozen Get route weights from the preceding expected-gain study. Threshold-zero arms use the sign of predicted token savings. No complete EggCC workload supplies training labels.

On complete sum-bits the mixed-training anchored max reader authorized two hops 59 times and eight hops 35 times. On 3mm it chose two hops 1,019 times and eight hops 2,058 times. These decisions preserved the fixed-deep totals of 11,950 and 539,418 paid proposals. Restricting this root family to two hops paid 11,956 and 539,874. The unanchored mixed max model paid 11,952 and 539,593. The original clean max reader chose eight every time. The mixed dataset and the subject-linked pooling restriction together account for the selective result on these workloads. The experiments used CPU training and inference. [Frozen workload and generated ablations](live-depth-results.json)

## Returning a row to a consumer with scalar guards

The bounded-walk issuer can sign a continuation into a seminaive rule with one constructor atom followed by integer comparisons. Bake binds each operand to a literal or a column of that same row. At release the receiver checks the named row's liveness, table, identity, version and watermark, evaluates each comparison with the runtime primitive, and stores its actual result in the query's destination slot. The destination is part of the matched input frame even when unused by RHS code. Failed comparisons leave the witness on the ordinary path. A guarded rule with uncovered rows retains residual issuance. The receiver performs no table search to establish a comparison.

Rebuild the native session; run catalog_credit.py with the same EXP, SESSION, PAIRED_POLICY_JSON, OUTPUT and frozen Get and depth weights as the online depth experiment. Add `--row-guards --cases dot-product sum-bits 3mm` and pass the synthetic mixed_anchored.json as `--depth-model`. For each workload the audit compares the guarded and previous catalogs using identical weights. It reconciles the source commits of rule 138 with signed internal children and externally issued roots. A workload can have zero external depth decisions when every occurrence is owned by another root. Failed predicate checks and net saved proposals are reported separately from guarded child commits. The frozen network controls the remaining external roots; Bake supplies the new continuations.

On dot-product, sum-bits and 3mm the new catalog took over 46/46, 87/94 and 2,888/3,077 rule-138 commits. With the original depth threshold the paid totals fell by 46, 87 and 2,730. On 3mm the net change is smaller than the direct takeover count because other internal completions changed. Using positive expected savings on the remaining roots recovered eight more proposals and matched the fixed-eight control. Only rule 138 recorded guarded child commits on these workloads. [Frozen weights, counters and strict comparisons](guarded-row-results.json)

## Independent parent addresses at issuance

Add `--parent-projection` to the guarded workload command to run the leaf and frozen positive-expected-savings arms. The offline audit reads the native commit and allocation ledgers in source order. For each external commit with at least two distinct versioned parent references it tries each earlier producer that allocated one of its fact frames. It measures how many references are absent from both that producer's input witnesses and its physically allocated fact frames. Inherited references require an exact version match. Physical output addresses still need a release-time version and visibility check. Reused returns allocated elsewhere and producers contributing only input witnesses are outside this measurement.

On 3mm, 3,997 of 144,647 external multi-parent commits had complete address coverage by such a producer. For 2,305 of the 31,574 commits with at least three parents, the best producer supplied all but one address. Rules 501 and 504 accounted for 934 and 929 of the full-coverage cases for consumer 286. The producer RHS builds a TCPair and passes the resulting slot to PotentialExtractedExpr; consumer 286 joins those two facts. This identifies a concrete two-output template for issuance experiments. This retrospective count measures address availability, without certifying release order, attributing savings, or changing the learned policy. [Workload breakdown](parent-projection-results.json)

## Producer-side proposals carrying two actual output ports

Add `--pair-owner --pair-device cpu` to the parent projection experiment after rebuilding the session. Bake identifies consumers with the ordered PotentialExtractedExpr and TCPair query and finds producer effects that feed the returned TCPair value to the outer constructor. It follows slot copies. At a successful producer RHS boundary the issuer receives the two actual constructor witnesses, including returns owned by another instance. It can release a shadow proposal naming both rows and their versions. Its five Boolean inputs indicate reuse of each constructor, the two row versions matching the current epoch, and prior issuance of this versioned pair. The export evaluates the frozen MLP on all 32 inputs. Rust executes the resulting decision table. The template supplies both parent positions. The MLP learns when to issue a pair with that wiring.

The generated training set samples Boolean return and duplicate histories under a one-epoch delta contract. The training label asks for an unclaimed pair containing a current-epoch port. This is a supervised finite decision problem. Complete workload traces only evaluate the frozen network. Each consumer query boundary checks pending proposals by direct witness reads, visibility, version, table, shared value and watermark. The independent online generator still issues its normal packets. The replay additionally requires each successful proposal to precede a distinct later source commit with both exact witnesses and versions. It checks every native proposal, producer ordinal and parent tuple against the Python policy.

On 3mm, 4,058 of 4,114 external rule-286 commits had a corresponding prior proposal, and all 4,058 proposals passed the native check. Issuing every wired pair yielded 1,002 unmatched proposals in replay. The simple fresh-unclaimed control and all neural arms tied on the three workloads. Synthetic accuracy varied with duplicate exposure and training duration; increasing hidden width from 8 to 32 gave no further gain. The Metal forward/backward probe failed to reach MTLCompilerService on this host. Training and execution in these results used CPU. The shadow experiment saved zero ordinary packets. Its extra proposals are reported separately; paying them independently would increase the denominator. [Frozen-policy and native results](pair-issuance-results.json)

## Executing producer-owned pairs on the source schedule

Run the preceding experiment with `--pair-takeover` to let the producer issue the compound template. Its immutable packet layout authorizes the wiring and a frozen conditional release policy before RHS. The loader checks source operations, copied-slot origins, the seminaive two-atom query and its dedup key. At RHS success the existing frozen decision table selects from the actual returned versioned ports. Each selected pair is a continuation of its producer. The consumer retains its ordinary source order.

At the consumer Run, the two named reads and shared-value check establish one binding. Skipping its entire outer pivot also requires a uniqueness proof. This experiment uses the saturated class-degree upper bound and ordered scheduling method from [the fresh-only dual-return study](../strict-dual-return/README.md), now for the guarded catalog and multiple producers with reused returns. An ambiguous count leaves the outer pivot in the residual issuer. A protected pivot bypasses the ordinary candidate lookup; the original multi-parent receiver consumes a private page naming the verified pair. The reference walks every ordinary pivot. The audit compares the entire external pivot multiset with that reference after subtracting only protected pivots. Each privately issued child must commit at a distinct source ordinal under the original producer and both named versioned references.

The audit translates private packet serials by source ordinal when comparing complete commit and physical allocation records. On 3mm one omitted candidate on a protected pivot never committed, so subsequent proposal serials can differ. Run `--pair-ambiguous` to force the uniqueness proof to fail at every pivot. The producer still makes its choices and the ordinary issuer keeps all the work. This is a CPU native execution experiment with the same trained gate as the shadow run. [Paid proposals and controls](pair-execution-results.json)

Use `--pair-tables OUTER INNER` to compile a two-constructor consumer with one shared slot connecting the inner result to an outer argument. The native loader verifies the column, source wiring and dedup key. A paid producer with a provably empty query and zero query-defined slots can sign outputs too. In separate arms the Const/Int family took over 14, 4 and 21 bindings on dot-product, sum-bits and 3mm. Requiring every producer to carry an input witness left all three at zero. Const/Bool had zero takeovers. Each arm runs one family in place of the prior pair family, so their savings cannot be added to its measured result. [Family controls](pair-family-results.json)

## EPT on the exact source schedule

Add `--ept` to the guarded pair takeover command. A separate exact-search run on the instrumented runtime freezes the ordered per-Run operation ledger before the policy arms execute. Its schedule, RHS, writes, resumes, Run count and endpoint digest must agree with the independent vanilla process. Each treatment must reproduce the exact ledger digest including source ordinals. All paid external proposals remain in the denominator.

EPT credits newly inserted constructors visible at their Run boundary, effective function writes (including multiple genuine improvements to a key), effective unions and visibility changes. The union audit carries the enqueueing RHS through the FIFO and only counts a successful class link. An absent row that subsume creates and immediately hides earns no visibility credit. The audit checks the full write and union event streams. An operation gets model credit when its originating RHS has a verified root with named independent witnesses and compiler-determined remaining reads, or belongs to a verified signed descendant of such a root. Maintenance with no proven RHS owner and incompletely attributed roots have separate columns. The audit is for settled ordinary source Runs; it has no latency result.

On 3mm rule 153 issued 40,018 committed RHS applications and produced 10,900 effective function writes. Rule 317 issued 7,393 and produced 1,957 effective class links. Both had zero credited constructor births. Across the leaf and composed arms the signed numerator was constant within each workload, so both EPT and FEPT ranked the arms in the same order. EPT exposes which operations bought that score. [Reference digests, attribution, denominators and both metrics](ept-results.json)

## Source-side filtering before token issuance

Use the guarded EPT command with `--source-delta local` after rebuilding the native session. The issuer can see literal constraints, repeated slots and fully bound integer comparisons on the pivot. Its trained decision table uses the operation and the observed field ordering. The loader checks the bounded table against the operation semantics. The audit independently checks every omitted lane against the original matcher before comparing the full reference ledger. Training uses synthetic comparisons on CPU. The distinct-only training control uses the same model capacity and sample budget with equal operands withheld.

On 3mm, training with ties reduced paid tokens from 532,621 to 519,987 with identical signed operations. The distinct-only arm paid 521,344. The rule 153 diagnostic correctly identified all 10,900 effective writes and 29,118 unchanged outcomes individually. These unchanged outcomes remained valid applications. The savings came from other rules whose pivot already contradicted the query. This experiment measures native token issuance and semantic attribution. It does not establish a latency gain or an advantage over compiling the comparison table directly. [Workload results](source-delta-results.json)

## Choosing independent parents from earlier token returns

Add `--history-ports` to the source-delta workload command after rebuilding the native session. Rust records the issuing epoch, execution ordinal, RHS effect, actual versioned return address and the first field of Get and HasArgType. Those two typed ports are the compiled interface of rule 518. The CPU reader replays their returns in source order and issues pairs naming both owner/effect exports. Constructor reuse retains the actual versioned witness. The source still executes independently. Initial facts, retirements, refreshed versions from repair and inherited input ports are outside the reader interface. Its proposals have no effect on the source run.

A new return scores all opposite-role addresses in memory. Each 64-bit subject has a binary encoding. A fixed matrix product gives the bit mismatch count and a learned two-parameter affine head scores the pair. Training uses 512 positive and 512 synthetic negative examples. Replacing half the random negatives with one-to-four-bit differences holds model size, sample count and optimizer budget fixed. On the finite feature domain the learned hard-negative head accepts exactly zero mismatches, so direct equality would implement the same predicate. The workload evaluation separately checks both physical witnesses and versions against later commits. Each proposed pair can receive credit once. Supplied template roles, exhaustive address scoring and offline reference validation limit what the result establishes about learned search.

| Workload | Source commits | Both inputs in prior returns | Matched / proposed with eight choices | Matched / proposed with all positive choices |
|---|---:|---:|---:|---:|
| dot-product | 125 | 117 | 117 / 147 | 117 / 147 |
| sum-bits | 175 | 56 | 56 / 216 | 56 / 216 |
| 3mm | 4,667 | 4,220 | 3,990 / 5,419 | 4,220 / 5,649 |

On 3mm the uniformly trained eight-choice head issued 83,704 proposals for the same 3,990 hits. Removing the eight-choice cap from the hard-negative head recovered 230 further bindings with 230 further proposals. Clearing the address memory between return epochs yielded zero pairs on all three programs. Every matched pair in this replay named distinct earlier owners. Of the remaining 447 reference commits on 3mm, 424 had both addresses somewhere in past returns or earlier cited premises and required at least one such citation. The other 23 lacked at least one address in that traced history. These figures measure availability and retrospective proposal matches. Live retirement, delta ownership and admission can still reject a pair. This experiment contributes no measured EPT or wall-time gain. [Results and controls](history-reader-results.json)

## Native issuance from prior token ports on rule 518

Build the native session with the issuer overlay. Add `--history-takeover --history-initial --history-release` to the guarded `--source-delta local` command. The full ordinary source and guarded issuer run as separate controls. In the exclusive arm the target rule's ordinary join, frame preparation and residual enumeration are bypassed. The existing named receiver consumes the chosen parent references in plan order. Other rules still use their original issuers.

The head scores pairs of Get and HasArgType ports. Its operands come from actual constructor returns and the input slots of earlier committed tokens. An input reference names its execution ordinal and query atom. The target rule's own input citations are withheld. The initial import found zero ports of these types on all three workloads. Rust evaluates the frozen affine distance head on exact bit mismatches. The independent PyTorch replay checks the complete candidate identities and birth epochs. Every parent's logical owner, position and version must trace to a receipt available by issuance.

With citations alone, every remaining missing source commit on sum-bits (27) and 3mm (23) required a newer version of an already named physical port. On the ordinary publication boundary, the experiment now consumes changes concerning ports the generator already holds. A version change carries the original owner/position, new version and observed subject. The policy never acquires an unseen parent from the change set. Use `--history-updates` without `--history-release` to isolate this addition. The final arm delays signing until the rule opens. An eight-entry decision table learned on synthetic presence/freshness snapshots consumes two live-port and version properties: both references remain available, and each version meets the current watermark. The issuer uses token lifecycle state and the watermark for this decision. The audit separately tests every suppressed pair by its two named references and fails if it would have been valid.

| Workload | Source commits | Citations alone, valid pairs on reference trajectory | Version receipts | Signed / committed with release | Total paid tokens, baseline → exclusive |
|---|---:|---:|---:|---:|---:|
| dot-product | 125 | 125 | 36 | 125 / 125 | 12,865 → 12,865 |
| sum-bits | 175 | 148 | 96 | 175 / 175 | 11,125 → 11,125 |
| 3mm | 4,667 | 4,644 | 1,706 | 4,667 / 4,667 | 519,987 → 519,976 |

With version receipts the exclusive arm reproduced the original ordered RHS, effective writes, resumes, all audited events, schedule, source state digest, named commit inputs and EPT ledger on every workload. Before adding signed release the same policy reached identical states but paid for 25, 89 and 1,115 excess proposals respectively. These still exist as internal pair candidates with release. The three-Run-family and replay studies did not exercise this exclusive path. This experiment exercises one rule on three complete native CPU workloads. It measures semantic equivalence and token counts; exhaustive model-side address scoring, lifecycle tracking and duplicate verification in audit mode preclude drawing a latency conclusion. [Reference, failed controls and exclusive results](history-issuance-results.json)

## A history-issued root can sign a point-determined successor

Run the guarded history command above with `--history-tail-negative` to have rule 518 sign a single conditional application of rule 521 before its RHS executes. If Get and HasArgType establish a new type propagation step, the logical owner can offer the actual HasArgType return, including a reused return, to the next occurrence of rule 521. The constructor Single takes exactly one input, provided by that port. The receiver reads the versioned pivot and uses the ordinary fully determined point lookup for Single at the original Run. Each distinct returned port gets one attempt at the next eligible occurrence. Claims sharing the same actual port are deduplicated.

A successful internal check retains the matched instance. The signed child receives a private recipe and the existing verifier consumes the retained binding. A failed internal check may also discharge an external packet on the identical pivot, version and snapshot. This second saving counts only after the ordinary issuer's earlier source filters and payment threshold. Both the point check and management of the claim still cost work. The residual issuer still traverses its headers and computes row scores to preserve its source ordering and recurrent inputs. The experiment does not measure wall time.

`--history-tail` keeps failed external lanes. `--history-tail-depth 8` authorizes a bounded sequence of the same successor at root issuance. An internal child can activate the next wire only through its own actual returned effect. `--history-tail-context` makes the scale choice conditional on a prior Single port whose subject matches the result of the root Get. This arm reuses the frozen two-parameter affine distance head on the earlier token features. It uses past observations of Single, including observations that may have since expired. All arms still check current visibility before executing the child. The full arm uses a fixed action. This comparison trains no additional policy on the workloads.

| Workload | Root-only paid | Paid with one signed successor including failed checks | Successful independent proposals displaced | Failed independent proposals displaced | Signed successor checks attempted |
|---|---:|---:|---:|---:|---:|
| dot-product | 12,865 | 12,822 | 29 | 14 | 94 |
| sum-bits | 11,125 | 11,091 | 25 | 9 | 114 |
| 3mm | 519,976 | 518,453 | 1,292 | 231 | 3,103 |

The paired root-only control runs on the same executable. The audit requires identical ordered source operations, committed input values and versions, source events, schedule, final state and EPT ledger. Each signed child must have a distinct source commit, an earlier signed ancestor and the exact versioned output of that ancestor. A discharged failed lane must have no corresponding reference commit at that boundary. The full difference in paid proposals must equal successful children plus discharged failed lanes. EPT attribution follows the signed chain to its root.

On 3mm, allowing depth eight increased attempts from 3,103 to 4,395 and added no successful child beyond the first step. The context selector at depth eight kept all 1,292 successes using 4,157 attempts. On sum-bits it lost three successful takeovers. A useful larger Cell here spans two different rules. The measured traces provide no evidence for recursively repeating rule 521. [Native results and controls](history-tail-results.json)

## Retaining signed point continuations across Runs

Rebuild the native overlay and run the guarded history experiment with
`--source-delta local --history-release --history-initial --point-claims gated --point-family all`.
Each eligible producer signs static wiring to later consumers. A checked actual return supplies the
pivot and its version. Remaining reads have fully determined keys. The runtime retains this authority
while the port is live, checks the scheduled watermark and verifies the application in the original
Run. Unowned roots keep their ordinary issuer. This extends one-parent continuations.
Independent two-parent issuance from history is still exclusive to the rule 518 experiment.

The native CPU experiment preserved the signed operation components and reference ledger on each
workload. Paid tokens fell from 12,822 to 11,848 on dot-product, 11,091 to 10,476 on sum-bits and
518,453 to 450,049 on 3mm relative to the previously signed 521 arm. Fourteen consumer templates
qualified. The 3mm reduction includes 60,475 successful applications and 7,929 displaced failed
proposals. Applications that leave the reference state unchanged earn zero effective operations.

Use `--point-family size` with `--point-claims once` or `retained` to isolate authority lifetime.
On those two rules, mixed synthetic freshness training reduced exact point attempts from 2,428,978
to 53,617 compared with `--point-claims gated --point-training only_new`. The executable freshness
gate runs on CPU. It still visits retained claims and maintains version upper bounds. For the larger
family, `--point-unions batch` visited 2,601,337 entries on 3mm. The default incremental variant
rekeyed 4,006 entries and made 281,420 union probes. EPT measures signed semantic output per paid
token. These experiments do not establish end-to-end latency. [Paired native results](point-claims-results.json)

## Addressing the second history read

Add `--history-address` to the gated signed-continuation experiment above.
For the rule 518 issuer, a new receipt supplies the first port. Its role selects
a learned read instruction. The instruction names one of two memory banks and
projects one of four fields (subject, Cell id, operation or version) from the
first port. The generator owns an index from role and subject to versioned
ports; a read returns every alias at that address in stable order. A matching
pair still needs the release decision and two named checks. Template selection,
first-receipt dispatch and the storage key schema remain fixed.

The offline PyTorch policy trains on 512 synthetic receipts with randomized
fields, optimizing the total probability of actions that reach the labelled
partner address. The frozen argmax for each role becomes the two-instruction
native policy. Source runs only evaluate it. The dense control compares every
opposite-role address. The native study compares its entire issued, pending
and suppressed streams with conditional reads, then checks the source commits,
ordered effects, final state and signed ledger. It also evaluates the distinct
undertrained route on the same native history with commits provided by the
control. This measures access work, with no claim about process latency.
[Checkpoint, ablations and native access counts](history-address-results.json)

### Identifying a shared read instruction under correlated training data

Use `--address-renaming` in place of `--history-address` with the same native
binary. Keep 512 synthetic receipts fixed across 16 initialization seeds. In
the aliased fixture the Cell id always equals the subject. In the renaming
fixture exactly one receipt per role has its Cell id changed; its intended
partner address stays the same. The shared-route objective trains on the
intersection of valid actions for each role, as the deployed decoder emits
one instruction per role. This objective requires known role sharing and a
nonempty intersection. Every distinct decoded route is run on the same native
trajectory, with the selected checkpoint also exercised in exclusive mode.

The schema of rule 518 already determines the join column. A compiler can
emit the same two instructions directly. This experiment measures how training
recovers the addressing program and what an ambiguous program loses. It
establishes no advantage over static compilation and has no GPU timing.
[Routes by seed and native binding audit](history-renaming-results.json)

### Matched whole-Cell scale comparison

Add `--scale-comparison` to the gated `--point-family all --history-release
--history-initial --source-delta local` study with the frozen mixed anchored
depth model and the history-address native overlay rebuilt from this revision.
This also enables the conditional parent reads. Only the maximum signed
depth on an external rule-138 SubTuple root varies (two, eight or a learned
choice). The fixed controls bypass encoding and pooling the depth context.
The Get route policy, returned-port authorities, version receipts, private
point receiver and history-addressed 518 issuer remain active in every arm.

Three rotated native runs per policy capture schedule execution time and
caller-observed request time including audit transport. Each run must reproduce
the reference operation ledger, ordered effects, schedule, final state, and
the same rule-518 address counts, signed pairs and suppressions. Source
ordinals identify scale decisions that become internal to other tokens.
Header checks and the Set path's internal checks are separate counters.
Those Set counters cover only that path. Timings include audit instrumentation
and do not measure production GPU latency. [Counts and raw timings](scale-comparison-results.json)

Use `--fixed-subtuple-depth 8` on the guarded depth policy to select the baked
cap directly outside the comparison. On 3mm both this cap and the learned
reader signed deep on all 181 eligible roots, paid 450,049 tokens and achieved
0.454575 EPT. The median instrumented native run took 4.018 s with the baked
cap and 4.553 s with the reader. Depth two exposed 82 additional external
SubTuple roots and paid 306 additional tokens. On sum-bits the policies paid
10,476 tokens, including when all seven roots were shallow. Dot-product had
no eligible roots. These cases measure one root family on the specified stack.

### Compiling determined keys and discharging stale proposals

Use the guarded history-address command with `--fixed-subtuple-depth 8
--point-claims gated --point-family determined --own-stale-points`. This
extends the two-atom action catalog from 14 to 104 licensed consumers on the
three measured EggCC programs. The native compiler admits a constructor pivot
only if the original plan can form every remaining key input from its slots
and constants. It can project any returned field, including the actual result
of constructor reuse. The receiver still checks the complete source query,
including multiple key columns, repeated variables, types and visibility.
Known prefixes bound the newest possible matching suffix. A scalar, literal
or absent prefix uses a conservative table-wide bound. Unsealed updates go
through the ordinary point check.

The mixed synthetic policy can skip a point check when both operands are too
old for a semi-naive match. With stale ownership enabled, an ordinary lane
that would still issue a paid proposal can use the same proof, its previously
signed versioned port and its live owner to discharge it. The certificate
requires the same current table generation and union state. No per-rejected-lane
subscription is created. A separate ungated replay checks every signed
continuation and requires identical individual child and rejection receipts.
Credit counts changes in ownership of pre-existing strict paths by distinct
source ordinal, including paths the new owner displaces.

Use `--compare-point-families` to alternate the original first-field catalog
and the expanded policy four times each with source-addressed reads and
fixed depth held constant. The native time includes audit instrumentation.
Request time also includes report serialization and transport. The receiver
table-lookup counter covers the single-witness path. The effective-operations
numerator, paid rejections, exact point checks and elapsed times describe
different quantities. [Native comparisons and signed-receipt audit](projected-point-results.json)

On 3mm the expanded catalog with stale ownership paid 383,587 tokens against
450,049 for the first-field catalog. Of the 66,462 displaced proposals, 3,943
were successful and 62,519 would have failed. Both arms earned 204,581 signed
effective operations. Clearing the freshness gate verified the same 64,418
child receipts and 70,448 rejection receipts in order, with 4,763,237 exact
point attempts against 147,625. Across the entire single-witness receiver
the lookup counts were 379,845 and 380,445 for the final and first-field arms
respectively. Native schedule medians were 4.151 s and 4.044 s over four
alternating measurements each. This establishes improved signed EPT and a
reduction in paid rejection traffic; native execution time increased on this
workload. Dot-product and sum-bits also had higher native medians.

### Signing a complete point-query plan

Use `--point-family chain --compose-point-paths --point-batch-gate
--point-project-later` with the history-addressed, fixed-depth, gated
stale-ownership command above. A versioned constructor return can start any
licensed semi-naive query with at least two table atoms for which the original
native single-witness compiler finds a complete sequence of point reads and
forward primitives. The normal source pivot must match. The optional
`scalar-chain` catalog also admits a constructor followed solely by scalar
steps. On the three programs this admits one additional template and yielded
the same paid counts. The largest licensed query has eight atoms; sum-bits
actually exercised it. A template's arity is distinct from the number of
subsequent rule applications that its token can sign.

The composed variant attaches the child's static strict program to the original
signed claim when it needs no separate route, depth choice or Set admission.
It retains the ordinary checker and the actual returned version. Each control
accounts for changes in other strict paths by source ordinal and changes in
independently verified source rejections. The path audit traces descendants
back to their committed parent and actual input witness.

The batch gate can discard a rule's retained group for one invocation when the
largest registered pivot version and all relevant sealed table bounds are
older than its watermark. Skipped slots include any already retired ports;
their individual retirement check is deferred. Stale discharge at a paid lane
still checks the actual version and owner. When a later table has fresh changes,
the projected-key variant reads the named pivot and tests only the corresponding
key histories where Bake can derive those keys. A key depending on an unknown
intermediate result requires the usual check. No learned weights change across
these arms. The ungated reference replays every signed claim and compares
individual signed children and rejections, in addition to the Run ledger.

With `--compare-point-families` on `chain`, three rotated repetitions compare
the previous two-atom catalog, the expanded catalog and the freshness variant.
Native times include audit instrumentation. [Ablations, counts and raw native times](chain-point-results.json)

On 3mm the 140-template chain catalog paid 368,476 tokens against 383,587
for the 104-template two-atom control. The reduction contained 4,219 successful
proposals and 10,892 rejections. Signed EPT rose from 0.53334 to 0.55521.
Enabling the inherited static program preserved every previously signed
strict ordinal on all three workloads. The additional key-bound proof reduced
3mm point attempts from 394,468 to 155,411 while preserving every signed
receipt. Total single-witness table lookups fell from 379,845 on the two-atom
control to 367,959. In this three-way rotation the median instrumented native
times were 4.145 s and 3.973 s respectively; sum-bits had a higher native
median despite using fewer tokens. This comparison measures a broader
compiled action for an already signed token. It does not train a policy to
choose a new independent parent or measure GPU performance.

### Inheriting a signed input port

Use `--point-family input-chain --point-input-ports` with retained point ownership to include versioned constructor and mutable-function inputs already cited by a signed source. A later Run can consume that named input after checking its visibility and version. The compiled receiver must still determine its remaining reads. Add `--distinct-point-ports` to share registration of repeated observations of the same dependency and revision. Retirement reopens registration. `--compare-point-families` compares the returns-only, named-input and repeated-registration variants.

[input-port-results.json](input-port-results.json) records native Cell runtime audit results and three instrumented timing observations per variant. On 3mm the same 204,581 signed operations required 261,233 paid tokens versus 368,476. Median native time rose from 3.759 to 4.037 seconds. The change measures reuse of explicitly identified ports. Ordinary root matching can still enumerate candidates. These runs do not measure neural pointer selection or GPU inference.
