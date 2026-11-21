# Filtered Pass 3 with preselected, named-parent static Cell templates

The model supplies exactly the independent parent identities and versions. At issuance the existing template field commits to a static variant of the producer rule, whose internal edge identifies a particular typed constructor instruction. A child in this bounded grammar has exactly one constructor atom, distinct slots, and no other relation parent. Publication records a fresh actual returned FactRef for that operation. At the original child Run, the verifier checks those specific sources and can establish that their live members exhaust the child relation by comparing against its authoritative physical cardinality. It does not obtain a list of other potential parents. Missed interned outputs, ambiguous coverage or changed references leave the ordinary explicit path active. Reuse of an existing constructor is not credited as another birth or speculatively registered from its template's nominal owner.

On a successful internal release, the normal path does not open the ordinary child candidate bank, rank a child address, issue a child root packet or evaluate that child's neural logits. It performs the scheduled source commit. A separate audit is permitted to recompute the ordinary result as an independent oracle. No range/class/bucket descriptor participates. The model choosing root instances is unchanged. Bake selects the signed program variant for each eligible producer rule before it executes. This is an experiment in the expressiveness and transfer of a static template library; the root selector itself was not retrained.

We crossed the native named-parent implementation with the existing exact scalar negative filter. The leaf mode therefore reproduces the published explicit-parent baseline used in the FEPT contract. The same independent root references, zero-yield packets and selected nested child charges apply throughout.

| Program | Leaf FEPT (packets) | All one-edge variants | All up to two edges | Frozen donor library, 1 / 2 edges |
|---|---:|---:|---:|---:|
| sum-bits | 0.212526 (12,662) | 0.216614 (12,423) | 0.216614 (12,423) | 0.212526 / 0.212526 |
| 3mm | 0.166032 (558,074) | 0.167064 (554,626) | 0.167064 (554,626) | 0.166032 / 0.166032 |

On sum-bits / 3mm, the two compiled comparisons each supplied 239 / 3,448 actual original RHS commits without another external child token. The second edge saved no additional external decision on these holdouts. Each FEPT numerator is fixed at 2,691 / 92,658 final visible constructor origins. Native visible state, ordered Run RHS, writes, unions, Spine, physical source parent identities, root and nested Cell IDs, birth stream and endpoint digest are preserved. Deliberately changing a designated constructor operation is rejected. Counting the table cardinality is allowed here only as a check on the already named origins. The implementation still visits previously registered exact references to check whether they are current. These visits cost time. For example, the 3mm compiled first-hop arm checked 176,990 named addresses over all attempted releases.

**Which nodes came from the newly internal work?** The separate links audit joins the actually committed internal serial to the signed external producer, native constructor ledger and final export. In 3mm, 3,448 external producers each supplied an internal commit. The external producers' original typed RHS operations contributed 7,024 final-visible nodes. The new internal commits contributed two final-visible facts from explicit typed constructor instructions and 264 from runtime dynamic constructions; these categories are separate. Among these producers 3,183 had no additional visible node from their child. In sum-bits the internal source actions contributed ten visible typed facts. A further twenty came from separately paid merge-child tokens and are excluded from the internal marginal yield. These are changes of who can account for an unchanged semantic result, not additional global graph output. The population selected for successful composition must not replace the full issued-token denominator.

**Donor transfer.** Two-round Bake selected 23 one-edge and three longer schema paths on dot-product/Jacobi. The unchanged donor library succeeded in neither held-out program. complete_library.py keeps the donor-selected *consumer schemas* and relinks every statically compatible constructor operation of the held-out compiler program before execution. The resulting 33 one-edge paths cover 141 / 3,448 actual releases. Extending to 40 paths preserved those counts. Source names and held-out traces are never used to choose which schemas to retain. Adding missing producer schemas helps some consumers pass the coverage test. It does not authorize inferring an unspecified parent or granting a new permission after seeing its future match.

**Memory.** The median time to the independently frozen +9.27 MiB sum-bits watermark was 28.27 / 26.02 / 28.54 ms for leaf / one / two compiled edges. The +264.11 MiB 3mm watermark was reached at 1,083.59 / 1,028.09 / 1,164.13 ms. Each arm has three rotated, fresh process samples and the full traces. Inference medians use separate resident runs. No performance conclusion follows from the small differences across these three RSS samples alone.

Reproduction uses fresh external directories. The filtered build and links build share the named-parent source and differ only in recording internal-to-external provenance for the links run.

```sh
python build.py "$EXP/new-filtered-named"
native="$EXP/new-filtered-named/session"
python study.py "$EXP" "$native" library.json "$EXP/new-strict-holdout"
python rss.py "$EXP" "$native" library.json "$EXP/new-strict-holdout/results.json" "$EXP/new-strict-rss"
python complete_library.py "$EXP" "$native" library.json "$EXP/new-strict-holdout/results.json" "$EXP/new-strict-complete"
python build_links.py "$EXP/new-filtered-links"
python trace_links.py "$EXP" "$EXP/new-filtered-links/session" library.json "$EXP/new-strict-holdout/results.json" "$EXP/new-strict-links"
python verify.py
```
