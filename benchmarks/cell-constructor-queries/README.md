# Cell 任务内完成构造子查询

本轮针对 `5f87ba03` 中的实际限制：函数 point-query host 只承担完整 Raytrace 约 0.76% 的 key 读取，而 `lookup_port_key` / signal 域仍留在协调线程。实现对象是 **standalone Cell CPU**，不是 native egglog。仍通过 `--query-workers N --query-grain N` 显式启用，默认关闭。

## 共享现有 Cell 数据的完整查询

`Query::point_tables` 从原指令推导无枚举的完整 key 查询能力，覆盖普通函数及有完整稳定字段覆盖的构造子。原 Step 的参数、结果约束和标量语义保持唯一；没有第二套查询 IR。运行时准入要求图 settled、查询表的全部存活构造子均已被共享端口表示覆盖。缺乏该证明的表、Unit 专用存储、枚举和已有 history/context/local-witness 路径继续由原 host 执行。

`query_reads.rs` 借用现有函数索引、Cell 生命周期、稳定节点、父关系、组件、模板、birth hint 和边界 signal 域。`constructor_reads.rs` 在 worker 中执行全部候选定位、跨阶段分组跳过、静态字段用途定位、精确 key/Eq 检查和结果读取。协调线程不再先替它枚举候选或建立 read set。

有完整覆盖的构造子表，其相关 Eq 使用全部来自共享 Cell wiring；新 host 不再遍历旧反向依赖补充同一表的候选。birth hint 仍是候选提示，命中必须检查全部参数。失效的提示走完整 signal 域；候选复用临时向量，排序去重后保持原 FactRef 顺序。没有扫描整个构造子桶，没有新增实例消费者表。

任务只取当前结果值、epoch 和实际 Dependency，不解码整个临时 Row。可见性仍在选中原顺序的精确候选后检查，不能因为它被隐藏就擅自改选其他候选。Cell 实际存活元数据和稳定节点共同约束结果；Rust 借用跨越整个只读 Run，RHS 发布前全部 worker 已交回。完整查询替换旧 host 的相应执行，不是失败后再执行一次旧查询。

编译期可复用的是既有模板、静态端口和 Entry 连接；跨 Run 保留原实例与 receipt。union 后的当前 Eq、函数值、晚到输入、watermark、存活及隐藏状态仍是运行时义务。没有提前执行未来 Run，没有移除 repair 或并行化 RHS。

## 所有权、局部性与新增成本

为直接借用原 Cell 元数据，`sparse-cells` 的字段页由 `Rc<[Value]>` 改为 `Arc<[Value]>`；共享 ownership 模板/Shape 同样改为 Arc。没有克隆图或一套绑定，也没有把整个 Graph/Cursor 标为线程安全。`Rc<Row>`、Cursor、history 和发布仍在协调线程；worker 只借用内部不可变数据，不克隆这些 Arc。原串行字段页/模板克隆会承担原子引用计数成本，计时中的关闭 worker 配置同时测量这个布局影响。

同一实际 Cell 在一个源 Run 内的合格 Entry 仍连续交给一个任务，跨规则复用临时结果、见证和候选帧。负载均衡依然是保持 Cell 完整的 grain 分块加 Rayon 工作窃取，不是耗时加权或跨 Run 线程亲和性。大量 chunk 仍反复创建临时帧；这是真实剩余成本。

扩大覆盖的首个完整诊断出现 22,564,887 次归组/恢复顺序比较。本轮接着改为只排序 `usize` 任务下标，原 Cursor 队列保持源顺序，结果直接写回原位置，删除第二次排序和排序期间的大块 Cursor 移动。新增下标、结果槽初始化和写入均计入 work-credit；临时结果槽不构成跨 Run 的事实存储。

`cell-run/v2` 报告增加构造子查询工作和上述顺序成本。原 signal 域、端口读、根解析和 Eq/key 检查折回原计数器，避免与 marker/Cell 路径重复收费；仅额外的元数据读取、候选向量增长/排序、下标和结果槽操作在新计数器收费。覆盖数和答案数不赚取节省分。计数器不是硬件 cache miss、allocator 总调用数或 wall-time 权重；当前逐规则 `view_rule_profile.search_s` 仍不包括 Run 末的延迟查询，完整 Run search 阶段才包含它们。

## 完整 Raytrace 工作量与实测

全部 20 个预热/计时进程的最终图和 16,883 个有序 Run 签名一致。新版完成 1,076,546 个 Entry、1,097,825 次 key 读取，其中构造子查询 1,063,132 次；对全部 4,195,491 次 key 读取的覆盖从 **0.76% 提升至 26.2%**。19,529 个 Cell/Run 组合并了跨规则查询。读取只是换了执行位置，全部 key 调用数未下降。

下标归组把比较次数从本轮首个诊断的 **22,564,887 降至 11,326,502**，同时增加各 1,076,546 个下标、结果槽初始化和写入。仍有 27,845 个 chunk、55,058 次临时帧分配及 2,439 次候选向量增长；Entry 头累计容量为 77,511,312 字节，原 Cursor 队列峰值容量 7,602,176 字节。这些是指定缓冲区计量，不是总分配或 peak RSS。

| 同轮配置 | 推理中位数 / 秒 | 进程 wall 中位数 / 秒 |
|---|---:|---:|
| 历史串行二进制，重新运行 | 10.040 | 12.752 |
| `5f87ba03`，4 worker / g64 | 9.631 | 12.543 |
| 本轮，关闭 worker | 9.913 | 12.592 |
| 本轮，inline 1 / g64 | 9.411 | 12.140 |
| 本轮，4 worker / g64 | 9.706 | 12.527 |

**四线程仍未建立加速。** 相对上一版四线程，推理中位数增加 0.8%，成对耗时比区间为 [0.984, 1.072]。相对同一新版 inline 路径，三对样本均更慢，成对中位比为 **1.031**，区间 [1.0002, 1.124]。相对历史串行的区间 [0.967, 1.034] 也跨过 1；不能用较低的独立中位数宣称胜出。

新版四线程的全进程平均 CPU 为 **1.035–1.037 核**。首个样本的 worker Entry 分布为 [282382, 262502, 257188, 243440]；这不是 CPU 权重，但也没有显示旧方案那样悬殊的数量差异。实际瓶颈仍包括协调线程准备/交回、很多小 chunk，以及尚未接管的枚举、RHS 和发布。接下来先减少重复帧分配和准备，再依据真实热点扩大 Cell 任务，而非只调线程数量。

## 验证

- 84 项集成测试通过：query workers、query receipts、Cell ownership、stable ports、union digest、repair ports、scoped/staged completion。另 61 项 runtime 单元测试与 5 项 work-credit 测试通过。下标归组改动后重跑 13 项 worker/receipt 测试。
- 新测试涵盖多参数构造子的两次独立 union、旧 birth hash 失效后的正候选、标量不符、隐藏、删除重建；比较每个 Run 的完整图和有序绑定。普通无覆盖后端仍验证回退。已有 snapshot/COW 与共享模板指针检查继续验证相同共享语义。
- 最终 release 的 off/inline 1/pool 2/pool 4 与旧二进制在 sum-bits、普通/碰撞短例中共运行 15 个进程，图和 Run 签名一致；短例还比较全阶段快照和有序绑定。
- 指定 `choice_diagnosis.py` 复用已保存 native exports，对 sum-bits 给出 `status: pass` / exit 0，没有放宽证明。
- 默认/all-features `cargo check` 和 README 的 Cargo compile/run/bench 短例入口通过。bench 仅一次 smoke，不作为速度结论。

完整 Raytrace 结果、工作量、哈希和计时见 [summary.json](summary.json)、[samples.json](samples.json)、[checks.json](checks.json)。对照检查最终图及全部 16,883 个有序 Run 签名；不是独立 native Raytrace 证明，也不是所有中间图快照对照。

sum-bits 的 grain 1 覆盖检查比 `5f87ba03` 同配置净**增加 30,615 项等权操作**，见 [work-sum.json](work-sum.json)。新增调度/帧/顺序工作超出该小例上省掉的旧域遍历和 Row 读取，Bake 不能因覆盖上升给出正节省分。它不是 grain 64 的速度结论。

## 复现

计时使用 Apple M3 Max / 16 logical CPU、普通 release features `sparse-cells,view-ports,storage-metrics`，统一冻结 Raytrace artifact。五个配置各预热一次、交错测量三次；计时期间不编译或修改 runtime。交互应用和系统负载未控制。包括旧串行配置、上一版 4 worker、本版关闭 worker、inline 1 和 4 worker；inline 对照用于区分新读取路径收益与真正并行收益。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts --test cell_ownership --test stable_ports --test union_digest --test repair_ports --test scoped_completion --test staged_completion
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
python3 benchmarks/cell-query-workers/check.py CANDIDATE BASELINE SUM_PROGRAM FIXTURE_PROGRAM SAVED_SEMANTIC OUTPUT --baseline-commit 5f87ba03
python3 benchmarks/marker-handoff/choice_diagnosis.py OUTPUT/semantic OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-query-workers/raytrace_measure.py measure MANIFEST TIMING_OUTPUT --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/cell-constructor-queries/collect.py out/cell-constructor-queries benchmarks/cell-constructor-queries
python3 docs/optimization-catalog/catalog.py check
```

使用新输出目录，把 [manifest.json](manifest.json) 中路径换为当地二进制和程序。保留的 SHA-256 将语义检查、计时进程与同一份最终二进制连接；collector 只读取已有输出。构建、完整图和原始日志保留在未跟踪的 `out/cell-constructor-queries`。
