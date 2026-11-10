# 五次修改后的完整速度检查点

候选为 `114543ae`，包含 owned Instance、输出片段封存、共享历史/发布结果、
输入身份修复和赢家整理合并。完整分支同步后的检查点是上一轮实际计时的
`c8b099fd` 快照；它与候选之间还包含已合并的 closure 位图准备改动。
因此检查点差值是累计效果，不能归因于上述任何单项。直接前版 `c8d0584b`
另列一组，用来隔离赢家整理改动。

测量对象是 standalone Cell CPU。使用同一冻结程序和 catalog，普通 release
`sparse-cells,view-ports,storage-metrics`，不启用 allocator。核对历史二进制
哈希，预热一次、交错测量三次；计时期间未编译或修改引擎。Apple M3 Max
为交互式机器，末轮存在明显波动，全部样本保留。

| 配置 | sum-bits 推理 / ms | Raytrace 推理 / s | Raytrace 整进程 / s |
|---|---:|---:|---:|
| 历史串行 | 24.484 | 8.463 | 11.138 |
| `168285bd` inline 1 | 25.801 | 8.494 | 11.132 |
| 上次计时检查点 / 4 workers | 24.669 | 8.436 | 11.057 |
| 直接前版 / 4 workers | 24.560 | 8.465 | 11.112 |
| 当前关闭 worker | 24.866 | 8.687 | 11.452 |
| 当前 inline 1 | 25.552 | 8.557 | 11.203 |
| 当前 4 workers | 25.098 | 8.476 | 11.107 |

表中为各组三个样本的中位数。当前四线程没有建立超过历史较快配置的总体
加速。相对上次检查点，Raytrace 中位数慢 0.46%，三个配对都较慢；配对比
中位数 1.0092，bootstrap 区间 [1.0030, 1.0970]。直接前版对照的中位数
慢 0.12%，配对比 1.0044，区间 [1.0001, 1.1062]。不能宣布速度保持或
把末轮慢样本删除。sum-bits 相对直接前版中位数慢 2.19%，区间跨 1。

当前 Raytrace 四线程比同版关闭 worker 快，中位数比为 0.9756；相对同版
inline 1 为 0.9904，但后者配对区间跨 1。较慢的本版串行不是唯一验收基线。
三次小样本区间只描述本轮波动，不是跨机器保证。本轮没有通过总体加速门槛。

## 实际接管与剩余机会

完整 Raytrace 相同配置的赢家搬运从 477,068 降到 44,652 条，少 432,416；
容器批次从 24,564 降到 19,703，少 4,861。它们是已消除的工作，不能继续
当成速度预测。新版比较器计数也不能与旧版漏计第二次排序的计数直接相减。

累计共享结果路径有 55,771 个实例，覆盖 144,421 个历史槽；原历史捕获读取
和写入均从 159,828 降至 15,407。同时新增 56,056 次资格检查、55,771 次
查询导出读取及同量写入、55,771 次发布寻址，初始化槽从 1,672,342 增至
1,695,234。不能只拿捕获下降评价净成本，覆盖量也不另计收益。

当前 worker 执行 1,076,546 个 Entry、1,097,825 次 point read。31,372 个
Cell task 具有多个入口，其中 18,524 个跨规则；小 Run 的 31,034 个入口
没有建立归组索引。上述数值没有证明重复读取量，尤其同 Cell 的入口可能
使用不同投影。下一项应诊断同 Cell/Run 中实际相同的读取与共同前缀，再用
原查询指令和静态槽来源证明可共用的部分；各入口的 watermark、delta 归属、
拒绝条件和输出顺序仍独立。

冻结计时程序没有 state_plan，故本轮不能测得 `tracks_slots()` 对联合结果
路径的阻挡规模。第 4 项需在已有 selected v2 / materialized 对照上另查；
不能根据本轮历史覆盖量声称父帧继承已经接通共享发布。

## 语义与复现

全部 56 个完整进程（含预热）保持各自 workload 的精确最终图及有序 Run
签名：sum-bits 1,428 个 Run，Raytrace 16,883 个 Run。短例的独立 sum-bits
语义验收见 [results.json](results.json)。Raytrace 这里是原 runtime 回归
对照，没有冒充独立 native 证明。

原始精简计时见 [sum-samples.json](sum-samples.json)、
[ray-samples.json](ray-samples.json)，汇总、SHA256、配对区间和完整 worker
计数见 [timing.json](timing.json)。构建、完整导出、原始大报告留在忽略的 out。

```sh
python3 benchmarks/cell-winner-fold/timing.py prepare OUT
python3 benchmarks/cell-query-workers/raytrace_measure.py measure OUT/sum-manifest.json OUT/sum-timing --repeat 3 --warmups 1 --timeout 30
python3 benchmarks/cell-query-workers/raytrace_measure.py measure OUT/ray-manifest.json OUT/ray-timing --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/cell-winner-fold/timing.py collect OUT
```

`prepare` 核对已有历史和本次短例中的二进制哈希；重建其它版本时需明确更新
相应基线 provenance，不能沿用旧哈希或覆盖旧样本。
