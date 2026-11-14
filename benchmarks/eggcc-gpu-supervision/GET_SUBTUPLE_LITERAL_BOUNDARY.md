# Literal coverage needed by Bake's completed suffixes

Bake aedc2707 reports paths such as 341 → 145 → 139. The last two rules implement
Get → Single/Get/SubTuple and SubTuple length one → Single/Get. Both require the
literal i64 value 1. The previous synthetic generator and independent CPU oracle
rejected those operations before an actual GPU coverage test was possible.

The generator now instantiates exact i64 query literals. The reference oracle
checks literal fields by typed scalar identity, and interns literal operands
used by copy/construct/set/union effects (ill-typed unions still fail). Constants
reuse existing scalar identities and never go through f32 conversion. Values
outside signed i64 range, bool/float masquerading as i64 and unsupported literal
sorts are rejected. The constant's scalar address is not an Eq-class prediction.

Using only actual compiler definitions for rules 145 and 139, seeds 20261500–
20261511 each produce a rule-valid local input and complete in two reference Runs.
This is independent CPU local-family execution, not native Eggcc acceptance and
not a GPU result. No real program bindings or values are training data. Logical
application counts in the manifest must not be interpreted as committed writes.

The GPU boundary remains explicit:

- Rule 145's Get query is covered, but its SubTuple RHS has `literal_argument`.
- Rule 139's SubTuple query has `literal_atom` and unbound-query coverage marks.

These cases are not admitted to GPU training. The existing incomplete-view and
completion marks are retained. No full-history completion or ownership takeover
is claimed. Adding CPU reference support alone does not finish GPU literal
execution; it establishes the oracle against which the fixed template literal
slots and query filters must be implemented next.

Reproduce generation with `synthetic_cell_inputs.py get-subtuple-literal-recipe.json
ARTIFACTS --rules 0,1 --seed 20261500 --count 12`. Eleven focused tests pass, including
exact rejection of a nonmatching literal, large integer retention, constant reuse,
and previous nonliteral reference/synthetic/schedule regressions. No accuracy or
speed improvement is claimed, and no native CPU executor was changed.
