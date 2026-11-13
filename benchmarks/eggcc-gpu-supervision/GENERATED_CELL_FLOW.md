# Device-generated Cell states consumed by subsequent Cells

This experiment tests the missing dataflow connection, not Eq classification.
It loads only the compiled program and initial facts. No execution trace,
post-Run state or recorded successor match is loaded. CPU performs one initial
query bootstrap. Bake-derived complete bindings then connect producer outputs
to consumers within one MLX-compiled device graph.

The execution unit is a batch of Cell frames. Constructor expressions inside a
Cell produce dense floating columns using table/argument-specific 32x32 matrices
and tanh. Copy aliases share values. Consumers take their input columns directly
from these device outputs; there is no CPU encoding or rematching between layers.
Exact structural meaning comes from the shared template and symbolic boundary
provenance, not equality of floating vectors. This version uses fixed encoding
weights; **it does not yet learn token completion with ridge**.

## Two issues found rather than hidden

The first run appeared to generate four states from two seeds. Inspection showed
all four were the same template and same input binding: pure identity self-handoffs.
They were not new information. The compiler now removes 62 such entries from the
843-entry catalog, leaving 781 potential entries. General duplicate elimination
is still unresolved; the remaining entries do not imply novel facts.

The bootstrap also incorrectly skipped empty-LHS rules. The actual sum-bits
initialization is an unconditional Cell with 120 constructor operations, so
omitting it removed the starting program structure. Empty LHS now yields exactly
one seed, without consulting an execution trace. Unsupported empty-LHS effects
are marked rather than silently skipped.

## Actual program-derived dataflow

With cross-stage speculation explicitly enabled and a two-layer depth bound:

- 3 initial Cell tokens;
- 118 first-layer generated states;
- 149 second-layer states consuming generated first-layer state;
- 34 Cell templates, 269 batches;
- no CPU matching, generated-state encoding or readback between layers.

These 267 generated tokens are **derivation instances, not 267 novel facts**.
Cross-ruleset edges carry pending stage-validation marks. The code does not run
the source schedule or commit graph changes. It therefore cannot establish
saturation, claim a completed source Run, or prove whole-program correctness.
Uncovered mutable/primitive effects, external joins, stage ordering, novelty,
capacity and depth remain obligations. No CPU correction mechanism is bypassed.

The final generated floating arrays match the NumPy reference to maximum
absolute error 7.31e-7. The reference runs only after the entire device chain
finishes. This is a numerical check of the state transformation, **not native
Egglog semantic acceptance or a native proof audit of speculative effects**.

A dependency test changes only the initial input and observes changed grandchild
state, then checks exact equality between each producer result column and its
consumer input column. Only seed arrays are kernel inputs; generated-stage arrays
cannot be supplied by a trace. Other tests cover capacity marks, unconditional
seeds and removal of identity self-handoffs.

The cold device call took approximately 1.25 s versus 6.70 ms for the numerical
CPU reference. Compilation and many small template batches dominate this tiny
experiment; no speedup is claimed. This path is not the proposed efficient final
GPU runtime. Its purpose is to establish and test actual producer-to-consumer
state flow before learning and batching that flow.

## Reproduction

```sh
$PYTHON benchmarks/eggcc-gpu-supervision/generated_cell_flow.py PROGRAM OUTPUT --speculate-stages
$PYTHON -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_generated_cell_flow.py
python3 -m unittest discover -s benchmarks/eggcc-gpu-supervision -p test_cell_token_successors.py
```

Without `--speculate-stages`, cross-ruleset transitions stop at marks. It is not
valid to remove those marks merely because the numerical reference agrees.
The tracked result summarizes marks; full per-transition marks stay in the
untracked output. No runtime mode is enabled by default.
