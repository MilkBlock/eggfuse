# Cell domains replace optional constructor birth hints

The installed catalog already proves complete constructor candidate enumeration
through shared template wiring and native/boundary ports for covered tables with
at least one equality input. These rows also retained a second, immutable
birth-hash candidate index. Unlike scalar-key tables, they do not require that
index for completeness. A scheduled Run switch does not invalidate their static
wiring; current equality, liveness, visibility and pending collision ordering
still must be checked. No new closure is inferred from observed value equality.

`Graph::use_port_domains_only()` is an explicit compression option. It requires
settled, complete port coverage, removes existing covered hint entries once, and
reclaims the resulting hash capacity. Subsequent covered births and retirements
skip hint membership maintenance. Both coordinator and borrowed query readers
skip hint lookup and use their existing exact port-domain path. Uncovered
canonical indexes remain. There is no replacement runtime reverse list, fact
copy, template catalog or binding table. The default retains hints.

The lookup count is now recorded independently of hint probes; otherwise turning
off an accelerator would incorrectly look like eliminated logical queries.

## Actual standalone Cell runtime evidence

Same baked sum-bits artifact, inherited owners and completion binding retirement:

| Metric | Hints | Domains only |
| --- | ---: | ---: |
| Covered birth-indexed facts | 2,847 | 0 |
| Constructor index requested bytes | 102,408 | 1,608 |
| Entire Graph requested heap | 2,784,981 | 2,684,181 |
| Retained Program heap | 117,230,752 | 117,230,752 |
| Process execution/transfer peak | 125,480,739 | 125,379,947 |
| Port-key lookups | 11,063 | 11,063 |
| Exact candidate checks | 12,174 | 16,972 |
| Hint probes | 11,053 | 0 |
| Port-domain probes | 4,720 | 11,063 |

This removes 100,800 bytes and a duplicate membership-maintenance path. Candidate
checks increase by 4,798. No timing improvement is claimed; this remains optional
because the memory/query-work tradeoff is real. Birth hash calculation is still
present. Facts and committed RHS mutations do not decrease. This does not meet
the requested large saturated-Cell compression and RHS completion goal.

All 1,428 saved source-Run graph and ordered RHS/write/resume hashes pass, as do
exact final-state comparison and semantic acceptance using the equal saved export.
The mutation counters are unchanged. Runtime library tests: 148; ownership
integration tests: 37, including explicit domains-only serial/two-worker union,
delete and reconstruction. Default runtime Cargo check passes. Measurements are
requested heap, not RSS; this is the standalone Cell runtime, not native egglog.

The next useful Bake contribution is to limit the extra port-domain candidate
work with checked local wiring or existing completed witnesses. Reintroducing
another per-node hash/consumer directory would undo this takeover.

```sh
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_closure_work -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/original-baseline.json out/cell-structural-compression/domain-only-audit.json --natural --shared-owners --parent-takeover --port-domains-only
CARGO_INCREMENTAL=0 CARGO_TARGET_DIR=$PWD/target cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,iterative-bake,storage-metrics --example runtime_storage_peak -- out/cell-structural-compression/closure-existing/program.json out/cell-structural-compression/domain-only-heap.json inherited-owners --port-domains-only
python3 benchmarks/cell-structural-compression/analyze_domain_only.py out/cell-structural-compression/completion-all-writers-audit.json out/cell-structural-compression/domain-only-audit.json out/cell-structural-compression/completion-all-writers-heap.json out/cell-structural-compression/domain-only-heap.json benchmarks/cell-structural-compression/domain-only-results.json
```
