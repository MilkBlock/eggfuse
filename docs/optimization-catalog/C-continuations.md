# C · 跨阶段见证与接续

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## C1 · 完整 stage Entry 与 Spine block

启用条件：已证明完整 key 覆盖的 Cell Entry；Bake catalog 只决定跨阶段组合。

编译期依据：函数 key 流可完成全部 atom，primitive 顺序明确。

替代的旧工作：完整匹配环境和重复入口处理。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[cell_query.rs](../../engine/cell-runtime/src/cell_query.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [spine_blocks.rs](../../engine/cell-runtime/src/spine_blocks.rs) · [cell_match.rs](../../engine/cell-runtime/src/cell_match.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/query_takeovers [value]`<br>`report:/stage_spine/stats/block_resumptions [value]`<br>`report:/stage_spine/stats/pivots_skipped [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/guards [value]`<br>`report:/stage_spine/stats/port_refreshes [value]`<br>`report:/stage_spine/stats/origin_map_writes [value]`<br>`report:/stage_spine/stats/context_reads [value]`<br>`report:/stage_spine/stats/cell_query_steps [value]`<br>`report:/stage_spine/stats/cell_query_result_writes [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/routed_spine_seeds [value]`<br>`report:/stage_spine/stats/routed_matcher_seeds [value]`<br>`report:/stage_spine/stats/uncovered_queries [value]`<br>`program:/spine_blocks/entries [count]`<br>`report:/stage_spine/stats/cell_query_entries [value]`<br>`report:/stage_spine/shared_query_plans [value]` |

解释与缺口：完整接管与部分前缀必须分开；matched binding 不等于实际 mutation。 所有完整 Entry 共用 Cell query 指令；cell_query_entries/steps/result_writes 是执行覆盖和成本，不能算作新增节省。block 指标仍只计算 Bake 选中的组合。残余枚举现在共用 Cell Query 指令与字段表示；shared_query_plans 统计两个入口持有同一计划的数量。残余枚举和完整入口的覆盖/增量归属策略仍分别执行。 Complete Entry stores results only through the last new output, omitting trailing bound-result writes. Internal holes keep instruction-position addresses. sum-bits writes fell 2604 to 2455; the five-commit timing checkpoint did not establish a speedup. Complete stage Entries now directly produce Cell Matched with requested facts and the existing move-only origin; full witness packets and the duplicate executor adapter are removed. Winner ordering and source lifetime remain. Projection occurs before deduplication; no allocation or speed claim follows from unchanged output counts.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/leaf-completion/README.md](../../benchmarks/leaf-completion/README.md) · [benchmarks/cell-unification/query.md](../../benchmarks/cell-unification/query.md) · [benchmarks/cell-unification/query-storage-results.json](../../benchmarks/cell-unification/query-storage-results.json) · [benchmarks/cell-unification/match-entry-check.json](../../benchmarks/cell-unification/match-entry-check.json)

## C2 · RHS handoff 与 query receipt

启用条件：iterative Bake 的 typed handoff 证书。

编译期依据：前序事实、完整 key 与源边界 congruence；禁止未来查询倒证先前读取。

替代的旧工作：后继 RHS 构造子查找、部分完整 Cell frame。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [iterative.rs](../../engine/cell-runtime/src/iterative.rs) · [cell_binding.rs](../../engine/cell-runtime/src/cell_binding.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/handoff_lets [value]`<br>`report:/stats/handoff_sets [value]`<br>`report:/stats/handoff_closed [value]`<br>`report:/stats/rhs_frames_avoided [value]`<br>`report:/stage_spine/stats/query_receipt_hits [value]` |
| 成本 / 剩余工作 | `report:/stats/handoff_attempts [value]`<br>`report:/stats/handoff_stale [value]`<br>`report:/stats/handoff_missing [value]`<br>`report:/stage_spine/stats/history_capture_reads [value]`<br>`report:/stage_spine/stats/history_slots_written [value]`<br>`report:/stage_spine/stats/history_allocations [value]`<br>`report:/stage_spine/stats/query_receipt_stale [value]`<br>`report:/stage_spine/stats/history_result_reads [value]`<br>`report:/stage_spine/stats/history_empty_slots_written [value]`<br>`report:/stage_spine/history_handle_bytes [value]`<br>`report:/stage_spine/stats/joint_history_checks [value]`<br>`report:/stage_spine/stats/joint_history_frames [value]`<br>`report:/stage_spine/stats/joint_history_query_reads [value]`<br>`report:/stage_spine/stats/joint_history_query_writes [value]` |
| 覆盖 / 规模 / 回退 | `program:/iterative_bake/rhs_handoffs/states [count]`<br>`report:/stage_spine/stats/history_carried_steps [value]`<br>`report:/stage_spine/stats/history_shared_slots [value]` |

解释与缺口：实际 lookup 差值已经计入 key_lookup_calls；hit 不能再给第二份 credit。 Cell result ports use compiled slots; history_empty_slots_written charges padding. history_result_reads includes local-witness reads; do not sum it again with C3 local_witness_slot_reads. Source marker publication, typed local projection and runtime query/Entry frames now share Cell Operand and Bindings. Arg is the typed alias, with unchanged wire shape. Equality evidence stays at each source boundary; rollback remains with the caller. Marker fields are lowered before candidate enumeration and variable names are borrowed. Candidate policies and materialization boundaries remain separate; temporary patterns and generic binding costs have not been timing/allocation-profiled. Local source/typed candidate projection and uniqueness now execute shared Cell code. Typed donors are compared by source row, source publication candidates by binding; the first equivalent candidate is preserved. Separate uniqueness collections are removed and ambiguity stops enumeration. Operator filtering precedes typed frame copies. Source-root deduplication, donor admission and iterative materialization remain necessary. Removed static work is not separately operation/allocation-counted. The acab2911 five-implementation checkpoint used four frozen normal-release sum-bits lanes. Paired inference/process intervals cross 1 against immediate, last-timed and historical controls. No speedup or strict speed preservation is established; this does not measure native compiler time or allocations. 闭合 miss 现继续同一 Cell 前缀，已验证收据和计算结果不再重做；失败检查也计入 handoff_attempts。实际不同的结构性替代见证仍须验证，live/key/Run 约束保留。 组合中间阶段不导出新结果时，沿用已有 history 容器，只推进阶段位置；保留编译期生命周期边界与逐次存活性验证。短链和删除样例的 history 容器分配 6→2、槽写 8→4，读取与查询不变；sum-bits 不覆盖这类深链，工作量不变。句柄新增一个阶段偏移，从 8 增至 16 字节，深层数组元素仍为指针大小；未测速。非空结果转存和通用 Entry 发布仍未消除。 cell-results/v1 在完整导出覆盖的 Cell 中让 RHS、Entry 与已有 History owner 共用实际结果数组；sum-bits 捕获读/写各 1508→129。查询捕获提前、共享数组分配和发布 owner 读取仍收费；slot inheritance、审计与不完整状态继续原路径。历史最终存储规模不变；未完整测速。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/query-receipts/README.md](../../benchmarks/query-receipts/README.md) · [benchmarks/compiler-congruence/README.md](../../benchmarks/compiler-congruence/README.md) · [benchmarks/cell-unification/projection-binding-check.json](../../benchmarks/cell-unification/projection-binding-check.json) · [benchmarks/cell-unification/projection-candidates-results.json](../../benchmarks/cell-unification/projection-candidates-results.json) · [benchmarks/cell-unification/closed-cells-check.json](../../benchmarks/cell-unification/closed-cells-check.json) · [benchmarks/cell-unification/history-carry-check.json](../../benchmarks/cell-unification/history-carry-check.json) · [benchmarks/cell-joint-results/README.md](../../benchmarks/cell-joint-results/README.md) · [benchmarks/cell-joint-results/results.json](../../benchmarks/cell-joint-results/results.json)

## C3 · 已有见证的实际来源直达

启用条件：完整 Spine 的非空完整 key 读取。

编译期依据：已验证的实际 query/effect 来源；静态别名归并；仅使用已有目录保留的 receipt；排除零参数单例读取。

替代的旧工作：history/cache 未命中后的完整查询。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [producer.rs](../../engine/cell-runtime/src/producer.rs) · [multistage.rs](../../engine/cell-runtime/src/multistage.rs) · [result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [mod.rs](../../engine/cell-runtime/src/compiler/mod.rs) · [cell_routes.rs](../../engine/cell-runtime/src/cell_routes.rs) · [cell_producer.rs](../../engine/cell-runtime/src/cell_producer.rs) · [iterative.rs](../../engine/cell-runtime/src/iterative.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/local_witness_hits [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/local_witness_contexts [value]`<br>`report:/stage_spine/stats/local_witness_route_probes [value]`<br>`report:/stage_spine/stats/local_witness_route_steps [value]`<br>`report:/stage_spine/stats/local_witness_key_fields [value]`<br>`report:/stage_spine/stats/local_witness_stale [value]`<br>`report:/key_lookup_calls [value]`<br>`report:/stage_spine/stats/local_witness_receipt_probes [value]`<br>`report:/stage_spine/stats/local_witness_receipt_steps [value]`<br>`report:/stage_spine/stats/local_witness_history_borrows [value]`<br>`report:/stage_spine/stats/local_witness_row_reads [value]`<br>`report:/stage_spine/stats/local_witness_slot_reads [value]`<br>`report:/stage_spine/stats/local_witness_route_comparisons [value]`<br>`report:/stage_spine/stats/local_witness_read_index_probes [value]`<br>`report:/multi_stage/witness_plan/route_directory/vector_capacity_bytes [value]`<br>`report:/multi_stage/witness_plan/route_directory/read_index_capacity_bytes [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/local_witness_routes [value]`<br>`report:/stage_spine/stats/local_witness_reads [value]`<br>`report:/stage_spine/stats/local_witness_misses/cell_missing [value]`<br>`report:/stage_spine/stats/local_witness_misses/fact_missing [value]`<br>`report:/stage_spine/stats/local_witness_misses/receipt_missing [value]`<br>`report:/stage_spine/stats/local_witness_misses/hidden [value]`<br>`report:/stage_spine/stats/local_witness_misses/shape [value]`<br>`report:/stage_spine/stats/local_witness_misses/key [value]`<br>`report:/stage_spine/stats/local_witness_receipt_hits [value]`<br>`report:/multi_stage/witness_plan/new_capture_slots [value]`<br>`report:/multi_stage/witness_plan/retained_receipt_reads [value]`<br>`report:/multi_stage/witness_plan/physical_fallback_reads [value]`<br>`report:/multi_stage/witness_plan/excluded_reads [value]`<br>`report:/stage_spine/stats/local_witness_route_index_probes [value]`<br>`report:/multi_stage/witness_plan/route_directory/direct_entries [value]`<br>`report:/multi_stage/witness_plan/route_directory/direct_slots [value]`<br>`report:/multi_stage/witness_plan/route_directory/sparse_entries [value]`<br>`report:/multi_stage/witness_plan/route_directory/routes [value]`<br>`report:/multi_stage/witness_plan/route_directory/read_index_slots [value]` |

解释与缺口：receipt_hits 只说明找到地址；当前存活、完整 key、结果约束仍需验证。只读取已有捕获范围，未保存的关系仍回退；排除零参数读取避免用更昂贵的分派换取 lookup 计数下降。row_reads 是实际行读取，donor/read 尝试不一定访问行；Spine 的行读取已包含在 decoded_rows，不能重复收费。新增静态元数据的解析成本仍须在最终计时中检查。 完整/残余入口共用静态 Cell 路线目录；直接索引和见证源索引仍有成本，比较归零不是速度收益。目录容量不含 Rc 与 allocator 元数据；route_index_probes 是 route_probes 的子集，不重复评分。 Compiled Cell transitions now bound result-history retention per state, including inherited jumps and restart paths. Deep short fixtures reduce history container allocations 10→6 and slot writes 10→8 with unchanged lookups/fallbacks; sum-bits work is unchanged. These are structural counters, not total allocator bytes or timing evidence. Added static retention words, deep-frame enum tags and fixed-point setup remain to be timed. Cell 路线证明现借用同一份构造子别名，原始 source slot 仍逐项校验；域已返回唯一 witness 时直接读取，不再重新按 key 查找。sum-bits 查询 19237→18692，旧接线兼容对照已取得全部 545 次减少；扩大接线 6325→6825 只再省 11 次解码、多 12 次路线比较，等权 Work 单项净值 -1，目录容量合计多 4524 字节。c2f665a2 的五组交错实测：相对 135dfb1b，配对推理比 1.0131 [1.0061,1.0438]，整进程比 1.0435 [1.0305,1.0863]；本轮性能回退。新增接线加载中位数 68.685→73.211ms（同一运行时），尚未证明覆盖扩张值得默认采用。纯 witness 直读对照的时间区间跨 1；计数减少不等于加速。下一步收缩低收益接线及其加载成本。

状态：真实来源与已有 receipt 交接已实现；专项及全工作区检查通过；最新短样例观测见 witness-sources，尚无新的整体加速结论。

证据：[benchmarks/witness-prefix/design.md](../../benchmarks/witness-prefix/design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md) · [benchmarks/witness-sources/README.md](../../benchmarks/witness-sources/README.md) · [benchmarks/cell-unification/retention-check.json](../../benchmarks/cell-unification/retention-check.json) · [benchmarks/cell-unification/alias-routes-check.json](../../benchmarks/cell-unification/alias-routes-check.json)

## C4 · 匹配前缀接续

启用条件：含 Expand 的 register kernel，具有非空完整 key 的连续前缀。

编译期依据：已验证的实际 query/effect 来源；静态别名归并；仅使用已有目录保留的 receipt；排除零参数单例读取。

替代的旧工作：从 PC=0 重做已有事实前缀。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[row_kernel.rs](../../engine/cell-runtime/src/row_kernel.rs) · [execute_kernel.rs](../../engine/cell-runtime/src/execute_kernel.rs) · [producer.rs](../../engine/cell-runtime/src/producer.rs) · [multistage.rs](../../engine/cell-runtime/src/multistage.rs) · [result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [mod.rs](../../engine/cell-runtime/src/compiler/mod.rs) · [cell_routes.rs](../../engine/cell-runtime/src/cell_routes.rs) · [cell_producer.rs](../../engine/cell-runtime/src/cell_producer.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/register_prefix/key_reads_avoided [value]`<br>`report:/stats/register_prefix/resumes [value]` |
| 成本 / 剩余工作 | `report:/stats/register_prefix/context_reads [value]`<br>`report:/stats/register_prefix/plan_comparisons [value]`<br>`report:/stats/register_prefix/donor_reads [value]`<br>`report:/stats/register_prefix/key_fields [value]`<br>`report:/stats/register_prefix/stale_fallbacks [value]`<br>`report:/stats/register_prefix/key_fallbacks [value]`<br>`report:/stats/register_prefix/receipt_probes [value]`<br>`report:/stats/register_prefix/receipt_steps [value]`<br>`report:/stats/register_prefix/history_borrows [value]`<br>`report:/stats/register_prefix/row_reads [value]`<br>`report:/stats/register_prefix/publication_probes [value]`<br>`report:/stats/register_prefix/receipt_slot_reads [value]`<br>`report:/stats/register_prefix/entry_publication_reads [value]`<br>`report:/stats/register_prefix/plan_index_probes [value]`<br>`report:/stats/register_prefix/source_index_probes [value]` |
| 覆盖 / 规模 / 回退 | `report:/stats/register_prefix/eligible_seeds [value]`<br>`report:/stats/register_prefix/plan_hits [value]`<br>`report:/stats/register_prefix/owner_rejections [value]`<br>`report:/stats/register_prefix/misses/cell_missing [value]`<br>`report:/stats/register_prefix/misses/fact_missing [value]`<br>`report:/stats/register_prefix/misses/receipt_missing [value]`<br>`report:/stats/register_prefix/misses/hidden [value]`<br>`report:/stats/register_prefix/misses/shape [value]`<br>`report:/stats/register_prefix/misses/key [value]`<br>`report:/stats/register_prefix/receipt_hits [value]`<br>`report:/multi_stage/witness_plan/new_capture_slots [value]`<br>`report:/multi_stage/witness_plan/route_directory/prefix_routes [value]` |

解释与缺口：receipt_hits 只说明找到地址；当前存活、完整 key、结果约束仍需验证。只读取已有捕获范围，未保存的关系仍回退；排除零参数读取避免用更昂贵的分派换取 lookup 计数下降。row_reads 是实际行读取，donor/read 尝试不一定访问行；Spine 的行读取已包含在 decoded_rows，不能重复收费。新增静态元数据的解析成本仍须在最终计时中检查。 key_reads_avoided 包括原本可命中 PointPorts 的读取，不等于等量哈希查询。 Entry-managed seeds carry publication locations; entry_publication_reads counts attempts, including empty handles. publication_probes counts the remaining legacy map probes. 完整/残余入口共用静态 Cell 路线目录；直接索引和见证源索引仍有成本，比较归零不是速度收益。目录容量不含 Rc 与 allocator 元数据；route_index_probes 是 route_probes 的子集，不重复评分。 Compiled Cell transitions now bound result-history retention per state, including inherited jumps and restart paths. Deep short fixtures reduce history container allocations 10→6 and slot writes 10→8 with unchanged lookups/fallbacks; sum-bits work is unchanged. These are structural counters, not total allocator bytes or timing evidence. Added static retention words, deep-frame enum tags and fixed-point setup remain to be timed. Cell 路线证明现借用同一份构造子别名，原始 source slot 仍逐项校验；域已返回唯一 witness 时直接读取，不再重新按 key 查找。sum-bits 查询 19237→18692，旧接线兼容对照已取得全部 545 次减少；扩大接线 6325→6825 只再省 11 次解码、多 12 次路线比较，等权 Work 单项净值 -1，目录容量合计多 4524 字节。c2f665a2 的五组交错实测：相对 135dfb1b，配对推理比 1.0131 [1.0061,1.0438]，整进程比 1.0435 [1.0305,1.0863]；本轮性能回退。新增接线加载中位数 68.685→73.211ms（同一运行时），尚未证明覆盖扩张值得默认采用。纯 witness 直读对照的时间区间跨 1；计数减少不等于加速。下一步收缩低收益接线及其加载成本。

状态：真实来源与已有 receipt 交接已实现；专项及全工作区检查通过；最新短样例观测见 witness-sources，尚无新的整体加速结论。

证据：[benchmarks/witness-prefix/register-prefix-design.md](../../benchmarks/witness-prefix/register-prefix-design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md) · [benchmarks/witness-sources/README.md](../../benchmarks/witness-sources/README.md) · [benchmarks/cell-unification/retention-check.json](../../benchmarks/cell-unification/retention-check.json) · [benchmarks/cell-unification/alias-routes-check.json](../../benchmarks/cell-unification/alias-routes-check.json)
