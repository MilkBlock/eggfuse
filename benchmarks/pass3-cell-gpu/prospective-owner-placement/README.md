# Prospective placement of completed Cell members

The previous [old-owner policy](../owner-action-policy/README.md) could choose between keeping and merging two prepared allocations. In ordinary pooled execution no compiler-checked component covered all members of two existing owners. This experiment changes which members share backing arrays at their first ordinary storage admission. The source rule matcher, member identities, stable external ports and original Run schedule execute in the pinned standalone Rust Cell engine.

At a settled boundary, the store takes the component's currently eligible source members. A complete component is extendable when its current checked shape appears on the input side of a transition in the frozen fragment catalog. A new source-only component can then be stored together in one private owner, avoiding pooling with unrelated components. Once a later source Run adds eligible members to an already-backed prefix, the store can give only those newly arriving members a single separate owner. The old prefix is eligible for this change only if its physical owners have no outside members. A newly eligible, entirely ordinary component is never split. Graph mutations, source seeds and preassembled owner pairs are absent from all arms. The same compiler profile baked independently on each workload is reused across its arms; absolute shape identifiers only compare within that profile.

The controls use stock pooling; isolation of extendable prefixes alone; separate new cohorts alone; isolate only extendable multi-member prefixes and separate new cohorts; and both mechanisms at any prefix width. When the observer encounters two old owners it requires full coverage of both, an extant compiler component, settled effects and a visible external reader. The stream considers at most one new physical group per Run. A distinct group is tracked by its sorted-in-component-order old source/owner mapping; the distinct coverage census also includes the logical shape. Repeated visits to the same owners at later Runs do not give additional action credit. Immediate allocator deltas measure the actual Rust move. The retained graph measurement drops the final native Graph with observer outputs still held, counting requested live heap bytes released. Completed-owner charges count arrays and headers. None of these represent process RSS.

Every run is audited against a separately captured source schedule, ordered RHS inputs, effective writes, actual Spine resumes, union pairs, and final graph. Each attempted action records and compares its old readable facts and external readers immediately before and after. Until the end of the pass, an additional reader digest follows the first issued pair's old sources. The neural policy chooses keep versus consolidate after the exact native matcher has discovered an eligible component; this physical action receives no source RHS or independent parent discovery credit.

## First opportunity on a naturally evolving graph

Dot-product's first complete reader-visible pair occurs at source Run 19 with shape 391. Source 274, born at epoch 17, belongs to owner 127. Source 297, born at epoch 18, belongs to owner 144. Under the keep control the old owners persist. Under merge, the original source 297 now resolves through owner 127, and owner 144 is actually relinquished. Ten external readers and all still-issued source facts were checked before and after. The pair's source ports remain equivalent throughout 1,517 post-action boundary reads and 597 later source unions. The move increased live requested heap by 88 B and incurred a 448 B temporary peak. The frozen return-regression model correctly chose keep at this first opportunity. Stable-argmax also produced a real pair, at Run 15, with member birth epochs 0 and 14 and 25 external readers. Combining its owners increased requested heap by 108 B. [First-issued native controls and source digests](first.json)

The selective comparison additionally runs merge and the frozen gate on the two narrower allocations. Capture resumes at completed arms, writing the original source audit hash and every native placement decision. The faster census first builds a directory of visible consumer Cell identities per canonical e-class at the settled boundary. It uses that directory only to skip groups without an outside reader. A successful offer still undergoes the original full external reader walk, and a deterministic sample of negative observations also checks the full walk. The initial dot-product broad results use the original exhaustive reader observer. The separate placement timers turn off this diagnostic and keep both owners; they measure how much the earlier storage strategy itself costs before adding a trained action.

The natural-data transfer test refits the same nine scalar coefficients using the physical moves actually executed under broad placement on dot-product and stable-argmax. It uses the prepared-data return head's normalization, 160 Adam updates, learning rate, L2 penalty and quantized export. GEMM-bias-ReLU and gated-state receive those frozen weights. Each proposed natural merge still needs a checked source component and complete physical ownership; training learns only the yes/no placement choice. Immediate allocator rewards and terminal graph charges are reported separately.

## Natural opportunity supply and placement cost

The keep arms expose the physical supply without consuming it. Each count is a distinct fully covered owner pair followed by the number actually offered. Eligibility includes components without external readers and the observer offers at most one new group per Run. Bytes compare retained native Graph heap to the same program under stock pooling at the end of the pass. The isolate-only and stock controls both supplied zero on every program.

| Source | Separate late cohort only, eligible / offered | Graph Δ B | Reserve multi-member prefixes, eligible / offered | Graph Δ B | Reserve all extendable prefixes, eligible / offered | Graph Δ B |
|---|---:|---:|---:|---:|---:|---:|
| dot-product | 5 / 3 | +312 | 22 / 20 | +184 | 401 / 144 | +128,836 |
| stable-argmax | 2 / 2 | +0 | 15 / 15 | -520 | 497 / 194 | +159,404 |
| gemm-bias-relu | 9 / 7 | +96 | 24 / 21 | +12,776 | 1,026 / 373 | +334,420 |
| gated-state | 3 / 3 | +0 | 10 / 10 | +10,588 | 407 / 159 | +138,976 |

The broad policy creates real trainable decisions while substantially increasing the cost of housing the original frames. The two narrower policies expose fewer groups. Their low cost on dot-product and stable-argmax does not generalize to reserving multi-member prefixes on every program. [All 46 native arms, old-source read digests and storage accounts](stream.json) · [Deduplicated physical action receipts](actions.jsonl)

## Transfer of the natural-data regression

The broad all-compose training runs emitted 188 dot-product and 220 stable-argmax physical moves. Both held-out programs use the same frozen weights and decision threshold. Positive action rewards below are reductions in requested live allocation inside the move. Final graph deltas include the cost of the altered earlier layout. Each policy encounters its own later components and owner capacities.

| Held-out program | Gate training | Issued / accepted | Sum of immediate savings B | Final graph Δ vs stock B |
|---|---|---:|---:|---:|
| gemm-bias-relu | prepared | 406 / 245 | -6,344 | +339,440 |
| gemm-bias-relu | natural | 406 / 252 | +8,632 | +332,564 |
| gated-state | prepared | 170 / 100 | -3,896 | +141,180 |
| gated-state | natural | 174 / 112 | -1,668 | +139,132 |

Training on naturally formed owners improves the immediate allocation result in both held-out programs. Gated-state still loses bytes in the accepted actions. Both broad layouts leave the complete final Graph larger than ordinary pooling. For example, the GEMM-bias-ReLU natural-data gate would lose 9,560 B on the frozen all-compose state sequence, yet gains 8,632 B when it controls the earlier moves and consumes its own resulting states. [Frozen checkpoint and donor identities](natural-regression.json) · [Fixed-trajectory reward bounds](returns.json)

## Source execution cost of earlier placement

The timing companion executes the source Run schedule, storage admission and both normal boundary compactions with the same audited allocator. It omits the exhaustive candidate census, external reader diagnostics, and the later keep/merge actor. The timer starts after graph initialization and ends before final export. Each sample begins in a fresh process with an initialized graph. Four rotated samples per arm follow warmup. The five layouts have equal final semantic hashes and matching admissions with the independently instrumented keep runs.

| Program | Stock pool | Isolate extendable | Separate late cohort only | Multi-prefix + separate | All extendable + separate |
|---|---:|---:|---:|---:|---:|
| dot-product, inference ms | 32.81 | 33.78 | 33.24 | 33.34 | 32.42 |
| stable-argmax, inference ms | 44.64 | 44.87 | 46.29 | 43.55 | 44.80 |

Measured storage admission plus compaction ranges from 2.31 to 2.63 ms on dot-product and 2.17 to 2.58 ms on stable-argmax. The layout switch does not establish a repeatable whole-pass speedup. [Paired unobserved placement samples](timing.json)

## What these natural rewards teach

On the fixed dot-product all-compose trajectory, 188 actual moves yield 3,712 B on positive events alone. Choosing the better constant action for each observed eight-field feature vector in hindsight can realize at most 3,500 B on this trajectory. The prepared-data regression picks 52 B on the same sequence. In its own native rollout it earns −656 B: early choices change which old owners and later transfers exist. One feature vector `[1,1,3,1,3,1,2,2]` admits changes of −88, +24 and +124 B. This bounds the predictability of that action representation on the measured encounters. It does not bound all alternative physical trajectories. The broad keep placement itself retains 128,836 B more graph heap than stock on dot-product.

## Reproduction

The script uses the pinned native source tree with the existing verified-owner action interface. Populate the four workload catalogs and prepared return weights using the prior [owner policy](../owner-action-policy/README.md) and [owner transfer](../existing-owner-transfer/README.md) recipes. The training source families are disjoint from the two programs passed as transfer tests below. Use fresh output directories on the experiment volume.

```sh
d=benchmarks/pass3-cell-gpu/prospective-owner-placement
python "$d/build.py" "$EXP/owner-action-policy-build-v1" "$EXP/placement-build"
bin="$EXP/placement-build/engine"
python "$d/study.py" "$EXP" "$bin" "$EXP/placement-first" --cases dot-product stable-argmax
python "$d/stream.py" "$EXP" "$bin" "$EXP/place-dot" --all-actions --cases dot-product
python "$d/stream.py" "$EXP" "$bin" "$EXP/place-stable" --all-actions --cases stable-argmax
for case in gemm-bias-relu gated-state; do
    python "$d/stream.py" "$EXP" "$bin" "$EXP/place-$case" --all-actions --cases "$case" \
        --donors "$EXP/place-dot/results.json" "$EXP/place-stable/results.json"
done
python "$d/timing.py" "$EXP" "$bin" "$EXP/place-time"
python "$d/archive.py" "$EXP/place-dot/results.json" "$EXP/placement-first" --additional \
    "$EXP/place-stable/results.json" "$EXP/place-gemm-bias-relu/results.json" "$EXP/place-gated-state/results.json"
cp "$EXP/placement-first/results.json" "$EXP/placement-first/first.json"
cp "$EXP/place-time/timing.json" "$EXP/placement-first/timing.json"
cp "$EXP/place-gated-state/natural-regression.json" "$EXP/placement-first/natural-regression.json"
python "$d/returns.py" "$EXP/placement-first"
python "$d/verify.py" --folder "$EXP/placement-first"
```
