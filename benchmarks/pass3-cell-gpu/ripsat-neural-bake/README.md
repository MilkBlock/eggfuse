# RipSat in the named-parent neural Bake path

Two real donors (dot-product and jacobi-1d) provide native RipSat histories. The default compiler checks the native fixed point, reconstructs the signed source port, finds the exact produced token in a later native read, checks the original donor physical occurrence, and relinks to the exact target rule/effect/pivot. The output is a static template program. The existing network still chooses the individual physical parent. We tested the *final* authenticated evidence, identical in the portable and native-file forms. The manifest pins the actual target, native binary, evidence, independent trust index and consumer library. The normal neural Bake entrypoint can publish a target library or revalidate it from its original inputs before loading.

## Four matched source executions

All arms used the same filtered native Cell CPU session and original schedule. Roots explicitly name every independent parent; no range or class packet is used. Composite arms enable strict partial release: already signed physical return ports supply only their own child inputs. Other external proposals stay charged. Four rotated resident inference samples follow warmup. Their source audit was independent. Timing excludes offline Bake, verification of the portable library, program setup and final export.

| Program / library | External packets | Actual source commits supplied internally | Strict FEPT | Inference median ms | Time to common incremental RSS ms |
|---|---:|---:|---:|---:|---:|
| sum-bits / Leaf | 12,662 | 0 | 0.212526 | 35.86 | 27.93 |
| sum-bits / Trace Bake | 12,595 | 67 | 0.213656 | 34.33 | 28.45 |
| sum-bits / RipSat | 12,627 | 35 | 0.213115 | 36.30 | 27.13 |
| sum-bits / Trace + RipSat | 12,560 | 102 | 0.214252 | 34.78 | 29.38 |
| 3mm / Leaf | 558,074 | 0 | 0.166032 | 1,835.63 | 1,034.54 |
| 3mm / Trace Bake | 556,500 | 1,574 | 0.166501 | 1,828.16 | 1,039.34 |
| 3mm / RipSat | 556,845 | 1,229 | 0.166398 | 1,799.55 | 995.92 |
| 3mm / Trace + RipSat | 555,271 | 2,803 | 0.166870 | 1,914.85 | 1,063.15 |

Independent exact CPU execution agrees on all 1,428 sum-bits and 4,260 3mm Runs: ordered RHS inputs and effective writes, Spine resumes, unions, schedule and final graph. Across library arms the model's singleton decision digest, winning root/child physical identities, birth count and final visible origin count agree as well. FEPT charges all external single/multi proposals plus every independently selected child. The final-visible numerator is 2,691 on sum-bits, 92,658 on 3mm.

The default RipSat library admits one native-linked edge: rule 143 operation 1 returns Single, rule 55 consumes that specific Single. This edge occurs in neither target's transferred trace library (19 and 18 paths respectively). In 3mm, for example, the root in Run 822 names cell 129/op 44 version 1. Its actual returned port is cell 18,438/op 1 version 822. The original Run 826 consumes that port. The verifier checks the named graph row and source version with no independent selection of a partner. The residual issuer can still traverse its own remaining input. In the default RipSat arm the 35 / 1,229 removed child packets produced 35 / 1,229 new typed constructor facts, of which **6 / 139** kept their original identities at final export. These are contributions from the internal steps at constant total graph output.

The union does more than just contain the additional schema. The independent set of actual source RHS ordinals supplied internally by trace is disjoint from that supplied by RipSat on both workloads. In the union run its set is exactly their union: 102 and 2,803. Archived results include each set and positive examples. The optional producer-return-only diagnostic (a native producer and statically valid later consumer without a local effective read) is kept separate; on these targets it supplied zero internal commits and is not in the four-arm default.

RSS was sampled in fresh processes using native start/end markers, four measured and four unsampled controls per arm. Fixed thresholds use a previous independent CPU calibration. Time to a +9.27 MiB (sum-bits) or +264.11 MiB (3mm) rise is measured from that process's own inference-entry RSS. All four arms reached these increments. Use the [RSS sample and control report](RSS.md) for absolute levels, sampling gaps, per-trial outcomes and limitations. The independent 3mm peak RSS medians were 720.69 / 720.20 / 706.44 / 706.80 MiB. In this sample RipSat alone reached the chosen level earlier than leaf; combining the two libraries reached it later. The FEPT improvement is small.

## From the default one-hop edge to a checked second hop

The default library admits a fresh constructor **Let-return**. Both donors contain the native local record sequence 0→8→12, but the middle rule 55 writes Get through a Set. Its Let op0 returns the already known Single. Interpreting the Set as another Let-return would give the wrong proof. The default library therefore contains no length-two path. A producer-only NoAlias fixed point, a coinciding target schema and two unrelated source occurrences are insufficient alternatives.

The separate [publication authorizer](../ripsat-publication-chain/README.md) and [native Set-publication executor](../ripsat-set-receipt/README.md) cover one explicit exception with a new typed effect port. They check the actual Set key and assigned value, new public version, producer Cell, operation, source schedule and exact target bytes. The dot-product source receipt records the *same* middle invocation across both edges. It was different on Jacobi, whose accepted middle was not followed by a qualifying read of that Get. The terminal can consume only the actual fresh published result; missing/stale evidence restores its ordinary paid packet. Results for the opt-in publication ABI have a separate source matrix. They are never added arithmetically to the default union score.

## Reproduction

A native session built by the sibling strict-partial-named-ports build script and the original workload/weight bundles are required. Library verification is offline. The recorded experiment used source-equivalent compiled artifacts and trained weights from the same frozen bundles; input files are not fetched by any command here.

```sh
d=benchmarks/pass3-cell-gpu
a="$EXP/compact-holdouts-20261121-v1"
n="$EXP/strict-partial-named-v2/session"
l="$d/filtered-explicit-parent/library.json"
python "$d/ripsat-neural-bake/study.py" "$EXP" "$n" "$d/ripsat-donor-evidence/evidence.json" "$l" "$EXP/new-ripsat-comparison" \
  --donor "dot-product=$a/dot-product-1703/program.json" --donor "jacobi-1d=$a/jacobi-1d-1703/program.json" --cases sum-bits 3mm --repeats 4
python "$d/ripsat-neural-bake/rss.py" "$EXP" "$n" "$l" "$EXP/new-ripsat-comparison/results.json" "$EXP/new-ripsat-rss"
python "$d/ripsat-neural-bake/check_entry.py" "$EXP" "$EXP/new-ripsat-entry-check"
python "$d/ripsat-neural-bake/verify.py"
```

See the [standard compilation and cached-load commands](../explicit-parent-cell-composition/README.md), [lowering and rejection contracts](../ripsat-strict-programs/README.md) and [independent counterexamples](../ripsat-strict-acceptance/README.md).
