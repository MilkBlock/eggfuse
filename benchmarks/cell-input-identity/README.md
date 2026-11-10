# Cell 匹配身份只取定义中的输入

对象为 standalone Cell CPU，基线 `d61afeb6`。本步建立 worker 继续填 RHS
槽之前必须满足的身份约束，没有扩大 worker 执行范围或宣称速度收益。

此前 `seal_answers` 用整个 `Instance.values` 排序去重，未封存的 legacy
origin 也保存整个槽数组作为 key。查询刚完成时数组只含输入，两者恰好一致；
一旦实例已有 RHS 结果，同键实例会被错误区分，legacy key 也与 `begin_step`
按 Rule.inputs 查找的键不一致。

现在赢家比较、去重和 legacy origin 写入均使用原 Cell 的 Rule.inputs。
只有输入的实例仍直接比较连续 Slots；附带结果时借用输入投影，支持 RHS
地址插在稀疏输入地址之间。不复制绑定、不扩大实例头，也不添加运行时 key
缓存。原深度优先、同深度先到者优先和源 Run 顺序保持。

回归把相同输入、不同 RHS 槽以及不同深度的实例混在一起，验证只保留原来
应获胜的实例及其原始分配。查询 worker、Entry 发布与跨阶段继承测试通过。
20 个短例配置保持最终图和 Run 签名；fixture 还比较阶段图与有序绑定。
指定 sum-bits `choice_diagnosis.py` 返回 pass / 0，README 的本地
compile/run/bench 短例入口通过。正常 workload 尚未提前填 RHS 槽，因此
其工作量保持不变；这个正确性准备不能算作已完成的计算接管。

## 从既有执行记录选择后续工作

[opportunity.json](opportunity.json) 由 [opportunity.py](opportunity.py) 只读生成。
使用当前 sum-bits 与保存的完整 Raytrace report 中 `bindings_by_rule` 加权，
不是新一轮测速，也不是 worker 的实际命中量。

| 源形状机会 | sum-bits | 完整 Raytrace 旧执行 |
|---|---:|---:|
| RHS 开头只依赖匹配输入的标量操作 | 193 | 19,819 |
| 全 RHS 中仅依赖输入或此前标量的操作 | 483 | 42,394 |
| 未被静态别名消除的构造子前缀操作 | 2,741 | 371,286 |

这说明仅搬走开头算术的规模有限。构造子读取仍需当前 Eq、可见性和真实结果
证明；提前 miss 或落选实例会增加工作，不能把上表当实际节省。并行计算前
还需处理查询赢家的重复整理，以及同 Cell 多 Entry 的重复读取规模。

```sh
python3 benchmarks/cell-input-identity/opportunity.py SUM_PROGRAM SUM_SAVED_REPORT RAY_PROGRAM RAY_SAVED_REPORT benchmarks/cell-input-identity/opportunity.json
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports --lib cell::
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test state_inheritance --test entry_publications
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime
python3 benchmarks/cell-query-workers/check.py AFTER BEFORE SUM_PROGRAM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit d61afeb6 --extra-fixture MIXED
```
