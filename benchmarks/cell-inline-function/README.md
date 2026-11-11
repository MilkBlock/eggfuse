# Inline function results through Cell publication

Control: `b47330c8`. This changes the actual standalone Cell CPU path, not
native egglog. It removes intermediate receipt storage, not a source rule,
logical match, function update or publication. No new throughput result is
claimed; the complete 2x and computational-locality objectives remain open.

## Opportunity and remaining obligations

The preceding complete execution profile attributed 46.81% of query time to
`Expr-size` and observed 790,076 unchanged single writes in that family. This
does not justify dropping their completions: an unchanged write can still be
the final source-ordered publisher, replacing another producer's continuation.
Live histories, new entry assumptions and mutable-result validation remain
authoritative. Reusing an old Entry at RHS time without accounting for pending
writers would not establish the same winner. That shortcut was not implemented.

The existing Cell output layout does prove a simpler redundancy: a single
actual function receipt, with one retained Entry-owned output, has no need for
a separate arena slot. Previously the receipt was copied from `SingleEffect`
to `cell_outputs`, then read and cleared at publication. Its table/operation
already live in the shared template; its producer already lives in Completion.

Completion now carries one of three output sources: arena offset, shared-history
mask, or actual function index. Removing the duplicate producer field leaves
this representation the same size. A lone function receipt stays inline from
RHS completion through publication. There is no extra binding, subscriber list,
fact graph, cache or per-rule catalog. Larger function indices retain the arena
path rather than truncate; multi-output and existing result frames retain their
shared spans.

Publication still runs after the legal completion boundary, resolves receipt
forwarding, checks visibility and chooses the last publisher in original order.
Mutable/deletable boundaries retain the previous path. Cursor/history capture,
source selection and all graph effects remain unchanged. This is not yet a
cross-Run block switch or a proof that an unchanged match can be skipped.

## Bounded work comparison

Both lanes use the same frozen programs, repair ports, Entry publication and
four query workers. The control exports are the aligned diagnostics under
`out/cell-prefix-configuration`; intervening commits did not change production
runtime behavior. The collector checks exact final graphs, all ordered Run
records, graph effect counts, query counts and Entry maintenance counts.

| Work, before → after | sum-bits | Raytrace first 1,280 Runs |
|---|---:|---:|
| Receipt copies into output storage | 957 → 358 | 59,311 → 34,979 |
| Allocated logical output positions | 5,827 → 5,228 | 296,507 → 272,175 |
| Output-array/history slot reads | 5,827 → 5,228 | 296,507 → 272,175 |
| Inline receipt deliveries | 0 → 599 | 0 → 24,332 |
| Table queries | 12,085 → 12,085 | 578,591 → 578,591 |
| Actual anchor publications | 6,588 → 6,588 | 295,161 → 295,161 |
| Completion record bytes | 104 → 104 | 104 → 104 |

The removed arena operations refer to the **same receipts** and must not be
counted as three independent eliminated publications. Each still incurs an
inline receipt read, forwarding, candidate selection and visibility validation.
There is also output-source dispatch and one producer read from the existing
Completion phase. No allocator or latency improvement is inferred from these
counters. Peak arena positions change from 44,177 to 42,909 on the prefix;
sum-bits remains 196. Short Raytrace runs do not cover the late attribute-update
hotspot seen in the complete profile.

## Validation and reproduction

- 96 runtime unit tests; ordinary Entry/port completion tests and scoped tests.
- Entry tests with transfer auditing compare ordered RHS, committed-write and
  resume-root digests, plus Run snapshots. New cases cover duplicate unchanged
  writes, post-union function forwarding, late consumers, deletion/recreation.
- A scoped regression checks that the inline function output is delivered only
  once while an unrelated Cell's outputs remain pending. Native runs the small
  fixtures too. The source does not require postponing ordered function effects.
- The seven query-receipt tests preserve learned mutable-receipt histories.
- Existing sum-bits semantic acceptance passes unchanged. Raytrace has only the
  bounded relative comparison, not a new native/full-workload proof.
- Minimal and all-feature checks, and README compile/run/bench repeat 1 pass.
  The bench is a smoke check, excluded from speed claims.

The scoped survivor-epoch regression previously expected a duplicate collision
to refresh an unchanged row from epoch 0 to 1. The unmodified `b47330c8` control
fails that assertion too. It is corrected to require epoch 0 in both global and
deferred completion, consistent with the earlier collision-delta fix. Production
epoch behavior is unchanged by this patch.

```sh
cargo test --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports --lib
cargo test --release --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test entry_publications --test query_receipts --test port_completion --test scoped_completion --test collision_delta
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
PREFIX out/cell-fixed-reads/sum-program.json ROOT/sum 2000 4 64 canonical --repair-ports --entry-publications
PREFIX out/cell-fixed-reads/ray-program.json ROOT/ray1280 1280 4 64 canonical --repair-ports --entry-publications
python3 benchmarks/marker-handoff/choice_diagnosis.py ROOT/semantic ROOT/semantic-acceptance.json
python3 benchmarks/cell-inline-function/collect.py ROOT benchmarks/cell-inline-function/results.json
```

Use fresh outputs. `ROOT/semantic` reuses the reviewed native exports and points
`run-values` to the new sum-bits export. Preserve the compiled binary and helper
as `ROOT/runtime` and `ROOT/prefix`; the collector records their hashes. Saved
exports and binaries remain ignored; reproducible sources and compact counts
are tracked.
