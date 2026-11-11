# Native egglog 3.0 comparison on eggcc

[Complete results](results.md): 288/288 inputs, three pairs each.

This tests the **actual native egglog runtimes**, not a standalone kernel
prototype. Both execute the original 96 × 3 captured eggcc pass inputs from
`../eggcc-suite/`. No input is rewritten to accommodate a newer version.

The two native binaries are:

- `egglog2`: the unchanged `egglog-baseline` (`62ae6baa`, version 2.0.0)
  binary used in the preceding replay.
- `egglog3`: upstream release tag `v3.0.0`, commit `8879605c`, not subsequent
  unreleased `main`. Only the included timing example is added. Its thread
  setter uses the new per-EGraph API; the measured boundary is unchanged.

Both use ordinary Cargo release builds, `--no-default-features`, Rust's default
allocator and one runtime thread. Three fresh-process pairs alternate execution
order for each input. Inference starts after initialization at the first source
schedule, and excludes parsing, initialization, output and process teardown.
CLI time and whole-process peak RSS are separate. Internal search/application,
merge and rebuild timers provide diagnostic breakdowns; their sum need not
equal externally timed inference.

## Reproduce

1. Obtain upstream `v3.0.0`, checking the tag and source archive identities in
   `provenance.json`. Add `native-inference.rs` under `examples/`.
2. Build using `cargo build --release --locked --no-default-features --example
   native-inference -j 2`. Copy the executable to `OUTPUT/bin/egglog3`.
3. Build or reuse the pristine baseline adapter from `../eggcc-suite/`, and
   copy its executable to `OUTPUT/bin/egglog2`.
4. Run `python3 benchmarks/egglog3-suite/run.py OUTPUT --capture CAPTURE --repeat 3`.
   The capture directory is the unchanged historical corpus, not the compiled
   Cell programs. Binary and source checksums are checked throughout.
5. Run `python3 benchmarks/egglog3-suite/summarize.py OUTPUT/suite.jsonl` to
   regenerate tables from saved observations without executing workloads.

Smoke measurements on sum-bits and Raytrace were used only for compatibility.
They are excluded from the full-suite samples. Compilation completed before
timing. The workstation is otherwise unisolated. Failures and timeouts remain
in the manifest and denominator; no failed input is silently dropped.

## Interpretation

`egglog2_over_3` above one means 3.0 is faster. The aggregate ratio uses sums
of per-input medians. The workload geometric mean first sums the three pass
medians for each workload. A version's total runtime improvement need not
imply improvement on every input.

The paper combines the earlier Cell campaign with this native-version campaign
in one table and figure. `python3 benchmarks/egglog3-suite/combine.py` joins all
288 matching source hashes, verifies the common native-2.0 executable and
configuration, and retains all measured times without rescaling. Aggregate
2.0 repeat drift is 0.37%; the median workload repeat ratio is 1.001. Cell comes
from batch A and both plotted native series from batch B. The figure uses
the same workload order and batch-B 2.0 denominator for all three engines.
`combined-summary.json` also retains the workload drift range; a stable total
does not imply every small input is equally stable.

Successful original-source execution is not a proof of final-state or extracted
program equivalence between versions. In particular, 3.0 changes relations to
constructors and contains correctness changes as well as query optimizations.
Lower search time alone does not establish identical logical work. No semantic
acceptance contract is weakened or extended by this timing experiment.

## Follow-up parallel comparison (not measured here)

When the Cell worker feature is fixed to a reviewable revision, compare 1, 2,
4 and 8 threads for all three engines on this corpus. Report both absolute
inference time at equal thread counts and each engine's speedup relative to
its own one-thread execution. Include small workloads and peak RSS; retain
the original completion/publication boundaries. Record Cell preparation,
worker evaluation, coordination, ordered effects and repair waiting separately
where existing timers support them. Version 3.0 requires configuring each
EGraph's thread pool; setting a global Rayon environment variable is insufficient.
These are planned measurements, not claims that Cell already scales better.
