# Retaining settled work at the ordered repair barrier

The standalone Cell CPU executor commits each source union in order, walks the dependencies of the displaced representative in their original order, and then repairs dirty source facts and functions. The ordinary reverse index uses ordered sets. This experiment runs under the two-view neural CPU issuer with published headers and lazy arithmetic ports. It preserves the independent root selections, exact graph checks, commit order, collision winner, query versions, effective writes and Spine activation. Default exact EggFuse CPU runs in a separate process using the same source program. The changes are local to the pinned experimental Rust build.

## Union and physical key work

- **Reverse.** Leave the displaced bucket in its original order during notifications. Then retain the larger physical tree as the survivor's storage and insert members of the smaller tree into it. The surviving equality ID is still the native lower ID, independently of which allocation is larger. If a large class repeatedly absorbs singleton buckets, the original merge presents the entire growing survivor for reinsertion each time. The small-side merge presents one dependency per absorption. Both visit exactly the same displaced subscribers to make them dirty. This changes the ordinary backend's reverse bucket merge in isolation, borrowing the size comparison from sparse storage. Detailed mode enumerates and compares each merged bucket against the original ordered set union.
- **Payload.** Compile each scalar table's Eq-column positions from the declared schema (up to 64 fields). For a previously decoded visible payload, replace every occurrence of the displaced canonical representative in those columns with the new representative. A shared immutable payload is cloned before editing, so an earlier receipt retains its old version. Fact Cells' immutable slot projections and current function tuples depend on equality via canonicalization. A set requires recursive normalization and deduplication, so the normal decoder handles it. Undecoded sources also use ordinary repair. The audit re-evaluates the template fields or function storage independently after every accepted patch while the original repair worklist is still pending.
- **Key.** A surviving fact whose physical reference is already in the same intern bucket needs no erase and insertion. Actual key equality is still checked to select a possible peer, including hash collisions. On an actual retirement the original physical remove occurs once and reuses the already decoded source table. The function arm retains an unchanged key entry only after confirming its exact physical ID, with no compressed unit alternative. The source timestamps, notifications, visible payload and subscriptions remain governed by the same terminal effect.
- **Delayed fact payload.** Keep an old decoded fact's immutable fields aside when its union invalidates them. Ordinary reads before the fact's repair turn still use the native decoder. At its original position, normalize the schema's Eq columns against the current parents, compare with the ordinary instruction decode in the audit, then consume the payload. This can coalesce several unions before touching the data. Functions and sets retain ordinary invalidation; the transient store is capped at 32,768 facts and retirement removes a stored payload.

## Forward subscriptions already closed by the union

The source union moved the whole reverse use set for the displaced representative, including every dependency of the surviving repair row. For a surviving ordinary fact or noncompressed function, the canonical repair without a peer changes only how its existing fields are represented. The set of canonical roots in its prior forward subscriptions therefore equals the set of current canonical roots in the repaired fields. The source still advances its table generation and emits the original change at that exact point. A merged function value or a retiring source still goes through the original subscription updater.

**Rebase** canonicalizes the previous forward set once and reinserts no reverse edges. **Defer** keeps the preceding forward set, whose elements the original updater already resolves through the parent relation before any later edge removal. That makes the raw count of historical forward entries a separate measure from the unique live reverse edges. Both paths require a previously installed forward header. They apply to ordinary graph storage and exclude the specialized local- or stable-port union paths. The detailed run checks every adopted forward set against a fresh recursive traversal of all current fields, checks each corresponding live reverse membership and reconstructs the complete normalized reverse graph at termination.

Earlier [canonical root and compact forward list experiments](../canonical-batches/README.md) changed how a root is read or a subscription list is represented. Here the recanonicalization-only repair can reuse the reverse subscriptions themselves. The earlier [union digest](../../union-digest/README.md) provides a separate constructor congruence detector. All of this experiment's constructor collision searches and source-ordered dirty work are still exercised.


## Interleaved native results

Each row below uses the median of four rotated resident passes following warmup at seed 1703. The phase column is the native repair interval over the source Runs. It is included in the full inference interval.

| Program | Arm | Repair ms | Full inference ms |
|---|---|---:|---:|
| sum-bits | Original | 2.35 | 34.24 |
| | Smaller reverse merge | 1.97 | 33.27 |
| | Scalar payload | 2.11 | 32.89 |
| | Physical key | 2.24 | 34.63 |
| | Three changes | 1.79 | 33.14 |
| | Default exact CPU | — | 22.61 |
| 3mm | Original | 110.89 | 1,978.47 |
| | Smaller reverse merge | 79.25 | 1,934.50 |
| | Scalar payload | 104.55 | 1,987.11 |
| | Physical key | 103.23 | 1,954.45 |
| | Three changes | 71.75 | 1,894.96 |
| | Default exact CPU | — | 938.96 |

The original and combined 3mm route completed exactly 28,142 unions and 58,632 dirty dependencies. Presenting the smaller reverse bucket to insertion reduced its input from 815,544 to 65,347 entries. The payload arm applied 70,336 Eq substitutions and copied 36,550 shared immutable vectors. The key arm kept 19,533 fact buckets and 3,050 function entries in place and avoided 26,845 repeat retirement reads. Combined repair time fell 35.3%; full inference fell 4.2%, with three of four pairs faster. This comparison is for the learned Rust CPU backend, whose original and treated source bindings and physical Cell identities were audited separately. [Work counts, samples, clocks and source checks](effects.json)

A second paired matrix isolates forwarding the existing subscription proof. The first three changes are enabled together only in the structural and combined columns.

| Source | Original repair / full | Structural | Rebase alone | Defer alone | Structural + defer, ms |
|---|---:|---:|---:|---:|---:|
| conjugate-gradient | 41.48 / 661.42 | 31.76 / 654.46 | 41.60 / 666.82 | 37.94 / 659.98 | 27.71 / 636.72 |
| 3mm | 108.37 / 1,999.62 | 74.62 / 1,984.09 | 108.33 / 1,985.60 | 103.48 / 2,006.91 | 64.03 / 1,905.68 |

CG adopted 12,657 and 3mm adopted 28,728 surviving row subscriptions. On 3mm the combined treatment visited 524,441 values to maintain subscriptions, down from 618,081, and attempted 413,629 reverse insertions, down from 476,962. It retained all 321,407 live reverse edges, exactly equal to a reconstruction from the canonicalized final forward sets. Raw forward entries were 327,096 rather than 321,407 due to the deferred collapse of older identities. The corresponding CG counts were 118,914 raw and 116,168 normalized. The eager rebase avoided these additional entries. Its full-pass timings alone did not establish a benefit. Combined vs original was faster in 4/4 CG and 3/4 3mm pairs. [Source/physical ledgers and detailed counts](subscriptions.json)

A six-Run source test creates multiple Eq positions in one constructor, independent old facts that become equal and a set initially containing three different Eq values. The first union Run commits four ordered equalities including two resulting constructor retirements. The ordinary set-normalization path changes the published Size from 3 to 1 on Run 3. A later rule changes a function's old value, replacing an old subscription; a fifth union on Run 5 exercises the new subscription. Every arm preserves the ordered source, writes, Spine, final graph and physical Cell IDs, including when old forward subscriptions had been deferred. [Source](repair.egg) · [Native test](fixture.json)

On 3mm the second full-pass median fell about 94 ms whereas measured repair fell about 44 ms. Search and RHS medians also varied despite identical source work. Only the measured repair interval and its operation counts are directly attributed to this algorithm. The source stream contained 294,917 RHS and 229,311 directly attributed root/child Cell IDs among 229,880 fresh IDs in every arm.

## Delayed normalization and transfer

| Source | Exact CPU | Original repair / full | Reverse alone | Delayed fact alone | Eager structural + deferred subscription | Delayed structural + deferred subscription, ms |
|---|---:|---:|---:|---:|---:|---:|
| 3mm | 921.85 | 107.09 / 1,985.06 | 75.82 / 1,874.59 | 103.89 / 1,943.37 | 63.19 / 1,885.03 | 67.81 / 1,927.78 |
| Deriche | 1,598.29 | 170.10 / 3,543.22 | 134.24 / 3,632.61 | 167.59 / 3,555.34 | 107.86 / 3,624.65 | 107.84 / 3,470.24 |

Deriche had 46,146 unions. The smaller-side merge presented 108,622 entries instead of 1,171,446. The eager treatment applied 115,999 scalar replacements, and 37,106 fact and 10,269 function subscriptions were maintained by the earlier union. All 446,700 normalized reverse edges survived. Deferred forward storage had 456,698 raw entries. The delayed representation consumed 50,259 / 80,373 previously decoded facts on 3mm / Deriche, holding at most 1,812 / 6,903 pending at once. On Deriche the eager and delayed combined repair intervals were effectively equal despite their different complete-pass medians. Eager combined won two of four total-time pairs, delayed combined three of four. The fixed repair-phase gain transfers. Complete pass timings do not support a universally superior payload policy. [Larger programs and timings](late.json)

## Reproduction

Build with the ordinary composed CPU provider and use fresh output folders on the experiment volume. [Build identity](build-manifest.json)

```sh
d=benchmarks/pass3-cell-gpu/ordered-repair-reuse
python "$d/build.py" "$EXP/repair-build"
python "$d/study.py" "$EXP" "$EXP/repair-build/session" "$EXP/repair-primary"
python "$d/study.py" "$EXP" "$EXP/repair-build/session" "$EXP/repair-forward" --cases conjugate-gradient 3mm --arms off all rebase defer combined
python "$d/study.py" "$EXP" "$EXP/repair-build/session" "$EXP/repair-late" --cases 3mm deriche --arms off reverse delayed combined delayed-combined
python "$d/fixture.py" "$EXP" "$EXP/repair-build/session" "$EXP/repair-fixture"
python "$d/capture.py" "$EXP" "$EXP/repair-build/session" "$EXP/repair-work"
python "$d/verify.py"
```
