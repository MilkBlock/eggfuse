# I · Bake 选择与评分

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## I1 · 模板选择、迭代 catalog 与实际工作 credit

启用条件：bake-cell-ownership / cell-iterate；明确 backend。

编译期依据：profile 选代码、typed facts 证明；同工作负载完整执行比较。

替代的旧工作：仅以模板数、静态收益或命中率选方案。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[ownership_bake.rs](../../tools/cell-compiler/src/ownership_bake.rs) · [iterate.rs](../../tools/cell-compiler/src/iterate.rs) · [work_credit.rs](../../tools/cell-compiler/src/work_credit.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/key_lookup_calls [value]`<br>`report:/allocations/alloc_calls [value]`<br>`report:/inference_seconds [value]` |
| 成本 / 剩余工作 | `report:/setup_seconds [value]`<br>`report:/setup_allocations/requested_bytes [value]`<br>`program:/iterative_bake/joins [count]` |
| 覆盖 / 规模 / 回退 | `program:/ownership_fragments/fragments [count]`<br>`program:/iterative_bake/rhs_handoffs/states [count]` |

解释与缺口：work credit 是等权操作差值，不是纳秒模型；训练耗时/峰值内存和单优化边际 ablation 尚未统一进 runtime report，必须看训练产物与实测。 Measured credit includes Free Join probing/grouping/reverse enumeration and Sieve preparation/maintenance. Older incomplete reports fail closed; rejection totals are not savings. Work now charges register_result_writes and cell_query_result_writes once, excluding the prefix field_writes subset. Equal-weight savings remain an uncalibrated proxy; timing intervals crossed equality against all three controls at c8ef6edc. Context shape selection and full artifact validation now precede executable Cell lowering. Only admitted general cuts allocate instructions; Bake refitting and compiler emission need only source-order certificates. The 1481→17 plan count is inferred from validated sum-bits admission and code paths, not timed or allocator evidence. Prefix frames now use dense static Cell addresses instead of full RHS-template slot width. Existing copied-slot credit observes sum-bits 21→14, with copy/clear counts unchanged; each scoped instruction gains a static base word. No runtime translation map, allocation count or speed claim is introduced.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/entry-publications/README.md](../../benchmarks/entry-publications/README.md) · [benchmarks/condition-bake/README.md](../../benchmarks/condition-bake/README.md) · [benchmarks/cell-unification/context-branches-check.json](../../benchmarks/cell-unification/context-branches-check.json) · [benchmarks/cell-unification/context-terminal-check.json](../../benchmarks/cell-unification/context-terminal-check.json) · [benchmarks/cell-unification/query-storage-results.json](../../benchmarks/cell-unification/query-storage-results.json) · [benchmarks/cell-unification/context-selection-check.json](../../benchmarks/cell-unification/context-selection-check.json) · [benchmarks/cell-unification/context-compact-check.json](../../benchmarks/cell-unification/context-compact-check.json)
