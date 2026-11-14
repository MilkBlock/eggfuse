# Use every atom's shared binding evidence for GPU takeover

The previous catalog used only the preferred, first-atom origin of each consumer
input. For `F(a,b), G(b,c)`, the G witness also supplies b, but that knowledge was
not used when laying out G's payload takeover. Some source/consumer combinations
were therefore rejected for insufficient width although all needed values fit.

Compilation first tries the existing layout. If it cannot fit, it uses every
input witnessed by the current atom, including variables shared with another
atom, and attempts compilation again. Only the selected plan reaches the GPU;
there is no second runtime search, fallback graph, or new dynamic control flow.

Keeping an existing fitting plan is intentional: equal e-class roots do not imply
identical original IDs or scalar metadata. An existing plan can preserve that
value by copying it. Newly covered shared-field plans still require the complete
runtime value/metadata checks and all original lifetime, generation, visibility,
reader and ownership checks. A false exact-value alias rejects compression while
leaving semantic execution intact.

For the captured three-rule recipe at width 8, covered plans grow from 7 to 12;
projection/alias/mask arrays grow from 560 to 960 bytes (excluding scalar plan
headers). More plans can cause more transfer attempts; no dispatch or throughput
speedup is claimed. Payload capacity is unchanged.

Actual GCD isolates the compiler change using the copy-only catalog from commit
9785012d with otherwise identical current code, inputs and weights. Owner releases
increase from 30 to 33. Both modes generate 41 Cells, have 15 generated-source
consumers, and preserve Run changes `[true,true,false]`. Graph and label audits
pass. Predicted tokens, targets, target classes, rules and source-origin arrays
are identical; reconstructed features differ by at most 3.58e-7. Thus this is
three additional physical-owner releases on a real workload, not just increased
catalog coverage. This does not change the 36/41 prediction correctness.

All 12 existing synthetic producer-frame inputs also pass; they remain at 9
releases and 62/75 exact predictions. This collection alone does not demonstrate
incremental benefit from the new plans. The earlier no-copy real baseline also
had 30 releases, but the separately executed copy-only control is what isolates
this change.

Tests exercise actual compiled GPU transfer for both atom witnesses without
extra width, rejection when only Eq roots match, and preservation of the existing
copy plan when raw IDs differ. Five existing matched-takeover tests and three
new tests pass, including cross-stage execution and reader/generation boundaries.

`shared-atom-owner-results.json` records results and artifact identities. Full
synthetic runs, real GCD captures and the catalog-isolation runner are archived in
`/Volumes/Extreme SSD/eggfuse-artifacts/21ee/shared-atom-owner-v1.tar.gz`.
The real argv and label commands are `matched-entry-gpu-v1/gcd-shared-atom-owner-*`;
`run-copy-only-gcd.py` in the archive injects only the prior catalog compiler.
No CPU executor path or model training was changed. General matching/effect
authority, producer-frame prediction quality and complete transfer coverage remain
outside the demonstrated result.
