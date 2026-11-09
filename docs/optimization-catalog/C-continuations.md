# C · 跨阶段见证与接续

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## C1 · 完整 stage Entry 与 Spine block

启用条件：编译计划及已验证 block catalog。

编译期依据：函数 key 流可完成全部 atom，primitive 顺序明确。

替代的旧工作：完整匹配环境和重复入口处理。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [spine_blocks.rs](../../engine/cell-runtime/src/spine_blocks.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/query_takeovers [value]`<br>`report:/stage_spine/stats/block_resumptions [value]`<br>`report:/stage_spine/stats/pivots_skipped [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/guards [value]`<br>`report:/stage_spine/stats/port_refreshes [value]`<br>`report:/stage_spine/stats/origin_map_writes [value]`<br>`report:/stage_spine/stats/context_reads [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/routed_spine_seeds [value]`<br>`report:/stage_spine/stats/routed_matcher_seeds [value]`<br>`report:/stage_spine/stats/uncovered_queries [value]`<br>`program:/spine_blocks/entries [count]` |

解释与缺口：完整接管与部分前缀必须分开；matched binding 不等于实际 mutation。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/leaf-completion/README.md](../../benchmarks/leaf-completion/README.md)

## C2 · RHS handoff 与 query receipt

启用条件：iterative Bake 的 typed handoff 证书。

编译期依据：前序事实、完整 key 与源边界 congruence；禁止未来查询倒证先前读取。

替代的旧工作：后继 RHS 构造子查找、部分完整 Cell frame。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[result_handoff.rs](../../engine/cell-runtime/src/result_handoff.rs) · [iterative.rs](../../engine/cell-runtime/src/iterative.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/handoff_lets [value]`<br>`report:/stats/handoff_sets [value]`<br>`report:/stats/handoff_closed [value]`<br>`report:/stats/rhs_frames_avoided [value]`<br>`report:/stage_spine/stats/query_receipt_hits [value]` |
| 成本 / 剩余工作 | `report:/stats/handoff_attempts [value]`<br>`report:/stats/handoff_stale [value]`<br>`report:/stats/handoff_missing [value]`<br>`report:/stage_spine/stats/history_capture_reads [value]`<br>`report:/stage_spine/stats/history_slots_written [value]`<br>`report:/stage_spine/stats/history_allocations [value]`<br>`report:/stage_spine/stats/query_receipt_stale [value]` |
| 覆盖 / 规模 / 回退 | `program:/iterative_bake/rhs_handoffs/states [count]` |

解释与缺口：实际 lookup 差值已经计入 key_lookup_calls；hit 不能再给第二份 credit。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/query-receipts/README.md](../../benchmarks/query-receipts/README.md) · [benchmarks/compiler-congruence/README.md](../../benchmarks/compiler-congruence/README.md)

## C3 · 已有 effect 见证直达

启用条件：有静态 effect route 的完整 Spine Entry。

编译期依据：真实 Entry 的当前 producer + 当前完整 key 校验。

替代的旧工作：history/cache 未命中后的完整查询。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/local_witness_hits [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/local_witness_contexts [value]`<br>`report:/stage_spine/stats/local_witness_route_probes [value]`<br>`report:/stage_spine/stats/local_witness_route_steps [value]`<br>`report:/stage_spine/stats/local_witness_key_fields [value]`<br>`report:/stage_spine/stats/local_witness_stale [value]`<br>`report:/key_lookup_calls [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/local_witness_routes [value]`<br>`report:/stage_spine/stats/local_witness_reads [value]` |

解释与缺口：命中才省一次 fallback lookup；不能把所有 context probes 都视作成功复用。 当前地址策略在真实样例均回退；不能把本轮整体时间变化归因于见证直达。静态 route 尚无独立的收益准入。

状态：已实现并通过回归；当前 sum-bits/Raytrace 实测命中均为 0，未获得实际查询缩减。

证据：[benchmarks/witness-prefix/design.md](../../benchmarks/witness-prefix/design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md)

## C4 · 匹配前缀接续

启用条件：含 Expand 且存在 producer-local effect 前缀的 register kernel。

编译期依据：连续完整 key 前缀；保留 delta owner、guards 与全部 residual Expand。

替代的旧工作：从 PC=0 重做已有事实前缀。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[row_kernel.rs](../../engine/cell-runtime/src/row_kernel.rs) · [execute_kernel.rs](../../engine/cell-runtime/src/execute_kernel.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/register_prefix/key_reads_avoided [value]`<br>`report:/stats/register_prefix/resumes [value]` |
| 成本 / 剩余工作 | `report:/stats/register_prefix/context_reads [value]`<br>`report:/stats/register_prefix/plan_comparisons [value]`<br>`report:/stats/register_prefix/donor_reads [value]`<br>`report:/stats/register_prefix/key_fields [value]`<br>`report:/stats/register_prefix/stale_fallbacks [value]`<br>`report:/stats/register_prefix/key_fallbacks [value]` |
| 覆盖 / 规模 / 回退 | `report:/stats/register_prefix/eligible_seeds [value]`<br>`report:/stats/register_prefix/plan_hits [value]`<br>`report:/stats/register_prefix/owner_rejections [value]` |

解释与缺口：key_reads_avoided 包括原本可命中 PointPorts 的读取，不能当作等量哈希查找节省。 当前地址策略在真实样例均回退；不能把本轮整体时间变化归因于见证直达。静态 route 尚无独立的收益准入。

状态：已实现并通过回归；当前 sum-bits/Raytrace 实测命中均为 0，未获得实际查询缩减。

证据：[benchmarks/witness-prefix/register-prefix-design.md](../../benchmarks/witness-prefix/register-prefix-design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md)
