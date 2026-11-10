# Baked Cell completion

This measures the actual standalone Cell CPU path against merge `718259bc`,
not native egglog performance. `check.py` runs full short sum-bits and only the
first 128 source Runs of Raytrace. It does not time either workload.

The compiler rechecks result-switch v4 and emits the native Cell egraph report.
Positive constructor graphs share alpha-normalized structures; unsupported
normalization retains exact ordered source contracts. Direct execution uses a
checked actual-result projection, including an inherited query anchor. A Set
whose output is already proved equal needs no new union. Effects not covered
by that proof retain their source execution.

The first useful short check (`initial-checks.json`) passes exact parsed graph
equality and all Run metadata against the merge, with workers off and four
workers. Saved native sum-bits exports also pass the required choice diagnosis.
JSON object serialization order differs between Cargo feature combinations;
the checker compares all parsed fields and retains both file and canonical
object hashes. It excludes no graph data.

| Sum-bits work | Merge | Completion |
|---|---:|---:|
| Direct completed applications | 0 | 165 |
| Ordinary handoff attempts | 592 | 262 |
| Effect slots initialized | 11,324 | 10,829 |
| Effect slot probes | 12,569 | 12,239 |
| History allocations | 663 | 663 |
| Constructor/union effects | unchanged | unchanged |

Added work is explicit: 2,692 completion-plan probes, 223 layout checks,
633 receipt checks, 165 boundary reads and 22 inherited history reads.
58 applications fail receipt validation and retain the normal path. These
counts are not a speed claim and do not establish a positive net work score.
The 128-Run Raytrace prefix reaches none of the three selected direct states;
it pays 2,876 unsuccessful plan probes. A whole-workload benefit is unproven.

The regression tests additionally compare every source Run's graph, ordered
RHS inputs, writes and resumptions on the optimized configuration. They cover
foreign constructor returns, an intervening union, repeated completion with
permuted layouts, a no-op constructor Set, deletion fallback and forged proofs.
A separate 101-transition test retains the original slot allocation and a
single ancestor owner; it performs no runtime map composition.

```sh
python3 benchmarks/ripsat-cell-completion/check.py COMPILER BASELINE_PREFIX CANDIDATE_PREFIX SUM_PROGRAM RAY_PROGRAM SAVED_NATIVE_EXPORTS NEW_OUTPUT
```

The baseline prefix binary is frozen from `718259bc`. Build all binaries before
collecting work. The initial candidate includes the compiler's optional
transfer-audit hooks (inactive); use separately built normal runtime binaries
for a subsequent speed campaign. See [the plan](../../docs/RIPSAT_CELL_COMPLETION.md)
for remaining scope and acceptance requirements.
