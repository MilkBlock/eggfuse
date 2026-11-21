# Detecting old-owner references at neural issuance

The PyTorch CompoundActor can take one optional feedback value for each parent
and candidate join. A committed transfer marks the former endpoint −1, the
current endpoint +1, and unrelated endpoints 0. Its two child rows score
parents and joins jointly, before choosing their emitted parent token address,
effect port and consumer. Both addresses remain legal in the sampling domain.
A learned null score allows the second row to abstain. Inference can take
explicit pass-local parent addresses. The original constructor and forward
signatures remain usable without feedback and accept their existing checkpoints.
The Metal kernel continues to use its original ABI.

Each pass has its own Transfers object. Issuance must read the ledger at the
issuance boundary after applying only committed transfer events. The caller
provides a generation for each endpoint; a token address is immutable over
its pass. The ledger checks single current ownership and supports chains of
moves. It audits the raw output address before any redirection. For this
fixed-entry experiment, the duplicate key within a wave is the logical port
obligation plus consumer. Multiple pivots, other independent bindings, or
source boundaries in a larger grammar would also have to enter that key.
This audit is for continuation claims. A read through a stable source member
after a storage move is legal. Storage-owner IDs and neural token addresses
belong to different namespaces.

## Learning and evaluation

Start with the committed seed-1703 continuation policy. REINFORCE updates the
actual child pointer/join scores, row-specific join scores, null logits, and
ownership coefficients. The root network and latent parameters are frozen.
Generated windows condition the root actor on one active leaf candidate; the
selected root latent consumes the previous pair of self-generated children.
Two generated parent endpoints are available. Random fixtures determine which
owns the continuation. Independent and other-port controls require both claims.
The executed action receives +1 for each unique live continuation and −1 for
each retired, unknown or duplicate claim. No graph speed enters this reward.
The ledger feedback is explicit; the network need not infer an unobservable
transfer from latent similarity. Evaluation compares the same tuned weights
with the feedback present or zeroed.

In 384 held-out move episodes on leaf 8, the blind selector emitted 171
retired and 213 current references. The informed selector emitted 384 current
and zero retired references. Leaf 8 was absent from the training episodes.
On the independent control for that leaf, both arms produced only 384 of
768 required independent claims. On both training leaves, independent and
other-port controls retained both claims in all 384 fresh episodes per leaf.

## Native traces and controlled replay

The four archived seed-1703 pending-parent Metal streams contained 167 active
children. All addressed roots from their own Run. These archives have
publication/retirement outcomes but do not include an issuance-time mapping
from a transferred storage owner to a neural token port. Their spontaneous
post-transfer reference rate is unknown.

The paired intervention uses the native dot-product Run 19 and stable-argmax
Run 15 moves from the prospective-owner experiment. The same member survived
each move. For each archived emitted child on those workloads we take its
actual parent tensor, expose two copies as the old and new owner alternatives,
and project that member onto its requested effect port. Other effects remain
independent. We run the child selector with each lane ordering. This is an
explicitly constructed mapping across experiments. The actor emits raw new
tokens, and the study never writes these proposals into an EggCC graph.

| Intervention, both lane orders | Blind | With transfer |
|---|---:|---:|
| Retired references / emitted children | 57 / 212 | 0 / 118 |
| Exact original continuation covered / 118 cases | 57 / 118 | 66 / 118 |

A current endpoint can support different consumers. A useful deduplicator must
preserve the distinct required consumers as well as avoid retired references.
These results establish sensitivity to ownership in the child selector, with
incomplete retention of the original consumer. No native performance or
end-to-end semantic parity is claimed for the modified model.

## Reproduce

Use the external worktree launcher and shared compute queue:

```sh
d=benchmarks/pass3-cell-gpu/recurrent-generator/ownership
e=/Volumes/EggFuseWorkspace/experiments
o="$e/new-owner-port"
job() { ~/.local/bin/eggfuse-job run --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse "$@"; }
job python "$d/study.py" "$o" --device cpu
job python "$d/replay.py" "$e/compound-pending-pass3-v1/paired" "$o/weights.json" "$o/replay.json"
python3 "$d/test_ports.py"
```

The GPU training attempt failed at MPS pipeline creation because
MTLCompilerService was unavailable. The recorded training and paired inference
used PyTorch on a single CPU thread. The JSON checkpoint contains the updated
parameters over the committed continuation policy. The study and replay JSON
files report all arms and denominators.
