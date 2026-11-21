# Predict, allocate and seal a whole wave before its first validation

The engine first predicts a vector of physical Cell counts across the active source rules. The cap is shared across all predicted templates. It allocates a private contiguous slab of headers whose records own their fact backing. Explicit logical Cell IDs, indexes and graph effects remain private until original commit. In source order the actual recurrent singleton and multi-parent models issue and seal their selected parents for ALL rules of this Run. Page-scoped forecasts can instead use the count of candidates actually emitted in that page. Only after the complete issue wave does the source verifier inspect its pending candidates, recompute exact conditions, process Spine and publish the original ordered RHS.

The original source also reads all LHS before publishing effects, but ordinarily each rule verifies its candidates before moving to the next rule's generation. Here counters at the first actual verifier call independently partition model offers and physical allocations by whether they occurred before or after that call. These include empty rule sites separately from offers. A correct staged root consumes the actual preallocated fact buffer at the normal allocation point. Record headers move into normal native graph storage. Template-only pooling can let any matching verified root of the same rule use a physical slot. A named slot additionally checks the sealed page, serial, original physical parents/versions, template and epoch. A valid but unserved winner gets its ordinary allocation with its original neural root proof. Withheld, expired or rejected candidates never publish an invented Cell.

The baseline is ordinary learned inference. Wave seals every rule before verification without reserving new storage. Reserve only allocates record capacity. Pool preconstructs real Cells from the frozen Run coverage head; named also attaches each to a specific root token. Optimistic uses a doubled prediction on the shifted log scale and a larger cap. All lanes preconstructs a distinct private Cell for every sealed parent token (32,768 per-Run limit). The model runs online in all arms; no future outcome, exact acceptance trace or oracle is used to issue counts or choose parents.

| Program | Default exact | Original | Wave | Reserve | Pool | Named | Optimistic | All lanes, ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| conjugate-gradient | 354.91 | 621.55 | 633.17 | 678.22 | 662.52 | 659.03 | 675.83 | 674.49 |
| 3mm | 869.47 | 1,863.50 | 1,837.76 | 1,914.97 | 1,909.44 | 1,931.28 | 1,958.71 | 1,987.99 |

| Program / real record arm | Prebuilt / used | Unused | Peak private records | Estimated peak private payload bytes | Fraction of true roots staged |
|---|---:|---:|---:|---:|---:|
| conjugate-gradient / pool | 97,293 / 59,752 | 37,541 | 3,719 | 1,163,392 | 61.9% |
| conjugate-gradient / named | 97,293 / 36,907 | 60,386 | 3,719 | 1,163,392 | 38.2% |
| conjugate-gradient / optimistic | 330,810 / 54,675 | 276,135 | 7,666 | 2,393,408 | 56.6% |
| conjugate-gradient / all-lanes | 326,696 / 96,535 | 230,161 | 7,100 | 2,169,792 | 100.0% |
| 3mm / pool | 232,796 / 137,864 | 94,932 | 8,192 | 2,666,688 | 60.4% |
| 3mm / named | 232,796 / 78,955 | 153,841 | 8,192 | 2,666,688 | 34.6% |
| 3mm / optimistic | 673,058 / 111,680 | 561,378 | 16,742 | 5,442,304 | 49.0% |
| 3mm / all-lanes | 1,066,140 / 228,095 | 838,045 | 15,968 | 4,948,224 | 100.0% |

For both workloads every issued parent and every granted speculative Cell in these whole-wave controls preceded its own Run’s first validation. The all-lanes arms supplied every fresh primary record with zero physical fallback. Across 3mm, 1,066,140 records were built, 228,095 were consumed with their original backing and 838,045 remained unpublished. One individual Run (epoch 847) had 222 scheduled rules, 47 nonempty Run-head grants totaling 7,159 slots, 15,968 issued offers, 9,902 winning bindings and 9,082 actual fresh primary Cells. Rule 122 was granted 590 slots for 438 eventual fresh Cells; rule 137 was granted 311 for 309 fresh Cells. All recorded Run forecasts were independently recalculated from pre-issue inputs. [Largest wave example](example.json)

| Whole-process peak RSS, MiB | Original | Wave | Named | All lanes |
|---|---:|---:|---:|---:|
| conjugate-gradient | 464.19 | 461.31 | 461.47 | 464.31 |
| 3mm | 747.27 | 742.27 | 743.48 | 747.67 |

The physical counter measures primary root allocation, excluding separately allocated nested cells. Its direct and promoted measurements distinguish immediate construction in a speculative record from source executions that require transient scratch before promotion. RSS is the high-water value in three fresh native processes per arm after warmup; it need not grow by the sum of all transient allocations. Inference medians use four rotated resident samples at seed 1703. Both held-out workloads agree on raw model choices, input and effect order per Run, Spine, union, final graph, exact parent origins and physical IDs. [Timings and counters](results.json) · [RSS](rss.json)

## Joint batch verification

The actual parent wave can feed the compiled multi-parent page verifier directly. In its own 3mm comparison, the ordinary wave, compiled block without speculative storage, named forecast + compiled block, and all-lanes + compiled block took 1,853.01, 1,823.21, 1,967.13, 1,911.87 ms respectively. The full all-lanes variant enqueues the identical live parent tokens and consumes exactly the same staged allocation identities with or without compiled block verification. Source effect publication remains ordered. [Same-binary evidence](batch-verifier.json)

```sh
d=benchmarks/pass3-cell-gpu/wave-cell-allocation
python "$d/build.py" "$EXP/wave-private"
python "$d/study.py" "$EXP" "$EXP/wave-private/session" "$EXP/private-training/policy.json" "$EXP/wave-private-run"
python "$d/example.py" "$EXP" "$EXP/wave-private/session" "$EXP/private-training/policy.json" "$EXP/wave-private-example"
python "$d/peak.py" "$EXP" "$EXP/wave-private/session" "$EXP/private-training/policy.json" "$EXP/wave-private-run/results.json" "$EXP/wave-private-rss"
python "$d/build_block.py" "$EXP/wave-private-block"
python "$d/block.py" "$EXP" "$EXP/wave-private-block/session" "$EXP/private-training/policy.json" "$EXP/wave-private-block-run"
python "$d/verify.py"
```
