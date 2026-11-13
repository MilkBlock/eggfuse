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
