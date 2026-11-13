# Constructor completion between device Entry rounds

`device_constructor_completion` joins existing constructor execution, transient
witness views and floating token refresh. Sites retain original effect_pc order;
an unsupported effect blocks later sites rather than being silently skipped.
Constructor results update authoritative slots and current roots, then mark the
floating token dirty. A settled Cell refreshes the existing class-balanced token
from its completed slots before it may participate in another Entry round.
Scalar feature columns at a constructor destination are cleared with the write,
so old scalar features cannot survive into a new Eq-valued result.

`compile_completion` derives constructor sites, existing witness layouts and
per-rule completed-state encoding layouts from the recipe. It adds no persistent
fact registry. The current execution loop unrolls static sites and refresh layouts;
this remains a bounded correctness mechanism with expensive scans/pairwise work,
not a neural-throughput implementation. It executes constructor identity work
exactly; ridge remains the continuation-state predictor, not proof of effects.

## Verified chain

The GPU test starts with one unfinished Cell holding its input. It completes F,
refreshes the source, generates a consumer, executes that consumer's G constructor,
refreshes its token, then generates the next consumer. New-token counts are
[1, 1, 0], new allocation IDs are 100 and 101, and actual result slots feed the
successor key. All of this runs in one compiled call without intermediate host
reads or a supplied successful consumer list. Test ridge coefficients are
synthetic; this is not a real workload prediction-accuracy result.

68 mechanism tests pass. Unknown external witnesses prevent allocation;
unsupported union ahead of a constructor leaves effect_pc unchanged. The previous
constructor-to-successor test now explicitly refreshes after effects: consuming
its stale pre-effect token was not a legal path. No completion status is inferred
from a predicted vector.

## Real workload opportunity and remaining constraints

Of the 44 previously probed dot-product continuation Entries, 11 consumers have
only supported constructor effects and 19 have a supported constructor prefix.
The first effect is construct in 24 cases and copy in 20; five initial constructs
are outside current lowering (for example literal arguments). These are static
opportunity counts, not executed completion results. See
`constructor-completion-opportunities.json`.

A witness view must be complete relative to the relevant external graph and use
settled Eq roots. The CPU-captured one-source probes do not establish that
coverage, so this implementation does not assert external completeness for real
Eggcc samples or allocate into an unknown graph. Initial import, exact boundary
coverage, copy/literal/scalar/mutable effects and ordered cross-instance commit
remain required. Union completion exists as a separate bounded mechanism but is
not yet integrated into this orchestration. Source Run/stage closure and full
ownership takeover are still unfinished.

Reference Bake tip remains `51853f11`; its diagnostic receipt omission is based
on generator provenance, not permission to omit required RHS effects. No native
runtime or full-workload speed change is claimed here.

## Ordered copy effects

`device_copy_effects` now lowers same-sort slot copies and executes them alongside
constructor sites in original `(rule, effect_pc)` order. Exact values, Eq roots,
numeric/category feature columns and validity follow the same source slot.
A copy consumes no global identity and requires no constructor witness search.
Missing source slots leave the effect pending. Completed copies mark the token
dirty; the same completed-state refresh handles copy-only and mixed rules.
Literal copies remain explicit boundaries, and compile-time sort mismatch is an
error. Unsupported effects still prevent later sites from running.

71 mechanism tests pass, including copying a distinct actual ID/root pair,
scalar columns, unavailable source rejection, copy -> constructor -> refresh in
one GPU invocation, and copy-only completion without external constructor data.
These tests do not establish full-workload semantics or prediction accuracy.

On the same dot-product recipe, 1,043 of 1,047 copy sites lower; four literal
copies remain uncovered. Copy plus constructor support covers 1,944 effect sites
and all effects of 199 rules. Among the previously probed 44 Entries, supported
prefix coverage rises from 19 to 39 and full effect-list coverage from 11 to 22.
This is static coverage, not measured completed consumers: external constructor
views, current roots and all source fields must still be available at runtime.
Union, mutable writes, primitive computations and literal constructor arguments
remain major boundaries. Reference Bake tip is still `51853f11`.

Reproduce the coverage report with `device_copy_effects.py TRACE ENTRY_AUDIT
OUTPUT`; it rejects a mismatched trace identity. Results are saved in
`copy-completion-coverage.json`. No native runtime or speed claim is made.

## Ordered typed union integration

With `compile_completion(..., include_unions=True)`, the completion plan includes
union sites and a recipe-wide typed slot layout. `complete` then requires an
explicit fixed-capacity identity registry (`roots`, `sorts`); `eq_sort_names`
defines its type codes. It returns the updated registry and Eq settlement flag
in its diagnostics. Constructor allocation is capped by registry capacity and
initializes the new identity's type and self-root. It does not infer a global
namespace reservation from a partial witness view.

At a union site, the device collects only instances at the matching effect_pc,
checks declared slot types against the registry, runs bounded Eq/congruence
completion, and advances only if completion settles. The subsequent constructor
uses refreshed roots. Query-only constructor views are included in congruence;
refresh layouts include all recipe templates so inactive but visible shared
readers also receive updated tokens. Actual slot IDs remain unchanged. No-op
completed union effects still refresh their instance's completed representation.

No applicable union means no closure state is installed. Missing operands,
wrong types, unknown external coverage or exhausted closure rounds remain
pending. New roots may be provisional on budget exhaustion, but later constructor
lookup is blocked until a settled snapshot is available. This exact dense
closure is a correctness path, not the desired efficient floating execution.
It does not establish whole-program saturation or ownership transfer.

75 mechanism tests pass. A compiled GPU fixture merges a/b, propagates equality
through two F witnesses, reuses an existing G result later in the same effect
sequence, and refreshes a visible shared reader. Other tests cover budget and
external-view failure, typed fresh allocation and equal-registry-type values
that disagree with template slot types. Full original cross-instance effect
ordering and Run/stage scheduling remain outside this fixture's evidence.

The recipe-only coverage report (`device_copy_effects.py ... --unions`) now
includes 52 union sites, 1,996 total supported effect sites, and complete effect
lists for 235 rules. The prior 44-Entry probe still has only 22 completely
supported consumers; adding union does not remove their other boundaries. The
report is `union-completion-coverage.json`; it is not executed coverage or
prediction-accuracy evidence. Default constructor/copy-only plan behavior is
preserved for callers without a typed registry.

Reference Bake tip `3ae40414` measures receipt omission against the original
workload and reports both Program and Graph storage. Its key lesson applies
here: static support counts and local fixture completion cannot replace a full
runtime denominator or final semantic acceptance. No native branch was merged
and no full Eggcc execution/speed claim is made.
