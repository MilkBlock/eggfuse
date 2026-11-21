# Transfer surviving scalar-function witnesses to the original verifier

The source snapshot and frozen learned policy are identical to the scalar omission experiment. This follow-up compares the original issuer, exact negative-only filtering and negative filtering plus positive witness transfer in one native Rust Cell CPU executable. All three arms score the same candidates and advance the recurrent network with the original causal inputs.

Consider a scored Concat pivot. The negative filter already reads the native function directory for each of the two operand keys to test presence and visible epoch. If it survives, the positive arm appends those two physical row references and their versions to a contiguous per-rule page, alongside the issuing model token serial. The compiler maps the two verifier atom positions to offsets in this lane. Repeated reads of a single table/column share the issued reference. The page stores a compact receipt per distinct port and leaves the source values in their native rows.

At consumption, the original verifier reopens the pivot, runs its source checks, materializes each key from verified registers and resolves the named physical row directly. It checks the original source table, physical witness, live visibility, version and equality of the canonical complete key before using the row’s current value. The existing verifier then evaluates result predicates, source arithmetic, Run freshness and RHS slot projection as usual. An invalid transferred version aborts the request. Unsupported plans retain their ordinary issuer and point verifier. The existing whole-Run wave additionally checks graph epoch, union count and watermark at handoff. Each page checks its consumed token serials and empty tail. Model credit remains the original pivot choice; the positive proofs and numeric values are deterministic work.

During independent per-Run auditing, each transferred read is also compared with the original complete-key lookup, including its exact fields. A fault control alters transferred versions and must fail at the first point consumption. The timing pass checks the count of real native transfers again with that independent comparison disabled. Primary/nested Cell identities, source parent versions, winner fields and ordered effects must match across all three neural arms. Raw proposal and receipt hashes must match between negative-only and positive handoff. Benchmarking uses the same allocator and frozen seed, charges the full runtime, warms each mode and rotates six samples.

## Results

| Measured complete path | CG | 3mm |
|---|---:|---:|
| Independent default CPU inference, ms | 326.15 | 844.55 |
| Original / negative / negative plus ports inference, ms | 595.56 / 578.76 / 570.35 | 1,844.79 / 1,754.64 / 1,732.73 |
| Original / negative / negative plus ports full resident request, ms | 703.24 / 695.10 / 682.89 | 2,069.65 / 2,014.11 / 1,982.60 |
| Surviving eligible pivots | 49,378 | 93,729 |
| Distinct point references emitted | 69,971 | 127,482 |
| Native verifier point lookups replaced by checked direct reads | 67,562 | 120,889 |
| Total logical verifier table-atom reads | 149,463 | 368,757 |
| Sum of retained per-rule serial/reference capacities, bytes | 98,624 | 116,480 |

CG avoids a repeat keyed lookup on 45.2% of all singleton verifier table reads; 3mm avoids one on 32.8%. A surviving lane may still fail a pivot or intermediate result predicate before reading its last reference. The negative and positive arms have identical counts for proposals, decisions, root payload wire bytes and allocations. The additional receipts reside in separate verifier-side pages and are charged in timing. The buffer-capacity row excludes the compiler maps, Vec headers and allocator overhead.

The median improvement from the positive handoff alone is 1.45% / 1.25%. It wins three of six pairs on CG and four of six pairs on 3mm. The search interval medians are 404.11 → 400.33 ms and 1,267.27 → 1,249.94 ms. The strongest evidence is that all 188,451 actual direct reads validate against independently recomputed exact lookups, with unchanged source and physical ledgers. Both version-corruption controls fail explicitly after two completed Runs. Six noisy timing pairs on one host and one seed give limited confidence in the smaller latency difference. [Timing samples, fault outputs and source receipts](results.json) · [Executable and frozen inputs](manifest.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/single-scalar-handoff
python "$d/build.py" "$EXP/port-handoff-build"
python "$d/study.py" "$EXP" "$EXP/port-handoff-build/session" "$EXP/port-handoff-results"
python "$d/verify.py"
```
