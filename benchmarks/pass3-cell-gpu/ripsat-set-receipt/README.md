# Use an actual fresh constructor-Set publication as a second named return

This native extension introduces the typed sequence `fresh_constructor_let → fresh_constructor_set`. The existing strict Let grammar and default RipSat adapter are unchanged. The separate [authorization artifact](../ripsat-publication-chain/README.md) establishes the exact earlier evidence and maps the source schemas to each target. The matched control grants only the original Let edge. The treatment tags the producer’s already issued root with the distinct Set-capable variant *before* verification, using another discriminator value in the existing template word. The original neural actor still chooses the root and named parents. There is no learned search for the middle or terminal parent.

In the authorized program, rule 143 constructs Single at its op 1. Its actual freshly returned FactRef permits rule 55 at a later Run. Only if this first child was internally generated from that exact root and successfully commits may its op 1 publish a fresh Get for another rule 143 activation. The Set first performs its ordinary source uniqueness/union logic. If an old key exists the extension grants nothing, regardless of whether the Set enqueues a union. Only the native fresh `Graph::activate` branch supplies the concrete physical address. The extension performs no additional Get lookup by key to find a parent.

The runtime checks the source instruction kinds, constructor table declarations, named slot/key sorts and initialized dependencies. On activation it checks the executing primary Cell ID, static op, current root and authenticated immediate model serial, source generation, native membership, fresh visible FactRef and exact ordered key/assigned value. It independently re-reads the actual operands from the named frame. The receipt remains private until successful completion of that whole RHS; source failure clears it. On subsequent original Runs the receiver opens that designated address, rechecks live visibility, version, original Run, table, value/keys under current canonicalization and the original signed path. An externally issued intermediate cannot mint a Set continuation. Both the submitted source hash and authorization target must equal the SHA-256 of the bytes actually loaded by the Rust process, also in persistent sessions.

## Native results

| Complete Pass 3 | dot-product | sum-bits | 3mm |
|---|---:|---:|---:|
| Actual first-hop commits reaching the Set / fresh Set publications | 44 / 44 | 35 / 35 | 1,229 / 1,229 |
| Additional second-hop packets omitted and actually committed | 36 | 26 | 932 |
| New / endpoint-visible typed constructors created by those terminal RHSs | 36 / 15 | 26 / 6 | 932 / 139 |
| External singleton roots, Let → Let plus Set | 6,752 → 6,716 | 6,524 → 6,498 | 333,365 → 332,433 |
| External multi-parent roots / selected child packets | 7,207 / 210 | 5,912 / 191 | 220,972 / 2,508 |
| Total actual paid packets, Let → Let plus Set | 14,169 → 14,133 | 12,627 → 12,601 | 556,845 → 555,913 |
| Final-visible origins per actual external packet | 0.189781 → 0.190264 | 0.213115 → 0.213554 | 0.166398 → 0.166677 |
| Inference, median of four rotated warm samples, ms | 31.25 → 31.72 | 34.68 → 34.91 | 1,836.48 → 1,869.77 |

Both arms run the same scalar-filtered partial named-port protocol. The paid denominator includes failed root proposals and every selected child action, even if no graph node is created. There were 416 / 305 / 7,120 separate child decisions. The total endpoint-visible constructor counts owned by these tokens remain 2,689 / 2,691 / 92,658. The 15 / 6 / 139 origins attributed to the second internally executed RHS are typed constructors; its dynamic and separately paid constructor counts are all zero. Each internal binding saves an external packet. The original root wire counter changes by −544 / +16 / +1,376 bytes because contiguous residual spans may need extra page headers.

Actual terminal examples were independently compared with the original committed source parent vector, complete physical birth event, owning root-frame allocation, assigned values and original constructor identity.

| Program | Original root → internal middle → internal terminal serials | Let FactRef / source Run | Fresh Set FactRef / source Run | Terminal Run |
|---|---|---|---|---:|
| dot-product, original authorized donor | 1,737 → 1,822 → 2,625 | (893,1) / 131 | (971,1) / 135 | 139 |
| sum-bits | 761 → 795 → 1,274 | (532,1) / 98 | (572,1) / 102 | 106 |
| 3mm | 43,986 → 45,772 → 66,237 | (18,438,1) / 822 | (20,198,1) / 826 | 831 |

These examples expose the original successful Set’s own publication. The receiver never infers an address by matching another row with the same key. All successful terminal activations retain the same root, actual immediate predecessor and full two-coordinate trail, including its concrete captured Get arguments and value. [Every verified release](links.json)

The ordinary source ledger matches on every Run's RHS inputs, effective writes, unions, Spine and final graph. Learned winner scores, ordered original parents, actual root/merge-child Cell IDs and both full constructor/endpoint identity ledgers match too. In normal execution there were zero internal receiver logits; only the fresh, prebound coordinates determine an internal child. The ordinary residual scorer still tests metadata and scores unowned rows. For 3mm, the treatment checks 62,168 registered named coordinates. Across its mixed occurrences, it inspects 5,540 residual-bank metadata entries and scores the remaining 3,379 external ones. Receipt checks, memory, ordering and bookkeeping are charged in the complete timing. Prepared request wall medians for 3mm were 2,100.43 / 2,136.32 ms. [Non-audit work](work.json) · [Paired samples, endpoints, faults and birth classification](results.json)

Withholding a real fresh publication or offering a changed version restores the Let-only packet counts, correct source graph and physical allocation stream. Deliberately corrupting the captured value fails its native row check. Declaring the Set to be a Let, a changed authorization hash and coordinated forged request/authorization hashes are rejected. These workloads exercised the fresh branch for every admitted Set; the preexisting-key/union-only and unsuccessful-RHS cancellation branches are explicit in the implementation but had zero observed instances in these traces.

```sh
d=benchmarks/pass3-cell-gpu/ripsat-set-receipt
auth=benchmarks/pass3-cell-gpu/ripsat-publication-chain
python "$d/build.py" "$EXP/set-build"
python "$d/study.py" "$EXP" "$EXP/set-build/session" "$auth" "$EXP/set-study"
python "$d/work.py" "$EXP" "$EXP/set-build/session" "$auth" "$EXP/set-study/results.json" "$EXP/set-work"
python "$d/verify.py"
```
