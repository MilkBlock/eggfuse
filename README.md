# EggFuse · Cell CPU

This branch builds the Rust Cell compiler, offline Bake and standalone CPU executor in one Cargo workspace. The compiler uses the vendored egglog frontend for native analysis. The executor runs checked recipe IR, publishes at the original Run boundaries and exports a logical graph.

[优化分类与度量目录](docs/optimization-catalog/README.md)：按被替代的工作整理 9 类、30 组优化，列出启用条件、精确计数器路径、新增成本、验证状态与缺测项。

[规则完成接管](benchmarks/cell-rule-retirement/README.md)：将 Cell 赢家与 residual 的最终合并纳入规则完成任务，协调线程只原地封存 Cursor；Raytrace 这一环节的 93.7% 候选移到 worker。实际实例、全部 Run 摘要及语义验收保持一致；本轮仅验证工作量，尚无新测速。

[Cell 完成事件](benchmarks/cell-completion-events/README.md)：查询结果整理、RHS 就绪前缀接管和 Sieve 后继条件改为事件推动，保留实际实例与结果槽。语义与 Run 检查通过；修正后的计数区分提前接收和真正重叠完成。两轮实测未建立稳定加速，最终四线程 sum-bits / Raytrace 分别回退约 2.3% / 2.7%；源前缀提交及 Run 可见性仍是待拆边界。

[Cell 所有权执行链](benchmarks/cell-owner-chain/README.md)：将已发布 Entry 的枚举、筛选、查询和既有纯 RHS 接续交给 worker，并把 Shared Entry 更新并入索引的表任务。完整 Run 与语义检查通过；本轮四 worker 中位数仅小幅改善，sum-bits 单 worker 仍回退，未建立显著加速，采样仍显示大量池内空闲。

[Raytrace 同步诊断](benchmarks/cell-sync-diagnosis/README.md)：关闭进度日志的两次采样中，协调线程条件等待约 17%–18%，worker 池内空闲约 80%–86%。新增 Unit 登记两轮仅占推理约 0.63%；主要接管机会仍在查询/Entry 准备、发布与剩余串行维护。区分有用计算、等待与调度间隙，保留全部对照和语义验证。

[Worker Entry 范围、Unit 接续与表所有权](benchmarks/cell-entry-owned/README.md)：worker 接管大范围 Entry 枚举、匹配后实际 Unit 候选行构造，以及终端 Cell 的索引/变化登记。完整语义与 Run 对照通过；本次四线程 Raytrace 中位数改善约 2.3%，sum-bits 回退约 7.3%，未通过双样例性能门槛，也未打满线程。保留全部计时尝试及新增成本。

[Cell 继承与并行分支整合](benchmarks/cell-parallel-merge/README.md)：合入 `17d8dbe6` 的全部分支，接通字段变化掩码与并行发布，保留混合域吸收和结果封存。单候选内联、点结果投影与 worker 接管的收益存在覆盖，按实际路径记账。完整样例语义通过；下方两条分支的历史测速不代表合并后的性能。

[最新多线程检查点](benchmarks/cell-parallel-current/README.md)：`9ac332c4` 合并后完整 Raytrace 串行/四线程推理中位数为 5.507/5.240 s，约快 4.8%；八线程 5.734 s，反而较慢。四线程进程平均约使用 1.10 核，worker 在采样窗口仍约 91%–93% 的时间等待；sum-bits 四线程退化。保留全部交错样本与语义检查，尚未打满多核。

[混合 Cell 的查询所有权分派](benchmarks/parallel-cell-partition/README.md)：有 Cursor 的入口保留接续，其余合格入口直接进入共享 worker 队列。完整 Raytrace 新增约 111 万个入口在线程上完成，免除约 84 万次 Seed/domain 交接和约 112 万次邻居缓存发布检查；总点读取不变，队列与结果整理成本已计入。这是工作量与语义验证，尚无新的整体速度或线程利用率结论。

[最新维护优化检查点](benchmarks/cell-maintenance-checkpoint/README.md)：`d7b2b9ac` 的最近五项改动没有建立相对 `2af82c27` 的净加速，反向 Entry 选取和四线程也未建立独立收益。下降的维护计数不能代替耗时；现有证据既不证明全图稠密，也不保证稀疏性足以带来 2×。

[完整测速与源 Run 选择验证](benchmarks/cell-publication-windows/README.md)：当前串行推理相对历史最快对照有收益；四线程尚未建立额外加速，未达到 2×。记录 Raytrace 历史 hoist 选择的边界证据、完整计时及验收限制。

[Cell 变化局部性](benchmarks/cell-change-locality/README.md)：用实际 Get / Expr-size 匹配与提交区分单步扇出、变化后的重复传播和 min 吸收。热点窗口呈现较小扇出，但尚未证明可免除工作或全局稀疏性。

[Cell 的吸收条件](benchmarks/cell-absorption-guard/README.md)：默认关闭的实验在完整 Raytrace 省去 509,296 次绑定及对应单写/完成。五次实现改动相对上次测速版本的 Raytrace 推理配对耗时约降 2.7%；同二进制开关的推理区间仍略跨持平，整进程约降 1.4%。sum-bits 未建立增量收益，四 worker 的 Raytrace 推理约慢 1.7%。保留全部成本、样本及语义检查，未达到 2×。

[Cell 查询并行接管](benchmarks/cell-query-workers/README.md)：复用现有 Entry 和 Query，在源 Run 内并行完成有证明覆盖的函数查询；默认关闭，尚未建立整体加速。

[按 Cell 实例组织查询](benchmarks/cell-run-queries/README.md)：同一源 Run 内跨规则归组、借用实例字段并复用临时帧，保留原发布顺序；完整 Raytrace 的工作量、性能与正确性对照。

[Cell 任务内的构造子查询](benchmarks/cell-constructor-queries/README.md)：借用现有 signal 域完成精确查询，完整 Raytrace key 读取覆盖增至 26.2%；四线程仍未超过同路径单线程。

[Ripsat Cell 直接补全](docs/RIPSAT_CELL_COMPLETION.md)：按已完成局部结构共享推导与静态转换，复用实例结果槽，删除覆盖范围内的 RHS 重放和转存；[验证与成本](benchmarks/ripsat-cell-completion/README.md)。

```sh
cargo cell-compile --case sum-bits --output out/sum-bits
cargo cell-run --program out/sum-bits/program.json --output out/run
cargo cell-bench --program out/sum-bits/program.json --repeat 5
```

Use fresh output directories. Substitute `raytrace` for the larger Pass 3. Both named cases load a small frozen optimization catalog after compiling the source. The compiler checks the suite checksum, the recipe digest and the executable plans before publishing the artifact. A clean checkout therefore reproduces the 64-block configuration with these three commands.

### Implementation priorities

1. **Preserve source semantics and throughput.** Keep structural-key rewriting, bounded native Bake, marker selection and checked Recipe lowering. Keep ordinary Cell storage, canonical repair, compiled register joins, shared parameter slots, single-write RHS and static constructor aliases. These changes together previously took Raytrace inference from 33.81 to 15.50 s. [Throughput ablation](https://github.com/MilkBlock/eggfuse/blob/508e1c8/tools/cell-compiler/benchmarks/runtime-modules/INFERENCE_THROUGHPUT.md)
2. **Retain the winning matching and handoff routes.** Shared entries, Sieve, column intersections, planned Free Join and range guards handle residual matching. Live Spine receipts, compiled blocks and learned RHS handoffs execute at scheduled entries. Uncovered attribute entries can reuse demanded sibling slots and decoded parents. Runtime cardinality and coverage checks keep their original fallbacks. General connected cuts require offline admission. Fresh untrained sources use eligible narrow contexts. [Spine handoff study](https://github.com/MilkBlock/eggfuse/blob/4da35ee/tools/cell-compiler/benchmarks/runtime-modules/RHS_COMPLETION.md) · [Neighbor ablation](https://github.com/MilkBlock/eggfuse/blob/f985eb7/tools/cell-compiler/benchmarks/runtime-modules/NEIGHBOR_CONTEXT.md)
3. **Remove the remaining experiment machinery from the product path.** The branch drops retained-prefix and refutation matchers, presearch surveys, local saturation, union graft, union impact, local congruence, reference-view absorption, composition takeover and experimental slot transfer. It also removes the older CPU driver, Python/UI experiment suite, historical benchmark patches and duplicated plan exports. Those experiments and their measurements are available on the parent research branch. [Research snapshot](https://github.com/MilkBlock/eggfuse/tree/f985eb7)

The normal commands select a single CPU execution strategy. For checkpoint/resume of research snapshots, historical ablation lanes and debugger sessions, use the parent branch. The registered output includes `program.json`, selected markers, the Bake Cell e-graph, source snapshots and a manifest. The branch keeps the whole vendored egglog dependency and native training code needed by Bake. [Minimal CPU measurements](MINIMAL_CPU.md) · [Run-boundary publication study](docs/CHANGE_BATCH.md) · [Incremental Free Join survey and ablations](docs/SEMIJOIN.md) · [Compiled view consumer blocks](docs/VIEW_CONSUMER_BLOCKS.md) · [Pass 3 family opportunity rankings](docs/family-survey/README.md)

### Custom programs and training

```sh
cargo cell-compile --source app.egg --output out/app
cargo cell-compile --source app.egg --bake-source training.egg --catalog catalog.json --output out/trained
cargo cell-bench --program out/trained/program.json --reference-program out/app/program.json --repeat 3
```

A reference-program comparison checks the initial graph and every Run's graph, bindings and schedule before timing. It is intended for small regression fixtures. Offline iterative Bake remains available for a seed program containing validated Spine blocks.

```sh
cargo cell-iterate --program out/sum-bits/program.json --output out/learned --rounds 4 --objective rhs-lookups
cargo test --release --locked --workspace --all-features
```

[Compiler and audit commands](tools/cell-compiler/README.md) · [Workload and catalog provenance](workloads/pass3/README.md)

[Experimental union-digest matching](benchmarks/union-digest/UNIT.md)
is opt-in and supports scalar constructors and Unit-presence markers through
shared graph storage and Entry delivery. Source Run publication is retained;
value-producing/effectful merges, containers and visibility changes remain
unsupported. Application-wide performance gains are unproven.

[Congruence completion expressions](benchmarks/congruence-cells/README.md)
add an opt-in `--congruence-cells` path: immutable applications and shared
equality premises can complete across Runs before table publication. This is
an experimental representation, not yet a Bake-trained or parallel backend.

[Compiler congruence and root continuations](benchmarks/compiler-congruence/README.md)
add the opt-in `rhs-congruence` learning objective. It strengthens cross-Run
constructor proofs and records a root producer's first useful continuation;
measured extra reuse on the current narrow leaf catalog is still small.

[Complete stage entry Bake](benchmarks/leaf-completion/README.md)
extends opt-in leaf admission to dependent table ports and primitive guards.
Wider measured coverage supplies 864 additional complete Raytrace RHSs; the
report separately records the limited extra reuse from complete stage lowering.

[Completed producer receipt nodes](benchmarks/producer-receipts/README.md)
let typed source executions supply cross-Run proofs without a matching entry.
An exact compiler fact index makes the larger candidate audit practical;
measured extra receipt reuse has not improved application throughput.

[Typed result-port repair](benchmarks/result-port-repair/README.md) adds an
opt-in `--repair-ports` path. A compiler-checked key footprint lets result-only
equality changes update a constructor's output without reindexing its body.
Key changes and collision handling retain the ordinary repair algorithm.

[Cell-local union completion](benchmarks/local-unions/README.md) uses whole-Cell
equations to defer new constructor subscriptions and complete internal work from
a finite local list. Actual reverse maintenance, local proof cost and remaining
boundary work are measured separately; `bake-local-unions` rejects candidates
whose observed savings do not cover their costs. The runtime path is opt-in via
`--local-unions`.

[Persistent cross-stage Cell ownership](benchmarks/cell-ownership/README.md)
extends this to live bodies across Runs. `bake-cell-ownership` emits checked
entry/body markers without executing the workload. `--cell-ownership` shares
boundary routing between local completion and candidate matching, retains
internal ownership across stages, and reports coverage and remaining maintenance.
All eligible live scalar bodies are covered, but the final CPU campaign regresses
25.7% / 52.6% on sum-bits / Raytrace: coarse owner traversal remains too expensive.

The experimental `bake-cell-ownership --query-classes true` option compiles
[possible operator use across frozen continuations](benchmarks/stable-port-congruence/query-class-design.md).
The runtime checks the certificate, then skips incompatible groups in its
existing boundary index before visiting instances. It retains exact Eq,
lifetime and ordered-publication checks. Training uses the complete unfiltered
path; absent certificates retain ordinary lookup. This is an opt-in standalone
Cell CPU feature. The [final campaign](benchmarks/query-classes/final/README.md)
improves inference against the preceding shared-code experiment, but does not
establish a whole-process improvement on both workloads or beat the fastest path.

[Shared symbolic repair slices](benchmarks/ownership-slices/README.md) replace
that owner traversal with compiled port programs and incremental boundary bindings.
The sum-bits audit uses 2,098 port checks versus 3,773 in the ordinary backend
(306,860 in the regressed owner-scan version), with identical ordered effects.
New binding and temporary-dispatch costs remain; this iteration records structural
evidence without a validated speedup claim or a new timing campaign.

[Checked cross-template port composition](benchmarks/ownership-composition/README.md)
shares producer/consumer symbols through Entry receipts and replaces temporary
union-dispatch maps with a reusable ordered merge. Sum-bits external bindings
fall from 4,922 to 3,434, with identical ordered effects. The full-cost gate
rejects acceleration: inference is 13.5% slower and process wall time 23.8%
slower than the ordinary fast baseline. Allocation and cold composition costs
are retained alongside structural counters; the backend remains opt-in.

[Baked local repair fragments](benchmarks/ownership-fragments/README.md) remove
the obsolete Owner lifecycle and move composition construction out of production
execution. An explicit profile selects bounded, shared fragments from checked
Entry reuse; unselected continuations retain external boundaries. On sum-bits,
inference improves 9.4% over the previous composition but remains 4.3% slower than
the ordinary fast baseline; whole-process time is 27.3% slower. The performance
gate rejects acceleration despite zero runtime shape construction and fewer
external bindings than uncomposed ownership. Remaining binding access, allocation
and loading costs are recorded alongside exact semantic checks.

[Component-lifetime signal slots](benchmarks/signal-lifetime/README.md) remove
per-field detach reference counting and the global signal binding hash map.
Existing fact liveness filters retained slots; final component retirement cleans
their boundaries. Exact audits pass on sum-bits and Raytrace. Relative to the
previous ownership implementation, inference improves 1.82% / 1.53% and complete
process time improves 1.63% / 13.31%; both workloads pass the paired confidence
gate. The ordinary fast baseline remains faster, so this is a local improvement
to the opt-in path, not an overall acceleration claim.

[Stable ports and dependency-scoped completion](benchmarks/stable-port-congruence/README.md)
starts the structural replacement of canonical field storage. `--stable-ports`
stores covered equality fields as shared symbolic addresses and resolves values
on read; the frozen sum-bits ordered audit is unchanged. Constructor key repair
and the global Run barrier remain in this first step, with separate evidence for
the new read costs. The complete objective includes local congruence conditions,
checked coverage, and independent progress while unrelated regions are pending.

[Cross-stage query receipts](benchmarks/query-receipts/README.md) extend opt-in
Bake to constructor and mutable query ports, with current-value checks and
resumable catalogs. More checked reuse is learned, but the measured catalogs
do not improve total inference time; source capture and publication still cost
more than the small number of global lookups avoided.

[Shared entry publication ownership](benchmarks/entry-publications/README.md)
lets exhaustive entry nodes hold both matching packets and producer expressions,
removing their separate Spine source index. Iterative Bake now defaults to
measured marginal operation credit, charging source history and failed reads;
the previous static score remains an explicit proposal/diagnostic policy.
