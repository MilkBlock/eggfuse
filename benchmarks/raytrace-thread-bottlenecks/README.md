# Raytrace 多线程堵点：2026-11-10

当前多线程的主要限制是：查询匹配、RHS 和发布仍由主线程执行，worker
只接走部分 congruence 条件读取。4 worker 在采样窗口中约 98% 的采样点
处于等待工作状态。此次没有建立稳定的线程扩展收益。

测量对象是 **standalone Cell CPU**，不是 native egglog。源版本为
`f4fd21cb`，运行时最近的实现变更为 `14e112c7`。使用同一个普通 release
二进制，features 为 `sparse-cells,view-ports,storage-metrics`，没有 allocator、
有序审计或 overlap-probe 插桩。Apple M3 Max，16 logical CPU。

旧的临时 Raytrace artifact 已不存在。本次从仓库的 named Raytrace 和冻结
64-block catalog 重新编译，再执行 `bake-cell-ownership --query-classes true`。
所有配置共用这一份输入；不把历史不同版本的耗时作为本次基线。
文件哈希、机器和输入来源见 [provenance.json](results/provenance.json)。

## 实际耗时与验证

每配置一次预热，之后三轮交错运行独立进程。采样剖析另外执行，不进入计时。
worker 数不含主协调线程；普通串行配置没有线程池。

| 配置 | 推理中位数 | 完整进程中位数 | 相同轮次推理比值的中位数，串行=1 |
| --- | ---: | ---: | ---: |
| local serial | 9.423 s | 12.163 s | 1.0000 |
| serial + scoped queues | 9.520 s | 12.272 s | 0.9990 |
| 2 worker + overlap | 8.752 s | 11.390 s | 0.9641 |
| 4 worker + overlap | 9.119 s | 11.822 s | 1.0125 |

三轮存在明显波动，不能仅用两组独立中位数相除宣称加速。2 worker 的逐轮
推理比值为 0.9641、1.0150、0.9288；4 worker 为 1.0125、1.0332、0.9677。
2 worker 有改善迹象，4 worker 没有稳定收益。这是定位堵点的小样本实验。

全部 16 次计时/预热进程和另外一次 profile 的最终 `state.json` 哈希、完整
有序 Run 签名一致，共 16,883 个 Run。签名包含 ruleset、path、iterations、
epoch、logical_matches、executed_bindings 和 changed。该验证说明这些配置
与串行 Cell 的结果和调度一致，不是独立的 native egglog 语义证明；logical
matches 也不代表已提交 mutation。

原始数据：[samples.json](results/samples.json)；聚合数据及配对区间：
[summary.json](results/summary.json)。

## 堵点在哪里

### 1. 主线程仍承担绝大多数工作

| 源 Run 阶段 | 串行中位数 | 4 worker 中位数 |
| --- | ---: | ---: |
| 查询匹配 search | 4.420 s | 4.096 s |
| RHS | 2.845 s | 2.650 s |
| 查询索引更新 query_update | 1.415 s | 1.354 s |
| repair / completion | 0.723 s | 1.022 s |
| delivery_gc | 0.016 s | 0.016 s |

串行的 search、RHS、query_update 合计约占推理的 92%。它们未被此次 worker
路径并行化；表中这些阶段的较小绝对耗时也不能算作并行收益。对当前约 7.7%
的 repair 段，即使把整个阶段都免费消除，保持其他工作不变，端到端上限也只
约 1.08 倍；真正移交给 worker 的只是其中一部分。

4 worker 三次进程的 `(user + system CPU seconds) / wall seconds` 均约
1.04；串行约 1.00，2 worker 约 1.01–1.02。这是全进程平均核心使用量，
包含加载和输出，不是瞬时 CPU 利用率。

在首次源 Run 开始后，使用 macOS `sample` 采样 10 秒、间隔 5 ms。
每线程取得 1,675 个采样点；主线程其中 1,565 个在 `execute_until` 内。
主要推理栈如下，**inclusive 数量相互重叠，不能相加**：

| 主线程推理栈 | 采样数 | 占推理采样 |
| --- | ---: | ---: |
| `Executor::matches` | 642 | 41.0% |
| `lookup_port_key` | 311 | 19.9% |
| `owned_candidates`，包含于上层调用 | 187 | 11.9% |
| `publish_finished_tables` | 255 | 16.3% |
| `repair_selected` | 188 | 12.0% |
| `complete_port_read_batch` | 144 | 9.2% |
| `overlap_completion_tasks` | 98 | 6.3% |
| `Once::wait`，等待有序结果槽 | 17 | 1.1% |

四个 worker 的条件变量等待采样分别为 1,640、1,648、1,652、1,655，占各自
采样的 97.9%–98.8%。窗口覆盖大部分推理及少量报告生成；这表示栈驻留，
不能把百分比当作精确 CPU 时间。进度日志和采样本身会扰动诊断进程。

主线程等待结果确实存在，但这次的主要限制是 worker 没有持续可做的重活。
栈证据：[profile.json](results/profile.json)、[完整 sample 文本](results/stacks.txt)。

### 2. 并行条件读取带来额外准备、overlay 和废弃工作

4 worker 每次运行的完成批次计数：

| 工作 | 次数 |
| --- | ---: |
| completion 批次 | 11,219 |
| 预备并执行读取的任务 | 173,196 |
| 用于有序完成的任务 | 160,933 |
| 未用于提交的已读任务 | 12,263（7.08%） |
| 读集排序/定位比较 | 2,652,680 |
| 批次 lane spawn | 44,540 |
| overlay 写入 | 878,521 |
| overlay 合并条目 | 643,080 |
| preparation scratch + input/result buffer 分配计数 | 52,887 |

最后一行是代码记录的三类 buffer 分配事件，不是 allocator 全量统计；累计
请求容量 254,490,208 bytes，不代表同时存活内存，也不包含所有线程池、overlay
或 allocator 内部开销。普通构建没有全量 allocation 数据，缺测不记为零。

与串行相比，4 worker 还多出 334,563 次 port read、811,503 次 node lookup、
151,214 个 key candidate 和 12,263 个 row view。总查询调用仍为 4,195,491，
逻辑写入/union 数量相同。当前路径没有消除主线程的主要查询工作。

[批次准备](../../engine/cell-runtime/src/completion_read_batches.rs)先在协调线程
解码事实、枚举候选、构造并排序 read set，才交给 worker 做条件检查。
[union 检查](../../engine/cell-runtime/src/completion_read_batches.rs)会在后续任务
依赖发生变化时缩短有效前缀；1,219 次 union 缩短了前缀。失效后 worker 仍可能
继续完成读取，epoch 结束还需 join、收集结果和合并 overlay。不能把全部
12,263 个未提交任务直接归因于 union；该总计还包含有序队列选择导致的停止。

### 3. 任务太小，增加线程还会改变派发门槛

独立的 ordinary guard 路径默认 `grain=32`，派发门槛是 `workers × grain`：
2 worker 为 64，4 worker 为 128。本次普通 guard 批次的实际派发因此从
282 次降到 5 次。它与上面的 11,219 个 completion 批次是两条不同的路径。
这次对比使用现有默认参数，不能理解为只改变核心数、完全不改变调度策略。

4 worker 首个计时进程实际完成的 batch 任务分布为
`[110758, 35392, 20604, 6442]`，其他轮次分布不同。源码以固定 stride 的 lane
执行小任务，lane 与 worker 的实际映射由 Rayon 决定；任务数不等于每个任务
的耗时。存在明显分布不均，但整体 worker 等待比例表明，仅重新均衡这些小任务
无法解决主线程的大部分工作。

## 后续优先级

1. 从 `matches`、`lookup_port_key / owned_candidates` 和
   `publish_finished_tables` 下手：让编译好的 Cell 连接直接承担候选定位、
   匹配接续与发布，并把足够大的只读匹配片段纳入 worker 执行范围。
2. 在扩大批次前，减少协调线程构造候选/read set、重复 buffer 和 overlay
   合并的工作；保留 union 两侧依赖与有序可见性的校验。
3. 再优化失效取消和任务粒度。当前没有准备、等待、overlay 各自的精确墙钟
   计时，不能把 repair 增加的约 0.30 秒全部记到某一个计数器上。

此次只添加诊断脚本与结果，未改执行引擎，也未测 pure-epoch 或
`--scoped-execution` 的其他组合。

## 复现

从仓库根目录运行，使用新的输出目录。编译与计时分开完成：

```sh
CARGO_TARGET_DIR=target/raytrace-diagnosis cargo build --release --locked -p eggfuse-cell-compiler
target/raytrace-diagnosis/release/eggfuse-cell-compiler compile --case raytrace --output out/raytrace-thread-replay/input
target/raytrace-diagnosis/release/eggfuse-cell-compiler bake-cell-ownership --program out/raytrace-thread-replay/input/program.json --query-classes true --output out/raytrace-thread-replay/query-classes
CARGO_TARGET_DIR=target/raytrace-diagnosis cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics
python3 benchmarks/raytrace-thread-bottlenecks/prepare.py target/raytrace-diagnosis/release/eggfuse-cell-runtime out/raytrace-thread-replay/query-classes/program.json target/raytrace-diagnosis/release/eggfuse-cell-compiler out/raytrace-thread-replay
python3 benchmarks/witness-prefix/measure.py out/raytrace-thread-replay/manifest.json out/raytrace-thread-replay/timing --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/raytrace-thread-bottlenecks/profile.py out/raytrace-thread-replay/manifest.json out/raytrace-thread-replay/timing/samples.json out/raytrace-thread-replay/profile --duration 10
python3 benchmarks/raytrace-thread-bottlenecks/collect.py out/raytrace-thread-replay out/raytrace-thread-replay/evidence
```

原次编译使用现成 debug compiler；实际编译器和 runtime 哈希均保存在 provenance，
重新构建的二进制可能不同。复现应比较同一轮新构建的各配置，保留新的哈希。
profile 脚本需要 macOS `/usr/bin/sample`。计时进程禁用进度日志，独立 profile
进程启用日志定位首次 Run，并再次核对最终图和 Run 签名。collector 校验 sample
树的父子计数和完整文件哈希，避免将递归栈重复计为额外时间。
