# Deferred typed requests at the cross-Run SubTuple port

The frozen four-producer library sends the verifier one signed integer guard and, on a recursive step, a checked predecessor length. All modes use the same four parent interfaces, recursive request inheritance, root encoding and CPU policy. Physical descriptor retirement is disabled throughout. The source graph still publishes each winning parent and executes the constructor arithmetic at its original ordinal.

At a true Spine publication, the Rust runtime captures its physical address, visible generation, integer port, producing root ordinal/serial and optional prior receipt. An unowned publication can invalidate the old generation at that address. The same native process validates the inherited arithmetic against the immutable published value. It dispatches the equality, greater-than or empty outcome and installs the allowable future child. A consumer reads the child at its original Run and checks the row generation again. This scope defers the verifier's conditional computation and maintenance of the continuation table. It does not defer the source RHS or require a separate service.

The immediate control resolves one event inline. The other controls use one queue with capacity 1, 8 or 32. Capacity triggers a drain. A second publication of the same address drains the pending prefix before appending the new event. The next source Run, a dependent same-Run search and program exit also drain pending events. The batch first validates every member against its immutable inherited input. Only after those checks pass does it mutate the continuation table in source order. A stale generation returns control to the ordinary proposal and exact verification path. The endpoint timer includes the final drain. It excludes the detailed receipt serialization and final graph export, consistently with the original native study.

The audit compares all three ordered sequences independently. The first covers every publication, including invalidations. The second covers true winning child/parent pairs with their source ordinals, physical addresses, versions, depth and computed integer. The third covers every applied root recipe, including roots outside the guarded family. Each arm is separately checked against the source RHS, effective writes, actual Spine resumes, unions and final graph. [Execution and barriers](higher.rs) · [Experiment](transaction_study.py)

## Full-pass evidence

The table gives complete resident inference medians from eight alternated samples per arm and seed. Publication counts include events that invalidate an old continuation. The request column counts events that actually evaluate the higher-order guard. The source graphs, parent identities and counts are the same under every batch limit. [Raw samples, batch histograms and identities](transactions.json) · [Executable and compiled Rust fingerprints](transaction-build.json)

| Program / seed | Published events / actual guard requests / winning children | Drains at 8 / 32 | Immediate / 1 / 8 / 32 (ms) |
|---|---:|---:|---:|
| sum-bits/1703 | 435 / 194 / 90 | 79 / 47 | 108.17 / 108.37 / 108.93 / 110.14 |
| sum-bits/1709 | 435 / 194 / 90 | 79 / 47 | 107.92 / 108.61 / 112.24 / 109.45 |
| dot-product/1703 | 267 / 100 / 44 | 40 / 21 | 106.89 / 108.31 / 108.04 / 107.36 |
| dot-product/1709 | 267 / 100 / 44 | 40 / 21 | 106.68 / 108.63 / 111.48 / 108.58 |
| gemm-bias-relu/1703 | 933 / 460 / 194 | 132 / 47 | 307.38 / 303.60 / 302.22 / 301.11 |
| gemm-bias-relu/1709 | 933 / 460 / 194 | 132 / 47 | 318.70 / 315.54 / 312.45 / 316.22 |
| stable-argmax/1703 | 453 / 218 / 95 | 64 / 25 | 102.89 / 103.34 / 104.20 / 105.73 |
| stable-argmax/1709 | 453 / 218 / 95 | 64 / 25 | 106.74 / 103.74 / 104.84 / 103.73 |

On sum-bits only one of 47 capacity-32 drains was full. The Run boundary triggered the other 46. Those drain groups averaged 4.13 actual guard computations. On GEMM, 17 of 47 drains reached capacity and each drain averaged 9.79 guard computations. The signed predicates themselves still execute once for every genuine request. Every captured publication/dependency order and all winning parent/child/recipe records matched immediate dispatch. Across all eight measurements the source triggered capacity and next-Run barriers. None exercised a repeated address within a batch, a dependent read before the next Run, or pending work at final exit.

On this ABI a queued native record occupies 192 bytes. An eight-entry buffer reserves 1,536 bytes. A 32-entry buffer reserves 6,144 bytes. These fixed allocation sizes exclude the common continuation map and audit streams. GEMM improved under both seeds, including the single-entry timing control. The small loads and stable-argmax show that simply grouping requests is insufficient for a general speedup. These timings use the pinned request-bearing Rust build. The sibling batch and the separately tuned multi-parent production engine use their own matched controls.

## Reproduce

Use the artifact variables from the main README.

```sh
python "$dir/build.py" "$e/NEW-transaction-build"
python "$dir/transaction_study.py" "$e/NEW-transaction-build/session" "$ref" "$families" "$caps" "$train" "$e/NEW-transaction-study"
python "$dir/verify_transactions.py"
```
