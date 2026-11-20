# Reuse a previous no-binding proof on a newly issued token

The CPU network can issue the same parent in another source Run because a suffix table changed somewhere. The verifier now retains a bounded certificate keyed by the original rule, parent address and parent version. A previous successful proof records its maximum supporting epoch; it can reject a later proposal only when the source rule is seminaive and its current watermark is strictly higher. A failed pure guard records the support that determined it. A missing complete-key fact also records the table and key. No cached proof can produce a positive binding, allocate a Cell or advance a source obligation by itself. The new token is still independently issued in original order.

The compiled plan must have a nonempty determinate suffix and only supported deterministic operations. The current observer admits up to six positive supports, each containing at most eight Eq/i64 fields. Captured rows retain their actual immutable payload and physical witness. A stable table generation suffices within the same union generation. In the more precise arms a table-generation mismatch verifies the original anchor address or live unique function row; a changed virtual point rechecks the complete key and the physical source returned. Forwarded values and epochs must agree. Crossing a union rechecks all retained supports and any previously missing key. A changed result expires the certificate and resumes the ordinary verifier. Successful revalidation rebases the generation stamps. A source watermark can move backwards without turning a previous stale positive into a permanent refusal.

Each executor has an 8,192-entry directly mapped directory. The delayed variant retains a full certificate only after seeing the same rule, address and version twice in its admission slot. The stamp is evidence for admission frequency only. Except for the deliberately cached decision, each audit independently re-evaluates the original projected verifier on every refused token. Actual source checks, raw proposals, source winner parents and fresh physical allocations are compared with the independent frozen CPU control. Search, verification, RHS and notifications remain inside resident inference timing.

| Program | Vanilla | Joint default | Projected | Table stamps | Row recheck | Across union | Second visit, ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.19 | 33.44 | 33.61 | 34.00 | 34.80 | 35.04 | 34.36 |
| conjugate-gradient | 358.22 | 658.37 | 662.35 | 694.33 | 646.16 | 636.00 | 628.24 |
| 3mm | 917.05 | 1,952.65 | 1,935.04 | 2,063.81 | 2,001.40 | 1,910.34 | 1,912.27 |

| Program, second visit | Cross-Run hits | Certificate writes | Baseline suffix points | Remaining suffix points | Positive point rechecks | Missing point rechecks | Additional physical row reads |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 1,668 | 971 | 8,270 | 4,964 | 1,785 | 425 | 2,597 |
| conjugate-gradient | 95,053 | 53,549 | 317,345 | 163,933 | 21,363 | 9,721 | 188,091 |
| 3mm | 424,042 | 124,822 | 1,125,727 | 482,101 | 68,810 | 33,029 | 679,682 |

On the seven-rule marker-compiled fixture, the first search can read LeftScore(Key 2) but lacks RightScore(Key 2). An update at Key 99 leaves that absence usable. Filling the missing key in Run 4 permits the previously absent result in Run 5. A Key 1/Key 3 union in Run 6 and a later smaller integer value both permit new original RHS inputs. The union-aware verifier reused six proofs across Runs and independently reconfirmed all six refusals. One saved missing-key proof expired after a real insertion and two header/payload checks failed. All successful bindings, old and new, still passed through the normal verifier. [Fixture source](change.egg) · [Detailed controls](fixture.json)

Fresh-process peak RSS includes graph setup and final export and was measured separately from the resident clocks. The projected / eager cross-union / second-visit medians were 271.91 / 272.92 / 272.45 MiB on sum-bits, 464.19 / 466.30 / 466.84 MiB on conjugate-gradient, and 747.38 / 751.64 / 756.28 MiB on 3mm. Fewer occupied certificate entries do not by themselves establish an RSS improvement. [Fresh process samples](rss.json)

## Read the stored Cell instruction directly

A further treatment revalidates the old address without reconstructing an intermediate Row where the original storage layout permits it. For a function or a fact that retains a decoded immutable payload, pointer identity proves the values equal after liveness, table and version checks. If the payloads differ, the full treatment compares their slices. A compressed fact uses the same linked cell instruction, source slots, result argument and canonical argument accessor as the ordinary decoder, comparing in place. A bare function reads and canonicalizes its actual key and value. A special unit payload or stable fact representation retains the ordinary accessor. A virtual complete-key point which could choose a different physical source still performs its point lookup. The detailed evaluator independently checks both the accept and reject outcomes of the physical row comparison before trusting them.

| Source | Same-build projected | Second visit, original revalidation | Shared identity/header | Full direct comparison, ms | Full direct checks: header / shared payload / compressed fact / bare function |
|---|---:|---:|---:|---:|---:|
| conjugate-gradient | 618.76 | 615.52 | 599.85 | 610.56 | 38,463 / 149,409 / 0 / 219 |
| 3mm | 1,935.21 | 1,935.38 | 1,909.68 | 1,882.17 | 69,688 / 609,789 / 0 / 205 |

Both source programs typically kept the immutable payload needed for the cheap identity comparison. No compressed-fact instruction comparisons occurred naturally in these timed passes. A separate source-fixture control clears an existing fact's decoded field cache and a unary function's decoded cache, leaving the graph and source versions in place. Both direct accessors reproduced the ordinary decoder and rejected forged fields and epochs. No timing benefit is attributed to this forced cache state. [Physical ablations](physical.json) · [Representation-only control](representation-probe.json) · [Source and timing archive](results.json)

```sh
d=benchmarks/pass3-cell-gpu/run-result-certificates
python "$d/build.py" "$EXP/result-proofs"
python "$d/study.py" "$EXP" "$EXP/result-proofs/session" "$EXP/proof-runs"
python "$d/study.py" "$EXP" "$EXP/result-proofs/session" "$EXP/proof-fields" --cases conjugate-gradient 3mm --arms reference two-hit identity compressed eager-compressed
python "$d/peak.py" "$EXP" "$EXP/result-proofs/session" "$EXP/proof-runs/results.json" "$EXP/proof-rss"
python "$d/fixture.py" "$EXP" "$EXP/result-proofs/session" "$EXP/baked-verifier/session" "$EXP/new-fixture"
python "$d/probe.py" "$EXP/result-proofs" "$EXP/new-fixture/compiled/program.json" "$EXP/field-probe"
python "$d/verify.py"
```
