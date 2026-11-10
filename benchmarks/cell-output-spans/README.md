# Cell 结果按段交给 Shared Entry

对象为 standalone Cell CPU，基线 `33f5fada`。本轮使用短例、保存的 native
sum-bits 导出及 Raytrace 前 128 个 Run，未进行完整速度测量。

## 实际机会与接管

上轮已经让 worker 查询与 RHS 共用输入实例，但 `Programs::complete` 仍对每个
输出读取 operation→receipt 映射、构造 Publication，并再次登记已有输出槽。
sum-bits 的 6,966 个结果、Raytrace 前缀的 33,647 个结果早已直接写在最终发布
arena 中；这里的冗余是逐输出读取和登记，不是深复制或重复构造。

`EffectPlan` 从同一 Cell 的 `static_skip`、`static_sources` 和关系操作推导
保留布局：不被静态跳过的关系操作在成功执行或有效 handoff 后必有实际收据。
effect 别名直接引用这个 donor；不使用当前 Cell/op 伪造构造子的物理地址。
只有原 permanent、Entry-owned 前缀参与接管，运行时还需满足已有可见性条件。

成功 RHS 完成时，先保留原始历史捕获，再一次封存已有输出 span。
已证明输出不再进入旧的逐项来源读取和 `capture_receipt` 路径。
查询别名仍需补齐，缺少见证仍走原 key 路径；可删除或未知边界仍按连续后缀
处理。只有查询别名需要共享例外索引，边界不增加逐项间接寻址。
没有新增实例消费者列表、运行时事实图或全量绑定副本。

发布仍在原 Run / scope 边界进行，使用实际 receipt forwarding，按原 operation
顺序选最终 Entry 赢家，验证存活及可见性。失败的 RHS 丢弃私有输出尾部；
已提交的前序图效果按原语义保留。历史仍观察原始 RHS，不把静态跳过的别名
伪装成执行过的操作。

## 工作量与新增成本

| 同配置前后对照 | sum-bits，4 worker/g64 | Raytrace 前 128 Run，4 worker/g64 |
|---|---:|---:|
| 逐输出来源/登记次数 | 12,574 → 5,608 | 53,839 → 20,192 |
| 保留槽逐项登记次数 | 8,450 → 1,484 | 35,455 → 1,808 |
| 新增整段资格检查 | 6,422 | 31,884 |
| 新增整段封存 | 5,394 | 22,495 |
| 新增查询别名索引读取 | 513 | 103 |
| 上述登记相关等权工作净减少 | 1,603 | 12,812 |
| 新增共享布局字节 | 6,184 | 1,888 |

`cell-span/v1` 报告使用实际 `output_registrations` 和
`cell_output_registrations`，并向 Bake 收取 span 检查、封存和例外索引读取。
历史报告按旧代码每个 captured anchor / retained receipt 各一次登记还原。
`cell_output_sealed_receipts`、`cell_output_receipts` 只表示覆盖，不能再加一次
收益。登记相关净值使用原等权操作模型，不是耗时预测。

实际效果写入、最终发布槽读取、receipt 解析和历史捕获数量均保持。
共享计划会增加分配；完整 allocator 请求对照见 [results.json](results.json)。
sum-bits 四线程 execute 的 alloc/realloc 请求合计增加 22 次，申请字节增加
6,456，峰值在用申请量增加 6,146；inline 一线程合计同样增加 22 次，申请字节
增加 6,344，峰值增加 6,018。这些不是逐实例历史或输出缓冲扩张。
分配诊断每配置一次，计数器会干扰计时，字节表示申请量而非 RSS。

## 验证与边界

相关 runtime、查询 worker、Entry 发布、闭合别名、状态继承、scope/Run 完成及
Bake 计费测试通过。新增回归同时覆盖 query/effect 别名、他处已有构造子、
可退役边界、重复发布及后续 Run；比较有序效果、接续、绑定和每 Run 图。
default/all-features 编译与包含局部 RHS、结构诊断的发布测试通过。

20 个短例配置保持原最终图及 Run 签名，fixture 另比较完整阶段图和有序绑定。
指定 `choice_diagnosis.py` 对保存的 native sum-bits 契约返回 pass / 0。
Raytrace 前缀的图、128 个 Run 和原逻辑计数相同，不据此宣称完整 Raytrace
native 语义或多线程速度已验收。README 的 compile/run/bench 短例入口也通过。

RHS 效果仍按序提交；跨阶段 history 的独立存储、合法发布边界的逐结果处理
和未证明纯度的 worker RHS 扩展仍未消除。本轮只删除已有结果的重复登记。

## 复现

冻结基线的普通 runtime、query_prefix 和 allocation-metrics runtime，分别
命名 `runtime-before`、`query-prefix-before`、`runtime-alloc-before`，并记录
SHA256 到 `OUT/before.json`。本次复用了上轮已验证的同配置基线导出。

```sh
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --test entry_publications --test closed_aliases --test query_workers --test state_inheritance --test query_receipts
cargo test --locked -p eggfuse-cell-compiler --features sparse-cells,view-ports,iterative-bake --lib work_credit
cargo test --locked -p eggfuse-cell-compiler --all-features --test entry_publications --test closed_aliases --test scoped_completion --test state_inheritance
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics --bin eggfuse-cell-runtime --example query_prefix
python3 benchmarks/cell-query-workers/check.py AFTER BEFORE SUM FIXTURE SAVED_SEMANTIC OUT/checks --baseline-commit 33f5fada --extra-fixture MIXED
QUERY_PREFIX_BEFORE RAY OUT/prefix-before 128 4 64
QUERY_PREFIX_AFTER RAY OUT/prefix-after 128 4 64
cargo build --release --locked -p eggfuse-cell-runtime --features sparse-cells,view-ports,storage-metrics,allocation-metrics --bin eggfuse-cell-runtime
ALLOC_BEFORE --program SUM --output OUT/alloc-before-4 --local-congruence --query-workers 4 --query-grain 64
ALLOC_AFTER --program SUM --output OUT/alloc-after-4 --local-congruence --query-workers 4 --query-grain 64
```

将最后两条的 worker / 输出后缀改成 1，保存 inline 诊断。按 collector 中的
文件名保留新旧二进制及导出，然后运行：

```sh
python3 benchmarks/cell-output-spans/collect.py OUT benchmarks/cell-output-spans/results.json
python3 docs/optimization-catalog/catalog.py check
```

生成图、二进制、日志均留在忽略的 `out/cell-output-spans`；仅提交可复现源和
相关文本结果。
