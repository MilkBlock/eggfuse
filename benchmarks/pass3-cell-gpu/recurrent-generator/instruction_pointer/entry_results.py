"""Export reproducible catalog, frozen training, native oracle and independent results."""

import argparse
import hashlib
from pathlib import Path
from shutil import copyfile
from receipt_bake import read, save, external
from ripsat_replay import unpack


def report(source, target):
    raw = target / "independent"
    raw.mkdir(parents=True, exist_ok=True)
    for name in (
        "373.json",
        "construction.json",
        "training.json",
        "unseen.json",
        "repairs.json",
        "entry.pt",
    ):
        copyfile(source / name, target / name)
    comp = {}
    for arm, folder in (("entry", source), ("trace", source / "trace-control")):
        d = target / arm
        d.mkdir(exist_ok=True)
        copyfile(folder / "catalog.json", d / "catalog.json")
        units = unpack(read(d / "catalog.json")["layouts"])
        comp[arm] = dict(
            templates=len(units),
            steps=sum(map(len, units)),
            outer=sum(len(external(u)) for u in units),
            steps_after_entry=sum(len(u) - 1 for u in units),
            outer_after_entry=sum(len(external(u)) - len(set(u[0][2])) for u in units),
            programs={},
        )
        if arm == "trace":
            copyfile(folder / "population.json", d / "population.json")
        for n in ("sum", "dot", "fact", "loopfact", "sum-divisors"):
            copyfile(folder / (n + "-oracle.json"), d / (n + "-oracle.json"))
            o = read(d / (n + "-oracle.json"))
            packed = o.pop("packed")
            native = o.pop("native")
            if (
                not all(native["checks"].values())
                or o["internal_requests"] != native["graph"]["issued_steps"]
            ):
                raise ValueError("native scope or signed child count changed")
            o.update(
                ready_templates=len(read(folder / (n + "-occasions.json"))),
                native_batches=native["native_batches"],
            )
            comp[arm]["programs"][n] = o
            if n in ("sum", "dot"):
                continue
            copyfile(folder / (n + "-marginal.json"), d / (n + "-marginal.json"))
            marginal = read(d / (n + "-marginal.json"))
            o.update(
                marginal_visits_removed=marginal["counts"]["removed_terminal_visits"],
                suppressed_b_proposals=marginal["counts"]["suppressed_b_proposals"],
            )
            if not (folder / (n + "-search.json")).exists():
                if arm == "entry":
                    raise ValueError("missing primary paired search measurement")
                o["full_stream_check"] = "not measured"
                continue
            copyfile(folder / (n + "-search.json"), d / (n + "-search.json"))
            s = read(d / (n + "-search.json"))
            if "oracle_event_lookup" not in s:
                raise ValueError("shadow needs separate oracle accounting")
            o.update(
                search_visits_before=s["control"].get("visits", 0),
                search_visits_after=s["specialized"].get("visits", 0),
                suppressed_b_proposals=s["removed_b_proposals"],
            )
    comparison = {}
    for n in ("fact", "loopfact", "sum-divisors"):
        comparison[n] = {}
        for arm in ("B", "frozen", "trained"):
            pairs = []
            for rep in (0, 1):
                name = f"{n}-{arm}-{rep}.json"
                src = source / (f"{n}-0-50.json" if arm == "B" and rep == 0 else name)
                copyfile(src, raw / name)
                pairs.append(read(raw / name))
            a, b = pairs
            for k in (
                "facts",
                "reference",
                "state_sha",
                "paid",
                "proof_paid",
                "verdicts",
                "signed_ops",
                "termination",
                "synchronizations",
            ):
                if a[k] != b[k]:
                    raise ValueError((n, arm, k))
            for k, v in a["work"].items():
                if "seconds" not in k and v != b["work"].get(k):
                    raise ValueError((n, arm, k))
            if a["termination"] != "schedule_end":
                raise ValueError("incomplete independent rollout")
            comparison[n][arm] = dict(
                facts=a["facts"],
                reference=a["reference"],
                sha=a["state_sha"],
                ept=a["ept"],
                eps=[v["eps"] for v in pairs],
                wall=[v["wall"] for v in pairs],
                paid=a["paid"],
                signed_ops=a["signed_ops"],
                synchronizations=a["synchronizations"],
                external_proof_requests=a["proof_paid"]
                - a["work"].get("lowered_steps", 0),
                visits=a["work"]["visits"],
            )
    save(
        target / "summary.json",
        dict(
            compilation=comp,
            independent=comparison,
            checkpoint_sha=hashlib.sha256(
                (target / "entry.pt").read_bytes()
            ).hexdigest(),
        ),
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("target", type=Path)
    a = p.parse_args()
    report(a.source, a.target)
