# Baking a request schedule from training programs

This experiment selects one of three execution orders for each compiler-proved, read-only multi-parent verification suffix. The actions execute each instance immediately, share an eight-packet cache while keeping each instance immediate, or delay up to eight sealed packets and execute the same instruction for all lanes. All actions retain the same neural witnesses, original graph, ordered commits, and source visibility.

Four training families are separate from the evaluated workloads. One CPU profiler times verification beginning after independent parent proposals have been sealed. Every arm reads the same frozen checkpoint and program, and the capture rotates the order of the arms. For each unique normalized query, effects, seminaive mode and independent pointer ordering, compare the median costs for each training program. A mode is admitted only with at least three training programs reaching 20 microseconds of accumulated verification time, at least three program-level wins above 3 percent and a median improvement above 8 percent. The thresholds are fixed before held-out policy evaluation. Unseen or unselected templates use immediate verification. The actual runtime accepts a schedule only when it is compatible with the current program digest, proved request grammar and complete coverage of the rule ordinal space.

Evaluation uses the held-out original source executables, the same two static alternatives and the serialized offline schedule on complete Rust CPU Pass 3. Equal ordered request outcomes, including negative lookups, match the immediate verifier. Every proposed binding and every directly allocated fresh Cell is audited. Held-out timing is independent of profiler labels.

```sh
python benchmarks/pass3-cell-gpu/transaction-admission/build.py "$EXP/admission"
python benchmarks/pass3-cell-gpu/transaction-admission/study.py "$EXP/admission/session" "$EXP/vanilla" "$EXP/bundles" "$EXP/lookup" "$EXP/repair-bake-families-20261120" "$EXP/admission-study"
python benchmarks/pass3-cell-gpu/transaction-admission/verify.py "$EXP/admission-study"
```

## Frozen seed 1703 results

One of 79 observed templates passed the four-family admission threshold. It selected deferred width eight. On separate genuine executions it admitted 141, 193, 952 and 2,328 validated parent lanes on the four evaluation programs. The other templates took the original path.

| Workload | Vanilla | Immediate | Learned admission (ms) |
|---|---:|---:|---:|
| sum-bits | 23.14 | 41.13 | 41.91 |
| dot-product | 19.36 | 41.11 | 40.68 |
| jacobi-1d | 122.37 | 330.48 | 325.94 |
| conjugate-gradient | 372.03 | 1450.63 | 1496.23 |

The runtime did execute the learned decision. The end-to-end speed advantage did not replicate across all workloads. Source-mismatched, incomplete and unproved schedules failed closed. [Training labels](training.json) · [Held-out samples](heldout.json)
