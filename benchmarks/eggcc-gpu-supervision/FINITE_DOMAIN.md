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
