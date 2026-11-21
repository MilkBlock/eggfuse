# One admission for the signed 143 → 55 → 143 Cell

The recursive issuer selects the signed continuation using its frozen issuance
actor. The native Rust verifier checks the typed two-edge plan against the
loaded program at configuration. A named external root that passes verification
and selects the full plan admits one instance. Its existing ownership records
carry that admission along the two specific physical outputs. A leaf or an
unrelated outgoing edge has no such permission.

At an internal Run, the release code reads the physical pivot, checks membership,
visibility and generation and projects the live slots. After the scheduler
selects that exact lane, a private grant ties its root, child rule, serial,
physical address and version to the owner. The receiver consumes the grant and
the released slots directly. This removes internal recipe creation, decoding
and per-field graph probes at the ordinary proposal verifier. The original
commit still compares the input slots and runs the ordered RHS. A successful
fresh Set captures its actual operands directly from the source activation.
An existing key grants no fresh Set permission. A subsequent Run still checks
the captured fields against the live row under current equality. A completed
block is counted only on successful return of the terminal RHS. During that
RHS the existing graph birth hook also observes nested activations. If it
creates another Get or Single, the fresh-pivot frontier remains open. Only
blocks with no such birth contribute to the exhausted-frontier count.
A concurrent or later union, a residual rule, and a future Run retain their
original scheduling and validation.

The covered scope is the finite two-edge Bake program. Its dynamic guards can
leave a prefix with no terminal grant. Closure under additional rules, and
certification of an arbitrary graph claimed saturated by an external model,
are outside this experiment. Both arms use the same frozen actor, single CPU
thread, physical parent addresses and version index. Timing uses six alternating
pairs after warmup, with separate profiled requests for the internal bind,
capture and whole receipt-opening loop. Full inference is timed without those
clocks. The standalone semantic script additionally checks saved sum-bits exports.

From the external GPU-session worktree:

```sh
d=benchmarks/pass3-cell-gpu/ripsat-block-verifier
e=/Volumes/EggFuseWorkspace/experiments
o="$e/new-block-study"
job() { ~/.local/bin/eggfuse-job run --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse "$@"; }
job env PYTHONPATH=benchmarks/pass3-cell-gpu/joint-witness python "$d/build.py" "$o"
job python "$d/study.py" "$e" "$o/session" "$o/results.json"
job python "$d/controls.py" "$e" "$o/session" "$o/controls.json"
job python benchmarks/marker-handoff/choice_diagnosis.py "$e/pass3-atlas-integration-20261120/semantic-sum" "$o/choice.json"
```

## Native Pass 3 results

The following are per-workload totals or median elapsed times for the same
frozen generator with the generic and block receivers respectively.

| Work | sum-bits | 3mm |
|---|---:|---:|
| External block admissions | 194 | 5,413 |
| Middle and terminal generic bindings bypassed | 61 | 2,161 |
| Completed blocks with exhausted fresh-pivot frontier | 26 | 932 |
| Fresh Set frame replays removed, also fresh row reads removed | 35 each | 1,229 each |
| Internal binding, µs | 9.56 → 2.62 | 274.61 → 84.56 |
| Fresh Set capture, µs | 6.44 → 0.90 | 191.89 → 29.33 |
| Entire receipt-opening loop, µs | 70.12 → 69.87 | 1,128.92 → 1,086.44 |
| Full native inference, ms | 31.77 → 32.78 | 1,606.15 → 1,586.59 |
| External proposals, both receivers | 12,601 | 555,913 |

Both arms agree with the independent vanilla oracle on ordered RHS, writes,
unions, Spine resumes, schedule, Run count and end graph. Their signed
commit lists and actual root commits agree. Withholding the middle receipt or
staling its version restores exactly one external proposal per formerly
completed block. Injecting a wrong operand packet is rejected. Ordinary
inference leaves profiling and audit replay off. These measurements concern the
actual Rust runtime with the experimental generator active, on one CPU thread.
The full-inference results are mixed across workloads.

Four separately profiled single-witness verification passes give median totals
of 2.180 → 2.159 ms and 126.391 → 125.881 ms. Across all roots the number of
header checks falls by 209 and 7,415. Time to the same calibrated increase in
RSS in four fresh sampled processes is 24.62 → 24.93 ms and 931.12 → 930.16 ms.
The raw trials, endpoint checks and unsampled controls are in
[controls.json](controls.json). [results.json](results.json) contains the
component clocks, six unprofiled timing trials and source checks.
