# Check a model instead of assuming an observed plateau is final

For the selected positive constructor/union rules, an executed derivation proves
that two boundary ports are equal. To prove that the remaining pairs cannot be
merged by further rule applications, it suffices to exhibit a model of the seed
facts and every rule in which those ports remain distinct. A single checked
model preserving the entire observed boundary partition establishes both sides.
It need not be the least model and need not enumerate every generated constructor.

`finite_boundary_model.py INPUT_CAPTURES BOUNDED_NATIVE_CAPTURES OUTPUT` tries a
simple finite completion: use the bounded execution's classes, add a default
value per Eq sort, totalize each constructor, and close the rules. This search is
heuristic. Its output is checked separately: all typed domains are nonempty and
disjoint, every constructor is total/functionally unique, every seed fact holds,
and every ground rule match satisfies its RHS. The native eight-Run boundary
partition supplies positive evidence. The model supplies non-equality evidence.
A model that merges more boundary ports is **inconclusive**, never a new label.

Supported semantics are immutable constructors returning Eq, positive constructor
queries, copy, construct, constructor set and union. i64 is used only through
equality/forwarding; all represented literal values are distinct, with a default
class for other values. The finite interpretation lifts to actual i64 inputs
because omitted values only add possible abstract matches, and all such matches
are checked. No arithmetic, ordering, disequality, mutable reads, deletion,
observable scalar outputs or stage-dependent effects are covered. This verifier
must not be applied to those semantics without extension.

Results on the 20 growing two-Cell inputs:

- 16 checked models preserve exactly the native observed boundary partition.
- 4 checked models are too coarse; they remain unresolved.
- Together with 487 terminating native cases, 503/507 boundary Eq projections now
  have evidence. This is **not** 503 completed whole-graph executions.

The new certificates do not authorize discarding new constructors, skipping
queries in later stages, or retiring an owner/token. They establish only the
selected initial boundary Eq projection under the selected rules. A GPU execution
contract still needs to preserve other exports and continuation obligations.

See `finite-boundary-model-results.json`; full total-function certificates are
hashed and retained on the external disk. Two tests cover a valid model and
rejection of missing totality, empty domains and violated universal rules. All
20 actual certificates passed their ground-rule checks; only the 16 matching
partitions are certified. No training, gradient descent or speed claim.
