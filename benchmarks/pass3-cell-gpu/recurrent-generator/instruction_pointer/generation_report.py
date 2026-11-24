"""Export independent-run endpoints, matched cost observations and figures."""

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from statistics import median


def read(p):
    return json.loads(p.read_text())


def write_table(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def load_trials(out):
    sweep = {}
    for archive in sorted(out.glob("rollouts-*.jsonl")):
        for line in archive.read_text().splitlines():
            m = json.loads(line)
            sweep[m["case"], m["arm"], m["threshold"]] = m
    for p in sorted(out.glob("*_*_0.json")):
        m = read(p)
        if "threshold" in m:
            sweep[m["case"], m["arm"], m["threshold"]] = m
    rows = {key: [m] for key, m in sorted(sweep.items())}
    for case in sorted({k[0] for k in rows}):
        items = [g[0] for k, g in rows.items() if k[0] == case]
        path = out / f"rollouts-{case}.jsonl"
        path.write_text(
            "".join(json.dumps(m, separators=(",", ":")) + "\n" for m in items)
        )
        assert items == [json.loads(line) for line in path.read_text().splitlines()]
    for p in sorted(out.glob("paired-*.json")):
        for m in read(p):
            key = (p.stem.removeprefix("paired-"), m["arm"], m["threshold"])
            if key not in rows:
                raise ValueError(f"missing sweep for {key}")
            m0 = rows[key][0]
            for k in ("reference", "coverage", "state_sha", "paid_total", "signed_ops"):
                if m[k] != m0[k]:
                    raise ValueError(f"paired {key} disagrees on {k}")
            rows[key].append(m)
    return rows


def export(out):
    groups = load_trials(out)
    ends = []
    prefix = []
    shadow = []
    samples = defaultdict(set)
    for (case, arm, cut), ms in groups.items():
        m = ms[0]
        paired = ms[1:] or ms
        eps = median(r["eps"] for r in paired)
        ends.append(
            dict(
                case=case,
                arm=arm,
                threshold=cut,
                derived=m["coverage"],
                reference=m["reference"],
                coverage=m["coverage"] / m["reference"],
                paid=m["paid_total"],
                signed=m["signed_ops"],
                visits=m["work"].get("visits", 0),
                ept=m["ept"],
                eps=eps,
                wall=median(r["wall"] for r in paired),
                timing_trials=len(paired),
                pareto=False,
            )
        )
        for o in m["points"]:
            t = o["tokens"]
            elapsed = o["elapsed"]
            prefix.append(
                dict(
                    case=case,
                    arm=arm,
                    threshold=cut,
                    **o,
                    ept=o["signed_ops"] / t if t else 0,
                    eps=o["signed_ops"] / elapsed if elapsed else 0,
                )
            )
            samples[case, o["coverage"]].add(arm)
    for e in ends:
        others = (o for o in ends if o is not e and o["case"] == e["case"])
        axes = ("coverage", "ept", "eps")
        e["pareto"] = not any(
            all(o[k] >= e[k] for k in axes) and any(o[k] > e[k] for k in axes)
            for o in others
        )
    write_table(out / "endpoints.csv", ends)
    write_table(out / "budget-prefixes.csv", prefix)
    # Exact equality in the measured reference-fact count; retain the earliest
    # sampled occurrence per configuration. Different facts can give equal counts.
    matched = {}
    for r in prefix:
        key = (r["case"], r["coverage"], r["arm"], r["threshold"])
        if r["coverage"] and len(samples[key[:2]]) >= 2:
            matched.setdefault(key, r)
    write_table(out / "matched-coverage.csv", list(matched.values()))
    for p in sorted(out.glob("shadow-*.json")):
        for case, s in read(p).items():
            for cut, r in s.items():
                hits = sum(v[0] for v in r["by_run"].values())
                assert hits == r["matched"]
                shadow.append(
                    dict(
                        case=case,
                        arm=p.stem[7:],
                        threshold=cut,
                        runs=r["runs"],
                        hits=hits,
                        teacher=r["reference"],
                        recall=hits / r["reference"] if r["reference"] else 0,
                        proposed=r["proposed"],
                    )
                )
    write_table(out / "frozen.csv", shadow)
    return ends, prefix


def paired_summary(out):
    rows = []
    for f in sorted(out.glob("paired-*.json")):
        case = f.stem[7:]
        groups = defaultdict(dict)
        for r in read(f):
            groups[r["arm"], r["threshold"]][r["repeat"]] = r
        for left, right in (
            (("A", 0), ("trained", 0)),
            (("A", 0), ("B", 0)),
            (("A", 0), ("residual", 0)),
            (("A", 0), ("fixed", 0)),
            (("unranked", 0), ("trained", 0)),
            (("A", -3), ("trained", -3)),
            (("A", -1), ("trained", -3)),
        ):
            a, b = groups[left], groups[right]
            if set(a) != set(range(1, 5)) or set(a) != set(b):
                raise ValueError(f"incomplete pairs for {case} {left} {right}")
            rows.append(
                dict(
                    case=case,
                    baseline=left[0],
                    base_cut=left[1],
                    arm=right[0],
                    cut=right[1],
                    base_derived=a[1]["coverage"],
                    derived=b[1]["coverage"],
                    same_sha=a[1]["state_sha"] == b[1]["state_sha"],
                    base_paid=a[1]["paid_total"],
                    paid=b[1]["paid_total"],
                    base_visits=a[1]["visits"],
                    visits=b[1]["visits"],
                    base_ept=a[1]["ept"],
                    ept=b[1]["ept"],
                    base_eps=median(x["eps"] for x in a.values()),
                    eps=median(x["eps"] for x in b.values()),
                    base_wall=median(x["wall"] for x in a.values()),
                    wall=median(x["wall"] for x in b.values()),
                    faster_pairs=sum(b[i]["wall"] < a[i]["wall"] for i in a),
                )
            )
    write_table(out / "paired-summary.csv", rows)


def figure(out, ends, prefix):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    styles = {
        "A": "#195493",
        "B": "#d55e00",
        "residual": "#be598d",
        "trained": "#008057",
        "fixed": "#776645",
    }
    fig, axes = plt.subplots(2, 3, figsize=(12.2, 7.4), layout="constrained")
    for axs, case in zip(axes, ("fact", "sum-divisors")):
        denom = next(r["reference"] for r in ends if r["case"] == case)
        for arm, color in styles.items():
            rr = [r for r in ends if (r["case"], r["arm"]) == (case, arm)]
            if not rr:
                continue
            axs[0].scatter(
                [r["coverage"] * 100 for r in rr],
                [r["ept"] for r in rr],
                s=32,
                facecolors="none",
                edgecolors=color,
                label=arm,
            )
            axs[1].scatter(
                [r["coverage"] * 100 for r in rr],
                [r["eps"] for r in rr],
                s=32,
                facecolors="none",
                edgecolors=color,
            )
            base = [
                r
                for r in prefix
                if (r["case"], r["arm"], r["threshold"]) == (case, arm, 0)
            ]
            axs[2].plot(
                [p["tokens"] for p in base],
                [100 * p["coverage"] / denom for p in base],
                color=color,
                drawstyle="steps-post",
                lw=1.4,
            )
        for ax in axs:
            ax.grid(alpha=0.15)
        axs[0].set(
            ylabel=case + "   ·   EPT", xlabel="Final coverage (%)", yscale="log"
        )
        axs[1].set(ylabel="Effective ops / second", xlabel="Final coverage (%)")
        axs[2].set(
            ylabel="Observed coverage (%)",
            xlabel="Paid tokens (threshold 0)",
            xscale="symlog",
        )
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.savefig(out / "frontier.pdf")
    plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(12.2, 7.3), layout="constrained")
    for row, case in enumerate(("fact", "sum-divisors")):
        den = next(e["reference"] for e in ends if e["case"] == case)
        for col, (axis, label) in enumerate(
            (
                ("tokens", "Paid tokens"),
                ("visits", "Candidate visits"),
                ("elapsed", "Online seconds"),
            )
        ):
            ax = axes[row, col]
            for arm, cut, style in (
                ("A", 0, "-"),
                ("trained", 0, "-"),
                ("A", -1, "--"),
                ("trained", -3, "--"),
                ("B", -6, ":"),
            ):
                points = [
                    r
                    for r in prefix
                    if (r["case"], r["arm"], r["threshold"]) == (case, arm, cut)
                ]
                ax.step(
                    [p[axis] for p in points],
                    [100 * p["coverage"] / den for p in points],
                    where="post",
                    c=styles[arm],
                    ls=style,
                    lw=1.4,
                    label=f"{arm}  {cut:g}",
                )
            ax.set(xlabel=label)
            if not col:
                ax.set_ylabel(case + "   ·   Coverage (%)")
            ax.grid(alpha=0.15)
    axes[0, 0].legend(fontsize=8, frameon=False)
    fig.savefig(out / "coverage-cost.pdf")
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    args = p.parse_args()
    figure(args.out, *export(args.out))
    paired_summary(args.out)
