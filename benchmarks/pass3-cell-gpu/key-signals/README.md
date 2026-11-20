# Complete-key parent ambiguity (Figure 46)

Two independently trained seeds (1703/1709) each use the same synthetic key bags and 800 training steps across four arms. The narrow baseline has 1,025 parameters. Widening the single 128-bucket embedding from 8 to 16 dimensions uses 2,049. A second domain-separated hash with its own 8-dimensional book, or the compiler origin role with an 8-dimensional book, also uses 2,049. A dynamic canonical constructor class can supply the table that defined its result slot. Imported/released origins and ordinary scalars map to the explicit unknown role. Each arm has exactly the same candidate addresses, per-key abstention contract and lookup fallback. No Pass 3 data or ground truth is used in training.

| Real program | Valid RHS | Directly supplied: narrow | Wide | Two hashes | Role |
| --- | ---: | ---: | ---: | ---: | ---: |
| sum-bits | 889 | 680 | 680 | 889 | 857 |
| dot-product | 952 | 563 | 563 | 952 | 876 |
| gemm-bias-relu | 2,103 | 951 | 951 | 2,053 | 1694 |
| stable-argmax | 1,266 | 709 | 709 | 1,266 | 1120 |

Counts in this table are identical across the two seeds (see per-seed results). On sum-bits, both the narrow and the wider single code leave 6,402 present anchor obligations with an indistinguishable competitor; two hashes leave zero. On gemm-bias-relu the count falls from 44,197 to 2,471. A single full key can recur in many Run obligations. The audit also counts absent parents, wrong references with exactly the query's encoded key, wrong references sharing only the first bucket, and near-score false positives. The reference directory read in the audit build checks actual physical parent identity and never contributes an execution row.

Improved discrimination does not make scoring cheap. On sum-bits (seed 1703) the two-hash head takes about 102 ms; direct CPU point lookup takes 26 ms for the whole pass. There is still a score over every candidate position in the resident bank. The role feature helps even with frequent unknowns, and a larger single-book embedding cannot separate identical codes. Use the CPU key index in the tested engine. The two GPU channels remain useful controls for future template-selection studies.

All four model arms and the CPU point control use the same compiler certificates. Ordered Run path, effective writes, RHS, Spine and final graph match the independent Rust reference. Timed and audited binaries are separate. Each timing has ten rotated fresh-process samples; the report includes CLI and inference, device forward and port maintenance. See [counts and samples](results.json), [training](train.py) and [paired execution](study.py).
