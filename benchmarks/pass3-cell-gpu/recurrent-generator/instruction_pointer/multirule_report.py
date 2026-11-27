"""Export compact text results, including per-slot provenance and held-out facts."""

import csv
import hashlib
import json
import pickle
import shutil
from collections import Counter
from pathlib import Path

from completion_context import read, write
from first_parent import records
from partner_index_worlds import args
from recursive_train import folder
from selective_kernel import role_tree


def report(a):
    dest = Path("run-recall/multirule-association")
    dest.mkdir(exist_ok=True)
    rows = []
    audit = []
    facts = {}
    funnel = []
    manifest = {}
    duplicate_runs = {}
    for case in ("sum-divisors", "fact", "loopfact"):
        source = a.out / case
        events = read(source / "audit-0/slots.json")
        duplicate_runs[case] = {
            row["run"] for row in events if row["status"] == "duplicate"
        }
        online_frames = [
            json.loads(line)
            for line in (source / "audit-0/observer.jsonl").read_text().splitlines()
        ]
        replay_frames = [
            json.loads(line)
            for line in (a.out / "forks" / case / "observer").read_text().splitlines()
        ]
        # Offline replay can omit the final terminal notification.
        assert [f for f in online_frames if not f[3]] == [
            f for f in replay_frames if not f[3]
        ]
        admitted = {
            uid: (r, rule, epoch, enabled, dirty)
            for r, uid, rule, epoch, enabled, dirty in (
                map(int, line.split(","))
                for line in (source / "audit-0/admit.csv").read_text().splitlines()
            )
        }
        signed = {x["uid"] for x in events if x["uid"] is not None}
        assert signed == set(admitted)
        requests_seen = set()
        for event in events:
            uid = event["uid"]
            info = admitted.get(uid)
            if info:
                assert info[:3] == (
                    event["run"],
                    event["rule"],
                    event["epoch_at_submit"],
                )
                if event["status"] == "untriggered_rule":
                    assert info[3:] == (1, 0)
            request = (
                event["run"],
                event["rule"],
                tuple(map(tuple, event["refs"] or ())),
            )
            repeated = uid is not None and request in requests_seen
            if uid is not None:
                requests_seen.add(request)
            audit.append(
                dict(
                    case=case,
                    **event,
                    repeated_signed_in_run=repeated,
                    issue_dirty=info[-1] if info else "",
                    check_dirty=info[-2] if info else "",
                )
            )
        counter = Counter(x["status"] for x in events)
        funnel.append(
            {
                "case": case,
                "slots": len(events),
                "paid": len(signed),
                "empty": counter["empty_domain"],
                "empty_dirty": sum(
                    x["dirty"] and x["status"] == "empty_domain" for x in events
                ),
                "stale": sum(
                    x["status"] == "untriggered_rule" and x["dirty"] for x in events
                ),
                "inactive": sum(
                    x["status"] == "untriggered_rule" and not x["dirty"] for x in events
                ),
                "binding": counter["binding"],
                "guard": counter["guard"],
                "watermark": counter["watermark"],
                "duplicates": counter["duplicate"],
                "accepted": counter["accepted"],
                "positive": sum(x["gain"] > 0 for x in events),
                "ops": sum(x["gain"] for x in events),
            }
        )
        for f in sorted(source.glob("*/result.json")):
            r = read(f)
            key = case + "/" + f.parent.name
            facts[key] = r["facts"]
            rows.append(
                {
                    "case": case,
                    "trial": f.parent.name,
                    "arm": r["arm"],
                    "draw": r["draw"],
                    "block": r["block"],
                    "attempts": r["stats"]["attempts"],
                    "empty": r["stats"].get("empty_domain", 0),
                    "paid": r["stats"]["paid"],
                    "accepted": r["receipts"]["accepted"],
                    "joint_slots": r["stats"].get("index_slots", 0),
                    "fallback_slots": r["stats"].get("fallback_slots", 0),
                    "partner_rows_indexed": r["stats"].get("partner_rows_indexed", 0),
                    "index_pages": r["stats"].get("index_pages", 0),
                    "inactive": r["receipts"]["rejected"].get("untriggered_rule", 0),
                    "ops": r["ops"],
                    "covered": r["covered"],
                    "reference": r["reference"],
                    "coverage": r["covered"] / r["reference"],
                    "ept": r["ept"],
                    "eps": r["eps"],
                    "wall": r["wall"],
                    "graph": r["graph"],
                }
            )
        for f in a.out.glob(case + "-ce-*.pt"):
            manifest[f.name] = hashlib.sha256(f.read_bytes()).hexdigest()
    records(dest / "slots.csv", audit)
    records(dest / "funnel.csv", funnel)
    records(dest / "native.csv", rows)
    write(dest / "facts.json", facts)
    write(dest / "weights.json", manifest)
    corpus = []
    for f in sorted((a.out / "corpus").glob("*/examples.pkl")):
        with f.open("rb") as rd:
            xs = pickle.load(rd)
        for x in xs:
            corpus.append(
                {
                    "source": x["case"],
                    "run": x["run"],
                    "rule": x["rid"],
                    "owners": x["owners"],
                    "targets": len(x["g"]),
                    "wake": x["wake"],
                    "versions": x["versions"],
                    "retired": x["retired"],
                    "repair_events": x["repairs"],
                    "previous_native_duplicate": (
                        x["run"] - 1
                        in duplicate_runs[x["case"].removeprefix("rollout-")]
                        if x["case"].startswith("rollout-")
                        else ""
                    ),
                    "sample_support": float(x["features"][3][x["target"]]),
                }
            )
    records(dest / "corpus.csv", corpus)
    programs = {
        case: read(folder(a.data, case) / "program.json")
        for case in ("fact", "loopfact", "sum-divisors")
    }
    with (a.out / "oracle.csv").open() as rd:
        trials = list(csv.DictReader(rd))
    for row in trials:
        schema = programs[row["case"]]["recipe"]["rules"][int(row["rule"])][
            "interface"
        ]["rows"]
        slots = [[c.get("slot") for c in role["columns"]] for role in schema]
        assert len(slots) == int(row["arity"])
        decoder = "no-parents" if not slots else "fallback"
        if len(slots) >= 2:
            try:
                role_tree(slots)
            except ValueError:
                pass
            else:
                decoder = "joint-index"
        row["decoder"] = decoder
    records(dest / "oracle.csv", trials)
    for filename in (
        "curves.json",
        "checkpoints.csv",
        "higher.csv",
        "maintenance.csv",
        "stream.json",
    ):
        shutil.copyfile(a.out / filename, dest / filename)


if __name__ == "__main__":
    report(args())
