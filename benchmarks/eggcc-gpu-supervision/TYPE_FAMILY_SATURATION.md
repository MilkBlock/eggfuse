# Real type-analysis Cells repeatedly consume generated facts on GPU

The earlier regeneration test executed each rule independently. This test keeps
four original Eggcc rules together: 534 and 535 produce PureType, while 536 and
537 establish PureTypeList from TNil and TCons. All belong to type-analysis.
The family starts from 40 visible real snapshot facts, with PureType and
PureTypeList removed. Those missing predicates are not supplied by the CPU.

Each source Run queries one frozen state, generates Cell instances with ridge
tokens, executes ordered immutable effects, refreshes tokens and performs checked
physical-owner takeover. Subsequent Runs query the resulting state. The nested
schedule controller resides on device and decides when saturation has completed.
A fixed host loop launches 24 compiled control ticks without reading intermediate
state or branching on device results. Extra ticks after HALT remain masked; this
is not a claim that all GPU work or launches stop immediately at saturation.

## Independent CPU verification

Only after device execution, the CPU independently joins raw seed facts and
interprets the original rule bodies to a fixed point. It freezes the fact snapshot
for all rule queries within each Run. GPU completion results are decoded directly
from ordinary query/effect operations and owner slot reads, independently of the
GPU view compiler. Overwritten or missing facts are not silently omitted.

Seed identities remain fixed. Fresh IDs are decoded into constructor terms;
all allocations must be explained and distinct terms must not alias. Exact
closure and per-Run fact-growth sequences must both agree. Final-state equality
alone cannot establish a pass.

## A real scheduling bug found and fixed

The first 32-lane run reached the expected final facts but had failed enumeration
and never legally completed its Run. The controller still committed effects
after detecting a query failure. It now discards those speculative effect outputs,
ID changes and Eq-registry changes, retaining admitted instances as pending.
It records query_failed and cannot advance the failed Run. Explicit recovery is
still a caller responsibility; the test does not claim automatic CPU correction.

A second issue was repeated facts exposed by overlapping Cell views. They could
fill the bounded intermediate candidate array before final binding deduplication.
The matcher now retains the first live witness of each identical typed fact
before candidate compaction. Eq fields compare current roots; scalar fields
compare exact scalar identities. Different result roots remain distinct, and
missing-view coverage is not weakened. No persistent fact registry is added.

This first worked by enlarging capacity to 128. With pre-compaction fact dedup,
the same family now completes at 32 lanes. The implementation adds dense O(V^2)
witness comparisons per atom, so it reduces capacity pressure without proving
lower runtime or scan cost. It remains an exact fallback, not neural matching.

## Results

type-family-results.json records input/model hashes and the final checked run.

| Measure | Result |
|---|---:|
| Original rules in selected family | 4 |
| Seed facts | 40 |
| New Cell instances per Run | 3, 2, 2, 0 |
| New constructor facts per Run, GPU and CPU | 3, 2, 2, 0 |
| Final facts, GPU and CPU | 47 |
| Explained fresh identities | 7 |
| Pending Cells / failed Run | 0 / false |
| Released physical rows | 9 |
| Logical Cell instances / live payload owners | 47 / 38 |
| Rejected takeover attempts | 0 |

The last Run produces no new Cell and no new fact, and the device controller
reaches HALT. The CPU's repeated logical rule applications are 3, 5, 7, 7; those
are not counted as new Cells or committed mutations. Previously admitted keys
suppress duplicate instances. Source facts and logical identities remain live
after physical relocation.

The final recorded GPU compile/upload/execution time is about 1.03 seconds;
CPU reference closure, decoding and checks take about .011 seconds. Earlier
compilations took substantially longer. Shader cache and shared-machine effects
are not controlled, and the scopes differ. These timings do not demonstrate a
speedup, native audit throughput or neural-network execution efficiency.

## Scope and remaining requirements

This establishes repeated generation and consumption through saturation for a
real four-rule family. It is **one selected ruleset**, not all type-analysis rules,
not original Eggcc initialization, and not the full multi-stage schedule. Pure
constructor/copy semantics permit this closed-world test; unions, mutable effects,
deletion, delta ownership and missing external coverage need their own contracts.
The ridge model is used to infer admission tokens, but exact GPU query/effect
kernels establish completion and regenerate authoritative tokens. No learned
completion-accuracy or ownership-proof claim is inferred from this test.

The latest reviewed Bake reference remains fba15b23. It warns that shape alone
does not determine layout/epochs and that most physical owners are shared. This
test preserves checked source projections, epochs and aliases. Nine reclaimed
rows are reusable arena capacity, not nine deleted logical source records.

## Validation and reproduction

172 related tests pass. Added cases verify failed-query effect gating, preserving
the first duplicate fact witness, scalar-versus-Eq comparison, retaining distinct
result roots, family import and frozen-Run CPU closure. Final reference checks
also reject overwritten fact slots.

Run audit_type_family.py with rhs-dot-product.json, the frozen
class-history-neighborhood-input.npz and an output JSON. Defaults are --capacity
32 --ticks 24. Data/logs remain under /Volumes/Extreme SSD/eggfuse-artifacts/21ee.
No captured future binding list or cross-stage execution itinerary is loaded.
