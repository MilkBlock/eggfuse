# 查询拥有的 Cell 实例直接进入 RHS

对象为 standalone Cell CPU，基线 `8758d461`。本轮只做短例语义、工作量、
allocator 诊断和 Raytrace 前 128 个 Run 检查，没有完整速度测量。

## 已有执行与编译事实

当前 catalog 的实际 sum-bits 执行产生 3,034 个 Spine 赢家和 4 个 context
结果。每个结果在查询后已经拥有完整输入和实际见证，但旧 `Binding::matched`
仍按 `Rule.inputs` 把 `Vec<Value>` 重新装入 `Slots`，再收集一份 RHS 结果向量。
这些不是深复制：Value 被搬运，字符串/集合内容没有在此重新克隆。

原 Cell 定义已经给出输入槽编号，Query 已给出对应字段投影；无需再训练一个
catalog 或解析第二套 sidecar 指令。完整匹配键仍用于赢家选择、残余去重和
既有接续，所以这里没有按 `rhs_input_slots` 提前裁掉输入。

## 已删除的交接

`cell::Instance` 现在是查询、赢家选择和 RHS 的同一所有权类型。
`Matched` / `Binding` 只是各调用点保留的类型别名，不再是两种存储。
worker、串行 Spine 和 context 查询直接写入最终输入 Slots；成功实例带着
原 QueryFacts、epoch 和接续 token 进入原 Run 的 StagePatch。

赢家队列直接借用实例输入作键，删除单独的 key 向量加空答案壳。源 ordinal
恢复、同键较深 Cursor 优先、同深度保留先到者、残余合并的顺序均保持。
三个 `Matched → Binding` 的转换/collect 路径全部删除；RHS 接受原实例向量，
输入 Slots 随执行转入原 Cell frame。尚未封存的 legacy origin map 仍保留其
所需的独立键，并承担该复制成本。

worker 的输入布局引用同一份 `Rule.inputs`，不另复制一张槽位表。sparse 模式
为这份不可变布局使用 Arc，workers 只借用其内容；共享 handle 在编译 CellCode
时克隆。Rule 的现有克隆也会承担原子引用计数成本。Graph/Cursor 没有改成可
并发写入，RHS 仍按原顺序执行，真实构造子返回值、union、可见性和生命周期
检查保持原路径。

## 成本核算

| 同配置前后对照 | sum-bits，4 worker/g64 | Raytrace 前 128 Run，4 worker/g64 |
|---|---:|---:|
| 删除的输入重装分配，按实际返回数及源码槽宽推导 | 3,038 | 3,683 |
| 删除的 Value 搬运 | 11,622 | 15,448 |
| 候选提前成形额外写入的槽位编号 | 255 | 6 |
| key 查询变化 | 0 | 0 |

旧分配/搬运数由实测 `bindings_by_rule`、context 返回数和已校验程序的输入槽宽
推导，collector 同时核对新实例的实际槽数，不能把覆盖数直接当成 allocator
总收益。候选使用 `(slot, Value)`，每项 24 字节；旧纯 Value 项为 16 字节。
普通 release 中实例头为 120 字节，带 Cursor 的赢家记录为 288 字节。模板
输入指针使编译 CellCode 存储从 41,304 增至 43,352 字节。这些不是总 RSS。

另用前后两份 `allocation-metrics` 诊断二进制，测量整个 execute 的分配器请求：

| sum-bits / 4 worker | 前 | 后 | 差值 |
|---|---:|---:|---:|
| alloc 调用 | 172,006 | 168,362 | −3,644 |
| realloc 调用 | 19,392 | 19,393 | +1 |
| requested bytes | 33,647,298 | 33,437,034 | −210,264 |
| peak live requested bytes | 157,308,218 | 157,322,608 | +14,390 |

inline 1 的 alloc/realloc 合计少 3,644 次，申请字节少 210,184，峰值在用申请量
多 14,486。每个配置只执行一次，worker scratch 首次分配可能随任务落在哪个
线程而小幅变化。allocator 原子计数会扰动耗时，这些执行不作速度结论。
诊断排除 setup/export；setup 计数也完整保留在 [results.json](results.json)。

新增片段/槽位计数是存储规模和接管证据，不给 Bake 重复的覆盖奖励。现有
等权 Work 未包含旧 Binding 重装成本，因此本轮不把历史 Work 分数当成这项
表示变更的收益证明；实际总分配与新增存储另行核算。

## 验证与剩余路径

- 68 项 runtime 单元测试、19 项 query worker/receipt/state inheritance 测试、
  2 项 context 集成测试通过，共 89 项。新测试检查实例能跨线程交回、稀疏槽
  地址保持和真实 mutable receipt 不丢失；已有测试比较完整 Run 图与有序绑定。
- release 的 20 个短例配置通过，sum-bits 指定 `choice_diagnosis.py` 为 pass；
  Raytrace 前缀最终图、128 个 Run 和旧逻辑计数一致。allocator 前后执行同样
  验证图、所有 Run、key 查询、图统计和各规则返回数。
- default/all-features 检查及 README Cargo compile/run/bench 短例入口通过。

查询 scratch 仍与成功实例分开，以便在 Cell 任务内重复使用。RHS 的结果
receipt 收集、导出 capture 和 Shared Entry 发布尚未统一到这份实例的保留
布局；本轮不声称已删除这些转存，也没有扩大 worker 执行效果的范围。

## 复现

在修改前冻结 `8758d461` 的普通 runtime、query_prefix 和 allocator runtime。
新旧都使用相同 Cargo profile/features，构建期间不修改 Rust 文件。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts --test state_inheritance
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test compiler context
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py AFTER BEFORE SUM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit 8758d461 --extra-fixture MIXED_FIXTURE
QUERY_PREFIX_BEFORE RAY OUT/prefix-before 128 4 64
QUERY_PREFIX_AFTER RAY OUT/prefix-after 128 4 64
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics --bin eggfuse-cell-runtime
ALLOC_BEFORE --program SUM --output OUT/alloc-before-4 --local-congruence --query-workers 4 --query-grain 64
ALLOC_AFTER --program SUM --output OUT/alloc-after-4 --local-congruence --query-workers 4 --query-grain 64
```

再把最后两条中的 worker 和输出后缀改为 1，保存同配置 inline 诊断。
`before.json` 记录基线提交与三份冻结二进制的哈希；按 collector 的固定文件名
保留二进制及输出后执行：

```sh
python3 benchmarks/cell-owned-fragments/collect.py OUT SUM RAY benchmarks/cell-owned-fragments/results.json
python3 docs/optimization-catalog/catalog.py check
```

完整图、二进制和原始日志留在忽略的 `out/cell-owned-fragments`；只提交复现
源与相关文本证据。
