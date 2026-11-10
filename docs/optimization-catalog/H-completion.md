# H · 完成调度与并行

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## H1 · 编译 scope 与按需完成

启用条件：--scoped-queues / --scoped-execution。

编译期依据：完整 table/type influence、opaque effects 回退与原观察边界。

替代的旧工作：不相关 table 的强制等待。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[completion_plan.rs](../../engine/cell-runtime/src/completion_plan.rs) · [scoped_completion.rs](../../engine/cell-runtime/src/scoped_completion.rs) · [runtime_completion.rs](../../engine/cell-runtime/src/runtime_completion.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/scoped_completion/stats/bypassed_tasks [value]`<br>`report:/scoped_executor/stats/runs_with_unrelated_pending [value]` |
| 成本 / 剩余工作 | `report:/scoped_completion/stats/head_probes [value]`<br>`report:/scoped_executor/stats/readiness_dependency_checks [value]` |
| 覆盖 / 规模 / 回退 | `report:/scoped_executor/stats/compiler_full_completion_runs [value]`<br>`report:/scoped_completion/stats/opaque_full_completions [value]` |

解释与缺口：静态粗 scope 常退化成全局；目前没有专门的 wall-clock stall 分项，不把 bypassed_tasks 叫已消除 stall。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/stable-port-congruence/scoped-executor-contract.md](../../benchmarks/stable-port-congruence/scoped-executor-contract.md)

## H2 · concrete-port influence 与 pure epoch

启用条件：--port-scopes / --pure-epochs / --unique-port-publication。

编译期依据：端口影响 frontier、纯构造效果、birth/order 检查。

替代的旧工作：有界区域内的多余完成屏障和发布查找。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[port_completion.rs](../../engine/cell-runtime/src/port_completion.rs) · [pure_effects.rs](../../engine/cell-runtime/src/pure_effects.rs) · [cell_bound.rs](../../engine/cell-runtime/src/cell_bound.rs) · [runtime_pure_epochs.rs](../../engine/cell-runtime/src/runtime_pure_epochs.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/port_completion/stats/bypassed_tasks [value]`<br>`report:/scoped_executor/stats/rhs_fact_births_while_pending [value]` |
| 成本 / 剩余工作 | `report:/port_completion/stats/root_visits [value]`<br>`report:/port_completion/stats/static_steps [value]`<br>`report:/port_completion/stats/pure_epoch_frontier_checks [value]`<br>`report:/port_completion/stats/pure_epoch_order_checks [value]`<br>`report:/scoped_executor/stats/bound_rhs_attempts [value]`<br>`report:/scoped_executor/stats/bound_rhs_rule_checks [value]`<br>`report:/scoped_executor/stats/bound_rhs_ops [value]`<br>`report:/scoped_executor/stats/bound_rhs_expression_steps [value]`<br>`report:/scoped_executor/stats/bound_rhs_input_reads [value]`<br>`report:/scoped_executor/stats/bound_rhs_key_reads [value]`<br>`report:/scoped_executor/stats/bound_rhs_value_slots [value]`<br>`report:/scoped_executor/stats/bound_rhs_scratch_growths [value]`<br>`report:/scoped_executor/stats/bound_rhs_overlay_checks [value]` |
| 覆盖 / 规模 / 回退 | `report:/port_completion/stats/pure_epoch_accepts [value]`<br>`report:/port_completion/stats/typed_fallbacks [value]`<br>`report:/port_completion/stats/pure_epoch_order_rejections [value]`<br>`report:/scoped_executor/stats/bound_rhs_accepts [value]`<br>`report:/scoped_executor/stats/bound_rhs_budget_rejections [value]` |

解释与缺口：while_pending 的 binding/逻辑 match 不是 mutation；只有实际 birth/update/union 计数能说明执行。 Bound RHS 仅保留原 Cell 操作的位置和紧凑操作数布局；证明读取不是实际写入。布局统一的速度保持尚待后续计时确认。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/stable-port-congruence/scoped-executor-contract.md](../../benchmarks/stable-port-congruence/scoped-executor-contract.md)

## H3 · 并行 guard、跨 task 读取与 overlap

启用条件：--guard-workers；--completion-batch-tasks；--overlap-completion。

编译期依据：不可变 snapshot、完整输入 read set、两侧 union 失效和有序提交。

替代的旧工作：将可独立的 Eq/条件读取并行执行。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[parallel_port_guards.rs](../../engine/cell-runtime/src/parallel_port_guards.rs) · [completion_read_batches.rs](../../engine/cell-runtime/src/completion_read_batches.rs) · [completion_overlap.rs](../../engine/cell-runtime/src/completion_overlap.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stable_ports/completion_batches/stats/committed_tasks [value]`<br>`report:/stable_ports/completion_batches/stats/reused_after_union [value]` |
| 成本 / 剩余工作 | `report:/stable_ports/completion_batches/stats/dispatches [value]`<br>`report:/stable_ports/completion_batches/stats/read_set_comparisons [value]`<br>`report:/stable_ports/completion_batches/stats/unused_tasks [value]`<br>`report:/stable_ports/completion_batches/stats/scratch_allocations [value]`<br>`report:/stable_ports/completion_batches/overlap/stats/task_spawns [value]` |
| 覆盖 / 规模 / 回退 | `report:/stable_ports/completion_batches/worker_tasks [value]` |

解释与缺口：需要同二进制1/2/4线程整进程与推理时间；worker参与和并行读取不代表并行提交或无 stall。历史测试未建立加速。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/raytrace-parallel/README.md](../../benchmarks/raytrace-parallel/README.md)

## H4 · 大 Cell 的完整域并行完成

启用条件：已有 completion batch 模式自动扩大可读范围。

编译期依据：局部条件超16 sites时，完整端口域 + exact key guard 仍可证明候选完整。

替代的旧工作：因局部条件容量限制而截断整个读取批次。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[completion_read_batches.rs](../../engine/cell-runtime/src/completion_read_batches.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stable_ports/completion_batches/stats/exact_domain_tasks [value]`<br>`report:/stable_ports/completion_batches/stats/committed_tasks [value]` |
| 成本 / 剩余工作 | `report:/stable_ports/completion_batches/stats/exact_domain_candidates [value]`<br>`report:/stable_ports/completion_batches/stats/candidate_positions [value]`<br>`report:/stable_ports/completion_batches/stats/unused_tasks [value]`<br>`report:/stable_ports/completion_batches/stats/scratch_allocations [value]` |
| 覆盖 / 规模 / 回退 | `report:/stable_ports/completion_batches/stats/uncovered_stops [value]`<br>`report:/stable_ports/completion_batches/stats/short_prefixes [value]` |

解释与缺口：覆盖扩大不是速度改善；原条件代码容量界不变，提交仍按序且必须允许失效回退。

状态：完整回归及真实双线程按序诊断通过；sum/Raytrace 额外接管 6/4426 个 exact-domain task；未重测普通构建线程扩展性。

证据：[benchmarks/witness-prefix/design.md](../../benchmarks/witness-prefix/design.md) · [benchmarks/witness-prefix/README.md](../../benchmarks/witness-prefix/README.md)

## H5 · 按 Cell 实例归组的源 Run 查询执行

启用条件：sparse-cells 构建；--query-workers N；--query-grain N（默认 64）。

编译期依据：从原 Cell Query 编译 Entry 能力表；在源 Run 的只读边界内跨规则合并同一实际 Cell 实例，保留原 Query 与现有槽位。

替代的旧工作：不合格 Cell 查询的批量缓冲和逐 Entry 类型准入；重复遍历全体 seed；已覆盖查询的串行 host 和逐规则 worker 等待。

运行时仍须满足：只执行本 Run 已激活的 Entry；current value、delta/watermark、实际结果来源、live 位及缓存/history 归属仍须有效。恢复原 Entry 胜者顺序后按原规则/RHS 顺序提交。

代码：[query_workers.rs](../../engine/cell-runtime/src/query_workers.rs) · [function_reads.rs](../../engine/cell-runtime/src/function_reads.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [cell_query.rs](../../engine/cell-runtime/src/cell_query.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/pre_resume_port_lookups [value]`<br>`report:/key_lookup_calls [value]`<br>`report:/inference_seconds [value]` |
| 成本 / 剩余工作 | `report:/query_workers/stats/admission_entry_checks [value]`<br>`report:/query_workers/stats/admission_table_checks [value]`<br>`report:/query_workers/stats/seed_selection_visits [value]`<br>`report:/query_workers/stats/entry_headers [value]`<br>`report:/query_workers/stats/chunks [value]`<br>`report:/query_workers/stats/frame_allocations [value]`<br>`report:/query_workers/stats/batch_buffers [value]`<br>`report:/query_workers/stats/answer_buffer_allocations [value]`<br>`report:/query_workers/stats/entry_buffer_bytes [value]`<br>`report:/query_workers/stats/output_buffer_capacity [value]`<br>`report:/query_workers/stats/rule_admissions [value]`<br>`report:/query_workers/stats/entry_mask_checks [value]`<br>`report:/query_workers/stats/seed_range_comparisons [value]`<br>`report:/query_workers/stats/cell_source_reads [value]`<br>`report:/query_workers/stats/cell_order_comparisons [value]`<br>`report:/query_workers/stats/serial_order_headers [value]`<br>`report:/query_workers/stats/winner_order_comparisons [value]`<br>`report:/query_workers/stats/deferred_winner_moves [value]`<br>`report:/query_workers/stats/completion_binding_moves [value]`<br>`report:/query_workers/stats/cell_queue_growths [value]`<br>`report:/query_workers/stats/borrowed_job_headers [value]`<br>`report:/query_workers/stats/peak_cell_queue_bytes [value]` |
| 覆盖 / 规模 / 回退 | `report:/query_workers/stats/entries [value]`<br>`report:/query_workers/stats/spine_entries [value]`<br>`report:/query_workers/stats/spine_point_reads [value]`<br>`report:/query_workers/stats/worker_entries [value]`<br>`report:/query_workers/stats/cell_instances [value]`<br>`report:/query_workers/stats/multi_entry_cells [value]`<br>`report:/query_workers/stats/cross_rule_cells [value]`<br>`report:/query_workers/stats/coordinator_entries [value]`<br>`report:/query_workers/stats/worker_steps [value]` |

解释与缺口：Entry 掩码检查与恢复源顺序仍有成本，不能只报告准入下降。worker_entries 仅含池线程，coordinator_entries 单列 inline 工作；两者之和是 entries。未把静态指令数当作耗时权重。构造子/枚举、已有 history/context、特殊端口索引仍保留原路径，尚未消除 repair 等待。

状态：Cell 实例跨规则归组已接入；跨规则读后写/别名/有序绑定测试、sum-bits 专用验收和完整 Raytrace Run 签名通过。16 次完整进程测量未建立加速：新 4 worker 中位数 11.561 s，旧 4 worker 10.779 s；成对区间仍跨 1。。

证据：[benchmarks/cell-query-workers/README.md](../../benchmarks/cell-query-workers/README.md) · [benchmarks/cell-query-workers/results.json](../../benchmarks/cell-query-workers/results.json) · [benchmarks/cell-query-workers/raytrace-full.md](../../benchmarks/cell-query-workers/raytrace-full.md) · [benchmarks/cell-run-queries/README.md](../../benchmarks/cell-run-queries/README.md) · [benchmarks/cell-run-queries/checks.json](../../benchmarks/cell-run-queries/checks.json) · [benchmarks/cell-run-queries/timing-summary.json](../../benchmarks/cell-run-queries/timing-summary.json) · [benchmarks/cell-run-queries/work-sum.json](../../benchmarks/cell-run-queries/work-sum.json)
