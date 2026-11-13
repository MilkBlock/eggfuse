# Compile actual original-source witnesses into worker continuation

The previous four-worker audit admitted 709/976 composed Cells on the original
1,428-Run source but retained all 14,653 generic constructor queries. The audited
round-one observation already contains 408 constructor-witness recipes across
69 rules. The composition selector retained the fragment language but did not
install these witness routes. Another observation or larger fragment budget
cannot fix that missing connection.

`bake_observed_witnesses` checks both source and exact installed-catalog identity,
requires completed audited Runs, preserves existing recipes, and loads the
extended program through the ordinary typed compiler. Shapes and transitions
must remain identical. Observations authorize no equality or effects. The
existing key proof, exact comparison of unproved candidates, actual returned
witnesses, visibility, forwarding and source generation checks remain live.
This uses existing Cell/query bindings and shared static routes; no runtime
producer lists, extra fact graph or result representation is introduced.

The intended removal is a real generic constructor query when an existing
witness is accepted, including inside worker prefixes. Route selection, candidate
checks, lifecycle work and extra result retention must be charged. The direct
result replaces that query; misses retain the ordinary path. Ordinary residual
matching and all Run/effect boundaries remain authoritative. No speed or coverage
claim is made merely by producing the catalog; actual execution follows.

Job 327 passes the source/catalog rejection test and compiles all 408 recipes
against the exact audited round-one catalog, preserving every composition shape
and transition. Job 329 uses the frozen merged runtime `437d1e7c` with four
workers. It rechecks the saved baseline binary/input/command and decompressed
stage hashes, then compares the newly executed artifact against all 1,428 source
Run snapshots, ordered binding sequences, Run summaries and logical effects.
All agree, and its fresh final state has the reviewed native-accepted hash.
No new native contract or table exclusion is introduced.

Generic constructor lookups fall **14,653→14,373**: 268 are removed in workers
(6,514→6,246), and 12 on the source path. Worker key fields remain 12,575;
composition hits remain 709, result joins 49, source prefix Entry reads 1,263,
and cumulative result-buffer capacity 37,968 bytes. Additional worker route
work is 3,510 attempts, 2,758 anchor reads, 1,511 map probes, 951 operation checks,
768 candidates and 787 lifecycle checks. Only 19 of the 268 accepted worker
witnesses have a static key proof. These new costs prevent treating the lookup
reduction alone as a speedup.

The reproduction helper can now reuse the exact saved baseline audit and check
one newly installed witness artifact. It hashes the saved compressed snapshots
and checks the current runtime, program, flags, bindings and accepted final state
before reuse. It still requires fresh full snapshots and ordered bindings from
the candidate. Runtime source order, residual enumeration and effects are not
inferred from equal counts alone.

```sh
eggfuse-job run --kind compute -- cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells --example bake_observed_witnesses -- ROUND1_PROGRAM ROUND1_AUDITED_TRACE OUTPUT
eggfuse-job run --kind compute -- python3 benchmarks/cell-bake-owner-merge/original_worker_audit.py REPO MERGE_ARTIFACTS ORIGINAL_COMPOSITION CHECK_OUTPUT --witness-program OUTPUT/program.json --reuse-baseline MERGE_ARTIFACTS/original-workers
```

## Timing does not pass the speed gate

Job 335 compares only the catalog change using the **same frozen runtime** and
source. Nine measured samples plus one warmup per lane, all control before all
candidate, with 44 clear process-boundary guards. Inference medians are
**21.743→21.815 ms (+0.33%)**: no demonstrated speed benefit. The worker/source
lookup savings above are real, but their replacement work must be counted.
Load medians rise **98.712→122.797 ms**, and process wall medians rise
158.697→186.021 ms. Typed route construction is paid during runtime program load;
it cannot be called free offline Bake. `original_witness_timing.py` preserves
this distinction and binds every sample to the accepted state, schedule,
logical effects and expected actual lookup count. The installed catalog remains
an opt-in experiment, not a new default or a claimed performance win.

Source-side route selection additionally performs 558 map probes and 39
alternative checks for its 12 accepted witnesses; the saved queries must not be
credited again through composition hits. The original-source integration is
useful coverage evidence, but expanding this catalog without reducing its
selection/validation work would amplify the wrong cost.

## Raytrace confirmation is still slower

A separate predetermined confirmation (job 334) reuses the exact pre-merge and
merged binaries from job 320. Five samples each for sum-bits and Raytrace;
whole control before whole candidate, 56 clear guards. Sum-bits is
22.025→21.977 ms (−0.22%); Raytrace is **4.666472→4.821128 s (+3.31%)**.
All five merged Raytrace samples (4.713–4.909 s) exceed all five control samples
(4.657–4.703 s). This does not reproduce the earlier 8.47% magnitude, but does
reproduce the slower direction; do not dismiss the regression as one outlier.

The runtime merge changes only context-admission preparation, Program loading
and optional completed-owner transfer. Both timed artifacts have an admitted
context policy, so they still take the compiled-context branch. The ordinary
runtime does not call the completed-owner transfer API. In the original saved
trial, residual worker execution medians were 0.785→0.796 s, while RHS and
query-index update grew more substantially. Aggregate graph/ownership/stable-port/
maintenance counters match exactly. This narrows the audit away from a newly
added worker synchronization path, but does not prove a cause: program allocation
lifetimes and generated-code layout remain untested possibilities.

Full samples, binary/input hashes, work counts and acceptance provenance are in
`original-witness-results.json`. The original `aef89181` performance reference
remains pinned. No full parallel-completion or saturated-Cell speed claim is
made by this iteration.
