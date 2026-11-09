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
| 成本 / 剩余工作 | `report:/entry_schedule/stats/predicate_checks [value]`<br>`report:/entry_schedule/stats/row_decodes [value]`<br>`report:/entry_schedule/stats/node_notifications [value]`<br>`report:/publication/row_reads [value]` |
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

## E3-new · 片段内部 publication

启用条件：至少两个 anchor；全为 permanent、Entry-owned，非 audit_receipts。

编译期依据：共享 anchor wiring + compact receipts + Entry 槽位 ordinal。

替代的旧工作：中间 direct-publication 哈希登记/重映射与二次 Entry 寻址。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[stage_spine.rs](../../engine/cell-runtime/src/stage_spine.rs) · [entry_schedule.rs](../../engine/cell-runtime/src/entry_schedule.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stage_spine/stats/fragment_direct_inserts_avoided [value]`<br>`report:/stage_spine/stats/fragment_deliveries [value]` |
| 成本 / 剩余工作 | `report:/stage_spine/stats/fragment_packets [value]`<br>`report:/stage_spine/stats/fragment_receipt_spills [value]`<br>`report:/stage_spine/stats/fragment_delivery_checks [value]`<br>`report:/stage_spine/stats/direct_publication_hash_probes [value]`<br>`report:/entry_schedule/stats/publication_slot_probes [value]`<br>`report:/entry_schedule/stats/fragment_pending_writes [value]`<br>`report:/entry_schedule/stats/fragment_pending_reads [value]`<br>`report:/entry_schedule/stats/publication_pending_pushes [value]` |
| 覆盖 / 规模 / 回退 | `report:/stage_spine/stats/fragment_receipts [value]` |

解释与缺口：这是有覆盖证明的 RHS 片段交付；未知边界仍走旧路径。audit_receipts 会主动禁用该快路，验证不能只用 audit 模式。

状态：本轮实现；正确性与性能见本轮验证记录。

证据：[benchmarks/witness-prefix/design.md](../../benchmarks/witness-prefix/design.md)
