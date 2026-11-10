# 从已激活的 Cell Entry 形成查询任务

本轮对象是 **standalone Cell CPU**，基线 `00f33da0`。仅做短例和 Raytrace 前 128 个源 Run 的语义/工作量检查，没有重测完整速度。上一轮完整性能证据仍为 `ae123cf9`：四 worker 9.706 s、同路径 inline 9.411 s，尚未建立多线程加速。

## 机会与模板依据

上一轮完整 Raytrace 仍有 11,326,502 次 Cell 归组比较；`00f33da0` 的短前缀也有 140,137 次。每个激活 Entry 都携带规则、pivot、水位和源 Cell 身份，Run 末再排序、取得查询代码、扫描查询的帧需求。原 Cell Query 已经给出每个 Entry 的固定代码、pivot 和临时槽位上界；它们不需要由每个实例重新描述。

执行器准备 worker 时，从现有 Cell Query 派生共享 `CellCode`，只保存原查询的共享指针及规则、pivot、帧需求。`sparse-cells` 的查询程序使用 Arc，kernel、stage Entry 与 worker 引用同一份 Query；没有复制查询指令，也没有第二套匹配 IR。Arc 只在模板准备/共享时克隆，运行中的 Entry 头借用 `CellCode`，不逐 Entry 克隆 Arc。

跨 Run 可以复用这份代码以及任务缓冲的容量；实际激活、源事实、watermark、当前 Eq/函数值、可见性和存活状态仍由现有调度器及当前 Run 提供。没有从前次成功匹配推断本次必然成功，也没有提前执行未来 Run。

## 删除的路径

- Entry 激活时，直接加入实际物理 Cell 的当前任务。临时索引使用 `(template, actual Cell)`；复用已有构造子的返回值仍按真实来源归组。未知边界保留独立 Dependency，不能假定逻辑生产者就是结果地址。
- 每个 Cell 的 Entry 连接存在一份平坦队列中，模板桶连接其当前活跃 Cell。没有逐 Cell 分配 Vec，也没有持久化生产者订阅表；Run 结束清掉任务索引和连接。后续变化仍由原调度器通知。
- Run 末按模板及 Cell 任务直接生成连续借用头，删除全量比较排序和单独的排列下标向量。原队列上的 Cursor 不移动，成功结果仍通过原位置取回；原规则 ordinal 决定胜者和 RHS 顺序。
- 共享代码保存帧上界，组装任务头时合并上界；worker 不再分别扫描每个 chunk 的全部查询计算两遍宽度，也不重新按编号查找查询代码。
- 当整个 Run 小于 grain 时，它直接成为一个 inline 任务，不构建 Cell 归组索引。若收集过程中达到 grain，已有前缀只归组一次，后续 Entry 直接追加。同一 Cell 不被拆到不同 worker。

这仍使用上游调度器产生的逐规则 Entry 激活；没有消除 Seed、route 和 Cursor 准备，也没有扩大查询覆盖、并行化 RHS 或删除 repair。后续若让 Cell 直接展开静态 Entry 表，必须保留这些激活路径当前承担的 delta、覆盖和边界义务。

## 成本与结果

`cell-run/v4` 对任务索引探查、任务记录、连接、发出/清理、容量增长、代码地址读取和模板访问收费。源码中保留旧排序计数器，其值为零；不能把一个排序比较与一次哈希探查视为相同耗时。等权 work-credit 仍是未经时间校准的代理。

| 同配置对照，旧版 → 本轮 | sum-bits / g64 | Raytrace 128 Run / g64 |
|---|---:|---:|
| Cell 归组比较 | 7,792 → 0 | 140,137 → 0 |
| Cell 来源读取 | 1,907 → 391 | 21,186 → 20,247 |
| chunk 数 | 486 → 203 | 436 → 417 |
| 借用头累计容量（字节） | 137,304 → 106,792 | 1,525,392 → 1,186,416 |
| 原 Cursor 队列峰值容量（字节） | 59,392 → 51,200 | 950,272 → 819,200 |
| 新任务索引/队列容量（字节） | 29,296 | 327,152 |
| 净减少的等权操作 | 7,748 | 22,659 |

均为四 worker，查询调用、Entry 数、答案数、查询指令与结果写入保持一致。新任务顺序的胜者排序仍需收费：Raytrace 前缀从 3,926 次变为 3,934 次。939 个 Raytrace 前缀 Entry 和 1,516 个 sum-bits Entry 走无需归组的 inline 路径。

**结果没有在所有短配置上改善。** grain 1 的 sum-bits 压力检查净增加 1,661 项操作，grain 16 的短例净增加 651 项。其 Cell 索引等新增成本超过原本较少的比较；这些配置不能获得正 Bake credit。不会将正配置的节省套用于它们。

队列和任务头变薄，但新增索引占用内存。本轮 sum/Raytrace 程序的静态代码、准入表和指针目录容量计为 41,304 字节；短例为 1,480 字节。任务内存计量包含哈希表条目容量，排除其私有控制字节；这些指标既不是整体 peak RSS，也不能证明缓存 miss 下降。尚未测量新增索引对完整运行时间的影响。

首版短前缀的账本为净增加 3,220 项。随后直接借用编译代码、删除 worker 的重复代码索引读取，并跳过小 Run 的任务归组，得到上表的最终结果。所有最终数据来自同一份冻结 release 二进制；没有只保留排序归零而忽略新的准备工作。

## 语义与复现

14 项 query worker/receipt、62 项 runtime 单元测试与 5 项 work-credit 测试通过。原多规则 Cell、实际来源别名、隐藏/删除重建、union、晚到输入、空结果后再次激活和原序绑定检查继续通过；小 Run 测试增加任务索引完全不创建的检查。

最终 release 在 sum-bits、普通/强制碰撞短例中运行旧版、off、inline 1、pool 2、pool 4，共 15 个配置。最终图及 Run 签名一致；短例比较全部 Run 快照和有序绑定。指定 `choice_diagnosis.py` 复用保存的 native exports，返回 `status: pass` / exit 0。另比较 sum-bits g64 两个版本的最终图和 Run 签名；其最终图与通过指定验收的 sum-bits 图相同。

Raytrace 仅验证前缀最终图和 128 个有序 Run 签名，不是完整 workload 或独立 native 语义证明。默认/all-features `cargo check` 以及 README Cargo compile/run/bench 短例入口通过；bench 仅一次 smoke，不作为速度结论。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --lib work_credit
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py CANDIDATE BASELINE SUM_PROGRAM FIXTURE_PROGRAM SAVED_SEMANTIC OUTPUT/checks --baseline-commit 00f33da0
CANDIDATE_QUERY_PREFIX RAY_PROGRAM OUTPUT/ray-prefix-after 128 4 64
BASELINE --program SUM_PROGRAM --output OUTPUT/sum-g64-before --local-congruence --query-workers 4 --query-grain 64
CANDIDATE --program SUM_PROGRAM --output OUTPUT/sum-g64-after --local-congruence --query-workers 4 --query-grain 64
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --example compare_work -- OLD_REPORT NEW_REPORT WORK.json
python3 benchmarks/cell-activation-tasks/collect.py out/cell-worker-scratch OUTPUT benchmarks/cell-activation-tasks
python3 docs/optimization-catalog/catalog.py check
```

旧版 worker 执行复用 `out/cell-worker-scratch` 的保存报告；collector 校验二进制/report 哈希关联和图/Run 一致性。分别生成 `work-sum.json`、`work-fixture.json`、`work-sum-g64.json`、`work-ray-prefix.json` 后汇总。证据见 [results.json](results.json) 及相邻工作账本；原始图、构建和日志保留在未跟踪的 `out/cell-activation-tasks`。
