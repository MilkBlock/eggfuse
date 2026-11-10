# Cell 查询的并行接管

本页记录 `13cfd235` 的首次接管。后续见 [完整 Raytrace 线程实测](raytrace-full.md) 和 [按 Cell 实例跨规则组织查询](../cell-run-queries/README.md)。

这次修改在 **standalone Cell CPU** 中执行真实查询，不是 native egglog 运行时的线程优化。基线为 `efc06d49`；功能显式通过 `--query-workers N` 开启，默认关闭。`N=1` 在调用线程运行同一个新 host，`N>=2` 使用固定 Rayon pool；`--query-grain` 默认为 64，与线程数独立。

## 从上一轮实际执行得到的机会

[上一轮 Raytrace 诊断](../raytrace-thread-bottlenecks/README.md) 中，search/RHS/query update 仍占大部分串行工作，局部 guard worker 大量空闲。冻结 catalog 已完成 663,403 次跨阶段接续，但仍有 1,104,033 次 `pre_resume_port_lookups`，实际 history/query receipt 覆盖很少。继续扩大 guard 队列不能直接承担这些查询。

本轮先接入 residual Cell Query，短样例成功，但 sum-bits 和 Raytrace 前 128 个 Run 的覆盖均为零：这些可执行的 Entry 已被 StageSpine 领取。因此同一个指令执行器随后接入 StageSpine 的实际查询路径。这不是新建第二套匹配计划或事实图。

跨 Run 可以保留的是已发布的 Cell Entry、真实结果及模板指令；可变函数的当前值、late input、union 后的新匹配和 watermark 不能由上一次匹配推断。本轮不消除这些读取。类型信息能证明：全键普通函数读取和纯标量指令，可以在当前已 settled 的 Run 上借用现有函数槽位完成，不需要临时 Row 或 canonical repair 的并发写入。

## 实现与仍然生效的义务

- `cell_query.rs` 从原 Query 推导函数查询能力；剩余 host 和跨阶段 host 都执行同一份 `Step.bind/evaluate`。不发新 `.egg` marker，不复制实例绑定或图索引。
- 将原 Function 的 `Rc` decoded cache 移入 Graph 内按相同函数索引寻址的缓存向量；Function 的现有 key/value/lifecycle 槽位可安全跨线程借用。没有把所有 Rc 换成 Arc。新增向量容量、额外缓存寻址属于真实布局成本，未单独标定 setup 耗时。
- 普通函数 key 索引、当前父关系和 live 位都来自 Graph。未完成 repair、Unit/view 独占存储、特殊 port-key 索引及构造子枚举不进入借用路径；有额外逐读取诊断副作用的 feature 也回退。
- 跨阶段只接管没有 context cache、没有任何保留 history、没有局部见证路线的 Entry。已有 receipt/prefix 路径保持原先职责。dispatch 不产生新的完成结果，因此空 history 的证明在 dispatch 后仍成立。
- residual 查询保留原 `(epoch, witness, atom)` delta 归属；跨阶段查询保留原最大 epoch/watermark 规则。不是把两种归属规则强行统一。
- worker 借用 Entry 字段，在原输出中直接构造 Binding/Matched。失败的查询不会在串行 host 重跑。按原 Entry 位置交回，包括拒绝和错误；原深度去重、相同深度胜者顺序、cursor sealing、RHS 和 Run 发布顺序继续生效。
- 读借用在 RHS 写入前结束，不新增运行时反向消费者表、逐行版本校验或 repair overlay。**这没有消除 repair 阶段，也没有实现并行 RHS。**

## 工作量检查

完整保存结果见 [results.json](results.json)，没有把单次诊断耗时列为速度结论。

| 工作负载 / 检查粒度 | worker Entry | 其中跨阶段 | 主线程接续 key 读取：基线 → 新版 | 全部 key 查询：基线 → 新版 |
|---|---:|---:|---:|---:|
| sum-bits，grain 1 | 269 | 269 | 2,092 → 1,794 | 18,692 → 18,692 |
| 短样例，grain 16 | 730 | 128 | 133 → 5 | 18,520 → 18,520 |
| 短样例，强制构造子 hash 碰撞，grain 16 | 749 | 128 | 133 → 5 | 18,691 → 18,691 |
| Raytrace 前 128 Run，grain 16 | 9,642 | 9,642 | 22,169 → 12,527 | 88,737 → 88,737 |

`pre_resume_port_lookups` 降低表示这些读取离开串行 `read_port` 路径，不是逻辑查询消失。worker 读取仍计入 `key_lookup_calls`，原 Cell 步数、结果写入数和完成接续数不变。Raytrace 前缀的 4 个 worker 均执行了查询；它不是全 Raytrace 语义或性能验收。Entry/answer 数也不是 committed mutation 数。

新增成本包括准入检查、重复 seed 遍历、Entry 头、批次/结果缓冲区、每 chunk 的临时帧和分派。Raytrace 前缀有 24,990 次 Entry 准入检查、619 个 chunk、1,238 个帧分配；sum-bits 的 grain 1 专用于覆盖检查，粒度过小产生很多准备工作，不是建议的速度配置。`entry_buffer_bytes` 是累计容量字节，不是峰值；`batch_buffers` 是缓冲区对象数，不是分配器总调用数。向量增长之外的值内部/投影分配没有冒充全量分配指标。

Bake 使用同一个 `work_credit` 账本收取新增准备费用，读取、字段写入和 key 操作只在原计数器收费一次，不给 answers/worker coverage 加分。[sum-bits 账本](work-sum.json) 净增加 10,279 项等权操作；[Raytrace 前缀账本](work-ray-prefix.json) 净增加 38,570 项。这个保守账本没有单列被移除的临时 Row/Rc 操作，也不是并行耗时模型。因此既不能从接管量宣称加速，也不能从等权总数直接换算退化百分比。完整线程扩展性尚未测量。

下一项有证据支撑的优化是让静态能力在缓冲 Entry 之前过滤整类无关查询，并复用现有批次存储，压缩上述准入与缓冲成本；不能仅扩大 worker 或模板数量。

## 验证与复现

- 43 项 integration tests：query_workers、query_receipts、parallel_guards、read_guards、stable_ports、union_digest、repair_ports；另 5 项 work_credit 单元测试通过。
- 新测试逐 Run 比较完整图快照、**有序 binding audit** 和调度记录，涵盖缺失函数、算术溢出/拒绝、可变结果、Eq 结果、复合 key、late input、删除/重建、union，以及未覆盖的构造子枚举。既有 history/receipt 测试同时打开 query workers，验证保留路径。
- 同一最终 release binary 的 off/1/2/4 worker 与旧二进制比较：sum-bits、普通/碰撞短样例共 15 个进程；最终状态及 Run 记录精确一致，短样例有完整阶段快照和有序绑定一致性检查。
- `choice_diagnosis.py` 对 sum-bits 已保存的 native exports 和这次完整输出给出 **status: pass / exit 0**。没有扩大证明规则。sum-bits 的全部中间图快照未重新做 native 比较。
- Raytrace 只执行前 128 个 Run，前缀最终图和每个 Run 的调度/匹配/执行数精确一致。对照前缀为本轮加入 StageSpine 接管之前、关闭 query workers 的同分支实现；完整 sum-bits/fixture 则对照 `efc06d49` 二进制。
- 默认与 all-features runtime `cargo check` 通过；README 的 Cargo compile/run/bench 入口均完成短样例 smoke（bench 一次，未作性能对比）。日志摘要见 [validation.json](validation.json)。`union_digest` 旧测试的 `.collect()` 增加 `Vec<_>` 注解，以消除现有泛型实参推断错误，不改变运行时行为。

以下使用新输出目录。常规源码编译、运行和 bench 入口仍沿用 README 的 Cargo 流程；bench 仅作一次短样例 smoke，不代表性能验收。

```sh
python3 benchmarks/cell-query-workers/prepare_fixture.py tools/cell-compiler/tests/fixtures/cell-point-queries.egg
cargo cell-compile --source tools/cell-compiler/tests/fixtures/cell-point-queries.egg --output out/query-fixture
cargo run --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics -- --program out/query-fixture/program.json --output out/query-fixture-run --local-congruence --query-workers 4 --query-grain 16 --audit-stages
cargo cell-bench --program out/query-fixture/program.json --repeat 1
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test query_workers --test query_receipts --test parallel_guards --test read_guards --test stable_ports --test union_digest --test repair_ports
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --lib work_credit
```

`check.py CANDIDATE BASELINE SUM_PROGRAM FIXTURE_PROGRAM SAVED_SEMANTIC OUTPUT` 复现 15 进程检查并运行指定语义验收脚本。`SAVED_SEMANTIC` 需包含 `native-source.json`、`native-legacy.json`、`native-values.json`、`sum-legacy`；该脚本只复用，不重跑 native。最终本地证据根为 `out/cell-query-workers/final`。

```sh
python3 benchmarks/marker-handoff/choice_diagnosis.py out/cell-query-workers/final/semantic out/cell-query-workers/final/semantic-acceptance.json
cargo run --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --example query_prefix -- RAYTRACE_PROGRAM PREFIX_OUTPUT 128 4 16
python3 benchmarks/cell-query-workers/collect_results.py CHECK_ROOT PREFIX_BEFORE PREFIX_AFTER RESULTS.json
cargo run --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --example compare_work -- BEFORE_REPORT AFTER_REPORT WORK.json
python3 docs/optimization-catalog/catalog.py check
```
