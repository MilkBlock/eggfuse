# G · 构造子判重与等价条件

[返回总目录](README.md)。本页从 [catalog.json](catalog.json) 生成。

指标路径以 `report:` 或 `program:` 开头；`*` 表示逐规则/逐 Run 展开。
同一指标可能被多个优化使用，不能跨条目累加成总收益。

## G1 · 端口等价构造子判重与 birth hint

启用条件：--port-keys。

编译期依据：完整端口域给候选；完整 key Eq/标量校验；hint 只作正提示。

替代的旧工作：canonical-key 哈希维护。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[port_keys.rs](../../engine/cell-runtime/src/port_keys.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stable_ports/stats/birth_hint_hits [value]`<br>`report:/stats/repair_key_hash_changes [value]` |
| 成本 / 剩余工作 | `report:/stable_ports/stats/birth_hint_probes [value]`<br>`report:/stable_ports/stats/port_domain_probes [value]`<br>`report:/stable_ports/stats/key_candidates [value]`<br>`report:/stable_ports/stats/key_field_comparisons [value]` |
| 覆盖 / 规模 / 回退 | `report:/stable_ports/port_key_matching [value]`<br>`report:/stable_ports/pending_canonical_keys [value]` |

解释与缺口：birth hint 失效只能 fallback，不能证明无匹配；候选顺序决定 survivor。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/stable-port-congruence/README.md](../../benchmarks/stable-port-congruence/README.md)

## G2 · 局部 congruence 条件与 typed dispatch

启用条件：--local-congruence。

编译期依据：共享静态 site/输入 Eq 条件，运算符 identity 与 scalar guard；有容量界。

替代的旧工作：重复局部候选枚举、反身 Eq 检查与泛化字段扫描。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[ownership_conditions.rs](../../engine/cell-runtime/src/ownership_conditions.rs) · [local_port_conditions.rs](../../engine/cell-runtime/src/local_port_conditions.rs) · [ownership_queries.rs](../../engine/cell-runtime/src/ownership_queries.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/stable_ports/local_conditions/stats/completed_conditions [value]`<br>`report:/stable_ports/local_conditions/stats/cross_stage_conditions [value]` |
| 成本 / 剩余工作 | `report:/stable_ports/local_conditions/stats/condition_visits [value]`<br>`report:/stable_ports/local_conditions/stats/operator_guards [value]`<br>`report:/stable_ports/local_conditions/stats/equality_guards [value]`<br>`report:/stable_ports/local_conditions/stats/scalar_guards [value]`<br>`report:/stable_ports/local_conditions/stats/boundary_signals [value]`<br>`report:/cell_ownership/stats/domain_route_probes [value]`<br>`report:/cell_ownership/stats/domain_column_checks [value]` |
| 覆盖 / 规模 / 回退 | `report:/stable_ports/local_conditions/stats/uncovered_shapes [value]`<br>`report:/stable_ports/local_conditions/stats/open_domains [value]`<br>`report:/stable_ports/local_conditions/stats/closed_domain_probes [value]` |

解释与缺口：条件满足数不是额外独立收益；完整输入证明、存活及边界候选不能删。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/condition-bake/README.md](../../benchmarks/condition-bake/README.md)

## G3 · 跨阶段候选域分组跳过

启用条件：bake-cell-ownership --query-classes true。

编译期依据：所有允许未来 hop 的可能运算符闭包，certificate 验证。

替代的旧工作：先访问实例再拒绝的 signal/slice 遍历。

运行时仍须满足：当前存活、完整等价/标量约束、源 Run 与提交顺序仍需满足；专项限制见证据文档。

代码：[ownership_query_classes.rs](../../engine/cell-runtime/src/ownership_query_classes.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/cell_ownership/stats/domain_signal_visits [value]`<br>`report:/cell_ownership/stats/domain_slice_steps [value]` |
| 成本 / 剩余工作 | `report:/cell_ownership/stats/query_class_probes [value]`<br>`report:/cell_ownership/stats/query_class_range_jumps [value]`<br>`report:/stable_ports/stats/key_candidates [value]`<br>`report:/stable_ports/stats/key_field_comparisons [value]` |
| 覆盖 / 规模 / 回退 | `program:/ownership_fragments/query_classes/masks [count]`<br>`report:/cell_ownership/stats/domain_queries [value]`<br>`report:/cell_ownership/stats/domain_results [value]` |

解释与缺口：当前已知改进相对前一共享代码版本；没有双工作负载整进程胜出，仍慢于历史 fast。候选减少不能推出 RHS 同比例加速。

状态：已实现；性能结论仅适用于链接中的具体版本和配置。

证据：[benchmarks/query-classes/final/README.md](../../benchmarks/query-classes/final/README.md)

## G4 · union digest、显式 congruence cells 与 repair blocks（替代实验后端）

启用条件：--union-digest / --congruence-cells，以及所选 repair-cell catalog；与现行 local-congruence 区分。

编译期依据：typed scalar/Unit 范围、精确 key 与显式 Eq premises；digest 不能代替证明。

替代的旧工作：传统修复中的部分表示、匹配与 typed repair 解释。

运行时仍须满足：保留源 Run 发布和普通 dirty queue 顺序；有副作用的 merge、容器等不受支持时明确拒绝或走其既定回退。

代码：[union_digest.rs](../../engine/cell-runtime/src/union_digest.rs) · [congruence_cells.rs](../../engine/cell-runtime/src/congruence_cells.rs) · [repair_cells.rs](../../engine/cell-runtime/src/repair_cells.rs)

| 指标用途 | 精确数据路径 |
|---|---|
| 收益观察（需基线差值） | `report:/union_digest/stats/congruence_matches [value]`<br>`report:/union_digest/congruence_cells/stats/completed_across_runs [value]` |
| 成本 / 剩余工作 | `report:/union_digest/stats/shared_incidence_visits [value]`<br>`report:/union_digest/stats/full_key_checks [value]`<br>`report:/union_digest/stats/key_packets_updated [value]`<br>`report:/union_digest/congruence_cells/stats/waiter_visits [value]`<br>`report:/repair_cells/stats/steps [value]`<br>`report:/repair_cells/stats/row_copies [value]` |
| 覆盖 / 规模 / 回退 | `report:/union_digest/enabled [value]`<br>`report:/union_digest/congruence_cells/waiting_cells [value]`<br>`report:/repair_cells/enabled [value]` |

解释与缺口：这些是替代后端，不能把它们的命中和现行 shared-port 路径相加；早期显式 waiter/index 方案不等于已消除反向依赖。运行级加速未被这些计数证明。

状态：保留的可选实验；不作为当前默认路径的加速结论。

证据：[benchmarks/union-digest/UNIT.md](../../benchmarks/union-digest/UNIT.md) · [benchmarks/congruence-cells/README.md](../../benchmarks/congruence-cells/README.md) · [benchmarks/repair-cells/README.md](../../benchmarks/repair-cells/README.md)
