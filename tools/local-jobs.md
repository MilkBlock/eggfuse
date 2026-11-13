# Local experiment queue

All worktrees on this account share one FIFO at
`~/.local/state/eggfuse-jobs`. A job owns the execution window until its entire
process group exits. Both compute and timing jobs are exclusive; internal worker
threads are unrestricted. Submit the whole baseline/candidate comparison as one
timing job, so another build cannot enter between its samples.

Install the standard-library Python launcher once:

```sh
python3 tools/local_jobs.py install
~/.local/bin/eggfuse-job status
```

Installation copies the implementation to `~/.local/share/eggfuse-jobs`, outside
ephemeral worktrees. The daemon starts on demand. No shell configuration,
system service or global Cargo executable is replaced.

The shared build cache may live on an external disk: keep `target` as a symlink
and keep other worktrees' `CARGO_TARGET_DIR` pointing at that same path. The
repository ignores both a `target` directory and a `target` symlink. Cache
relocation must itself hold a compute lease: copy and verify the files before
replacing the old path, then verify a Cargo command through the symlink before
removing the original copy. Keep frozen benchmark executables and reports in
`out/`; relocating a build cache does not establish a runtime speed change.

On this machine, worktree `3063/egg_layout/target` points to
`/Volumes/Extreme SSD/eggfuse-build-cache/3063/target`. Migration job 121 verified
13,181 files by size and SHA-256; job 122 passed both parallel-publication tests
through the original target path. Existing build commands need no path changes.

Every session running compute work should use the launcher:

```sh
~/.local/bin/eggfuse-job run --kind compute -- cargo build --release --locked
~/.local/bin/eggfuse-job run --kind compute -- cargo test --locked -p eggfuse-cell-runtime
~/.local/bin/eggfuse-job run --kind compute -- target/debug/examples/batch_cell_learning check-passive out/batch audit
~/.local/bin/eggfuse-job run --kind timing -- python3 benchmarks/raytrace-parallel/quick.py CONTROL CANDIDATE OUTPUT RESULT.json
```

`quick.py` also acquires a timing reservation when launched directly. Nested
managed commands reuse their live lease, so they do not queue behind themselves.
A compute job cannot silently upgrade to timing: submit that entire pipeline
with `--kind timing` instead. Run boundaries inside the Cell runtime are unchanged.

For work that should survive the submitting terminal, use `submit` and keep its
printed job ID. `run` waits for completion, then prints the job log and returns
the command's exit status; it does not stream log reads during measurement.

```sh
~/.local/bin/eggfuse-job submit --kind timing -- python3 benchmark.py
~/.local/bin/eggfuse-job status
~/.local/bin/eggfuse-job wait 12
~/.local/bin/eggfuse-job cancel 12
```

Commands are passed as argv, without an implicit shell, and inherit the submitter's
working directory and environment. For a multi-command pipeline, explicitly use
a shell or a script. Jobs are noninteractive: stdin is closed. Live logs are in
the path printed at submission; reading them is optional, not a periodic sampler.
Environment variables and lease tokens are never saved in the queue journal.
The private queue directory contains job records, separate logs and the Unix
socket. It is not part of Git.

Before admission, the daemon waits for known unmanaged Cargo/rustc, runtime,
test and Bake processes to finish. Timing jobs then require three continuous
seconds without those processes; compute jobs require no extra quiet interval.
No periodic process inspection runs while the foreground command executes;
after it returns, the guardian checks for remaining descendants. Waiting clients block
on a socket rather than polling. The quick harness retains its sample-boundary
checks: an unmanaged process started during a trial still invalidates that trial.
The queue does not suspend unrelated processes or freeze background OS services.
Sessions bypassing the launcher therefore remain detectable interference, not
participants whose execution the scheduler can prevent.

Execution exclusion does not validate Cargo artifact identity. A shared target
can leave a fresh fingerprint beside a top-level launcher from another
worktree/configuration. Frozen runtime comparisons use `tools/freeze_runtime.py`:
inside the lease, clean only the runtime release package, rebuild its requested
features and immediately copy the executable. Dependency and debug caches stay.
The helper records its commands, features and binary hash. Check expected runtime
path coverage as well: two identical executables can pass a semantic comparison
while failing to test the proposed change. The publication integration caught
and rejected exactly that case before timing.

For CPU diagnosis, build both frozen versions with the optional `inference-cpu`
feature (macOS/Linux). It samples process user/system CPU, coordinator thread CPU
and context switches immediately around `runtime.execute()`. It is independent
of `storage-metrics` and adds no per-Cell or periodic sampling. The quick harness
retains the `inference_cpu` record plus existing completion/wait statistics before
removing temporary reports. Keep diagnostic builds separate from ordinary speed
acceptance. CPU divided by wall time is average cores consumed by the whole
process, not worker utilization; wall minus coordinator CPU also includes OS
preemption and is not pure synchronization time. The report records boundary
sampling overhead; CPU samples have that small boundary skew.

Cancellation terminates only the owned process group, escalating after five
seconds if necessary. It cannot cancel an unrelated external blocker. The
guardian keeps the reservation while background descendants remain. If the
daemon dies, a closed control pipe terminates its owned group; after restart,
unfinished records become `interrupted`, and queued commands are **not replayed**.
Check their outputs before explicitly resubmitting. A stale lease cannot bypass
the queue. Commands must not detach into new sessions to escape their process group.

For upgrades, wait until the queue is idle, then run `eggfuse-job stop` and repeat
installation. `stop` rejects a live queue; it does not cancel work implicitly.
Do not remove socket/lock files based on their age, and do not select different
`--state-dir` directories for real workloads: that would create independent queues.
The alternate directory and `serve --guard none` exist for isolated lifecycle
tests. The quick timing harness rejects a lease whose external guard is disabled.

Validation (isolated short commands, not Cell performance samples):

```sh
~/.local/bin/eggfuse-job run --kind compute -- python3 tools/test_local_jobs.py
~/.local/bin/eggfuse-job run --kind compute -- python3 benchmarks/raytrace-parallel/test_quick.py
```

Tests cover FIFO across working directories, command exit status and environment,
queued/running cancellation, nested leases, daemon crash recovery, descendant
draining and fail-closed process inspection. Existing quick tests cover retained
samples and rejection when unmanaged work appears at a sample boundary.

The installed queue passed eleven scheduler tests and five quick-harness tests,
including idempotent installation and protection of an unrelated launcher.
It also completed the full sum-bits/Raytrace comparison as timing job 6 after
five unmanaged attempts had been interrupted by other sessions. All 48 boundary
guards and the trial's state/Run/effect checks passed. This validates scheduling
and admission; it does not claim improved benchmark speed or isolation from OS
background services. See `local-jobs-validation.json` for the recorded evidence.
