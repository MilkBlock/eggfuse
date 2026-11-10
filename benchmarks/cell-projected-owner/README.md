# Publish completed Cell projections through their original owner

This is an implementation and work-count check in the standalone Cell CPU
runtime, against `bf03e824`. It does not measure native egglog throughput or
establish a speedup. The 2× objective and general egraph sparsity remain unproved.

## Opportunity and takeover

The previous [actual-history admission](../cell-history-admission/README.md)
selected join `(3, 2, 5)` from real completed executions. Its consumer rule 137
needs two producer-rule-143 results: a query witness and a constructor result.
Neither is dead. The compiler already describes the entire consumer output as
a static projection, but retaining it allocated another `Rc<Trail>` containing
an empty local Results array, the donor owner and the compiled layout.

`ResultFrame` now carries that donor and layout directly when there are no local
slots and every projected slot is inherited. `ResultView` supplies the logical
consumer's ResultPort identity while reading the existing donor. History,
pending publication, Shared Entry and local query witnesses all use this view;
there is no new per-producer consumer list, binding copy or fact graph.
Mixed local/inherited results retain their existing owner. Deeper histories
store frame handles, including their logical projection, rather than losing
that identity when carrying or trimming stages.

Repeated complete projections still use the compiler's composed layouts; they
do not build a chain of per-instance wrappers. Ordinary partial inheritance
without a valid composed mapping retains its original recapture fallback.
Actual returned references, receipt forwarding/visibility checks, original Run
publication boundaries and empty-stage offsets remain authoritative. A view is
not a cached value or proof that a retired constructor remains live.

## Measured work and new costs

The same source and candidate program hashes as the earlier experiment are
used. `round0-before` / `round0-after` run the uncombined catalog; `before-normal`
/ `after-normal` run the identical combined catalog on frozen old/new binaries.
All four executions retain the same final state and 1,428 ordered Runs.

| Combined sum-bits | Before | After |
|---|---:|---:|
| History owner/container allocations | 534 | 369 |
| Direct Cell completions | 165 | 165 |
| Joint result-frame creations | 369 | 369 |
| Joint query-witness reads / writes | 311 / 311 | 311 / 311 |
| Key queries | 18,759 | 18,759 |
| Constructor requests | 11,569 | 11,569 |

The 165 removed owner allocations are real removed calls to `Rc::new`, not
logical matches relabeled as mutations. All other 676 checked integer work
counters are unchanged. The uncombined catalog's checked work is unchanged.
The original 370 query and 205 constructor-request savings belong to the join,
not to this change. They are not counted again.

This representation has a material cost on the tested 64-bit target:

| Inline record | Before bytes | After bytes |
|---|---:|---:|
| History handle | 16 | 24 |
| Completion record | 184 | 192 |
| Query winner | 288 | 296 |
| Cell Entry record | 184 | 192 |
| Legacy route record | 176 | 184 |

Each nonempty projected history also owns a reference to its shared layout;
cloning that history clones that reference. Deeper-history array elements grow
from 8 to 16 bytes. Final reachable history owners decrease from 143 to 136,
saving 560 bytes of owner payload plus estimated Rc headers; result-array bytes
remain 4,352. That census excludes inline Cursor/Entry storage and therefore is
**not a total-memory improvement claim**. No new liveness cache was introduced.

One new Bake round, still trying just the same single ranked candidate, passes
its ordered audits and uses the exact measured candidate in the next round.
Its equal-weight score rises from 2,603 to 2,768 solely because of the removed
allocations. That score does not price the larger handles, reference counting,
cache effects or latency. It cannot admit a speedup on its own.

## Checks

- 94 sparse runtime unit tests and 79 default runtime unit tests pass. These
  include 101 composed permutations retaining the original owner, differently
  named ResultPorts, foreign witnesses, published donor sharing, empty stages,
  deeper retention, retirement of the last owner and partial-inheritance
  fallback. The two new history tests exercise lifecycle and identity, not
  merely a new counter.
- 30 compiler/runtime integration tests pass across `ripsat_completion`,
  `state_inheritance`, `joint_results`, `entry_publications`, `query_receipts`.
  The direct-completion fixtures compare every Run's graph and ordered inputs,
  writes and resumes while actually taking the optimized path.
- The sum-bits Bake replay preserves all five stored graph/schedule/ordered
  effect hashes. Final-state native choice acceptance passes through
  `choice_diagnosis.py`, using saved native exports and these new runtime states.
- The `--audit-stages` old/new comparison also agrees, but disables the compiled
  publication path; it is explicitly an additional fallback-path check.
- `--no-default-features` compile and README compile/run/bench commands pass.
  The README bench uses one repetition as a smoke check, not a performance
  campaign. No Raytrace timing was launched.

## Reproduction

Use fresh output directories. Freeze the old runtime from `bf03e824`, and the
new runtime from this change, with the same command:

```sh
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime
```

The saved input artifacts are the same as the preceding admission experiment:
`out/queued-union-admission/program.json` and its `round-0/catalog.json`.
To reconstruct the uncombined program, replace `iterative_bake` with that
round-0 catalog and recompute the artifact checksum. The collector verifies
both artifact identities; merely using a similar program does not reproduce
these numbers. Run both binaries on both programs with `--local-congruence`.
Run the combined old/new pair separately with `--audit-stages` for the fallback
check. The reviewable result is [results.json](results.json).

```sh
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo test --locked -p eggfuse-cell-runtime --lib
cargo check --locked -p eggfuse-cell-runtime --no-default-features
cargo test --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells,view-ports --test ripsat_completion --test state_inheritance --test joint_results --test entry_publications --test query_receipts
cargo run --locked -p eggfuse-cell-compiler --features iterative-bake,sparse-cells -- iterate --program out/terminal-union-seed.json --output out/cell-projected-owner/iteration --objective ripsat-completion --score measured-work --rounds 1 --trial-limit 1 --local-congruence true
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-projected-owner/semantic out/cell-projected-owner/semantic-acceptance.json
cargo cell-compile --case sum-bits --output out/cell-projected-owner/readme-program
cargo cell-run --program out/cell-projected-owner/readme-program/program.json --output out/cell-projected-owner/readme-run
cargo cell-bench --program out/cell-projected-owner/readme-program/program.json --repeat 1
python3 benchmarks/cell-projected-owner/check.py out/cell-projected-owner benchmarks/cell-projected-owner/results.json
```

`build-identity.json` records the baseline commit, common feature list and new
runtime source hashes. The collector checks that it is running against that
source, binds semantic acceptance to the new exports, and records binary/log
hashes. Build directories, binaries and generated programs remain untracked.

The next admission must account for the handle growth across *all* entries,
including uncombined Cells. Do not expand the catalog on the strength of this
allocation counter alone. The remaining 369 producer result frames and their
311 query captures still provide live evidence; removing them requires reusing
an existing instance owner, not dropping the evidence.
