# Execute the learned batch and its verification program together

One native EggFuse research binary executes a complete Pass 3 on each program. It seals online neural proposals for the Run, optionally proves that certain singleton suffixes cannot match, and can share a compact candidate page and its checked scalar references with the exact verifier. The final arm also lets a donor-trained fraction head reserve compatible private Cells after the wave has been issued. These are sequential additions to one executable. All measurements charge their actual costs. The separate default CPU executes the same compiled source; it uses ordinary exact search.

| Program | Default CPU | Whole-wave issuer | Omit proved negatives | + compact queue | + positive row refs | + shared physical allocation |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 20.84 | 33.96 | 33.16 | 32.42 | 32.96 | 43.47 |
| dot-product | 17.62 | 30.63 | 30.37 | 30.02 | 29.71 | 39.39 |
| conjugate-gradient | 313.50 | 614.17 | 578.15 | 570.67 | 573.25 | 610.44 |
| 3mm | 860.75 | 1,854.22 | 1,767.33 | 1,739.79 | 1,803.07 | 1,810.46 |
| deriche | 1,477.74 | 3,411.18 | 3,007.98 | 2,978.12 | 2,969.18 | 3,214.76 |

Four rotated inference samples per arm after warmup, median ms. A sign change between two medians, especially on a small input, does not demonstrate a repeatable improvement. See the native samples in small.json and large.json. Input loading, detailed audit and final export are outside this interval.

| Program | Original RHS | Guaranteed negative lanes removed | Actual positive point references used | Private records granted | Prebuilt records used | Real fresh primary births |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 7,265 | 1,330 | 523 | 5,589 | 4,485 | 5,764 |
| dot-product | 6,704 | 1,778 | 1,439 | 5,698 | 4,229 | 5,538 |
| conjugate-gradient | 131,371 | 109,818 | 67,562 | 88,109 | 77,077 | 96,535 |
| 3mm | 294,917 | 510,574 | 120,889 | 209,856 | 181,707 | 228,095 |
| deriche | 635,818 | 1,652,058 | 491,435 | 400,274 | 359,600 | 447,949 |

Source attribution is unchanged. The model selects typed parents and the private allocation head predicts resource demand. The exact compiler-derived verifier inspects real graph keys, versions and epochs to omit impossible returns or produce a positive function-row reference. Every omission was rechecked with the original native verifier in the detailed audit, and every transferred positive reference was compared with the corresponding ordinary key lookup. The compact queue creates individual recipe handles only after successful positive matches. Prebuilt Cells stay private until the original rule's authenticated winner publishes one. A compatible empty header cannot transfer its donor's write permission.

The allotment includes four compiler-derived pristine layouts. For every program, the number of actual redemptions equals its independent fixed-budget layout ceiling and the payload-identity count. The causal model never sees this ceiling. Every configuration preserves the ordered Run RHS, effective writes, Spine, unions, final graph, winning original source parent + score + neural serial, root and nested physical Cell IDs. The filters can change raw certificate counts and compact serials in that raw stream. Once filtering is fixed, all deployment arms preserve its exact raw bytes and physical ledger. The 98% audit applies to direct source allocation; the last two columns count the separate subset of prebuilt primary Cells.

The count weights were frozen on sum-bits, dot-product and jacobi-1d. CG, 3mm and Deriche are separate workload tests; the two small programs check correctness and overhead on programs also used by the demand head. This integrated result is a single native issuer seed (1703); the independent wave-demand-policy directory contains a second-seed demand experiment. No GPU inference or concurrent Rust verifier is involved in these times.

```sh
python build.py "$EXP/new-integrated-build"
native="$EXP/new-integrated-build/session"
python study.py "$EXP" "$native" "$EXP/new-integrated-small" --cases sum-bits dot-product
python study.py "$EXP" "$native" "$EXP/new-integrated-large" --cases conjugate-gradient 3mm deriche
python verify.py
```
