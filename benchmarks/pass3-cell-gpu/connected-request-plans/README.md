# Function requests between learned parent selections

In a three-parent offer for rule 507, the old generator picks a TCPair, an ExtractedExpr and a CellSpineView8. At the compiler interface those atoms read `TCPair(s0,s1,s2)`, `ExtractedExpr(s3,s2)` and `CellSpineView8(s6,s3,s7,s8,s4,s9)`. Once the first proposed parent is the CellSpineView8, its slot s3 is the complete key of the function ExtractedExpr. The request evaluator returns that row and its s2. The trained tied projection of s2 selects a bucket of TCPair parents. Exact verification checks the original LHS, including the residual s4 < s1. The ordered RHS and the root's published coordinate system stay the same.

## Which plans admit this representation?

For each source rule, the offline compiler computes the closure of known slots under forward primitives and complete function or constructor keys. It searches these closures in breadth-first order. A new independent parent must have a slot in common with the closure after the preceding selection. The first parent can introduce an unbound component. For a connected solution, the lowering reconstructs which deterministic requests supply a connecting slot; obligations that can wait are placed after the last parent. Every source atom occurs exactly once. Constants, shared input slots and repeated result slots remain available to validate the binding. A missing key or failed primitive can invalidate a candidate at execution. The source plan alone cannot predict the success or cost of a request.

The six real Pass 3 sources share this 582-rule program family. Among 341 original multi-parent plans, 107 use more independent picks than the unconstrained functional-dependency lower bound. Allowing a connected request reduces the width of 64 plans; 55 of those reach that lower bound. The other nine still require extra picks under this connectivity constraint. The original execution profile of the 64 reachable plan shapes accounts for 17,495 previously issued tuples and 699,606 root visits on 3mm, 44,331 tuples and 1,238,235 root visits on Deriche. A count of visits by a rule marks where the representation could apply. It does not establish how many visits can disappear. [Reproducible census](census.json)

## Executable subset

The native study tests a restricted family with two independent picks and one complete-key request. The three atoms must exactly cover the original independent triple. The middle request must have unique physical function-table storage. A constructor that might have multiple physical witnesses keeps its original issuer. The original source is the authority on membership, typed input values, watermark and source-order publication. The two-parent rule is still selected using the same tied neural port tables. One of the previous three independent addresses now comes from the deterministic function request. We retain that address in the original three-address receipt, so this experiment charges verifier work and measures changed generation. A physical Cell from such a receipt is attributed to the joint recipe, including its deterministic address.

An optional invocation-local directory memoizes up to 4,096 complete keys, including missing results. All reads in that invocation share the same immutable graph snapshot. The implementation restores original parent order before sealing. A buffer over 32,768 triples abandons the tentative traversal before issuance and runs the original learned proposer. An explicitly finite source budget also keeps the original proposer and its exhaustion semantics. Tests compare the actual winning parents and new physical Cell IDs as well as source Run, union, effective writes, Spine and final graph.

## Resident execution on the original four programs

At frozen seed 1703 the driver rotated four measured samples after a warmup. All arms ran the same complete standalone Cell CPU workload including verification and ordered execution. Vanilla was measured using a separate default EggFuse CPU binary.

| Program | Vanilla | Joint CPU off | Direct request | Memoized, ms | Function reads direct → memoized | Triples sealed by the new path | Full multi-parent proposals off → direct |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.59 | 34.52 | 33.12 | 34.19 | 12,090 → 7,126 | 560 | 5,912 → 5,918 |
| conjugate-gradient | 334.23 | 609.76 | 625.26 | 627.57 | 182,687 → 109,586 | 4,293 | 83,313 → 83,320 |
| 3mm | 898.34 | 1,866.79 | 1,929.50 | 1,977.44 | 613,362 → 352,910 | 12,365 | 220,972 → 220,962 |
| deriche | 1,546.44 | 3,510.88 | 3,583.64 | 3,573.27 | 1,106,732 → 594,550 | 35,486 | 309,277 → 309,270 |

Across each of these executions the independent default CPU reference agrees on all source Run events and final graph. Off and both request arms agree on the winning source parents and directly allocated Cell IDs. The loose equality bucket can admit additional false candidates; some original false candidates disappear when the intermediate key is read exactly. The new route still checks the same three source witnesses. On 3mm, merely moving the function request before a learned choice trades one independent selection per new-path triple for hundreds of thousands of point evaluations. Local memoization does not remove the cost of probing for nearly every possible root. [Results and activity by source rule](results.json)

## Share the function's visible port directory

The final control builds a complete map for one immutable single-key function table from its existing source frame. It maps an Eq or i64 key to the physical row offset and the learned output signature. A generation or union change invalidates the directory. One table of up to 16,384 entries is retained, and an unsupported key layout or nonunique key retains the direct evaluator. Each decision was independently compared to the original graph lookup in a separate audited execution. With either representation the last parent is still selected by the neural projection.

| Program | Vanilla | Joint CPU off | Direct request | Per-invocation memo | Shared directory, ms | Native point requests → directory reads | Directory rows built |
|---|---:|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 343.74 | 633.04 | 632.53 | 636.73 | 650.92 | 182,687 → 182,687 | 48,828 |
| 3mm | 887.68 | 1,918.22 | 1,920.55 | 1,929.78 | 1,932.20 | 613,362 → 613,362 | 178,749 |

Direct runtime graph requests fell to zero in the directory arm. On 3mm it performed the same 613,362 logical reads, including 158,544 missing keys; all sealed proposals matched direct evaluation. This explains why the initial source population matters even when the request itself resolves to a narrow record. The paired measurements give no reason to enable eager connected requests on all eligible roots. [Independent paired comparison](directory.json)

```sh
d=benchmarks/pass3-cell-gpu/connected-request-plans
python "$d/census.py" "$EXP/compact-holdouts-20261121-v1/sum-bits-1703" benchmarks/pass3-cell-gpu/pair-source-frontier/profile.json "$EXP/census.json"
python "$d/build.py" "$EXP/bridge-build"
python "$d/study.py" "$EXP" "$EXP/bridge-build/session" "$EXP/bridge-study"
python "$d/study.py" "$EXP" "$EXP/bridge-build/session" "$EXP/bridge-directory" --cases conjugate-gradient 3mm --directory
python "$d/verify.py"
```
