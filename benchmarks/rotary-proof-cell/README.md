# Rotary proof-carrying Cell prototype

This is a **standalone, bounded neural experiment**, not the egglog runtime or an
EggFuse/eggcc execution backend. It tests whether a generated latent can carry a
small Cell through local union and ownership transfer without a CPU reconstructing
the next state. It does not measure compression, inference speedup or verifier
speedup. The source runtime is unchanged.

The learned transition, shared decoder, rotary references and active payload bank
execute on Metal through MLX. A symbolic teacher supplies offline supervision.
After inference, a NumPy-only checker decodes saved latent bytes and rejects
invalid results; it never supplies a replacement state to the network.

## The complete example

The trusted vocabulary is deliberately finite. Cell roles are `a,b,u,v,w`;
`u=F(a)`, `v=F(b)`, and a later `w=G(u)`. These are symbolic roles, not scalar
numeric values. An opaque 8-bit Cell annotation must survive every transition;
it is not an e-class attribute. There are three source Run boundaries:

1. `Seed(x,y) -> F(x), F(y)`. Cell A receives `[a,b,u,v,empty]`.
2. `SameValue(x,y) -> union(x,y)`. A composed `merge_f` proof also justifies
   `F(x)=F(y)` by congruence. A retains its address; only its latent changes.
3. `Seed(x,x) and F(x)=u -> G(u)`. The repeated-variable LHS requires an equality
   witness. If enabled, create B, preserve old members and transfer ownership.
   Otherwise retain A and the pending extension obligation.

In the illustrated held-out case, there is no initial equality, `SameValue(a,b)`
is present, the requested free result port is 2, and the annotation is `0xA5`.
The input, A and B positions are 0, 5 and 9:

| Generated state | Owner | Layout | Equality | Pending work |
| --- | --- | --- | --- | --- |
| Run 1 | A at 5 | `[a,b,u,v,empty]` | none | merge, extend |
| Run 2 | A at 5 | `[a,b,u,v,empty]` | `a=b`, `u=v` | extend |
| Run 3 | B at 9 | `[a,b,w,u,v]` | `a=b`, `u=v` | none |

Run 3 emits `extend_transfer(seed, build, union)`, selects the `u` argument and
emits the nonuniform old-port projection `[0,1,3,4]`. Therefore `(A,2)` now resolves
to `(B,3)`, still denoting `u`. The verifier also accepts `v` as the G argument
when the equality proof justifies it. Equality does **not** silently erase the
old logical u/v roles or allow their projection to be swapped.

## What the network actually computes

`CellNet` has a 15-feature input encoder, a 128-float recurrent latent, one shared
residual transition MLP conditioned on the Run ordinal, and one linear decoder.
The 15 initial features are: initial-equality bit, SameValue bit, five-way free
port request and eight annotation bits. The free port is an input constraint,
not a target layout. The encoder runs once per rollout.

```text
initial facts -> encoder -> latent 0
latent 0 -> shared transition(Run 1) -> latent 1 -> decoder: layout/proof
latent 1 -> shared transition(Run 2) -> latent 2 -> decoder: layout/proof
latent 2 -> shared transition(Run 3) -> latent 3 -> decoder: layout/proof
                                                |
                                   masked bank / old-reference reads
                                                |
                                 saved bytes -> independent CPU audit
```

Each transition directly consumes the previous generated float tensor. It does
not consume a teacher latent or decode a reference state and re-encode it.
Discrete owner decisions route the generated tensor to its position. The decoder
predicts layout, alias ports, owner, proof opcode, premise references, G argument,
equality bits, pending obligations, retirement and annotation bits. Supervision
is on these decoded fields at every Run, not on an invented target latent.

The five proof opcodes and six premise roles are a **manually specified trusted
vocabulary** for this example, not learned theorem semantics or an automatically
Baked proof library. In particular `merge_f` combines union and congruence, and
`extend_transfer` combines a repeated-variable LHS witness, construction and
role-preserving transfer. The CPU checker expands these meanings locally.

## Coordinates, transfer and masking

Cell and port rotations operate on disjoint 64-dimensional subspaces. Using the
same rotation space for both would collapse the distinction between the two
coordinates. For a decoded projection `mu`, old references are rebased by:

```text
key(c,p) -> inverse cell(c), inverse port(p)
         -> cell(c_new), port(mu(p))
```

Routing uses GPU dot products and argmax against the finite candidate port keys.
The projection and owner are decoded from the generated latent. The rotary
operators themselves, argmax, fixed Run schedule and masking are ordinary GPU
operations; this is not an entirely learned interpreter. Rotation is an addressing
feature, **not a proof of identity or collision freedom for unbounded graphs**.

Once the generated retirement bit retires A, the active read bank masks A with
`where` **before arithmetic**. Multiplying a NaN payload by zero would be unsafe.
If there is no transfer, A instead receives its newest generated latent. All old
interface reads after transfer use B. Audit checkpoints remain separately saved;
they are not read-bank fallbacks. No claim of reduced physical allocation is made.

## Checks and evidence

See `results.json`, `training.json` and `audit-result.json` for recorded results.

- 3,840 training-domain examples rechecked at held-out positions: all pass.
- 1,280 held-out annotation/position examples: all pass all three Run contracts.
  Of these, 960 transfer and 320 correctly retain an unfinished obligation.
- In those 960 transfer cases, replacing the retired payload with zeros, random
  values or NaNs leaves old-interface reads identical. Its active-bank contents
  are zero and its active bit is false.
- Reading old ports in order `[3,0,2,1]` returns roles and remapped ports in that
  order, including with the old payload poisoned. This is a reference-order test,
  not a proof of arbitrary input-token permutation invariance.
- CPU decoding of the **actual rotated latent bytes** agrees exactly with GPU
  categorical/Boolean decisions. Float logits agree only approximately.
- Eight negative controls are rejected: wrong premise, unauthorized union, early
  G publication, wrong projection, lost annotation, lost pending obligation,
  advertised proof inconsistent with latent, and wrong owner position.
- Final-stage logits have a nonzero gradient to the initial input. Replacing the
  second generated latent with zeros makes the third-stage certificate fail.
  The unit test separately checks every recurrence tensor against explicit calls.
- Six unit tests pass. The saved checkpoint can be audited in a separate process
  using only NumPy, without importing MLX or executing the network.

All **20 semantic/layout patterns occur in training**. The train/test split holds
out 64 of the 256 annotation values, including `0xA5`; it does not hold out rules,
operator structures or semantic branches. Training Cell positions start in 0..63
with gaps 1..8; test starts are 1024..3999 with gaps 9..39. Success on this small
finite domain is not a universal correctness guarantee or evidence of general
proof synthesis.

The CPU auditor independently runs the small source rules and congruence closure,
checks the decoded state, checks proof premises and checks owner/port bindings.
It performs no matching or state correction on the inference path. This experiment
does not yet establish that verification is cheaper than the computation.

## Reproduce

Use an Apple Silicon Mac with Metal and the versions in `requirements.txt`.
Weights and binary checkpoints must remain outside Git. On the shared experiment
machine, submit compute commands through `eggfuse-job`:

```sh
python3 -m venv /tmp/rotary-cell-venv
/tmp/rotary-cell-venv/bin/pip install -r benchmarks/rotary-proof-cell/requirements.txt

~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /tmp/rotary-cell-venv/bin/python benchmarks/rotary-proof-cell/test_rotary_proof.py

~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /tmp/rotary-cell-venv/bin/python benchmarks/rotary-proof-cell/experiment.py \
  /tmp/rotary-cell-result --steps 3000

~/.local/bin/eggfuse-job submit --kind compute -- env PYTHONDONTWRITEBYTECODE=1 \
  /tmp/rotary-cell-venv/bin/python benchmarks/rotary-proof-cell/audit.py \
  /tmp/rotary-cell-result/audit-checkpoints.npz
```

For inference-only replay, provide `--weights PATH/model.safetensors` and a new
output directory. Reports record source and model hashes. On a dedicated machine
without the shared queue, invoke the Python commands directly. Missing Metal is
an error; no CPU inference fallback exists.

## Remaining contract boundaries

This prototype has no automatic Cell extraction, iterative Bake, arbitrary LHS
search, external constructor collisions, mutable functions, dynamic global
stopping, arbitrary token ordering or general ownership graph. It does not run
sum-bits, dot-product or eggcc. It has no online CPU approval gate: a bad network
output produces a rejected audit, not a corrected inference result.

Coordinates deliberately change latent bytes. We check exact decoded logical
state, not bitwise-equal latent representations for differently numbered graphs.
The earlier stronger canonical-latent / permutation-invariant contract remains
unproved. Preserving information here means preserving the defined members,
authorized equality, annotation and pending obligations, not preserving every
historical float tensor in the active runtime state.
