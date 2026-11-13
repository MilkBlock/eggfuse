# Selected Cursor scalar writes

This experiment measures the actual standalone Cell CPU runtime. The control
is `23d55e65`, including the cross-stage wiring merge. It does not measure native
egglog inference speed or a separate simulator.

The previous frozen Raytrace execution had 577,650 resumed Cell steps, but a
selected Cursor excluded every binding in a scalar-write batch from the existing
worker-owned write path. The same run already committed scalar rows on workers
for 840,367 root candidates. The opportunity is to reuse the selected Cell's
existing continuation for those same typed writes, rather than interpreting its
single RHS effect on the coordinator. These counts identify available execution
evidence; they are not the new path's coverage or a speedup.

The independent early/late profiles of the previous `50e3822a` CPU-instrumented
binary found coordinator stacks in RHS execution, function writes and boundary
resolution as well as query and publication work. They are bounded wall-residence
samples, not CPU percentages. See `out/cell-inference-cpu/profile-{early,late}` and
the committed CPU diagnostic in `benchmarks/cell-inference-cpu`.

## Existing proof and remaining obligations

The compiler's existing single-write plan supplies the input projection, optional
scalar prefix and supported old/min/max merge. A selected origin token supplies
the actual matched cross-stage continuation. The original Cursor and history
remain in the stage owner; this change builds no second binding or fact graph.

The write gate still requires an immutable constructor-backed parent (or no
parent), supported scalar writes, enough identity capacity and no pending origin
map. Ownership Entries, slot-tracking Bake plans, scoped completion, constructor
continuations and ordered unsupported effects retain their original paths. An
unselected matched handoff still needs the original resume probe. Speculative
arithmetic is checked before any origin token is consumed; failure returns the
original bindings so the original error and partial effects are preserved.

Workers perform the already implemented exact-key grouping, source-ordered merge,
physical row writes and duplicate invalidation. Completion restores source order
and consumes the selected token once via `begin_step`, instead of treating the
write as a new root. Existing result witnesses, history completion and publication
retain the source Run boundary. The logical application observer is retained for
selected continuations; it does not count an application as a committed mutation.

This takeover removes the coordinator's scalar RHS execution within that gate.
It does not remove source completion or parallelize union. The additional state
is a sparse vector of `(ordinal, origin token)`; root-only batches allocate none.
`writes.inherited_candidates` reports actual coverage, and
`writes.origin_token_bytes` charges allocated token storage, also included once
in the existing temporary-byte total.

A later Bake iteration can learn which observed continuations repeatedly reach
this supported write form and combine their static boundaries. This patch reuses
the compiler's existing proof; it neither invents a new catalog nor advances an
effect across a Run. Visibility, same-key merge order, error order, retirement and
actual returned witnesses remain live obligations.

## Validation and reproduction

`prepare.py CONTROL ACCEPTED TARGET OUTPUT` runs the existing ordered integration,
runtime, legacy/all-feature and README checks through one compute lease, freezes
the two binaries with `tools/freeze_runtime.py`, and compares exact source Runs,
effects and final states. It also runs the reviewed native sum-bits acceptance
entrypoint against saved exports. The local `out/cell-entry-owned/semantic` path
must expose those saved exports; an isolated worktree can symlink that directory.

The new regression exercises two and four workers, old/min/max writes to the same
key, deletion/recreation, union-enabled rematching and same-Run/next-Run observers.
It compares each Run snapshot and binding audit, plus the write audit when enabled.
The scalar-overflow regression also covers inputs from a preceding producer Run.

Timing is a separate queue reservation, with five sum-bits samples and three
Raytrace samples per lane, one warmup each, all control runs before all candidate
runs. Compilation, profiling and timing never overlap. Runtime binaries and
measurement outputs stay on the internal disk; only the shared Cargo cache is
on the external SSD.

## Coverage

Queue job 124 passed 211 runtime tests, 112 ordinary integration tests and 89
ordered integration tests (the suites overlap), legacy/all-feature checks, and
the README compile/run/bench commands. Frozen sum-bits and Raytrace states, source
Run summaries and logical effects matched the control exactly. The reviewed
sum-bits semantic validator returned `pass` for both binaries. Resumed/completed
steps, root attempts, maximum chain and block resumptions also stayed equal.

| Raytrace work | Control | Candidate |
| --- | ---: | ---: |
| Worker write batches | 3,660 | 4,786 |
| Worker write candidates | 840,367 | 1,161,128 |
| Candidates carrying a selected Cursor | 0 | 302,679 |
| Invalidated redundant rows | 84,978 | 90,054 |
| Cumulative temporary bytes in this path | 175,246,480 | 249,207,360 |

The new origin vector accounts for 7,066,304 cumulative bytes (6.74 MiB), not peak
memory. The broader path also creates more existing worker task storage; the
temporary-byte counter does not include the old coordinator allocations it
replaces. Sum-bits enters neither version's scalar-write batch path and preserves
the same stage statistics. No timing conclusion follows from these counts.
