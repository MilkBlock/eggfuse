# Generate the two-parent candidate family before the directional join

The sender scans each table marginally. For a bounded interval of the public left frame, the trained tied projection produces the occupied query prototype IDs. The sender asks the right-table histogram how many rows have each corresponding key prototype and their maximum epoch. It can certify an absent prototype or a fully stale interval without visiting a single pair. It packs the remaining dynamic prototype IDs into a byte stream before the first candidate tuple in that occurrence is enumerated. This route enters before the ordinary issuer chooses forward, reverse-delta or guarded pair traversal. Higher-arity rule entries retain the original explicit issuer.

Each packet encodes nine little-endian 64-bit words (source epoch, original rule, left/right public generations, begin/end of the left interval, offset/limit inside each matched right posting and the predicted pair count), followed by bounded 32-bit learned prototypes. It contains no row IDs or candidate pairs. A small packet covers at most 8 left positions, 2 prototypes and 64 possible pairs. A wide packet covers at most 32 positions, 8 prototypes and 256 pairs. A heavy single prototype is split at a bounded posting offset. Neither the choices nor the packet budget depend on later winners. The query/key network is the frozen donor model common to the other verified-wave studies; the packetizer and its sizes are deterministic algorithm choices.

The receiver builds independent typed indexes from visible public graph rows and authenticates the source positions, generations, rule and extent. It intersects the packet's exact prototype set with its declared root interval and its bounded windows into the receiver's own right postings. This procedure never invokes the original directional join. The receiver then evaluates the original watermark, local, correlated freshness and derived arithmetic guards, restores the original left-major source order, rejects duplicate generated pairs and retains compact private offsets for the ordinary exact rule/suffix verifier. These separately allocated offsets, receiver indexing, filtering, sorting and later exact checks are charged. They do not cross the sender boundary. Every legitimate packet's decoded upper extent must equal the actual number of combinations visited. Fault controls change this extent and must be rejected.

The audit compares the *complete* regenerated raw multi-parent stream, ordered source RHS, effective writes, unions, Spine, exact graph, physical root/child identities and the full original constructor birth and final-visible origin ledgers. Every transmitted family, including those with no eventual commit or visible constructor, is in the packet denominator. We also charge each failed prototype (absent or entirely stale) separately, and report the marginal source scans and receiver work. The matched optimistic ceiling keeps the same original left intervals and all actually requested candidate combinations. Within each interval it lower bounds necessary packets by the larger of the key-count and candidate-volume packing bounds. It relaxes exact packing and right-window restrictions, and cannot use future winners to delete required work.

## Source-aligned Pass 3 results

| Workload | Scope | Group packets | External pair proposals replaced | Receiver pairs visited | Final-visible births on generated lanes | FEPT, emitted | FEPT, including absent/stale | Matched optimistic FEPT ceiling | Native median, ms |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3mm | off | 0 | 0 | 0 | 0 | 0.166032 | 0.166032 | 0.166032 | 1,725.01 |
| 3mm | small | 199,223 | 176,167 | 4,632,190 | 37,286 | 0.159445 | 0.023214 | 0.163443 | 2,313.52 |
| 3mm | wide | 58,264 | 176,167 | 4,633,068 | 37,286 | 0.210505 | 0.024703 | 0.212332 | 2,348.15 |
| deriche | off | 0 | 0 | 0 | 0 | 0.122863 | 0.122863 | 0.122863 | 3,331.39 |
| deriche | small | 266,406 | 217,988 | 5,513,738 | 39,790 | 0.117080 | 0.016909 | 0.118938 | 4,419.85 |
| deriche | wide | 76,821 | 217,988 | 5,514,532 | 39,790 | 0.143534 | 0.017770 | 0.144253 | 4,480.65 |

On 3mm, the wide actions replace 176,167 of 220,972 externally issued multi-parent tuples. On Deriche they replace 217,988 of 309,277. Source-aligned final-visible constructor counts remain 92,658 and 120,436. The wide descriptor format is close to its size/shape ceiling on both programs. A small size bound generates *more* packets than the ordinary representation. The smaller issued denominator has a large real cost. At the wide setting, 36,133 / 49,598 issued actions produced no committed lane and 49,874 / 67,741 produced no directly attributable final-visible node. Failed marginal prototype probes substantially outnumber transmitted packets.

One diagnostic execution per arm puts original two-parent generation at 318.57 / 481.17 ms. Wide issuing took 272.53 / 403.84 ms and the independent receiver took 619.44 / 866.01 ms. Source planning, final exact matching and RHS commit are additional costs in the whole-inference medians. In 3mm, rule 144 alone accounts for 4,084,017 regenerated combinations from 28,010 packets, with only 10,285 original candidates surviving. The projected second arithmetic condition is still checked by the receiver. Deriche shows 4,776,649 combinations narrowed to 12,246 for that rule. These observations identify a secondary port whose predictive value is omitted by the one-key packet. [Measurements, source ledgers, fault and per-rule counts](results.json) · [Independent sum-bits smoke run](smoke.json)

For a concrete packet, sum-bits Run epoch 9 uses compiled rule 279, whose independent parents are Const and Int. The wide action names source generations 4 and 2, the public Const interval [0, 4), and learned prototypes 963821 and 988663. It permits the first bounded right posting window and predicts four possible combinations. The receiver reads its public Int posting and the Const rows to recover their physical identities. The action carries no Int parent identities.

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/generative-pair-families
python "$d/build.py" "$EXP/pair-families-build"
python "$d/study.py" "$EXP" "$EXP/pair-families-build/session" "$EXP/pair-families-smoke" --smoke --cases sum-bits
python "$d/study.py" "$EXP" "$EXP/pair-families-build/session" "$EXP/pair-families-heldouts"
python "$d/verify.py"
```
