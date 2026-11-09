# Cell CPU 优化分类与度量目录

这份目录按**被替代的运行时工作**分类，不按实验出现的先后顺序分类。覆盖当前分支的 9 类、28 组优化；一组可以包含紧密耦合的几个实现，不把每个微优化算成独立 feature。

适用对象是 **standalone Cell CPU**。native egglog 在前端/Bake 中作为工具使用，不能把本目录的运行时结果描述为 native egglog 加速。历史实验的报告仅证明其冻结版本和配置，不能自动继承为当前代码的性能结论。

| 类别 | 优化对象 | 首要收益观察 | 必须同时付账 |
|---|---|---|---|
| [A 前端与 marker](A-frontend.md) | 结构 key、native Bake、marker、Recipe lowering | 静态计划规模、实际 marker 使用 | 离线编译时间/内存、产物体积、加载成本；部分专项指标仍缺失 |
| [B 匹配](B-matching.md) | register join、Free Join、Sieve、范围、邻居/context/view | 实际 lookup、残余候选、重复解码下降 | 投影构建/维护、候选物化、guard、cache 维护 |
| [C 跨阶段复用](C-continuations.md) | 完整 Spine、RHS/query receipt、已有见证、前缀接续 | 真正免除的读取、RHS frame、匹配前缀 | history/route/context 读取、存活/key 校验、失效回退 |
| [D RHS](D-rhs.md) | known results、静态别名、单写、稀疏 frame、merge program | 被消除的构造与 frame、实际分配下降 | 结果验证、merge 指令、剩余构造查询 |
| [E 发布](E-publication.md) | 变更批次、共享 Entry、publication ownership、片段发布 | 参数复制、重复索引与临时哈希下降 | 槽位访问、forwarding、最后写入者选择、延迟发布状态 |
| [F 端口与生命周期](F-ports.md) | repair ports、ownership、slices、composition、signal 槽、稳定字段 | 订阅/解绑/字段重写下降 | 端口读取、静态 slice 分派、边界维护、滞留空间 |
| [G 判重与等价](G-congruence.md) | port keys、局部 congruence、typed dispatch、跨阶段分组及替代后端 | 候选访问、key 重建与哈希下降 | Eq/标量检查、边界搜索、分组跳转、静态代码体积 |
| [H 调度与并行](H-completion.md) | scope、port influence、pure epoch、并行 guard/batch/overlap、大 Cell 完成 | 独立进展、有效完成任务、真实线程扩展性 | influence 证明、分派、snapshot、失效与废弃工作、有序提交 |
| [I Bake admission](I-admission.md) | 模板选择、迭代 catalog、实际工作 credit | 同源执行真正减少的工作 | 新机制全部维护/分配/编译成本，以及最终整进程时间 |

每组条目都有编译期依据、启用条件、替代的旧工作、代码入口、精确数据路径、当前约束和证据链接。完整数据源是 [catalog.json](catalog.json)，分类页由 [catalog.py](catalog.py) 生成。

## 统一读数规则

每项优化分别看四层，不能用前一层替代后一层：

1. **覆盖**：静态模板/运算符范围、实际 eligible/attempts、fallback。模板多不代表实际执行多；`composition_baked_hits` 等是事件数，不是独立 Cell 数。
2. **净工作**：同输入、同语义的基线与候选之间，旧工作减少多少、新工作增加多少。`key_reads_avoided` 可能包含原本的 PointPorts 命中，必须再看 `key_lookup_calls`。同一个动作的总量/子集不能重复收费。
3. **资源**：运行时分配次数/字节、setup 分配、静态产物、峰值 RSS、滞留 inactive slots。压缩、直接寻址、分组和提前保留状态会互相交换成本。
4. **实际时间**：推理与整进程时间分别报告，拆开 load/setup/search/RHS/repair/query update/report/export。报告生成变快不能称为 RHS 变快；并行工作量增加不能称为线程加速。

公共指标来自 `report.json` 的 `inference_seconds`、`load_seconds`、`setup_seconds`、`report_seconds`、`export_seconds`、`steps[*].phases`、`allocations`、`setup_allocations` 和峰值 RSS。**整进程 wall time 在测量 harness 的 `samples.json` 中，不能把这些 phase 相加后冒充实测 wall time。** allocator 指标需要 `allocation-metrics`，RSS 需要相应构建支持；正常计时二进制和诊断二进制必须区分。

正确性门槛始终独立：最终状态、源 Run 调度、按序 RHS/写入/resume，以及删除、重建、可见性和 union 后的语义一致。逻辑 rule matches、候选数和执行过的 binding 均不等于 committed mutations。针对发生改变的路径，还要证明测试确实进入了该路径；例如 `audit_receipts` 会禁用片段发布快路。

## 本轮三项工作的位置

| 工作 | 目录条目 | 当前完成范围 |
|---|---|---|
| 已有见证直达＋匹配前缀接续 | C3、C4 | 按实际 query/effect 来源读取已保存的 receipt；分派前保留本次匹配需要的历史引用；非空完整 key 前缀可接续，残余匹配保持完整 |
| 片段内部发布 | E3 | 多 anchor、permanent、Entry-owned 的 RHS 片段；在现有 Entry 槽位选择最后发布者，未知边界回退 |
| 扩大并行完成范围 | H4 | 超过局部条件容量的形状可用完整端口候选域进入读取批次；有序提交和 union 失效仍保留 |

这三项的初次代码/验证记录在 [witness-prefix 实验目录](../../benchmarks/witness-prefix/README.md)。该版本 C3/C4 在 sum-bits、Raytrace 中实际命中为 0，未减少查询；E3 已触发，H4 在真实并行诊断中接管了额外任务。合测没有通过双工作负载推理收益门槛，不能给前两条路径记收益。

后续 [实际来源与无效分派清理](../../benchmarks/witness-sources/README.md) 只做短样例诊断：sum-bits 的 Spine context/route probes 从各 90 降到各 12，31 次失败 donor 尝试归零；实际查询仍为 19,222，捕获和分配未增加。真实 receipt 直达由专项回归覆盖，当前短样例仍是零命中；没有新的整体加速结论或 Raytrace 计时。前一轮跨阶段分组另有可追溯结果：[query-classes 最终报告](../../benchmarks/query-classes/final/README.md)；不同轮次和基线不能混用。

## 读取现有报告，不触发新实测

```sh
python3 docs/optimization-catalog/catalog.py check
python3 docs/optimization-catalog/catalog.py extract \
  --report out/run/report.json \
  --program out/compiled/program.json \
  --output out/run/optimization-metrics.json
```

提取器校验 report/program 的 digest，按每项优化组织观察值，保留输入文件哈希。`disabled`、`missing_source`、`missing_counter` 和真实的数值 `0` 分开表示；不会从缺失数据制造收益。`sum` 只求和明确列出的逐规则或逐 Run 数值；`count` 表示指定容器的直接元素数，不是递归节点总数。该工具不运行 workload、不计时，也不自动宣称加速。

修改分类或指标时编辑 `catalog.json`，然后执行：

```sh
python3 docs/optimization-catalog/catalog.py render
python3 docs/optimization-catalog/catalog.py check
```

## 当前度量缺口

- 前端/Bake 的分阶段编译时间、峰值内存、前后 IR 大小还没有统一字段。已有产物规模只是覆盖/成本代理。
- 部分旧优化没有独立的启停对照与净耗时归因，只能结合专项实验和共同 counters。不能把总 lookup 下降全部分配给其中一项。
- `known_stats` 原来存在于 Graph 内但未统一导出，本轮补入 `report.known_results`。旧报告缺失该字段，不补零。
- 目前没有完整的 wall-clock repair stall 分解；`bypassed_tasks`、`while_pending` 和 worker 分布都不能替代它。
- Bake 的工作 credit 是等权操作差值，不是 CPU 周期模型；最终 admission 仍需同源语义验证和整进程/推理实测。失败或被撤回的候选保留在证据目录，不计为已获得的收益。
