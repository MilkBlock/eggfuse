"""Archive checked, complete independent runs; keep paired work and timing distinct."""
from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from shutil import copyfile
from receipt_bake import read, save


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def archive(out, dest, runtime):
    dest.mkdir(exist_ok=True, parents=True)
    for name in ("costs", "ranks", "independent"):
        (dest / name).mkdir(exist_ok=True)
    provenance = {}
    for file in ("rank.pt", "wired.pt", "graph.pt", "fit.json"):
        copyfile(out / file, dest / file)
        provenance[file] = digest(out / file)
    base = Path(__file__).parent / "run-recall"
    for file in (base / "cell-events/template.pt", base / "parameterized-deep-ripsat/event-gnn.pt",
                 out / "catalog.json", runtime):
        provenance[str(file.name)] = digest(file)
    provenance["node_actor_sha256"] = read(base / "parameterized-deep-ripsat/training.json")["root_actor"]
    summary = {}
    for name in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
        cost = read(out / (name + "-cost.json"))
        if not cost["native_batches"] or not all(all(batch["checks"].values()) for batch in cost["native_batches"]):
            raise ValueError("incomplete native counterfactual checks")
        copyfile(out / (name + "-cost.json"), dest / "costs" / (name + ".json"))
        copyfile(out / (name + "-ranking.json"), dest / "ranks" / (name + ".json"))
        if name in ("sum", "dot"):
            continue
        summary[name] = {}
        for arm in ("rank", "wired"):
            runs = []
            for rep in range(2):
                filename = f"{name}-{arm}-{rep}.json"
                r = read(out / filename)
                if r["termination"] != "schedule_end" or not all(r["work"].get(k) for k in (
                        "joint_terminal_scores", "higher_started", "completed_deep")):
                    raise ValueError(f"incomplete rollout {filename}")
                runs.append(r)
                copyfile(out / filename, dest / "independent" / filename)
            first, second = runs
            for k in ("facts", "reference", "state_sha", "paid", "signed_ops", "verdicts", "synchronizations"):
                if first[k] != second[k]:
                    raise ValueError(f"{name} {arm} unstable {k}")
            for k in ("visits", "completed_deep", "joint_terminal_scores", "proven_candidate_positions_skipped"):
                if first["work"][k] != second["work"][k]:
                    raise ValueError(f"{name} {arm} unstable {k}")
            summary[name][arm] = dict(
                facts=first["facts"], reference=first["reference"], paid=first["paid"],
                coverage=first["facts"] / first["reference"], ept=first["ept"],
                eps=[r["eps"] for r in runs], seconds=[r["wall"] for r in runs],
                visits=first["work"]["visits"], completed=first["work"]["completed_deep"],
                state_sha=first["state_sha"],
            )
    save(dest / "summary.json", dict(hashes=provenance, independent=summary))


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("out", "dest", "runtime"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    archive(a.out, a.dest, a.runtime)
