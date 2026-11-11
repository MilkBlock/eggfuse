# Parameterized union ports in direct Cell completion

Control: `b756e96e`'s v4 completion policy, rebuilt with the candidate to isolate
v4/v5 behavior. Scope: **standalone Cell CPU**, not native egglog. This is an
opt-in executable experiment, not a speedup or a completed 2x result.

## Opportunity and implemented takeover

The preceding maintenance checkpoint established no stable incremental speed
gain. Structural sparsity alone does not bound query, publication or boundary
cost. The proposed LazyUnion representation instead asks whether different
external constructor shapes can share the same small equality interface.

The existing direct completion could project witnessed constructor results,
but rejected a terminal RHS containing Union or a constructor Set that required
new equality. The fallback reconstructed temporary RHS values, validated each
constructor key again, and recorded each effect before history/publication.
Actual completed Cell paths and typed query/effect operands already provide
the proofs needed to avoid part of that work.

`bake-cell-completion --lazy-unions true` emits result-switch v5:

- A union operand addresses either an existing matched input slot or an actual
  retained constructor-result port. Copy/static aliases resolve during Bake.
  The external constructor opcode does not occur in the union program; equality
  sorts, source assumptions and actual witnesses remain in the checked Cell.
- Explicit Union and the constructor Set form used by source lowering both
  compile to ordered operand pairs. Their original queue/ownership accounting
  remains distinct. Repeated same-stage constructor uses can inherit an already
  proved historical donor; no producer/operation address is invented.
- A pending Set retains the constructor's old result in the symbolic pre-commit
  state. Its requested result becomes equal only at the source boundary. This
  prevents an earlier queued union from proving a later RHS constructor lookup.
- After the normal match and receipt validation, direct completion projects the
  existing result owner and queues the parameterized equalities. It skips
  `result_inputs`, the temporary RHS frame, repeated constructor/full-key
  handoffs, result assignments and intermediate receipt stores on that path.
  Results continue through the existing history and publication layout.
- Identical union programs share one immutable allocation across completion
  plans even when their constructor contexts differ. Different entry contracts
  are not merged into one semantic eclass. Existing and observed iterative Bake
  retain v5 when their input program selected it. v1–v4 reconstruction is kept.

The runtime creates no LazyUnion graph fact, consumer list, private union queue
or per-instance RHS operation log. It borrows the existing inputs/results and
uses the ordinary ordered queue. Any number of admitted union pairs is supported;
the existing result-layout limits still bound optional direct completion.

## Live obligations and limits

All required constructors must already have a valid donor in the supported
single-owner result layout. Source matches, residual/delta ownership, actual
returned witnesses, lifetime, visibility, source Run/effect ordering and normal
repair remain authoritative. Deletable tables retain the original path. Missing
or invisible receipts cannot justify skipping an RHS.

This implementation generalizes the executable completion over external equality
operands. It does **not** yet generalize the structural normalizer across a
nonterminal pending union, compile an arbitrary external repair neighborhood,
or establish full domination equivalence after erasing constructor assumptions.
The existing internal congruence/repair machinery still processes committed
unions. Parameterized code sharing alone does not prove that work removable.

## Actual work

Frozen ordinary query-prefix executable, four query workers, grain 64, canonical
storage, repair ports, Entry publication and absorption. This is a work/semantic
check; no elapsed-time comparison was performed. All values are retained in
[results.json](results.json).

| Small fixture | v4 | v5 |
|---|---:|---:|
| Direct union states | 0 | 1 |
| Actual Cell completions with union | 0 | 4 |
| Point queries | 38 | 33 |
| Old handoff attempts | 8 | 0 |
| Temporary effect slots initialized | 32 | 20 |
| New union input/result reads | 0 / 0 | 4 / 12 |
| Direct layout/witness checks | 0 / 0 | 4 / 12 |
| Direct boundary reads | 0 | 12 |
| Decoded rows | 12 | 13 |

Constructor requests, function updates, union requests/commits and created facts
are equal. Completed Cells are not committed-mutation counts. The new input and
result acquisition is charged in Work credit; union requests were already
charged and coverage is not rewarded again. Result acquisition can decode a
row. An optional shared-program handle enlarges each compiled completion plan;
`Catalog::completion_storage()` reports unique union-program payload/owner bytes
and the enlarged direct-plan storage. These are logical storage counts, not
allocator/RSS measurements. This fixture does not establish a net equal-weight
work or latency win from the selected decreases alone.

Complete sum-bits and the first 128 Raytrace Runs each compile three union states,
sharing one union program. Total direct states rise from three to seven, but
**neither workload execution completes a union Cell through the new path**.
Point queries stay 12,085 and 74,265 respectively. Sum-bits adds 14 layout checks,
28 witness checks and 18 projection comparisons; witness fallbacks rise 40→54.
These are additional costs, not gains. The short Raytrace window does not bound
later workload coverage. Do not promote v5 or enlarge the catalog on these data.

The sum candidates include the existing `Get`/`Single`/`SubTuple` equality rule.
The next investigation must distinguish missing retained results from invisible
or retired results at those failed transitions, using their actual source
slots. A larger structural normalizer is not justified as the immediate fix for
a missing runtime witness. New templates should be selected only when their
proofs discharge substantial remaining work and survive the required boundary.

Follow-up: [Cell result sealing](../cell-result-sealing/README.md) identifies the
14 new failures as populated references to retired constructors. Updating a
fresh unique frame at its first publication enables five actual union completions
on the same sum-bits input. That later implementation has separately charged
costs and does not replace this initial zero-coverage result or establish speed.

## Validation and reproduction

- 101 runtime unit tests and 44 compiler/unit/integration tests pass. Minimal
  no-default-feature compilation and README compile/run/bench (repeat 1) pass;
  the latter are command smoke checks, not throughput evidence.
- Runtime unit tests cover actual shared union-program allocation and preserve
  alias incidence/effect order across distinct constructor contexts.
- Integration checks compare every Run snapshot and ordered inputs/writes/resumes
  with v4 for one to three equality effects, explicit Union, constructor Set,
  foreign constructor results and parent congruence. Native egglog executes the
  fixture checks. Deletion/recreation stays on the original path; a negative
  case requires a fresh constructor before a queued Set commits.
- Forged operand wiring is rejected by reconstruction from the original typed
  operations. Iterative re-emission preserves the selected v5 policy.
- Saved workload comparisons require exact final states, all ordered Run fields
  and actual graph effects. The unchanged sum-bits native choice entrypoint
  returns `pass` / exit 0. Raytrace is a short relative regression check, not an
  independent native or full-workload proof.

Use fresh output directories. Build/freeze the compiler, the fixture emitter and
the `query_prefix` executable before running the collector:

```sh
cargo build --release --locked -p eggfuse-cell-compiler --features iterative-bake,cell-absorption,view-ports --bin eggfuse-cell-compiler --example emit_lazy_union
cargo build --release --locked -p eggfuse-cell-runtime --features cell-absorption,view-ports --example query_prefix
target/release/examples/emit_lazy_union ROOT/fixture
python3 benchmarks/lazy-union-ports/check.py COMPILER QUERY_PREFIX ROOT/fixture/program.json SUM_PROGRAM RAY_PROGRAM SAVED_SEMANTIC ROOT/checks
```

The saved short-run artifacts/binaries are in `out/lazy-union-ports`. Program,
binary, state and report hashes are recorded; generated binaries and exports
are not tracked. The normal five-implementation timing cadence is unchanged.
