# Offline opportunities for a single producer to supply every named input of a later rule

**Status: retrospective wiring evidence on four actual Pass 3 traces.** The native computation used the ordinary filtered, packed, explicitly addressed root issuer. Each child still had its independent original token. This audit did not add an instruction, suppress a packet, change latency, or measure an improvement in explicit-parent FEPT.

The unit counted is a unique committed child serial. Both producer and child must already name every table atom in their original LHS by its typed physical address and visible version. Primitive predicates may still require deterministic checking. A child's ordered table premises must each be one of the same producer's literally named input atoms, or a strictly new constructor fact resulting from its own typed RHS operation. At least one premise must use a new output. We check the output's actual first-activation event, table, birth epoch, producer serial and source template/op; dynamic, nested merge and previously interned results receive no new-output credit. Multiple possible owners or source-port mappings are declined. Names, e-class proximity and logical key similarity cannot establish identity.

Only distinct original source Runs are linked, with a verified producer commit strictly earlier than the consumer in both Run and execution ordinal. A changed physical version disqualifies a carried slot. Queries with unprovided LHS table atoms are excluded even when a unique ordinary lookup could supply them. Graph repair, effective writes, every original RHS, union, Spine and schedule are checked independently; the ordered entire native birth-event list also matches the independent source-mode execution. Later retained membership of a newly born constructor is checked against its original fact identity.

## What the ordinary traces contain

| Program | Committed roots | All table parents already named | Eligible child commits | Unary | Multiple atom positions, one physical ref | Multiple distinct physical refs | Three-member terminal children |
|---|---:|---:|---:|---:|---:|---:|---:|
| dot-product | 6,704 | 4,288 | 1,107 | 792 | 136 | 179 | 295 |
| jacobi-1d | 41,319 | 25,581 | 4,631 | 3,411 | 504 | 716 | 1,347 |
| sum-bits | 7,265 | 5,228 | 973 | 652 | 140 | 181 | 207 |
| 3mm | 294,917 | 160,694 | 25,487 | 20,184 | 2,158 | 3,145 | 9,028 |

On 3mm the multi-atom census excludes 134,222 children with unprovided table atoms, 113,765 with another uncovered input, 3,881 with only stale birth versions, 3,354 for which the candidate producer itself had an unprovided table atom, and 2,527 with uncovered or changed-version premises. A successful physical match still needs the existing release-time guards and a way to suppress the independent external child without losing alternatives. The union of all honest new births is deliberately incomplete for constructor operations that returned an existing interned fact. The trace does not generally identify the returning operation/owner of every such existing receipt; counting those by key would violate this contract. [Full census, examples and source identities](results.json)

## Freeze shapes on dot-product and jacobi-1d

A pair shape is identified by both typed rule definitions, the offset in original Runs and the complete ordered mapping of child atom to named producer input or typed output operation. IDs contain no graph address. A triple is a pair of such edges whose intermediate is the same committed serial. Pair and triple counts are separate, with no sum across overlapping chains or siblings. Exact Run offsets are intentionally retained.

| Donor selection | Shapes | sum-bits held-out children | 3mm held-out children |
|---|---:|---:|---:|
| Pairs seen at least twice across donors | 60 | 522 | 15,537 |
| Of those, multiple distinct physical parents | — | 83 | 1,685 |
| Of those, excluding named CellSpineView completion consumers | — | 20 | 445 |
| Pairs seen in both donors | 18 | 453 | 14,376 |
| Of those, non-CellSpineView consumers with multiple distinct physical parents | — | 0 | 330 |
| Connected triples seen at least twice across donors | 28 | 102 | 4,227 |

All held-out occurrences of the repeated triple shapes had unary middle and terminal interfaces. The unmatched traces did contain physically multi-input terminal rules in three-member chains: three on sum-bits and 18 on 3mm. In all eligible pairs before donor selection, explicitly named `complete-CellSpineView…` consumers contributed 154 of 181 physically multi-input opportunities on sum-bits and 2,503 of 3,145 on 3mm. This label describes a generated maintenance rule and does not imply a corresponding new user-program constructor. [Frozen mappings and counts](catalog.json) · [Transfer by category](transfer.json) · [Complete shape-frequency archive](shape-counts.json)

## A five-input transition

On 3mm, rule 249 committed root serial 87,125 at Run 839. At Run 843, serial 98,777 committed the same rule using its producer's DoWhile, two distinct ContextOf witnesses and HasArgType in atom positions 0, 1, 2 and 4, with unchanged physical versions. Its atom 3 used the producer's new Const output from RHS op 2: FactRef `181123065839618` at version 839. The original commit and birth event establish this reference and its source rule. The same +4-Run mapping appears 12 times on dot-product and 62 times on jacobi-1d, then 330 times on 3mm and zero times on sum-bits.

Another recurrent two-reference map uses both freshly produced outputs of rule 501: op 6 PotentialExtractedExpr feeds atom 0 of rule 286, and op 5 TCPair feeds atom 1 one Run later. Counts were 26 and 174 on the donors and 29 and 928 on the holdouts. Its destination is the generated CellSpineView8 completion. A recurrent unary chain, 55→143→137, advances four original Runs on each edge and occurs 37 / 247 times in donors, 30 / 591 times in holdouts.

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/strict-composition-opportunities
# Reuse the pinned native token-constructor-births v2 session, or build that experiment.
python "$d/audit.py" "$EXP" "$EXP/token-constructor-build-v2/session" "$EXP/new-strict-opportunities"
python "$d/report.py" "$EXP" "$EXP/new-strict-opportunities" "$d"
python "$d/verify.py"
```
