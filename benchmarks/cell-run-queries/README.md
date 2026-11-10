# 在源 Run 内按 Cell 实例完成查询

本页记录 `5f87ba03`。后续构造子接管与真实线程对照见 [Cell 任务内的构造子查询](../cell-constructor-queries/README.md)。

这是 **standalone Cell CPU** 的实验实现，不是 native egglog 的多线程实现。对照为 `13cfd235`；该版本的完整 Raytrace 测量已单独保存在 [上一轮结果](../cell-query-workers/raytrace-full.md)。入口仍为 `--query-workers N --query-grain N`，默认关闭。

本轮已经把符合条件的跨阶段查询从逐规则 Entry 批次改成了源 Run 内的 Cell 实例任务，**尚未建立端到端加速**。worker 仍只承担普通函数的全键查询和标量指令，没有覆盖构造子查询、枚举、RHS 或 repair，也没有测到硬件 cache miss 的下降。

## 上一轮执行揭示的机会

原 4-worker / grain 64 配置在完整 Raytrace 中只执行 26,262 个 Entry，却产生 1,809,576 次逐 Entry 准入检查、1,305,155 次 seed 遍历和累计 335,456,192 字节的 Entry 缓冲容量。这些准备工作可以从既有 Cell Query 的类型能力、Entry 编号，以及 Scheduler 已按 atom 排列的 seed 推导掉。

执行器原本就先完成一个源 Run 内的全部 LHS，再执行任何 RHS。因此同一实际 Cell 在这个边界内服务不同规则的 Entry 可以交给同一个任务，无需逐规则提交和等待。跨 Run 能保留的是模板指令、已发布的实例槽位和现有 receipt；可变函数当前值、后续输入、union 触发的匹配、watermark 仍然必须在当前 Run 检查。本轮没有提前执行未来 Run。

## 接管与剩余成本

- 从现有 Query 编译每个规则的 Entry 能力掩码和所读函数集合，在缓冲之前排除完全不适用的规则。没有另建查询 IR、事实图或实例绑定副本。这张掩码在运行器装载计划时推导一次，尚未序列化为 Bake 的直接任务目录。
- 已选中的 Entry 保留原 `Rc<Row>` 和 Cursor，在协调线程的移动队列中按实际源 Cell 分组。同一 Cell 的合格 Entry 可以跨规则连续执行；不同模板在 chunk 边界分开。源地址依据实际返回事实的 owner/context，不把 `(逻辑生产者, RHS 操作)` 当作事实地址。
- worker 借用原字段、Query 和函数槽位，复用临时结果/见证帧。失败的查询由这里完成，不回原 host 再查询一次。旧 `spine_batch` 缓冲和逐规则等待路径已删除。
- residual host 对已有 atom 顺序的 seed 做两次二分定位，删除反复扫描全体 seed 的筛选循环；这一边界 host 仍保持原来的执行组织。
- 恢复 Entry 的原位置，再沿用深度、key 去重和 Cursor sealing。Stage 胜者仍位于 residual binding 之前；原本需要的最终去重延迟到交回时执行一次。全部读取在 RHS 前结束，保留 source Run、delta ownership、watermark、可见性、history 和存活检查。

当前负载均衡是 **保持 Cell 完整的 grain 分块 + Rayon 工作窃取**，不是按查询耗时权重分配，也没有跨 Run 的线程亲和性。`worker_steps` 记录实际执行的指令数，不能冒充 CPU 时间或经过标定的权重。当前最大 Cell 有 974 个合格 Entry，可能限制单个 Run 内的均衡；没有为了均衡把它再次打散。

完整 Raytrace 的工作量对照见 [checks.json](checks.json)。这里的次数不代表 committed mutation；容量也不等于 allocator 调用数。

| 工作 | 原 4-worker g64 | Cell 4-worker g64 |
|---|---:|---:|
| 执行的 Entry（含 inline） | 26,262 | 29,649 |
| 其中函数 key 读取 | 28,016 | 31,784 |
| 逐 Entry 动态准入检查 | 1,809,576 | 91,349 |
| seed 遍历 | 1,305,155 | 27,674 |
| Entry 头缓冲累计容量 / 字节 | 335,456,192 | 2,134,728 |
| 模板 Entry 位检查 | 无此路径 | 1,231,139 |
| seed 二分比较 | 无此路径 | 110,872 |
| Cell 归组与恢复顺序比较 | 无此路径 | 378,802 |
| 串行胜者原位置登记 | 无此路径 | 344,736 |
| 胜者顺序比较 | 无此路径 | 242,966 |
| 临时帧分配 | 870 | 1,933 |

新版还增加 56,872 次延迟胜者移动、34,111 次完成时 binding 移动、29,649 个借用任务头。复用队列增长 12 次，峰值容量 1,966,080 字节，和累计头容量分别计量。每个配置的原始计数器都已保留；CellPlan 初始化的向量、Value 内部分配和全部排序字节流量没有单独计量，不能声称这是全量分配或缓存统计。

26,060 个 Cell/Run 组中，1,040 组有多个 Entry，48 组合并了不同规则的查询。2,481 个 Entry 因整个 Run 小于 grain 而在协调线程完成，其余由 pool 执行。全程 4,195,491 次 key 查询没有减少，受新 host 覆盖的读取仅约 **0.76%**。这仍不是“一个线程完成 Cell 的全部查询”。

Bake 账本收取掩码、二分、归组、头部及恢复顺序/移动成本，不给覆盖量加节省分。sum-bits grain 1 相对 `13cfd235` 的同配置净减少 **518** 项等权操作，见 [work-sum.json](work-sum.json)。它不是耗时模型；仅看准入/缓冲降幅会高估本轮价值。

## 完整 Raytrace 实测

Apple M3 Max / 16 logical CPU；普通 release `sparse-cells,view-ports,storage-metrics`，统一冻结 artifact。每配置预热一次、交错测量三次，合计 16 个完整新进程；计时期间没有 Cargo 编译或源码修改。机器仍有交互应用运行，未控制系统负载。详见 [timing-summary.json](timing-summary.json)、[原始样本](timing-samples.json) 和 [命令清单](timing-manifest.json)。

| 配置 | 推理中位数 / 秒 | 进程 wall 中位数 / 秒 |
|---|---:|---:|
| `13cfd235`，关闭 worker | 10.669 | 13.622 |
| `13cfd235`，4 worker / g64 | 10.779 | 13.691 |
| 本轮，关闭 worker | 10.601 | 13.448 |
| 本轮，4 worker / g64 | 11.561 | 14.615 |

新版 4 worker 的中位数比旧版 4 worker **高 7.3%**。按同一交错轮次计算，耗时比中位数却是 **0.984**，三对样本的 bootstrap 95% 区间为 **[0.972, 1.087]**；相对本轮关闭 worker 的区间为 **[0.958, 1.109]**。这批数据存在明显波动，既不能取其中较快的两对宣称成功，也不能忽略较慢的整体中位数。平均进程 CPU 约 1 核，没有建立线程扩展收益。

后续应优先减少任务准备和恢复顺序工作，并让同一套 Cell 任务覆盖真实构造子查询热点；只增加线程数或调整这些少量查询的权重解决不了当前覆盖限制。

诊断注意：延迟执行后，`view_rule_profile.search_s` 只覆盖该规则在协调线程的准备和同步查询，**不包含 Run 末尾的 worker 完成时间**；完整 `steps[].phases.search` 包含这些工作。当前不可用该逐规则时间给 Bake 或调度器标定权重。

## 语义检查与复现

- 51 项集成测试通过：Entry 发布、query receipt、query workers、scoped/staged completion、stable ports；5 项 work-credit 单元测试通过。最后计数器修改后重跑 query worker/receipt 的 12 项测试。
- 新的多规则测试比较全部 Run 图快照和有序绑定，覆盖三个消费者读取同一 Cell、同 Run 的 RHS 修改函数但不得影响其他 LHS、下一 Run 看到修改，以及生产者复用其他 Cell 已有结果。
- 最终 release 的 off/inline 1/pool 2/pool 4 对照旧二进制，sum-bits 和普通/碰撞短例共 15 个进程，最终图及 Run 签名一致；短例还比较每个 Run 完整快照和有序绑定。
- 指定的 `choice_diagnosis.py` 复用已保存 native exports，对 sum-bits 给出 `status: pass` / exit 0，没有扩大证明规则。
- 最终二进制的完整 Raytrace 及全部 16 个计时进程，与旧版最终图和 16,883 个有序 Run 签名完全一致。这不是独立 native Raytrace 证明，也没有把最终图对照称作全部中间图快照对照。

常规 README 的 Cargo compile/run/bench 入口用短例 smoke 验证；bench 只跑一次，不作为速度结果。默认和 all-features runtime 的 `cargo check` 同时检查。构建输出、完整图和日志位于未跟踪的 `out/cell-run-queries`。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts --test entry_publications --test scoped_completion --test staged_completion --test stable_ports
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --lib work_credit
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
python3 benchmarks/cell-query-workers/check.py CANDIDATE BASELINE SUM_PROGRAM FIXTURE_PROGRAM SAVED_SEMANTIC OUTPUT --baseline-commit 13cfd235
python3 benchmarks/marker-handoff/choice_diagnosis.py OUTPUT/semantic OUTPUT/semantic-acceptance.json
python3 benchmarks/cell-query-workers/raytrace_measure.py measure MANIFEST TIMING_OUTPUT --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/cell-run-queries/collect.py out/cell-run-queries benchmarks/cell-query-workers/raytrace-results/summary.json benchmarks/cell-run-queries
python3 docs/optimization-catalog/catalog.py check
```

使用新的输出目录。复现计时需把清单中的二进制/程序路径改成当地路径；二进制和程序 SHA-256 保存在结果中。收集脚本只读取既有输出，不重新运行工作负载。
