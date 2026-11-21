# Borrow pristine private Cell storage across rules in a sealed Run

A whole-Run model allocates a fixed number of headers and fact buffers per rule before source validation. A rule may receive more memory than its eventually accepted bindings can use, while a neighboring rule needs another record. This experiment lets the second rule borrow a still-private record. It executes the complete native CPU Pass 3 with the same frozen forecast, exact source validator and schedule in both arms.

**Compatibility.** The executable derives a storage class from each compiled RHS program, using the same number of fact entries as the existing reservation constructor, `clamp(operation_count, 1, 4)`. All classes share the concrete Rust Cell header and fact-entry type. On a claim, the record must be unused in this Run, with exactly the requested fact-buffer capacity, empty slots and facts, the expected donor template, no parent, and zero recipe depth and completion progress. There are no pre-executed donor operations or values to transplant.

**Authority.** The recipient's issued lane retains its own rule, template, serial, immutable page identity and epoch. Once the original source verifier has accepted that lane and needs a fresh primary Cell, the pool first checks the storage class and then redeems that exact recipient voucher. The per-lane claimed bitmap prevents reuse. Only then may the allocator bind the empty header to the recipient's template. Programs, parameter bindings, integer semantics, RHS effects and graph visibility still come from the verified recipient. The physical fact buffer is transferred into the live graph, including through transient frame promotion.

**Allocation.** Both arms preconstruct the same per-rule spans in a single Run slab and issue the same vouchers to all lanes whose class has capacity, including rules whose personal grant is zero. The control restricts the allocator to its own span. The shared arm takes from that span first, then takes from another nonempty span of the same class. Each class maintains a stack of donor spans, with amortized constant-time selection. Unused private storage expires at the original Run boundary. Records can come from a funded rule that issued no lanes. The private slab capacities and bitmap/page admission are equal across the two arms. Peak private bytes are not whole-process RSS.

## Source-aligned measurement

The independent default-feature CPU and the staging-disabled proposal wave provide same-program references. Each timing arm uses the same resident native process, a fresh graph per measurement and seed 1703. Four rotated full inference measurements follow warmup. Compilation, detailed tracing and export are outside the inference interval. The native audit and a separate Python pass over compiler effect counts, per-rule grants, offers and fresh births both calculate the attainable capacity at each Run and layout. Every successful claim also checks physical backing identity in the detailed audit.

| Held-out program | Fresh primary Cells | Prebuilt | Rule-local used | Shared used = compatible ceiling | Own / other-rule physical records | Equal-budget, any-layout ceiling |
|---|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 96,535 | 97,293 | 59,752 | 69,855 | 56,046 / 13,809 | 72,777 |
| 3mm | 228,095 | 232,796 | 137,864 | 161,160 | 131,011 / 30,149 | 168,345 |

Cross-rule borrowing supplied **10,103 additional verified physical Cells on CG and 23,296 on 3mm**. Some recipients borrowed while their original span had already supplied another rule. This explains why total borrowed records exceed the net increase. Every loan switched to a different recipient template. On CG, 3,248 loans came from rules issuing no lanes, and 3,902 went to recipients with no original grant. On 3mm those counts were 7,050 and 6,682. The sets can overlap.

The earlier retrospective ceiling used only donors with offers. Under that restriction the per-Run ceilings that ignore layout were 68,637 and 158,785. Enforcing physical compatibility in that same subset gives 67,087 and 154,527. This native execution can also borrow records already allocated to donors with no offers. The aggregate private header and fact-buffer bytes match between arms, as do the bitmap bytes. For CG these capacities sum over Runs to 12,453,504 header bytes and 17,770,240 fact-buffer bytes. For 3mm they sum to 29,797,888 and 43,078,528. Peak private slab bytes were 1,163,392 and 2,666,688 respectively. [Counters, layout digests and timing pairs](results.json)

| Held-out program | Independent exact CPU | Proposal wave, staging off | Sealed per rule | Sealed shared | Faster than per rule |
|---|---:|---:|---:|---:|---:|
| conjugate-gradient | 331.15 ms | 631.87 ms | 696.51 ms | 673.05 ms | 3/4 pairs |
| 3mm | 878.16 ms | 1,883.98 ms | 1,992.02 ms | 1,971.56 ms | 2/4 pairs |

The measured median decreases were 3.37% on CG and 1.03% on 3mm. The four 3mm pairs split evenly; these samples do not establish a repeatable speed gain. Staging off was faster than either allocator on both workloads. All source audits align ordered Run RHS, effective writes, union, Spine and final state. Candidate, winner, ordered commit, parent provenance and physical Cell evidence also match between allocation arms.

On sum-bits, valid sharing used 3,150 records compared with 2,140 under the personal grants. A deliberately incompatible required width on a loan caused 1,563 layout denials and restored exactly the personal-grant result. Substituting a different recipient rule, another lane, a newly reissued page of identical contents, a stale epoch, or missing evidence each produced zero successful claims. Replaying accepted vouchers triggered 3,150 duplicate denials. All fault arms preserved independent source results. [Fault evidence](faults.json)

## Reproduce

```sh
d=benchmarks/pass3-cell-gpu/cross-rule-cell-pool
python "$d/build.py" "$EXP/cross-pool-build"
python "$d/study.py" "$EXP" "$EXP/cross-pool-build/session" "$EXP/cross-pool-heldout"
python "$d/study.py" "$EXP" "$EXP/cross-pool-build/session" "$EXP/cross-pool-faults" --faults
python "$d/verify.py"
```
