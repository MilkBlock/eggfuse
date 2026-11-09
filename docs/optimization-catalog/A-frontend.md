# A · 前端表示与 marker

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## A1 · 结构 key 与有界 native Bake

启用条件：编译命令默认前端。

编译期依据：结构 key ABI、源程序及训练环境检查。

替代的旧工作：重复表达的前端重写与分析。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[keys.rs](../../tools/cell-compiler/src/keys.rs) · [native_analyze.rs](../../src/native_analyze.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/key_operations [value]` |
| 成本 / 剩余工作 | `report:/load_seconds [value]`<br>`report:/setup_seconds [value]` |
| 覆盖 / 规模 / 回退 | `program:/source_core/structural_key/nodes [count]` |

解释与缺口：缺少统一导出的分阶段离线编译时间、Bake 峰值内存和前后 IR 节点数；运行时 key_operations 不是离线收益。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[README.md](../../README.md)

## A2 · marker 选择与 Recipe lowering

启用条件：编译时选择；产物绑定 recipe digest。

编译期依据：原查询变量、运算符和控制流一致，marker 不改变原程序效果。

替代的旧工作：重复入口谓词与参数表达。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[markers.rs](../../tools/cell-compiler/src/markers.rs) · [marker_ir.rs](../../tools/cell-compiler/src/marker_ir.rs) · [mod.rs](../../engine/cell-runtime/src/compiler/mod.rs) · [cell_symbols.rs](../../engine/cell-runtime/src/cell_symbols.rs) · [cell_binding.rs](../../engine/cell-runtime/src/cell_binding.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/marker_roots [value]` |
| 成本 / 剩余工作 | `report:/setup_seconds [value]`<br>`report:/setup_allocations/requested_bytes [value]` |
| 覆盖 / 规模 / 回退 | `program:/marker_tables [count]`<br>`program:/entry_schedule/nodes [count]` |

解释与缺口：marker 数量仅表示静态规模；没有统一的逐 marker 净节省计数，需要禁用/启用同源消融。 Source marker publication now uses the same Cell equality/congruence implementation as typed cross-stage proofs. Source operands are resolved once; the independent union-find and repeated term/key closure loop are removed. The source frontend still owns publication admission and original effect boundaries. Selection, publication matching and iterative materialization boundaries remain separate. Cached compiler operands add storage; no allocation, speed or runtime-repair savings are inferred. Source marker publication, typed local projection and runtime query/Entry frames now share Cell Operand and Bindings. Arg is the typed alias, with unchanged wire shape. Equality evidence stays at each source boundary; rollback remains with the caller. Marker fields are lowered before candidate enumeration and variable names are borrowed. Candidate policies and materialization boundaries remain separate; temporary patterns and generic binding costs have not been timing/allocation-profiled. Local source/typed candidate projection and uniqueness now execute shared Cell code. Typed donors are compared by source row, source publication candidates by binding; the first equivalent candidate is preserved. Separate uniqueness collections are removed and ambiguity stops enumeration. Operator filtering precedes typed frame copies. Source-root deduplication, donor admission and iterative materialization remain necessary. Removed static work is not separately operation/allocation-counted. The acab2911 five-implementation checkpoint used four frozen normal-release sum-bits lanes. Paired inference/process intervals cross 1 against immediate, last-timed and historical controls. No speedup or strict speed preservation is established; this does not measure native compiler time or allocations.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[tools/cell-compiler/README.md](../../tools/cell-compiler/README.md) · [benchmarks/cell-unification/marker-symbols-check.json](../../benchmarks/cell-unification/marker-symbols-check.json) · [benchmarks/cell-unification/projection-binding-check.json](../../benchmarks/cell-unification/projection-binding-check.json) · [benchmarks/cell-unification/projection-candidates-results.json](../../benchmarks/cell-unification/projection-candidates-results.json)

## A3 · .egg marker 结果变量交接

启用条件：编译参数 --marker-handoff values；默认 legacy 保持冻结目录。

编译期依据：原始永久构造子 LHS 与完整 marker 参数证明结果；按原求值位置捕获生产者返回值。

替代的旧工作：消费者 RHS 重建已知构造子及生成 marker 参数时的重复构造。

运行时仍须满足：剩余 LHS、可变函数、数值 guard 和原 Run 继续执行；可删除或 subsume 的构造子不进入证明；旧 completion 路径仍保留。

代码：[marker_handoff.rs](../../tools/cell-compiler/src/marker_handoff.rs) · [markers.rs](../../tools/cell-compiler/src/markers.rs) · [marker_ir.rs](../../tools/cell-compiler/src/marker_ir.rs) · [cell_construction.rs](../../engine/cell-runtime/src/cell_construction.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/key_lookup_calls [value]`<br>`report:/entry_schedule/stats/fragment_pending_writes [value]` |
| 成本 / 剩余工作 | `report:/allocations/alloc_calls [value]`<br>`report:/allocations/realloc_calls [value]`<br>`report:/allocations/requested_bytes [value]`<br>`report:/setup_allocations/alloc_calls [value]`<br>`report:/setup_allocations/requested_bytes [value]`<br>`report:/entry_schedule/stats/fragment_pending_reads [value]`<br>`report:/entry_schedule/stats/publication_slot_probes [value]` |
| 覆盖 / 规模 / 回退 | `program:/marker_tables [count]`<br>`program:/recipe/rules/*/effects [count]` |

解释与缺口：静态替换详情在 marker-selection.json/result_handoff；不能当运行时 credit。必须重编译源程序，旧目录不能搬用。sum-bits 的严格 native 全图差异已定位为等成本提取及合法 hoist 选择：98 个提取成本一致，选中项由已有 Add/Mul 交换律对应，核心 Expr 等价与可见性一致。该最终状态诊断不等于完整跨引擎逐 Run 或生成代码证明。 Native marker emission and typed static aliases now execute one Cell construction proof, preserving the first actual query/effect result and ordered fresh construction. Typed Copy/invalidation use the same flow; native lexical binding and purity/deletion eligibility remain frontend obligations. The 5853 sum-bits static eliminations already existed; this rewrite adds no runtime credit. Proof-state/key layout costs are not yet timed or allocation-profiled. Shared propagation does not unify marker selection or iterative materialization boundaries.

状态：实验模式已实现；短样例减少查询和分配；尚未完成新目录及历史最快配置的性能验收。

证据：[benchmarks/marker-handoff/design.md](../../benchmarks/marker-handoff/design.md) · [benchmarks/marker-handoff/README.md](../../benchmarks/marker-handoff/README.md) · [benchmarks/marker-handoff/choice-diagnosis.md](../../benchmarks/marker-handoff/choice-diagnosis.md) · [benchmarks/cell-unification/construction-check.json](../../benchmarks/cell-unification/construction-check.json)
