"""Compare nested native-state and target pools, with the same programs, steps and exposure."""

import argparse
import json
import subprocess
import time

from scaling_campaign import REPORT, SEEDS, Campaign, grid, save
from scaling_pool import verified_forks


def checkpoint(evidence, group):
    save(evidence, group)
    subprocess.run(["git", "add", "--", str(evidence)], check=True)
    subprocess.run(
        [
            "git", "-c", "core.hooksPath=/dev/null", "commit", "--only", "-m",
            f"results(pretraining): validate matched control {evidence.stem}",
            "--", str(evidence),
        ],
        check=True,
    )


def parameter_controls():
    """Complete matched 100K parameter regimes without entering the promotion ranking."""
    campaign = Campaign(1, 8)
    while not (campaign.log / "center-s71-t100000.log").exists():
        if time.time() >= campaign.state["end"] - 1500:
            return
        time.sleep(30)
    campaign.state = json.loads(campaign.plan.read_text())
    configs = {c["name"]: c for c in grid()}
    names = {
        g["config"]["name"] for g in campaign.state["groups"].values()
        if g["exposures"] == 30000
    }
    ranks = campaign.order(names, 30000, SEEDS)
    layer = next((n for n in ranks if n in ("layer01", "layer03", "layer-lr-interaction")), None)
    promoted = {"center", "local", layer, *ranks[:2]}
    dest = REPORT / "size-controls"
    dest.mkdir(exist_ok=True)
    for cap in (10000, 30000, 100000):
        for name in ("decoder", "layer01", "layer03"):
            if name in promoted:
                continue
            for seed in SEEDS:
                tag = f"{name}-s{seed}-t{cap}"
                evidence = dest / (tag + ".json")
                if tag in campaign.state["groups"] or evidence.exists():
                    continue
                if time.time() >= campaign.state["end"] - 1500:
                    return
                cfg = configs[name]
                fit = campaign.disk / "fits" / (tag + ".json")
                if not fit.exists():
                    campaign.call(
                        "scaling_fit.py", "train", tag,
                        CELL_CFG=json.dumps(cfg), CELL_SEED=seed, CELL_MILESTONES=cap,
                    )
                if not fit.exists():
                    return
                campaign.call("scaling_eval.py", "evaluate", tag + "-val", CELL_MODEL=tag)
                val = campaign.disk / "eval" / f"validation-{tag}-T1-U1-N6.json"
                group = campaign.summarize(
                    json.loads(fit.read_text()), json.loads(val.read_text())
                )
                checkpoint(evidence, group)


def run(effects, frequency, curriculum):
    campaign = Campaign(1, 8)
    dest = REPORT / "size-controls"
    dest.mkdir(exist_ok=True)
    configs = []
    if curriculum:
        counts = json.loads((campaign.disk / "inventory.json").read_text())
        for schedule in ("all", "strict", "retain", "adaptive"):
            conf = {
                "name": "mixed" if schedule == "all" else "fixedblock-" + schedule,
                "sampling": "mixed",
                "block": 16,
            }
            if schedule != "all":
                conf["curriculum"] = schedule
            configs.append(
                (
                    conf,
                    counts["counts"]["states"],
                    counts["counts"]["state_named_token"],
                    counts["programs"],
                )
            )
    elif frequency:
        info = json.loads((campaign.disk / "issued-frequency.json").read_text())
        for sampling in ("trajectory", "state"):
            configs.append(
                (
                    {
                        "name": "issued-" + sampling,
                        "executed_frequency": True,
                        "sampling": sampling,
                        "block": 16,
                    },
                    info["states"],
                    info["state_named_tokens"],
                    info["programs"],
                )
            )
    elif effects:
        proven = verified_forks(campaign.disk)
        for sampling in ("state", "effect"):
            configs.append(
                (
                    {
                        "name": f"fork-{sampling}",
                        "verified_forks": True,
                        "sampling": sampling,
                        "block": 16,
                    },
                    len(proven),
                    sum(map(len, proven.values())),
                    len({k[0] for k in proven}),
                )
            )
    else:
        for states, names in ((2, 16), (8, 16), (2, 64), (8, 4)):
            cfg = {
                "name": f"size-{32 * states}x{names}",
                "sampling": "state",
                "block": 16,
                "states_per_program": states,
                "names_per_state": names,
            }
            configs.append((cfg, 32 * states, 32 * states * names, 32))
    for seed in (71, 113):
        for cfg, state_count, name_count, prog_count in configs:
            name = cfg["name"]
            tag = f"{name}-s{seed}-t10000"
            evidence = dest / (tag + ".json")
            if evidence.exists():
                continue
            if time.time() > campaign.state["end"] - 900:
                return
            fit = campaign.disk / "fits" / (tag + ".json")
            if not fit.exists():
                campaign.call(
                    "scaling_fit.py",
                    "train",
                    tag,
                    CELL_CFG=json.dumps(cfg),
                    CELL_SEED=seed,
                    CELL_MILESTONES=10000,
                )
            if not fit.exists():
                return
            campaign.call("scaling_eval.py", "evaluate", tag + "-val", CELL_MODEL=tag)
            r = json.loads(
                (campaign.disk / "eval" / f"validation-{tag}-T1-U1-N6.json").read_text()
            )
            group = campaign.summarize(json.loads(fit.read_text()), r)
            assert (
                group["state_pool"] == state_count
                and group["exposures"] == 10000
                and group["steps"] == 625
            )
            group.update(available_names=name_count, programs=prog_count)
            checkpoint(evidence, group)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--effects", action="store_true")
    parser.add_argument("--frequency", action="store_true")
    parser.add_argument("--curriculum", action="store_true")
    parser.add_argument("--parameters", action="store_true")
    options = parser.parse_args()
    if options.parameters:
        parameter_controls()
    else:
        run(options.effects, options.frequency, options.curriculum)
