# Mixed result slots: work and storage checks

This experiment measures the standalone Cell CPU on the frozen sum-bits program.
It does not measure native egglog execution speed. Source rule matches and RHS
requests are not counted as committed graph mutations.

`slot-inheritance-check.json` records 13 exporting states (eight mixed), work
changes, program/binary hashes and semantic acceptance. `slot-storage-check.json`
records the separate storage comparison. Neither file contains timing results.
The 88-byte reference is the earlier mixed-frame representation reconstructed
with `frame88-reference.patch`, plus the reporting-only storage census. It is
not the historical fastest runtime. The frozen `575faa4d` runtime remains the
semantic baseline used by the work check.

## Reproduce

Use separate Cargo target directories for production and reference kernels.
Build the production kernel by itself, so compiler feature unification does not
add diagnostic runtime features:

```sh
CARGO_TARGET_DIR=/private/tmp/cell-slot-runtime cargo build --locked --release -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
CARGO_TARGET_DIR=/private/tmp/cell-slot-tools cargo build --locked --release -p eggfuse-cell-compiler --features iterative-bake --example bake_state_plan --example compare_work
```

Invoke `run_slot_inheritance.py` with a fresh output directory and these inputs:

- `--baseline`: frozen ordinary-release `575faa4d` binary.
- `--runtime`: newly built ordinary-release kernel.
- `--program`: frozen `out/cell-state-timing/program-old.json` input from the
  earlier state-plan timing experiment (input hash is in the saved check).
- `--emitter`, `--ledger`: the two compiler examples built above.
- `--native-reference`: the native semantic fixture directory containing
  `native-source.json`, `native-marked.json`, and `sum/`.

The script rebakes selected and all-materialized v2 artifacts, executes all
three lanes, checks every Run and final state, charges new costs, and invokes
`benchmarks/marker-handoff/choice_diagnosis.py`. Output directories must not
already exist. The materialized control disables inheritance provenance marks.

For the uncompressed representation, make an isolated checkout of the commit
containing this document, apply `frame88-reference.patch` **only there**, and
build its ordinary kernel using a separate target directory. Execute the exact
selected `program.json` emitted above with `--local-congruence`. Compare:

```sh
python3 benchmarks/cell-unification/compare_slot_storage.py --root PATH_TO_WORK_CHECK --reference PATH_TO_FRAME88_RUN --output PATH_TO_STORAGE_CHECK
```

The census deduplicates shared owner/layout pointers, includes retained leaf
parents and array capacities, and estimates Rc headers as two machine words.
The combined total replaces the referenced layout subset with all compiled
layouts, including those currently unused. Allocator rounding, transient or
unpublished cursors, program JSON, effect descriptors and unrelated graph data
are outside this specific total. Effect descriptor storage is reported
separately; it remains 6,376 bytes in this comparison.

## Result and limits

| Metric | Uncompressed mixed frame | Compact mixed frame | Compact materialized |
|---|---:|---:|---:|
| Result frame bytes | 88 | 56 | 56 |
| Published owner count (including parents) | 155 | 155 | 139 |
| Compiled shared layouts | 8 | 4 | 4 |
| Published storage + all layouts, bytes | 25,328 | 19,480 | 18,200 |

The compression reduces the measured scope by 23.1%. Inheritance still costs
1,280 bytes over compact materialization. It eliminates 195 capture reads and
195 stores, but adds 232 marks and 71 indirect reads; the equal-weight ledger
is not a time model. Reducing inline capacity raises spill events against the
uncompressed mixed representation (258 to 392), despite the lower byte total.
The source checks and 1,428 Runs agree; native semantic acceptance passes.

Runtime history tests cover missing local slots, bit 63, published snapshots,
parent lifetime and deduplication, and a 300-stage inherited chain with one leaf
owner. Compiler tests cover deletion, intervening unions and forged contracts;
state tests also pass with all hashes forced to collide. V1 artifacts remain
accepted and produce the same final state and Run sequence.
