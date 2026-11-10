# 完整 Raytrace：Cell 查询 worker 对照

测量 13cfd235 的 standalone Cell CPU，不是 native egglog。Apple M3 Max，16 logical CPU；普通 release features `sparse-cells,view-ports,storage-metrics`。所有配置共用冻结的 Raytrace artifact，旧二进制也在本轮重新运行。每配置 1 次预热、3 轮交错独立进程，共 24 次完整执行；进程耗时包括加载、输出和退出。

| 配置 | 推理中位数 | 整进程中位数 |
|---|---:|---:|
| 旧基线 efc06d49 | 10.629 s | 13.436 s |
| 13cfd235，关闭 workers | 11.299 s | 14.225 s |
| 同版 inline，grain 64 | 10.637 s | 13.500 s |
| 2 worker，grain 64 | 10.478 s | 13.375 s |
| 4 worker，grain 64 | 10.418 s | 13.299 s |
| 4 worker，grain 16 | 10.491 s | 13.363 s |

4 worker / grain 64 相对旧基线的逐轮推理比中位数为 0.995990，3 轮 bootstrap 区间 [0.960945, 1.006649]，没有建立稳定收益。相对本版关闭 workers 为 0.922032，但关闭路径本身本轮比旧基线慢；不能只选这个对照宣称成功。相对同 host inline 为 0.975639，亦不是完整架构优于旧基线的证据。交互式机器的系统负载没有隔离，小样本区间不代表跨机器保证。

全部执行的最终图和 16,883 个有序 Run 签名精确一致；比较 fields 包含 epoch、规则集、路径、迭代、logical_matches、executed_bindings、changed。该结果是 Cell 配置间一致性检查，不是 native Raytrace 语义证明。

## 分配方式与成本

当前调度是 Entry 数量分块，Rayon 动态窃取；没有根据 Cell 查询权重分配。chunk 内顺序执行，每条规则/批次都等完成。Cell 模板只用于证明能否进入函数读取路径，尚未承担跨规则任务组织。

默认 grain 64：26,262 个 Entry、28,016 次函数读取、61 个 batch、441 个 chunk。全程 key 查询 4,195,491，worker 仅承担其中 0.668%。主线程先做 1,809,576 次准入检查、1,305,155 次 seed 遍历；累计 Entry 缓冲容量 335,456,192 bytes（不是峰值或 allocator 全量分配）。因此主要结构性问题是准备层破坏 Cell 的分组、覆盖过小，单独调整负载权重不能消除这些工作。

grain 16 只把 Entry 扩大到 28,131、读取到 30,174，却把 chunk 增到 1,820、帧分配从 870 增到 3,595。各 worker 的 Entry 数见 summary；数目不是执行权重或 CPU 时间。整进程平均使用约一个核心，也不能据此推算单个查询片段的瞬时利用率。

下一步依据同一 Cell 的静态 Entry 表，在当前 Run 的只读边界内合并实例任务；共享输入和临时帧，保留未激活 Entry、delta、当前 mutable value、存活状态及原 RHS 顺序。后续改造必须与这里的 13cfd235 当前分支对照。

## 复现与证据

[summary.json](raytrace-results/summary.json)、[samples.json](raytrace-results/samples.json)、[provenance.json](raytrace-results/provenance.json)。此提交只保存测量脚本和证据，不改变引擎。

```sh
python3 benchmarks/cell-query-workers/raytrace_measure.py prepare OLD_RUNTIME CURRENT_RUNTIME RAYTRACE_PROGRAM OUTPUT
python3 benchmarks/cell-query-workers/raytrace_measure.py measure OUTPUT/manifest.json OUTPUT/timing --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/cell-query-workers/raytrace_measure.py collect OUTPUT EVIDENCE
```
