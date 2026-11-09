# Cell 完成状态与最终 Entry 发布

对象为 standalone Cell CPU，基线 `ec6586d4`。不是 native egglog 内核改动，也不是整套 Cell 统一工作的最终验收。

上一轮 sum-bits 已有 3,421 个 fragment receipt，但发布仍进行了 5,505 次 Pending 写、4,533 次 Pending 读。同一 Entry 可以收到普通边界输出和 fragment 输出；旧实现先把候选放入 Pending，以 ordinal 选择最后生产者，再转为 Live。直接删除 Pending 会丢失胜者裁决，不能只根据固定槽位跳过它。

本轮让一个源 Cell 持有一个 Completion。完成状态从 Started 移动为共享 PublishedBase，删除平行的 published_bases 数组；Live Cursor 在第一次有效输出时移动一次，不再复制后同时保留两份状态。后续输出复用同一 base，包括跨 scope 的延迟发布。

在合法发布边界，已归一化的普通输出挂入源 Cell 自身的短输出链；链内按源 RHS ordinal 倒序排列。fragment 使用共享 anchor_ops 的静态位置。运行时倒序访问源 Cell，再合并它的普通输出与 fragment 端口，因此同一目标 Entry 的最终胜者先到达。Entry 每个发布批次只写一次最终 Published，后续候选跳过且不 materialize continuation。旧 Pending 枚举、staged-id 队列和 stage/pop/finish 接口全部删除。

这条短链保存的是本发布边界内、尚待投递的 Cell 输出，不是消费者订阅表；投递后清空并复用存储。共享模板内部没有新增 producer→consumer 反向列表。但它仍是新增的运行时维护，必须与被删除的 Pending 一起核算。

源 Run/effect 顺序、receipt forwarding、visibility、删除重建、delta ownership 和发布边界都保留。Entry 的批次代号只仲裁当前边界，不把上一边界的 ordinal 当成永久胜者。未就绪表的 fragment receipt 留在原 Cell；已经提升的 Completion 继续存活，后续边界直接复用。未知边界仍需 key 归一化与哈希合并，fragment receipt 数组也尚未消除。

| 短 sum-bits 工作 | 基线 → 候选 |
|---|---:|
| Pending 写 / 读 | 5,505 / 4,533 → 0 / 0 |
| 旧 fragment 槽探测 / 替换 / 较旧候选跳过 | 5,754 / 972 / 249 → 0 / 0 / 0 |
| 最终 Entry 写 | 5,913 → 5,913 |
| 发布槽寻址 | 7,134 → 7,134 |
| fragment receipts / deliveries | 3,421 / 3,421 → 不变 |
| direct-publication 哈希探测 | 10,438 → 10,438 |
| 最终 anchor publications | 8,414 → 8,414 |
| 新观测：候选检查 / 失败候选跳过 | 7,134 / 1,221 |
| 新观测：普通边界输出记录 / 回读 | 3,713 / 3,713 |
| 新观测：边界输出链插入比较 / Cell 访问 | 1,262 / 7,153 |
| 新观测：Cursor 移动提升 | 1,752 |

新计数在基线中是 missing_counter，不人为记作零。候选检查与槽寻址观察同一次尝试，不能相加成两份收益。链插入比较只计链构造时的比较；fragment 合并的循环仍发生，由输出和 Cell 访问规模共同约束。fragment deliveries 是交付尝试，anchor publications 是最终 continuation 发布，都不是图的 committed mutation 数。

第一版使用 `Option<usize>` 保存两处可空链索引，执行期申请量比基线多 3,872 bytes。改为 `Option<NonZeroUsize>` 后，最终 setup 分配不变；执行期 alloc 少 1 次，realloc 少 9 次，申请量少 16,544 bytes，净存活增长少 8,192 bytes。诊断构建执行期峰值 live requested bytes 仍多约 4 KiB，不能用总申请量减少代替峰值内存结论。

| 普通构建，7 组交错配对进程、1 次预热 | 基线 → 候选 |
|---|---:|
| 推理中位数 | 25.963125 → 24.891750 ms |
| 整进程中位数 | 137.021959 → 131.564042 ms |
| 峰值 RSS 中位数 | 178,798,592 → 178,749,440 bytes |

推理配对比率中位数 0.98684，bootstrap 95% 区间 [0.95565, 1.00593]；整进程配对比率中位数 0.99145，区间 [0.95917, 0.99167]。样本中各自中位数的比率与配对比率相差较大，不能只引用前者宣称约 4% 加速。推理区间跨过持平，稳定推理收益尚未证明。没有新增 Raytrace 或历史最快配置测试，也没有多线程收益结论。

217 项编译器测试、52 项 runtime 全特性测试和 33 项最小特性测试通过。新增测试让同一 Cell 的 B fragment 先发布并消费，A fragment 等待 repair 后发布；另外用没有全局审计栅栏的配置单独运行同一测试，确认确实留下未完成的 scope。既有测试覆盖重复输出、union forwarding、隐藏、删除重建、可变函数与迟到消费。

22 个重编译组件一致；sum-bits 语义脚本 pass，1,428 个 Run 的工作字段，以及最终 state、顺序 RHS/write/resume 摘要一致。诊断 sum-bits 不启用 audit-stages，因此 fragment 快路实际开启；三个不足一秒的冻结 runtime fixture 另行核对逐阶段快照、bindings 与写入顺序。指标目录新增 7 个成本计数，并补入原已输出的 3 个旧 fragment 计数；其余工作指标严格保持。

结果、命令与完整未完成清单见 [publication-results.json](publication-results.json)、[publication-timing-spec.json](publication-timing-spec.json) 和 [coverage.json](coverage.json)。下一步仍需统一 capture/result 存储与边界归一化，不能因为 Pending 归零就把整个 RHS 发布类别标为完成。
