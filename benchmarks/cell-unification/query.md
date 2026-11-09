# Cell 查询执行统一

这是 standalone Cell CPU 的重写，不是 native egglog 内核性能结果。基线为 `4b5070cf`；整个 Cell 统一目标仍在进行中。

本次将完整 stage Entry 的普通槽位解释器、单表 Port 执行器和 staged Block 执行器合为 `cell::Query`。共享编译器从原查询及完整 Entry 证书生成 Anchor / StepResult / Literal 操作数。输入仍需实际匹配；编译出的结构本身不证明实例事实已经成立。

Program 持有一份查询计划；执行和 Bake 引用同一份定义。Bake 目录仅保存准入状态，迭代 dispatch 不再返回、克隆独立 Block。`PortResult` 只留在旧 artifact 的序列化格式中，加载后没有对应的第二套执行器。原 block 计数继续只表示 Bake 组合准入。

残余寄存器查询与完整 Entry 共用确定性的 atom 排序编译器，允许的 Expand 数量分别为一和零。残余枚举的寄存器、delta ownership、prefix 接续仍待统一，不能将此步记为查询部分全部完成。repair Cell 复用相同指令绑定和数据流组合。

来源 Run 顺序、缺失读取后迟到的输入、输出约束、活跃性检查、见证及完整/部分覆盖语义保留。成功结果生成同样的 witness map，短失败查询先保存在栈内暂存；未选择 Bake 的完整查询不再建立运行时槽位环境。

新增 `cell_query_entries` 记录执行覆盖，`cell_query_steps` 与 `cell_query_result_writes` 记录仍在发生的工作；不能把这些计数当成节省。收益检查还必须包括执行期分配、加载/setup、端到端时间，以及旧目录所有工作指标。

实验结果由 `collect.py --part query` 汇总到 `query-results.json`。诊断构建用于语义、Run 顺序、分配和写入摘要；普通构建用于计时。开发样例限于 sum-bits 与已授权的短 reused/replaced fixture，未运行新的 Raytrace 或历史最快配置对比。

本轮有 256 个完整查询定义，运行时执行 5,738 个完整 Entry，其中 3,828 个属于 Bake 已选组合。共执行 5,228 条后续指令，保存 2,604 个成功结果；这些不是新增收益。原目录全部已有工作计数及状态保持，新增三项成本/覆盖计数。

| 短 sum-bits 检查 | 基线 → 候选 / 减少量 |
|---|---|
| 普通构建推理中位数 | 24.719125 → 24.285000 ms |
| 整进程中位数 | 131.098041 → 130.211875 ms |
| 峰值 RSS 中位数 | 178,094,080 → 177,504,256 bytes |
| setup 分配 / 请求字节 | −221 次 / −21,800 bytes |
| 执行期分配 / 重分配 | −1,800 / −990 次 |
| 执行期请求字节 | −229,680 bytes |

7 组成对顺序随机的独立进程测试，1 次预热；没有并行构建。推理配对比率中位数 0.97968，bootstrap 95% 区间 [0.95358, 0.98697]；整进程配对区间 [0.99517, 1.00627]，不能声称端到端显著加速。加载新的查询计划不在 allocation 计数区间内，但计入整进程时间和 RSS。

编译器 215 项、runtime 全特性 52 项、最小特性 33 项测试通过；另重跑一项完整 stage 集成测试验证未入选和已入选 Bake 都进入共同执行器。22 个初始编译产物完全一致，附加 Bake catalog 通过校验。sum-bits 语义检查通过，最终状态、Run 序列、RHS、write/resume 摘要相同；reused/replaced 短例的状态、每阶段快照、binding/write/resume 摘要以及 prefix 工作一致。这些是 standalone Cell CPU 与冻结 native 导出之间的既有语义合同，不是 native 内核加速结果。
