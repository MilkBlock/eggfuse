# Published single-parent source headers on the frozen two-view policy

The frozen profile's `single_headers` clock covers the interval from the beginning of single-parent production through construction of its row-policy input. It already excludes scoring, sealing, source-suffix verification and attachment. This experiment splits that interval into static rule features, empty-table checks, immutable header lookup/build, the table-wide watermark filter, the per-signature frontier, and the remaining policy/group descriptor. Two additional nested clocks separate snapshot hits from reconstruction. Instrumented data are collected separately from the rotating clock-free latency trials.

Before this change, the certified row engine already kept one ordered header snapshot per parent table generation. The verifier also cached the table-wide maximum epoch, the typed port index reused signatures, and the scorer evaluated a common logit only once per distinct fresh/stale group in a rule occurrence. These structures had separate source enumerations. Earlier reverse-domain routing applied to multi-parent learned pointer expansion. The new reverse path below operates on the single-parent producer's original watermarked address bank.

In a fresh instrumented control, 3mm spent 270.62 ms in the combined header interval and Deriche 496.54 ms. The table shows medians in milliseconds from three resident repetitions. Each component starts its own clock; component medians need not sum to the median of their parent.

| Workload | Rule features | Empty-table check | Source snapshot | Table watermark | Signed frontier | Policy/group descriptor | Full header interval |
|---|---:|---:|---:|---:|---:|---:|---:|
| 3mm | 0.70 | 0.40 | 116.90 | 33.71 | 118.67 | 0.32 | 270.62 |
| Deriche | 1.18 | 0.65 | 185.28 | 59.60 | 249.64 | 0.47 | 496.54 |

The per-row test that selects the fresh/stale logit and writes it to a score slot occurs in the separately measured scoring phase. It cannot account for time inside the reported header interval. Classification, scattering and all neural score arithmetic together took 1.86 ms on 3mm and 3.80 ms on Deriche in that instrumented control.

The original source snapshot rebuilt 1,191 times and hit 7,906 times on 3mm. For Deriche the counts are 1,207 and 10,798. Both spend most of this interval maintaining or consulting candidate-source state. Computation of the rule features and the policy descriptor together costs under 2 ms on either program. The pre-existing 251.8/450.7 ms figures came from an earlier independently instrumented run. [Fresh phase samples](baseline.json)

## Runtime treatments

All arms use the same seed 1703, complete multi-parent enumeration, two tied learned views, immutable pages, constant-key guards, frozen bounded single-parent signed-epoch admission, updated epoch directories, and the source-checked Rust runtime. The original source binaries run independently. The changes live only in this isolated build.

* **Static features.** Cache the compiler-fixed rule and pivot features on first use. The current hidden state, candidate revivals, fresh/stale category, source identity and version still reach the scorer at every occurrence. It is incorrect to replay the previous hidden state's logits.
* **Published view.** One immutable source table view owns the typed address and its visible epoch in original order. Table frontier queries read its maximum epoch. Scalar snapshot reconstruction can consume it; both cold signed suffix scans and table-wide fresh-only parent filters use its per-watermark source offsets. Up to four recent watermarks are retained per current visible view. Every view is stamped with its table generation.
* **Incremental view.** Once a view has readers, the native post-repair publication records changed source addresses. On a version change merge the unchanged portion and current changed-address epochs in stable order. If the journal misses a generation, coalesces too many notifications to account for the difference, or exceeds 16,384 different addresses, reconstruct the source view. Audit compares all returned address/epoch pairs with a fresh native enumeration. The stale-generation control makes covered transitions ineligible and exercises that reconstruction route.
* **Direct typed headers.** The publication can emit the certified actor's immutable header rows directly. It retains the exact initial membership recorded by the actor, copies old source/address features across covered publications, and materializes new rows only for changed addresses. Table maxima and cold suffix queries read the same representation. A later generation consumes its new view without expanding an intermediate address/epoch vector.
* **Reverse single-parent routing.** For a nontrivial eligible source bank with one dynamic port, build typed row postings by the frozen learned key signature. At a later occurrence test only the occupied keys against every fresh suffix proof. Combine the surviving posting lists with **all** fresh parents, deduplicate, and restore original source order. If the enumerated ranges would contain more than half the bank, use ordinary forward filtering. Every selected root retains its exact original address and version. The reverse index covers at most 2 MiB of retained posting-array payload. Current per-table source views, up to four watermark offset buffers per table, transient sort buffers and journal metadata are additional. Process RSS is outside this experiment. Independent scalar replay in audit mode validates every routed candidate, including the rejected half of the original bank.

## Shared publication and source-order enumeration

Each full-pass time is a clock-free median after warmup, five samples on each anchor and four on each large program. The final three columns are independently instrumented medians; snapshot rebuild is nested within the total header interval.

| Source program | Vanilla | Original | Static features | Shared view | Incremental | With reverse postings | Original → incremental snapshot rebuild | Original → incremental table watermark | Original → incremental full header interval |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.83 | 32.46 | 32.53 | 32.67 | 31.92 | 32.46 | 0.99 → 0.40 | 0.18 → 0.22 | 2.15 → 1.62 |
| dot-product | 17.69 | 29.58 | 30.16 | 29.81 | 29.39 | 29.79 | 0.75 → 0.31 | 0.23 → 0.26 | 1.94 → 1.66 |
| 3mm | 906.91 | 2,150.72 | 2,098.09 | 2,082.63 | 1,986.49 | 2,017.60 | 119.63 → 30.52 | 35.90 → 15.13 | 283.53 → 166.19 |
| deriche | 1,523.11 | 3,752.80 | 3,682.14 | 3,691.50 | 3,605.83 | 3,641.15 | 179.01 → 41.56 | 58.43 → 27.03 | 476.24 → 301.51 |

On 3mm a full rebuild of each new shared view examines 5,701,120 visible-source candidates. Incremental publication enables 927,723 cold reads and 95,268 changed-address reads while inheriting 4,678,137 unchanged rows across snapshots. Deriche inherits 6,955,928 rows with 1,791,345 cold and 165,353 changed-address reads. The original and incremental four-trial timings favor incremental publication on every paired large-workload trial. The lower header reconstruction and watermark costs explain most of the observed header savings. The magnitude of end-to-end improvement remains machine- and schedule-dependent.

On 3mm the posting route enumerated a matching subset of 342,391 in banks totaling 3,763,702 source rows. On Deriche it selected 560,971 of 5,347,745. Sorting, deduplication, testing occupied codes, and index construction are included. The signature-frontier interval decreases by 5.4 ms on 3mm and by 4.0 ms on Deriche compared with incremental publication, but the complete median is slower on both. The small anchor header intervals are only around 2 ms before optimization. [Anchor samples and stale controls](anchors.json) · [Large source schedules and raw proposal comparisons](large.json)

## Direct typed parent headers

A separate same-binary comparison hands the versioned header payload directly to the actor. Scores are still computed against its current predecessor state. The original compiled control, the incremental intermediate view, the direct payload and direct payload with reverse postings were interleaved.

| Source | Vanilla | Original | Incremental | Direct typed | Direct + postings | Direct payload builds / inherits / actor borrows |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 21.70 | 33.80 | 33.02 | 33.18 | 35.29 | 14,690 / 24,830 / 398 |
| dot-product | 18.77 | 32.10 | 30.80 | 30.89 | 30.40 | 12,652 / 30,882 / 286 |
| 3mm | 870.61 | 2,112.49 | 1,944.97 | 1,918.26 | 2,001.63 | 1,022,983 / 4,678,137 / 1,191 |
| deriche | 1,553.31 | 3,804.47 | 3,631.74 | 3,523.35 | 3,593.59 | 1,956,639 / 6,955,928 / 1,207 |

Complete inference favors the direct payload against the original on both larger schedules. Its marginal advantage over the incremental intermediate view is uncertain: it wins only two of four corresponding timed repetitions on each large program. On 3mm its instrumented header interval actually increases from 166.05 to 175.31 ms, while on Deriche it decreases from 296.05 to 290.88 ms. Rich typed headers have a higher copy cost when rebuilding a table, and creating the shared view can be charged to the first reader. The primary result is shared incremental publication. Marginally lower median times for some later treatments should be compared against the full sample list. The direct learned path still costs 2.20× vanilla on 3mm and 2.27× on Deriche in this group. [Direct samples and provenance](direct.json)

All 7,265, 6,704, 294,917 and 635,818 source RHS retain neural ownership on sum-bits, dot-product, 3mm and Deriche, respectively. For 3mm and Deriche, 229,311/229,880 and 450,414/452,913 new physical Cell IDs retain direct source-certified recipes. In all four, the full single-parent decision fingerprint, including rejected proposals and score bits, accepted parent identities, source ordering and multi-parent raw hashes agree with the original. Injecting a stale transition on the two anchors triggered 567 and 466 explicit full-view reconstructions with identical source ledgers. These measurements use one frozen seed on one host. Jacobi and conjugate-gradient were outside this round. [Build identities](build-identities.json)

## Evidence and reproduction

The frozen policy must reproduce the complete source schedule, ordered RHS, effective writes, union sequence, Spine and final graph. Arms must additionally preserve all raw learned single-decision hashes, multi-parent raw packet hashes, issued counts, source addresses and ordinals, physically allocated root and nested Cell IDs, and the exact multi-parent budget/completeness contract. Diagnostic term construction and publication work are charged when performed inside inference. The source parse, initial graph setup, independent audits and final export are outside the resident wall clock.

```sh
d=benchmarks/pass3-cell-gpu/published-single-headers
e="$EGGFUSE_ARTIFACT_ROOT"
python "$d/build.py" "$e/NEW-published-build"
python "$d/study.py" "$e/NEW-published-build/session" "$e" "$e/NEW-header-baseline" --cases 3mm deriche --modes compiled --clocks 3 --repeats 4
python "$d/study.py" "$e/NEW-published-build/session" "$e" "$e/NEW-header-anchors" --cases sum-bits dot-product --modes compiled static publication delta postings stale --clocks 2 --repeats 5
python "$d/study.py" "$e/NEW-published-build/session" "$e" "$e/NEW-header-large" --cases 3mm deriche --modes compiled static publication delta postings --clocks 2 --repeats 4
python "$d/study.py" "$e/NEW-published-build/session" "$e" "$e/NEW-header-direct" --cases sum-bits dot-product 3mm deriche --modes compiled delta direct direct-postings --clocks 2 --repeats 4
python "$d/check.py"
```
