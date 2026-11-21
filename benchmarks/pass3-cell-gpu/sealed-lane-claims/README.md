# Redeem private Cells by sealed page and lane

A native issuer can retain the identity of an immutable proposal page across verification. The question here is how much the CPU gains if it uses that identity to authorize a preallocated Cell. Both arms run the same model and exact source schedule, propose the same witnesses and reserve the same number of private Cells per rule. The model predicts the count for a whole Run before its first source verification. The existing group policy lets any verified fresh primary Cell of the authorized rule and template redeem an unused record.

In the content arm, the staging group recovers the candidate's original page, decodes its reference vector and compares it with the consumed proof. In the sealed arm, the native issuer mints a monotonically increasing thread-local seal while freezing each single- or multi-parent page. Both the validated binding and the reservation refer to the same seal and lane. The redeemer checks their equality in constant time. The existing epoch, rule, template, source serial, lane bounds, remaining budget and one-time bitmap checks still apply. A failed private claim leaves the exact source allocator responsible for the fresh Cell.

A seal belongs to the local runtime. The network cannot encode or mint it. This experiment uses the single-threaded CPU executor and immutable pages that stay alive through the claim. Cross-thread or serialized handoff would need an issuer namespace or another transport for identity. The original source validation, numeric operations, ordered RHS commits, union, rebuild and Spine are all charged. Only the subsequent reservation check changes.

## Held-out Pass 3 results

| Workload | Independent exact CPU, ms | Proposal wave, staging off, ms | Group content, ms | Group sealed, ms | Parent-content checks removed | Sealed faster pairs |
|---|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 341.36 | 647.26 | 676.50 | 673.29 | 59,752 | 3/4 |
| 3mm | 836.98 | 1,851.52 | 1,906.91 | 1,888.07 | 137,864 | 3/4 |

The sealed arm reduces the median resident inference time by 0.48% on CG and 0.99% on 3mm. Both staged arms take longer than running the same proposal wave with staging disabled. Individual CG pairs range from a 42.41 ms loss to a 31.97 ms gain. On 3mm the range is a 22.76 ms loss to a 60.44 ms gain. Four samples establish a small observed difference with considerable variation. They do not establish a repeatable latency win. [All paired samples and counters](results.json)

Detailed audits independently decoded every successful seal and agreed with the original content verifier on all 59,752 and 137,864 decisions. The timed sealed arm disabled those audit decodes. Both staged arms match in every allocation counter, including preconstructed, consumed, unused, and verified physical payload identity. Independent source audits compare ordered per-Run RHS and effective writes, Spine, unions and the final graph. Comparing the two proposal arms also checks the issued wire, winners, committed parent IDs, nested Cells and physical allocation digest.

On sum-bits, the valid gate consumed 2,140 private Cells. A newly minted seal for the exact same page contents and a copy with its seal stripped each produced 2,828 denials and zero claims. The separate content audit accepted the payload of every such copy. Substituting another lane, withholding the receipt and supplying a stale epoch also resulted in zero claims. Replaying every successful grant produced 2,140 duplicate denials. All six faults preserve the source ledgers and final graph. [Fault controls](faults.json)

## Reproduce

Use the frozen Pass 3 artifacts and allocation policy from the [group experiment](../group-named-cells/README.md). The held-out stage runs are actual Cell CPU inference. Each sample starts with a fresh graph in a resident process. Program compilation and detailed audits run outside measured inference. Four rotated measurements follow warmup for each complete workload.

```sh
d=benchmarks/pass3-cell-gpu/sealed-lane-claims
python "$d/build.py" "$EXP/sealed-build"
python "$d/study.py" "$EXP" "$EXP/sealed-build/session" "$EXP/sealed-heldout"
python "$d/study.py" "$EXP" "$EXP/sealed-build/session" "$EXP/sealed-faults" --faults
python "$d/verify.py"
```
