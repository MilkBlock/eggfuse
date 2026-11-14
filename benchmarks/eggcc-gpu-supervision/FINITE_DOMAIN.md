# Finite Cell interface census

This measures the standalone synthetic GPU-model experiment's dataset generator,
not native egglog execution or GPU throughput. The compiler recipe is used;
observed Eggcc Run bindings are not training samples.

The target is coverage of a bounded structural domain, not generalization to
unseen programs. Previously, unbound consumer inputs were fresh and each
producer/consumer pair retained at most two entries. This omits aliases to
existing source classes even within a single rule's continuation domain.

`finite_entry_domain.py` enumerates typed input equality partitions and, for a
fixed completed source, consumer inputs that alias existing classes or fresh
classes. Consumer query facts are constructed and congruence is closed by the
reference implementation. Contexts changing prior source roots are excluded.
Budgets raise errors rather than silently truncate the claimed domain.

Reproduce with the MLX environment used by the other neural experiments:

```sh
python census_finite_domain.py RECIPE_TRACE OUTPUT.json --ruleset canon --rule 0
python -m unittest discover -s . -p test_finite_entry_domain.py
python -m unittest discover -s . -p test_neural_cell_chains.py
```

Run from this directory. The saved recipe hash and rule manifest are in
`finite-domain-results.json`. All eight canon rules have five typed input
partitions, giving 40 valid source samples. For local rule 0's self-continuation,
the same sources yield 10 positive legacy samples and 186 bounded-enumeration
samples. There are also 186 diagnostic negatives; negatives are not exhaustive.
All nine relevant tests pass.

These counts are candidate training tuples, not committed mutations or actual
ownership transfers. The existing narrow ownership plan covers zero of the
reported transfer opportunities. No weights were changed and no accuracy or
speed improvement is established by this census.

Remaining obligations include contexts changing existing source equality,
other rule pairs, scalar domains, external facts, recurrent closure, and
ownership/lifetime checks. A finite template vocabulary does not by itself
establish a finite sufficient state representation. Even exhaustive fitting
cannot separate two semantically different inputs collapsed to the same encoded
state; this requires an encoding collision audit. Closed-loop execution must
also be checked separately from fitting exact reference inputs.

## All canon rule pairs and encoding audit

Add `--all-pairs` to the census command to consider every producer/consumer pair
in the selected ruleset. `finite-all-pairs-results.json` records 61 represented
pairs, 4,258 positives and 3,908 diagnostic negatives (8,166 total), compared
with 400 positives using the legacy generator on the same source partitions.
The 1,080 compiler-covered ownership opportunities are static candidates,
not executed transfers. Three pairs produced no samples within this bounded
domain; this does not prove they cannot interact in a larger context.

The exact-input audit uses reference source tokens, boundary encoder inputs,
edge features, masks, replacement selection, request, and ordered incidence.
Unused boundary teacher tokens and owned seed inputs are zeroed before comparison.
It found 4,426 distinct inputs and zero conflicting validity/Eq-label samples.
Only overlapping supervised Eq labels are compared; this is not proof of
injectivity, adequate numerical separation, accurate predicted tokens, or
recurrent closure. Ten finite-domain/audit unit tests pass. No model is retrained
or promoted by this result. The next training gate is fitting this covered
domain, followed by actual cumulative admission and ownership audits.

## Generated-token fitting and cumulative execution

`train_finite_completion.py TRACE COMBINED_WEIGHTS OUTPUT.json --steps 600`
fits the enumerated domain on MLX. It differentiates through the source Cell
and consumer transition, rather than substituting reference source tokens.
The existing interface predicate weights remain frozen (six tensors checked
unchanged). This experiment measures training-domain fitting, not generalization.

`finite-training-results.json` records complete Eq states improving from
4,006/4,258 to 4,170/4,258, with states containing false merges falling from
206 to zero. Matching errors stay zero. The 88 remaining failures are in
consumer rules 6 and 7. The artifact archive contains weights and full reports;
binary weights are not tracked in Git.

The subsequent cumulative GPU audit uses seed 93003, six sweeps and Bop pool
capacity 32. It passes 58/61 cases; 60 final graphs pass comparison. Targeted
twelve-sweep checks distinguish three failures:

- Pair (6,7) reaches a verified fixed point.
- Pair (5,7) continues correctly but reaches 34 Bop candidates, exceeding 32.
- Pair (7,6) stops proposing tokens while CPU validation still finds a missing
  union. GPU idleness is therefore not sufficient evidence of saturation.

The candidate is not promoted. The deeper audit demonstrates remaining
boundary-equivalence/closure obligations, even after local fitting improves.
These results do not establish a complete ownership lifecycle or multi-stage
runtime. The default model remains unchanged.

## Cross-Cell alias diagnosis

`finite-boundary-diagnosis.json` records the twelve-sweep (7,6) case with
per-admission result-root inspection. The device retains only each selected
frame's result roots; CPU checks run after execution and do not feed the GPU.
Every admitted frame has correct within-frame Eq relations. Nevertheless,
admission 6 (rule 7) creates handle 247 where the reference already has result
8 for `Const(10,11,12)`. Final roots retain both results, plus unmatched pairs
(6,248) and (7,253). Full graph comparison rejects this despite device idleness.

This is evidence of a missing cross-Cell result alias, not a demonstrated
within-frame Eq predictor error. Source witness reuse currently inspects only
selected matched source Cells; absence there is not global freshness proof.
The next structural obligation is to expose the relevant completed constructor
witness through Bake's ownership/export context, preserving actual returned
identity and lifetime. Training local Eq alone cannot recover an external
identity absent from its interface. No graph-wide runtime scan or weakened
acceptance was introduced to hide the failure.

## Bounded source-export context

The cumulative prototype now accepts `--witness-context-depth 1` (default zero).
Each admitted Cell retains fixed-width references to the actual matched source
rows and their generations. It does not copy their bindings or slot payloads.
Constructor witness lookup follows these forward references with a fixed
number of tensor gathers, then reads the same template export sites and owned
slots used for direct sources. Visibility, settlement, physical owner validity,
and generation are checked on every link. New references are recorded only
for accepted admissions. This is not a reverse consumer index.

At four query atoms, depth one visits at most 20 source positions per lookup
instead of four, including duplicates. Stored context costs 36 bytes per
reserved logical Cell row (two int32 arrays and a Boolean array). These costs
are real; no speedup is claimed. The depth is currently an explicit compiled
budget, not a Bake proof of full constructor coverage. It is not a replacement
for layout-directed selective context extraction, nor proof of global freshness
when lookup misses. No reclamation or full ownership lifecycle is established.

With unchanged trained weights, the (7,6) counterexample passes its twelve-sweep
cumulative audit at Bop capacity 32: correct complete graph, CPU fixed point,
device idleness, and no remaining cross-Cell alias errors. It admits 12 instances
instead of the failing run's 14. This demonstrates actual result reuse on the
GPU; the final CPU audit supplies no corrections to execution.

The full 61-entry cumulative check with depth one, twelve sweeps and Bop
capacity 64 gives 61 correct final graphs and 60 verified fixed points.
It executes 255 admissions; CPU audit totals about 0.349 seconds (diagnostic
timing, not a performance comparison). Context storage is 3,636–4,104 bytes
per case. The overall audit still reports `difference`; neither raw follow
prediction checks nor fixed-point requirements are waived.

Pair (5,7) remains productive. At 24 sweeps it reaches 24 admissions and 76
correct facts, then overflows at 67 Bop candidates. Its lack of saturation is
unresolved, not proof of infinite growth. Raising capacity again without
examining this expansion is not the next correctness fix. See
`witness-context-results.json` for the retained results and artifact location.
