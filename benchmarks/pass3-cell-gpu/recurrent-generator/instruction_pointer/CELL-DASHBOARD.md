# Cell Foundation Model 本地实验看板

在这台 Mac 的终端运行以下命令。

```bash
cell-dashboard
```

默认地址为 [127.0.0.1:5092](http://127.0.0.1:5092)。若看板正在运行，命令会打开浏览器。首次启动会同时开启本地网页、历史导入和检查点监听。关闭启动它的前台命令即可停止这一组服务。研究分支也提供同名可执行脚本。

```bash
# 从研究分支仓库根目录启动，或只同步已有记录
cd benchmarks/pass3-cell-gpu/recurrent-generator/instruction_pointer
./cell-dashboard
./cell-dashboard sync
```

看板使用 SwanLab 0.10.6 的本地模式和官方 Dashboard 扩展。训练进程只写普通 JSONL，导入器使用 `init`、`run.log(metrics, step=...)` 和 `finish`。切换可视化服务只需替换写入端。SwanLab 将此离线界面列为基础维护功能。[SwanLab 离线看板文档](https://docs.swanlab.cn/guide_cloud/offline-board.html)

## 怎样看数据

| 实验名称 | 横轴 | 内容 |
|---|---|---|
| `fit` | 单个模型累计完整 Token 曝光 | 训练 CE、LR、优化步数、Token/s、时间、实际状态和具名目标数、总参数与前后向连通参数 |
| `live` | 训练进程实际累计曝光 | CPU 训练采样点的裁剪前梯度范数、采样步前向、反向和优化器的主机耗时、累计计数 |
| `probe` | 检查点曝光 | 在固定、离线核验的内部验证目标上，按目标数加权的完整 Token CE、各父数及 Higher 的自由生成命中率 |
| `native` | 付费请求预算 | 完整调度前缀、首次成功后的预算曲线、Coverage、EPT、EPS、Continuation EPT、付费短缺、原生拒绝、重复和通信耗时 |
| `complete Cells` | 配置中列出的工作负载序号 | 按生成种子、Primitive / Higher 和外部父数统计的生成、入口接受、有新增贡献的完整实例、签名有效操作 |
| `prior ablation`、`prior native` | 实际曝光或请求预算 | 上轮超参数矩阵和已发表的原生对照。原生分组保留阶段、程序、温度、不放回开关和页容量，曲线展示对应预算下的中位数 |
| `archive` | 配置中列出的来源文件序号 | 历史 CSV、JSONL、配置和清单的正文。较长文件以连续文本分段保存，保留每个来源文件的 SHA-256 |

`native` 的 `total` 以整个运行计数，`continuation` 从第一笔具有原生签名有效操作的付费请求之后开始计数。回执字段中的 `run` 表示该预算下整个运行的计数。完整调度指标按实际付费数放在 `schedule` 下。原生有效操作以 Runtime 归因为准，Higher 的内部后缀归入其已签发的根实例。

历史记录缺少的梯度范数和耗时留空。冻结探针的已知目标命中率受核验目标集合覆盖范围限制。训练采样点的阶段耗时可用于定位单步开销，累计训练时间来自原始优化循环。对比墙钟时应使用已注明硬件和配对条件的实验。

## 存储与复现

- 原生 SQLite、训练检查点、配置和权重仍由原实验生成。看板只读这些记录。每个投影保留来源和指纹，重复同步复用已导入的同版结果。
- 默认看板数据在 `~/Library/Application Support/CellFoundation/SwanLab`，SDK 隔离环境在 `~/.local/share/cell-tracking/venv`。可分别设置 `CELL_SWANLOG`、`CELL_SWAN_VENV` 和 `CELL_SWAN_PORT`。本地网页只监听回环地址。
- `PARTNER_INDEX_OUT` 指向包含 `full-ce-scaling` 和 `continuation-exposure` 的原始实验目录。移动盘断开时仍可查看已经导入的数据。`CELL_DATA` 指向原生程序目录，用于按程序指纹核验 Primitive/Higher 的静态分界。
- 默认每跨过 1,000 次完整 Token 曝光或到达检查点采集一次更新。可用 `CELL_LOG_INTERVAL` 设置间隔，或用 `CELL_TRAIN_LOG=0` 进行关闭日志的成本对照。CPU 裁剪复用本来就会产生的范数，设备张量不会因写日志而被逐项同步回 CPU。
- 已启动训练在保存下一份原始检查点时可被导入。带采样日志的训练可以在检查点之间刷新。模型权重与数据不上传。
- 新训练记录 Git 提交和关键源码摘要。旧投影区分原始训练提交与报告入库提交；缺乏证据的训练提交留空。
- 运行 `sh partner_index_reproduce.sh swan_logging_bench.py train` 可复现同权重的训练日志对照。设置 `CELL_LOG_BENCH_CONSUMER=1` 会在开启组同时启用真实 SwanLab 写入进程。原始配对计时保存在 `continuation-exposure/swan-logging-cost.json` 和 `swan-logging-sidecar.json`。
