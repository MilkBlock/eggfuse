# A shared field-aware boundary pointer for higher Cells

The existing pointer pools similarities between every bound field and every candidate field. Bake can identify which positions carry the same variable through a query, a copy or a returned table instruction. In a graph whose first step reads A(x,y) and returns F(x), a later step reading F(v) and B(u,v) can compare A's first field with B's second field. The graph can span multiple Runs and several returned instructions. A mutable Set contributes its key positions. Union, mutable merge results and literal arguments introduce no guessed field identities. The compiled positions supply evidence for scoring; current versions and effective equality still go through the native verifier.

All 54,156 layouts use the same three learned coefficients. Each candidate receives the frozen pointer score plus a weighted sum of the minimum, mean and maximum 64-bit field-vector similarities at the wired positions. Every visible port of the required type is scored. On the two training programs, 22,679 sampled independent reads had both useful wiring and multiple candidate addresses. Training used Metal, one observed certificate per graph per program, teacher-forced earlier slots, and at most 15 sampled negative addresses per slot. Other valid certificates can exist. The 6,719 held layout hashes were excluded. The catalog contains 9,118 distinct slot wiring patterns including the empty pattern. [Training metadata](model/training.json)

## Conditional read quality

On a held layout with a recorded complete teacher certificate, start with its correct root. Let the reader fill each later independent slot using its own previous choices and the full visible typed domain. The table counts exact addresses agreeing with the recorded certificate. A different valid certificate may count as a miss here.

| Held layouts on training programs | Correct individual reads, old → field | All independent ports correct, old → field |
|---|---:|---:|
| sum-bits | 397 → 542 / 2,427 | 64 → 81 / 560 |
| dot-product | 332 → 478 / 1,686 | 41 → 63 / 399 |

## Native validation and test

The receipt policy, root Actor, recovery head, graph catalog, receiver, thresholds and seed match across arms. All independently valid bindings and all failed requests use the existing native logic. The paired validation programs improved the minimum recall and macro recall while pooled paid external packets per distinct signed commit fell. The predeclared program-level decision therefore selected the field reader. [Protocol](protocol.json) · [Locked selection](lock.json)

| Validation workload in assist | Signed reference commits, old → field | Paid external packets | Fully signed nonempty Runs |
|---|---:|---:|---:|
| affine-twins | 3,337 → 3,345 / 4,215 | 11,352 → 11,291 | 188 → 189 |
| gated-state | 4,448 → 4,490 / 6,118 | 14,005 → 14,098 | 200 → 205 |

Pooled signed EPT went from 0.21040 to 0.21182. The reader changed 3,134 of 7,193 routed choices on affine-twins and 4,297 of 9,046 on gated-state. In exclusive mode the source-aligned prefixes remained 14 and 10 Runs.

The locked window-laplacian test used the same EggCC rules and a separate input program. Native assist signed 5,536 / 8,005 reference commits (69.16%). Residual search supplied 2,469. The final state, ordered source execution and effective-operation ledger matched. The model signed 3,917 effective operations with 18,991 paid external requests (EPT 0.20626), covered every teacher submission on 243 / 541 nonempty Runs and completed five of 752 issued instances of held graph layouts. Its longest fully completed instance had nine rule occurrences. Only the selected reader ran on the test. In exclusive mode the model matched the first 13 Runs with zero independent search. It diverged on Run 14 and hit a source panic at Run 92. [Assist test audit](test/assist/window-laplacian.json) · [Exclusive test trajectory](test/exclusive/window-laplacian.json)

## Reproduction

Run from instruction_pointer in the configured MPS Python environment. ROOT, WEIGHTS, POLICY, RECOVERY, BIN and BAKE match the marginal-policy experiment. VALID is its program-held validation corpus, and BASELINE its uncalibrated deployed policy's assist audit directory. OUT is a fresh directory. All model, tape, program and wiring identities are recorded. Historical benchmark defaults remain available. Pass --field-reader to run the selected configuration.

~~~sh
PROTO=run-recall/field-wiring/protocol.json
python train_field_wiring.py "$ROOT" "$ROOT/sum" "$BAKE" "$PROTO" "$OUT/model"
python train_field_wiring.py "$ROOT" "$ROOT/sum" "$BAKE" "$PROTO" "$OUT/model" --audit-held
python layout_credit.py "$VALID" "$ROOT/sum" "$BIN" "$WEIGHTS" "$BAKE" "$OUT/validation" --cases affine-twins gated-state --omit --attach --run-recall --recovery "$RECOVERY" --policy "$POLICY" --field-reader "$OUT/model"
python field_reader_validation.py "$PROTO" "$VALID" "$BASELINE" "$OUT/validation" "$OUT/model" "$OUT/lock.json"
~~~

For the locked input, capture the protocol's pinned window-laplacian program with the same BIN, run native reference with --ept, and use a separate corpus manifest with seed 1731. Run layout_credit.py with that corpus, the locked model and --cases window-laplacian. Use separate output directories for assist and --exclusive.

## Residual search

Window-laplacian's exact reference recorded 10,084 residual candidate visits in the graph counter. Native assist recorded 10,067 total visits on the same counter, all in its residual exact calls. It avoided 17 candidate visits (0.17%), while signed commit coverage was 69.16%. The locked test was replayed after sharing the field encodings. Its per-Run signed counts, selected-port counters, graph completions, effective-operation ledger and final state matched the original field-reader audit. The two percentages have different denominators. The receiver can accept individual proofs and still call the ordinary matcher to establish whether additional bindings exist. [Source and candidate counts](test/search.json)

## Actual CPU inference and native receiver time on affine-twins

Each row below comes from four alternating-order comparisons in a single-threaded Python model process. Timings include loading the Actor and graph library, CPU inference, native verification, residual matching and IPC. The exact and teacher-oracle arms use the native executable. Each timed model execution must reproduce the audited issuance, final state and native counters. Signed EPS is signed effective operations per wall-clock second.

| Encoding lifetime | Original pointer median | Field pointer median | Original → field median signed EPS | Paired EPS wins for field | Exact / teacher-oracle median |
|---|---:|---:|---:|---:|---:|
| One encoding per read | 26.927 s | 33.092 s | 86.85 → 71.26 | 0/4 | 0.167 / 0.165 s |
| One encoding per used table in the sealed Run | 18.374 s | 18.644 s | 127.27 → 126.33 | 1/4 | 0.176 / 0.174 s |

Both pointers can share static-in-the-snapshot field bits and row keys. Typed port order, model weights, thresholds and the verifier stay fixed for this comparison. Shared encodings substantially reduced observed time for both arms. The field-aware scorer improved signed coverage and EPT on validation. It did not improve paired EPS against the equally cached baseline on this program. The full neural assist deployment remains much slower than native exact execution. [Per-read timing](timing-per-read.json) · [Shared-encoding timing](timing-shared.json)

To reproduce the shared run, create OUT/timing/original and OUT/timing/refit as links to the two validation audit directories. Invoke ripsat_density.py with VALID, ROOT/sum, BIN, WEIGHTS, BAKE, OUT/timing and the output JSON as positional arguments. Use --policy and --base-policy with POLICY, --base-bake with BAKE, --recovery-dir with RECOVERY, --field-reader with OUT/model, and --cases affine-twins. The per-read study used the graph reader before commit ed386e21.
