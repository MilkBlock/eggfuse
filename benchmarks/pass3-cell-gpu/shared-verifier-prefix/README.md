# Reusing a verified LHS prefix across independent neural tickets

The single-parent generator commits to a rule and a physical source address before verification. Sibling rules can have different slot numbers, result predicates and RHS effects while performing an identical initial check. This experiment identifies shared prefixes at setup and lets the verifier reuse the partial result on the composed Cell CPU path. Each rule retains its own proposed token, source watermark, complete remaining LHS, committed root and physical Cell allocation.

## Compilation and reuse

The compiler normalizes slot names in their first-appearance order across the pivot atom and up to one initial complete-key or pure scalar step. The table and primitive identities, argument order, repeated operands, literal values, primitive result sort and equality constraints all participate in this comparison. It first groups prefixes of depth one that occur in at least two single-parent rules, then groups leftover rules by their pivot alone. The unsupported primitive and literal cases remain on the unshared source path. A register map restores the normalized values to the receiving rule's own slot coordinates. The first suffix witness returns to its original atom position. Rule guards after the shared prefix, RHS admission and the final seminaive epoch check remain local to each consumer.

Each family lazily allocates 512 direct-mapped slots. A hit requires the physical dependency, issued row version, current pivot table generation, current first suffix table generation when relevant and committed union generation. Positive partial receipts hold bound values, the first step's source dependency when it has one, and the greatest observed row epoch. Negative entries record prefix failure. Only a sealed token can request either. An invalid or displaced receipt uses the original verifier. On detailed runs, a separate fresh register file reruns the source prefix for every hit and checks the returned values, source witness and epoch. The independently executed default CPU pass supplies the final source oracle.

The anchor arm shares the pivot alone. Prefix shares the pivot and first instruction wherever a common full prefix occurs. Sibling disables reuse by the writing rule. Negative stores only failed prefixes. Live stores the union of slots required by all consuming tails and RHSs in a family. All tail inputs and outputs count, since a previously bound tail result is an equality constraint. Remaining prefix fields can be released once the prefix has been verified. None of these arms changes model weights or the set of issued proposals.

## Reproduction

Use fresh experiment directories on the external volume. The default comparison runs sum-bits and 3mm at seed 1703. The resident inference measurements rotate four observed repeats after warmup and include issuance, verification, updates and source-ordered effects. The later phase run uses the built-in instrumentation to time single-parent verification plus winner assembly separately.

```sh
d=benchmarks/pass3-cell-gpu/shared-verifier-prefix
python "$d/build.py" "$EXP/shared-prefix-build"
python "$d/study.py" "$EXP" "$EXP/shared-prefix-build/session" "$EXP/shared-prefix-study"
python "$d/study.py" "$EXP" "$EXP/shared-prefix-build/session" "$EXP/shared-prefix-phases" --profile --repeats 3
python "$d/verify.py"
```

## Complete source execution

| Program | Default CPU | Composed off | Shared anchor | Shared prefix | Sibling only | Negative only | Live slots, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 23.13 | 34.21 | 32.97 | 33.56 | 34.14 | 35.20 | 34.73 |
| 3mm | 903.74 | 1,921.60 | 1,980.04 | 1,931.94 | 1,951.58 | 1,988.02 | 1,957.32 |

On both programs the compiler admitted 177 source rules. In the depth-one arm five rules share their first operation, and 172 share only their pivot's checked binding. The resulting 42 families have 670 normalized register positions across rules. All 670 remain live under the source input and suffix contract. The live arm and the full prefix arm performed identical slot operations. Differences in their timings measure run-to-run variation for the same work.

On 3mm the prefix arm reused 193,015 partial proofs. Another rule had written 42,768 of them. It restored 620,942 slot values, encountered 526,465 direct-map address collisions and saved seven exact suffix point reads. The largest actual sibling pair was rule 102 → rule 151 (6,399 hits). Both consume the same four-column Bop parent; rule 102 asks about operator/operand purity whereas rule 151 reads child Expr-size values and adds them. These rules can share the checked parent. Their suffix requests have different semantics. The sibling-only arm saved no suffix point reads on this program. Sum-bits had 2,909 hits including 2,503 from another rule, and saved 54 point reads. Each arm matched the source RHS, effective writes, Spine, unions, schedule, final graph, neural decision digests, all root parent identities and actual Cell allocations. [Per-rule observations and paired samples](results.json)
