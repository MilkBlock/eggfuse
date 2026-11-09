# Rebuilding intermediate runtime candidates

The intermediate candidates were measured before final integration. These
runtime-only patches retain their source without introducing experiment flags
into the production query loop. They add `ownership_queries.rs` as well as
changing existing files; tests and compiler CLI changes are not needed to build
these runtime executables.

| Candidate | Clean base commit | Patch |
| --- | --- | --- |
| columns | `d03b69e9` | `columns.patch` |
| typed | `ff5e6bc4` | `typed.patch` |
| marker | `ff5e6bc4` | `marker.patch` |
| absence (rejected) | `ff5e6bc4` | `absence.patch` |

All patches pass `git apply --cached --check` against their specified base
trees in independent temporary indexes. In an isolated checkout of that base,
apply the corresponding patch and build:

```sh
cargo build --release --locked -j 2 -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
```

Use the same rustc, machine, artifact and command arguments recorded in the
measurement metadata. Source paths and compiler versions can affect binary
hashes. The reported hashes identify the actual frozen measured executables.
No allocator or audit features belong in the normal timing build.

The absence patch also includes its parent-epoch unit test and compiler-runtime
regressions. Its incoming-edge bitmap proof was correct under the checked
monotone-equality contract, but timing rejected the added runtime work. The main
worktree does not retain that bitmap or negative-lookup fast path.
