# I · Bake 选择与评分

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## I1 · 模板选择、迭代 catalog 与实际工作 credit

启用条件：bake-cell-ownership / cell-iterate；明确 backend。

编译期依据：profile 选代码、typed facts 证明；同工作负载完整执行比较。

替代的旧工作：仅以模板数、静态收益或命中率选方案。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[ownership_bake.rs](../../tools/cell-compiler/src/ownership_bake.rs) · [iterate.rs](../../tools/cell-compiler/src/iterate.rs) · [work_credit.rs](../../tools/cell-compiler/src/work_credit.rs) · [result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/key_lookup_calls [value]`<br>`report:/allocations/alloc_calls [value]`<br>`report:/inference_seconds [value]` |
| 成本 / 剩余工作 | `report:/setup_seconds [value]`<br>`report:/setup_allocations/requested_bytes [value]`<br>`program:/iterative_bake/joins [count]` |
| 覆盖 / 规模 / 回退 | `program:/ownership_fragments/fragments [count]`<br>`program:/iterative_bake/rhs_handoffs/states [count]` |

解释与缺口：Work credit 是等权操作差值，不是纳秒模型。账本收费实际查询、字段写入、Free Join/Sieve 准备维护、历史、全部 Cell 输出登记/读取/补写/转发解析、实际 receipt 可见性检查、Entry 探测及边界维护；覆盖量、命中、拒绝和子集计数不重复收费，缺失必需字段拒绝评分。静态相同来源输出选择在当前口径节省 1666 项，混合输出改造以来相对 3e622300 累计节省 746 项；不能把初始化槽减少、命中率或少掉的校验另算为全部查找消失。训练/准备耗时、配置期临时集合与分配器全量数据、单优化边际 ablation 尚未统一入评分；新增布局成本已进入 311a3ef8 五提交测速的 setup，但没有单独分配/指令归因。历史保留等结构容器计数不等于总分配字节。整体速度保持与最终并行验收尚未建立。 本步现有补写计数再少 278；不把对应复用命中增加重复计分。单轮配对推理相对直接前版为 0.983497 [0.977410,0.990010]，相对 acab2911/24c4ae8a 的区间跨 1；工作量改善不是该时间差的因果证明。 handoff_attempts 现计入失败预检的实际检查；311a3ef8 只修计数的控制将旧 592 修正为 690，其他工作完全不变。本次前缀接续在这个公平控制下为 592，净少 98 项现有计分操作。闭合失败次数 58→75 不再意味着丢弃/重放，不能把它单独当维护成本；槽/端口读取减少与命中不额外重复计分。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/entry-publications/README.md](../../benchmarks/entry-publications/README.md) · [benchmarks/condition-bake/README.md](../../benchmarks/condition-bake/README.md) · [benchmarks/cell-unification/context-branches-check.json](../../benchmarks/cell-unification/context-branches-check.json) · [benchmarks/cell-unification/context-terminal-check.json](../../benchmarks/cell-unification/context-terminal-check.json) · [benchmarks/cell-unification/query-storage-results.json](../../benchmarks/cell-unification/query-storage-results.json) · [benchmarks/cell-unification/context-selection-check.json](../../benchmarks/cell-unification/context-selection-check.json) · [benchmarks/cell-unification/context-compact-check.json](../../benchmarks/cell-unification/context-compact-check.json) · [benchmarks/cell-unification/prefix-witness-check.json](../../benchmarks/cell-unification/prefix-witness-check.json) · [benchmarks/cell-unification/retention-check.json](../../benchmarks/cell-unification/retention-check.json) · [benchmarks/cell-unification/mixed-outputs-check.json](../../benchmarks/cell-unification/mixed-outputs-check.json) · [benchmarks/cell-unification/publication-winners-check.json](../../benchmarks/cell-unification/publication-winners-check.json) · [benchmarks/cell-unification/output-selection-check.json](../../benchmarks/cell-unification/output-selection-check.json) · [benchmarks/cell-unification/output-donors-results.json](../../benchmarks/cell-unification/output-donors-results.json) · [benchmarks/cell-unification/closed-cells-check.json](../../benchmarks/cell-unification/closed-cells-check.json)
