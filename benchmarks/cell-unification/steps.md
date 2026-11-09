# Cell 统一的小步记录

对象为 standalone Cell CPU。按用户更新后的要求，小步复用现有针对性检查；一组结构改动结束后再集中核对常用指标和速度。

## 闭合交接的字段读取

基线 `ff23dc09`。删除闭合 handoff 的整宽 key 数组和逐操作 key 分配；预检直接比较实际字段。临时 Cell 只拥有原本的计算结果槽，借用匹配输入，与普通/局部 Cell 共用字段读取。边界确需 key 时才构造，覆盖内仍直接发布 receipt。删除 `local_key` 和分立的 `capture_step/capture_keys`，统一调用 `complete`。

保持原来的全部预检、成功后才消费 Cell ID 和排队 union、失败后从源 RHS 回退。待发布输出不提前可见；只排队 union，不在边界读键前应用它。

检查：现有闭合成功/删除后回退、结构性跨三阶段、局部首次 miss 提升及六项 Entry 发布测试通过；Entry 检查包含有序 RHS/write/resume-root。没有新增计时或全量测试。key 存储路径已删除；尚不将它记为实测速度收益。

## 单写完成接入共同 Cell 路径

接续 `e4a4810d`。删除独立 `capture_write`；普通、局部、闭合和单写 RHS 共用 `complete` 的历史捕获、源顺序和发布逻辑。`CompletedEffects` 只抽象存储：单写携带内联的一个实际引用，其他 Cell 使用共享槽。静态分派保留单写无数组、无收据计划分配的形式；结构性观察器也读取同一接口。未合并效果执行器和 merge 解释器。

已有六项 Entry、有函数写入的 register 计划、无匹配 Entry 的 producer receipt 检查通过；最小特性编译通过。两项重写合用一次普通构建 sum-bits 检查：语义脚本 pass，1,428 个 Run 和最终状态相同，目录的 300 个非时间/RSS指标值或状态全部保持，实际执行 1,422 次 single write。见 [completion-check.json](completion-check.json)。没有新增性能采样或分配审计构建；不能据此宣称耗时提升。

## RHS 与 merge 的共同调用执行

基线 `fc5e7883`。原有 `Op::Let` 通过 `cell::evaluate_call` 统一分派、计算和写回；删除普通 RHS 与已编译 merge 各自的 Call 解释。Frame 只提供存储及读写能力：RHS 保留稀疏结果和实际 receipt；merge 仍读取 repair 中的完整可见端口并折叠合法 lattice 冲突。短 merge 的结果和参数改用内联槽，动态构造 miss 直接建立 Cell Slots，省去中间 BTreeMap。纯投影及 scalar merge 快路保持。

八项 merge 检查和六项 Entry 检查通过。新增用例在运行时触发有序构造、相同输入加法和嵌套函数读取，比较独立 AST 控制的逐阶段状态、有序 RHS/write/resume 摘要及其余工作计数，并检查 native 源程序。AST 控制仍供显式关闭编译 merge 的差分/存储测试使用；其他效果和局部计划尚待接入。没有单独计时。
