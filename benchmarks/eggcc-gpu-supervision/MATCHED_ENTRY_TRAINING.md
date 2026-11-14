# Add matched-only entrances to synthetic completion training

All 189 native-audited terminating matched-only inputs completed the GPU capture
and independent labeling pipeline. There are 851 samples and 368 generated-source
consumers. The other two native inputs timed out and remain unresolved; they are
not silently labeled as completed or included in this training set.

Merge policy: include every distinct input hash, retain the existing capture on
duplicate identity, never select on accuracy. Of 189 inputs, 35 overlap the prior
487; 154 new inputs produce a combined 641-entry corpus with 3,109 samples. The
fitter uses the same fixed joint projection, ordinary weights and alpha 10.
Both synthetic feedback parent heads are explicitly identified. Real GCD/LCM
runs are development evaluation only, never training samples. No gradients.

| Exact complete states | Prior joint head | Added matched-entry head |
|---|---:|---:|
| GCD, exact-source offline | 26/41 | 26/41 |
| LCM, exact-source offline | 36/99 | 65/99 |
| GCD, actual predicted-source GPU feedback | 23/41 | 25/41 |
| LCM, actual predicted-source GPU feedback | 34/99 | 65/99 |

Actual feedback direct/generated counts are GCD 14/26 and 11/15; LCM 45/78 and
20/21. Both graph and independently reconstructed feature/label audits pass.
Exact kernels still authorize effects. This is selected-family prototype
correctness, not full Eggcc inference, learned semantic authority, or speedup.
No global model promotion is claimed against every historical configuration.

A scalar-value census found old enumeration values {0,1} versus {0,1,2,3,4} in
these development inputs. That alone does not explain failures: in the GCD
feedback run, direct inputs with 2/3 are correct 5/6, while inputs without any
query scalar are correct only 1/8. Scalar extrapolation remains a hypothesis,
not the established cause of the remaining errors.

Artifacts: `/Volumes/Extreme SSD/eggfuse-artifacts/21ee/matched-entry-gpu-v1`.
`merged-training-selection.json` preserves every included and duplicate input;
`merged-fit-argv.json` records the exact fitter command. Weights, full fit report,
GCD/LCM rollout arguments, execution captures and labels are saved alongside it.
The tracked collection and ridge result JSONs contain provenance and all reported
validation groups. Binary artifacts are not tracked.
