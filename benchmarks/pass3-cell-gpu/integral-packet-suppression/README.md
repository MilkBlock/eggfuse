# Remove actual singleton wire packets from fully certified Run occurrences

> **Metric clarification.** A released fact certificate lets the runtime reconstruct a consumer whose external proposal was suppressed. A birth rate using only transmitted packets measures external transport yield. The suppressed consumer contributes no separately demonstrated model choice of its concrete parents. [Explicit-parent FEPT accounting](../../../docs/EXPLICIT_PARENT_FEPT.zh.md)

A previously accepted producer root already supplies a fact and ownership certificate to a future consumer. At its original Run release, the independent integral verifier reads the published source address/version, checks the key program and computes a potential exact binding. The outer model still scores its ordinary source bank, including each rejected candidate, using its actual prior recurrent state.

A rule occurrence is eligible for suppression when its singleton plan has a compiler-proved deterministic pivot. Every proposed source address and version must appear exactly once in the independently released bank for that very pivot, in the same order. Every learned decision must send, and the certified model must have a common exact score for each occupied old/fresh group. Sizes, source order, aliases, watermark and parent/root identities have to agree. Missing, colliding or differently ordered banks use the ordinary external issuer. Suppression does not read eventual accepted tickets.

For a closed occurrence the model emits **zero singleton page lanes or wire bytes**. The local verifier uses its earlier root and ordered independently computed slots, exact witness identities, two local score groups and a logical serial range to construct the consumer's native binding. Reserving a serial range does not allocate or serialize per-lane wire. Native mark and root records still exist for source arbitration and ordered RHS projection. The real ordered commit verifies the parent provenance and uses that binding. No extra external summary, per-child certificate or per-bank packet is serialized. This is a local native CPU issuer/verifier experiment; byte counts describe the original root wire encoding. The internal CPU proof pages, checking and graph queries are real work, all charged to the full inference clock.

## Measured packet and node counts

This matched build uses the previous integral verifier with the singleton scalar filter **disabled** in both arms. Its sum-bits baseline is 7,889 singleton packets; the separately measured filtered headline used 6,559. The denominator counts every emitted root in this build and every selected nested merge-child packet, including packets that produce zero nodes. Treating every merge-child decision as traffic is a separate, larger denominator.

| Actual complete Pass 3 measurement | sum-bits | 3mm |
|---|---:|---:|
| Singleton proposals, external → closed | 7,889 → 7,175 | 845,168 → 836,221 |
| Multi-parent proposals | 5,912 | 220,972 |
| Selected merge-child packets / all child decisions | 191 / 305 | 2,508 / 7,120 |
| External roots + selected child packets | 13,992 → 13,278 | 1,068,648 → 1,059,701 |
| External roots + all child decisions | 14,106 → 13,392 | 1,073,260 → 1,064,313 |
| Token-attributed new constructors / original identities visible at final export | 3,610 / 2,691 | 119,503 / 92,658 |
| New constructor births per root + selected child packet | 0.258005 → 0.271878 | 0.111826 → 0.112770 |
| Final-visible constructor births per root + selected child packet | 0.192324 → 0.202666 | 0.086706 → 0.087438 |
| External root wire bytes | 287,128 → 261,032 | 20,817,600 → 20,586,680 |
| Whole native inference, median of three warm samples, ms | 39.39 → 39.24 | 2,209.01 → 2,190.28 |

The native birth ledger attributed constructors by actual ordered root serial and final membership by the original fact identity. One / 28 other constructor births occurred with no active token and are excluded from both numerator ratios. [Node attribution and denominators](effective.json)

Of 1,525 / 8,334 nonempty singleton banks, 140 / 253 met closure. All **714 / 8,947** omitted packets became independently verified, actually committed internal bindings. No candidate from a partially covered bank was removed. The other banks had no matching integral offer (1,264 / 7,740) or mismatched bank cardinality (121 / 341). The integrated verifier still examined 12,066 / 1,284,218 scheduled delta ports and did 2,635 / 106,245 exact suffix lookups to derive 1,243 / 36,873 first-hop offers. The model still scored the external source bank. Three timings give limited evidence for speed; the verified reduction is in emitted packets.

Every omitted lane was rematched against the original checker on a separate audit pass. Detailed singleton decisions, original ordered winners and slot values, all committed root serials including logical internal serials, nested/physical IDs, each Run's RHS, effective writes, union, Spine, final graph and complete constructor birth/endpoint identity ledgers agree. A corrupt internal release epoch aborts after 8 / 26 completed Runs. [Per-rule savings, corruption controls and timing samples](results.json) · [Frozen executable and sources](manifest.json)

```sh
d=benchmarks/pass3-cell-gpu/integral-packet-suppression
python "$d/build.py" "$EXP/closed-integral-build"
python "$d/probe.py" "$EXP" "$EXP/closed-integral-build/session" "$EXP/closed-integral-run" --cases sum-bits 3mm
python "$d/effective.py" "$EXP" "$EXP/closed-integral-build/session" "$EXP/closed-integral-nodes"
python "$d/verify.py"
```
