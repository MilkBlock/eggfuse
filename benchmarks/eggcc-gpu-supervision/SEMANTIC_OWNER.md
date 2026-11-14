# Semantic ownership in the GPU prototype

This is a standalone MLX experiment, not the egglog runtime. Physical payload
transfer does not establish that a successor token represents the source Cell.
In particular, fields copied into spare payload slots are not part of the
successor's semantic template.

`neural_semantic_owner.compile_semantic_transfer` checks a conservative sealed
constructor/copy/union subset. It proves source constructor facts and equalities
under the slot mapping from destination facts and explicit Eq closure. Constructor
`set` is interpreted as a fact only for constructor tables. Mutable functions,
unsupported guards/effects and overwritten slots remain uncovered. Lowered
constructor-set temporaries use the existing semantic slot projection. This is
an offline structural proof, not proof that a learned token is numerically right.
The existing completion certificate and CPU numerical audit remain necessary.

Opt-in initialization adds two int32 vectors: semantic source row and generation,
8 bytes per logical Cell. No bindings, facts or floating tokens are copied.
A certified handoff composes aliases to the new source. Candidate construction
keeps original logical witnesses and binding-slot projections, but reads token
content and relational port-role features from the semantic source. Referencing
a retired, hidden, unsettled, dirty or reused semantic source blocks consumption.
This conservatively requires a live semantic owner; independent retirement and
asynchronous audit still need explicit lifecycle integration.

The implementation uses fixed tensor operations. It currently scans the bounded
logical arena during handoff and may include the same semantic source repeatedly
as resident context. It is not a dispatch or bandwidth speedup claim. New entries
and recycled rows do not automatically inherit a valid semantic directory.

Tests cover physical transfer with semantic aliasing, old Entry consumption,
matching owner roles, repeated alias composition, generation rejection and
rejection of field-only containment or missing Eq evidence. Existing model weights
have not been retrained for these changed inputs.

Run the independent synthetic audit with:

```sh
python benchmarks/eggcc-gpu-supervision/audit_neural_gpu_rhs.py TRACE \
  TRANSITION_WEIGHTS OUTPUT.json --limit 107 --follow --interface-only \
  --context-capacity 8 --eq-readout EQ_WEIGHTS --semantic-owners
```

Inspect `semantic_owner.adopted` per case before interpreting any accuracy result.
A pass with no semantic adoptions does not validate this execution mode. For
uncovered cases Bake must construct a combined semantic Cell layout and training
must learn its output token; a destination-only token cannot be relabeled as
containing its entire ancestry. Speculative corrections still require an updated
token, and full multi-stage GPU saturation is not implemented here.

The full existing 107-case synthetic corpus admitted zero semantic takeovers:
83 retained source fields only in payload slack, 23 lacked payload coverage, and
one lacked structural facts. Its 312 subsequent states still had 16 incorrect Eq
states including two false-merge states (`difference`, exit 1). These reproduce
the old model's behavior; they do not measure a trained combined-owner token.
See `semantic-owner-results.json`. This rejects promoting destination-only tokens
as semantic dominators and motivates combined template output supervision.
