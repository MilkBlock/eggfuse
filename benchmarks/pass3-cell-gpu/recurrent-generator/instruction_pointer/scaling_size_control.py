"""Compare nested native-state and target pools, with the same programs, steps and exposure."""

import argparse
import json
import subprocess
import time

from scaling_campaign import REPORT, Campaign, save
from scaling_pool import verified_forks


def run(effects, frequency):
    campaign = Campaign(1, 8)
    dest = REPORT / "size-controls"
    dest.mkdir(exist_ok=True)
    configs = []
    if frequency:
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
            save(evidence, group)
            subprocess.run(["git", "add", "--", str(evidence)], check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "commit",
                    "--only",
                    "-m",
                    f"results(pretraining): validate nested native corpus {tag}",
                    "--",
                    str(evidence),
                ],
                check=True,
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--effects", action="store_true")
    parser.add_argument("--frequency", action="store_true")
    options = parser.parse_args()
    run(options.effects, options.frequency)
