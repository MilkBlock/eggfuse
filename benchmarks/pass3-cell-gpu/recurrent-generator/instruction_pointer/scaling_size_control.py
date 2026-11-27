"""Compare nested native-state and target pools, with the same programs, steps and exposure."""

import json
import subprocess
import time

from scaling_campaign import REPORT, Campaign, save


def run():
    campaign = Campaign(1, 8)
    dest = REPORT / "size-controls"
    dest.mkdir(exist_ok=True)
    for seed in (71, 113):
        for states, names in ((2, 16), (8, 16), (2, 64), (8, 4)):
            name = f"size-{32 * states}x{names}"
            tag = f"{name}-s{seed}-t10000"
            evidence = dest / (tag + ".json")
            if evidence.exists():
                continue
            if time.time() > campaign.state["end"] - 900:
                return
            fit = campaign.disk / "fits" / (tag + ".json")
            cfg = {
                "name": name,
                "sampling": "state",
                "block": 16,
                "states_per_program": states,
                "names_per_state": names,
            }
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
                group["state_pool"] == 32 * states
                and group["exposures"] == 10000
                and group["steps"] == 625
            )
            group.update(available_names=32 * states * names, programs=32)
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
    run()
