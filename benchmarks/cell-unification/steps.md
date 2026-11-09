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

两项改动合用一次 sum-bits 检查，见 [prefix-check.json](prefix-check.json)：语义 pass、1,428 个 Run 与最终 state 相同，300 项非时间/RSS指标保持；旧 sum-bits artifact 的 22 个编译组件重新生成一致，最小特性编译通过。没有新增性能采样或分配审计。

## 闭合与普通交接共用见证执行

基线 `f672cabb`。删除两套 handoff 字段校验和结果绑定：共同执行器按源 Cell 操作验证实际 receipt、完整当前字段、构造子结果，再写入结果或处理 Set 的 union。Cell frame 提供共同的参数读取和赋值；闭合预检借用输入，保留小型内联 union 队列，全部通过后才消费 ID、提交 union 和计数。普通路径即时提交当前操作；缺失和 stale 计数保持。没有新增匹配状态或反向订阅。

闭合成功/删除回退、三阶段结构交接、显式 union 与 congruence，以及六项 Entry 顺序检查通过。未单独计时。一般效果分派和源 union 的重复 marker 读取继续处理。

## 源 Cell 效果直接执行 union

接续 `92c63be6`。普通 RHS 的效果执行归入 `RhsFrame`，调度器只维护源操作位置和完成边界。union 直接读取手中的源操作数，删除 ownership 分支重新查模板/marker、克隆第二份 union 指令的路径；实际 equality 入队、ownership 请求计数和信号激活语义保持。marker 产物中的旧 union 字段暂留兼容，其静态存储去重属于后续 port plan 整理。

六项 Entry 有序检查、删除失败后不得执行后续 union、无关节点不得放大 repair 两项现有测试，以及最小特性编译通过。没有新增测试或单项计时。

两项改动合做一次 sum-bits 检查，见 [handoff-check.json](handoff-check.json)：语义 pass，1,428 个 Run 与最终 state 相同，300 项非时间/RSS指标保持。共用执行器实际完成 165 个闭合交接，保留 58 次闭合回退和 155 次 stale；不是仅覆盖普通 RHS。ownership union 由上述短 fixture 单独覆盖。本轮没有计时采样或分配审计构建。

## Port program 只保存 Cell 的局部连接

基线 `3e051d5d`。union 已由源 Cell 直接执行，port program 中的 union 操作数及 marker 的 union 位置列表不再有运行时读者。本步删除它们，并从新计划的共享判重中去掉源 union 差异；同一局部连接可供不同源 union 的 Cell 共享。编译时 interner 使用 Rc，删除整份 PortProgram 的深拷贝。源 union 仍按原位置执行，不成为静态 equality 假设。

新 marker/fragment/profile 格式分别为 v5/v2/v2，区分改变后的程序地址；旧 v4/v1/v1 加载时只借用源操作恢复旧编号，发出/校验产物时临时投影旧字段，没有第二套运行时 union 指令。完整字段校验、query class 证书和覆盖范围保持；混合地址版本拒绝加载。

新短用例验证不同 union 共享同一个 Rc，并对照旧地址的逐阶段状态、bindings、union 请求和 native 源程序；现有 typed wiring 校验、八项 query-class/receipt 测试及 Bake 输出检查通过。冻结旧格式程序重新加载、旧 profile 再 Bake 也通过。未测时间。marker 的逐操作覆盖数组继续消除。

## 覆盖范围直接来自共享字段布局

接续 `8f60229c`。删除每个 marker 的 `bodies: Vec<bool>` 和 `active` 副本；操作覆盖由共享 PortProgram 的字段布局判断，是否活跃只在共享程序缓存一次。规则准入、事实激活和 operator 代码准备读取同一份布局。产物里的覆盖字段在序列化时投影生成，现有 v4/v5 证书仍逐项检查；执行期不保留第二个覆盖数组。

共享 union 用例、三个 ownership receipt/源顺序检查、Bake 输出及最小特性编译通过。没有新增测试或单项计时。

两项改动的合并核对见 [port-plan-check.json](port-plan-check.json)。短 fixture 的共享程序 7 → 6、composition shape 10 → 9；实际完成的跨阶段 join 仍为 2，全部 runtime/ownership 工作计数相同，逐 Run 的 state、bindings 与最终 state 相同。冻结旧产物在旧/新 binary 上的 300 项非时间/RSS指标相同，新布局也保持这些工作指标。fixture 包含三条真实观察到的 continuation；为检查地址兼容而全部纳入诊断，生产 ranking 仍正确地不选择这些仅使用一次的片段。

复现入口是 `emit_port_sharing` example（源代码在 `tests/support/port_sharing.rs`）；从其 profile 的全部 `records[].fragment` 构造相应 v1/v2 `ownership_fragments`，重算 checksum，再以 `bake-cell-ownership --query-classes true` 校验和生成证书，使用冻结的旧/新 runtime `--local-congruence --audit-stages` 比较。新规则仍由源 Cell 执行 union；程序数量下降不等于已测得速度提升。

同组只运行一次 sum-bits：语义脚本 pass，300 项工作指标、1,428 个 Run 和最终状态保持。sum-bits 没有替代上面的 ownership 专项检查；本轮没有计时采样或分配审计。

## 共享 Cell 符号与 congruence 求解

基线 `664b4189`。port wiring、局部 union completion 和跨阶段 handoff 共用 `cell_symbols` 的符号分配、literal、等价根和构造子闭包；删除 local-union 与 handoff 两套求解器。闭包借用当前仍有效的构造子 key/result，短 key 使用内联存储，不另存一份事实图。handoff 仅附带原有 key footprint/epoch 观察器，保留条件闭包和 donor 索引失效条件；普通 wiring 不承担这个状态。

port wiring 仍不提前使用源 union，局部 repair 的预测仍生成运行时 equality obligation；handoff 只在原有源屏障关闭 congruence。五项 local-union、四项 handoff 索引/闭包、两个源 union 屏障及删除重建用例通过。库测试编译还发现此前 `slot_fields` 新增借用输入参数后遗留的两处测试调用，补上 `None` 后 sealed-input union 失效检查通过。没有新增计时。

## 从同一源 Cell 扫描符号构造子

接续 `0ac8dde9`。port wiring 和局部 repair 共用 Copy/构造子扫描；各自仅处理不同的剩余源效果（Set incidence 或待验证 union）。短字段保留内联，port wiring 在闭包后投影一次，删除原来的 `ports.clone()`。没有源 union 的 Cell 在建立符号数组前直接跳过局部 repair 分析。局部完成计划删除另一份 union 操作数，原证书只在序列化时借用源操作投影。

handoff donor 索引与闭包使用同一 canonical symbol key，短索引 key 也采用内联存储。五项 local-union、不同 union 共享局部连接、四项 handoff 索引/闭包、多参数 equality 条件及最小特性编译通过；没有新增测试或单项计时。

两项合并核对见 [symbols-check.json](symbols-check.json)：一次 sum-bits 语义 pass，300 项非时间/RSS指标、1,428 个 Run、最终 state 与完整 local-union 证书保持。ownership 短 fixture 的 runtime/ownership 计数、三个 Run 的 state/bindings 和 local-union 证书相同。冻结的旧/新地址格式各 24 个编译组件重新生成一致，附带 port/composition 证书通过原校验。未做计时采样或分配审计；静态存储与重复代码的删除不单独视为速度结论。
## 主线程与 worker 共用稳定端口读取

基线 `61f272de`（冻结 binary 来自相同运行时代码 `05c1fd9a`）。删除 Graph 自己的端口绑定/等价根读取实现，字段读取与 worker guard 共用借用 Cell 组件、稳定节点和 equality 的 ReadView。整行只建立一次读视图，先累计端口读取及 parent probe，最后写回计数；纯标量列不建立视图。condition 仍只查一次组件，不把每个 Eq 条件变成重复的组件查询。

保留 coordinator 的当前 overlay、worker 的冻结快照及端口删除失效；没有复制绑定、建立反向依赖或放松多输入 conjunction。既有共享 guard、有效 union 与快照共存、端口代表变化/删除重建检查和最小特性编译通过。通知后的发布/排队路径仍待合并。

按用户更新的节奏，本项实现提交后运行一次 sum-bits 配对计时；此后每累计约五个实现提交检查实际速度，期间继续相关短检查。证据提交不单独触发一次计时。计时是 standalone Cell CPU，不能表述为 native egglog 性能。

`24c4ae8a` 的检查见 [port-read-results.json](port-read-results.json)：语义 pass，300 项工作指标、1,428 个 Run 和最终 state 保持；端口 fixture 的逐阶段 state/bindings 与全部 runtime、ownership、稳定端口工作计数保持。普通构建采用每组一次预热、七次交错采样，同时重测直接前版与上次计时版本 `ff23dc09`。

相对直接前版，推理配对中位比为 0.976（95% bootstrap 区间 0.908–1.012），进程为 0.996（0.977–1.041）；相对上次计时版本分别为 1.004（0.968–1.028）与 0.998（0.937–1.049）。两项都不足以判定加速或退步，不用独立中位数差值替代配对比较。相对上次版本，setup 配对中位比 0.906（0.819–0.946），但推理及整体收益尚未成立；RSS 中位数约增加 0.72 MiB，分配未另行采样。没有新增 Raytrace 或历史最快配置扫描。

复现计时：`python3 benchmarks/witness-prefix/measure.py benchmarks/cell-unification/port-read-timing-spec.json out/cell-port-reader-unified/timing --repeat 7 --warmups 1`（输出目录须不存在）；核对已有输出：`python3 benchmarks/cell-unification/port-read-check.py out/cell-port-reader-unified benchmarks/cell-unification/port-read-results.json`。语义、目录指标及源运行输出使用上述既有入口生成；冻结 binary 的 SHA 保存在结果中。

## Cell 字段变化共用发布与完成排队

基线 `53bdc930`。删除 `project_owned_ports`、`notify_stable_fields`、`publish_unique_port` 三份提交实现；共享 wiring 激活后由 `propagate_cell_fields` 处理。表示差异仅保留稳定字段无需写回、旧 decoded 字段需要实际替换的分支。发布、query version、change batch 和 key 排队只实现一次；输入发生变化时不再查询无法影响决策的 canonical singleton 桶。

唯一性证明仍检查完整 live domain、pending peer、union batch 和源顺序，不能被上述快路推断替代。其直接发布保留 completion epoch join 与原独立计数；普通结果发布、stable cause 通知及 decoded 未变化早退均保持。实际更新同一个 fact，未添加状态或反向边。

10 项 unique publication、跨阶段 stable/decoded/keyed/local 差分、并行多输入与级联有序检查及最小特性编译通过。已有用例覆盖 hidden peer、旧 union 不得回退新 consumer epoch、删除重建和多个源阶段。上次速度检查后的第 1 个实现提交，本项不单独计时。

## 碰撞完成共用 Cell 效果

接续 `230dbc51`。普通 repair 与 owned canonical completion 共用 hash/精确候选查询；canonical、稳定端口和批量预取结果接入同一个 `complete_cell_collision`，删除各自的 epoch 合并和输出 union 实现，以及两层 port-key 提交包装。最终 visibility、receipt forward、退役与发布仍是原来的共同提交。

没有把出生 hint 当 canonical key 维护。批量路径保留提交时刷新过的实际 result，不能回用旧 row 的输出；非构造子 relation 不发布输出 union。显式 repair Cell 已执行的源 Union 不重复执行，它的 publish 指令调用共同终结效果。候选完整性、源序排队和存活判断不因共享提交而省略。

预取跨 result union 复用、批量 key/result delta 的 merge/visibility/retirement、晚到边界 union、容器回退和重复初始桶的现有短用例通过；最小特性编译通过。上次速度检查后的第 2 个实现提交，不单独计时。

这两项合做一次普通构建 sum-bits 核对，见 [propagation-check.json](propagation-check.json)：语义入口 pass，300 项非时间/RSS指标、1,428 个 Run 与最终 state 保持。1,046 次 equality completion 实际经过共同提交。短 port fixture 的逐阶段状态、binding audit、runtime/ownership/stable-port 工作计数也一致；16 项针对性短测试通过。没有新增计时或 allocation 审计。

复现输出使用冻结 `out/cell-port-reader-unified/runtime-candidate` 作前版，当前源码普通 release 构建作后版，分别运行相同的 `sum/program.json --local-congruence` 与 `port-program.json --local-congruence --audit-stages`，输出保存在 `out/cell-propagation-unified`。沿用 `catalog.py extract` 的工作指标及 `choice_diagnosis.py` 的 semantic 入口，比较上述 Run 字段、完整工作计数和状态摘要；binary/program SHA 与短测试日志 SHA 记录在结果文件。

## 查询、边界条件和唯一性证明共用字段使用索引

基线 `cd20519b`。删除 condition plan 的第二份 `inputs` 目录，以及边界条件/唯一性证明各自的 bounded/unbounded 枚举实现。三者共用借用的 Cell `FieldUses` 视图；普通查询仍能按输出列查询，输入证明只接受输入使用。每个 query position 的一个低位表示输入角色，位置仍占一个 usize，没有扩大每项存储。共享地址只提供潜在使用位置，table、存活、pending 和完整 Eq/标量证明仍在原处执行。

编译字段索引不受最多 16 个条件 site 的界限影响，较大 shape 也按字段直接寻址。未见过的训练 shape 保留完整静态 wiring 扫描；没有为任何实例维护消费者列表。唯一性证明按真实访问数执行既有预算，省掉无关字段后可能证明更多合法实例，不能靠提高预算掩盖成本。

新增 `boundary_indexed_steps`，与剩余 `boundary_uncompiled_steps` 一同进入目录和 Bake 评分。旧报告没有新计数应显示缺失，不能当作零。19 项短检查覆盖条件容量回退、唯一性、未来 class 过滤/训练回退、多输入别名、超大 shape 的并行完成及评分缺项拒绝；最小特性编译通过。相对上次测速是第 3 个实现提交，本步不计时。

本步检查见 [field-uses-check.json](field-uses-check.json)：sum-bits 语义 pass，1,428 个 Run 与最终 state 相同。目录新增两项已有/新成本后，299 项指标值或状态保持，boundary 未编译扫描 1,542 → 0、node lookup 64,493 → 64,347；boundary site 恰减少 146，实际返回候选不变。新增 indexed steps 为 15,777，旧报告缺项，没有把它当零；不能由这些数字推出总成本或速度收益。短 port fixture 的逐阶段 state/bindings 保持。当前普通构建与冻结 `out/cell-propagation-unified/runtime-candidate` 使用同一 sum/port 输入，输出和目录提取保存在 `out/cell-field-uses-unified`；无新增时间或分配采样。

用户追加了后续目标：完成统一重写并逐项确认后，再恢复完整多线程运行，尝试清除非本质阻塞。coverage 中记录了该顺序和独立验收阶段；本步的并行短回归仅用于避免破坏已有语义，不算该后续阶段完成。

## Cell 出生只遍历一次字段布局

基线 `95530d4a`。上一组 sum-bits 安装了 3,739 行、10,122 个稳定端口；此前先 attach signal，再独立遍历同一字段布局构造 PortRef。删除这两套遍历，`initialize_cell_fields` 统一绑定和安装：每行解析一次 frame/shape 的共享端口映射，同一个地址用于绑定及稳定字段。借用两个 Rc 代码句柄以允许修改实例，不新增字段数组或反向索引。

已有 ownership 导入使用同一初始化；之后启用 stable representation 时只投影字段，不重绑 signal、不重复增加 component 的 live-fact 计数。保留别名一致性、训练时真实跨阶段复用检查及原 scalar/port 校验。retire 接口删除未使用的字段参数，存活和 retired port 行为保持。

稳定地址随代表变化/删除重建、跨阶段共享绑定、inactive slot 退休清理、stable/decoded/keyed/local 差分的四项既有短检查及最小特性编译通过。上次测速后的第 4 个实现提交，随下一项集中核对指标与时间。

## native 地址使用共同 Cell 解析

接续 `6bc74cf3`。`signal_is_native` 与 `native_signal` 共用 ID → frame/local slot → PortRef 的地址解析；后者不再通过 `composed_signal/composed_port` 重复查同一 frame。frame → component symbol 的映射也收敛到同一个实现。出生使用上一项已解析的整行映射，无需逐字段再进入解析器。

异 component 检查仍在 native slot 查询之前。地址只表示归属，不代替 equality：`native_signal` 仍验证实际绑定及其当前根，然后才生成带 class 的 signal。保留被删除 producer 的必要地址，直到整个 component 退休；不以地址存在推断事实存活。

多轮 union 后 native alias、retained inactive 候选剔除、五项 query-class 证书/跨阶段/训练回退检查以及最小特性编译通过。至此距上次测速累计 5 个实现提交，下面统一进行普通构建的工作量和速度检查。

## 速度检查发现共享投影的额外调用

五提交检查的首组采样中，`9f767036` 相对 `24c4ae8a` 的推理配对中位比为 1.027，区间 1.020–1.029，不能按速度保持验收。分段重测波动较大，尚不能完全归因；汇编确认 `FieldUses::fact` 在 owned candidates、local candidates 和 union 的三个热点循环中成为独立调用。这是静态调用位置数，不是运行时调用计数。

给这个借用访问器加 inline 提示，使固定的输入/全字段访问模式能在调用点特化，避免每个候选重新传递视图。结构仍是同一实现，没有恢复重复枚举。条件容量回退短检查通过；保留首组和定位采样，修订后重新验证调用与速度。

普通 inline 提示仅消除一个静态调用位置，local candidates 和 union 中仍有调用。改用 `inline(always)` 后，普通 release 汇编中的三个调用位置全部消除。最终 sum-bits 的语义验收通过，1,428 个 Run、最终状态和 302 项工作指标的值/缺失状态与直接前版一致；端口短样例的三个 Run、逐阶段状态和绑定审计一致。

调用消除没有证明速度收益：最后一组相对上次计时版的推理配对中位比为 1.0140，95% 小样本区间 1.0000–1.0444；整进程为 1.0004，区间 0.9854–1.0091。首组出现的回退不能因此宣布消失。保留全部四组采样，速度保持仍待确认，不为获得更好数字反复采样；后续重写继续减少实际冗余，按五个实现提交的节奏复查。
