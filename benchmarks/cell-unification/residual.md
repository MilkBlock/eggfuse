# Cell 残余查询数据流统一

实验对象是 standalone Cell CPU；基线为 `9dfe6986`。这不是 native egglog 内核改动或整套统一工作的最终验收。

完整查询、残余查询和 repair Cell 现在共用 `cell::Query` 的指令绑定与操作数。残余入口只保留准入、prefix 和现有索引能力的配置，不再定义第二套 Step/assign/check 指令。功能 key 完整的残余入口与完整入口直接共享同一 `Rc<Query>`。

入口字段用 Anchor 读取，计算结果用 StepResult 读取，展开字段用 Column(step, column) 读取当前候选行。候选行只在当前递归调用期间借用；写图和下一个 Run 不会保留这条借用。重复变量比较当前候选行的首次出现列。原来的种子槽位复制、候选逐列赋值、规则槽位读取器均删除。prefix 成功后保存实际结果，失败时仍在同一 Cell 指令位置执行正常查询，已经完成的前缀不会重跑。

`row_kernels` 的旧 JSON 仅是兼容投影：编码器根据同一个 Cell 指令的 order/access 输出旧 SSA 坐标，加载器校验后不保留、更不执行这份 assign/seed 描述。不是保留两套运行时方案。

完整入口的覆盖证明和残余枚举的 delta ownership 仍各自生效。完整入口不会因为残余查询能 Expand 就接管全部结果。PointPorts、邻居缓存、sum 过滤、查询版本、当前存活/可见性和源 Run 顺序都保留。Free Join、Sieve、range/local-context/view 等入口仍有待后续审查和统一，不能只凭共同数据流就宣称匹配部分已全部完成。

新增 `register_result_writes` 计算实际结果保存，包含原 `register_prefix.field_writes` 子集，不能重复累加。`register_expansion_rows` 计算当前候选访问，含约束失败的候选；`shared_query_plans` 计算共享计划规模。三项都不是直接的性能收益指标。收益仍由旧工作指标、分配和正常构建的成对计时判断。

验证限于既有 sum-bits 合同和三个短 fixture。新增 borrowed 用例包含重复候选字段、逐候选标量运算、失败 guard 与后续 Run 的迟到输入；冻结旧 runtime 和新 runtime 执行同一 artifact，对比所有阶段和写入结果，并在集成测试中执行 native 源程序的 check。

| 最终短 sum-bits 检查 | 基线 → 候选 / 变化 |
|---|---|
| 推理中位数 | 24.721791 → 24.834917 ms |
| 整进程中位数 | 130.036042 → 131.629625 ms |
| 峰值 RSS 中位数 | 177,504,256 → 178,798,592 bytes |
| setup 分配次数 / 申请量 | 不变 |
| 执行期分配次数 | 不变 |
| 执行期申请量 | −70,144 bytes |
| 共享完整/残余计划 | 177 |
| 实际展开候选行 / 计算结果保存 | 7,097 / 1,544 |

7 组成对独立进程测试，1 次预热，无并行构建。推理配对比率中位数 0.99834，bootstrap 95% 区间 [0.95810, 1.00881]；整进程配对比率中位数 0.99725，区间 [0.98276, 1.00538]。中位数之比和配对比率方向不同，区间均跨过持平；这不是加速证据。峰值 RSS 仍增加约 1.23 MiB，性能验收未完成，不能用复制减少代替它。

第一版的兼容编码重复复制已生成的 JSON 树，公共指令绑定也复制了已绑定的预期结果。最终版移动 JSON 子树、借用预期值，删除这两项额外工作。第一版记录保留在结果 JSON 的 earlier_attempt 中；不跨两轮比较绝对耗时来宣称收益。

最终 216 项编译器测试、52 项 runtime 全特性测试、33 项最小特性测试通过。22 个编译产物、1428 个 Run 的顺序和工作字段、sum-bits 的 state/RHS/write/resume 摘要保持一致，既定语义脚本返回 pass。三个 fixture 均小于 1 秒，分别保存并校验逐阶段 state、binding、RHS、write/resume 摘要。新增 borrowed 用例实测访问 6 个候选行、保存 12 个结果；prefix 查找/接续的旧工作计数与冻结基线相同。

结果及复现入口见 [residual-results.json](residual-results.json)、[residual-timing-spec.json](residual-timing-spec.json) 和 [coverage.json](coverage.json)。普通构建计时、诊断构建核查语义与分配；没有新增 Raytrace 或历史最快配置测试。加载分配不包含在 setup/execute allocation 区间中，仍须由整进程时间和 RSS 共同约束。
