# Request-dependent cross-stage Cell templates

This experiment runs the standalone Rust Cell engine on complete eggcc Pass 3 programs. A learned parent can issue a conditional continuation before its own match is accepted. The compiler supplies its typed branches. The source controls which winning effect returns a physical row, when a consumer is allowed to read it and whether its binding wins an original RHS ordinal. The comparison uses the two frozen CPU neural checkpoints from the 98% path. Unassisted publication, union/rebuild and boundary work remain part of the timed execution.

## How a conditional Cell executes

1. The compiler recognizes a single constructor entrance with an integer literal and a sibling entrance on the same constructor/column with a strict greater-than guard. It verifies the table schema, the fresh variable layout, the primitive's Unit result and the consumer's ordered input projection. Training picks a producer effect; the runtime checks its actual source definition again on each program.
2. When a trained single- or multi-witness producer emits an instance, its root recipe carries the static request and the producer's generation. Only the root that actually wins can attach the request at its source effect. Spine provides the published physical witness after source repair. An existing constructor returned by an effect is eligible if that precise return is published.
3. The verifier reads the constructor's immutable i64 key and resolves equal, greater or neither. The choice stays private. At the original consumer Run it checks source address, generation, visibility, delta watermark and the compiled layout. Other consumers, including the separate rule that reads tuple length, keep their own entrance.
4. The **flat** control issues both possible branch intents; their normal source predicates decide which can win. **Dispatch** selects the signed comparison outcome and retains ordinary binding verification. **Baked** directly projects the certified branch's slots and primitive result and binds them to its typed parent. The **recursive** form can inherit its owner's request and previously supplied length when the next source effect provably computes the new length by subtraction. It checks that prediction against the value actually published. The executor always preserves the original source Run of each write. Expired-ticket and shadow controls drop back to the prior independently audited neural path.

For example, the first-round sum-bits producer at Run 106, RHS #692 publishes its effect 5 at physical Cell 820, operation 5. Its recorded length is 4. The later Run 110, RHS #875 is actually supplied by the selected greater-than child. The experiment also measures source publications with length 1. A legal branch is a necessary condition for a future source binding and can remain unused.

## Two actual Bake rounds

The initial compiler scan uses all four training families and no evaluation traces. The learned seed is source rule 138, effect 5. Across 333 training publications, 82 lengths equal one and 251 exceed one. The second round executes that precise new library on the four native training graphs, measures actual later consumption, then adds at most three upstream source effects that reached the learned greater-than consumer in at least two families. These are (144, 2), (142, 2), (140, 2). This expands the portion of the source forest sharing a guarded branch. A statically proved recursive handoff reuses the prior conditional's owner across the decrement path. [Train-only candidate census](catalog.json) · [Observed first-round executions and grown catalog](growth.json)

| Workload (source RHS count) | Winning children R1 → grown, either seed | Longest guarded chain | Independent flat / grown baked / inherited request / base complete ms, seeds 1703 and 1709 |
| --- | ---: | ---: | --- |
| sum-bits (7,265) | 14 → 90 | 5 | 101.79 / 103.10 / 105.83 / 104.78; 100.52 / 101.60 / 100.39 / 102.53 |
| dot-product (6,704) | 15 → 44 | 6 | 101.47 / 101.24 / 102.04 / 102.45; 108.52 / 109.78 / 102.66 / 107.35 |
| gemm-bias-relu (15,462) | 63 → 194 | 10 | 311.14 / 308.85 / 308.52 / 312.36; 321.41 / 323.07 / 319.97 / 324.35 |
| stable-argmax (8,190) | 30 → 95 | 7 | 97.72 / 99.01 / 97.31 / 99.95; 101.24 / 102.75 / 101.32 / 101.86 |

Every positive arm has the same complete ordered source RHS, effective writes, actual Spine resumes, unions and final graph as its reference, with both neural providers running without residual search. All benchmark arms preserve at least 98% direct physical-cell coverage. The source graph already gets these RHS with the ordinary joint engine. The child counts above identify work **replaced** inside that trajectory. Flat and compact controls match the same winning child/parent ordinals, effect ports, physical rows and versions; rejected speculative branches can change later emission serials. The frozen policy and the two Bake rounds show substantial attributable takeover within this family, but no consistent whole-pass speedup across seeds and workloads. The scope is small relative to the 6,704–15,462 source RHS in these programs. [Raw work, examples and eight resident samples per timed arm](results.json)

The native request byte counter describes a logical envelope, not total RSS or saved allocations. The first-round overlay uses a typed request attached to a Rust recipe and a live table of pending source generations. A compact child can reuse static projection fields; a skipped numerical comparison and a reduced root wire are separate counters. Full root-wire serialization remains enabled outside the taken-over region. Pure provenance diagnostics run outside the paired timer.

## Does the next owner retire the intermediate persistent record?

A separate round-two control checks the source table generation, the exact previously consumed port and its version, and that the consuming monotone watermark advanced beyond that immutable source version. Only then can the next published child remove the old family's pending descriptor. Independent ordinary graph readers and their physical data remain accessible. In sum-bits the source delivered 82 such retirements per seed. The peak number of pending descriptors changed from 104 to 85 (12,480 to 10,200 bytes of occupied payload); dot-product delivered 43 retirements and the peak changed from 56 to 51. GEMM delivered 181 retirements (peak 228 to 203), stable-argmax 91 (116 to 99). The native hash map also reports allocated capacity separately: occupied payload is not RSS. The release arms preserve every child winner, but the paired complete timings are mixed. [Paired descriptor retirement](retirement.json)

## Reproduction

Use the external workspace environment with the frozen source families and image exports. Every output directory must be new. The builder checks out the joint experiment installer from `6c2e1583` and builds the corresponding native crate privately with Cargo. Executing the compiled session requires no Python inference.

```sh
dir=benchmarks/pass3-cell-gpu/higher-order-bake
e="$EGGFUSE_ARTIFACT_ROOT"
families="$e/repair-bake-families-20261120"
ref="$e/pass3-atlas-integration-20261120"
caps="$e/recurrent-compositions-20261120"
train="$e/recurrent-compositions-train-20261120"
python "$dir/bake.py" "$families" "$train" "$e/NEW-guard-catalog.json"
python "$dir/build.py" "$e/NEW-guard-build"
python "$dir/study.py" "$e/NEW-guard-build/session" "$ref" "$families" "$caps" "$train" "$e/NEW-guard-catalog.json" "$e/NEW-guard-study"
```
