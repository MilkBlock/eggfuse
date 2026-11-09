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

## 局部执行计划直接引用 Cell 操作

接续 `1f4226f3`。删除局部计划的 `ResultUse`、表编号、key 和结果操作数副本；计划只保留操作位置、跳过计数和覆盖信息，执行直接读源 Cell 的 `Op`。字段读取沿用共同 frame 接口，首次 miss 的提升及原 RHS 接续不变。旧产物布局由源 Cell 临时投影生成，不另存第二份指令。

既有局部完成/首次 miss 提升/选择用例通过；冻结 borrowed fixture 的全部编译组件重新生成一致，旧产物正常加载。没有独立计时。尚未统一单写的预编译标量前缀、闭合预检及完整效果调度。

两项改动的合并检查见 [evaluation-check.json](evaluation-check.json)：一次普通构建 sum-bits，语义 pass、1,428 个 Run/最终 state 相同、300 项非时间/RSS指标保持；197 次已编译 merge 调用、194 条 merge 操作确实经过共用执行器。局部计划和 merge 函数读取由上述针对性用例覆盖，不能用 sum-bits 的零读取代替覆盖。最小特性编译通过；没有新增性能/分配审计构建。

## 构造子前缀与局部完成共用执行器

基线 `f887a07f`。删除 `start_constructor_rhs` 和独立 `local_rhs_exec`，统一为 `start_cell`。策略只选择源操作及计数，查找、复用、首次 miss 后保存同一 Cell 和接续位置、完成返回共用实现。源前缀的短 key 使用内联数组，局部路径原有内联形式不变。输入信任、别名计数及收据范围维持原准入；不会为已完成的前缀重复执行效果。

既有局部完成/首次 miss/选择用例、六项 Entry 顺序检查及三阶段结构性交接通过。尚未统一闭合 handoff 的预检与一般效果调度；本步不作耗时声明。

## 单写标量前缀引用源 Cell

接续 `609f76ae`。单写前缀只保留源操作位置，删除独立保存的 primitive 名称、sort 和参数数组；直接通过共同 Cell 调用执行器计算临时 writer frame。PortWrite 的直接整数投影仍由源指令派生，最终写入的规范化 key/value 投影保留。旧 artifact 的 prefix 由源指令投影生成。

带函数写入的 register 用例及六项 Entry 顺序检查通过；前者的整数 key 不能进入 Eq-key PortWrite，确实经过共同标量执行器。没有独立计时。
