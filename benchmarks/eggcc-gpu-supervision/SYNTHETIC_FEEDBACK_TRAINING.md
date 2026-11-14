# Synthetic predicted-source collection and refitting

`collect_synthetic_feedback.py INPUTS MODEL HEAD HEAD_REPORT OUTPUT` runs the
actual GPU family runtime on each accepted synthetic input, with the supplied
head producing tokens retained for later consumption. Independent original-rule
CPU saturation labels actual captured witnesses afterward. Original generation
rejections remain in the output manifest. GPU/audit failure stops collection.
This does not replace exact execution or make learned equality authoritative.

The collector requires a matching synthetic-only parent training report. Fitting
also requires explicit `--feedback-head PARENT.npz`; its sibling JSON must match
the artifact hash and declare synthetic-only training. The capture must itself
be synthetic, in the direct-state feedback mode, and name that parent head.
Unknown heads, real feedback training, mismatched bases and incompatible modes
are rejected. Exact-source and predicted-source entries of the same synthetic
input may coexist. Normal real-program inputs remain evaluation-only.

The 11 previously completed synthetic inputs pass all feedback GPU graph and
match audits. They supply 94 samples, including 31 generated-source consumers.
Twenty generated-source feature rows change by more than 5e-6; no direct-source
row does. Compared with the corresponding exact-source captures, rule alignment
and all completion labels are identical. One original non-saturating-budget input
remains excluded rather than being treated as complete.

Adding these trajectories to the existing 25 synthetic contexts, fixed alpha 10:

| Evaluation | Parent head | Feedback-refitted head |
| --- | --- | --- |
| GCD exact-source complete states | 25/41 | 23/41 |
| GCD exact-source direct states | 17/26 | 17/26 |
| LCM exact-source complete states | 80/99 | 78/99 |
| LCM exact-source direct states | 60/78 | 60/78 |
| GCD actual predicted-feedback complete states | 20/41 | 20/41 |

The actual GCD feedback outputs are identical to the parent for all 41 tokens
(maximum float difference zero). All exact graph and match checks pass; token
recovery is 41/41 but independent completion correctness remains 20/41. This
candidate is not promoted. No real training or backpropagation occurred.

Training collected 280 observations; exact feature/target byte deduplication
retained 201 (95/60/46 per template). This deduplication does not merge near-equal
floating rows: small recomputation noise can still alter sample multiplicity.
The experiment does not establish independent sample count, generalization or
benefit from exposure correction. These are old synthetic training inputs replayed
under their fitted model; next coverage work needs fresh synthetic structures and
controlled structural holdouts, not repeated replay alone.

The historical decoder is not used to establish the new GCD feedback result.
`audit_token_state_recovery.py` independently reads the floating representation
and compares recovered states with CPU labels. It still does not authorize unions.

Bake branch inspection remains ace4f4c4. No CPU executor changes were made.
Full multistage GPU execution, learned matching authority, efficient token
expansion and applied CPU correction remain outstanding.
