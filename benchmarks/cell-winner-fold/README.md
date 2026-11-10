# Cell 赢家整理只排序一次

对象为 standalone Cell CPU，直接基线 `c8d0584b`。已有查询执行仍把同一
Run 的成功实例放进带 source ordinal 的规则容器；此前先恢复 ordinal 顺序，
搬到独立 Winners 数组，再稳定地按输入、深度排序。原 Rule.inputs 和已保存
的 Cursor.depth、唯一 source ordinal 足以直接确定同一个赢家，不需要第二份
容器或编译期新增事实。

现在在原容器上按「输入键、深度降序、source ordinal」一次排序去重，然后
直接封存原 Instance。深度较大的实例优先，同深度保留源顺序最早的实例。
比较只取原输入，不让提前存在的 RHS 槽改变身份。最终 Matched 数组、残余
匹配合并及其去重仍保留；源错误顺序、Run 可见性和有序 RHS 不变。

跨 Run 仍沿用上一轮共享结果槽，本步不新增跨阶段接管。下一轮共同读取的
机会需要按实际同 Cell/Run 的 Entry 重复输入和指令测量，不能从归组数推断。

## 短例证据

| 工作 | sum-bits（inline 1 与 4 worker） | Raytrace 前 128 Run / 4 worker |
|---|---:|---:|
| 删除的中间赢家记录搬运 | 1,244 | 2,971 |
| 删除的中间容器批次 | 383 | 149 |

两种 sum-bits 配置的 execute 总 allocator 诊断均为：alloc -238 次、realloc
-48 次、累计请求 -308,544 字节、峰值请求 -5,986 字节。结果已包含失去旧
winner scratch 容量复用后的成本。每种配置诊断一次，细小调度相关差异仍可能
波动。记录搬运不是槽值深复制，容器批次也不等于 allocator 调用次数。

报告增加 `winner_ordering: input-depth-ordinal/v1`。旧
`winner_order_comparisons` 只计 ordinal 排序，漏计随后的 key/depth 排序；新版
计整个合并比较器。因此这两个版本的原始比较数及包含它的旧 Work 分数不能
直接用于声称节省。移除的记录搬运只按实际差额计一次，不另给覆盖奖励。

72 项 runtime 单元测试通过，包含 64 种到达排列与旧选择算法的等价回归。
query worker、receipt、Entry、joint results、跨阶段继承及 all-features scoped
completion 测试通过。20 个短例配置保持最终图及 Run 签名，fixture 另比较
阶段图和有序绑定；指定 sum-bits `choice_diagnosis.py` 返回 pass / 0。
Raytrace 128 Run 的图、签名和逻辑计数一致；README compile/run/bench 短例
入口通过。详见 [results.json](results.json)。这里不声称完整 Raytrace native
正确性或速度收益，普通 release 的统一计时另行记录。

## 复现

冻结基线普通、allocator 和 query_prefix 二进制，记录 SHA256 到
`OUT/before.json`；构建候选并分别冻结，避免 allocator 覆盖普通计时二进制。

```sh
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts --test state_inheritance --test entry_publications --test joint_results
cargo test --locked -p eggfuse-cell-compiler --all-features --test entry_publications --test joint_results --test scoped_completion --test state_inheritance
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py OUT/runtime-after OUT/runtime-before SUM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit c8d0584b --extra-fixture MIXED
OUT/query-prefix-before RAY OUT/prefix-before 128 4 64
OUT/query-prefix-after RAY OUT/prefix-after 128 4 64
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics --bin eggfuse-cell-runtime
OUT/runtime-alloc-after --program SUM --output OUT/alloc-after-4 --local-congruence --query-workers 4 --query-grain 64
python3 benchmarks/cell-winner-fold/collect.py OUT benchmarks/cell-winner-fold/results.json
```

allocator 还需要对 before/after 各执行 inline 1 和 4 worker；完整图、二进制
和构建输出保留在忽略的 `out`，只提交复现脚本和文本结果。
