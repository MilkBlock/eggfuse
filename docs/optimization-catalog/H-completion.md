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

编译期依据：原 Cell Query 的固定 Entry 代码、pivot 和临时帧上界可共享，point-only 能力由原指令推导；稳定构造子完整覆盖证明候选来自共享 wiring。运行时仅收集当前 Run 已激活的 Entry，按实际 Cell 形成任务。

替代的旧工作：已覆盖函数/构造子查询的串行 host、完整临时 Row 读取与重复 seed 扫描；构造子完整覆盖下的旧反向依赖补充；逐规则 worker 等待；恢复源顺序的第二次排序和 Cursor 排序移动；逐任务重复创建值/见证/候选临时帧；负匹配结果物化及全部 Entry 的中间结果槽初始化/写回；Run 末的全量 Cell 归组排序、独立排列向量、worker 重复计算帧宽度和查询地址；小 Run 的归组索引。

运行时仍须满足：只执行本 Run 已激活的 Entry；current value、delta/watermark、实际结果来源、live 位及缓存/history 归属仍须有效。恢复原 Entry 胜者顺序后按原规则/RHS 顺序提交。 线程缓冲仅跨 Run 保留容量，每批完成、报错或展开均释放值/见证；每个 point Entry 至多一个结果才可预留任务上限。 当前 Run 任务连接结束后清空；新的静态代码与 kernel/Stage Entry 共享同一 Query。

代码：[query_workers.rs](../../engine/cell-runtime/src/query_workers.rs) · [query_reads.rs](../../engine/cell-runtime/src/query_reads.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [cell_query.rs](../../engine/cell-runtime/src/cell_query.rs) · [constructor_reads.rs](../../engine/cell-runtime/src/constructor_reads.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/pre_resume_port_lookups [value]`<br>`report:/key_lookup_calls [value]`<br>`report:/inference_seconds [value]` |
| 成本 / 剩余工作 | `report:/query_workers/stats/admission_entry_checks [value]`<br>`report:/query_workers/stats/admission_table_checks [value]`<br>`report:/query_workers/stats/seed_selection_visits [value]`<br>`report:/query_workers/stats/entry_headers [value]`<br>`report:/query_workers/stats/chunks [value]`<br>`report:/query_workers/stats/frame_allocations [value]`<br>`report:/query_workers/stats/batch_buffers [value]`<br>`report:/query_workers/stats/answer_buffer_allocations [value]`<br>`report:/query_workers/stats/entry_buffer_bytes [value]`<br>`report:/query_workers/stats/output_buffer_capacity [value]`<br>`report:/query_workers/stats/rule_admissions [value]`<br>`report:/query_workers/stats/entry_mask_checks [value]`<br>`report:/query_workers/stats/seed_range_comparisons [value]`<br>`report:/query_workers/stats/cell_source_reads [value]`<br>`report:/query_workers/stats/cell_order_comparisons [value]`<br>`report:/query_workers/stats/serial_order_headers [value]`<br>`report:/query_workers/stats/winner_order_comparisons [value]`<br>`report:/query_workers/stats/deferred_winner_moves [value]`<br>`report:/query_workers/stats/completion_binding_moves [value]`<br>`report:/query_workers/stats/cell_queue_growths [value]`<br>`report:/query_workers/stats/borrowed_job_headers [value]`<br>`report:/query_workers/stats/peak_cell_queue_bytes [value]`<br>`report:/query_workers/stats/task_order_headers [value]`<br>`report:/query_workers/stats/completion_slot_initializations [value]`<br>`report:/query_workers/stats/completion_slot_writes [value]`<br>`report:/query_workers/stats/constructors/domain_key_fields [value]`<br>`report:/query_workers/stats/constructors/metadata_reads [value]`<br>`report:/query_workers/stats/constructors/candidate_pushes [value]`<br>`report:/query_workers/stats/constructors/candidate_growths [value]`<br>`report:/query_workers/stats/constructors/candidate_sort_comparisons [value]`<br>`report:/query_workers/stats/frame_cache_borrows [value]`<br>`report:/query_workers/stats/frame_capacity_bytes [value]`<br>`report:/query_workers/stats/worker_frame_capacity_bytes [value]`<br>`report:/query_workers/stats/coordinator_frame_capacity_bytes [value]`<br>`report:/query_workers/stats/completion_headers [value]`<br>`report:/query_workers/stats/completion_error_checks [value]`<br>`report:/query_workers/stats/cell_task_probes [value]`<br>`report:/query_workers/stats/cell_task_records [value]`<br>`report:/query_workers/stats/cell_task_links [value]`<br>`report:/query_workers/stats/cell_task_emissions [value]`<br>`report:/query_workers/stats/cell_task_clears [value]`<br>`report:/query_workers/stats/cell_task_growths [value]`<br>`report:/query_workers/stats/cell_code_reads [value]`<br>`report:/query_workers/stats/active_template_visits [value]`<br>`report:/query_workers/stats/peak_cell_task_bytes [value]`<br>`report:/query_workers/stats/compiled_cell_code_bytes [value]` |
| 覆盖 / 规模 / 回退 | `report:/query_workers/stats/entries [value]`<br>`report:/query_workers/stats/spine_entries [value]`<br>`report:/query_workers/stats/spine_point_reads [value]`<br>`report:/query_workers/stats/worker_entries [value]`<br>`report:/query_workers/stats/cell_instances [value]`<br>`report:/query_workers/stats/multi_entry_cells [value]`<br>`report:/query_workers/stats/cross_rule_cells [value]`<br>`report:/query_workers/stats/coordinator_entries [value]`<br>`report:/query_workers/stats/worker_steps [value]`<br>`report:/query_workers/stats/constructors/lookups [value]`<br>`report:/query_workers/stats/constructors/domains [value]`<br>`report:/query_workers/stats/constructors/results [value]`<br>`report:/query_workers/stats/max_entries_per_cell [value]`<br>`report:/query_workers/stats/ungrouped_inline_entries [value]` |

解释与缺口：当前任务索引仍需逐 Entry 探查并保留额外容量；上游 Seed、route 与 Cursor 准备未消除。代码/字段页 Arc 原子引用计数、硬件缓存事件未单独计量。枚举及已有 history/context/local-witness 保持旧 host；RHS/repair 未并行化。逐规则 search_s 不包括延迟完成，不能用作调度权重。

状态：cell-run/v4 激活时形成 Cell 任务，共享编译代码并删除归组排序；g64 sum-bits/128-Run Raytrace 净少 7,748/22,659 等权操作。grain 1 sum 与短例仍增工作，索引增加内存。语义短检查通过，完整线程加速仍未证实。

证据：[benchmarks/cell-query-workers/README.md](../../benchmarks/cell-query-workers/README.md) · [benchmarks/cell-query-workers/results.json](../../benchmarks/cell-query-workers/results.json) · [benchmarks/cell-query-workers/raytrace-full.md](../../benchmarks/cell-query-workers/raytrace-full.md) · [benchmarks/cell-run-queries/README.md](../../benchmarks/cell-run-queries/README.md) · [benchmarks/cell-run-queries/checks.json](../../benchmarks/cell-run-queries/checks.json) · [benchmarks/cell-run-queries/timing-summary.json](../../benchmarks/cell-run-queries/timing-summary.json) · [benchmarks/cell-run-queries/work-sum.json](../../benchmarks/cell-run-queries/work-sum.json) · [benchmarks/cell-constructor-queries/README.md](../../benchmarks/cell-constructor-queries/README.md) · [benchmarks/cell-constructor-queries/summary.json](../../benchmarks/cell-constructor-queries/summary.json) · [benchmarks/cell-constructor-queries/checks.json](../../benchmarks/cell-constructor-queries/checks.json) · [benchmarks/cell-constructor-queries/work-sum.json](../../benchmarks/cell-constructor-queries/work-sum.json) · [benchmarks/cell-worker-scratch/README.md](../../benchmarks/cell-worker-scratch/README.md) · [benchmarks/cell-worker-scratch/results.json](../../benchmarks/cell-worker-scratch/results.json) · [benchmarks/cell-worker-scratch/work-sum.json](../../benchmarks/cell-worker-scratch/work-sum.json) · [benchmarks/cell-worker-scratch/work-ray-prefix.json](../../benchmarks/cell-worker-scratch/work-ray-prefix.json) · [benchmarks/cell-activation-tasks/README.md](../../benchmarks/cell-activation-tasks/README.md) · [benchmarks/cell-activation-tasks/results.json](../../benchmarks/cell-activation-tasks/results.json) · [benchmarks/cell-activation-tasks/work-sum-g64.json](../../benchmarks/cell-activation-tasks/work-sum-g64.json) · [benchmarks/cell-activation-tasks/work-ray-prefix.json](../../benchmarks/cell-activation-tasks/work-ray-prefix.json)
