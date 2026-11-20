# Figure 54 — CPU Set layout and who subscribes to its members

This runs the actual source-ordered Rust Cell CPU engine on the complete eggcc load-after-write workload and the explicit observer/union controls from figure 36. The implementation is an isolated checkout of 3cf9cd5d with the native Set ABI specialized to flat sets of e-class handles. Identical source bindings, effective writes, Spine resumes, union/birth events and final typed graph are checked against the original native runtime. The source matcher is deterministic here. No neural RHS credit is assigned for changing storage or subscriptions.

The one-word layout admits 63 raw identities in a shared member dictionary. Segmented values store ordered (segment index, nonzero word) pairs and visit those segments for binary operations. The sparse alternative stores a sorted vector of raw member ids. Raw value keys remain immutable while indexed. Union forwards admitted dictionary slots. At canonicalization, masks merge forwarded bits and vectors normalize/sort/deduplicate native ids. A failed single-mask capacity check returns an error and cannot silently switch layouts.

Row subscriptions use the original reverse-dependency graph. Instance subscriptions intern equal normalized shared sets as one membership group. A class subscribes groups and a group holds the rows that read it. A union redirects the displaced class's groups and wakes the union of their readers at the normal source rebuild barrier. Changed row keys, intern collisions, lengths and source-visible writes are still repaired. This is grouping by identical Set membership, not arbitrary Cell ownership. A separate diagnostic counts actual displaced rows from the original graph and verifies the same notification count in the group path. Teardown measures the group directory allocations.

## Actual source

| Input | Source Runs / RHS | Helper Runs / helper RHS | Primitive activity |
| --- | ---:| ---:| --- |
| Original full eggcc memory test | 835 / 382 | 4 / 4 | No ExprSet primitive executes |
| Same full schedule with explicit observer terms | 835 / 390 | 4 / 12 | 1 insert, 2 intersections, 2 unions, 3 lengths |
| Memory-only source | 39 / 111 | 9 / 5 | No ExprSet primitive executes |
| Memory-only source with observers | 39 / 119 | 9 / 13 | Same primitive counts as the full observer case |

The complete observer workload took 2.89–3.07 ms across the six arms. Its original schedule has no set-member union pressure, so it does not support a claim of a production throughput gain. The dynamic union control really changes a previously written length from 2 to 1 at the same key under min merge. The no-merge control rejects the conflicting value in all six arms. The separate cross-segment compiled algebra fixture uses 128 identities and checks union, intersection, difference and insertion lengths before and after a real class merge. Its two snapshots are [4,1,1,3] and [3,2,0,3] for both larger layouts and both subscription modes.

## Controlled fanout and density

Nine generated programs vary the total identity population, members per shared set and number of reader rows. Pool singleton facts ensure a sparse set in a large population really consumes the declared number of identities. Readers all observe the shared set; a source union aliases its first and last members. The counters and timing include native index maintenance and rebuild.

| Universe / members / readers | Layout | Row / shared-set ms | Row / shared-set peak requested heap B |
| --- | --- | ---:| ---:|
| 16 / 2 / 512 | mask | 2.967 / 2.982 | 7,091,011 / 7,168,355 |
| 63 / 63 / 128 | mask | 3.006 / 2.304 | 3,604,774 / 3,264,158 |
| 63 / 63 / 128 | segments | 3.002 / 2.287 | 3,607,846 / 3,267,230 |
| 128 / 2 / 128 | sparse | 0.931 / 0.986 | 4,199,324 / 4,294,196 |
| 128 / 64 / 128 | segments | 3.069 / 2.300 | 4,734,513 / 4,429,617 |
| 256 / 128 / 128 | segments | 5.455 / 3.949 | 7,701,144 / 7,026,848 |
| 256 / 128 / 128 | sparse | 5.350 / 3.874 | 7,817,288 / 7,142,992 |

For 63 members and 128 readers the shared path needs two group notifications and still wakes the same 130 actual affected rows as the ordinary path, including the extra shared/pool records. The change reduces the work of maintaining repeated member subscriptions, not the number of observable result rows. Above 63 identities the single-mask runs fail as expected and are excluded from timing. The segmented representation need not win against the sorted vector; for this 256-member-population case with 128 members in a set, the sparse vector's shared version was slightly faster. The choice of grouping matters more here than the choice between those two encodings.

Successful arms compare all Run outcomes and final state to an independently built native engine. Ordered timing rotations cover six equal-domain lanes below the capacity boundary, and four above it. Fresh-process CLI samples and inference medians are recorded separately. A counted System allocator measures total requested heap in separate native passes. Process maximum RSS, creation counts, live/peak Set payload, set-member dictionary and subscription-directory teardown are also recorded. The positive-allocation-growth counter includes increases in requested heap during realloc, not all bytes copied. Row-side member registrations count submitted member ids; the independent wake audit counts *actual affected rows*. [Raw timings and memory](results.json) · [Union wake audit](wake-results.json) · [Multi-segment algebra](algebra-results.json)

## Reproduction

    dir=benchmarks/pass3-cell-gpu/set-representations
    mkdir -p "$OUT/source"
    git archive 3cf9cd5d | tar -xf - -C "$OUT/source"
    python "$dir/prepare.py" "$OUT/source"
    CARGO_TARGET_DIR="$OUT/target" cargo build --release --locked --manifest-path "$OUT/source/Cargo.toml" -p eggfuse-cell-runtime --features slot-transfer-audit --bin eggfuse-cell-runtime --example set_repr_heap
    cpu="$OUT/target/release/eggfuse-cell-runtime"
    reference="$SET_SOURCES/audited-runtime"
    python "$dir/fixtures.py" "$CARGO_TARGET_DIR/release/eggfuse-cell-compiler" "$OUT/fixtures"
    python "$dir/study.py" "$cpu" "$OUT/target/release/examples/set_repr_heap" "$reference" "$SET_SOURCES" "$OUT/fixtures" "$OUT/paired"
    python "$dir/wake.py" "$cpu" "$SET_SOURCES" "$OUT/fixtures" "$OUT/paired" "$OUT/wake"
    python "$dir/algebra.py" "$CARGO_TARGET_DIR/release/eggfuse-cell-compiler" "$reference" "$cpu" "$OUT/algebra"

SET_SOURCES is the archived set-memory-reproduction experiment directory. Keep outputs on the external workspace volume.
