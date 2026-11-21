# A conservative higher-order Cell, an actual CPU request, and transfer to a specialized owner

This bounded prototype executes the [separately authorized 143 → 55 → 143 Set-publication path](../ripsat-publication-chain/README.md). Before any root verification, the issuer selects a distinct higher-order template code in the original root packet's existing template word. That code fixes a request to resolve a constructor Set and the allowed fresh, no-new-fact and stale branches. The root token has explicit input witnesses. A successful verified external root allocates one pending boxed context with those witnesses/versions, original root serial, issuance Run and a fresh monotone generation **before the producer RHS runs**. One CPU work item is placed in a request queue immediately. The model does not predict which branch will happen. This is an exact native runtime operating on the original graph; the token carries no independent terminal search.

At post-repair source Run publication, a FIFO batch opens each root's named first output if it was actually produced. The worker computes the Set key and assigned value from its port columns and a literal. A missing fresh first output settles that owner with no result. A retired or outdated first output cannot authorize later work. For a surviving request, the original middle Run must present the same physical input and version. The operation checks the current predecessor version and one actual middle alias slot, then uses the prepared arguments in the real Set. It executes the original exact source lookup/Set/union at its normal position. The request worker cannot move that lookup earlier, search for another parent, or assume in advance that the Set will be fresh. A failed alias guard uses the normal source operands and issues no specialized permission.

Only after the middle RHS succeeds is its verified actual Set outcome enqueued for resolution. Each reply must match the outstanding handle, generation and expected source Run. At the original Run boundary the reply processor checks current canonical operands, live membership and version. On a fresh result it **moves the same Box allocation** from the pending directory into a specialized directory. Publication checks that there is exactly one owner and that its physical address stayed fixed. The public routing entry contains a handle; the authoritative receipt and captured fields live in the specialized Box. Future source releases and the original ordered terminal RHS fetch that receipt through the handle. Absence, stale results and cancellation grant no terminal permission. End-of-pass retirement removes the routing entry, checks its owner identity and releases all surviving Boxes. Handles are scoped to a single inference request. Public fact identities, e-classes and the graph's own ownership remain under their original source rules.

## Outcomes and cost

| Complete Pass 3, same frozen CPU model | sum-bits | 3mm |
|---|---:|---:|
| Pending requests / request batches | 194 / 25 | 5,413 / 34 |
| No fresh first output | 159 | 4,171 |
| Actual prepared Set computations / operand slots delivered | 35 / 105 | 1,229 / 3,687 |
| Fresh physical Sets observed | 35 | 1,229 |
| Contexts retired stale across both source boundaries | 9 | 310 |
| Contexts moved in place / terminal commits | 26 / 26 | 932 / 932 |
| Same terminal typed constructor births / final-visible | 26 / 6 | 932 / 139 |
| Largest reply batch / peak specialized contexts | 49 / 26 | 1,075 / 932 |
| External packets / final-visible constructor origins per packet, both arms | 12,601 / 0.213554 | 555,913 / 0.166677 |
| Inference, direct / higher, ms | 36.03 / 35.76 | 1,875.02 / 2,053.68 |
| Prepared request wall, direct / higher, ms | 73.83 / 73.68 | 2,138.07 / 2,324.57 |

In 3mm, 1,242 first-output addresses were opened, of which 1,229 supplied the operands. Thirteen were already stale. Another 297 fresh Set results failed the later boundary check. The other 4,171 genuine no-result roots had no newly published first output; they did not execute a Set and should not be described as existing-key Set hits. In both traces every middle Set that actually ran was fresh. Existing-key Set and aborted-RHS branches are implemented but were not observed on these workloads. The peak combined Box-header reservations were 20,160 / 309,680 bytes. These are payload-layout counts, excluding vectors of named inputs and captured values, queue allocations, tree nodes, tombstones and allocator overhead. No RSS claim follows from these figures.

### Local verification clocks

Times are milliseconds from three separate complete diagnostic passes on each arm. The four alternating ordinary inference trials disable all these clocks. Each total is the median of the sum *within each diagnostic pass*, so it can differ from summing displayed component medians.

| Scoped clock | sum-bits direct | sum-bits higher | 3mm direct | 3mm higher |
|---|---:|---:|---:|---:|
| Request setup and transfer of checked operands, including alias guard | — | 0.0370 | — | 0.7929 |
| CPU request queue: exact named first-output read and projection | — | 0.0153 | — | 0.5313 |
| Original direct Set operand evaluation | 0.0037 | — | 0.1325 | — |
| Capturing/verifying the actual fresh Set row | 0.0072 | 0.0035 | 0.2106 | 0.0924 |
| Direct immediate end-RHS receipt publication | 0.0069 | — | 0.2354 | — |
| CPU response batches, scope checks and ownership transfer | — | 0.0428 | — | 1.1509 |
| Successful terminal receipt/field validation | 0.0093 | 0.0162 | 0.7026 | 1.1187 |
| Charged end-of-pass owner retirement | — | 0.0088 | — | 0.2275 |
| **Measured protocol total** | **0.0271** | **0.1266** | **1.2515** | **3.9717** |

The queued strategy reduces the direct fresh-row capture interval but adds selection-independent work for many roots without a result. Terminal receipt validation costs more for the same 190 / 7,418 successful port inspections. It must address and verify a separate specialized owner. Both arms still pay for the original keyed Set, native scheduler, maintenance and ordinary residual matching; shared graph work and uninstrumented outer loops are outside the component table and inside full inference time. The data do not establish a faster verifier from this representation. Locality here is a semantic addressability property. [Complete samples, outcomes, sampled addresses and clock counters](results.json)

Injecting a response with a different generation or source Run preserves the pending owner for its authentic reply. Replaying a committed response cannot transfer or retire a second time. Each such injection generated 194 / 5,413 explicit denials. Withholding every authentic reply and sending only stale generations yields zero specialized terminal commits and restores the Let-only external packet counts. Corrupting the middle alias guard triggers ordinary source operands and no specialization. Detailed fault audits compare against the correct direct or Let-only source, including every original Run's ordered RHS, effective writes, unions, Spine, final graph, original source scores, serials, physical allocations, birth/endpoint identities and actual terminal links. [Fault receipts](faults.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/ripsat-higher-cell
auth=benchmarks/pass3-cell-gpu/ripsat-publication-chain
python "$d/build.py" "$EXP/higher-build"
"$EXP/higher-build/session" --higher-cell-capabilities
python "$d/study.py" "$EXP" "$EXP/higher-build/session" "$auth" "$EXP/higher-study"
python "$d/fault_proofs.py" "$EXP" "$EXP/higher-build/session" "$auth" "$EXP/higher-faults"
python "$d/verify.py"
```

The opt-in `strict_named.higher_cell` includes `schema="eggfuse-ripsat-higher-cell/v1"`, `request="resolve-constructor-set"`, ordered branches `["fresh","no-new-fact","stale"]`, `batch="post-run"` and the SHA-256 of the actual target. The original checked Set-publication authorization remains mandatory. The runtime also pins the Set target to the program bytes actually loaded in both one-shot and persistent sessions.
