# GPU 生成绑定，Rust Cell CPU 提交

在相同的 M3 Max 和两个冻结的 eggcc Pass 3 上，GPU 生成的见证引用可以直接驱动原 Rust `cell_runtime`。sum-bits 的 7,265 个 RHS 输入有 3,043 个来自 GPU（41.9%），dot-product 的 6,704 个有 2,092 个来自 GPU（31.2%）。两例均逐 Run 对齐。按 Run 合批后，整轮推理耗时仍为 CPU 对照的 6.9 和 7.1 倍。[原始样本、计数及审计摘要](results.json)

## 一个 token 如何进入原引擎

1. 规则计划选择只含一或两个关系原子的查询。每个源 Run 冻结时，CPU 保留其调度、脏标记、整表为空的快速判断、水位和活 Spine 判断。其余规则继续走现有 CPU 路径。
2. CPU 枚举所选表的物理行，保留位置到真实见证的映射，将当前规范值无损地编码为局部整数。每行附带可见性与增量标志。编译出的等列或字面量检查由 Metal 执行。GPU 枚举行或行对，返回满足全部约束的行位置。合批时输出规则组与组内行对位置。
3. CPU 按返回的位置读取冻结行的槽值和事实引用，复用源规则的绑定排序和去重。获胜绑定进入同一条 Rust `apply`。构造、函数合并、有效写入、Spine 发布、union、同余修复与下轮可见性都在原 CPU 图上发生。设备错误直接终止实验。
4. 有活 Spine 的规则由原执行器接续。永久退订只允许在静态上全部消费者都由 GPU 覆盖、无潜在 Spine 消费者且无发布所有者的节点。此功能位于默认关闭的 Cargo feature `gpu-bindings`。

这里比较的是精确的设备匹配和见证 token 交接。混合路径没有训练新的指针策略，也没有使用纯 GPU 版的已生成轨迹作输入。CPU 的图是每个 Run 的唯一事实来源。实验衡量独立的 Cell CPU 执行器；原生 egglog 的执行时间不在这组对照里。

## 执行耗时

| 路径 | sum-bits 推理 ms | 完整 CLI ms | dot-product 推理 ms | 完整 CLI ms |
| --- | ---: | ---: | ---: | ---: |
| 纯 CPU | 21.9 | 131.6 | 18.5 | 128.1 |
| 逐规则 PyTorch MPS，进程间交换 | 1837.6 | 2500.3 | 1164.7 | 1811.8 |
| 逐规则进程内 Metal，共享缓冲区 | 407.4 | 552.3 | 245.0 | 391.4 |
| 进程内 Metal，移除专属订阅 | 409.4 | 554.1 | 254.7 | 401.6 |
| 移除专属订阅，同 Run 合批 | 150.0 | 298.2 | 130.9 | 273.7 |

同一份未插桩 Rust 二进制，程序与 GPU 管线在 setup 中加载，推理期间服务常驻。每次新进程跑完整源调度；一轮预热后，十次轮换各臂顺序。CLI 含进程启动、装入、初始化、整轮推理、持久化状态及退出。每次导出都与 Rust 基准逐字节比较。独立审计构建仅用于验证。原纯 GPU 路径的常驻推理与 CLI 在另一组交错测量中取得。[图 30–32 及纯 GPU 分项](../profile/README.md)

## CPU 省下的工作与设备新增的工作

| 全程计数，sum-bits／dot-product | 纯 CPU | 按 Run 合批 |
| --- | ---: | ---: |
| CPU 残余候选 | 8,769／8,022 | 5,583／5,834 |
| CPU 入口 seed 递交 | 5,355／5,480 | 2,999／3,543 |
| CPU 入口参数复制 | 18,731／15,875 | 17,052／14,968 |
| CPU 终态活入口包 | 3,665／3,467 | 3,444／3,320 |
| CPU 入队节点通知 | 6,337／4,932 | 5,847／4,595 |
| CPU repair 实际依赖 | 2,229／1,362 | 2,229／1,362 |
| 为设备打包的关系行 | 0 | 179,779／141,423 |
| Metal 检查的行或行对（含旧行） | 0 | 4,824,849／5,156,042 |

每次只把一条规则送往设备时，需要 1,410／865 次发射。同 Run 合批后，352／312 个批次需 369／324 次发射，回传的见证位置共 24,344／16,736 字节。按批的输入准备耗时 29.8／24.6 ms，交接 95.5／84.8 ms，其中 Metal command buffer 的 GPU 执行区间累计 7.7／4.2 ms。交接还包含共享缓冲区写入、编码、提交、等待和读回。各列分别取中位数。PyTorch 的 service 计时边界覆盖 Python 设备调用与结果读回，与原生 Metal 的硬件时间戳不同。

CPU 残余候选和设备行对是两种工作单位。设备采用穷举的一／二关系匹配，为 3,043／2,092 个 token 检查约 482／516 万个行或行对。每次调用重新打包当前可见表，局部字典和数据只在当前查询有效。原 CPU 的共享入口和索引能直接避开大部分组合。

## 哪些 CPU 模块能够收缩？

被 GPU 接管的查询可以绕过 CPU 的规则入口搜索、Sieve、Free Join 和入口 seed 组装，两例都减少了实际入口状态。进一步静态退订 19 个入口节点，对终态活包数、入口通知数与参数复制数均无额外收益；这些入口本来就按需激活。共享订阅、稳定见证、提交顺序、union 修复和 Spine 生命周期仍有实际消费者。两例尚未验证整个 CPU matcher 可以删除。若继续评估，应把表变更按 epoch 增量发布给设备，让同一表的多个查询共享设备上的行与键索引，衡量能否同时压低打包和行对检查。

## 复验

五条路径分别在 sum-bits 的 1,428 和 dot-product 的 1,535 个源 Run 上对齐有序 RHS、有效写入、Spine 接续和最终图。sum-bits 有 1,450 次有效函数写入、2,098 次接续；dot-product 有 2,168 次有效函数写入、1,835 次接续。完整图、程序和三类轨迹各自保存摘要。计时样本另核对每个源 Run 的控制路径、变化标志、RHS 数和终图。

```sh
verified=/Volumes/EggFuseWorkspace/experiments/pass3-atlas-integration-20261120
~/.local/bin/eggfuse-job submit --kind compute -- /Volumes/EggFuseWorkspace/bin/run-eggfuse python benchmarks/pass3-cell-gpu/hybrid/bench.py "$verified" /Volumes/EggFuseWorkspace/experiments/NEW-hybrid-profile
```

研究分支可用 Cargo 单跑共享缓冲区合批模式。输出目录须为新目录。

```sh
cargo run --release --locked -p eggfuse-cell-runtime --features gpu-bindings -- --program "$verified/sum-bits/program.json" --output /tmp/eggfuse-hybrid-result --gpu-binding-native --gpu-binding-retire --gpu-binding-batch
```
