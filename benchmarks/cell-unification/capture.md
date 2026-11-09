# Cell 输出 capture 统一

对象为 standalone Cell CPU，冻结基线为 `f995cea7`。本轮接续 [最终 Entry 发布重写](publication.md)，不是 native egglog 内核改动，也没有完成整体 Cell 统一或多线程验收。

上一轮已经消除了 Entry Pending，但 capture 仍分成单输出 receipt 哈希登记、多输出 FragmentPublication 包，以及未知边界 key 三种存储。发布时前两种又汇合到同一 Entry。sum-bits 的 direct-publication 哈希探测为 10,438 次，普通边界记录/回读各 3,713 次；部分工作只是维持这两种表示之间的转换。

本轮从 `cell::Definition` 派生一份共享 Output 描述，保留 effect 位置、表和已证明的 receipt 来源。capture、owner 准入、发布与 Bake 的形状统计读取同一描述，删除平行的 anchor tuple 和 fragment table 数组。操作本身仍是字段及效果的权威来源；没有另外维护一份事实图，函数读取也不会仅凭这份描述获得生产者权限。

所有已证明 permanent 且由 Entry 接管的 Cell 输出，包括单输出，共用完成 Cell 的输出槽区间。实际存储的是执行返回的 Dependency，可以指向其他物理 Cell 的已有节点。普通 capture 与单写 specialization 调用同一 receipt sink。独立 FragmentPublication 类型、包数组及其 retain/合并过程删除。没有为消费者建立反向订阅列表。

发布顺序直接取 `(完成 Cell 槽位, 源 effect 位置)`，不再保存每个输出的全局 ordinal，也不再给输出片段存一份 ordinal 基址。完成 Cell 按源执行顺序追加；其中输出保持源 effect 顺序，因而与原 ordinal 的比较等价。部分 scope 未发布完时，完成 Cell 槽位不会重用，新 Run 只追加；全部排空后，才释放完成状态和输出槽。这是源顺序坐标，不是实际返回结果的物理地址。

未知边界及未由 Entry 接管的输出仍走 key/receipt 归一化。已覆盖输出直接按 Cell 顺序进入最终 Entry 裁决；同一批次只保存最终胜者，后续候选不 materialize continuation。收据 forwarding、visibility、删除重建、Run 边界与延迟发布检查继续执行。

| sum-bits 工作 | 基线 → 候选 |
|---|---:|
| 独立 fragment 包 | 1,447 → 0 |
| direct-publication 哈希探测 | 10,438 → 7,573 |
| 普通边界记录 / 回读 | 3,713 / 3,713 → 1,687 / 1,687 |
| 最终 Entry 候选检查 / 槽寻址 | 7,134 / 7,134 → 7,740 / 7,740 |
| 失败候选跳过 | 1,221 → 1,827 |
| receipt 尝试 / 成功 | 9,693 / 9,635 → 10,299 / 10,241 |
| packetless Entry 已排队复用检查 | 271 → 366 |
| 最终 Entry 写 / anchor publications | 5,913 / 8,414 → 不变 |
| 多输出 receipt 子集 | 3,421 → 3,421 |
| 新观测：Cell 输出区间 / 槽位 | 4,079 / 6,053 |
| 新观测：receipt 保存 / 槽读取 / 检查 / 交付尝试 | 6,053 / 6,053 / 6,053 / 6,053 |
| 新观测：待发布槽位峰值 | 587 |

单输出接管了 2,632 次 receipt 保存，替代 2,026 条合并后的普通边界记录，差额正是新增的 606 次最终候选检查。取消早期哈希合并并没有消除重复候选本身。哈希减少量还包含空 fallback 哈希表不再遍历 forwarding 的节省。不能把这些不同操作简单相加成统一的“收益次数”。

`fragment_receipts/deliveries` 继续观察多输出子集；它们包含在共同的 `cell_output_*` 中，不可重复计费。`cell_output_slots` 计初始化的槽位，receipt 保存另计实际写入；部分 scope 可以反复读取同一区间。交付尝试和 continuation 发布都不是 committed graph mutations。

第一版仍携带全局 ordinal，执行期申请量增加 4,384 bytes。改用 Cell/内部 effect 顺序并删除重复元数据后，最终 setup alloc 少 721 次、realloc 少 43 次、申请量少 55,968 bytes；执行期 alloc 不变、realloc 多 1 次、申请量少 39,136 bytes。新增输出槽 arena 的一次扩容明确保留为成本；采集器只为当前固定案例接受这一增量，并要求其他执行期请求不增加、setup 与 execute 合计的分配次数和申请量下降，不放宽其他重写的验收条件。

| 普通构建，7 组交错配对独立进程、1 次预热 | 基线 → 候选 |
|---|---:|
| 推理中位数 | 25.393083 → 24.703458 ms |
| 整进程中位数 | 134.981875 → 132.326083 ms |
| 峰值 RSS 中位数 | 178,749,440 → 178,749,440 bytes |

推理配对比率中位数 0.99310，bootstrap 95% 区间 [0.93155, 1.00550]；整进程配对比率中位数 0.99652，区间 [0.96868, 1.02290]。两者都跨过持平，尚无稳定加速结论；不能用各组中位数之比替代配对证据。计时期间没有并行构建，没有新增 Raytrace 或历史最快配置测试。

218 项编译器测试、52 项 runtime 全特性测试、33 项最小特性测试通过。新增单输出重复/union 用例；五个 Entry 测试进一步比较顺序 RHS、write 和 resume-root 摘要，确认最后生产者保持一致，而不仅检查最终事实集合。已有跨 scope 用例在没有全局审计栅栏的配置中再次通过。三个不足一秒的冻结 runtime fixture 保持逐阶段 state、bindings 和顺序写入摘要。

22 个重编译组件一致；sum-bits 语义脚本 pass，1,428 个 Run 的工作字段、最终 state 和顺序 RHS/write/resume 摘要一致。sum-bits 诊断构建未启用 audit-stages，确实执行新的输出槽路径。统一目录共 303 个指标：7 个新槽位成本指标，10 个明确解释的工作变化，其余工作指标保持原值或原状态。

结果与复现入口见 [capture-results.json](capture-results.json)、[capture-timing-spec.json](capture-timing-spec.json)、[coverage.json](coverage.json)。effect 临时收据数组、后续确实需要的 Results/history、未知边界归一化和 legacy owner 仍待统一。输出槽接管不等于 capture、RHS 执行和 Bake 的所有路径已经统一。
