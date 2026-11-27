"""Build the ablation matrix only from finished, natively evaluated checkpoints."""

import csv
import gzip
import pickle
import hashlib
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

from scaling_campaign import REPORT, grid


def read(p):
    return json.loads(p.read_text())


def csv_table(path, rows):
    if not rows:
        return
    with path.open("w") as f:
        out = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        out.writeheader()
        out.writerows(rows)


def report():
    raw = Path(os.environ["PARTNER_INDEX_OUT"]) / "full-ce-scaling"
    REPORT.mkdir(exist_ok=True, parents=True)
    state = read(raw / "campaign.json")
    archive = list(map(json.loads, (raw / "archive.jsonl").read_text().splitlines()))
    inv = read(raw / "inventory.json")
    runs = []
    rawhash = {}
    facts = {}
    rates = defaultdict(list)
    for p in sorted((raw / "eval").glob("*.json")):
        r = read(p)
        rawhash[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()
        for x in r["runs"]:
            graph = x["graph"]
            facts[graph] = x["facts"]
            z = {
                "model": r["model"],
                "phase": r["mode"],
                "case": x["case"],
                "generation_seed": x["seed"],
                "budget": x["cap"],
                "paid": x["paid"],
                "shortfall": x["shortfall"],
                "covered": x["covered"],
                "reference": x["reference"],
                "coverage": x["coverage"],
                "ops": x["ops"],
                "ept": x["ept"],
                "eps": x["eps"],
                "seconds": x["wall"],
                "temperature": r["temperature"],
                "unique": r["unique"],
                "slots": r["slots"],
                "productive_names": x["productive_names"],
                "higher_selected": x["stats"].get("higher_selected", 0),
                "higher_completed": x["stats"].get("higher_completed", 0),
                "statuses": json.dumps(x["statuses"]),
                "graph": graph,
                "response": x["response_sha"],
                "intervened_pages": x["intervention"].get("intervened_pages", 0),
            }
            runs.append(z)
            rates[r["mode"], r["model"], x["case"], x["cap"]].append(z)
    audit = (
        read(raw / "forward-replay.json")
        if (raw / "forward-replay.json").exists()
        else {}
    )
    grouped = dict(state["groups"])
    for path in sorted((REPORT / "size-controls").glob("*.json")):
        grouped[path.stem] = read(path)
    forks = {}
    fork_stats = []
    for label in ("fork-effects", "egg-fork-effects"):
        fp = raw / (label + ".jsonl")
        if not fp.exists():
            continue
        records = [json.loads(line) for line in fp.read_text().splitlines()]
        for r in records:
            forks[r["program"], r["state"]] = {
                (t[0], tuple(map(tuple, t[1]))): sig
                for t, _, _, _, _, _, sig in r["tokens"]
                if sig
            }
        sigs = [[t[-1] for t in r["tokens"] if t[-1]] for r in records]
        fork_stats.append(
            {
                "corpus": label,
                "states": len(records),
                "native_blank_and_singleton_forks": sum(
                    1 + len(r["tokens"]) for r in records
                ),
                "complete_candidates": sum(len(r["tokens"]) for r in records),
                "proven_productive_names": sum(map(len, sigs)),
                "proven_state_effects": sum(len(set(v)) for v in sigs),
            }
        )
    csv_table(REPORT / "native-effect-audit.csv", fork_stats)
    matrix = []
    for tag, g in sorted(grouped.items()):
        c = g["config"]
        member_path = raw / "fits" / (tag + ".seen.gz")
        audited = None
        if member_path.exists():
            with gzip.open(member_path, "rb") as f:
                members = pickle.load(f)
            audited = sum(
                len({group[t] for t in members.get(key, ()) if t in group})
                for key, group in forks.items()
            )
        matrix.append(
            {
                "model": tag,
                "name": c["name"],
                "seed": g["seed"],
                "registered": g["registered"],
                "forward": g.get(
                    "forward_observed",
                    audit.get(tag, {}).get(
                        "parameters", g["connected"] if g["connected"] == 18880 else ""
                    ),
                ),
                "backward": g["connected"],
                "pool_states": g["state_pool"],
                "constrained_pool_names": g.get("available_names", ""),
                "training_states": g["states"],
                "state_named_tokens": g["targets"],
                "state_effect_sets_proven": g["verified_distinct_effects"],
                "offline_fork_state_effects_seen": audited,
                "exposures": g["exposures"],
                "steps": g["steps"],
                "state_batch": c.get("batch", 1),
                "lr": c.get("lr", 0.001),
                "encoder_lr_ratio": c.get("encoder_lr", 1),
                "schedule": c.get("schedule", "constant"),
                "clip": c.get("clip", 2),
                "wd": c.get("wd", 0),
                "seconds": g["seconds"],
                "tokens_s": g["tokens_per_s"],
                "train_ce": g["train_ce"],
                "validation_ce": g["val_ce"],
                "free_known_hit": g["free_known_hit"],
                "free_two": g.get("free_parents_2"),
                "free_multi": g.get("free_parents_3"),
                "free_higher": g.get("free_higher"),
                "inner_loopfact": g["inner_area"]["loopfact"],
                "inner_foundation185510": g["inner_area"]["foundation185510"],
                "inner_foundation185511": g["inner_area"]["foundation185511"],
                "weight_sha": g["weights_sha"],
            }
        )
    csv_table(REPORT / "matrix.csv", matrix)
    csv_table(REPORT / "native.csv", runs)
    baseline = []
    for r in csv.DictReader(
        (REPORT.parent / "continuous-cell-stream/native.csv").open()
    ):
        if (
            r["arm"] in ("iid", "random", "history")
            and r["case"] in ("loopfact", "sum-divisors")
            and r["cap"] in ("16", "32", "64", "128", "256")
        ):
            baseline.append(r)
    csv_table(REPORT / "baselines.csv", baseline)
    (REPORT / "facts.json").write_text(json.dumps(facts, separators=(",", ":")) + "\n")
    (REPORT / "evidence.json").write_text(
        json.dumps(
            {
                "archives": len(archive),
                "archive_generated": sum(r["generated"] for r in archive),
                "archive_omission_occurrences": sum(
                    s[4] for r in archive for s in r["states"]
                ),
                "inventory": inv,
                "rollouts": read(raw / "rollouts.json"),
                "raw_sha": rawhash,
                "locked": state["locked"],
                "errors": state["errors"],
            },
            indent=1,
        )
        + "\n"
    )
    queued = [
        c["name"] for c in grid() if f"{c['name']}-s71-t10000" not in state["groups"]
    ]
    lines = [
        "# 完整 Cell CE 夜间消融",
        "",
        f"截止 {datetime.now().astimezone().isoformat(timespec='minutes')}，已完成原生验证的训练检查点 {len(matrix)} 个，含基线、诊断与采样对照的独立执行记录 {len(runs)} 条。外层配置锁定记录为 {state['locked']}。各程序的实际付费数和预算缺口在 native.csv 中逐行报告。",
        "",
        "## 数据、模型与训练预算",
        "",
        "注册参数 32,874。冻结比较本轮训练曝光 0、训练时间 0。各模型单列前向/反向参数、实际完整 Token 曝光、实测训练墙钟及吞吐。训练计时按进程计，各阶段累计曝光包含重复的完整 Token；嵌套检查点不能相加。原生评估和语料核验耗时另计。历史初始化的全部训练曝光与耗时缺乏完整记录。",
        "",
        f"逐条重放 {len(archive):,} 条归档，共 {sum(r['generated'] for r in archive):,} 枚生成请求；核对 Recipe、发布帧、回执、来源贡献及终图。训练主池 {inv['programs']} 个程序，{inv['counts']['states']:,} 个决策状态，{inv['counts']['state_named_token']:,} 个不同状态与完整具名 Token。具有可跨绑定比较的原生反事实新增效果集合的目标只有 {inv['counts']['effect_identity_known_targets']} 个，对应 {inv['counts']['state_verified_effect_sets']} 个状态与效果集合。其余保留具名监督，效果身份未知。",
        "",
        "训练分配到 fact、历史原生程序、基础与真实反事实。loopfact 和本轮新生成的两个完整基础程序用于内部验证。初测的基础程序 10/11 已被继承权重训练过；初测移入 seen-foundation，排除于超参数选择。对应历史连续程序也排除于内层验证。sum-divisors 为外层留出，仅在配置锁定后执行。继承权重来自既有实验，无法追溯其一生中所有预训练程序。每个训练步仅使用完整 Cell Token CE。局部组反向 4,160，Decoder 组 10,624，端到端与分层组通常 18,880。实际梯度张量清单保存在每组 JSON。",
        "",
        "中心为 AdamW、学习率 0.001、衰减 0、梯度裁剪 2，每步一个真实状态内抽到的完整目标集合。半批量将同一集合依次拆成两次更新；2/4 倍累积多个状态再更新。调度在预设曝光档位重启，分层倍率只作用于 Decoder 组以外的现有可训练参数。随机初始化使用同架构的原生 reset_parameters。小/大上下文分档综合同类型域、目录、父数、有效目标数、内部步数、回执数及 epoch。自适应课程用内部基础程序自由生成探针调整保留比例。",
        "",
        "## 原生验证与预算",
        "",
        "每个训练配置按 16、32、64、128、256 枚付费请求上限，在三个内部程序独立执行，每项使用生成种子 193 和 307。每程序的选择分数为五个预算的 Coverage 均值；再跨程序取均值。固定退出可能提前结束。10K 初筛按三程序均值。在双训练种子的 30K、100K 阶段，分别计算各程序的候选相对名次，同一程序取两个训练种子中较差的名次，再跨程序平均。推进超过 100K 还要求两种训练种子的三程序平均 Coverage 都提高，且 loopfact 的两条曲线均不回退、至少一条提高。训练与生成种子分别报告。独立计时受并行训练影响，跨配置 EPS 差距需结合计时复核。",
        "",
        "| 检查点 | 曝光 | 状态 | 完整目标 | 训练秒 | Train CE | Val CE | loopfact 命中事实 @256 | 两个基础程序平均 Coverage（全预算） |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for g in matrix:
        r = rates["validation", g["model"], "loopfact", 256]
        lines.append(
            f"| {g['model']} | {g['exposures']:,} | {g['training_states']} | {g['state_named_tokens']} | {g['seconds']:.1f} | {g['train_ce']:.3f} | {g['validation_ce']:.3f} | {mean(x['covered'] for x in r):.1f} | {(g['inner_foundation185510'] + g['inner_foundation185511']) / 2:.1%} |"
        )
    lines += [
        "",
        "## 外层与诊断",
        "",
        "外层仅汇报锁定后的自主执行。失活窗口干预在单独的离线组中进行；保留固定运行和发布，只有构造域非空、启用原生触发检查且每个可构造根均失活才跳过。该组的成本和 Coverage 不进入正式神经执行成绩。归档的因子化随机与历史高召回 Stream 保留原生计费口径及实际付费数。完整终图与命中集合可通过图摘要查找。",
        "",
        "| 方法 | 程序 | 预算 | 实付 | 覆盖事实 | EPT | EPS |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for (mode, model, case, cap), rs in sorted(rates.items()):
        if mode not in ("outer", "intervention", "inner-intervention") or cap != 256:
            continue
        lines.append(
            f"| {mode} {model} | {case} | {cap} | {mean(x['paid'] for x in rs):.1f} | {mean(x['covered'] for x in rs):.1f} | {mean(x['ept'] for x in rs):.3f} | {mean(x['eps'] for x in rs):.1f} |"
        )
    lines += [
        "",
        "## 数据与复现",
        "",
        "每次权重和原始逐预算执行文件保存在移动盘 conditional-value/full-ce-scaling 下。matrix.csv 给出消融矩阵，native.csv 给出逐次正式与诊断数据，baselines.csv 保留原始历史对照，evidence.json 保存原始文件校验和。每组权重有 SHA-256。未核验的自由生成只计为未命中已知目标。冻结探针的命中率是下界，不同具名引用也可能实现同一效果。",
        "",
        f"10K 筛选尚未完成的配置：{', '.join(queued) or '无'}。训练每档的继续条件、队列、运行状态与离线干预见 scaling_campaign.py 及移动盘 campaign.json。",
        "",
        "复现时设置 ARTIFACT_ROOT、PARTNER_INDEX_OUT、CELL_DATA、CELL_REPLAY、CELL_COMPILER、PYTHON 后运行 `sh full_ce_reproduce.sh`。",
    ]
    paired = []
    for g in matrix:
        base = state["groups"].get(f"center-s{g['seed']}-t{g['exposures']}")
        if not base or g["name"] == "center":
            continue
        gs = grouped[g["model"]]
        paired.append(
            {
                "config": g["name"],
                "seed": g["seed"],
                "exposures": g["exposures"],
                "validation_ce_delta": g["validation_ce"] - base["val_ce"],
                "loopfact_delta": g["inner_loopfact"] - base["inner_area"]["loopfact"],
                "foundation185510_delta": g["inner_foundation185510"]
                - base["inner_area"]["foundation185510"],
                "foundation185511_delta": g["inner_foundation185511"]
                - base["inner_area"]["foundation185511"],
                "free_two_delta": gs.get("free_parents_2", 0)
                - base.get("free_parents_2", 0),
                "free_multi_delta": gs.get("free_parents_3", 0)
                - base.get("free_parents_3", 0),
            }
        )
    csv_table(REPORT / "paired-training.csv", paired)
    latest = {}
    for g in matrix:
        k = g["name"], g["seed"]
        if k not in latest or g["exposures"] > latest[k]["exposures"]:
            latest[k] = g
    lines.extend(
        [
            "",
            "## 对照归因",
            "",
            f"已验收 {len(latest)} 个独立配置与训练种子组合。每条训练曲线只取最大已验收曝光后合计 {sum(g['exposures'] for g in latest.values()):,} 枚完整 Token，按进程合计 {sum(g['seconds'] for g in latest.values()) / 3600:.2f} 小时。",
            "",
        ]
    )
    ce_only = [
        p["config"]
        for p in paired
        if p["exposures"] == 10000
        and p["seed"] == 71
        and p["validation_ce_delta"] < 0
        and mean(
            [
                p["loopfact_delta"],
                p["foundation185510_delta"],
                p["foundation185511_delta"],
            ]
        )
        <= 0
    ]
    lines.append(
        "在 10K 单种子筛选中，验证 CE 优于中心、但三程序平均预算 Coverage 没有提高的配置为 "
        + ("、".join(ce_only) or "目前未观察到")
        + "。这仅是本次筛选中的配对描述。"
    )
    stable = []
    for name, cap in sorted({(p["config"], p["exposures"]) for p in paired}):
        ps = [p for p in paired if p["config"] == name and p["exposures"] == cap]
        if len({p["seed"] for p in ps}) >= 2 and all(
            min(
                p[k]
                for k in (
                    "loopfact_delta",
                    "foundation185510_delta",
                    "foundation185511_delta",
                )
            )
            > 0
            for p in ps
        ):
            stable.append(f"{name}@{cap}")
    lines.append(
        "在两个训练种子、三个内部程序各自都胜过同预算端到端中心的配置为 "
        + ("、".join(stable) or "尚无")
        + "。paired-training.csv 保留所有差值，包括基础二父、多父已知目标自由生成命中下降的配置。容量保持 32 维。"
    )
    lines.extend(
        [
            "",
            "温度应用于每次因子化神经选择的条件分布；页内不放回仅排除同一个完整具名 Token。native.csv 的 slots 表示 Run 中分给两页的生成槽数，改变该数会改变单次提交宽度。独立原生会话的纯工程并行容量和同轨迹吞吐对照见相邻 incremental-foundation/batch.csv。",
            "",
        ]
    )
    if state["locked"]:
        best = state["locked"]
        lines.append(
            f"内部验证锁定 {best['name']}，单模型曝光 {best['cap']:,}。适用范围为当前训练池、固定生成、固定退出及预算。外层独立结果在上表和 native.csv 中单列。"
        )
    skills_path = raw / "higher-counterfactual.json"
    if skills_path.exists():
        summaries = []
        for name, ss in read(skills_path).items():
            cases = sorted({x["program"] for x in ss})
            summaries.append(
                {
                    "model": name,
                    "pairs": len(cases),
                    "flips": sum(
                        all(x["wins"] for x in ss if x["program"] == i) for i in cases
                    ),
                    "mean_full_probability": mean(x["full"] for x in ss),
                    "mean_conditional_probability": mean(
                        x["full"] / x["family"] for x in ss if x["family"]
                    ),
                }
            )
        csv_table(REPORT / "higher-counterfactual.csv", summaries)
    lines.extend(
        [
            "",
            "分离状态和目标多样性的补充对照选定同样的 32 个训练程序，每个程序固定抽取 2 或 8 个真实状态，每个状态固定开放 4、16 或 64 个核验具名目标。各组均为 625 次更新，每次 16 枚，池内均匀抽样。比较同为 4,096 个可用具名目标的 64×64 与 256×16，也可在 256 个状态下比较每状态 4 与 16 个目标。该组独立于超参数筛选。",
            "",
            "higher-counterfactual.csv 单列 6 对发布后更换入口时的 Higher 排序翻转、完整目标概率、给定 Higher 家族的条件概率。逐请求重放恢复相关版本、原生回执和规则状态。给定目标概率属于离线诊断，自主发现与完成数量见 native.csv。继承的最近一段触发训练为 8,192 次曝光、512 次更新、5.25 秒，训练过最初的两个基础验证程序。",
        ]
    )
    if fork_stats:
        lines.extend(
            [
                "",
                "## 单请求反事实效果核验",
                "",
                "在同一起点分别执行空分支与单个具名请求，走完原生调度。要求请求被接受、有署名有效操作，且完整导出行集严格增加。保留终图摘要、可见端口、版本、退役及后续发布，才将不同物理引用合并到同一效果。在当前核验条件下未确认的目标保留 Unknown。",
                "",
                "| 训练来源 | 状态 | 空与单请求原生分支 | 完整候选 | 可证明新增的具名目标 | 不同状态与效果 |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for row in fork_stats:
            lines.append("| " + " | ".join(str(v) for v in row.values()) + " |")
        lines.append(
            "fork-state 与 fork-effect 固定相同状态流和曝光，分别均匀采样已核验具名目标和不同效果。旧地址审计的同 Key 建议在 fact 的完整实际批前状态重新执行后才纳入。该对照独立于主筛选。matrix.csv 保留训练当时已知效果数，并另列此次离线核验覆盖到的效果数；两列可能重叠。"
        )
    timing = raw / "paired-native-timing.json"
    if timing.exists():
        timed = read(timing)
        csv_table(
            REPORT / "paired-timing.csv",
            [{k: v for k, v in r.items() if k != "facts"} for r in timed],
        )
        lines.extend(
            [
                "",
                "## 串行交替计时",
                "",
                "固定 256 枚付费上限，两枚生成种子，每种方法按正反序各重复两次。同方法同种子的完整终图、事实、操作和付费数须一致。此表的 EPS 已含推理及原生执行。历史高召回 Stream 沿调度表逐规则访问半朴素单源 anchor，再使用学习过的前缀模型；它作为既有系统对照单列。",
                "",
                "| 方法 | 种子 | 次数 | 命中事实 | 实付 | 墙钟中位秒 [最短, 最长] | EPS 中位数 |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for method, seed in sorted({(r["method"], r["seed"]) for r in timed}):
            sample = [r for r in timed if r["method"] == method and r["seed"] == seed]
            sec = [r["wall"] for r in sample]
            lines.append(
                f"| {method} | {seed} | {len(sample)} | {sample[0]['covered']} | {sample[0]['paid']} | {median(sec):.3f} [{min(sec):.3f}, {max(sec):.3f}] | {median(r['eps'] for r in sample):.1f} |"
            )
    (REPORT / "README.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    report()
