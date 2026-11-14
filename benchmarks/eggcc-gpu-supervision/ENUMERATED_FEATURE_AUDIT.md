# Completion readout loses distinguishing context

`audit_enumerated_features.py MANIFEST MODEL OUTPUT --validation FILE ...`
reuses the classifier's feature alignment, compiled completion states and input
Eq constraints. It groups inputs across source cases, unlike the fit-time
per-source duplicate counter. Keys include both the complete f32 feature row and
required Eq mask; signed zero is normalized. Targets are compiled state indices,
not arbitrary class identifiers. This is an offline diagnostic, not a change to
GPU execution or permission to commit predicted equalities.

The 487-case collection contains 19 conflicting input groups (38 rows): 11 in
rule 1 and 8 in rule 2. These inputs have identical classifier arguments but
different target states. No deterministic head with this interface can satisfy
both labels. This is stronger evidence than regression alone; it does not prove
that every validation error has the same cause. Two tests cover cross-source
conflicts, required-mask distinctions, signed zero and nonfinite rejection.

A concrete pair is archived input 40 versus 41, sample 1, rule 1. Both contain:

```
AddContext(ctx, e0) = e4
AddContext(ctx, e1) = e3
Get(e0, 0) = e1
Get(e4, 0) = e3
```

The remaining fact differs:

```
case 40: AddContext(ctx, e3) = e4
case 41: AddContext(ctx, e3) = e5
```

Their classifier feature vectors and required Eq masks are identical, while
independently labeled target states are 1 and 0 respectively. The input graphs
therefore differ in boundary result sharing that the current readout cannot
distinguish. This pair motivates encoding typed boundary connections, including
result sharing, from existing GPU token slots before fitting another head.
It does not justify copying final-state labels into features or passing IDs as
floating values. Ownership context alone must also be checked rather than
assumed to resolve this structural distinction.

There is also a distribution difference: rule 1 training target counts are
{14:335, 4:64, 7:208, 10:48, 9:54, 0:74, 1:33}, while development validation has
{0:78, 7:20}. Rule 2 training counts are
{14:248, 4:45, 7:145, 10:34, 9:44, 0:58, 1:25}, versus validation {0:18, 7:2}.
No validation row exactly matches a training input. Exact non-membership alone
does not establish geometric out-of-distribution status. The diagnostic also
reports nearest training-standardized RMS distances without treating them as a
semantic certificate or using validation to select features/weights.

The full provenance and per-validation distances are in
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/enumerated-gpu-v1/feature-audit.json`.
The tracked summary preserves every conflicting example (without truncation), state counts and model identity.

## Fixed floating propagation resolves the observed collisions

The existing `device_boundary_bridges` encoder leaves all 19 groups identical.
The new opt-in `device_boundary_shared_context` encoder first aggregates floating
role/token messages across typed shared Eq ports, then across the ports of each
logical Cell, and finally into query-port context. It uses the captured current
GPU boundary snapshot, no completed target states and no numeric ID embeddings.
All 19 observed groups become distinguishable. Compiled MLX GPU versus NumPy
maximum error is 7.57e-7. This is feature separation, NOT trained accuracy,
learned execution correctness, or speedup. The new columns are not yet wired to
the resident classifier. Full-dataset collision checking and fitting remain.

The implementation uses a dense boundary-slot connectivity matrix: quadratic
capacity cost is explicit. Static loops and tensor operations introduce no
data-dependent GPU control flow. Sparse/compiled ownership layouts may later
replace the connection construction, but their savings are not claimed here.
ID-renaming invariance, retired NaN exclusion, and GPU parity tests pass.
The audit now retains all conflict examples (the earlier list truncated rule 1
at ten of eleven groups); its collision counts were already correct.
