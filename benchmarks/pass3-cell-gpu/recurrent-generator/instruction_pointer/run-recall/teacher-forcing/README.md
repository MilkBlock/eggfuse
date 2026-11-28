# 完整 Cell 的批量 Teacher Forcing

训练采用原生核验的具名目标，保持原有因子分解。对每个状态先编码 Memory，再收集真实目标中不同的前缀。对同模板、同深度的前缀批量运行原 GRU 和 Query。用原有静态操作数接线读取已选端口，端口字段的 latent 投影在该状态的前向图内共享。跨状态按端口数和 Query 数分桶，用 padding 和 batched GEMM 合并基础寻址。每个状态单独应用自己的类型声明、关系项和 LogSoftmax。Python 仍负责原始具名引用整理、不同模板族的变体概率和状态编码。模型的 Query 和 GNN 在 CPU 运行，混合 Metal 对照将稠密打分和最终概率归约放到 MPS。没有引入跨更新的可训练张量缓存。

## 计算图审计

原函数 complete_ce 已缓存每个不同前缀，但每个前缀分别进入 address。原 CPU 逐 owner 做两次归约。将 owner 选择概率与 owner 内端口选择概率相乘，公共的端口 logsumexp 项相消。重新归一化后的端口 logit 等于 Query 与 owner Key 加端口 Key 的内积除以 √32，再减去该 owner 公开端口数的对数。保留原字段关系加分后，在静态类型域上归一化。这沿用已验证的扁平读出代数，速度变化同时包含扁平归约与张量批处理的收益。

原单状态真实 CE 基准，16 个状态、632 次完整曝光，前向中 493 次地址调用，累计 526,922 次 logsumexp。单线程 CPU 下 cProfile 的完整记录见 [调用树](scalar-cprofile.txt)。按四状态等曝光更新做独占计时，Recipe/GNN 0.148 秒，Memory 0.152 秒，Query 和 GRU 0.028 秒，候选处理 4.280 秒，模板变体 0.005 秒，CE 拼装 0.121 秒，Backward 5.099 秒，Optimizer 0.002 秒。CPU 路径没有 GPU 同步。[计时定义与原始计数](reference-profile.json)

## 对照条件

每种机制使用相同初始化、632 个不同的状态 × 目标，四次更新。A 为原始前缀循环，B 仅在同一状态内批处理，C 允许四个状态在同一次更新中共享打分批次。模型登记 32,874 个参数，当前路径前向连通 18,880 个；局部和端到端反向分别连通 4,160 和 18,880 个。计时涵盖 GNN、Memory、前向、Backward 和优化器，语料预加载和事后数值校验在计时区间外。Metal 前后向阶段边界显式同步。各次时间会受到首次 MPS 编译和机器同时运行其他任务的影响。[局部训练](local.jsonl) · [端到端训练](end-to-end.jsonl)

逐目标对照含 48 枚原生核验 Cell、零至七父 Primitive、一父和二父 Higher，覆盖每一个反向连通张量。CPU 与混合 Metal 分别检查完整 NLL、梯度和一步 AdamW 更新；另有连续四步的批量对照。长训允许浮点归约顺序引起轨迹差异。[逐目标检验](equivalence.jsonl)

内存比较采用隔离进程的 RSS 高水位，包含 Python、Torch、语料和模型。设备内存另测驱动分配量。独立的 Metal 计数器观察本进程直接 dispatchThreads 和 dispatchThreadgroups 调用；该指标不推断驱动内部子派发、间接派发或 GPU 机器指令。显式同步的等待时间包含在前后向墙钟内。局部训练的四次更新在 B 和 C 中分别观测到 1,570 和 1,488 次直接派发。[独立进程](isolated.jsonl) · [Metal 派发](metal-dispatch.jsonl)

## 复现

在 instruction_pointer 目录设置 ARTIFACT_ROOT、CELL_DATA、CELL_COMPILER、CELL_REPLAY、PYTHON、PARTNER_INDEX_OUT，并使用原实验的 KV_READOUT=full、VALUE_READ_SCALE=rich。

```sh
sh partner_index_reproduce.sh tf_profile.py train
sh partner_index_reproduce.sh tf_equivalence.py train
sh partner_index_reproduce.sh tf_benchmark.py train
TF_ARM=C sh partner_index_reproduce.sh tf_benchmark.py train
clang -O2 -fobjc-arc -dynamiclib -framework Metal -framework Foundation tf_metal_dispatch.m -o /tmp/tfmetal.dylib
TF_ONLY=C:mps TF_METAL_COUNTER=/tmp/tfmetal.dylib sh partner_index_reproduce.sh tf_benchmark.py train
TF_ONLY=C:mps TF_SAMPLE_DEVICE=1 sh partner_index_reproduce.sh tf_benchmark.py train
CELL_TEACHER_FORCING=batched EXPOSURE_DATA=A EXPOSURE_ARM=local CELL_SEED=71 CELL_MILESTONES="250000 500000 1000000" sh partner_index_reproduce.sh exposure_train.py train
EXPOSURE_MODELS=A-batched/local-s71-t1000000 sh partner_index_reproduce.sh tf_native.py evaluate
```

长训保留 100K 的参数、AdamW、采样器、原有单状态更新预算和固定语料。从 100K 开始的批量路径写入独立 A-batched 目录。实际程序执行采用原有自主生成器和原生 CCP Runtime。离线前缀只用于有标签的优化。

## 实测结果

| 局部训练 | 完整目标/秒 | 毫秒/更新 | 独立进程峰值 RSS，MiB |
|---|---:|---:|---:|
| A 原始 CPU | 70.9 | 2,230 | 2,017 |
| B 同状态 CPU | 1,661 | 95 | 722 |
| C 跨状态 CPU | 1,750 | 90 | 721 |
| B 混合 Metal | 246 | 642 | 899 |
| C 混合 Metal | 1,034 | 153 | 898 |

本组目标全为不同的状态 × 完整具名 Token，所以唯一目标/秒与表中的完整目标/秒相等。端到端训练在 A CPU、B CPU、C CPU、B Metal、C Metal 下分别为 66.9、578、632、456、518 个目标/秒。冷启动、运行顺序与并发影响数值，独立进程对照仍保持 CPU C 的吞吐优势。Metal 内存在单独诊断中以约 1 ms 周期抽样，B、C 驱动分配采样峰值均为 42.08 MiB。显式前后向同步总等待分别为 1.13 和 1.82 ms；数据搬运等隐式等待计入总墙钟。[设备内存采样](metal-memory.jsonl)

固定语料、种子 71 的长训使用最快的 CPU 批量内核，并保留原来每次更新一个状态的曝光和步数。新增 900,000 次完整曝光耗时 476.03 秒（1,891 次/秒）。累计 1M 曝光历时 1,878.04 秒，其中原 100K 检查点耗时 1,402.01 秒。总计见过 6,376 个决策状态、448,602 个不同具名目标，完成 20,363 次更新。250K、500K、1M 均保存了权重与优化器进度；检查点权重和签名见外置 continuation-exposure/A-batched 与 [检查点学习曲线](exposure.csv)。验证 CE 由 5.924 下降至 500K 的 5.822，1M 时回升到 5.848。参数累计浮点漂移使长训后的自由生成可能不同，单步等价性不保证长程训练逐位相同。

三个检查点各使用五个程序和两个地址种子做原生独立执行，每条轨迹设 256 个付费请求的上限。请按各行实际付费数、终图和原生失败状态解释。原生 EPS 为该次运行的墙钟测量。[250K](native-250000.csv) · [500K](native-500000.csv) · [1M](native-1000000.csv)
