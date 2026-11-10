# D · RHS 执行

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## D1 · 静态构造子别名与 known results

启用条件：typed RHS alias 计划。

编译期依据：已匹配 query/effect 的同 key 结果；删除 guard 保留。

替代的旧工作：重复构造调用和部分 RHS frame。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[known_results.rs](../../engine/cell-runtime/src/known_results.rs) · [cell_match.rs](../../engine/cell-runtime/src/cell_match.rs) · [cell_construction.rs](../../engine/cell-runtime/src/cell_construction.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/known_results/static_eliminated [value]`<br>`report:/known_results/lazy_prefix_eliminated [value]`<br>`report:/known_results/avoided_lookups [value]`<br>`report:/stats/rhs_frames_avoided [value]` |
| 成本 / 剩余工作 | `report:/known_results/requests [value]`<br>`report:/known_results/dirty [value]`<br>`report:/known_results/mismatched [value]`<br>`report:/known_results/expired [value]` |
| 覆盖 / 规模 / 回退 | `program:/known_results/static_aliases [count]`<br>`program:/known_results/plans [count]` |

解释与缺口：本轮补导出已有 known_stats；旧 report 中缺失，不得补零。static plan 数不是运行时消除次数。 QueryFacts and requested row projection now belong to Cell; the static alias plan remains here. Moving this representation does not establish full known-results takeover. Native marker emission and typed static aliases now execute one Cell construction proof, preserving the first actual query/effect result and ordered fresh construction. Typed Copy/invalidation use the same flow; native lexical binding and purity/deletion eligibility remain frontend obligations. The 5853 sum-bits static eliminations already existed; this rewrite adds no runtime credit. Proof-state/key layout costs are not yet timed or allocation-profiled. Shared propagation does not unify marker selection or iterative materialization boundaries. Cell 路线证明现借用同一份构造子别名，原始 source slot 仍逐项校验；域已返回唯一 witness 时直接读取，不再重新按 key 查找。sum-bits 查询 19237→18692，旧接线兼容对照已取得全部 545 次减少；扩大接线 6325→6825 只再省 11 次解码、多 12 次路线比较，等权 Work 单项净值 -1，目录容量合计多 4524 字节。c2f665a2 的五组交错实测：相对 135dfb1b，配对推理比 1.0131 [1.0061,1.0438]，整进程比 1.0435 [1.0305,1.0863]；本轮性能回退。新增接线加载中位数 68.685→73.211ms（同一运行时），尚未证明覆盖扩张值得默认采用。纯 witness 直读对照的时间区间跨 1；计数减少不等于加速。下一步收缩低收益接线及其加载成本。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[docs/RHS_BLOCK_WORK.md](../../docs/RHS_BLOCK_WORK.md) · [benchmarks/cell-unification/match-completion-results.json](../../benchmarks/cell-unification/match-completion-results.json) · [benchmarks/cell-unification/construction-check.json](../../benchmarks/cell-unification/construction-check.json) · [benchmarks/cell-unification/alias-routes-check.json](../../benchmarks/cell-unification/alias-routes-check.json)

## D2 · 单写 RHS、稀疏 frame 与 merge program

启用条件：typed single-write / scalar merge / constructor-only 路径。

编译期依据：纯前缀、定义使用关系、merge 语义。

替代的旧工作：通用 Cell 分配、slot 初始化和 merge 解释。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[cell_effects.rs](../../engine/cell-runtime/src/cell_effects.rs) · [row_kernel.rs](../../engine/cell-runtime/src/row_kernel.rs) · [graph.rs](../../engine/cell-runtime/src/graph.rs) · [merge_programs.rs](../../engine/cell-runtime/src/merge_programs.rs) · [cell.rs](../../engine/cell-runtime/src/cell.rs) · [cell_handoff.rs](../../engine/cell-runtime/src/cell_handoff.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/single_writes [value]`<br>`report:/stats/transient_writes [value]`<br>`report:/stats/rhs_frames_avoided [value]`<br>`report:/stats/scalar_unchanged [value]` |
| 成本 / 剩余工作 | `report:/stats/cells_created [value]`<br>`report:/stats/merge_program_operations [value]`<br>`report:/stats/merge_port_reads [value]`<br>`report:/stats/merge_program_constructs [value]`<br>`report:/allocations/alloc_calls [value]`<br>`report:/stage_spine/stats/effect_frames [value]`<br>`report:/stage_spine/stats/effect_slots_initialized [value]`<br>`report:/stage_spine/stats/effect_slot_probes [value]`<br>`report:/stage_spine/stats/effect_slot_targets [value]`<br>`report:/stage_spine/stats/effect_outputs_reused [value]`<br>`report:/stage_spine/stats/effect_output_copies [value]`<br>`report:/stage_spine/stats/effect_aborted_frames [value]`<br>`report:/stage_spine/effect_plan_cache_bytes [value]` |
| 覆盖 / 规模 / 回退 | `program:/single_writes [count]`<br>`program:/merge_programs/programs [count]`<br>`report:/stats/matched_cells_completed [value]` |

解释与缺口：匹配事实直接完成已接入同一 Cell Completion；sum-bits 有 21 条合格规则、419 次实际接管。旧 rhs_frames_avoided 已含空临时帧释放，新 matched_cells_completed 仅计覆盖，当前等权 Work 增量为 0。删除单独 HandoffFrame、私有 union 队列、Copy 重写及无人读取的 handoffs 登记；绑定也不再携带仅供该登记使用的 producer 编号。保留原有 union 队列、真实结果、Run 顺序和 continuation 深度/残余计数。sealed_slot_reads 47308→48048 表示沿用已有输入权限，并非新增相同数量的图读取。静态选择替换原 constructor_only 标志，多一次别名覆盖扫描；未单独量化分配或时间收益。单写、一般 RHS 选择、源 marker 物化、一般 Bake 组合和最终并行验收仍待完成。本步不测速，808aadb3 仍为最后检查点。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[docs/SPARSE_CELL_CPU.md](../../docs/SPARSE_CELL_CPU.md) · [benchmarks/cell-unification/effects.md](../../benchmarks/cell-unification/effects.md) · [benchmarks/cell-unification/effects-results.json](../../benchmarks/cell-unification/effects-results.json) · [benchmarks/cell-unification/mixed-outputs-check.json](../../benchmarks/cell-unification/mixed-outputs-check.json) · [benchmarks/cell-unification/output-selection-check.json](../../benchmarks/cell-unification/output-selection-check.json) · [benchmarks/cell-unification/output-donors-results.json](../../benchmarks/cell-unification/output-donors-results.json) · [benchmarks/cell-unification/closed-cells-check.json](../../benchmarks/cell-unification/closed-cells-check.json) · [benchmarks/cell-unification/matched-completion-check.json](../../benchmarks/cell-unification/matched-completion-check.json)
