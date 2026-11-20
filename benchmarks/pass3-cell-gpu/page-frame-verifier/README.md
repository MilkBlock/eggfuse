# Using the original neural page as a source verification receipt

The frozen signed single-parent policy, 256 KiB incremental typed port index and multi-parent issuer run on one Rust Cell CPU executor. The network supplies ordered source addresses for every link in a page before the verifier reads a parent. The stock page path calls Graph::row on each attempted parent. A prior flat verifier accepted frame offsets under a different packet encoding and could not be enabled with the production page. This experiment passes the frame actually used to generate the current page. Every positive run uses the same frozen checkpoint and original source schedule. Vanilla runs in a separate default-feature Rust process. The covered workloads are real eggcc Pass 3 programs. [Pinned build](build.py) · [Oracle, ablations and error controls](bench.py)

## Source authority and exact plan

1. An offset is a hint into an immutable Rc frame. The verifier checks table identity and generation, bounds, physical source address and generation of the chosen row. The frame value is authoritative only if its union stamp matches the current graph. Otherwise the verifier explicitly reads that parent from the current source table and checks its version before use. The source-only arm applies the ordinary full lookup. Both paths run the exact typed LHS extension, suffix, delta eligibility, ordered RHS, writes, Spine and rebuild.
2. Adjacent tuples may share the first verified parent prefix inside a page. The key contains the exact physical address, row version and position. Reusing a successful prefix keeps its slot bindings and witnesses; a failed first parent rejects another identical prefix. Each positive tuple still gets the original page serial, later parents, source suffix and root. [Bounded verifier](kernel.rs)
3. The compiler already guarantees that sealed plans finish every neural pointer selection before entering the deterministic suffix. No later pointer can consume latents published by a successful suffix lookup or primitive. The tail arm keeps the exact computation and binding and skips writing those dead latent features.
4. Under the same immutable graph borrow, the exact matched page and typed suffix certify the present source rows. The receipt arm checks the original advertised version against the selected physical row at matching time, then reuses that verification at root binding. It checks the source Run, rule, template, layout identity, receipt address and version, availability of each required typed input, and retains the owned slot values for original source commit. The rejection tests perturb the offset, frame generation, parent version, root template, root version and withholding of the root. [Root binding](seal.rs)

## Direct frame reads and shared prefixes

The first ablation has six alternating resident samples per arm. All arms match the complete ordered RHS, effective writes, actual Spine resumes, union sequence, schedule and final graph. Within each program the experiment also compares the raw learned tuple digest, root choice digest, both providers' actual winners, committed parent references, source root IDs, nested physical IDs and the single-parent decision digest. At least 98% of fresh physical Cells retain a direct learned source. [Full counts, faults and samples](frames.json)

| Source | Original graph parent reads | Exact frame reads | Reads forced by intervening union | Consecutive first-parent prefix hits | Vanilla / production / frame / frame + prefix (ms) |
|---|---:|---:|---:|---:|---:|
| sum-bits | 21,808 | 15,533 | 6,275 | 3,174 | 22.36 / 34.40 / 35.50 / 35.54 |
| dot-product | 30,280 | 19,645 | 10,635 | 5,249 | 18.91 / 34.69 / 34.23 / 34.46 |
| jacobi-1d | 322,119 | 197,797 | 124,322 | 71,531 | 115.40 / 242.36 / 237.10 / 245.17 |
| conjugate-gradient | 1,822,658 | 966,757 | 855,901 | 563,575 | 343.10 / 1022.85 / 1016.49 / 1014.77 |

A graph row can already be cached. The physical Cell fact decoder ran exactly 2,623, 1,196, 13,133 and 38,979 times respectively in production and in the direct frame arm. Measured decoding savings are zero. Reduced parent lookups and repeated prefix checks alone did not consistently speed up the complete pass.

## Sharing the exact root proof with the deterministic suffix

| Source | Useless latent publications skipped | Successfully sealed page roots | Parent versions / projected field types spared a second graph query | Vanilla / production / tail only / receipt only / both (ms) |
|---|---:|---:|---:|---:|
| sum-bits | 2,019 | 4,588 | 10,198 / 27,637 | 22.13 / 34.87 / 34.76 / 34.96 / 35.03 |
| dot-product | 7,835 | 3,805 | 9,173 / 24,264 | 18.40 / 33.07 / 33.10 / 32.95 / 33.30 |
| jacobi-1d | 36,642 | 23,172 | 55,224 / 143,002 | 118.76 / 245.05 / 242.31 / 235.52 / 235.01 |
| conjugate-gradient | 73,122 | 57,695 | 133,269 / 339,316 | 364.57 / 1048.10 / 1040.43 / 1029.69 / 1032.69 |

Each remaining parent version is proved directly or by a frame with a valid union stamp. Sharing the proof reduces the repeated source lookups at root binding. The exact integer and table suffix remains authoritative. [Matched six-sample ablation](seals.json)

## Retaining the original parent page through source commit

The checked-slot root binder can own a Vec of copied parent references or retain the original immutable page and a slot index. The retained variant checks the physical parents at the same source point. The source commit and detailed archive can still access the complete ordered reference slice without cloning it. Taking a lease prolongs the lifetime of the complete page, including its other tuples. The experiment did not measure peak live pages or RSS. [Parent reference representation](parent_refs.rs) · [Eight-sample paired results](loans.json)

The issuer can also read a source version from the exact frame that produced its chosen address when table and union generations still match. It records an explicit source lookup for an older union frame and keeps the original page format. Every chosen address and version generated the identical raw issue digest.

| Source | Parent refs supplied by lease | Issuer frame reads / source lookups | Vanilla / production / copy / retained page / retained + issuer frame (ms) |
|---|---:|---:|---:|
| sum-bits | 10,198 | 16,151 / 6,870 | 21.73 / 34.68 / 34.18 / 34.47 / 35.18 |
| dot-product | 9,173 | 20,251 / 11,045 | 18.83 / 33.64 / 32.19 / 32.74 / 33.27 |
| jacobi-1d | 55,224 | 228,675 / 156,848 | 110.28 / 235.58 / 225.93 / 223.78 / 228.04 |
| conjugate-gradient | 133,269 | 1,424,518 / 1,302,761 | 357.02 / 1002.41 / 1000.24 / 1049.95 / 1043.57 |

The retained parent page helped Jacobi in this pairing and slowed conjugate-gradient. An earlier diagnostic allowed the bound root to release the exact reference list after validation when auditing was disabled. It retained source serial, template and owned slot values and kept full parent history in the audit run. That diagnostic did not keep a separately rereadable parent proof in production. Its timings are archived separately from the retained-page experiment. [Release diagnostic](released.json)

## Keeping audit-only anchor vectors out of the issuing path

The page and typed known rows already carry stable addresses into the source commit. Once every parent has been picked, the auxiliary anchors Vec is read only by the detailed multi-witness ticket archive. The compact arm allocates it during audit and omits it for ordinary production execution. Full audits still retain every physical parent. [Audit and production counter pairs](compact.json)

| Source | Production anchor lists / reference copies omitted | Vanilla / production / page loan / compact / compact + issuer frame (ms) |
|---|---:|---:|
| sum-bits | 8,471 / 18,943 | 21.77 / 36.10 / 34.44 / 34.49 / 34.97 |
| dot-product | 10,564 / 26,900 | 19.02 / 33.85 / 33.47 / 34.33 / 33.06 |
| jacobi-1d | 71,622 / 205,611 | 111.91 / 241.36 / 236.51 / 235.33 / 234.78 |
| conjugate-gradient | 189,604 / 496,983 | 373.81 / 1033.89 / 1030.45 / 1032.94 / 1042.30 |

The integrity checks operate on genuine physical addresses. On both small sources, shifting the offset, invalidating the frame generation or changing a parent version prevented the corresponding tuples from rebuilding the reference graph. A wrong root template, wrong root version and a withheld root failed the allocator’s mandatory ownership check. Source version fallback after a legitimate intervening union is counted on the positive paths. The fault controls do not use it to repair damaged hints.

## Reproduction

Both larger holdouts and the two original inputs use the frozen 1703 checkpoint and the original signed/typed production policy. These data do not establish sensitivity to a second model seed. The protected physical epochs and source semantics are independent of that checkpoint. The endpoint clock includes the entire native Pass 3 inference, including remaining searches, publications and graph repair. Final export takes place afterward. Timings from different matrices have their own interleaved production and vanilla controls. [Executable and installed-source fingerprints](builds.json)

```sh
dir=benchmarks/pass3-cell-gpu/page-frame-verifier
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/build.py" "$e/NEW-page-reader"
python "$dir/bench.py" "$e/NEW-page-reader/session" "$e" "$e/NEW-page-reader-comparison" --arms production source frame prefix frame-prefix
python "$dir/bench.py" "$e/NEW-page-reader/session" "$e" "$e/NEW-page-tail-comparison" --arms production tail receipt tail-receipt borrowed-receipt compact-issued
python "$dir/verify.py"
```
