# C · 跨阶段见证与接续

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## C1 · 完整 stage Entry 与 Spine block

启用条件：已证明完整 key 覆盖的 Cell Entry；Bake catalog 只决定跨阶段组合。

编译期依据：函数 key 流可完成全部 atom，primitive 顺序明确。

替代的旧工作：完整匹配环境和重复入口处理。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[cell_query.rs](../../engine/cell-runtime/src/cell_query.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [spine_blocks.rs](../../engine/cell-runtime/src/spine_blocks.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/query_takeovers [value]`<br>`report:/stage_spine/stats/block_resumptions [value]`<br>`report:/stage_spine/stats/pivots_skipped [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/guards [value]`<br>`report:/stage_spine/stats/port_refreshes [value]`<br>`report:/stage_spine/stats/origin_map_writes [value]`<br>`report:/stage_spine/stats/context_reads [value]`<br>`report:/stage_spine/stats/cell_query_steps [value]`<br>`report:/stage_spine/stats/cell_query_result_writes [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/routed_spine_seeds [value]`<br>`report:/stage_spine/stats/routed_matcher_seeds [value]`<br>`report:/stage_spine/stats/uncovered_queries [value]`<br>`program:/spine_blocks/entries [count]`<br>`report:/stage_spine/stats/cell_query_entries [value]` |

解释与缺口：完整接管与部分前缀必须分开；matched binding 不等于实际 mutation。 所有完整 Entry 共用 Cell query 指令；cell_query_entries/steps/result_writes 是执行覆盖和成本，不能算作新增节省。block 指标仍只计算 Bake 选中的组合。残余枚举共用排序编译器，但寄存器执行器尚未统一。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/leaf-completion/README.md](../../benchmarks/leaf-completion/README.md) · [benchmarks/cell-unification/query.md](../../benchmarks/cell-unification/query.md)

## C2 · RHS handoff 与 query receipt

启用条件：iterative Bake 的 typed handoff 证书。

编译期依据：前序事实、完整 key 与源边界 congruence；禁止未来查询倒证先前读取。

替代的旧工作：后继 RHS 构造子查找、部分完整 Cell frame。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [iterative.rs](../../engine/cell-runtime/src/iterative.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/handoff_lets [value]`<br>`report:/stats/handoff_sets [value]`<br>`report:/stats/handoff_closed [value]`<br>`report:/stats/rhs_frames_avoided [value]`<br>`report:/stage_spine/stats/query_receipt_hits [value]` |
| 成本 / 剩余工作 | `report:/stats/handoff_attempts [value]`<br>`report:/stats/handoff_stale [value]`<br>`report:/stats/handoff_missing [value]`<br>`report:/stage_spine/stats/history_capture_reads [value]`<br>`report:/stage_spine/stats/history_slots_written [value]`<br>`report:/stage_spine/stats/history_allocations [value]`<br>`report:/stage_spine/stats/query_receipt_stale [value]`<br>`report:/stage_spine/stats/history_result_reads [value]`<br>`report:/stage_spine/stats/history_empty_slots_written [value]` |
| 覆盖 / 规模 / 回退 | `program:/iterative_bake/rhs_handoffs/states [count]` |

解释与缺口：实际 lookup 差值已经计入 key_lookup_calls；hit 不能再给第二份 credit。 Cell result ports use compiled slots; history_empty_slots_written charges padding. history_result_reads includes local-witness reads; do not sum it again with C3 local_witness_slot_reads.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/query-receipts/README.md](../../benchmarks/query-receipts/README.md) · [benchmarks/compiler-congruence/README.md](../../benchmarks/compiler-congruence/README.md)

## C3 · 已有见证的实际来源直达

启用条件：完整 Spine 的非空完整 key 读取。

编译期依据：已验证的实际 query/effect 来源；静态别名归并；仅使用已有目录保留的 receipt；排除零参数单例读取。

替代的旧工作：history/cache 未命中后的完整查询。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [producer.rs](../../engine/cell-runtime/src/producer.rs) · [multistage.rs](../../engine/cell-runtime/src/multistage.rs) · [result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [mod.rs](../../engine/cell-runtime/src/compiler/mod.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/local_witness_hits [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/local_witness_contexts [value]`<br>`report:/stage_spine/stats/local_witness_route_probes [value]`<br>`report:/stage_spine/stats/local_witness_route_steps [value]`<br>`report:/stage_spine/stats/local_witness_key_fields [value]`<br>`report:/stage_spine/stats/local_witness_stale [value]`<br>`report:/key_lookup_calls [value]`<br>`report:/stage_spine/stats/local_witness_receipt_probes [value]`<br>`report:/stage_spine/stats/local_witness_receipt_steps [value]`<br>`report:/stage_spine/stats/local_witness_history_borrows [value]`<br>`report:/stage_spine/stats/local_witness_row_reads [value]`<br>`report:/stage_spine/stats/local_witness_slot_reads [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/local_witness_routes [value]`<br>`report:/stage_spine/stats/local_witness_reads [value]`<br>`report:/stage_spine/stats/local_witness_misses/cell_missing [value]`<br>`report:/stage_spine/stats/local_witness_misses/fact_missing [value]`<br>`report:/stage_spine/stats/local_witness_misses/receipt_missing [value]`<br>`report:/stage_spine/stats/local_witness_misses/hidden [value]`<br>`report:/stage_spine/stats/local_witness_misses/shape [value]`<br>`report:/stage_spine/stats/local_witness_misses/key [value]`<br>`report:/stage_spine/stats/local_witness_receipt_hits [value]`<br>`report:/multi_stage/witness_plan/new_capture_slots [value]`<br>`report:/multi_stage/witness_plan/retained_receipt_reads [value]`<br>`report:/multi_stage/witness_plan/physical_fallback_reads [value]`<br>`report:/multi_stage/witness_plan/excluded_reads [value]` |

解释与缺口：receipt_hits 只说明找到地址；当前存活、完整 key、结果约束仍需验证。只读取已有捕获范围，未保存的关系仍回退；排除零参数读取避免用更昂贵的分派换取 lookup 计数下降。row_reads 是实际行读取，donor/read 尝试不一定访问行；Spine 的行读取已包含在 decoded_rows，不能重复收费。新增静态元数据的解析成本仍须在最终计时中检查。

状态：真实来源与已有 receipt 交接已实现；专项及全工作区检查通过；最新短样例观测见 witness-sources，尚无新的整体加速结论。

证据：[benchmarks/witness-prefix/design.md](../../benchmarks/witness-prefix/design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md) · [benchmarks/witness-sources/README.md](../../benchmarks/witness-sources/README.md)

## C4 · 匹配前缀接续

启用条件：含 Expand 的 register kernel，具有非空完整 key 的连续前缀。

编译期依据：已验证的实际 query/effect 来源；静态别名归并；仅使用已有目录保留的 receipt；排除零参数单例读取。

替代的旧工作：从 PC=0 重做已有事实前缀。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[row_kernel.rs](../../engine/cell-runtime/src/row_kernel.rs) · [execute_kernel.rs](../../engine/cell-runtime/src/execute_kernel.rs) · [producer.rs](../../engine/cell-runtime/src/producer.rs) · [multistage.rs](../../engine/cell-runtime/src/multistage.rs) · [result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [mod.rs](../../engine/cell-runtime/src/compiler/mod.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/register_prefix/key_reads_avoided [value]`<br>`report:/stats/register_prefix/resumes [value]` |
| 成本 / 剩余工作 | `report:/stats/register_prefix/context_reads [value]`<br>`report:/stats/register_prefix/plan_comparisons [value]`<br>`report:/stats/register_prefix/donor_reads [value]`<br>`report:/stats/register_prefix/key_fields [value]`<br>`report:/stats/register_prefix/stale_fallbacks [value]`<br>`report:/stats/register_prefix/key_fallbacks [value]`<br>`report:/stats/register_prefix/receipt_probes [value]`<br>`report:/stats/register_prefix/receipt_steps [value]`<br>`report:/stats/register_prefix/history_borrows [value]`<br>`report:/stats/register_prefix/row_reads [value]`<br>`report:/stats/register_prefix/publication_probes [value]`<br>`report:/stats/register_prefix/receipt_slot_reads [value]`<br>`report:/stats/register_prefix/entry_publication_reads [value]` |
| 覆盖 / 规模 / 回退 | `report:/stats/register_prefix/eligible_seeds [value]`<br>`report:/stats/register_prefix/plan_hits [value]`<br>`report:/stats/register_prefix/owner_rejections [value]`<br>`report:/stats/register_prefix/misses/cell_missing [value]`<br>`report:/stats/register_prefix/misses/fact_missing [value]`<br>`report:/stats/register_prefix/misses/receipt_missing [value]`<br>`report:/stats/register_prefix/misses/hidden [value]`<br>`report:/stats/register_prefix/misses/shape [value]`<br>`report:/stats/register_prefix/misses/key [value]`<br>`report:/stats/register_prefix/receipt_hits [value]`<br>`report:/multi_stage/witness_plan/new_capture_slots [value]` |

解释与缺口：receipt_hits 只说明找到地址；当前存活、完整 key、结果约束仍需验证。只读取已有捕获范围，未保存的关系仍回退；排除零参数读取避免用更昂贵的分派换取 lookup 计数下降。row_reads 是实际行读取，donor/read 尝试不一定访问行；Spine 的行读取已包含在 decoded_rows，不能重复收费。新增静态元数据的解析成本仍须在最终计时中检查。 key_reads_avoided 包括原本可命中 PointPorts 的读取，不等于等量哈希查询。 Entry-managed seeds carry publication locations; entry_publication_reads counts attempts, including empty handles. publication_probes counts the remaining legacy map probes.

状态：真实来源与已有 receipt 交接已实现；专项及全工作区检查通过；最新短样例观测见 witness-sources，尚无新的整体加速结论。

证据：[benchmarks/witness-prefix/register-prefix-design.md](../../benchmarks/witness-prefix/register-prefix-design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md) · [benchmarks/witness-sources/README.md](../../benchmarks/witness-sources/README.md)
