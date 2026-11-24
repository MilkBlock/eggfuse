"""Check matched graphs and costs, then compact the original execution records."""

import argparse, csv, json
from collections import defaultdict
from pathlib import Path
from statistics import median
from tempfile import NamedTemporaryFile


def table(path, rows):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def collect(out):
    path = out / "executions.jsonl"
    rows = {}
    if path.exists():
        with path.open() as stream:
            rows.update(map(json.loads, stream))
    for pattern in ("service-*.json", "higher-*.json", "higher_*.json"):
        for f in out.glob(pattern):
            rows[f.name] = json.loads(f.read_bytes())
    if not rows:
        raise ValueError(f"No execution records in {out}")
    return dict(sorted(rows.items()))


def summarize(out):
    raw = collect(out)
    pfx = []
    pairs = []
    routing = []
    for case in (
        "fact",
        "sum-divisors",
        "cyk801",
        "grammar-benefit-held-deep-11901379",
        "grammar-36719037",
    ):
        records = defaultdict(list)
        for name, d in raw.items():
            if name.startswith("service-") and d["case"] == case:
                assert (
                    d["termination"] == "schedule_end" and d["lost"] == d["extra"] == 0
                )
                assert d["work"].get("deferred_prefixes") == d["work"].get(
                    "serviced_deferred"
                )
                records[d["arm"]].append(d)
        for arm, ms in sorted(records.items()):
            local = {d["rep"]: d for d in records["local"]}
            for m in ms:
                a = local[m["rep"]]
                assert (
                    m["state_sha"] == a["state_sha"]
                    and m["signed_ops"] == a["signed_ops"]
                )
                pairs.append(
                    dict(
                        study="prefix",
                        case=case,
                        arm=arm,
                        rep=m["rep"],
                        control_wall=a["wall"],
                        wall=m["wall"],
                        prefix=m["coverage"],
                    )
                )
            w = ms[0]["work"]
            pfx.append(
                dict(
                    case=case,
                    arm=arm,
                    facts=ms[0]["coverage"],
                    den=ms[0]["den"],
                    tokens=ms[0]["paid"],
                    ops=ms[0]["signed_ops"],
                    visits=w["visits"],
                    posting_positions=w["traversed_positions"],
                    fine_queries=w.get("fine_lookups", 0),
                    ept=ms[0]["ept"],
                    eps=median(m["eps"] for m in ms),
                    wall=median(m["wall"] for m in ms),
                    local_wall=median(local[m["rep"]]["wall"] for m in ms),
                    wins=sum(m["wall"] < local[m["rep"]]["wall"] for m in ms),
                    repetitions=len(ms),
                )
            )
    for case in ("fact", "sum-divisors"):
        for transport in ("CCP", "fused"):
            ms = [
                (name, v)
                for name, v in raw.items()
                if name.startswith("higher-" if transport == "CCP" else "higher_")
                and v["case"] == case
            ]
            # Baselines for limited menus are identical primitive generators,
            # recorded in the full-menu pair at the same repeat.
            grp = defaultdict(list)
            base = {}
            for name, v in ms:
                learn = bool(v.get("learned_prefix", False))
                rep = v["repeat"]
                if v["route"] == "atomic":
                    base[rep, learn] = v
                else:
                    cohort = "isolated" if rep >= 8 else "paired"
                    grp[v["route"], v["compiled_layouts"], learn, cohort].append(v)

            def state(v):
                return v.get("state_sha", v.get("sha")), v.get(
                    "signed_ops", v.get("signed")
                )

            for (mode, layouts, learn, cohort), runs in sorted(grp.items()):
                d = runs[0]
                w = d["work"]
                v = d.get("replacement", d.get("generation"))
                prim = [base[m["repeat"], learn] for m in runs]
                for m, a in zip(runs, prim):
                    assert state(m) == state(a)
                    skip = a["work"]["visits"] - m["work"]["visits"]
                    assert skip == m["work"].get("omitted_positions", 0)
                    if transport == "fused":
                        assert a["paid"] - m["paid"] == skip
                    if transport == "CCP":
                        assert (
                            m["paid"] - a["paid"]
                            == m["replacement"].get("lowered_steps", 0) - skip
                        )
                    pairs.append(
                        dict(
                            study=transport,
                            case=case,
                            arm=f"{mode}-{layouts}" + ("-local" if learn else ""),
                            rep=m["repeat"],
                            control_wall=a["wall"],
                            wall=m["wall"],
                            prefix=m.get("derived", m.get("coverage")),
                        )
                    )
                saved = prim[0]["work"]["visits"] - w["visits"]
                acts = v.get("recognized", v.get("higher_issued", 0))
                routing.append(
                    dict(
                        case=case,
                        entry=transport,
                        route=mode,
                        layouts=layouts,
                        local_prefix=learn,
                        cohort=cohort,
                        replicates=len(runs),
                        facts=d.get("derived", d.get("coverage")),
                        tokens=d["paid"],
                        net_tokens_saved=prim[0]["paid"] - d["paid"],
                        ops=state(d)[1],
                        visits=w["visits"],
                        visits_saved=saved,
                        activations=acts,
                        visits_saved_per_activation=saved / max(acts, 1),
                        net_tokens_saved_per_activation=(prim[0]["paid"] - d["paid"])
                        / max(acts, 1),
                        dense_scores=v.get("recognition_scores", 0),
                        direct_logits=v.get("route_logits", 0),
                        null_logits=v.get("use_logits", 0),
                        address_bits=v.get("address_bits", 0),
                        tree_decisions=v.get("tree_decisions", 0),
                        route_seconds=median(
                            m.get("replacement", m.get("generation"))[
                                "recognition_seconds"
                            ]
                            for m in runs
                        ),
                        setup_s=median(m["setup_seconds"] for m in runs),
                        ept=d["ept"],
                        eps=median(m["eps"] for m in runs),
                        wall=median(m["wall"] for m in runs),
                        cold_wall=median(m["wall"] + m["setup_seconds"] for m in runs),
                        atomic_wall=median(a["wall"] for a in prim),
                        wins=sum(m["wall"] < a["wall"] for m, a in zip(runs, prim)),
                    )
                )
    with NamedTemporaryFile("w", dir=out, delete=False) as stream:
        for name, data in raw.items():
            stream.write(json.dumps([name, data], separators=(",", ":")) + "\n")
    Path(stream.name).replace(out / "executions.jsonl")
    table(out / "prefix.csv", pfx)
    table(out / "routing.csv", routing)
    table(out / "pairs.csv", pairs)


def figure(out):
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    colors = dict(full="black", direct="#225ea8", sparse="#2ca25f", tree="#a7415b")
    fig, axes = plt.subplots(1, 2, figsize=(8, 3.4), layout="constrained")
    for ax, case in zip(axes, ("fact", "sum-divisors")):
        data = json.loads((out / f"router-recall-{case}.json").read_bytes())
        for arm, color in colors.items():
            sub = [v for v in data if v["arm"] == arm]
            ax.plot(
                [v["layouts"] for v in sub],
                [v["hits"]["any"] / v["positives"]["any"] for v in sub],
                "o-",
                label=arm,
                color=color,
            )
        ax.set(title=case, xlabel="Eligible Bake layouts", ylim=(0, 1))
        ax.yaxis.set_major_formatter(PercentFormatter(1))
        ax.grid(alpha=0.2)
    axes[0].set_ylabel("Known activation recall")
    axes[1].legend(frameon=False)
    fig.savefig(out / "activation-recall.pdf")
    plt.close(fig)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("out", type=Path)
    p.add_argument("--plot", action="store_true")
    a = p.parse_args()
    summarize(a.out)
    if a.plot:
        figure(a.out)
