# Recover an actual producer subscription from its Cell address

A physical Eq ID can encode an originating Cell ID in its upper 32 bits and a source slot plus one in the lower 32 bits. In this bounded experiment the compiler template must resolve that slot through its actual definition table to a constructor let at the same destination. The resulting address is a *possible* subscriber. A live equality can also have functions, parents in other Cells, repeated input slots and an owner whose source fact was retired. Correctly naming the producer does not certify the rest of a union's notification domain.

The standalone native Cell CPU engine now runs two ways to omit these reverse entries. All representations retain the independent neural parent issuer, typed graph verification, original ordered union pairs, displaced wake order, RHS, effective writes, Spine and physical allocation provenance.

- **Presence mask.** On an actual subscription, a singleton reverse set equal to its own template-derived producer records only a bit for that result slot. A sparse page covers 256 Cell IDs, with one 64-bit word per Cell. The owner address and class key do not occupy a tree node or hash entry. On the first external subscription the store reconstructs the original owner, promotes the class to a full ordered bucket and inserts the external reader. If removal leaves only the owner it can demote again. Union can consume a singleton address directly; it does not allocate a temporary tree for a singleton wake.
- **Forward-derived owner.** The graph already maintains the ordinary dependency set from each physical fact to the classes it reads. Intersect the template-derived owner with its existing forward set after resolving old class IDs through the current parent relation. Leave all external subscribers in the normal explicit directory. There is no new mask, per-class counter or explicit owner ID on this path. A self-only domain therefore needs no reverse header at all. A mixed domain still stores its external readers, merging the inferred owner into original source order when read. The old producer memberships of both representatives are established before the union commits and the high class disappears. An owner redirected onto a different class becomes an explicit reader there, unless it is the checked owner of that target. Updating a genuinely changed value computes canonical old/new forward sets, so it also removes obsolete implicit edges. The existing forward map, owner Cell/template and exact external memberships are still charged.
- **Storage controls.** Besides the original tree, controls isolate merging smaller reverse sets, removal of empty headers, stored singleton addresses, and a mixture of the presence mask and stored non-owner singletons. The explicit differential control uses the same old/new registration updates as the forward-derived variant. Unrepresentable class addresses and constructor positions outside slots 0–63 retain explicit subscriptions.

The detailed executor maintains a separate explicit reference map from actual subscription events. It compares the complete ordered displaced set at every union before waking any source, then compares the complete ordered merged set and the final reverse directory. It records how often a valid owner belongs to a mixed domain and how many other subscribers would be lost by treating that hit as a complete domain. A separate independent source CPU executes the full Pass 3 for per-Run audits. This study gives a learned predictor no credit for membership or whole-domain coverage.

## Charged measurement

Four rotated resident inference measurements per arm follow warmup at seed 1703. The timing build uses the same allocator as the default Cell CLI. In a separate executable, the original graph is exported before each memory measurement. The counter measures net requested allocator bytes released by independently dropping the native reverse trees, mask page directory, stored singleton map, and finally the remaining Graph fields with the original compiled Program held. This reports exclusive terminal storage in the native graph, not total RSS. There is no shadow reference map in those runs. Initialization migrates the original seed edges before inference.

## Membership mask and stored singleton controls

| Source | Layout | Native tree headers / entries | Implicit owner bits | Explicit inline addresses | Reverse heap B | Dynamic Graph B | Inference ms |
|---|---|---:|---:|---:|---:|---:|---:|
| sum-bits | off | 2,193 / 10,262 | 0 | 0 | 746,888 | 4,607,130 | 31.76 |
| sum-bits | small | 2,193 / 10,262 | 0 | 0 | 745,928 | 4,606,170 | 31.37 |
| sum-bits | empty | 2,193 / 10,262 | 0 | 0 | 745,928 | 4,606,170 | 31.41 |
| sum-bits | owner | 813 / 8,882 | 1,380 | 0 | 431,544 | 4,291,786 | 31.54 |
| sum-bits | inline | 715 / 8,784 | 0 | 1,478 | 411,984 | 4,272,226 | 31.43 |
| sum-bits | hybrid | 715 / 8,784 | 1,380 | 98 | 419,136 | 4,279,378 | 31.20 |
| 3mm | off | 75,452 / 321,407 | 0 | 0 | 25,958,216 | 140,396,806 | 1,929.53 |
| 3mm | small | 75,452 / 321,407 | 0 | 0 | 25,837,256 | 140,275,846 | 1,868.99 |
| 3mm | empty | 75,452 / 321,407 | 0 | 0 | 25,837,256 | 140,275,846 | 1,834.88 |
| 3mm | owner | 14,350 / 260,305 | 61,102 | 0 | 11,929,672 | 126,368,262 | 1,817.67 |
| 3mm | inline | 14,094 / 260,049 | 0 | 61,358 | 14,089,296 | 128,527,886 | 1,850.30 |
| 3mm | hybrid | 14,094 / 260,049 | 61,102 | 256 | 11,893,328 | 126,331,918 | 1,776.74 |

At the final 3mm boundary the owner-mask layout eliminated 61,102 of 75,452 ordinary tree headers and 61,102 of 321,407 edge records. Exact reverse-field storage fell 53.8% against the empty-header control, and the complete terminal dynamic Graph fell 9.91%. This difference pays for the mask pages and their index. The separate single-process peak RSS sample was 783,892,480 vs 755,875,840 B, with one sample per arm. On sum-bits masks displace 1,380 tree nodes/headers but the directory still covers 25 sparse Cell pages; storing every singleton explicitly inline was smaller than using a mask there. [Source, timing and physical counters](storage.json) · [Exclusive allocation measurements](heap.json)

| Source | Committed unions | Structural owner address exists | Owner only | Owner + other readers | Owner absent | Other actual visits lost by an owner-only claim |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 1,039 | 1,031 | 188 | 422 | 421 | 1,415 |
| 3mm | 28,142 | 27,655 | 5,002 | 9,004 | 13,649 | 35,524 |

These counts are per union occurrence. In the mixed-domain column the physical producer really is present; a proposal which named it correctly still leaves other subscribers. The complete ordered explicit audit verified every such domain. The storage saving applies whenever a class is currently self-only, including classes that never occur on a union frontier. Thus its denominator differs from prediction accuracy on actual unions.

## Omit the owner link even from mixed reverse buckets

In the second matrix the differential control explicitly stores every edge; the derived arm removes the producer's edge while keeping the same insert/remove differences and small-side union merge. Both are timed in the same binary.

| Source | Derived owner edges / all | Entire reverse headers absent | Remaining explicit edges | Reverse heap, differential → derived | Remaining plus reverse Graph, B | Differential / derived / original / vanilla, ms |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 2,001 / 10,262 | 1,380 | 8,261 | 745,928 → 375,080 | 4,606,170 → 4,235,322 | 32.94 / 34.21 / 32.01 / 21.42 |
| 3mm | 72,401 / 321,407 | 61,102 | 249,006 | 25,837,256 → 10,784,840 | 140,275,846 → 125,223,430 | 1,916.95 / 1,887.83 / 1,826.27 / 890.62 |

On 3mm 11,299 additional producer edges were implicit inside mixed domains. A reconstructed owner was present at 14,006 actual displacements, including 9,004 mixed and 5,002 sole-owner domains. The other 249,006 final reverse edges remain explicitly represented. This released 58.26% of the reverse bytes and 10.73% of the terminal dynamic Graph relative to the matched control. The corresponding sum-bits reductions were 49.72% and 8.05%. The one fresh-process peak RSS sample on 3mm changed from 783,499,264 to 767,803,392 B, and on sum-bits from 285,016,064 to 284,524,544 B. Fixed source fields and a cold source image also contribute to that process measurement. The derived route won four of four timing pairs versus its differential control on 3mm and zero of four on sum-bits. In both cases the original learned path in this matrix had a lower median than the derived route. The primary benefit is memory.

Positions that read the same row more than once yield one native reverse dependency. All reductions here count stored dependency records or actual bytes, not a number of predicted argument positions. The exact rule justifies the elision independently of any network score. A model can point to this owner, but a claim that no other readers exist still requires the residual directory to be empty and the forward subscription to establish the owner's membership. [Same-binary source and order checks](derived.json) · [Separate graph-drop measurement](derived-heap.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/implicit-owner-subscribers
python "$d/build.py" "$EXP/owner-store"
python "$d/study.py" "$EXP" "$EXP/owner-store/session" "$EXP/owner-study"
python "$d/heap.py" "$EXP" "$EXP/owner-store/heap" "$EXP/owner-study/results.json" "$EXP/owner-heap"
python "$d/study.py" "$EXP" "$EXP/owner-store/session" "$EXP/derived-study" --cases sum-bits 3mm --arms empty diff derived
python "$d/heap.py" "$EXP" "$EXP/owner-store/heap" "$EXP/derived-study/results.json" "$EXP/derived-heap"
python "$d/verify.py"
```
