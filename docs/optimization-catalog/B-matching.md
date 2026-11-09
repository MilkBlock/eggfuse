# B · 匹配与候选访问

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## B1 · 寄存器 join 与共享 point 读取

启用条件：可编译的 seminaive 查询。

编译期依据：至多一次 Expand，其余为完整 key 或已绑定 primitive。

替代的旧工作：通用环境、逐 atom 解释与重复 point 查找。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[cell_query.rs](../../engine/cell-runtime/src/cell_query.rs) · [row_kernel.rs](../../engine/cell-runtime/src/row_kernel.rs) · [execute_kernel.rs](../../engine/cell-runtime/src/execute_kernel.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/register_answers [value]`<br>`report:/stats/shared_point_hits [value]` |
| 成本 / 剩余工作 | `report:/stats/register_seeds [value]`<br>`report:/stats/shared_point_requests [value]`<br>`report:/stats/residual_candidates [value]`<br>`report:/key_lookup_calls [value]`<br>`report:/stats/register_result_writes [value]` |
| 覆盖 / 规模 / 回退 | `program:/row_kernels [count]`<br>`report:/stats/register_expansion_rows [value]` |

解释与缺口：register_answers 是逻辑匹配；point 命中率须同时看维护和实际 lookup。 Residual matching now reads the shared Cell Query operands: Entry/candidate fields are borrowed; only computed outputs are stored. register_result_writes includes register_prefix.field_writes, so do not sum them. register_expansion_rows counts visited live candidate rows, including rows rejected by constraints; it is not a saved-operation count. Register scratch now uses the largest compiled Cell Query result width across rule pivots. Width is derived once per query; the per-frame maximum scan and initialization savings are not separately instrumented. Context roots now compile to ScopedStep and share internal row checks/writes. Context and register candidate columns share Expansion binding; all context runtime Arg interpretation is removed. Static root instructions add metadata; this is not an allocation or speed result.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[README.md](../../README.md) · [benchmarks/cell-unification/residual.md](../../benchmarks/cell-unification/residual.md) · [benchmarks/cell-unification/query-storage-results.json](../../benchmarks/cell-unification/query-storage-results.json) · [benchmarks/cell-unification/context-root-check.json](../../benchmarks/cell-unification/context-root-check.json)

## B2 · Free Join、Sieve 与范围过滤

启用条件：产物具备计划；范围索引按需求构建。

编译期依据：共享列投影、类型正确的范围约束、版本化候选域。

替代的旧工作：读取后才拒绝的无关候选。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[entry_join.rs](../../engine/cell-runtime/src/entry_join.rs) · [free_join.rs](../../engine/cell-runtime/src/free_join.rs) · [sieve.rs](../../engine/cell-runtime/src/sieve.rs) · [physical_plan.rs](../../engine/cell-runtime/src/physical_plan.rs) · [cell_links.rs](../../engine/cell-runtime/src/cell_links.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/free_join/entry_rejections [value]`<br>`report:/free_join/disjoint_rule_skips [value]`<br>`report:/sieve/stats/rejected [value]` |
| 成本 / 剩余工作 | `report:/free_join/probes [value]`<br>`report:/free_join/entry_bucket_rows_examined [value]`<br>`report:/free_join/entry_bucket_rows_materialized [value]`<br>`report:/sieve/stats/build_rows [value]`<br>`report:/sieve/stats/update_rows [value]`<br>`report:/sieve/stats/probes [value]`<br>`report:/publication/range_rows [value]`<br>`report:/free_join/entry_rows [value]`<br>`report:/free_join/entry_probes [value]`<br>`report:/free_join/entry_cache_hits [value]`<br>`report:/free_join/cover_rows [value]`<br>`report:/free_join/key_groups [value]`<br>`report:/free_join/bucket_rows_examined [value]`<br>`report:/free_join/bucket_rows_materialized [value]`<br>`report:/free_join/reverse_keys [value]`<br>`report:/free_join/reverse_refs [value]`<br>`report:/free_join/reverse_epoch_bins [value]`<br>`report:/free_join/disjoint_key_reads [value]`<br>`report:/sieve/stats/rule_uses [value]`<br>`report:/sieve/stats/dependency_rows [value]` |
| 覆盖 / 规模 / 回退 | `program:/free_join_entry [count]`<br>`program:/physical_plan/ranges [count]` |

解释与缺口：不同过滤器的拒绝集合会重叠，不能把各自 skip 直接相加成全局收益。 Static shared-column wiring now comes from the same Cell query; runtime filtering and index lifetime remain distinct obligations. Removing repeated preparation does not establish a speedup. Bake now charges these pre-decode filter operations. membership_only/shared_column_reads and reused_summaries are subsets, not additional costs; rejection counts do not earn separate credit. Equal operation weights are not a speed model.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[docs/SEMIJOIN.md](../../docs/SEMIJOIN.md) · [benchmarks/cell-unification/steps.md](../../benchmarks/cell-unification/steps.md) · [benchmarks/cell-unification/links-check.json](../../benchmarks/cell-unification/links-check.json) · [benchmarks/cell-unification/sieve-results.json](../../benchmarks/cell-unification/sieve-results.json)

## B3 · 邻居、局部 context 与 view 消费

启用条件：窄 context 默认；通用 cut 需 admission；view-ports 为 feature。

编译期依据：受需求约束的 sibling/parent 投影与完整 residual。

替代的旧工作：重复解码父节点及重复局部连接。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[neighbor.rs](../../engine/cell-runtime/src/neighbor.rs) · [local_context.rs](../../engine/cell-runtime/src/local_context.rs) · [view_plan.rs](../../engine/cell-runtime/src/view_plan.rs) · [cell_links.rs](../../engine/cell-runtime/src/cell_links.rs) · [cell_query.rs](../../engine/cell-runtime/src/cell_query.rs) · [cell_match.rs](../../engine/cell-runtime/src/cell_match.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/neighbor_context/rules/*/stats/group_hits [sum]`<br>`report:/local_context/rules/*/root_reuses [sum]` |
| 成本 / 剩余工作 | `report:/neighbor_context/rules/*/stats/build_visits [sum]`<br>`report:/neighbor_context/publication/refreshed [value]`<br>`report:/view_consumers/port_payload_deliveries [value]`<br>`report:/local_context/rules/*/prefix_copies [sum]`<br>`report:/local_context/rules/*/prefix_slots_copied [sum]`<br>`report:/local_context/rules/*/branch_slot_clears [sum]`<br>`report:/local_context/rules/*/terminal_binding_copies [sum]`<br>`report:/local_context/rules/*/terminal_slots_copied [sum]`<br>`report:/local_context/rules/*/terminal_scratch_slots [sum]`<br>`report:/local_context/rules/*/terminal_result_writes [sum]` |
| 覆盖 / 规模 / 回退 | `report:/neighbor_context/demanded_keys [value]`<br>`report:/local_context/cut_rules [value]`<br>`report:/view_consumers/groups [count]` |

解释与缺口：每规则统计为可选结构；缺失必须显示未采集。通用 cut 与专用 view 不能合并宣称同一收益。 Static shared-column wiring now comes from the same Cell query; runtime filtering and index lifetime remain distinct obligations. Removing repeated preparation does not establish a speedup. Query binding now shares the Cell binder with ordinary search and Entries; cached context storage, root binding and index lifecycle remain to integrate. Prefix scopes now remove intermediate candidate copies; copied slot counts and new clears are charged. They do not measure allocator calls or nanoseconds. Terminal projection/post-guards now use the common Cell Query with borrowed fields; scratch/result costs are charged. Old artifact field names are serialization-only views. Retained prefixes now share Cell instruction lowering, reads and scalar evaluation; static writes also define rollback. Legacy port/post atom order is projected only at serialization. Removed Arg decoding/scalar Vec construction is not counted as measured savings. Context borrows the result width from Query instead of retaining a separate copy. Context shape selection and full artifact validation now precede executable Cell lowering. Only admitted general cuts allocate instructions; Bake refitting and compiler emission need only source-order certificates. The 1481→17 plan count is inferred from validated sum-bits admission and code paths, not timed or allocator evidence. Context roots now compile to ScopedStep and share internal row checks/writes. Context and register candidate columns share Expansion binding; all context runtime Arg interpretation is removed. Static root instructions add metadata; this is not an allocation or speed result. Prefix frames now use dense static Cell addresses instead of full RHS-template slot width. Existing copied-slot credit observes sum-bits 21→14, with copy/clear counts unchanged; each scoped instruction gains a static base word. No runtime translation map, allocation count or speed claim is introduced. Context now directly returns requested Cell facts, removing its outgoing full witness array and executor conversion. Required prefix witnesses remain; full stage Entries still use an intermediate array. Fact projection now precedes context deduplication; no allocation savings are inferred from output binding counts. The f1c69507 short checkpoint does not establish a speedup or resolve speed preservation.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[docs/VIEW_CONSUMER_BLOCKS.md](../../docs/VIEW_CONSUMER_BLOCKS.md) · [benchmarks/cell-unification/steps.md](../../benchmarks/cell-unification/steps.md) · [benchmarks/cell-unification/links-check.json](../../benchmarks/cell-unification/links-check.json) · [benchmarks/cell-unification/query-frame-check.json](../../benchmarks/cell-unification/query-frame-check.json) · [benchmarks/cell-unification/context-branches-check.json](../../benchmarks/cell-unification/context-branches-check.json) · [benchmarks/cell-unification/context-terminal-check.json](../../benchmarks/cell-unification/context-terminal-check.json) · [benchmarks/cell-unification/context-prefix-check.json](../../benchmarks/cell-unification/context-prefix-check.json) · [benchmarks/cell-unification/query-storage-results.json](../../benchmarks/cell-unification/query-storage-results.json) · [benchmarks/cell-unification/context-selection-check.json](../../benchmarks/cell-unification/context-selection-check.json) · [benchmarks/cell-unification/context-root-check.json](../../benchmarks/cell-unification/context-root-check.json) · [benchmarks/cell-unification/context-compact-check.json](../../benchmarks/cell-unification/context-compact-check.json) · [benchmarks/cell-unification/match-completion-results.json](../../benchmarks/cell-unification/match-completion-results.json)
