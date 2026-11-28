"""Build a matched report from saved weights' native ledgers and verified target probes."""

import ast
import csv
import gzip
import hashlib
import json
import math
import os
import pickle
from pathlib import Path
from statistics import mean

ROOT = Path(os.environ["PARTNER_INDEX_OUT"])
OUT = Path("run-recall/matched-learning")
START = "local-s71-t100000"
A = "A-batched/local-s71-t"
B = "matched-end-to-end/full-s71-t"
CAPS = (250000, 500000, 1000000)


def records(kind, name):
    return list(
        csv.DictReader((OUT / (kind + "-" + name.replace("/", "_") + ".csv")).open())
    )


def path(name):
    base = ROOT / ("continuation-exposure" if "/" in name else "full-ce-scaling/fits")
    return base / name


def meta(name):
    return json.loads(path(name).with_suffix(".json").read_text())


def tab(header, rows):
    return "\n".join(
        [
            "| " + " | ".join(map(str, r)) + " |"
            for r in [header, ["---"] * len(header), *rows]
        ]
    )


def write_csv(name, rows):
    with (OUT / (name + ".csv")).open("w", newline="") as f:
        w = csv.DictWriter(f, list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def run():
    models = [START] + [prefix + str(cap) for cap in CAPS for prefix in (A, B)]
    nick = {
        name: (
            "Start"
            if name == START
            else ("A" if name.startswith(A) else "B")
            + str(meta(name)["exposures"] // 1000)
            + "K"
        )
        for name in models
    }
    h = {
        int(r["exposures"]): float(r["entropy"])
        for r in csv.DictReader((OUT / "sampler-entropy.csv").open())
    }
    import torch

    def sampler_state(directory, stem):
        saved = torch.load(directory / (stem + "-resume.pt"), weights_only=False)
        assert saved["progress"][4] == 1_000_000
        return saved["rng"]

    assert sampler_state(path(A + "1000000").parent, "local-s71") == sampler_state(
        path(B + "1000000").parent, "full-s71"
    )
    start = meta(START)
    sizes = []
    groups = []
    for cap in CAPS:
        with (
            gzip.open(str(path(A + str(cap))) + ".seen.gz", "rb") as left,
            gzip.open(str(path(B + str(cap))) + ".seen.gz", "rb") as right,
        ):
            assert pickle.load(left) == pickle.load(right), (
                "training target histories differ"
            )
        x, y = (meta(prefix + str(cap)) for prefix in (A, B))
        for key in (
            "archive_sha",
            "steps",
            "states",
            "targets",
            "exposures",
            "verified_distinct_effects",
            "seed",
        ):
            assert x[key] == y[key], key
    for name in models:
        d = meta(name)
        tok = d["exposures"]
        delta = tok - start["exposures"]
        dur = d["seconds"] - start["seconds"]
        loss = (
            (d["train_ce"] * tok - start["train_ce"] * start["exposures"]) / delta
            if delta
            else None
        )
        sizes.append(
            {
                "model": nick[name],
                "registered": d["registered"],
                "forward": d["forward_observed"],
                "backward": d["connected"],
                "states": d["states"],
                "targets": d["targets"],
                "exposures": tok,
                "steps": d["steps"],
                "cumulative_seconds": d["seconds"],
                "fork_seconds": dur,
                "fork_tokens_s": delta / dur if delta else None,
                "train_ce": d["train_ce"],
                "fork_ce": loss,
                "fork_h": h.get(tok),
                "fork_excess": loss - h[tok] if delta else None,
                "weights": str(path(name).with_suffix(".pt")),
                "sha256": hashlib.sha256(
                    path(name).with_suffix(".pt").read_bytes()
                ).hexdigest(),
            }
        )
        rows = records("sets", name)
        for group in ("all", "1", "2-8", "9+"):
            selected = [r for r in rows if group == "all" or group == r["group"]]
            row = {
                "model": nick[name],
                "group": group,
                "states": len(selected),
                "targets": sum(int(r["k"]) for r in selected),
            }
            for field in (
                "ce",
                "h",
                "excess",
                "known_mass",
                "iid_recall_16",
                "iid_recall_64",
                "iid_recall_256",
                "actual_recall_16",
                "actual_recall_64",
                "actual_recall_256",
            ):
                row[field] = mean(float(r[field]) for r in selected if r[field])
            row["sampled_states"] = sum(bool(r["actual_recall_16"]) for r in selected)
            row["known_mass_cost"] = mean(
                -math.log(float(r["known_mass"])) for r in selected
            )
            row["imbalance_within_known"] = row["excess"] - row["known_mass_cost"]
            assert row["imbalance_within_known"] >= -1e-6
            groups.append(row)
    write_csv("fits", sizes)
    write_csv("validation", groups)
    sections = [
        "# CPU 批量完整 Cell 训练对照",
        "共同起点为 local-s71-t100000。训练种子 71，生成种子 193、307。两个分支沿同一采样流，使用相同 AdamW、LR 0.001、无 weight decay、梯度裁剪 2。A 继续既有优化器，B 保留原参数的优化器矩，新开放参数从零矩开始。逐检查点验证两臂的全部状态与目标集合相等；采样程序独立重放记录顺序摘要。真实执行使用原有固定调度、页内具名请求不放回和原生计费。",
        "## 每个模型的训练规模",
        tab(
            [
                "模型",
                "总/前向/反向参数",
                "状态",
                "具名目标",
                "曝光",
                "更新",
                "累计秒",
                "分叉后秒",
                "分叉 Token/s",
                "分叉 CE−H",
            ],
            [
                [
                    r["model"],
                    f"{r['registered']}/{r['forward']}/{r['backward']}",
                    r["states"],
                    r["targets"],
                    r["exposures"],
                    r["steps"],
                    round(r["cumulative_seconds"], 1),
                    round(r["fork_seconds"], 1),
                    round(r["fork_tokens_s"] or 0),
                    round(r["fork_excess"], 4) if r["fork_excess"] is not None else "—",
                ]
                for r in sizes
            ],
        ),
        "## 冻结验证状态上的集合预测",
        "每个真实状态的已核验具名目标各占 1/K，H(q|s)=ln K。验证结果等权平均状态，CE−H 等于对该监督分布的 KL。未核验计算的有效性未知。训练分叉列按实际目标曝光加权，不能和等状态权重验证直接相减。",
        tab(
            [
                "模型",
                "组",
                "状态/目标",
                "CE",
                "H",
                "CE−H",
                "已知概率质量",
                "召回@16/64/256 IID",
                "实抽页内不放回@16/64/256",
            ],
            [
                [
                    r["model"],
                    r["group"],
                    f"{r['states']}/{r['targets']}",
                    *[f"{r[k]:.3f}" for k in ("ce", "h", "excess", "known_mass")],
                    *[
                        "/".join(
                            f"{100 * r[f'{prefix}_recall_{b}']:.1f}%"
                            for b in (16, 64, 256)
                        )
                        for prefix in ("iid", "actual")
                    ],
                ]
                for r in groups
            ],
        ),
        "IID 是从完整 Token 概率精确求出的预期不同目标召回。实抽使用按状态签名排序后每组至多 12 个固定状态，每个状态两个生成种子。两列的状态构成不同；跨模型采用相同样本。具名监督目标可能语义等价。",
        "## 原生独立执行",
        "表中各数对应 seed 193 / 307。覆盖为实际参考事实数；每个模型和每个种子的 EPT、EPS、原生重复率、事实增减集合与终图摘要详见 native CSV。effects CSV 独立重放付费前缀，记录新增参考事实的不同有符号效果集合，以及无法用参考事实定位的有效计算；完整计算机会总数未知。不同终图时 EPS 仅作轨迹观测。历史 Stream 提前结束时保留实际付费量。",
    ]
    fixed = []
    for name in models:
        train = records("train-probe", name)
        for group in ("all", "1", "2-8", "9+"):
            subset = [r for r in train if group == "all" or r["group"] == group]
            fixed.append(
                {
                    "model": nick[name],
                    "group": group,
                    "states": len(subset),
                    "targets": sum(int(r["k"]) for r in subset),
                    **{
                        k: mean(float(r[k]) for r in subset)
                        for k in ("ce", "h", "excess")
                    },
                }
            )
    write_csv("fixed-training-states", fixed)
    sections.extend(
        [
            "### 相同训练状态上的拟合",
            "共同 100K 起点已经曝光的目标，按目标数分层，各固定抽取 80 个状态。后续检查点分别对完全相同的 240 个状态和标签评分。该诊断与 156 个验证状态的难度和权重不同。",
            tab(
                ["模型", "训练 CE−H", "唯一目标", "2–8 个", "≥9 个"],
                [
                    [
                        nick[name],
                        *[
                            f"{r['excess']:.3f}"
                            for r in fixed
                            if r["model"] == nick[name]
                        ],
                    ]
                    for name in models
                ],
            ),
        ]
    )
    for cap in ("256", "schedule"):
        table = []
        for name in [*models, "random", "history"]:
            rr = [r for r in records("native", name) if r["cap"] == cap]
            for case in dict.fromkeys(r["case"] for r in rr):
                pair = [r for r in rr if r["case"] == case]

                def both(field, fmt, pair=pair):
                    return "/".join(
                        fmt(float(r[field])) if r.get(field) else "失败" for r in pair
                    )

                table.append(
                    [
                        nick.get(name, name),
                        case,
                        both("paid", lambda x: str(int(x))),
                        both("covered", lambda x: str(int(x))),
                        both("coverage", lambda x: f"{100 * x:.2f}%"),
                        both("ept", lambda x: f"{x:.2f}"),
                        both("eps", lambda x: f"{x:.0f}"),
                        both("duplicate_rate", lambda x: f"{100 * x:.1f}%"),
                        "/".join(r.get("same_graph_100k") or "—" for r in pair),
                    ]
                )
        sections.extend(
            [
                "### " + cap,
                tab(
                    [
                        "模型",
                        "程序",
                        "实付",
                        "参考事实",
                        "Coverage",
                        "EPT",
                        "EPS",
                        "重复率",
                        "同100K终图",
                    ],
                    table,
                ),
            ]
        )
    pairs = []
    for exposure in CAPS:
        arms = [
            {
                (r["case"], r["seed"], r["cap"]): r
                for r in records("native", prefix + str(exposure))
            }
            for prefix in (A, B)
        ]
        assert arms[0].keys() == arms[1].keys()
        for key, left in arms[0].items():
            right = arms[1][key]
            pair = {
                "exposures": exposure,
                "case": key[0],
                "seed": key[1],
                "cap": key[2],
                "error": left.get("error") or right.get("error"),
            }
            if not pair["error"]:
                added_a, added_b = [
                    set(ast.literal_eval(r["facts_only_new"])) for r in (left, right)
                ]
                lost_a, lost_b = [
                    set(ast.literal_eval(r["facts_only_100k"])) for r in (left, right)
                ]
                only_a = (added_a - added_b) | (lost_b - lost_a)
                only_b = (added_b - added_a) | (lost_a - lost_b)
                assert len(only_b) - len(only_a) == int(right["covered"]) - int(
                    left["covered"]
                )
                pair.update(
                    equal_graph=left["graph"] == right["graph"],
                    equal_reference_facts=not (only_a or only_b),
                    equal_paid=left["paid"] == right["paid"],
                    facts_only_a=sorted(only_a),
                    facts_only_b=sorted(only_b),
                )
                for k in (
                    "coverage",
                    "ops",
                    "ept",
                    "eps",
                    "duplicate_rate",
                    "productive_names",
                ):
                    pair["delta_b_minus_a_" + k] = float(right[k]) - float(left[k])
            pairs.append(pair)
    with (OUT / "paired-native.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, list(dict.fromkeys(k for r in pairs for k in r)))
        writer.writeheader()
        writer.writerows(pairs)
    observed = {}
    effect_rows = []
    for name in [*models, "random", "history"]:
        for row in records("effects", name):
            if row.get("error"):
                continue
            ids = set(json.loads(row["effect_signatures"]))
            assert len(ids) == int(row["distinct_visible_effects"])
            key = (row["case"], row["seed"])
            observed.setdefault(key, set()).update(ids)
            effect_rows.append((key, ids, row))
    write_csv(
        "observed-effect-recall",
        [
            {
                "model": row["model"],
                "case": key[0],
                "seed": key[1],
                "cap": 256,
                "found": len(ids),
                "observed_union": len(observed[key]),
                "observed_recall": len(ids) / len(observed[key])
                if observed[key]
                else None,
                "unresolved": row["unresolved"],
            }
            for key, ids, row in effect_rows
        ],
    )
    sections.extend(
        [
            "## 付费预算 256 下的不同计算效果",
            "observed-effect-recall.csv 按程序和生成种子，计算每个策略发现的不同可见效果数，除以全部受测策略在同一初始状态和预算观察到的效果并集。不同轨迹能够进入不同状态，多个请求也可能形成等价效果。这是相对已观察效果的发现率，不是对所有可执行机会的精确召回。内部有效操作未形成可识别的新增参考事实时单列 unresolved。",
        ]
    )
    module_rows = []
    for name in models:
        params = records("parameters", name)
        for module in sorted({p["module"] for p in params}):
            group = [p for p in params if p["module"] == module]

            def norm(key, group=group):
                return sum(float(p[key]) ** 2 for p in group) ** 0.5

            module_rows.append(
                {
                    "model": nick[name],
                    "module": module,
                    "count": sum(int(p["count"]) for p in group),
                    "changed": sum(int(p["changed"]) for p in group),
                    "nonzero_probe_grad": sum(int(p["nonzero_grad"]) for p in group),
                    "probe_grad_norm": norm("grad_norm"),
                    "delta_norm": norm("delta_norm"),
                    "relative_delta": norm("delta_norm") / norm("start_norm")
                    if norm("start_norm")
                    else None,
                }
            )
    write_csv("modules", module_rows)
    sections.extend(
        [
            "## 梯度与权重变化",
            "modules.csv 包含各里程碑的模块 L2 梯度、相对 100K 权重位移及发生变化的标量数。梯度取固定的 32 次训练状态抽样，每次对该状态全部目标求平均。从未进入当前探针的路径可能在实际训练中有梯度。下列为 1M 检查点，展示有实际权重变化的模块。",
            tab(
                [
                    "模型",
                    "模块",
                    "变化/总参数",
                    "非零探针梯度数",
                    "梯度 L2",
                    "位移 L2",
                    "相对位移",
                ],
                [
                    [
                        r["model"],
                        r["module"],
                        f"{r['changed']}/{r['count']}",
                        r["nonzero_probe_grad"],
                        f"{r['probe_grad_norm']:.4f}",
                        f"{r['delta_norm']:.3f}",
                        f"{r['relative_delta']:.3f}"
                        if r["relative_delta"] is not None
                        else "—",
                    ]
                    for r in module_rows
                    if r["model"] in ("A1000K", "B1000K") and r["changed"]
                ],
            ),
        ]
    )
    (OUT / "results.md").write_text("\n\n".join(sections) + "\n")


if __name__ == "__main__":
    run()
