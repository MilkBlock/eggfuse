# Live GPU selection in the complete Cell CPU runtime

The existing Cargo runtime can now optionally send candidate expansions to a
persistent MLX Metal process. This runs the complete compiled source schedule.
CPU execution retains effects, primitives, union/rebuild, visibility and delta
ownership. Unsupported or small domains use the existing CPU path.

This is exact candidate filtering. It does not train a model, move an entire
join onto GPU, or implement an autonomous GPU egraph. The previous synthetic
prefix selector remains a separate experiment. This integration applies the
same equal-slot selection contract at the live executor's expansion boundary.

Both the generic query scanner and compiled register expansion call the
selector. Compiler slot identities provide repeated-column constraints; current
prefix bindings provide bound columns. A per-request typed Value interner emits
exact i32 codes. Scalar types, strings, large integers and canonical Eq values
never pass through lossy floating conversion. Metal returns a complete Boolean
mask. Original witness order is preserved. Existing CPU survivor checks remain.

No graph effects occur during the request. Overflow of the admitted domain
limits (65,536 rows or 64 columns) uses CPU. Empty, small and unconstrained
domains bypass dispatch. A disconnected, timed-out, incomplete or malformed
service response retains the original domain and disables further GPU dispatch
for that executor. Startup configuration errors are reported before inference.

The initial implementation decodes candidate rows for transport, uses JSON and
synchronous request/reply, then decodes surviving rows through the existing
executor. These costs are explicitly included. There is no resident GPU table,
cross-request batching or asynchronous overlap. No CPU matching results are
sent as GPU input.

## Run

Use Python with MLX and NumPy installed on Apple Silicon. From the worktree root:

```sh
cargo build --release --locked -p eggfuse-cell-runtime \
  --features sparse-cells,view-ports,slot-transfer-audit

cargo run --release --locked -p eggfuse-cell-runtime \
  --features sparse-cells,view-ports,slot-transfer-audit -- \
  --program /absolute/path/to/program.json \
  --output /absolute/path/to/new-output-directory \
  --gpu-selector-python /absolute/path/to/python \
  --gpu-selector-service benchmarks/eggcc-gpu-supervision/runtime_match_service.py \
  --gpu-selector-min-rows 2
```

The program is an ordinary complete Cargo compiler artifact. GPU dispatch is
opt-in. Both service options are required; the default minimum is two rows.
The runtime and compiler remain Rust; the Metal service currently requires Python.

For reproducible CPU/GPU and disconnect validation, use the same audit build:

```sh
/absolute/path/to/python benchmarks/eggcc-gpu-supervision/audit_runtime_match.py \
  target/release/eggfuse-cell-runtime /absolute/path/to/program.json \
  /absolute/path/to/new-audit-directory
```

## Actual sum-bits Pass 3 result

The saved artifact's source SHA256 matches workloads/pass3/suite.json.
This artifact completes 882 source Runs. Counts differ from older 1,428-Run
artifacts; this comparison uses identical program bytes and executable for all
lanes. No source schedule is replaced by the synthetic canon schedule.

hybrid-runtime-results.json records the binary, program and service hashes.
All lanes complete. GPU, large-batch and disconnect lanes exactly match CPU
for final exported state and source control schedule. Every Run's ordered RHS,
effective-write and Spine-resumption digests also match.

With minimum two rows, 808 GPU batches examine 2,973 rows, retain 2,581 and
reject 392. There are zero service failures. CPU preparation takes 0.803 ms;
request/reply takes 266.873 ms, including 190.996 ms measured inside the service.
The latter includes device dispatch, evaluation and result materialization;
it is not a hardware kernel counter and must not be added again to exchange time.

A single diagnostic execution measures 22.262 ms CPU inference and 291.879 ms
with GPU selection. Setup is separately 1.953 ms and 58.396 ms. These are
audit-instrumented measurements, not repeated benchmark estimates.
This implementation is substantially slower on this input.

At minimum 32 rows there are zero GPU batches; its CPU-equivalent result is a
bypass check, not successful offload. A forced service disconnect records one
failure, disables dispatch and completes on CPU with identical audited results.

The validation establishes equivalence to this standalone Cell CPU executor.
It does not rerun native egglog or certify every eggcc workload. Next performance
work must batch independent queries or retain inputs on device to amortize
dispatch, encoding and synchronization. Learned ordering still needs its own
complete residual-search contract.
