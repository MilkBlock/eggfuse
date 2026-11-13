# Actual RHS result capture

The earlier trace contained successful query inputs and their post-Run Eq
roots, but not constructor returns. `CellResultObserver` now reads selected
slots through existing Cell operand accessors at RHS completion. It covers
ordinary and preflighted frames, with a separate attempt on single writes.
Direct completions without an accessible frame explicitly report unsupported
capture. Incomplete RHSs do not certify slots. The observer is optional and
never feeds matching, effects, repair or publication.

This is diagnostic CPU instrumentation for the GPU training corpus, not a CPU
optimization or GPU executor. It collects actual values, including reused
constructor results. Eq identities are not full Dependency witnesses: ownership,
retirement and boundary premise validity still require evidence. Pending unions
may not yet have committed at capture; the example also records post-Run roots.

`capture_rhs_results` correlates one completion callback to each finalized
binding, checks source order and callback coverage, and compares logical graphs
against an observer-free reference at every Run and at the end. It checks Run
control counts as well. No full snapshots are retained in the artifact, though
temporary graph exports are allocated for comparison. Missing reads remain
explicit, not invented producer/operation addresses.

```sh
CARGO_INCREMENTAL=0 cargo build --locked -p eggfuse-cell-runtime \
  --example capture_rhs_results
target/debug/examples/capture_rhs_results "$PROGRAM" "$TRACE"
python3 benchmarks/eggcc-gpu-supervision/summarize_rhs_results.py \
  "$TRACE" "$REPORT"
```

Build cache and raw trace are stored on `/Volumes/Extreme SSD`; no binaries are
tracked. `rhs-dot-product-results.json` records the actual eggcc dot-product
program fingerprint and trace hash. Across 954 Runs / 5,935 applications:

- 47,173 requested slot reads; 44,510 available, 2,663 expired (5.645%).
- 13,723 available slots were absent from the original matched inputs; 12,107
  of these carry Eq values. These are reads, not unique new constructors.
- 774 captured Eq slots changed root between RHS capture and Run completion.
- All per-Run and final reference graph comparisons passed.

The debug observation execution took 0.716 s versus 0.206 s for reference
execution; temporary per-Run graph comparison took 48.818 s. Input and result
callback bodies took 0.152 s and 0.200 s; those callback timers exclude slot
collection, which is included in observed execution. Total capture/audit wall
was 49.791 s. These numbers expose diagnostic overhead; they are not a speedup
benchmark or GPU audit throughput claim. The expired reads remain a coverage
gap, especially where optimized paths have already released their frame.

Validation: constructor-reuse integration test passes with default features and
`sparse-cells`, checking actual returned values against constructor lookup,
including an initially existing constructor, plus unchanged snapshots,
bindings and final graph. Default and no-default runtime compile checks pass.
Python summary tests reject missing Run audit and keep unavailable reads in the
denominator. This does not replace native egglog/sum-bits semantic acceptance.

Next: use the actual RHS-only identities to connect producer outputs to later
consumer inputs; require complete external premise and lifetime evidence before
promoting candidates into training chains or transferring token ownership.
