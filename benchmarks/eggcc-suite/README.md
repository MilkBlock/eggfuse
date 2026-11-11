# Current eggcc replay

This reproduces the old preprint's **96 workloads × 3 compiler-pass inputs**,
using the captured corpus at `b89129cc`. The production capture used eggcc
`ae80f82a403c1209fb084b115ee89470c7e66d0e`; its own extraction fed later passes.
Our replay uses those frozen inputs. It does not rerun production extraction
or establish that independently extracted programs are equivalent.

The native timing binary is built from the immutable `egglog-baseline` tag,
with only the standalone `native-inference.rs` example added. No native kernel
patch is applied. The current Cell compiler uses fixed common training and
`transfer_suite.rs` links the historical donor by checked typed signatures.
Each target's compilation/Bake and catalog linking are measured separately.
The execution binary enables `sparse-cells,view-ports,storage-metrics` and runs
`--repair-ports --entry-publications`, on one thread. These options must be
reported alongside results; they differ from the upstream compatibility lane's
default runtime.

The driver alternates native/Cell order over three fresh-process pairs for
each pass. It saves all inference samples, complete command time and process
peak RSS. Cell also reports peak RSS through inference. Native inference starts
after initialization at the first schedule; Cell inference includes matching,
RHS, completion and publication. Command times have different output duties:
Cell exports its graph/report. Neither inference column includes Cell offline
preparation. A ratio is a ratio of the measured executions, not a certified
semantics-preserving compiler speedup.

## Reproduce

1. Extract `reproduce/captures.tar.gz` from the historical report into a fresh
   `ROOT/capture`, preserving its manifest. Decode `donor.json.gz` to
   `ROOT/donor.json`. Verify the hashes in `provenance.json`.
2. Concatenate `workloads/pass3/inputs/common-prefix.egg` and `bake.eggpart`
   into `ROOT/bake.egg`.
3. Build the current compiler and `transfer_suite` example with `iterative-bake`;
   build the runtime with `sparse-cells,view-ports,storage-metrics`. Copy them to
   `ROOT/bin/compiler`, `ROOT/bin/transfer` and `ROOT/bin/cell`.
4. Archive `egglog-baseline` into a separate source directory, add the supplied
   timing example, and build it with `--release --locked --no-default-features`.
   Copy it to `ROOT/bin/native`. Do not modify the tag or compile against the
   locally modified native library by accident.
5. Run `python3 benchmarks/eggcc-suite/run.py ROOT --repeat 3`.

The driver resumes completed rows only when executable hashes and repetition
count match. It checks each source hash, verifies executable hashes throughout,
and requires Cell endpoint and ordered schedule digests to repeat exactly.
Failures are retained rather than dropped. Store the manifest, metadata and
text samples; generated binaries and large temporary exports stay under `out/`.

## Semantic scope

Deterministic Cell endpoints do **not** prove native equivalence. The reviewed
sum-bits choice validator is used separately and its rules are not extended to
other workloads merely because their timings succeed. New upstream tests use
the strict grounded final-state contract documented in `../upstream-suite/`.
Suite-wide extraction choices and all native Run boundaries are not certified
by this replay. The manuscript labels that limitation next to timing tables.

A storage-pressure run was discarded before the final campaign. Final samples
use frozen binaries and sufficient scratch space. Analysis uses
`EGG_LAYOUT_ANALYSIS_THREADS=1`; runtime uses `RAYON_NUM_THREADS=1`. Machine and
toolchain details are in `machine.json`. The measured implementation is
`8450e627`; a subsequent optional-worker scalar-admission guard does not alter
this campaign's serial configuration.

Allocator scope follows the historical replay: the no-default-features native
example uses Rust's default allocator, while the standalone Cell runtime uses
mimalloc. The aggregate comparison includes this implementation difference; it
is not an isolated measurement of Cell locality. The upstream CI-style oracle,
by contrast, explicitly uses mimalloc in both arms.
