# Source continuation from a sealed constructor witness

Scope: **standalone Cell CPU runtime**, not native egglog performance.
Control: `bde30d99`. The complete ownership/parallel-execution objective remains
in [the refactor checklist](../../docs/CELL_EXECUTION_REFACTOR.md).

The preceding actual Raytrace execution moved 556,868 constructor lookups out of
the ordered RHS, but source validation still performed 1,027,684 key-field
comparisons and reconstructed each current key. The worker had already matched
these exact keys. More speculative queries would not remove that repeated work.

The checked preparation plan already restricts keys to immutable captured inputs,
their safe scalar descendants and validated aliases. The existing source-Run
union certificate proves whether their canonical interpretation can have changed.
An unchanged certificate plus a live, visible, original constructor witness in a
ready table therefore permits reading its actual result without rebuilding or
comparing its key. Ordinary RHS execution and constructor-only prefixes both
consume this proof at the original source instruction.

The result reader preserves the existing precedence: stable result port, cached
decoded result, then the producer recipe's result operand. It never reconstructs
the other fields. The returned constructor can belong to another Cell. A source
snapshot miss still requires ordinary resolution; no speculative Eq is assigned.

Actual union invalidates the old certificate. Hidden/deleted facts, receipt
forwarding, dirty tables, or unavailable certificates keep the original exact-key
validation and same-key lookup fallback. The original snapshot certificate
travels with suspended execution; a later current generation cannot certify old
inputs. Source ordering, queued union timing, completion, Run visibility and
publication are unchanged. No new per-instance version, binding, fact graph,
consumer index or result buffer is introduced.

This is a smaller ordered constructor boundary, not independently scheduled
parked execution or concurrent shared writes. It does not authorize crossing a
source Run before its scheduled occurrence. The next Bake opportunity remains
eliminating already-covered or weakly reusable probes and then using proven
completion/entry wiring to remove additional shared boundaries.

## Accounting and acceptance

[results.json](results.json) records complete sum-bits and Raytrace executions.
Both final exports are byte-identical to the control; all 1,428 / 16,883 ordered
Run summaries agree. Native sum-bits acceptance is `pass`, exit 0. All prior
graph statistics except the intentionally removed validation-field work agree.

| Work | sum-bits | Raytrace |
|---|---:|---:|
| Source witnesses returning only the result | 2,874 | 556,868 |
| Validation field comparisons, before → after | 5,250 → 0 | 1,027,684 → 0 |
| Source key fields no longer materialized | 5,250 | 1,027,684 |
| Certificate probes | 2,874 | 557,955 |
| Lifecycle probes | 2,874 | 557,955 |
| Invalid witnesses retaining source fallback | 0 | 1,087 |
| Total key lookups, unchanged | 14,478 | 4,050,662 |
| Net saved equally weighted operations | −3,372 | −645,094 |

All actual speculative lookup counts and source acceptance/rejection counts
are unchanged. The 144-byte instance and 456-byte RHS owner are unchanged, as
are the compiled-plan payload sizes. These workload rows were already cached,
so full-row decode counters do not decrease. The removed work is source key
construction and comparison, not an invented additional row-decode saving.

`cell-constructor-preparation/v2` reports certificate probes, lifecycle probes,
result-only reads, accepted sealed witnesses and omitted source key fields.
Existing acceptance/rejection counts still cover both sealed and exact-key
validation. Successful matches, sealed coverage and omitted fields earn no extra
work credit. Speculative queries remain charged in total lookup counts.

The work ledger conservatively charges the new path's certificate/lifecycle
probes and result-only reads separately. Its equal weights are not calibrated
latencies; previous cached result extraction and source key construction were
not individually metered. The ledger alone cannot establish a speedup. There is
no new timing campaign at this checkpoint.

[check.py](check.py) compares all final-state bytes and ordered Run summaries,
all prior graph work except the replaced validation-field counter, unchanged
speculation and lookup counts, and unchanged instance/owner/compiled-plan sizes.
It checks the exact conservation of removed field comparisons and selected key
widths. Native sum-bits acceptance uses saved exports with the reviewed
`choice_diagnosis.py` contract. Raytrace remains a full regression comparison
against the control, not an extended native semantic contract.

126 runtime unit checks and 93 compiler/integration checks pass. The latter
force hash/Sieve collisions and cover stable and canonical reads, ordinary and
constructor-prefix execution, foreign returns, source deletion, union, partial
publication and every Run's graph in focused fixtures. All-feature and
no-default-feature compilation pass. The first saved-native acceptance attempt
was `inconclusive` because the artifact setup used nonexistent nested filenames;
the missing-input result is retained. Linking the documented flat native exports
then passes without changing the validator or proof rules.
The README Cargo compile/run commands and repeat-1 bench smoke also pass.
Constructor preparation remains opt-in under experimental Cell execution.

## Reproduction

Use fresh output directories, the same frozen sum/Ray program hashes as the
control, and retain the feature runtime before README commands rebuild defaults.

```sh
cargo test --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication --lib
CELL_CPU_HASH_BITS=0 CELL_CPU_SIEVE_COLLISIONS=1 cargo test --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --lib --test cell_execution --test closed_aliases --test entry_publications --test joint_results --test parallel_residuals --test query_workers --test ripsat_completion --test scoped_completion
cargo check --release --locked -j1 -p eggfuse-cell-runtime --all-features
cargo check --release --locked -j1 -p eggfuse-cell-runtime --no-default-features
cargo build --release --locked -j1 -p eggfuse-cell-runtime --features cell-absorption,view-ports,parallel-publication
ROOT/runtime --program PROGRAM --output ROOT/CASE --repair-ports --entry-publications --cell-absorption --query-workers 4 --parallel-residuals --parallel-publication --cell-execution-grain 1
cargo run --release --locked -j1 -p eggfuse-cell-compiler --features cell-absorption,view-ports,parallel-publication,iterative-bake --example compare_work -- PRIOR/CASE/report.json ROOT/CASE/report.json ROOT/CASE-work.json
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-constructor-certificate/check.py ROOT PRIOR RESULTS.json
```
