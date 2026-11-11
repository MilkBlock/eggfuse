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

启用条件：sparse-cells 构建；--query-workers N；--query-grain N（默认 64）；parallel-residuals 构建 + --parallel-residuals 可接管无前缀/吸收/范围特化的单次展开查询。

编译期依据：原 Cell Query 的固定 Entry 代码、pivot 和临时帧上界可共享，point-only 能力由原指令推导；稳定构造子完整覆盖证明候选来自共享 wiring。运行时仅收集当前 Run 已激活的 Entry，按实际 Cell 形成任务；当前发布 Cursor 与完整 Cell Query 共同证明其直接读取原 Row，不需要残余 Seed 的消费者投影。可选残余路径从同一 Query 和 Free Join Entry plan 推导只读列布局；封存 Run 内借用已有 membership 和字段。

替代的旧工作：已覆盖函数/构造子查询的串行 host、完整临时 Row 读取与重复 seed 扫描；构造子完整覆盖下的旧反向依赖补充；逐规则 worker 等待；恢复源顺序的第二次排序和 Cursor 排序移动；逐任务重复创建值/见证/候选临时帧；负匹配结果物化及全部 Entry 的中间结果槽初始化/写回；Run 末的全量 Cell 归组排序、独立排列向量、worker 重复计算帧宽度和查询地址；小 Run 的归组索引；已接管 Entry 的 Seed、route 下标间接读取、空 domain 占位和混合查询覆盖排除集合；带源 ordinal 的赢家直接按输入/深度/ordinal 选择，删除恢复源顺序的预排序和独立 Winners 容器；合格残余 Entry 的协调线程 Free Join 准入、domain 物化和 Frame 枚举由 worker 接管；直接 Entry 路径删除 Sieve 幸存者的 Seed/consumer 克隆、空 domain 登记及稍后的 Seed→worker 交接，条件筛选与精确查询在同一任务中完成；合格残余查询并入同一源 Run 的物理 Cell 队列，删除逐 kernel/pivot 执行汇合与结果交接。

运行时仍须满足：只执行本 Run 已激活的 Entry；current value、delta/watermark、实际结果来源、live 位及缓存/history 归属仍须有效。恢复原 Entry 胜者顺序后按原规则/RHS 顺序提交。 线程缓冲仅跨 Run 保留容量，每批完成、报错或展开均释放值/见证；每个 point Entry 至多一个结果才可预留任务上限。 当前 Run 任务连接结束后清空；新的静态代码与 kernel/Stage Entry 共享同一 Query。 残余输入保持原图枚举、所有权和后续增量激活；route 仍按原 witness/pivot 排序。survey 模式保留完整 Seed 流。 残余查询与 point 接续按实际 Cell 共同归组，但仍逐 Entry 执行；所有权、watermark 和按序 RHS 不变；小 Run inline。借用索引令候选 domain 在 feature 构建中使用 Arc；旧 point 缓存命中可能丢失，必须计入新增 key lookup。 接管范围仍排除 active Cursor；保留 reverse 候选选择，selected/shared 投影与逐 Entry 审计走兼容路径。新增筛选失败候选和批次必须付账。 排队期间保留原 Row 的一个 Rc；惰性索引列必须在协调线程准备完成。直接 Entry 与兼容 Seed 保留原匹配位置，不能以完成顺序选赢家。

代码：[query_workers.rs](../../engine/cell-runtime/src/query_workers.rs) · [query_reads.rs](../../engine/cell-runtime/src/query_reads.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [cell_query.rs](../../engine/cell-runtime/src/cell_query.rs) · [constructor_reads.rs](../../engine/cell-runtime/src/constructor_reads.rs) · [cell_match.rs](../../engine/cell-runtime/src/cell_match.rs) · [slots.rs](../../engine/cell-runtime/src/slots.rs) · [query_expansion_workers.rs](../../engine/cell-runtime/src/query_expansion_workers.rs) · [query_snapshot.rs](../../engine/cell-runtime/src/query_snapshot.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/pre_resume_port_lookups [value]`<br>`report:/key_lookup_calls [value]`<br>`report:/inference_seconds [value]` |
| 成本 / 剩余工作 | `report:/query_workers/stats/admission_entry_checks [value]`<br>`report:/query_workers/stats/admission_table_checks [value]`<br>`report:/query_workers/stats/seed_selection_visits [value]`<br>`report:/query_workers/stats/entry_headers [value]`<br>`report:/query_workers/stats/chunks [value]`<br>`report:/query_workers/stats/frame_allocations [value]`<br>`report:/query_workers/stats/batch_buffers [value]`<br>`report:/query_workers/stats/answer_buffer_allocations [value]`<br>`report:/query_workers/stats/entry_buffer_bytes [value]`<br>`report:/query_workers/stats/output_buffer_capacity [value]`<br>`report:/query_workers/stats/rule_admissions [value]`<br>`report:/query_workers/stats/entry_mask_checks [value]`<br>`report:/query_workers/stats/seed_range_comparisons [value]`<br>`report:/query_workers/stats/cell_source_reads [value]`<br>`report:/query_workers/stats/cell_order_comparisons [value]`<br>`report:/query_workers/stats/serial_order_headers [value]`<br>`report:/query_workers/stats/winner_order_comparisons [value]`<br>`report:/query_workers/stats/deferred_winner_moves [value]`<br>`report:/query_workers/stats/completion_binding_moves [value]`<br>`report:/query_workers/stats/cell_queue_growths [value]`<br>`report:/query_workers/stats/borrowed_job_headers [value]`<br>`report:/query_workers/stats/peak_cell_queue_bytes [value]`<br>`report:/query_workers/stats/task_order_headers [value]`<br>`report:/query_workers/stats/completion_slot_initializations [value]`<br>`report:/query_workers/stats/completion_slot_writes [value]`<br>`report:/query_workers/stats/constructors/domain_key_fields [value]`<br>`report:/query_workers/stats/constructors/metadata_reads [value]`<br>`report:/query_workers/stats/constructors/candidate_pushes [value]`<br>`report:/query_workers/stats/constructors/candidate_growths [value]`<br>`report:/query_workers/stats/constructors/candidate_sort_comparisons [value]`<br>`report:/query_workers/stats/frame_cache_borrows [value]`<br>`report:/query_workers/stats/frame_capacity_bytes [value]`<br>`report:/query_workers/stats/worker_frame_capacity_bytes [value]`<br>`report:/query_workers/stats/coordinator_frame_capacity_bytes [value]`<br>`report:/query_workers/stats/completion_headers [value]`<br>`report:/query_workers/stats/completion_error_checks [value]`<br>`report:/query_workers/stats/cell_task_probes [value]`<br>`report:/query_workers/stats/cell_task_records [value]`<br>`report:/query_workers/stats/cell_task_links [value]`<br>`report:/query_workers/stats/cell_task_emissions [value]`<br>`report:/query_workers/stats/cell_task_clears [value]`<br>`report:/query_workers/stats/cell_task_growths [value]`<br>`report:/query_workers/stats/cell_code_reads [value]`<br>`report:/query_workers/stats/active_template_visits [value]`<br>`report:/query_workers/stats/peak_cell_task_bytes [value]`<br>`report:/query_workers/stats/compiled_cell_code_bytes [value]`<br>`report:/entry_schedule/stats/consumer_seed_deliveries [value]`<br>`report:/entry_schedule/cell_entry_bytes [value]`<br>`report:/entry_schedule/legacy_route_bytes [value]`<br>`report:/entry_schedule/seed_bytes [value]`<br>`report:/stage_spine/stats/query_fragment_slots [value]`<br>`report:/stage_spine/stats/query_fragment_capacity_bytes [value]`<br>`report:/stage_spine/query_fragment_header_bytes [value]`<br>`report:/stage_spine/query_winner_bytes [value]`<br>`report:/query_workers/residual_expansion/stats/admission_probes [value]`<br>`report:/query_workers/residual_expansion/stats/index_rows_examined [value]`<br>`report:/query_workers/residual_expansion/stats/point_reads [value]`<br>`report:/query_workers/residual_expansion/stats/row_reads [value]`<br>`report:/query_workers/residual_expansion/stats/entry_header_capacity_bytes [value]`<br>`report:/query_workers/residual_expansion/stats/answer_capacity_bytes [value]`<br>`report:/query_workers/residual_expansion/stats/prepare_seconds [value]`<br>`report:/query_workers/residual_expansion/stats/execute_seconds [value]`<br>`report:/query_workers/residual_expansion/stats/worker_task_seconds [value]`<br>`report:/query_workers/residual_expansion/stats/input_rows [value]`<br>`report:/query_workers/residual_expansion/stats/filter_probes [value]`<br>`report:/query_workers/residual_expansion/stats/filter_rejected [value]`<br>`report:/query_workers/residual_expansion/stats/worker_inputs [value]`<br>`report:/query_workers/residual_expansion/stats/queued_row_owners [value]`<br>`report:/query_workers/residual_expansion/stats/merge_capacity_bytes [value]`<br>`report:/query_workers/residual_expansion/stats/order_comparisons [value]`<br>`report:/query_workers/residual_expansion/plan_capacity_bytes [value]` |
| 覆盖 / 规模 / 回退 | `report:/query_workers/stats/entries [value]`<br>`report:/query_workers/stats/spine_entries [value]`<br>`report:/query_workers/stats/spine_point_reads [value]`<br>`report:/query_workers/stats/worker_entries [value]`<br>`report:/query_workers/stats/cell_instances [value]`<br>`report:/query_workers/stats/multi_entry_cells [value]`<br>`report:/query_workers/stats/cross_rule_cells [value]`<br>`report:/query_workers/stats/coordinator_entries [value]`<br>`report:/query_workers/stats/worker_steps [value]`<br>`report:/query_workers/stats/constructors/lookups [value]`<br>`report:/query_workers/stats/constructors/domains [value]`<br>`report:/query_workers/stats/constructors/results [value]`<br>`report:/query_workers/stats/max_entries_per_cell [value]`<br>`report:/query_workers/stats/ungrouped_inline_entries [value]`<br>`report:/entry_schedule/stats/cell_entry_deliveries [value]`<br>`report:/stage_spine/stats/query_fragment_frames [value]`<br>`report:/stage_spine/stats/query_fragment_sealed_slots [value]`<br>`report:/query_workers/stats/sharing_audit/point_reads [value]`<br>`report:/query_workers/stats/sharing_audit/cross_entry_repeated_reads [value]`<br>`report:/query_workers/stats/sharing_audit/same_anchor_prefix_steps [value]`<br>`report:/query_workers/residual_expansion/stats/entries [value]`<br>`report:/query_workers/residual_expansion/stats/coordinator_entries [value]`<br>`report:/query_workers/residual_expansion/stats/worker_entries [value]`<br>`report:/query_workers/residual_expansion/stats/expansion_rows [value]`<br>`report:/query_workers/residual_expansion/stats/answers [value]`<br>`report:/query_workers/residual_expansion/stats/direct_entries [value]`<br>`report:/query_workers/residual_expansion/stats/direct_batches [value]`<br>`report:/query_workers/residual_expansion/stats/merged_runs [value]`<br>`report:/query_workers/residual_expansion/stats/run_pool_calls [value]`<br>`report:/query_workers/residual_expansion/stats/mixed_runs [value]` |

解释与缺口：源 Entry 刷新、Cursor 展开、逐规则 route 排序仍存在；任务索引有额外探查与内存。直接交接同时覆盖串行/worker Cell host，不能视作新增线程工作。记录布局不是整体分配或 cache miss。枚举及已有 history/context/local-witness 保持原 host；RHS/repair 未并行化。逐规则 search_s 不含延迟完成。 owned-instance/v1 仅完成查询到 RHS 的实例交接；候选格式更宽，编译输入引用增加 2,048 字节。旧 Binding 重装未在历史 Work 中收费，不能用跨表示的历史等权分数证明这步收益；新增片段覆盖数不奖励，完整 allocator 成本单独对照。 E3 的 cell-span/v1 进一步删除 RHS 到 Entry 的逐输出重复登记，效果执行和最终发布仍按序；历史保留尚未统一。 cell-results/v1 接通合格 RHS 结果到 Entry/history 的同一存储，并保留原 Run 发布；这减少协调线程交接，不是把图写入移入 worker。 Cell 输入投影现在独立决定赢家与 legacy origin key，实例的 RHS 结果不再参与身份。纯查询实例沿用连续 Slots 比较，无新 key 存储；这是提前执行 RHS 的正确性准备，尚非新增计算接管或加速。 winner-ordering input-depth-ordinal/v1 用唯一 source ordinal 保持同输入同深度的源顺序，残余合并仍执行。sum-bits 删除 1244 条中间赢家搬运和 383 个容器批次；execute alloc/realloc 少 286 次、累计请求少 308544 字节。旧比较计数遗漏第二次 key 排序，跨版本比较数不可直接作收益。本步未测完整速度。 114543ae 五提交检查点已完成：当前四线程 sum-bits/Raytrace 推理中位数 25.098 ms/8.476 s，上次完整计时四线程为 24.669 ms/8.436 s；未通过总体加速门槛。完整 Raytrace 少 432416 条赢家中间搬运，但末轮有波动，不能以工作计数代替性能验收。 cell-query-sharing-audit 只诊断、不接管。sum-bits/Raytrace128 跨入口重复读取为 24/734，同锚点同前缀步骤均为 0；其中可归于字面量查询键的重复为 4/679。诊断键/锚点复制成本仅存在于该 feature，不参与普通构建性能评分。下一切口是必达的输入无关读取，不给所有 Cell 加通用缓存。 Run 合并后的 header/answer 容量与 task/execute 时间可包含共同执行的 point 工作，不能与旧 residual-only 字段直接比较；批次减少不是速度收益。

状态：owned-instance/v1 查询与 RHS 共用 Cell Instance；cell-results/v1 接通合格输出到 Entry/history 的共享存储。sum-bits 短例与指定语义验收通过，RHS 图效果仍按序提交；完整多线程速度收益未建立；残余准入/枚举已接通并通过 Run 边界回归；Raytrace 新路径总 key 查询增加 18,927，默认关闭，没有新增速度或满载结论；直接 Entry 接管在完整 Raytrace 省掉 1,881,965 次 Seed/domain 交接，所有图/Sieve/发布计数不变，未新增测速结论；Run 队列将 Raytrace 19,395 个源批次合入 2,785 次完成，查询/图/发布工作量不变，新增 Row 保留、归组与排序缓冲需付账，未建立加速。

证据：[benchmarks/cell-query-workers/README.md](../../benchmarks/cell-query-workers/README.md) · [benchmarks/cell-query-workers/results.json](../../benchmarks/cell-query-workers/results.json) · [benchmarks/cell-query-workers/raytrace-full.md](../../benchmarks/cell-query-workers/raytrace-full.md) · [benchmarks/cell-run-queries/README.md](../../benchmarks/cell-run-queries/README.md) · [benchmarks/cell-run-queries/checks.json](../../benchmarks/cell-run-queries/checks.json) · [benchmarks/cell-run-queries/timing-summary.json](../../benchmarks/cell-run-queries/timing-summary.json) · [benchmarks/cell-run-queries/work-sum.json](../../benchmarks/cell-run-queries/work-sum.json) · [benchmarks/cell-constructor-queries/README.md](../../benchmarks/cell-constructor-queries/README.md) · [benchmarks/cell-constructor-queries/summary.json](../../benchmarks/cell-constructor-queries/summary.json) · [benchmarks/cell-constructor-queries/checks.json](../../benchmarks/cell-constructor-queries/checks.json) · [benchmarks/cell-constructor-queries/work-sum.json](../../benchmarks/cell-constructor-queries/work-sum.json) · [benchmarks/cell-worker-scratch/README.md](../../benchmarks/cell-worker-scratch/README.md) · [benchmarks/cell-worker-scratch/results.json](../../benchmarks/cell-worker-scratch/results.json) · [benchmarks/cell-worker-scratch/work-sum.json](../../benchmarks/cell-worker-scratch/work-sum.json) · [benchmarks/cell-worker-scratch/work-ray-prefix.json](../../benchmarks/cell-worker-scratch/work-ray-prefix.json) · [benchmarks/cell-activation-tasks/README.md](../../benchmarks/cell-activation-tasks/README.md) · [benchmarks/cell-activation-tasks/results.json](../../benchmarks/cell-activation-tasks/results.json) · [benchmarks/cell-activation-tasks/work-sum-g64.json](../../benchmarks/cell-activation-tasks/work-sum-g64.json) · [benchmarks/cell-activation-tasks/work-ray-prefix.json](../../benchmarks/cell-activation-tasks/work-ray-prefix.json) · [benchmarks/cell-entry-partition/README.md](../../benchmarks/cell-entry-partition/README.md) · [benchmarks/cell-entry-partition/results.json](../../benchmarks/cell-entry-partition/results.json) · [benchmarks/cell-entry-partition/work-sum-g64.json](../../benchmarks/cell-entry-partition/work-sum-g64.json) · [benchmarks/cell-entry-partition/work-ray-prefix.json](../../benchmarks/cell-entry-partition/work-ray-prefix.json) · [benchmarks/cell-owned-fragments/README.md](../../benchmarks/cell-owned-fragments/README.md) · [benchmarks/cell-owned-fragments/results.json](../../benchmarks/cell-owned-fragments/results.json) · [benchmarks/cell-joint-results/README.md](../../benchmarks/cell-joint-results/README.md) · [benchmarks/cell-joint-results/results.json](../../benchmarks/cell-joint-results/results.json) · [benchmarks/cell-input-identity/README.md](../../benchmarks/cell-input-identity/README.md) · [benchmarks/cell-input-identity/opportunity.json](../../benchmarks/cell-input-identity/opportunity.json) · [benchmarks/cell-input-identity/checks.json](../../benchmarks/cell-input-identity/checks.json) · [benchmarks/cell-winner-fold/README.md](../../benchmarks/cell-winner-fold/README.md) · [benchmarks/cell-winner-fold/results.json](../../benchmarks/cell-winner-fold/results.json) · [benchmarks/cell-winner-fold/timing.md](../../benchmarks/cell-winner-fold/timing.md) · [benchmarks/cell-winner-fold/timing.json](../../benchmarks/cell-winner-fold/timing.json) · [benchmarks/cell-query-sharing/README.md](../../benchmarks/cell-query-sharing/README.md) · [benchmarks/cell-query-sharing/results.json](../../benchmarks/cell-query-sharing/results.json) · [benchmarks/parallel-residuals/README.md](../../benchmarks/parallel-residuals/README.md) · [benchmarks/parallel-residuals/results.json](../../benchmarks/parallel-residuals/results.json) · [benchmarks/parallel-residuals/entry-takeover.json](../../benchmarks/parallel-residuals/entry-takeover.json) · [benchmarks/parallel-residuals/run-queue.json](../../benchmarks/parallel-residuals/run-queue.json)
