# Cell Entry 直接交接，残余输入按所有权分开

对象为 **standalone Cell CPU**，基线 `7338103d`。本轮检查短例与 Raytrace 前 128 个 Run 的语义和工作量，没有完整速度测试。完整多线程加速仍未证实；上一轮完整实测是 `ae123cf9` 的四 worker 9.706 s、同路径 inline 9.411 s。

## 已有执行暴露的重复交接

前版 sum-bits 生成 12,066 个消费者 Seed，其中 5,738 个随即进入 Cell 查询；Raytrace 前缀有 52,057 个 Seed，其中 25,285 个进入 Cell 查询。路径为：

`已验证的共享 Entry → Seed + route 下标 → 再取 Row/pivot → Cell 查询`

进入 Cell 的判据是当前发布 Cursor 存在，且原 Cell 模板为该 pivot 提供完整查询代码。这个查询直接从原 Row 的列读取参数，Seed 的消费者投影和 publication handle 在这条路径上没有读者。因此模板事实已经足够，不需要 Bake 再学习一份运行时事实表。

## 实际接管

调度器现在把 `(pivot, 原 Row 引用, Cursor)` 直接交给 Cell 查询完成路径；只有未被接管的输入生成残余 Seed。`early_join` 的空 domain 占位也随相应 Seed 删除。Cell 交接记录按原 `(witness, pivot)` 排序，保留源 Entry 胜者顺序。

对于混合查询，残余输入已经排除了 Cell 所有的 Entry，因此删除这一已覆盖部分的 `BTreeSet<(pivot, witness)>` 登记及后续 Seed 筛选。残余查询仍从原图读取全部事实；变化的是驱动查询的输入队列。覆盖数独立携带给原来的完成统计，不能再用残余 Seed 数推断 Cell 覆盖规模。

模板的完整查询能力负责决定接管资格；当前 Run 的激活、Entry 谓词、watermark、可见性、实际 Row 来源及生命周期仍由原路径验证。原 Run/RHS 顺序、晚到输入、union 激活和残余枚举保持有效。若直接交出的 Entry 意外失去查询 owner，执行报错，不能悄悄当成没有匹配。

`family-survey` 的观察器需要完整 Seed 流，保留带排除集合的路径，并有独立回归检查。普通默认构建和 sparse-cells 都使用直接交接。既有 history/local-witness Cell 仍在其原查询 host 完成，也可省掉这个 Seed 中间层。没有扩展 worker 的查询能力或增加持久化反向订阅。

## 工作量与存储边界

| 同配置对照，旧版 → 本轮 | sum-bits / g64 | Raytrace 前 128 Run / g64 |
|---|---:|---:|
| 消费者 Seed 记录 | 12,066 → 6,328 | 52,057 → 26,772 |
| 直接交给 Cell 的 Entry | 5,738 | 25,285 |
| key 查询调用 | 18,692 → 18,692 | 88,737 → 88,737 |
| worker Entry 数 | 1,907 → 1,907 | 21,186 → 21,186 |
| 净减少的等权操作 | 6,293 | 27,099 |

sum-bits grain 1 压力配置净少 7,218 项操作，原短例 grain 16 净少 417 项。收益来自 Seed 记录及原有 seed-range/selection 计数下降；少量临时候选容量增长受线程分配影响，正负差值均保留在账本中。

本轮把旧报告已经具有的 `entry_schedule/stats/consumer_seed_deliveries` 加入 work-credit，两边都收费。它统计实际生成的 Seed 记录，与后续 worker 任务头属于两次不同的中间交接。新增 `cell_entry_deliveries` 只表示接管规模，不产生额外负成本或重复奖励。等权账本仍不能代替时间测量。

当前 release 布局中 Seed 为 24 字节，旧 route 记录为 176 字节，直接 Cell Entry 为 184 字节。后者多携带一个 Row 指针，同时省掉相应 Seed 记录及其消费者引用；Row 数据本身继续共享。上述值是记录布局，排除 Vec 剩余容量、排序临时存储、引用对象及 allocator 开销，不是总分配或 peak RSS。`borrowed_slots` 原来是 Seed 投影规模，随 Seed 下降；它不是减少字段读取次数的证据。

上游 Entry 刷新、Cursor 展开和逐规则 route 排序仍在。Cell 任务索引、RHS、repair 也继续有成本。本轮不把 Seed 删除量解释为查询减少、缓存 miss 改善或完整线程加速。

## 检查

- 15 项 query worker/receipt 测试、62 项 runtime 单元测试和 5 项 work-credit 测试通过；额外 1 项 `family-survey` 混合路径测试通过。
- 新源 [cell-entry-partition.egg](../../tools/cell-compiler/tests/fixtures/cell-entry-partition.egg) 同时包含已发布 Cell 和初始无 Cursor 的事实，检查残余枚举、标量拒绝、晚到函数值、删除重建；比较完整 Run 图和有序绑定。
- release 在 sum-bits、普通/强制碰撞短例、新混合短例中分别执行旧版、off、inline 1、pool 2、pool 4，共 20 个配置。最终图和 Run 签名一致；短例还比较全部 Run 快照和有序绑定。
- 新混合短例经 CLI Bake 后选择已有 context，worker 查询数为零；其 release 覆盖检查要求实际 Cell 直接交接及残余查询均存在。未 Bake 的集成测试覆盖 worker 路径。对两个版本的图、Run 和绑定比较全部保留，没有放宽语义条件。
- 指定 `choice_diagnosis.py` 复用已保存 native exports，对 sum-bits 返回 `status: pass` / exit 0。sum-bits g64 的最终图与这份验收图相同。新增短例是源 checks 和旧 runtime 回归，不扩张该 native 证明范围。
- Raytrace 仅检查前缀最终图和 128 个 Run 签名；默认/all-features `cargo check` 和 README Cargo compile/run/bench 短例入口通过，bench 仅一次 smoke。

## 复现

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake,eggfuse-cell-runtime/family-survey --test query_workers partitioned_cell_entries_keep_mixed_enumeration_and_late_inputs
cargo cell-compile --source tools/cell-compiler/tests/fixtures/cell-entry-partition.egg --output OUTPUT/fixture
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py CANDIDATE BASELINE SUM_PROGRAM FIXTURE_PROGRAM SAVED_SEMANTIC OUTPUT/checks --baseline-commit 7338103d --extra-fixture OUTPUT/fixture/program.json
CANDIDATE_QUERY_PREFIX RAY_PROGRAM OUTPUT/ray-prefix-after 128 4 64
CANDIDATE --program SUM_PROGRAM --output OUTPUT/sum-g64-after --local-congruence --query-workers 4 --query-grain 64
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --example compare_work -- OLD_REPORT NEW_REPORT WORK.json
python3 benchmarks/cell-entry-partition/collect.py out/cell-activation-tasks OUTPUT benchmarks/cell-entry-partition
python3 docs/optimization-catalog/catalog.py check
```

旧版 worker 报告复用 `out/cell-activation-tasks`。分别生成 `work-sum.json`、`work-fixture.json`、`work-sum-g64.json`、`work-ray-prefix.json`；collector 验证二进制/report 哈希关联、图/Run/覆盖一致性，并检查 `旧 Seed 数 = 新 Seed 数 + 直接 Cell Entry 数`。详细证据见 [results.json](results.json) 和相邻工作账本。构建、完整图和原始日志保留在未跟踪的 `out/cell-entry-partition`。
