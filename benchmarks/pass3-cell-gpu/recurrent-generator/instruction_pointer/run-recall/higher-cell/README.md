## Signed higher Cell execution on native EggCC

The donor is the sum-bits iterative Bake catalog. Of 32 joins, 19 had a suffix where each rule's complete independent input could come from one actual returned instruction port. Training-tape counts from sum-bits and dot-product selected one fixed unit per productive root rule (four units). At load time exact serialized rule fingerprints check compatibility. The native receiver separately checks every producer instruction's output type and each consumer's complete relational arity. See [catalog.json](catalog.json) for the wiring and training identities.

The frozen CPU Actor chooses the root and its external parents. A fixed policy associates its rule with a higher template. Instance-specific neural scale selection and RL remain open. After admission, the receiver waits for the actual result, records its version at the next sealed boundary and submits the named child on its first subsequent scheduled Run. Missing exports stop that suffix. Stale versions, false guards and duplicate witnesses use the ordinary verifier. An admitted internal child may arm the next step. Internal exports have unique token IDs and can be referenced by later proposals. Source RHS ordering and visibility remain native.

**Ownership experiment.** The add arm enables the higher templates. The owned arm additionally omits an external leaf request when its exact ordered address and version are already owned by the first internal edge in this Run. This check happens after neural decoding. On the three full programs, that removed 120 requests, 120 duplicate verdicts and 120 named reads versus add, with identical accepted counts and final state in each program. No neural inference saving is attributed to these omissions. The replace arm instead omitted all standalone decoding for suffix-only rules. Withhold applies the same blanket omission with no higher Cells. Each arm runs on its own actual assist trajectory. [Ownership comparison](ownership-control.json)

| Program | Accepted commits, base → owned | Paid external requests | Accepted internal steps (third step) | Signed effective operations | EPT |
|---|---:|---:|---:|---:|---:|
| fact | 1,242 → 1,254 | 3,814 → 3,804 | 86 (28) | 904 → 904 | .23702 → .23764 |
| loopfact | 1,040 → 1,044 | 3,756 → 3,713 | 63 (19) | 805 → 788 | .21432 → .21223 |
| sum-divisors | 8,558 → 8,649 | 24,855 → 24,783 | 376 (76) | 4,929 → 4,951 | .19831 → .19977 |

Across the three programs 582 of 1,060 issued compound roots were accepted. Of 851 internally issued steps 525 were accepted, including 123 at depth three. Missing exports ended 115 continuations. With 20,428 source commits, residual commits fell from 9,588 to 9,481. The residual candidate counter stayed at 26,148. Blanket withdrawal with higher Cells yielded 10,273 signed commits, compared to 9,912 with withdrawal alone and 10,840 with the base Actor. All four arms matched the reference schedule, ordered RHS, writes, continuations, events and final state. [Full assist measurements](assist.json)

The audit attributes visible constructor births at the settled Run boundary, effective function writes, effective unions with their FIFO issuing owner, and visibility changes to external signed requests, internal signed steps or the remaining execution. Every variant checks its ordered operation identities and total counts against an independent exact run. The fully replayed operation ledger is invariant to changing ownership. Totals across programs went from 6,638/32,425 to 6,643/32,300 signed operations per externally submitted token. Charging the 120 decoded proposals omitted before transmission gives 6,643/32,420. No-op commits earn zero effective operations. Higher templates may take credit previously held by a standalone request.

**Throughput.** Four alternating complete CPU trials on each of fact and loopfact used a warm Python service, one Actor thread, a fresh native process, and exact / base / owned / offline-teacher arms. The timed path disables the EPT ledger. Signed operations come from the matching audited trajectory. Fact measured 327.93 → 327.53 signed operations/s and loopfact 305.71 → 294.17. Owned won one pair out of four on each. The oracle and exact process walls are in the [pair records](density.json). Another audit process ran on the host for part of the comparisons. No throughput comparison was run on sum-divisors.

**Independent saturation.** Both policies diverged at Runs 7, 8 and 11. Sum-divisors still hit a source panic at Run 85 with residual search disabled. These experiments use development holdout programs with compatible existing templates. They do not evaluate generalization to novel higher templates. [Search-free execution](exclusive.json)

**Reproduction.** Build the native replay example with the optional cell-token-ept feature. Run these commands from the instruction_pointer directory using the same frozen opaque Actor, exported ROOT and interpreter as the prior assist study. Pass each wanted program to the run command.

```sh
cargo build --locked --release -p eggfuse-cell-runtime --features cell-token-ept --example cell_token_replay
mkdir -p "$ART"
python higher_cell.py compile "$ROOT" "$ROOT/sum" "$ART/catalog.json"
for arm in base owned replace withhold; do
  python higher_cell.py run "$ROOT" "$BINARY" "$WEIGHTS" "$ART/catalog.json" "$ART/$name-$arm.json" --case "$name" --arm "$arm" --ept
done
python higher_cell.py run "$ROOT" "$BINARY" "$WEIGHTS" "$ART/catalog.json" "$ART/$name-add.json" --case "$name" --arm add
python higher_cell.py run "$ROOT" "$BINARY" "$WEIGHTS" "$ART/catalog.json" "$ART/free-$name-owned.json" --case "$name" --arm owned --exclusive
python higher_density.py "$ROOT" "$BINARY" "$WEIGHTS" "$ART/catalog.json" "$ART" "$ART" --cases fact loopfact
```
