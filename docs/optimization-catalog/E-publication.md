# E · 发布与共享 Entry

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## E1 · Run 变更批次与共享 Entry 参数

启用条件：普通执行路径；编译共享入口谓词。

编译期依据：只发布当前 committed row，按消费者水位交付。

替代的旧工作：重复逐规则登记、字段复制与重解码。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[change_batch.rs](../../engine/cell-runtime/src/change_batch.rs) · [entry_schedule.rs](../../engine/cell-runtime/src/entry_schedule.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/entry_schedule/stats/parameter_packets_reused [value]`<br>`report:/entry_schedule/stats/borrowed_slots [value]` |
| 成本 / 剩余工作 | `report:/entry_schedule/stats/predicate_checks [value]`<br>`report:/entry_schedule/stats/row_decodes [value]`<br>`report:/entry_schedule/stats/node_notifications [value]`<br>`report:/publication/row_reads [value]`<br>`report:/entry_schedule/seed_bytes [value]` |
| 覆盖 / 规模 / 回退 | `report:/entry_schedule/nodes [value]`<br>`report:/entry_schedule/live_packets [value]` |

解释与缺口：参数共享是表示优化；不能省略可观察的 RHS 发布与源 Run 边界。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[docs/CHANGE_BATCH.md](../../docs/CHANGE_BATCH.md)

## E2 · Entry 持有 producer publication

启用条件：--entry-publications；ownership 自动启用。

编译期依据：唯一穷尽入口、当前可见性、同 key forwarding、最后写入者。

替代的旧工作：独立 Spine source 索引与重复退休维护。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[entry_schedule.rs](../../engine/cell-runtime/src/entry_schedule.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/node_cursor_reads [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/legacy_entry_writes [value]`<br>`report:/stage_spine/stats/legacy_retirement_checks [value]`<br>`report:/stage_spine/stats/legacy_cursor_probes [value]`<br>`report:/entry_schedule/stats/entry_publication_writes [value]`<br>`report:/entry_schedule/stats/entry_retirement_checks [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/node_entry_references [value]`<br>`report:/stage_spine/legacy_entry_references [value]` |

解释与缺口：比较旧/新索引双方维护成本；不要只报告 legacy writes 降低。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/entry-publications/README.md](../../benchmarks/entry-publications/README.md)

## E3 · Cell 输出 capture 与片段 publication

启用条件：非 audit_receipts；Cell 的全部待发布输出均为 permanent、Entry-owned；单输出和多输出使用同一槽位机制。

编译期依据：共享 Cell Output 描述、源 Cell/内部 effect 顺序、permanent 与 Entry ownership 证明。

替代的旧工作：已覆盖输出的 direct-publication 哈希登记与边界转换、独立 FragmentPublication 包和表编号数组；Entry Pending 往返及重复 completion 存储已在上一轮删除。

运行时仍须满足：仅在合法发布边界投递；同一 Entry 必须选择源顺序最后的候选。收据 forwarding、存活与可见性、部分 scope 发布及世代仍需验证。

代码：[cell_effects.rs](../../engine/cell-runtime/src/cell_effects.rs) · [cell.rs](../../engine/cell-runtime/src/cell.rs) · [stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [entry_schedule.rs](../../engine/cell-runtime/src/entry_schedule.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/fragment_direct_inserts_avoided [value]`<br>`report:/stage_spine/stats/fragment_deliveries [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/fragment_packets [value]`<br>`report:/stage_spine/stats/fragment_receipt_spills [value]`<br>`report:/stage_spine/stats/fragment_delivery_checks [value]`<br>`report:/stage_spine/stats/direct_publication_hash_probes [value]`<br>`report:/entry_schedule/stats/publication_slot_probes [value]`<br>`report:/entry_schedule/stats/fragment_pending_writes [value]`<br>`report:/entry_schedule/stats/fragment_pending_reads [value]`<br>`report:/entry_schedule/stats/publication_pending_pushes [value]`<br>`report:/entry_schedule/stats/publication_candidate_checks [value]`<br>`report:/entry_schedule/stats/publication_loser_skips [value]`<br>`report:/stage_spine/stats/completion_boundary_records [value]`<br>`report:/stage_spine/stats/completion_boundary_reads [value]`<br>`report:/stage_spine/stats/completion_order_checks [value]`<br>`report:/stage_spine/stats/completion_cell_visits [value]`<br>`report:/stage_spine/stats/completion_cursor_moves [value]`<br>`report:/entry_schedule/stats/fragment_slot_probes [value]`<br>`report:/entry_schedule/stats/fragment_slot_replacements [value]`<br>`report:/entry_schedule/stats/fragment_older_skips [value]`<br>`report:/stage_spine/stats/cell_output_spans [value]`<br>`report:/stage_spine/stats/cell_output_slots [value]`<br>`report:/stage_spine/stats/cell_output_receipts [value]`<br>`report:/stage_spine/stats/cell_output_slot_reads [value]`<br>`report:/stage_spine/stats/cell_output_checks [value]`<br>`report:/stage_spine/stats/cell_output_deliveries [value]`<br>`report:/stage_spine/stats/peak_cell_output_slots [value]`<br>`report:/stage_spine/stats/receipt_attempts [value]`<br>`report:/stage_spine/stats/receipt_hits [value]`<br>`report:/stage_spine/stats/receipt_redirects [value]`<br>`report:/entry_schedule/stats/publication_pending_reuses [value]`<br>`report:/stage_spine/stats/effect_frames [value]`<br>`report:/stage_spine/stats/effect_slots_initialized [value]`<br>`report:/stage_spine/stats/effect_slot_probes [value]`<br>`report:/stage_spine/stats/effect_slot_targets [value]`<br>`report:/stage_spine/stats/effect_outputs_reused [value]`<br>`report:/stage_spine/stats/effect_output_copies [value]`<br>`report:/stage_spine/stats/effect_aborted_frames [value]`<br>`report:/stage_spine/effect_plan_cache_bytes [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/fragment_receipts [value]` |

解释与缺口：Cell effect 槽直接承担已覆盖输出；永久 Entry 由输出布局接管，删除/可见性及未知边界仍保留。Entry 先选择同批次胜者再验证；现在 Cell 布局还消除同一实际来源的较早发布，保留最后原 operation 及实际 donor。sum-bits 候选/Entry 探测 9027→8703，输出登记/读取/解析 8774→8450；实际发布、查询、历史与 Run 不变。仅 Eq 相等不能作为静态合并证明。当前等权账本本步节省 1666 项，相对混合输出前 3e622300 累计节省 746 项；这不是速度证据。未知边界、源 marker 物化、一般 Bake 组合及最终多线程验收仍未完成。

状态：Cell 输出及 RHS receipt 数据流已统一；短样例语义和源顺序保持，分配下降；推理及整进程配对区间跨持平，尚未证明加速。。

证据：[benchmarks/witness-prefix/design.md](../../benchmarks/witness-prefix/design.md) · [benchmarks/witness-prefix/normal/README.md](../../benchmarks/witness-prefix/normal/README.md) · [benchmarks/cell-unification/publication.md](../../benchmarks/cell-unification/publication.md) · [benchmarks/cell-unification/publication-results.json](../../benchmarks/cell-unification/publication-results.json) · [benchmarks/cell-unification/capture.md](../../benchmarks/cell-unification/capture.md) · [benchmarks/cell-unification/capture-results.json](../../benchmarks/cell-unification/capture-results.json) · [benchmarks/cell-unification/effects.md](../../benchmarks/cell-unification/effects.md) · [benchmarks/cell-unification/effects-results.json](../../benchmarks/cell-unification/effects-results.json) · [benchmarks/cell-unification/mixed-outputs-check.json](../../benchmarks/cell-unification/mixed-outputs-check.json) · [benchmarks/cell-unification/publication-winners-check.json](../../benchmarks/cell-unification/publication-winners-check.json) · [benchmarks/cell-unification/output-selection-check.json](../../benchmarks/cell-unification/output-selection-check.json)
