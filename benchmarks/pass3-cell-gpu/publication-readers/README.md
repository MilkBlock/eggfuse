# Source publication readers under complete neural generation

This experiment uses the frozen two-view, typed-port Cell CPU provider, complete multi-parent generation and the ordinary source schedule. It compares against a separate default-feature Cell executable on the same eggcc source. The model, graph storage, all rule guards and RHS code stay common across neural arms. The measured change concerns subscription delivery after the source performs graph repair.

## Three separate readership contracts

1. The source table must notify each rule that can become dirty. Later source Runs consult this state to decide when to run the single- or multi-parent provider and when saturation has been reached. The original rule and set watermarks remain authoritative.
2. A legacy seminaive entry may additionally need the *individual changed physical witnesses*. A compiler-proved, installed, non-residual single-parent plan or a complete multi-parent plan supplies its own physical candidates. The executor checks that these exclusive normal queries return before the ordinary search path. A native probe reads its current source graph independently. An uncovered normal reader retains its original per-rule pending witness set.
3. A shared Entry node may have several subscribers. Even with learned generation, the winning single-parent token can resume Spine from the node's current delta packet. The compiler protects all rules with any possible Spine query port, including ports that become live in a later Run. It protects mixed nodes and explicit publication-owner nodes. Only nodes whose every subscriber is proved independent can be removed from table fanout. The existing dedicated-GPU entry-retirement routine already implements the shared-node condition. This experiment supplies its native CPU admission proof. Source repair, hash-consing, reverse equality edges, source row versions, original Spine publication and learned frame ChangeBatch notifications continue normally. [Admission and accounting](readers.rs) · [Integration](overlay.py)

QueryIndexes already constructs a column index on the first source query that needs it. Publication only obtains a writer for an existing index. The column/range/neighbour update counts therefore matter more than an estimate of what indexing every table might cost.

Each of the three source program plans has 582 rules, 1,562 distinct table-to-rule reader links, and 241 shared Entry nodes covering 580 rules. Rules 375 and 574 have empty premises and no table subscriptions. With this Entry plan enabled, every rule that could receive a changed table address already uses a shared entry. The pure legacy-pending retirement should therefore save zero address copies. [Source contracts and schedule census](contract.json) · [Static extractor](static_readers.py)

The source schedule has eight conservative sequencing regions when the optimizer keeps each repeating or saturating subtree as a single region. Of 582 rules, 530 can still run in the penultimate region. This limits the usefulness of retiring whole rules solely by their last syntactic region. The region census does not skip schedule work in the benchmark.

## Runtime controls

The observed control keeps the original delivery policy and records table wake cardinalities. The pending arm removes only certified private-address recipients. The entries arm removes only exclusive shared-node subscriptions. The combined arm applies both. The masks arm compiles a bitset of readers per table and unions masks from all tables that have a real Wake before waking source rules. ReadySets implements wake as setting source-order positions, so different notification orders do not reorder the source schedule. Source-address consumers receive the same original changed physical addresses. The graph-wide semantic checks also cover probes, ordered writes and actual Spine resumes. Counters are gathered in independent audited runs. [Paired experiment](bench.py)

## Which assumed costs are still present?

The same instrumented executable first runs ordinary exact search and checks its complete source trajectory against the independent vanilla process. In a separately reset executor it runs the frozen learned issuer. No graph maintenance counter is inferred by subtracting elapsed times. [Cases, physical identities and timings](readers.json)

| Source | Exact column / range / neighbour row updates | Exact publication row reads | Learned publication row reads / headers | Legacy witness insertions omitted | Cold node visits removed | Remaining real Entry notifications |
|---|---:|---:|---:|---:|---:|---:|
| sum-bits | 5,271 / 0 / 161 | 4,335 | 0 / 6,676 | 0 | 569 | 3,793 |
| dot-product | 4,410 / 0 / 523 | 3,893 | 0 / 6,225 | 0 | 514 | 2,968 |
| deriche | 444,736 / 1,680 / 214,601 | 397,279 | 0 / 501,614 | 0 | 1,728 | 353,953 |

The baseline learned configuration had zero column, range and neighbour row updates on all three programs, before this experiment changed any reader. For Deriche, ordinary exact search built 104 column indexes. Learned execution built zero and still received the 501,614 change headers required by other subscribers. Removing 82 table-to-node subscriptions saved 1,728 cold node visits, while 353,953 actual Entry address notifications survived. The CPU reader proof protects 239 rules with possible future Spine readers.

| Source | Rule-reader visits / distinct per-batch recipients / actual clean-to-dirty transitions | Vanilla / learned original / observed / pending / entries / combined / masks (ms) |
|---|---:|---:|
| sum-bits | 19,239 / 17,405 / 7,074 | 20.89 / 33.25 / 31.85 / 31.91 / 31.88 / 31.87 / 31.87 |
| dot-product | 14,103 / 12,737 / 5,535 | 17.84 / 30.21 / 29.78 / 29.13 / 29.87 / 29.22 / 29.67 |
| deriche | 82,989 / 76,616 / 30,227 | 1621.67 / 3881.85 / 3858.23 / 3765.63 / 3801.22 / 3777.78 / 3882.98 |

Sampling uses four rotating resident samples per arm after warm-up. Deriche completed all 635,818 source RHS ordinals. The original learned timings contain medians of 2,945.5 ms for search, 572.9 ms for RHS, 168.3 ms for repair, 161.0 ms for query publication and 33.6 ms for delivery plus GC. An arm that removed zero address copies also had a lower inference median than the original learned run. These differences do not support an end-to-end speedup claim from retiring addresses. The actual work eliminated at this layer was limited to cold dispatch and duplicate readiness visits. [Build fingerprint](reader-build.json)

## Testing only genuine readiness transitions

A rule that was already dirty needs no second source wake before its next legal read. The clean-mask arm initializes a second bitmap from the actual source flags. The two instructions that consume a seminaive rule and clear its source flag also mark it clean in this bitmap. After the changed-table reader masks have been united, the executor intersects them with the clean bitmap. Only those selected rules change state and set a bit in the original ReadySets. Each audited delivery and final exit checks the bitmap against every original source flag. The clean-only control preserves all ordinary graph subscriptions and changes just readiness delivery. The full clean arm also applies the previously proved exclusive Entry and private pending cuts. [Native change](clean.py) · [Instrumented build](clean-build.json)

The independent clock separately measures Spine publication, shared Entry publication, learned frame change notification, ordinary column/range/neighbour maintenance and Sieve, source dirty delivery, change-buffer clear and garbage collection. Each clocked request generates the reference graph. Three samples per configuration are excluded from the normal interleaved timing matrix. The equality inventory is a final audit scan. It counts graph records whose equality subscription set is already empty without deleting or redirecting any of them.

| Source | Already-dirty probes omitted | Original learned / table masks / clean masks / clean only / independent vanilla (ms) |
|---|---:|---:|
| sum-bits | 10,331 | 34.25 / 33.36 / 34.15 / 33.93 / 21.80 |
| dot-product | 7,202 | 32.89 / 33.30 / 31.73 / 32.44 / 19.85 |
| deriche | 46,389 | 3804.65 / 3783.79 / 3800.09 / 3787.13 / 1570.98 |

Deriche’s whole-source result included 635,818 RHS bindings, 265,407 effective writes and 112,378 independently audited Spine events. The neural root and nested cells retained 450,414 of 452,913 direct fresh physical identities. Compiling true readiness transitions avoided 46,389 checks, but saved only about 0.20 ms in the isolated source-delivery clock. The full-pass observations do not support introducing the second bitmap as a default speed improvement. [Root, stage and phase evidence](clean.json)

| Source / observed control | Spine publication | Shared Entry | Learned frame changes | Exact indexes and Sieve | Dirty delivery | Clear change buffer | Garbage collection |
|---|---:|---:|---:|---:|---:|---:|---:|
| sum-bits / observed | 1.231 | 0.225 | 0.268 | 0.037 | 0.095 | 0.031 | 0.097 |
| sum-bits / clean | 1.353 | 0.228 | 0.275 | 0.047 | 0.078 | 0.033 | 0.100 |
| dot-product / observed | 1.063 | 0.192 | 0.236 | 0.046 | 0.086 | 0.032 | 0.103 |
| dot-product / clean | 0.976 | 0.181 | 0.233 | 0.038 | 0.068 | 0.033 | 0.101 |
| deriche / observed | 104.979 | 21.956 | 25.324 | 0.287 | 0.885 | 0.178 | 31.145 |
| deriche / clean | 113.368 | 23.053 | 26.572 | 0.366 | 0.686 | 0.199 | 33.060 |

The times above are milliseconds. On Deriche the measured source Spine publisher installed 451,688 anchors from 451,718 distinct keys. The live-cursor publisher checked 357,532 changed addresses for retirement. These required native consumers and the learned frame notifier account for substantially more time than dispatch of ordinary exact indexes. Their actual work remains charged in each whole-pass arm.

| Source | Actual hot Entry insertions | Distinct changed addresses receiving those insertions within a batch | Repeated insertion into another hot node | Retired owners with empty equality subscriptions / all owner records |
|---|---:|---:|---:|---:|
| sum-bits | 3,793 | 3,235 | 558 | 994 / 5,039 |
| dot-product | 2,968 | 2,676 | 292 | 541 / 4,798 |
| deriche | 353,953 | 335,767 | 18,186 | 49,880 / 213,546 |

The hot-node audit checks actual pending membership before the native insertion. On Deriche, 18,186 of 353,953 accepted hot Entry insertions wrote a second copy of the same changed address in the same batch. Three siblings were hot at the maximum. This is a work-count ceiling for that specific form of sharing. The physical addresses may still serve different later source Runs. The equality inventory found 49,880 empty retired owner records alongside 446,700 recorded equality edges. The experiment retained both sets of structures. The sparse engine already avoids empty equality records by construction.

## Reproduction

All results use the frozen 1703 checkpoint and a complete two-view producer on the original external Deriche bundle. The ordinary exact run on the same instrumented binary verifies its full trajectory against the separately compiled default-feature reference. Timed requests omit the detailed ownership and graph inventory. Setup, export and request round-trip samples are archived alongside native inference. The selective phases use separate runs.

```sh
dir=benchmarks/pass3-cell-gpu/publication-readers
e="$EGGFUSE_ARTIFACT_ROOT"
python "$dir/build.py" "$e/NEW-publication-readers"
python "$dir/bench.py" "$e/NEW-publication-readers/session" "$e" "$e/extra-pass3-transfer-v1" "$e/NEW-reader-study"
python "$dir/build_clean.py" "$e/NEW-publication-clean"
python "$dir/bench.py" "$e/NEW-publication-clean/session" "$e" "$e/extra-pass3-transfer-v1" "$e/NEW-clean-study" --arms original masks clean clean-only
python "$dir/verify.py"
```
