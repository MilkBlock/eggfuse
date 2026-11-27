"""Budgeted overnight stages. Selection only consumes inner native runs, never outer results."""

import argparse
import hashlib
import json
import os
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean

HERE = Path(__file__).resolve().parent
REPORT = HERE / "run-recall/full-ce-scaling"
BUDGETS = (16, 32, 64, 128, 256)
SEEDS = (71, 113)
lock = threading.Lock()


def cfg(name, **kwargs):
    return dict(name=name, **kwargs)


def grid():
    return [
        cfg("center", arm="C"),
        cfg("local", arm="A"),
        cfg("decoder", arm="B"),
        cfg("layer01", arm="D", encoder_lr=0.1),
        cfg("layer03", arm="D", encoder_lr=0.3),
        *[cfg(f"lr{x:g}", lr=0.001 * x) for x in (0.25, 0.5, 2, 4)],
        *[cfg(f"batch{x:g}", batch=x) for x in (0.5, 2, 4)],
        *[cfg(s, schedule=s) for s in ("linear", "cosine", "warmcos")],
        *[cfg(f"wd{v:g}", wd=v) for v in (0.0001, 0.001, 0.01)],
        *[cfg(f"clip{v:g}", clip=v) for v in (0, 0.5, 1, 5)],
        *[
            cfg(s, sampling=s, block=16)
            for s in ("trajectory", "state", "effect", "mixed", "teacher-self")
        ],
        *[cfg(s, curriculum=s) for s in ("strict", "retain", "adaptive")],
        cfg("limited-states", state_limit=400),
        cfg("limited-targets", target_limit=4),
        cfg("random-init", random_init=True),
        cfg("adam", optimizer="Adam"),
        cfg("beta", betas=[0.85, 0.99]),
        cfg("richer-egg", extra_egg=True),
    ]


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, indent=1))
    tmp.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Campaign:
    def __init__(self, workers, hours):
        self.workers = workers
        self.disk = Path(os.environ["PARTNER_INDEX_OUT"]) / "full-ce-scaling"
        self.log = self.disk / "logs"
        self.log.mkdir(exist_ok=True)
        REPORT.mkdir(exist_ok=True, parents=True)
        self.plan = self.disk / "campaign.json"
        if self.plan.exists():
            self.state = json.loads(self.plan.read_text())
        else:
            # Archive creation is the start of this phase including preparation.
            start = (self.disk / "archive.jsonl").stat().st_birthtime
            self.state = {
                "start": start,
                "end": start + hours * 3600,
                "queue": grid(),
                "groups": {},
                "errors": {},
                "locked": None,
            }
            self.flush()

    def flush(self):
        save(self.plan, self.state)

    def call(self, script, action, tag, **env):
        env = {
            **os.environ,
            **{k: str(v) for k, v in env.items()},
            "CELL_STOP_AT": str(self.state["end"] - 600),
        }
        with (self.log / (tag + ".log")).open("a") as f:
            subprocess.run(
                ["sh", "partner_index_reproduce.sh", script, action],
                env=env,
                stdout=f,
                stderr=subprocess.STDOUT,
                check=True,
            )

    def fit(self, c, s, cap):
        tag = f"{c['name']}-s{s}-t{cap}"
        ck = self.disk / "fits" / (tag + ".json")
        # Reserve enough wall time for native acceptance and a clean final report.
        if not ck.exists() and time.time() > self.state["end"] - 900:
            return None
        if not ck.exists():
            milestones = " ".join(
                str(x)
                for x in (10000, 30000, 100000, 250000, 500000, 1000000)
                if x <= cap
            )
            self.call(
                "scaling_fit.py",
                "train",
                tag,
                CELL_CFG=json.dumps(c),
                CELL_SEED=s,
                CELL_MILESTONES=milestones,
            )
        if not ck.exists():
            return None
        self.call("scaling_eval.py", "evaluate", tag + "-val", CELL_MODEL=tag)
        met = json.loads(ck.read_text())
        result = json.loads(
            (self.disk / "eval" / f"validation-{tag}-T1-U1-N6.json").read_text()
        )
        with lock:
            self.state["groups"][tag] = self.summarize(met, result)
            self.state["errors"].pop(tag, None)
            self.flush()
            self.checkpoint(tag)
            from full_ce_report import report

            report()
        return tag

    def summarize(self, m, r):
        rows = r["runs"]
        by_case = {
            case: mean(x["coverage"] for x in rows if x["case"] == case)
            for case in {x["case"] for x in rows}
        }
        val = r["probes"]
        return dict(
            m,
            weights_sha=sha(self.disk / "fits" / (r["model"] + ".pt")),
            inner_area=by_case,
            val_ce=sum(x["ce"] * x["targets"] for x in val)
            / sum(x["targets"] for x in val),
            free_known_hit=sum(x["known_hits"] for x in val)
            / sum(x["slots"] for x in val),
            **{
                "free_" + g: sum(x["known_hits"] for x in val if x["group"] == g)
                / sum(x["slots"] for x in val if x["group"] == g)
                for g in {x["group"] for x in val}
            },
        )

    def checkpoint(self, tag):
        dest = REPORT / "groups"
        dest.mkdir(exist_ok=True)
        group = dest / (tag + ".json")
        save(group, self.state["groups"][tag])
        subprocess.run(["git", "add", "--", str(group)], check=True)
        staged = subprocess.run(
            ["git", "diff", "--cached", "--quiet", "--", str(group)], check=False
        ).returncode
        if staged:
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "commit",
                    "--only",
                    "-m",
                    f"results(pretraining): record native validation for {tag}",
                    "--",
                    str(group),
                ],
                check=True,
            )

    def stage(self, jobs):
        # Only a worker that is ready for work can start a training run.
        def one(job):
            c, s, cap = job
            tag = f"{c['name']}-s{s}-t{cap}"
            if tag in self.state["groups"]:
                return
            if time.time() > self.state["end"] - 900:
                return
            try:
                self.fit(c, s, cap)
            except Exception as e:
                with lock:
                    self.state["errors"][tag] = str(e)
                    self.flush()
                raise

        with ThreadPoolExecutor(max_workers=self.workers) as workers:
            for f in as_completed([workers.submit(one, j) for j in jobs]):
                f.result()

    def order(self, names, cap, seeds):
        eligible = []
        for name in names:
            gs = [self.state["groups"].get(f"{name}-s{s}-t{cap}") for s in seeds]
            if all(gs):
                # Each program and generation-budget point has equal weight.
                score = mean(mean(g["inner_area"].values()) for g in gs)
                eligible.append((score, name))
        if len(seeds) == 1 or len(eligible) < 2:
            return [name for _, name in sorted(eligible, reverse=True)]
        # Each program votes in its own Coverage scale. Prefer behavior reproduced by both fitting seeds.
        names = [name for _, name in eligible]
        groups = self.state["groups"]
        cases = groups[f"{names[0]}-s{seeds[0]}-t{cap}"]["inner_area"]

        def rank(name, seed, case):
            scores = {
                n: groups[f"{n}-s{seed}-t{cap}"]["inner_area"][case] for n in names
            }
            others = [v for n, v in scores.items() if n != name]
            return sum(
                (v < scores[name]) + 0.5 * (v == scores[name]) for v in others
            ) / len(others)

        robust = [
            (mean(min(rank(n, s, c) for s in seeds) for c in cases), avg, n)
            for avg, n in eligible
        ]
        return [name for _, _, name in sorted(robust, reverse=True)]

    def evaluate_frozen(self, mode, name, **opts):
        if time.time() > self.state["end"] - 90:
            return
        self.call(
            "scaling_eval.py",
            "evaluate",
            mode + "-" + name,
            CELL_MODEL=name,
            CELL_EVAL=mode,
            **opts,
        )

    def run(self):
        configs = grid()
        by = {c["name"]: c for c in configs}
        self.stage([(c, 71, 10000) for c in configs])
        ranking = self.order(by, 10000, [71])
        if not ranking:
            return
        lr_name = next(n for n in ranking if n.startswith("lr") or n == "center")
        layer = next(n for n in ranking if n in ("layer01", "layer03"))
        combo = dict(
            by[layer], name="layer-lr-interaction", lr=by[lr_name].get("lr", 0.001)
        )
        by[combo["name"]] = combo
        candidates = list(
            dict.fromkeys(
                ["center", "local", "layer01", "layer03", combo["name"], *ranking[:3]]
            )
        )
        # Keep two contrasting representation regimes past the short screen.
        for cap in (30000, 100000):
            if cap == 100000:
                ranks = self.order(candidates, 30000, SEEDS)
                layer = next(
                    (
                        n
                        for n in ranks
                        if n in ("layer01", "layer03", "layer-lr-interaction")
                    ),
                    None,
                )
                candidates = list(
                    dict.fromkeys(
                        ["center", "local", *([layer] if layer else []), *ranks[:2]]
                    )
                )
            self.stage([(by[n], s, cap) for n in candidates for s in SEEDS])
        ranked = self.order(candidates, 100000, SEEDS)
        selection_cap = 100000
        if not ranked:
            selection_cap = 30000
            ranked = self.order(by, selection_cap, SEEDS)
        if not ranked:
            return
        candidate = ranked[0]
        curves = self.state["groups"]

        def area(n, s, t):
            return mean(curves[f"{n}-s{s}-t{t}"]["inner_area"].values())

        def egg(s, t):
            return curves[f"{candidate}-s{s}-t{t}"]["inner_area"]["loopfact"]

        stable = (
            selection_cap == 100000
            and all(
                area(candidate, s, 100000) > area(candidate, s, 30000)
                and egg(s, 100000) >= egg(s, 30000)
                for s in SEEDS
            )
            and any(egg(s, 100000) > egg(s, 30000) for s in SEEDS)
        )
        # Precommit the search result before ever evaluating the outer workload.
        bestcap = selection_cap
        if stable:
            # Admit a longer rung only if both seeds and formal tests fit the remaining budget.
            for cap in (250000, 500000, 1000000):
                costs = [
                    curves[f"{candidate}-s{s}-t{bestcap}"]["tokens_per_s"]
                    for s in SEEDS
                ]
                if (cap - bestcap) / min(costs) * 1.2 + 1200 > self.state[
                    "end"
                ] - time.time():
                    break
                self.stage([(by[candidate], s, cap) for s in SEEDS])
                if not self.order([candidate], cap, SEEDS):
                    break
                if not all(
                    area(candidate, s, cap) >= area(candidate, s, bestcap)
                    and egg(s, cap) >= egg(s, bestcap)
                    for s in SEEDS
                ):
                    break
                bestcap = cap
        if not self.state["locked"]:
            self.state["locked"] = {
                "name": candidate,
                "cap": bestcap,
                "stable": stable,
                "outer": "sum-divisors",
                "time": time.time(),
            }
            self.flush()
        chosen = self.state["locked"]
        names = list(
            dict.fromkeys(
                [
                    "sweep",
                    *[
                        f"{n}-s{s}-t{t}"
                        for n, t in (
                            ("center", 100000),
                            ("local", 100000),
                            (chosen["name"], chosen["cap"]),
                        )
                        for s in SEEDS
                    ],
                ]
            )
        )
        names = [
            name
            for name in names
            if name == "sweep" or (self.disk / "fits" / (name + ".pt")).exists()
        ]
        for name in names:
            self.evaluate_frozen("outer", name)
        for name in ("sweep", names[-1]):
            self.evaluate_frozen("intervention", name)
        # Sampling and capacity sweeps use internal validation only.
        for temp in (0.25, 0.5, 0.75, 1, 1.25, 1.5, 2):
            for unique in (0, 1):
                self.evaluate_frozen(
                    "selection", names[-1], CELL_TEMP=temp, CELL_UNIQUE=unique
                )
        for capacity in (4, 12):
            self.evaluate_frozen("selection", names[-1], CELL_SLOTS=capacity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--hours", type=float, default=8)
    args = parser.parse_args()
    campaign = Campaign(args.workers, args.hours)
    try:
        campaign.run()
    finally:
        from full_ce_report import report

        report()
        files = [
            str(REPORT / name)
            for name in (
                "matrix.csv",
                "native.csv",
                "baselines.csv",
                "facts.json",
                "evidence.json",
                "README.md",
                "paired-training.csv",
                "higher-counterfactual.csv",
            )
        ]
        files = [f for f in files if Path(f).is_file()]
        subprocess.run(["git", "add", "--", *files], check=True)
        if (
            subprocess.run(
                ["git", "diff", "--cached", "--quiet", "--", *files], check=False
            ).returncode
            == 1
        ):
            subprocess.run(
                [
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    "commit",
                    "--only",
                    "-m",
                    "results(pretraining): summarize overnight scaling and native controls",
                    "--",
                    *files,
                ],
                check=True,
            )
