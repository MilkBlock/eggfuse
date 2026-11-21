# Published Cells at their speculative address

This native EggFuse research executor issues the learned proposal wave for a Run and acquires a bounded number of private, group-authorized Cell headers. Exact source validation and ordered physical birth authorize publication. The moving arm transfers a staged header into ordinary storage. The resident arms publish its address in a stable ID directory. Freshly promoted ordinary writers can still involve a temporary writer. The identity audit covers the finally published header and its backing fact buffer across handoff.

Four interleaved warm inference samples per arm, median milliseconds. The vanilla arm runs the original Cell CPU executor on the same program. Off retains the learned issuer with staging disabled. RSS is the median peak of three separate processes per layout, in MiB, including plans and process overhead.

| Program | Vanilla | Off | Move | Resident 16 / 64 / 256 | Peak RSS move / 16 / 64 / 256 |
|---|---:|---:|---:|---|---|
| sum-bits | 20.82 | 33.84 | 42.04 | 42.63 / 44.02 / 42.83 | 271.80 / 272.16 / 272.23 / 272.11 |
| conjugate-gradient | 326.17 | 632.31 | 642.95 | 639.08 / 654.59 / 655.41 | 461.23 / 466.58 / 468.98 / 471.56 |
| 3mm | 856.56 | 1,876.78 | 1,991.49 | 1,848.77 / 1,884.09 / 1,868.83 | 746.12 / 748.22 / 748.41 / 760.44 |

On 3mm, 137,864 authenticated Cells were published at their private address. At the endpoint, 43,542 survived. A width of 16 retained 40,325 vacant slots, compared with 74,367 at 64 and 113,503 at 256. The width-16 inspector recorded 10,629,893 reads of previously published Cells in later Runs. These are header accesses, including repeated accesses. Page capacity is charged while any resident survives. Each of the 120 bytes per retained slot counts even when vacant. The external allocator, ordinary graph storage, directories and fact buffers also contribute to process RSS.

Audit and timing use separate sessions. Verification covers ordered Run RHS, writes, Spine, unions, final graph, parent identity and physical births. To reproduce, build the sibling resident-cell-slabs executor, run study.py EXP NATIVE NEW_DIRECTORY, then peak.py EXP NATIVE TIMING_DIRECTORY NEW_DIRECTORY. Run python3 verify.py for the archived result.
