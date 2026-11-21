# Issue a union-position hint before validating the rule or walking reverse readers

This diagnostic instruments the real standalone Cell CPU Pass 3. It keeps the original neural parent issuer, exact residual verification, physical owner allocation, ordered RHS, equality queue, union-find and rebuild. The experiment asks what a selected parent already says about a future direct union. It never suppresses a reader, fabricates a source equality or closes an outstanding obligation.

## Static program and instance claim

For each explicit `Op::Union` the compiler records the template instruction ordinal and examines its two operands. It follows prior copy assignments. A direct input lists the LHS table atom and column positions from which that slot could be read. An equality literal is constant for this plan. For a prior constructor `Let`, it can instead emit the symbolic pair (this executing Cell, destination slot). A new physical constructor result in this representation can have address (Cell ID shifted left by 32) plus (slot + 1). A constructor can also return an existing result, so this is an optional *prediction* subject to checking. Computed primitives and opaque local values yield no guessed address.

After the learned provider seals its physical parents for a rule occurrence, but before it checks any parent or suffix, the observer joins those static descriptors only to the **already supplied** parent references. It reads the named row's version, visibility, table and field. It cannot search another row, consult the completed RHS, walk neighbors or use an address known only to the exact suffix. The root serial, rule/template, operation and ordered operand roles are the link. At ordinary source commit the compiler can additionally project verified RHS input slots. This later reference helps quantify how much information an issuer missed but is never included in the earlier gate's inputs.

Each candidate site may nominate one representative that it expects the union to displace. A parent-only control takes the larger current canonical value if both are available, or the supplied side otherwise. The static extended predictor preferentially names a symbolic local constructor result, or the larger local slot when both sides are local. Two equal concrete operands have no proposal budget because established equivalence is monotonic. At the actual RHS the enqueue record binds the hint to the *actual* Cell ID, template operation and originating neural root serial. At the beginning of `Graph::union`, before insertion of a parent or traversal of `uses`, both real source operands are resolved by native union-find. A valid nominated side must agree with that same source operand and with the actual displaced canonical representative. A local hint that denotes the wrong result fails. The original union still happens, independently of any hint.

## Denominators and causal limits

Every pair that enters the native equality queue has an origin. Explicit RHS Union, a writer setting an existing constructor, a constructor collision discovered in repair, and optional specialized routes are distinct. A second observation checks exact enqueue/dequeue order, nontrivial versus already-equal pairs, and the ordered digest of displaced/surviving IDs against the independent default CPU source. A pre-walk reader-count observation is checked against the size of the native displaced membership after it is removed. The work weight counts affected reader memberships at this union. The issuer neither receives their addresses nor proves that a supplied reader page is complete. A correct loser hint alone saves **zero demonstrated reverse visits** in this diagnostic.

The all-sites record stores all projected values for counterfactual analysis. The budgeted controls separately decide which optional hints to offer **during neural issuance**. Each immutable occurrence gets ceil(one quarter of admissible site offers). Uniform and static controls share the same deterministic tie rule and static side choice. The two learned controls produce a score for each possible operand side and choose the highest-ranked instance hints inside the same budget. Twelve causal features encode the presence of each direct word, observed equality and direction, any current-epoch parent, log-binned query size/instruction index/parent width/site count, whether both operands came from the same selected parent, and the two local-result flags. Numeric physical addresses, rule IDs, reverse reader information, future canonical representatives and source outcomes are excluded from learned features. The native actor loads 26 scalar coefficients fitted on grouped real source opportunities by CPU PyTorch ridge regression. Its targets are either one verified displaced root or its actual affected-reader count. Training uses sum-bits, dot-product and Jacobi. Conjugate-gradient and 3mm use frozen policies. These sources share the eggcc rule program. This tests workload transfer and no generalization to unknown rule interfaces is inferred.

## Native pre-walk census

The compiler found 48 source rule templates with one explicit union, two with two unions, and 532 without such an instruction. These 52 planned sites describe possible direct RHS operations. They do not describe unions discovered by key collision or constructor assignment. Numerical coverage compares a specific predicted losing class against the actual operands and direction before the original reverse-reader loop. The available-side ceiling gives credit if either available side could have named the displaced class, without charging for an ideal side choice.

| Source | All effective | Explicit RHS | Constructor set | Constructor collision | Displaced root from parent words alone | Complete validated pair, with local slots | Available-side ceiling, roots / reader memberships | All reader memberships |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 1,039 | 353 | 173 | 513 | 100 | 137 | 285 / 416 | 2,441 |
| dot-product | 611 | 155 | 186 | 270 | 10 | 55 | 139 / 149 | 1,440 |
| jacobi-1d | 5,258 | 1,496 | 866 | 2,896 | 481 | 675 | 1,222 / 1,914 | 12,199 |
| conjugate-gradient | 13,693 | 3,587 | 1,686 | 8,420 | 75 | 729 | 2,397 / 2,565 | 31,916 |
| 3mm | 28,142 | 7,616 | 3,928 | 16,598 | 231 | 1,471 | 5,071 / 5,421 | 65,816 |

Only 231 complete 3mm ordered pairs are available on the already sealed parents. At later ordered source commit, verified RHS input slots supply both endpoints for 2,412 effective unions. The diagnostic makes this distinction by comparing each selector against the source frame at its actual time of availability. [All donor ledgers and static descriptors](donors.json) · [Source, feature and per-site holdout ledgers](heldout.json)

## Which tags are worth offering?

Within each active rule occurrence, uniform, static, learned hit and learned reader-return rankings obtained the same aggregate outcome on both held-out programs. On CG each sent 5,540 tags, verified 610 losing roots and covered 668 memberships. On 3mm the totals were 15,839, 1,323 and 1,457. The per-occurrence ceiling prevents reallocating unused budget to a different rule. Equal aggregate counts alone do not prove identical individual choices.

A separate live native deployment ranks all occurrences against thresholds fixed using only donor offers. Scores are quantized to millionths, then a deterministic hash of the issued serial and operation resolves threshold ties. Thresholds calibrated to an expected quarter of admissible donor offers may spend a different fraction on a new program. In addition to the uniform and neural controls, local-first prioritizes possible local constructor results; the small Bake table ranks each rule/operation by its donor success count smoothed with eight offers of global prior mass. The table makes the same static side choice as local-first. All comparisons charge one offered tag per selected site. The observer still records counterfactual numerators and rechecks *all* source events.

| Holdout | Native pre-issue priority | Hints selected | Correct losing roots | Associated reader memberships |
|---|---|---:|---:|---:|
| conjugate-gradient | uniform | 5,479 | 572 | 620 |
| conjugate-gradient | local-first | 3,930 | 1,998 | 2,073 |
| conjugate-gradient | baked-hits | 3,266 | 2,370 | 2,508 |
| conjugate-gradient | learned-hits | 3,606 | 2,322 | 2,408 |
| conjugate-gradient | learned-readers | 3,602 | 2,320 | 2,404 |
| 3mm | uniform | 15,591 | 1,320 | 1,408 |
| 3mm | local-first | 9,063 | 4,157 | 4,252 |
| 3mm | baked-hits | 7,280 | 4,987 | 5,248 |
| 3mm | learned-hits | 7,726 | 4,838 | 4,946 |
| 3mm | learned-readers | 7,639 | 4,838 | 4,946 |

The learned gate improves on uniform and local-first under the donor-frozen cross-rule cutoff, while the smoothed table achieves more correct roots and reader memberships with fewer offered tags on both holdouts. It exploits the same rule vocabulary recurring across programs. No neural advantage over this Bake baseline is established. These are measurements of actual candidate choices and their source-validated labels. The separate expected-threshold calculation in thresholds.json averages random ties and is not used to claim a live result. [Global runs](global.json) · [Frozen native settings](frozen.json) · [PyTorch fit](train.py)

## Recover one missing port through a compiler-proved function request

Rule 143 matches Get(expr,i) and unites the results of Single(Get(expr,i)) and SubTuple(expr,i,1). Template 143's operands at operation 3 are local constructor slots 4 and 5. At 3mm source ordinal 18,310, Run 822, these resolve on physical Cell 18,438 to 79,190,607,003,653 and 79,190,607,003,654. The latter class was actually displaced. This rule accounts for 4,732 effective unions but only 4,732 displaced reader memberships. The static local-side heuristic nominates the correct root in 4,730 cases.

Rule 317 has a different information boundary. Its LHS contains an outer and an inner AddContext with the same context, and the RHS unites their outputs. The single independent parent supplied by the neural issuer is the inner AddContext. Its output directly provides one side. The missing outer value is uniquely determined by the complete key (context from the inner row, inner result). The direct/model+local-slot path identifies **zero of 1,957** actual displaced classes for this site although its source unions reach 8,387 reader memberships.

The bounded point treatment is an optional typed computation request. If a union operand is a table result, all key fields must come from already named parent words or literals. It admits up to four Eq/i64 input keys and performs at most one complete point lookup per missing operand, sharing repeated identical target atoms within that root. There is no rule number, source program name, oracle choice or general join in request extraction. The neural model supplies the original independent sources. The compiler defines the request and Rust resolves it. Each returned word retains the full key, table atom/column, physical row, version and Eq result. Before an effective union's reader traversal, Rust resubmits that exact key and checks visibility, physical source identity, version and the current canonical result. A stale request cannot support a positive location. The original LHS verifier and actual equality still execute.

On 3mm source ordinal 225,752, Run 2,887, the independent source is fact (Cell 227,171, op 1), atom 1, column 2, version 2,885. It supplies 975,692,015,599,623, which survives. The issued request's key is (554,050,781,199, 975,692,015,599,623). The returned atom 0, column 2 is fact (Cell 227,254, op 1), version 2,886. It supplies the actual losing value 976,048,497,885,191. The original walk then visits four readers. This is an instance-level checked source, and it remains a *compiler/Rust* discovery.

| 3mm, full admission | Parent words + local slots | Also allow one point result |
|---|---:|---:|
| Admissible tags emitted | 61,913 | 33,247 |
| Complete currently valid ordered pairs | 1,471 | 3,652 |
| Correctly nominated losers / all 28,142 effects | 5,069 | 7,250 |
| Associated memberships / all 65,816 | 5,419 | 15,572 |
| Rule 317 correct / 1,957 | 0 | 1,957 |
| Rule 317 associated memberships / 8,387 | 0 | 8,387 |
| Complete diagnostic inference, median ms | 1,924.36 | 1,965.05 |

Of 38,696 additional original Rust point requests, 30,847 returned an Eq result. The native pre-walk check performed 2,181 complete-key revalidations and found no stale receipts in this source. Rule 317 itself paid 23,336 issuance reads, 18,604 returns and 1,957 physical rechecks. The added aggregate issuer interval (including attempted key construction) was 6.52 ms median in four compact timed passes. In the separate detailed source run the aggregate request interval was 6.69 ms and the pre-walk revalidation interval was 12.43 ms; for rule 317 the corresponding times were 4.54 and 11.62 ms. More already-equal pairs can be seen before issuance in the request arm, reducing its admissible tag count. The additional word did not skip native verification or reverse-reader enumeration and did not provide a speedup. The resulting 7,250 nominations cover 95.2% of the explicit effects but 25.8% of *all* effective unions. The much larger repair-collision population needs a different certificate interface. [Point costs, per-site outcomes and four timing samples](point.json)

The independent synthetic source has two explicit union positions in one three-port template. After two direct equalities, two constructor collisions and one constructor-set equality also commit. All five committed pairs, the full source graph and physical Cell identities are checked against a default exact run. The compiled constructor-set route demonstrates why source syntax alone is insufficient for attribution. Deliberately forging the proposal IDs validates zero loser hints. It cannot alter any graph state. [Source](source.egg) · [Native negative and positive controls](fixture.json)

## Reproduction

The first native artifact captured occurrence budgets, the second added donor-threshold dispatch and the final point treatment adds the timed physical point recheck. Their checked reference source streams agree. The current source can run all three groups. [Frozen build/source identities](build-manifest.json)

```sh
d=benchmarks/pass3-cell-gpu/issuer-union-position
python "$d/build.py" "$EXP/issuer-position"
python "$d/study.py" "$EXP" "$EXP/issuer-position/session" "$EXP/position-donors"
python "$d/train.py" "$EXP/position-donors/results.json" "$EXP/position-donors/model.json"
python "$d/study.py" "$EXP" "$EXP/issuer-position/session" "$EXP/position-occurrences" --cases conjugate-gradient 3mm --policy "$EXP/position-donors/model.json"
python "$d/freeze.py" "$EXP/position-donors/results.json" "$EXP/position-donors/model.json" "$EXP/position-donors/frozen.json"
python "$d/study.py" "$EXP" "$EXP/issuer-position/session" "$EXP/position-global" --cases conjugate-gradient 3mm --global-policy "$EXP/position-donors/frozen.json" --omit static baked-readers
python "$d/study.py" "$EXP" "$EXP/issuer-position/session" "$EXP/position-point" --cases 3mm --point-control
python "$d/fixture.py" "$EXP" "$EXP/issuer-position/session" "$EXP/position-fixture"
python "$d/verify.py"
```
