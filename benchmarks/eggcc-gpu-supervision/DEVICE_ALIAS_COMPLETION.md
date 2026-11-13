# Existing-result effect completion: device implementation and coverage limit

`device_alias_completion.py` adds a compiler and GPU operation for RHS effects
that can be completely discharged using the matched Cell's own inputs. This is
an existing-result projection primitive, **not** the general GPU effect executor.

The compiler processes effects in source order. A copy follows the already
established slot alias. A constructor can be reused only if its exact symbolic
argument tuple is already witnessed by a constructor query atom. Its output
projects the observed returned input value, including foreign reuse, not an
operation address. A union is discharged only when both operands already name
the same symbolic input. Literal writes, new equalities, new constructors and
ordered/scalar effects stop admission. Later union effects cannot retroactively
justify skipping earlier work. Unsupported rules are not partially executed.

For an admitted rule, all final slot values are expressed as projections of the
original input snapshot. GPU performs one batched gather and masked write rather
than an interpreted effect loop. It checks input availability and source visibility;
only successfully projected Cells become settled. The newly completed source can
feed the existing compiled entry kernel in the same MLX invocation, with no CPU
state read between effect completion and successor generation. The example
constructor result remains the actual value 999 throughout. Missing source slots
prevent completion and continuation.

This exact proof stage leaves the floating payload unchanged: the payload supplied
by the prior numeric stage remains a prediction. No claim is made that these exact
slot effects train or validate a full token-state transition. The scheduler must
supply matched, current, snapshot-valid source inputs; this module has no concurrent
retirement protocol. Stage and lifecycle integration remain required.

## Real recipe result: no full RHS takeover

On the same dot-product recipe (548 rules), **zero** complete rules pass this
single-template proof. First blocking reasons are:

| Reason | Rules |
|---|---:|
| New constructor or no existing query witness | 338 |
| New equality | 32 |
| Mutable set | 83 |
| Scalar compute | 39 |
| Panic | 49 |
| Literal slot value | 3 |
| Subsume | 4 |

The prototype's global dense projection layout occupies 1,085,588 bytes even
though nothing is admitted. It is not enabled as a runtime optimization, and
this empty layout must not be presented as useful Bake compression. A future
integrated planner should allocate only supported family layouts.

The result rules out treating trivial single-Cell alias completion as the general
Eggcc solution. It does not establish that all 338 constructors are genuinely new
at runtime: their witness may exist in the producer's completed context or another
Cell. The next step needs those authoritative contextual interfaces and genuinely
new result identity handling, not test-specific extra equality assumptions.

## Tests and reference tracking

The GPU test starts with a matched but unsettled source, completes an existing
constructor result into its RHS slot, then generates/adopts a consumer through a
compiled query projection. All state stays on GPU until the final audit. Another
case removes the input witness and confirms both steps remain blocked. Unit tests
reject a circular proof using a later union and a constructor absent from queries.
These are mechanism tests, not a real Eggcc execution or native semantic gate.

The related suite comprises 22 tests across alias completion, lowering, device
admission, compiler contracts and successor matching.

Reference branch advanced to `b3322f9f`, `physical-regions.md`. Its actual source
regions can share physical owners or span suffix segments; physical allocation
identity is neither logical Cell identity nor saturation proof. Keep those identities
separate in GPU slot ownership and do not infer exclusive responsibility from
shared backing storage. No native code was merged.

Reproduce with the NumPy/MLX environment:

```
PYTHONPATH=benchmarks/eggcc-gpu-supervision $PYTHON -m unittest \
  test_device_alias_completion test_lower_device_entries test_device_token_commit \
  test_continuation_contract test_cell_token_successors
$PYTHON benchmarks/eggcc-gpu-supervision/device_alias_completion.py TRACE OUTPUT.json
```

`device-alias-completion-results.json` records the exact source hash and counts.
The broader goal (real GPU multi-entry matching, effect execution, ownership
transfer and repeated cross-stage fixed points with improved correctness) remains
unfinished; this negative coverage result changes the next implementation priority.
