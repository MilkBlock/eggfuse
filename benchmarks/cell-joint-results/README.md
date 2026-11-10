# RHS、Shared Entry 与跨阶段历史共用结果槽

对象为 standalone Cell CPU，基线 `8f4e914f`。本轮接续查询拥有的 Cell 实例，
删除已覆盖 RHS 输出到历史的再次捕获；不扩张 worker 的图写入范围。

## 实际机会与证明

上一版 sum-bits 仍有 1,508 次历史捕获读取和同量槽写。
保存的完整 Raytrace [执行记录](../raytrace-thread-bottlenecks/results/samples.json)
（`lanes/local_serial/samples/0/stage_spine_stats`）有 159,828 次捕获，说明后续 Run 值得接管；前 128 Run
没有历史捕获，不能用它估计完整覆盖。这里只用短例验证，不重新跑完整测速。

原始输出 arena 在发布后清空，历史还供后续 Cell 使用。现在共享 EffectPlan
从原 Cell exports、static_skip、static_sources 和 permanent Entry 输出推导布局：

- 当前状态必须需要该规则全部导出，且有非零历史保留深度。
- 保留发布前缀只有确定执行或被有效 handoff 接管的 effect，全部具有导出槽。
- 最后导出是实际执行的 effect，保证历史逻辑长度与原捕获一致。
- 发布输出最多 32 个、历史端口最多 64 个；更宽或不完整覆盖继续原路径。
- 原始收据审计、完整结构诊断、slot inheritance 开启时保留各自原路径。

RHS 直接在历史的最终端口位置写实际返回见证；查询导出在开始时填入。
剩余非历史结果使用紧凑的临时槽。成功后先登记未覆盖边界，再把这份结果数组
移交给已有 History owner；永久 Entry 发布通过共享模板投影读取同一数组。
没有新增历史 owner、按实例的消费者表、绑定副本或运行时事实图。

发布不清空历史槽。完成记录复用共享路径不需要的 arena 偏移字段，保存待发布
掩码，规则字段的一位区分两种来源。部分 scope 发布后，剩余位仍可继续；
更宽 Cell 不迫使所有完成记录扩张。实际 constructor 见证可以属于另一个 Cell。

Run 顺序、原始结果而非事后补齐别名、最终 Entry 赢家、union forwarding、
存活和可见性检查保持。失败 RHS 丢弃私有数组；已经发生的前序图效果仍遵循
原语义。边界、历史深度及世代沿用已有元数据。

## 工作量与成本

sum-bits 同配置四线程 / grain 64 的 534 个实例共享 1,379 个历史槽：

| 工作 | 前 | 后 |
|---|---:|---:|
| 历史捕获读取 | 1,508 | 129 |
| 历史另存槽写 | 1,508 | 129 |
| 捕获时分配的历史结果数组 | 534 | 0 |
| RHS 开始时分配的共享结果数组 | 0 | 534 |
| 槽初始化 | 12,028 | 12,251 |
| 新增共享资格检查 | 0 | 539 |
| 提前查询导出读取 / 写入 | 0 / 0 | 534 / 534 |
| 发布通过历史 owner 读取 | 0 | 534 |

数组分配是提前发生，不能把“历史 heap frames 为零”当成总分配为零。
上述等权工作净少 394 项；查询转存、初始化、共享检查和发布寻址均收费。
`history_shared_slots` 只表示覆盖，不再给一次收益。掩码检查和清位分别已被
原 `cell_output_slot_reads` / `cell_output_deliveries` 覆盖，不重复收费。

发布后的历史存储 census 与基线完全相同。共享计划占 1,576 字节；Raytrace
前缀仅有 352 字节计划成本，没有共享捕获收益。完整 allocator 请求及新增
存储成本见 [results.json](results.json)，这些不是速度或 RSS 测量。

完成记录保持 184 字节。四线程 execute 的 allocator 请求合计多 5 次，累计
申请量多 1,208 字节，峰值多 1,434 字节；inline 一线程多 8 次，累计申请量
多 1,576 字节，峰值多 1,546 字节。每配置只诊断一次，worker scratch 的首次
分配取决于任务分派，不能把几次请求差值当稳定收益。新增共享布局仍需付费。

## 验证与限制

回归覆盖实际返回他处已有构造子、查询导出、混合可删除边界、删除后重建和
后续 Run。原始审计路径与共享路径的有序绑定、效果、接续、最终图及逐 Run
执行签名相同。另验证共享数组的分配所有权未变，以及 32 位发布状态不会被
误解为 arena 地址。既有 partial scope、Entry、状态继承和 worker 测试保持。

20 个短例配置比较最终图及 Run 签名，fixture 另比较阶段图和有序绑定。
指定 `choice_diagnosis.py` 复用保存的 native sum-bits 导出返回 pass / 0。
Raytrace 128 Run 前缀的图、执行签名和逻辑计数相同。README 的本地
compile/run/bench 短例入口通过。

这不是 native egglog 执行优化，也不是完整 Raytrace native 正确性或多线程
速度验收。RHS 有序提交、合法边界发布、未覆盖历史捕获以及 worker 范围扩展
仍待推进。历史捕获下降不能单独证明加速。

## 复现

冻结基线普通、allocation-metrics runtime 和 query_prefix 二进制，记录 SHA256
到 `OUT/before.json`；同配置已保存的基线导出可复用。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test joint_results --test entry_publications --test scoped_completion --test state_inheritance --test query_receipts --test query_workers --lib
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports --lib
cargo test --locked -p eggfuse-cell-compiler --all-features --test joint_results --test scoped_completion --test entry_publications --test state_inheritance
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py AFTER BEFORE SUM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit 8f4e914f --extra-fixture MIXED
QUERY_PREFIX_AFTER RAY OUT/prefix-after 128 4 64
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics --bin eggfuse-cell-runtime
ALLOC_AFTER --program SUM --output OUT/alloc-after-4 --local-congruence --query-workers 4 --query-grain 64
python3 benchmarks/cell-joint-results/collect.py OUT benchmarks/cell-joint-results/results.json
python3 docs/optimization-catalog/catalog.py check
```

allocator 一线程对照把 worker 数和输出后缀换成 1。保留 collector 所需的
before/after 二进制与导出；完整图和二进制放忽略的 `out` 中，只提交复现脚本
及相关文字结果。本轮没有完整计时活动。
