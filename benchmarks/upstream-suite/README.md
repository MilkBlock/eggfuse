# Unmodified upstream `.egg` coverage

Scope: the **standalone Cell CPU runtime**, not an optimization inside native
egglog. Enumerate precisely the ordinary cases in `egglog/benches/common.rs`:
`tests/**/*.egg`, excluding `fail-typecheck` and `proofs` paths. Preserve each
source checksum. The separately added proof-testing variants and Rust API
benchmarks are not covered. The external nightly input directory is absent.

The scalar extension implements the vendored i64, f64, String, bool and Unit
sort primitives, plus generic inequality/value-eq. Identity-order-dependent
`ordering-min`/`ordering-max`, custom Rust primitives, other sorts and additional
source commands remain outside this extension. Set support is unchanged.

`scalar_primitives.rs` compares runtime rule evaluation with native egglog,
including checked overflow, invalid shifts, failed query guards, Unicode strings,
float casts, NaN and signed zero. Float equality, ordering and hashing use the
same OrderedFloat semantics. A small per-graph scalar context preserves native's
first interned zero representation, which to-string can observe. The native
frontend exports an existing representative without creating a new zero.

## Acceptance contract: upstream-grounded-final-state/v1

Both engines must execute the original source's checks. Compare every original
native table, including scalar values, Eq identity relationships, containers and
visibility, using the existing exact rooted bijection checker in
`../marker-handoff/audit.py`. Project away only compiler-introduced tables;
original empty tables remain in the selected schema. This contract applies to
unmodified inputs accepted by the current flat frontend. Unknown/unrooted
identities are **inconclusive**, never passes. No extraction tie or equational
relaxation is applied. This is a final-state contract: source checks execute at
their original positions, but a pass does not certify every unobserved Run
boundary or complete proof/extraction semantics. The sum-bits choice contract
remains separate and is not broadened by this audit.

## Reproduce

Build and copy the executables into an immutable experiment-local `bin` folder:

```
cargo build --release --locked -p eggfuse-cell-compiler -p eggfuse-cell-runtime --bins --example upstream_suite
python3 benchmarks/upstream-suite/run.py --bin-dir FROZEN_BIN --output out/upstream-suite-new --repeat 3
```

`FROZEN_BIN` must contain `eggfuse-cell-compiler`, `eggfuse-cell-runtime` and
`examples/upstream_suite`. The harness records their SHA-256 before and checks
it after execution. Do not run with Python `-O`. Each subprocess has a timeout;
its whole process group is terminated on expiry. Each failure remains in the
manifest. Capability preflight, full compiler/Bake failure, runtime failure,
semantic difference and inconclusive proof are distinct statuses.

Cell inference excludes compilation/Bake, setup and export. Native schedule
samples exclude initialization and include scheduled execution and source checks.
Native CI-style samples additionally include EGraph construction, parsing and
serialization, omitting destructor cost like the vendored benchmark. These
columns have different boundaries: do not compare Cell inference with native
CI-style totals. Three samples on small tests are coverage evidence with timing,
not a strong throughput claim. Results do not establish complete egglog support.

## Regression validation

The six scalar test groups pass, including native rule-level differential
checks and function-index collisions for signed zero and NaN. The full-feature
workspace run records 496 passes and 13 failures after skipping one known
worker-credit assertion. All 13 failures reproduce on `5197c099` with the
corresponding baseline features; the skipped assertion also fails there.
`test-validation.json` retains the test names. No test was weakened.
The named sum-bits compile/run/bench smoke commands complete, and the reviewed
`choice_diagnosis.py` entrypoint returns `pass` for the current runtime
(`sum-bits-acceptance.json`). Saved native exports were reused for that check.

The first exploratory scan used a shared build directory whose compiler was
replaced during execution; those timings are discarded. A subsequent scan hit
storage exhaustion; it is not used as final compatibility or performance
evidence. Final runs use frozen executable copies and record environment failures
separately from unsupported language features.

Parallel queries are explicitly rejected when float-to-string could observe a
not-yet-established zero representation; ordinary execution or one worker is
available. Malformed zero-representation metadata is rejected at admission.
These two subsequent guards were tested separately; the timing binaries remain
pinned to `8450e627` and do not enable parallel workers.

Final coverage: **26 exact final-state passes / 127 inputs**; 95 preflight
rejections, 5 full-compiler/Bake failures and 1 compilation timeout (30 seconds).
There are no environment failures in the final manifest. This does not claim
all egglog types, commands, proof modes or extension primitives are supported.
