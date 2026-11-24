"""Summarize completed executions and check which work was really replaced."""

import argparse
import csv
import json
from pathlib import Path
from statistics import median


def read(path):
    return json.loads(path.read_bytes())


def csv_file(path, rows):
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def summarize(out):
    reach = []
    pairs = []
    for fn in sorted(out.glob("reach-*.json")):
        m = read(fn)
        reach.append(
            dict(
                case=m["case"],
                arm=m["arm"],
                repeat=m["repeat"],
                termination=m["termination"],
                runs=m["runs"],
                reference=m["reference"],
                derived=m["derived"],
                extra=m["extra"],
                missing=m["missing"],
                paid=m["paid"],
                ops=m["signed_ops"],
                visits=m["work"].get("visits", 0),
                lookahead_reads=m["work"].get("lookahead_port_reads", 0),
                ept=m["ept"],
                eps=m["eps"],
                wall=m["wall"],
                sha=m["state_sha"],
            )
        )
    for c in ("fact", "sum-divisors"):
        for i in range(2, 6):
            select = lambda arm: next(
                r for r in reach if (r["case"], r["arm"], r["repeat"]) == (c, arm, i)
            )
            a, b = select("prefix"), select("learned-nolook")
            assert a["sha"] == b["sha"] and a["ops"] == b["ops"]
            assert b["visits"] < a["visits"] and b["paid"] < a["paid"]
            pairs.append(
                dict(
                    case=c,
                    pair=i,
                    open_wall=a["wall"],
                    learned_wall=b["wall"],
                    open_eps=a["eps"],
                    learned_eps=b["eps"],
                    open_ept=a["ept"],
                    learned_ept=b["ept"],
                )
            )
    csv_file(out / "reach.csv", reach)
    csv_file(out / "pairs.csv", pairs)
    rows = []
    for c in ("fact", "sum-divisors"):
        for transport in ("CCP", "layout"):
            get = lambda arm, i: read(
                out
                / (
                    f"higher-{c}-{arm}-{i}.json"
                    if transport == "CCP"
                    else f"higher_{c}_{arm}_{i}.json"
                )
            )
            for i in range(4):
                a, b, k, d = (get(arm, i) for arm in "ABCD")

                def sha(m):
                    return m.get("sha", m.get("state_sha"))

                def ops(m):
                    return m.get("signed", m.get("signed_ops"))

                assert len({(sha(m), ops(m)) for m in (a, b, k, d)}) == 1
                assert d["paid"] == k["paid"]
                saved = b["paid"] - k["paid"]
                assert (
                    saved
                    == d["work"]["omitted_positions"]
                    == a["work"]["visits"] - d["work"]["visits"]
                )
                assert k["work"]["visits"] == a["work"]["visits"]
                if transport == "CCP":
                    assert saved == d["internal_committed"]
                else:
                    assert saved == d["generation"]["verified_steps"]
            for arm in "ABCD":
                ms = [get(arm, i) for i in range(4)]
                cost = ms[0].get("replacement", ms[0].get("generation", {}))
                rows.append(
                    dict(
                        case=c,
                        transport=transport,
                        arm=arm,
                        derived=ms[0].get("coverage", ms[0].get("derived")),
                        paid=ms[0]["paid"],
                        ops=ops(ms[0]),
                        visits=ms[0]["work"]["visits"],
                        recognition_scores=cost.get("recognition_scores", 0),
                        recognition_seconds=median(
                            m.get("replacement", m.get("generation", {})).get(
                                "recognition_seconds", 0
                            )
                            for m in ms
                        ),
                        ept=ms[0]["ept"],
                        eps=median(m["eps"] for m in ms),
                        wall=median(m["wall"] for m in ms),
                        wins_over_A=sum(
                            m["wall"] < get("A", i)["wall"] for i, m in enumerate(ms)
                        ),
                    )
                )
    csv_file(out / "higher.csv", rows)
    for path in out.glob("funnel*.json"):
        m = read(path)
        assert not m["fork_errors"] and sum(m["first_loss"].values()) == m["targets"]
    for path in out.glob("oracle-open*.json"):
        m = read(path)
        assert m["exact_endpoint"] and m["derived"] == m["den"]
    for c in ("fact", "sum-divisors"):
        m = read(out / f"higher-{c}-Dunseen-long-0.json")
        assert m["replacement"]["completed_size_3"] > 0
        a = read(out / f"higher-{c}-A-learned-0.json")
        d = read(out / f"higher-{c}-D-learned-0.json")
        assert (a["state_sha"], a["signed_ops"]) == (d["state_sha"], d["signed_ops"])
        assert a["work"]["visits"] - d["work"]["visits"] == d["internal_committed"]


def plot(out):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    with (out / "reach.csv").open() as f:
        rows = list(csv.DictReader(f))
    labels = {
        "A": "A",
        "terminal": "Open final",
        "relaxed": "Prefix cutoff -1",
        "learned": "Learned + context",
        "learned-nolook": "Learned, local",
        "prefix": "Open prefixes",
    }
    colors = plt.get_cmap("tab10").colors
    fig, axes = plt.subplots(
        2, 2, figsize=(8.4, 5.8), sharey="row", layout="constrained"
    )
    for axrow, case in zip(axes, ("fact", "sum-divisors")):
        for ax, metric in zip(axrow, ("paid", "visits")):
            for (arm, label), color in zip(labels.items(), colors):
                row = next(
                    r
                    for r in rows
                    if r["case"] == case and r["arm"] == arm and r["repeat"] == "0"
                )
                ax.scatter(
                    int(row[metric]),
                    int(row["derived"]) / int(row["reference"]),
                    label=label,
                    color=color,
                    s=58,
                    alpha=0.85,
                )
            ax.set_xscale("log")
            ax.yaxis.set_major_formatter(PercentFormatter(1))
            ax.set_xlabel("Paid tokens" if metric == "paid" else "Candidate visits")
            ax.grid(alpha=0.2)
        axrow[0].set_ylabel(case + " · fact coverage")
    fig.legend(
        *axes[0, 0].get_legend_handles_labels(),
        loc="outside upper center",
        ncols=3,
        frameon=False,
    )
    fig.savefig(out / "reach-cost.pdf")
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--plot", action="store_true")
    args = p.parse_args()
    summarize(args.out)
    if args.plot:
        plot(args.out)
