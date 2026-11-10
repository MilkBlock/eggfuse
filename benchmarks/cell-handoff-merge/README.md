# Cell 状态继承分支的完整合并检查

对象是 standalone Cell CPU，合并前基线为 `168285bd`。完整合并
`codex/cell-state-inheritance`，冻结的分支头为 `c8b099fd`，共同祖先之后的
13 个提交全部保留。没有挑选提交，没有改写任一分支历史；查询片段到 RHS
的新布局改动尚未加入这次对照。

编译期机会来自已有成功 Cell/Run 转移：已证明的前序结果可以通过共享槽布局
继承，连续匹配规则也可以复用完全相同的 RHS completion 范围。合并保留实际
返回见证、当前 Eq/可见性和生命周期检查、原 Run/效果顺序、残余枚举及赢家
选择。worker handoff/v3 是已校验的编译描述，尚未给予运行时并发写图或删除
发布的权限。该描述本身不计节省分。

## 验证范围

- 56 项 compiler/unit/integration 与 66 项 runtime 单元测试通过，覆盖 query
  workers/receipts、状态继承和 scoped/staged completion；default/all-features
  检查及 README Cargo compile/run/bench 短例入口通过。
- release 运行 sum-bits、普通短例、强制 hash 碰撞短例、混合 Cell/残余输入
  短例，分别对比旧版、关闭 worker、inline 1、pool 2、pool 4，共 20 个配置。
  最终图及 Run 签名一致；短例还比较全部 Run 图和有序绑定。
- 指定 `choice_diagnosis.py` 复用 native exports，对冻结 sum-bits 返回 pass。
  另生成 v2 状态选择与全 materialized 对照，验证它们和旧版的最终图及
  1,428 个 Run 一致，再独立通过相同 native 语义验收。
- sum-bits 和 Raytrace 均成功生成并重建校验 handoff/v3。它们各有 582 个
  rule/layout；未在 runtime 中安装第二份指令或绑定图。

## 计时设计

使用同一冻结程序隔离 merge 的运行时影响，不重新训练 catalog，也不把新
state plan 安装进计时程序。关闭 worker、inline 1、4 worker/g64 分别有合并
前后配对；Raytrace 额外重跑历史串行二进制。所有配置预热一次，交错测量三次。
使用普通 release `sparse-cells,view-ports,storage-metrics`，不启用 allocator
诊断，计时期间不编译。环境为交互式 Apple M3 Max，非受控专用机器。

每个完整进程都验证最终图和有序 Run 签名：Raytrace 16,883 个 Run，sum-bits
1,428 个 Run。这是旧 runtime 回归对照，不能冒充独立 native Raytrace 证明。
三个样本的区间只反映本轮波动，不能证明跨机器或所有工作负载无回退。

| 推理中位数，合并前 → 合并后 | sum-bits / ms | Raytrace / s |
|---|---:|---:|
| 关闭 worker | 24.985 → 25.603 | 9.888 → 10.045 |
| inline 1 / g64 | 26.224 → 25.425 | 9.774 → 10.131 |
| 4 worker / g64 | 26.795 → 25.667 | 9.860 → 9.765 |

四线程未观察到明显的大幅回退。Raytrace 的合并后/合并前成对推理比为 0.985，
本轮区间 [0.980, 1.027]；sum-bits 为 0.947，区间 [0.943, 1.049]。
关闭 worker 有小幅回退：Raytrace 成对比 1.016、sum-bits 1.033。
Raytrace inline 成对比 1.038，区间 [0.994, 1.067]；不能说合并完全没有成本。

本轮合并后四线程比同版 inline 的三个样本都快，成对比 0.964，区间
[0.937, 0.985]。但合并前 inline 中位数已是 9.774 s，与合并后四线程
9.765 s 接近；不能把相对变慢 inline 的全部差额宣传成新的总体加速。
同轮历史串行中位数为 10.063 s。详情及原始计时字段见 [results.json](results.json)、
[ray-samples.json](ray-samples.json) 和 [sum-samples.json](sum-samples.json)。

状态继承单独的短例实际免除 195 次 capture 读取和 195 次存储，新增 232 次
继承标记和 71 次间接读取，见 [state-check.json](state-check.json)。这些是
相同 kernel 的 selected/materialized 工作量差异，不是上述冻结程序的加速来源。

## 复现

使用新输出目录 `OUT`，冻结合并前后的普通 release 二进制。保存程序、二进制
哈希和合并双方提交到 `provenance.json`，按相邻 manifest 修改本地路径。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --lib --test query_workers --test query_receipts --test state_inheritance --test staged_completion --test scoped_completion
cargo test --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --lib
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py AFTER BEFORE SUM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit 168285bd --extra-fixture MIXED_FIXTURE
python3 benchmarks/cell-query-workers/raytrace_measure.py measure OUT/ray-manifest.json OUT/ray-timing --repeat 3 --warmups 1 --timeout 90
python3 benchmarks/cell-query-workers/raytrace_measure.py measure OUT/sum-manifest.json OUT/sum-timing --repeat 3 --warmups 1 --timeout 30
python3 benchmarks/cell-handoff-merge/collect.py OUT benchmarks/cell-handoff-merge
```

状态选择另用 `bake_state_plan` example 生成 `sum-state-program.json` 和
`sum-materialized-program.json`（后者多传入 `materialize`）。对两个程序各执行
一次普通 release 4 worker/g64，保留为 `sum-state` / `sum-materialized`。
按 marker-handoff 的 contract 准备 `state-semantic`，执行指定验收器输出
`state-acceptance.json`。`emit_worker_handoff` example 生成两份 handoff 后运行：

```sh
python3 benchmarks/cell-handoff-merge/verify_state.py OUT SUM
```

验证脚本只读取这些已保存执行，不重跑工作负载。构建、完整图、日志、编译
sidecar 留在忽略的 `out/cell-handoff-merge`；仓库保留可复现脚本和文本结果。

## 后续分支同步

完整计时结束后又合入分支截至 `39512f71` 的两个提交，其中 `b840448c`
直接构造 closure 位图并复用临时行；另一个提交记录对方的测量结果。
本地重跑 49 项 compiler/query-worker/state/scoped/staged 测试和普通 release
构建通过。用户随后要求回到 worker 直接接续 Cell 的实现，因此没有启动
这两个追加提交的补充计时。上文计时与二进制哈希仍严格属于 `c8b099fd`
合并快照，不能用于声称追加提交的最终版本已经完成性能验收。
