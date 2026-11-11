# F · 端口、共享 wiring 与生命周期

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## F1 · result-only repair ports

启用条件：--repair-ports；sparse-cells 同时复用已校验 footprint 准备普通构造子的订阅。

编译期依据：typed key footprint 区分输入和结果变化；完整标量构造子的 Eq 输入列及 Eq 输出，原始操作提供当前 canonical 字段。

替代的旧工作：只有输出改变时的 key 重建与订阅重做；普通订阅的标量字段检查和新字段重复找根，以及存活 witness 订阅集合的删后重插。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。 新 Eq 集合仍排序去重；旧订阅 ID 仍 canonicalize。反向边差分、退役清理、union 唤醒、字段容器回退均保留，不能算作内部 repair 消除。

代码：[repair_ports.rs](../../engine/cell-runtime/src/repair_ports.rs) · [graph.rs](../../engine/cell-runtime/src/graph.rs) · [maintenance.rs](../../engine/cell-runtime/src/maintenance.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stats/repair_key_hash_changes [value]`<br>`report:/stats/repaired_dependencies [value]`<br>`report:/maintenance/stats/subscription_scalar_fields_skipped [value]`<br>`report:/maintenance/stats/subscription_root_reads_omitted [value]`<br>`report:/maintenance/stats/subscription_sets_replaced_in_place [value]` |
| 成本 / 剩余工作 | `report:/repair_ports/stats/attempts [value]`<br>`report:/repair_ports/stats/port_checks [value]`<br>`report:/repair_ports/stats/field_copies [value]` |
| 覆盖 / 规模 / 回退 | `report:/repair_ports/enabled [value]`<br>`report:/maintenance/stats/canonical_subscription_calls [value]` |

解释与缺口：收益必须与旧路径差值比较；key 改变仍有 repair。 Canonical subscription counters describe removed release-build work; debug assertions still check canonical roots. Existing Eq footprint storage is reused, with four global counters (32 B), no instance fields or second dependency graph. The selected footprint reads, exact set difference and reverse index remain. In-place replacement counts one removed remove/reinsert pair, not fewer edges. No timing gain is inferred from these counts.

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/result-port-repair/README.md](../../benchmarks/result-port-repair/README.md) · [benchmarks/cell-canonical-subscriptions/README.md](../../benchmarks/cell-canonical-subscriptions/README.md)

## F2 · Cell ownership 与共享 repair slices

启用条件：--cell-ownership / --local-unions 的相关后端。

编译期依据：全部标量 body、静态 signal→字段 wiring；未知外部关系保留。

替代的旧工作：逐字段反向订阅及逐 owner/body 扫描。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[cell_ownership.rs](../../engine/cell-runtime/src/cell_ownership.rs) · [ownership_slices.rs](../../engine/cell-runtime/src/ownership_slices.rs) · [local_union_cells.rs](../../engine/cell-runtime/src/local_union_cells.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/maintenance/stats/reverse_insert_attempts [value]`<br>`report:/maintenance/stats/reverse_remove_attempts [value]`<br>`report:/cell_ownership/stats/owned_births [value]` |
| 成本 / 剩余工作 | `report:/cell_ownership/stats/slice_steps [value]`<br>`report:/cell_ownership/stats/dispatch_comparisons [value]`<br>`report:/cell_ownership/stats/dispatch_scratch_growths [value]`<br>`report:/cell_ownership/stats/boundary_probes [value]` |
| 覆盖 / 规模 / 回退 | `report:/cell_ownership/inventory/eligible_live_facts [value]`<br>`report:/cell_ownership/inventory/unsupported_live_rows [value]` |

解释与缺口：早期 owner 扫描版本曾明显变慢；订阅减少不能单独证明更快。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/ownership-slices/README.md](../../benchmarks/ownership-slices/README.md) · [benchmarks/local-unions/README.md](../../benchmarks/local-unions/README.md)

## F3 · 跨模板共享符号与 frozen fragments

启用条件：ownership_fragments 证书；运行时只接受已烘焙 hop。

编译期依据：checked Entry substitutions；静态 frame/local wiring。

替代的旧工作：跨模板字段绑定记录和运行时 shape 构建。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[ownership_composition.rs](../../engine/cell-runtime/src/ownership_composition.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/cell_ownership/stats/composition_substituted_ports [value]`<br>`report:/cell_ownership/stats/composition_baked_hits [value]` |
| 成本 / 剩余工作 | `report:/cell_ownership/stats/composition_transition_probes [value]`<br>`report:/cell_ownership/stats/composition_shape_builds [value]`<br>`report:/cell_ownership/stats/composition_shape_steps [value]`<br>`report:/cell_ownership/stats/composition_unbaked_fallbacks [value]` |
| 覆盖 / 规模 / 回退 | `report:/cell_ownership/inventory/internal_eq_ports [value]`<br>`report:/cell_ownership/inventory/boundary_eq_ports [value]`<br>`report:/cell_ownership/inventory/cross_stage_live_facts [value]` |

解释与缺口：baked_hits 是事件，不能作为独立 Cell 数量；同时报告容量截断与 fallback。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/ownership-fragments/README.md](../../benchmarks/ownership-fragments/README.md)

## F4 · 直接 signal 槽与 component 生命周期

启用条件：ownership 后端。

编译期依据：稳定 component/symbol 地址；事实存活与最终 component 退休。

替代的旧工作：signal 绑定哈希和逐字段 detach 引用计数。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[ownership_composition.rs](../../engine/cell-runtime/src/ownership_composition.rs) · [ownership_slices.rs](../../engine/cell-runtime/src/ownership_slices.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/cell_ownership/stats/signal_port_detaches [value]`<br>`report:/cell_ownership/stats/signal_bindings_retired [value]` |
| 成本 / 剩余工作 | `report:/cell_ownership/stats/signal_binding_reads [value]`<br>`report:/cell_ownership/stats/component_lifetime_updates [value]`<br>`report:/cell_ownership/stats/component_signal_retire_visits [value]` |
| 覆盖 / 规模 / 回退 | `report:/cell_ownership/inventory/retained_inactive_signal_bindings [value]`<br>`report:/cell_ownership/inventory/allocated_signal_slots [value]` |

解释与缺口：将删除工作推迟到 component 退休会保留 inactive slots；必须报告峰值内存。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/signal-lifetime/README.md](../../benchmarks/signal-lifetime/README.md)

## F5 · 稳定字段 PortRef

启用条件：--stable-ports（port-keys/local-congruence 隐含）。

编译期依据：字段保存稳定端口，值通过当前 Eq 根读取。

替代的旧工作：复制 canonical 代表编号与逐字段重写。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[stable_ports.rs](../../engine/cell-runtime/src/stable_ports.rs) · [port_guard.rs](../../engine/cell-runtime/src/port_guard.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stable_ports/stats/notified_columns [value]`<br>`report:/stable_ports/stats/legacy_key_enqueues [value]` |
| 成本 / 剩余工作 | `report:/stable_ports/stats/port_reads [value]`<br>`report:/stable_ports/stats/root_resolutions [value]`<br>`report:/stable_ports/stats/root_parent_probes [value]`<br>`report:/stable_ports/stats/node_lookups [value]` |
| 覆盖 / 规模 / 回退 | `report:/stable_ports/live_stable_nodes [value]`<br>`report:/stable_ports/live_port_fields [value]` |

解释与缺口：字段重写降低不等于 key repair 消失；表示层成本转成读取时解析。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/stable-port-congruence/README.md](../../benchmarks/stable-port-congruence/README.md)
