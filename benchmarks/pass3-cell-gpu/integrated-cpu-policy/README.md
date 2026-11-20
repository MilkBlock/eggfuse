# Shared source ports, single-parent epoch bounds, multi-parent pages and production proof retention

The previous multi-root page study compared pages with audit-only winner retention on Jacobi and conjugate-gradient. The 64 KiB single-parent freshness study ran separate multi-parent envelopes and retained all winner histories. This experiment links both implementations into the same native Rust executor. Every measured arm executes a full Pass 3 program with the same allocator, tied model and source ordering. The compiler-established constant-key transaction guard is fixed after its explicit baseline arm; it can broadcast `Add()` to the operation ports of downstream `Bop` parents.

| Arm | Change from the preceding configuration |
|---|---|
| Legacy | Original one-envelope-per-tuple generator, full winner archive, table-wide single-parent freshness check |
| Constant | Add compiler-proved constant-key guard |
| Archive | Build historical single-parent JSON only when auditing |
| Pages | Share one typed, versioned multi-parent envelope per nonempty rule occurrence |
| Signed | Add the four-training-family frozen 64 KiB single-parent maximum-epoch cache to Archive |
| Integrated | Run Signed together with multi-parent pages |
| Typed | Add 64 KiB of resident per-port signature/epoch arrays to Integrated |
| Typed256 | Use a 256 KiB typed projection budget |
| Changed | Use a 256 KiB projection budget and carry unaffected source values through a checked ChangeBatch |

The typed index is distinct from the frozen 64 KiB epoch directory. For each selected (table, port) it caches the learned key signature (2 bytes) and visible epoch (8 bytes) in source order. One immutable projection can serve every rule reading that port. It can also supply a future epoch directory, and a suffix scan can seed a projection later used by parents. The complete typed view is stamped by source table generation and union generation. A same-version read must agree with the current source bank's length. Source order is the Cell engine's sorted visible address order. The independent audit decodes every reused parent and checks its current identity, epoch, table, visibility and learned key. It also rechecks the full original source ledger.

The incremental variant stores an additional typed source address (8 bytes per live row). Native post-repair ChangeBatch notifications identify rows to re-read. When a version changes, the runtime merges the current bank and old projection in stable address order. A projection transfers only across the same union generation, when the source address and epoch agree, the address was untouched, and every intervening publication was covered. Dropped addresses disappear naturally. A missing notification table, version increment greater than distinct reported notifications, changed union generation, or over 256 pending notifications in one column forces reconstruction. The native full-row audit checks inherited signatures directly. The byte cap covers the retained contiguous arrays. Temporary reconstruction arrays, map overhead, key metadata and up to 256 pending changed addresses per cached column are additional. Guards, stable factorization, source collection, capping, handling publications and incremental reconstruction all execute inside the resident inference clock.

The primary timings include the learned single/multi-parent producers, exact source verifier, graph changes, repair, and Spine. Separate per-request graph initialization, configuration, export and local JSON RPC round-trip timings are also retained. Process startup and initial source parsing occur before the persistent session receives its requests. Audits run outside the timings and force full historical records for every mode. The three malformed multi-parent page controls must fail on the original missing verified recipe requirement. The 64 KiB admission is frozen from the prior four-family study, seed 1703.

## Full paired source measurements

Each entry is the median resident inference time in ms from five paired repetitions, seed 1703. Every one of the four programs achieves exactly the same per-Run source state in every arm, including physical origin IDs. No claim in this table combines numbers from earlier studies.

| Pass 3 | Vanilla | Legacy | + constant | + audit-only archive | + pages | Archive + signed, separate envelopes | Pages + signed | + typed 64 KiB | + typed 256 KiB | + typed 256 KiB and row deltas |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 22.25 | 38.30 | 39.12 | 38.37 | 37.18 | 34.79 | 34.45 | 35.10 | 36.08 | 34.38 |
| dot-product | 19.38 | 40.49 | 39.79 | 36.57 | 36.35 | 33.19 | 33.67 | 33.53 | 34.26 | 35.31 |
| jacobi-1d | 108.56 | 296.47 | 281.67 | 275.70 | 271.33 | 229.97 | 229.87 | 223.55 | 230.30 | 229.46 |
| conjugate-gradient | 359.73 | 1,378.92 | 1,359.25 | 1,343.56 | 1,274.20 | 1,050.79 | 1,023.58 | 1,014.89 | 1,030.77 | 988.74 |

| Source | Multi-parent packets / pages | Single-parent packets before → after | Direct pivot row reads, Integrated → Changed | Reused immutable port entries | Additional entries inherited through a changed table | Old directory rows saved |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 9,956 / 1,467 | 27,299 → 8,378 | 8,595 → 4,637 | 9,455 | 123 | 438 |
| dot-product | 12,099 / 1,250 | 31,745 → 10,990 | 11,317 → 4,330 | 13,344 | 0 | 284 |
| jacobi-1d | 122,523 / 2,519 | 320,752 → 61,416 | 158,340 → 58,106 | 162,601 | 38 | 1,851 |
| conjugate-gradient | 765,670 / 4,092 | 1,671,823 → 279,611 | 999,369 → 285,716 | 959,730 | 70 | 8,161 |

All four workloads improve relative to the original joint learned path. The page's marginal wall-time result depends on workload: the dot-product signed path takes 33.19 ms with separate envelopes and 33.67 ms with pages. The biggest per-arm change on both larger programs comes from excluding old single-parent proposals. On conjugate-gradient the separate signed path takes 1,050.79 ms; adding pages brings this to 1,023.58 ms, and the changed-port arm measures 988.74 ms against 359.73 ms for vanilla. On Jacobi the 64 KiB immutable projection has the lowest median in this group. The small runs do not demonstrate a universal payoff from the extra cache. [Source hashes, full timing samples, inference phases and RPC round trips](results.json)

## Maintaining suffix epoch directories

Two additional arms isolate the cost of reconstructing a whole signature directory. In the incremental arm, post-repair ChangeBatch updates the existing maximum for each changed visible row. Deleted/hidden addresses may leave an overestimated maximum, so a conservative result can keep an additional old proposal. Table generations advance only on a covered transition within the same union generation. Auditing independently decodes all visible rows at each successful update and asserts that the saved maxima dominate reality. This maintenance is charged at the original publication boundary.

In the sparse-build arm, the runtime first asks each stable typed source address for its visible epoch. Only the fresh rows of a cold table need a field decode to build the directory. The directory is stamped with the minimum watermark that this partial build can support. If a later rule queries at an older watermark it reconstructs the directory before permitting any pruning. Admission still charges the original visible-address count against the frozen scan budget. The experiment also combines both treatments and the incremental typed parent index.

| Source | Vanilla | Integrated reference | Incremental epoch only | Watermark-aware build only | Both directory treatments | Both plus changed parent ports | Decoded suffix build rows before → after | Extra publication row reads |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.81 | 35.27 | 32.76 | 32.76 | 32.55 | 32.21 | 9,447 → 776 | 182 |
| dot-product | 18.38 | 33.29 | 33.51 | 33.91 | 33.38 | 33.01 | 14,955 → 682 | 556 |
| jacobi-1d | 116.34 | 250.03 | 225.19 | 223.29 | 228.85 | 222.29 | 166,764 → 6,074 | 3,041 |
| conjugate-gradient | 383.08 | 1,101.34 | 1,053.23 | 1,052.27 | 1,046.54 | 1,027.99 | 859,854 → 30,174 | 10,504 |

In this independently paired directory run, the full treatment takes 1,027.99 ms on conjugate-gradient versus 1,101.34 ms for its integrated reference and 383.08 ms for its own vanilla reference. The earlier 988.74 ms figure comes from the first trial matrix, whose common baseline was faster. On conjugate-gradient the final configuration maintains 355 source directory versions, rechecks 10,504 changed rows, and reduces decoded source rows needed to build suffix directories from 859,854 to 30,174. Collecting 188,245 already-stale row headers still has a real cost. The audit independently checks the maintained bound against 283,519 fresh values. On dot-product the additional machinery changes the median by only 0.28 ms.

Retaining directories through publications can also change where the fixed budget admits filtering. The final single-parent issued counts for sum-bits, dot-product, Jacobi and conjugate-gradient are 7,889, 8,574, 51,189 and 243,383, respectively. All surviving physical origins, source RHS tickets, effective writes, union order, Spine resumes and final graphs match the vanilla/source-certified pipeline. [Directory study and timing samples](directory-results.json)

## Reproduction

```sh
d=benchmarks/pass3-cell-gpu/integrated-cpu-policy
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-integrated-build"
python "$d/measure.py" "$e/NEW-integrated-build/session" "$e" "$e/NEW-integrated-study" --repeats 5
python "$d/check.py" "$e/NEW-integrated-study/results.json"
python "$d/measure.py" "$e/NEW-integrated-build/session" "$e" "$e/NEW-directory-study" --arms integrated epochs sparse both all --repeats 5
python "$d/check_directories.py" "$e/NEW-directory-study/results.json"
```
