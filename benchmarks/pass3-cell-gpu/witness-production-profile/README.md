# Full-process sampling of trained CPU proposals

This experiment charges the standalone Rust Cell executor for an entire frozen eggcc Pass 3 graph. It compares the normal Cell binary with the joint-witness driver running frozen weights on the CPU. It uses the CLI allocator on all measured paths. Both process the source schedule, ordered effective mutations, Spine resumes, union and final graph. A separate full source audit also compares the identity and contents of individual winners and newly created physical Cells.

## Timing boundaries

In both binaries the reported inference interval begins immediately before `Executor::execute()` and ends when it returns. Graph construction (including copying the parsed program and importing initial facts), model and plan validation, export of the complete graph, graph hashing, result serialization and process teardown sit outside it. The resident API round-trip includes a fresh graph and model setup per request, final export, response and local Python JSON decoding. The cold benchmark additionally starts a fresh executable, parses the source program and waits for process exit. Final graph export is performed in all arms.

The native clock accumulates distinct source Run intervals for search, ordered RHS, repair, publication to query and Spine indexes, and delivery/GC. Outer schedule and source check/probe time can fall outside these intervals. The multi-parent instrument's frame, issue/seal and verification counts are *nested inside search*. The Apple sampler charges each main-thread sample once by the deepest identifiable execution owner, inclusive of allocator, hash and value operations invoked by that owner. Source inlining can attribute work to an enclosing symbol. CPU sample shares and wall-clock phase totals use separate denominators.

The optional production driver moves historical single-winner JSON records behind the audit switch. Source validation, root address/version checks, typed input comparison, serials, commit ordinals, recurrent decisions and physical ownership still execute. Set `archive_single_winners=true` for the former detailed history. Any request with `audit=true` always emits that history; counters remain available in all arms.

## Reproduction

Use fresh external directories for each invocation. The weights are the exported frozen tied projection, 10 bits and Hamming radius zero, seed 1703. The resident arm uses incremental two-parent routing and freshness pruning. The tuned arm uses the same packed lookup, one recurrent scoring row, batched single-parent root pages, verification mode 2 and checked slots. The request microbatch has width zero on the sampled tuned arm.

```sh
d=benchmarks/pass3-cell-gpu/witness-production-profile
e="$EGGFUSE_ARTIFACT_ROOT"
b="$e/compact-holdouts-20261121-v1"
v="$e/compact-vanilla-20261121"
w="$e/baked-port-packed-study-v1"
python "$d/sample_full.py" "$e/inc-neural-index-profile-v9/session" "$v/vanilla" "$b" "$w" "$e/NEW-samples" --tuned-rows "$e/request-transactions-v1/session"
python "$d/attribute.py" "$e/NEW-samples" "$e/NEW-sample-shares.json"
python "$d/build.py" "$e/NEW-production"
python "$d/study.py" "$e/inc-neural-index-profile-v9/session" "$e/NEW-production/session" "$v" "$b" "$w" "$e/NEW-production-study"
```

## Results

Six alternating resident samples per arm follow one warmup. Cold process times use three starts after any system file caches are warm. The source exact control executes in the same binary with its learned providers disabled. [Timings and evidence digests](results.json)

| Workload | Vanilla inference | Same-binary exact | Resident learned + winner archive | Resident learned, audit-only archive | API round-trip before → after | Cold vanilla / production |
|---|---:|---:|---:|---:|---:|---:|
| jacobi-1d | 113.2 | 113.3 | 405.0 | 389.6 | 501.1 → 442.4 | 307.2 / 591.0 |
| conjugate-gradient | 372.2 | 392.6 | 2072.7 | 2031.2 | 2335.9 → 2127.4 | 640.5 / 2303.4 |

Removing historical JSON avoided writing 18,147 Jacobi and 73,676 CG winner records per inference. Both endpoints still expose the original proofs in audited requests. On conjugate-gradient the feature/build difference with an exact source search was 20.4 ms, far below the learned route's 1.6 s premium. A warmed API request still imports the input graph, constructs plans, exports the graph and decodes its response.

| Native executor phase, ms | Jacobi same-build exact / production | CG same-build exact / production |
|---|---:|---:|
| Search | 49.5 / 330.8 | 169.1 / 1810.7 |
| Ordered RHS | 30.6 / 36.5 | 107.1 / 136.2 |
| Repair | 11.9 / 12.2 | 44.5 / 43.4 |
| Index/Spine publication | 19.8 / 9.1 | 68.4 / 35.2 |
| Delivery and GC | 0.8 / 0.8 | 3.6 / 4.1 |
| Initial graph plus executor creation, outside inference | 19.2 / 17.9 | 29.7 / 21.7 |
| Final graph export, outside inference | 22.2 / 21.8 | 51.0 / 49.5 |

The trained route's extra time is concentrated in proposing and verifying matches. On the two newer checked-slot and batched-row runs, 3,744/4,151 samples landed inside execute. Multi-parent routines accounted for 39.6%/40.0%, the single-parent generation routine and its still-inlined work for 27.2%/34.0%. Root binding accounted for 2.7%/1.7%. The larger inclusive sample scope for sealing multi-parent raw proposals was 4.5%/6.6%, including work inside the shared issuance stack. Rebuild consumed 4.0%/3.0% of the tuned samples and 11.4%/10.7% of vanilla samples. The large difference in percentages has different denominators; the wall-clock source repair times are very close. The same named single-parent generation routine also invokes the typed verifier; symbols inlined into it cannot be billed to scoring without a nested clock. [Exclusive sample counts, important inclusive scopes and symbols](samples.json)

The existing tuned driver also measures source-header and feature construction, actual single-parent scoring, single-parent token creation and sealing, then the three multi-parent costs. On Jacobi these six clocks read 7.98, 1.03, 12.88, 4.28, 90.22 and 41.00 ms. On conjugate gradient they read 40.13, 3.67, 63.21, 13.46, 459.52 and 174.42 ms. The native single-parent clock array has a fourth reserved field in this binary. The saved trial-level values skip it before pairing columns with the three multi-parent clocks. [Nested native clocks, four profiled samples](tuned-phases.json)

A second diagnostic build clocks the complete single-parent suffix verification and attachment loop, including proof setup, source checks, root binding and winner annotation. With the production audit-only archive and the original checked-slot row policy, this cost 78.30 / 456.55 ms on Jacobi / CG. Feature construction cost 7.99 / 39.04 ms, actual row-policy scoring 1.01 / 3.63 ms, and single-parent token formation plus sealing 12.78 / 62.96 ms. Multi-parent issuance plus sealing cost 92.88 / 466.48 ms, and exact multi-parent verification 39.97 / 167.11 ms. The unprofiled measurements above remain the speed comparisons. Use `build.py OUT --rows` then `phase_tuned.py OUT/session BUNDLES WEIGHTS FRESH_OUTPUT --verifier-clock` for this diagnostic. [Complete nested clocks](tuned-production-phases.json)
