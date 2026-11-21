# Signed explicit-parent Cell composition

The unit of generation is an external token naming a source rule, its exact physical parent(s), versions and a compiled variant. The variant encodes fixed instructions `producer operation → sole consumer pivot`. Up to two such edges can follow a root. The issuer selects the program before any parent validation or execution. Only constructors with an actual newly published physical fact from that selected primary Cell frame may supply a continuation. A cached constructor returning an already existing row, a nested allocation or an unrelated neighborhood cannot supply a replacement child. A nullary producer is ineligible for a signed continuation.

**What the model learns.** The original frozen CPU model still selects each root instantiation and its concrete parent(s). This ablation does not train new weights to find a more productive root. Bake learns which static variant to attach to an eligible producer schema from dot-product and jacobi-1d, before held-out execution. The issuer puts its variant selector in the high half of the existing singleton or multi-parent template word. Multiple roots packed in the same native page remain distinct paid tokens. The additional ID consumes bits; it adds no serialized word or extra model packet in this encoding. The library, registry and per-instance verifier work are real costs.

**How a child executes.** The compiler requires a seminaive consumer with exactly one constructor table, distinct LHS slots and a complete direct RHS-slot projection. A signed producer can register only the physical FactRef at its specified constructor instruction and a statically wired future consumer. For a second hop, the first child must have been internally generated, actually committed, and must itself publish the specified primary-frame output. The original root identity, earlier Run, compiled payload position and row version are retained. The stored program fixes each operand column and output instruction before execution.

At a scheduled Run, the verifier visits previously registered obligations, opens **only their named addresses**, checks membership, current version, Run and visibility, and projects the existing fields. To replace an entire consumer occurrence, the number of distinct, live, correctly versioned signed addresses must equal the native table membership count. The scalar count supplies a completeness check without enumerating the graph or matching against model proposals. Hidden, retired and changed rows cannot falsely certify the count. An incomplete occurrence uses the original standalone issuer in full and gets no suppression credit.

On successful normal execution this closure check happens **before the ordinary candidate bank is accessed**. The actor neither scores nor emits standalone child candidates. Under the frozen certified single-row policy all released sole-table rows are fresh and would be selected. The original recurrent update depends only on the known occurrence size, number selected, fresh count and static rule ID; its original logical serials advance. Internal native bookkeeping records and slot copies still exist. Source Spine ownership is restored via a direct lookup at each known FactRef; closed occurrences bypass the generic scheduler's delta enumeration. Audit mode alone evaluates the old scores from these prebound headers and independently rematches each internal binding. Production counters and audit score counters distinguish these paths. The implementation supports the ordinary published cursor map and checked-slot source configuration.

## Training and withheld programs

Round one executes the compiler-enumerated one-edge variants on the two donor workloads. Rank consumer schemas by actual committed internally generated children, select up to four positive consumers, and retain all observed producer operations feeding those chosen consumer schemas. Round two freezes those prefixes and explores statically composable next operations only from internally committed children. The frozen library has 23 one-edge paths and 3 connected extensions. Rules are relinked only by unique compiled structural identity. The training set and held-out program hashes are disjoint.

A real dot-product template begins with rule 440, which checks a positive lower bound on a pointer addition, and publishes NoAlias at instruction 3. Rule 446 reads that exact NoAlias and constructs its transpose at instruction 0. Rule 446 then consumes this actual new output at its next eligible Run. There were 28 such genuine second-hop commits in dot-product; across its three paying extensions jacobi-1d produced six. Across both donors round one produced 1,294 committed internal children. These are donor results. [Frozen variants and donor receipts](library.json)

| Held-out real Pass 3 | sum-bits | 3mm |
|---|---:|---:|
| Retained constructor identities / new token-attributed constructors | 2,691 / 3,610 | 92,658 / 119,503 |
| Ordinary literal single / multi / selected merge-child packets | 7,889 / 5,912 / 191 | 845,168 / 220,972 / 2,508 |
| All child decisions, including unselected | 305 | 7,120 |
| All compiler variants, genuine internal first / second children | 239 / 0 | 3,448 / 0 |
| Frozen donor variants, genuine internal first / second children | 0 / 0 | 0 / 0 |
| All compiler variants, original → remaining external packets | 13,992 → 13,753 | 1,068,648 → 1,065,200 |
| All compiler variants, root wire bytes | 287,128 → 280,112 | 20,817,600 → 20,733,248 |
| Final-visible nodes/packet, leaf → all compiler variants | 0.192324 → 0.195666 | 0.086706 → 0.086986 |
| Final-visible nodes/packet, frozen donor 1 / 2 | 0.192324 / 0.192324 | 0.086706 / 0.086706 |

This is a like-for-like **unfiltered explicitly named leaf baseline**. The separately measured scalar-filtered source and generative class/region protocols have different denominators. Zero-birth external packets and all selected merge-child packets count here.

The compiler-enumerated variant tags 3,462 / 112,095 external roots. Of those, 1,760 / 53,117 are verified roots with explicit named inputs. At runtime it checks 3,973 / 176,990 previously registered coordinates and performs 902 / 12,780 local field reads. Only 20 / 25 consumer-rule occurrences establish whole-table coverage; they generate 239 / 3,448 internal children at their original releases, with the same number of direct Spine ownership lookups and zero normal child logits. The frozen library tags 79 / 2,049 external packets, registers 67 / 1,574 ports, and closes no occurrence. Its represented target, rule 506, failed all 27 / 47 pre-read cardinality checks. The maximum named / native membership sizes observed were 67 / 192 and 1,574 / 4,058 respectively. Merely learning more tokens from these same surviving signed instances would not certify the missing source members.

Full uninstrumented inference medians from three rotated samples were 32.39 / 1,971.42 ms for ordinary leaves, 35.92 / 1,931.94 ms for all one-edge templates and 34.97 / 1,884.04 ms for all two-edge templates. Donor one- and two-edge medians were 33.28 / 1,860.38 ms and 34.13 / 1,928.32 ms despite identical held-out packet counts. The spread limits timing attribution; suppression and immutable constructor identity ledgers determine the reported yield. Flipping the actual output operation index fails the signature check on the first would-be internal release, after 256 / 1,566 original Runs. Every mode matches the independent source on ordered RHS, effective writes, union, Spine and final graph, and preserves real winner scores in the separate audit, root and nested allocation IDs and the original constructor/endpoint identity ledgers. [Individual samples, production counters, physical receipts and controls](results.json)

```sh
d=benchmarks/pass3-cell-gpu/explicit-parent-cell-composition
python "$d/build.py" "$EXP/explicit-build"
python "$d/bake.py" "$EXP" "$EXP/explicit-build/session" "$EXP/explicit-bake"
python "$d/study.py" "$EXP" "$EXP/explicit-build/session" "$EXP/explicit-bake/library.json" "$EXP/explicit-study"
python "$d/verify.py"
```
