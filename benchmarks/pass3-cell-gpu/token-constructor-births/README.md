# Constructor e-nodes per neural packet in real Pass 3

An effective birth in this measurement is a newly published constructor e-node whose **original fact identity is visible at final export**. This is a retention criterion. A constructor merged into another witness might have enabled valuable inference before the merge. The raw birth count includes those events too. Each logical e-node has a native `FactRef` (owning Cell ID and instruction position). A Cell can publish many such facts.

The ledger records a unique identity immediately after native `Graph::activate` has inserted the fact, registered its membership and incremented `logical_facts_created`. It requires the compiled table kind to be `constructor`, excluding function writes and Unit relation inserts. An intern hit, rebuild scan or union creates no record. We group the synchronous RHS work under the actual consumed neural root recipe's global serial. Births within `dynamic_construct` are counted separately. Every other attributed birth is checked against the exact constructor effect in the compiled rule at that fact's instruction position, and against the actual root allocation for that serial. Initialization facts already present before inference, and new constructors outside every committed RHS, have separate totals.

Two engine executions establish the accounting. Ordinary source execution and the packed neural execution must emit the same ordered constructor/relation birth events, source RHS ordinals, stable identities, collision loser→keeper records, and final original witnesses and visibility. The independent compact plain CPU then supplies the complete per-Run RHS, effective writes, unions, Spine and final graph comparison. The root/child identity checks use the issued proofs and actual child allocation ledger. The audit instruments a standalone native Cell CPU engine on full eggcc programs. It does not time new inference code.

The denominator called **issued roots** counts emitted singleton and multi-parent root proposals after the scalar negative filter. **Committed roots** counts unique successfully consumed root serials. The broad actionable-packet denominator also includes selected merge-child packets, including their intern hits or verification failures. The broader decision-only alternative includes every child candidate, including declines. In the exclusive packet distribution, a successful fresh nested child receives its own birth and the root loses the matching credit. This preserves the numerator when switching denominators.

After inference, the sampler enumerates constructor witnesses through the export iterator and records their hidden bits. Visible original witnesses, hidden originals and matching repair-displacement chains are separate. Multiple retired origins can forward to one final fact. Every displaced witness remains retired under the original-identity criterion. The lineage view separately reassigns each attributable birth once to the neural producer of the original Spine context. Later descendants execute and validate their own tokens on their own Runs. That retrospective view measures lineage influence.

## Results

The numerator in the last three columns is independently verified final-visible original constructor identities born during an attributed RHS.

| Pass 3 | All owned births | Final visible originals | Committed roots | Issued roots | Selected children | Visible / committed root | Visible / issued root | Visible / issued root + selected child |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 3,610 | 2,691 | 7,265 | 12,471 | 191 | 0.3704 | 0.2158 | 0.2125 |
| dot-product | 3,035 | 2,689 | 6,704 | 14,003 | 210 | 0.4011 | 0.1920 | 0.1892 |
| conjugate-gradient | 48,711 | 34,595 | 131,371 | 216,878 | 1,088 | 0.2633 | 0.1595 | 0.1587 |
| 3mm | 119,503 | 92,658 | 294,917 | 555,566 | 2,508 | 0.3142 | 0.1668 | 0.1660 |
| deriche | 165,147 | 120,436 | 635,818 | 976,311 | 3,933 | 0.1894 | 0.1234 | 0.1229 |

| Pass 3 | Committed roots with 0 / 1 / 2+ final-visible births | Raw maximum | Final-visible maximum | Raw / final-visible maximum excluding initialization |
| --- | ---: | ---: | ---: | ---: |
| sum-bits | 5,222 / 1,657 / 386 | 88 | 84 | 7 / 5 |
| dot-product | 4,718 / 1,628 / 358 | 176 | 171 | 3 / 3 |
| conjugate-gradient | 103,694 / 23,249 / 4,428 | 1,697 | 1,528 | 6 / 6 |
| 3mm | 219,883 / 63,376 / 11,658 | 3,249 | 3,085 | 3 / 3 |
| deriche | 539,906 / 80,687 / 15,225 | 3,272 | 3,006 | 7 / 5 |

In all five workloads the largest immediate contributor is the single initialization match at epoch 1. On sum-bits its 220-instruction RHS publishes 88 constructors, 84 of whose original identities remain visible. On 3mm its 6,709-instruction RHS publishes 3,249 constructors, with 3,085 original identities still visible. Every birth in these two maxima matches an explicit compiled RHS constructor effect in the corresponding root Cell. The post-initialization maxima in the table describe these programs only.

On sum-bits that root's Spine lineage also contains 285 constructor births made by 252 different descendant tokens across a total of 14 Runs. On 3mm it contains 11,956 additional births made by 10,989 descendants across a total of 32 Runs. Treating those 373 or 15,205 births as the direct output of one token would double-charge work performed by later committed roots.

For 3mm, 26,845 of the 119,503 originally attributed identities were displaced on a duplicate repair path ending in a different visible witness. There were also 28 previously uncounted `Smaller` constructors outside any neural RHS, and 128 constructors already present before inference. The 1,216 fresh selected nested children form a subset of the 1,757 dynamically constructed nodes inside a root RHS. Child issuance also produced 1,292 reuse hits. The exclusive packet distribution credits a fresh child once.

[Five complete histograms, attribution checks and representative roots](results.json)

## Reproduction

```sh
exp=/Volumes/EggFuseWorkspace/experiments
python3 build.py "$exp/token-birth-build"
python3 study.py "$exp" "$exp/token-birth-build/session" "$exp/token-birth-audit"
python3 verify.py
```
