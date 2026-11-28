"""Local SwanLab projection of immutable Cell training checkpoints and native evidence."""

import argparse
import csv
import fcntl
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from pathlib import Path

import swanlab

HERE = Path(__file__).resolve().parent
REPORT = HERE / "run-recall"
DEFAULT_LOG = Path.home() / "Library/Application Support/CellFoundation/SwanLab"
DEFAULT_ART = Path("/Volumes/Extreme SSD/eggfuse-experiments/conditional-value")
PROJECT = "CellFoundationModel"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def signature(obj):
    return sha(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode())


def jsonfile(p):
    return json.loads(p.read_text())


def flat_numbers(obj, prefix=""):
    for key, value in obj.items():
        path = prefix + key
        if isinstance(value, dict):
            yield from flat_numbers(value, path + "/")
        elif isinstance(value, (float, int)) and not isinstance(value, bool):
            yield path, value


def provenance(p):
    try:
        return (
            subprocess.check_output(
                ["git", "log", "-1", "--format=%H", "--", str(p)], cwd=HERE, text=True
            ).strip()
            or None
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def config(**items):
    return {k: v for k, v in items.items() if v is not None}


def init_run(logdir, name, settings):
    return swanlab.init(
        project=PROJECT,
        experiment_name=name,
        mode="local",
        logdir=str(logdir),
        config=settings,
        settings={
            "probe": dict.fromkeys(
                (
                    "monitor",
                    "hardware",
                    "runtime",
                    "requirements",
                    "conda",
                    "git",
                    "swanlab",
                ),
                False,
            )
        },
    )


class Sink:
    def __init__(self, root):
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.db = sqlite3.connect(root / "cell-import.sqlite")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS committed (name TEXT, signature TEXT, source TEXT, PRIMARY KEY(name,signature))"
        )

    def has(self, name, sig):
        return (
            self.db.execute(
                "SELECT 1 FROM committed WHERE name=? AND signature=?", (name, sig)
            ).fetchone()
            is not None
        )

    def publish(self, name, sig, settings, series):
        if self.has(name, sig):
            return
        old = self.db.execute(
            "SELECT 1 FROM committed WHERE name=?", (name,)
        ).fetchone()
        display = name if not old else f"{name} rev-{sig[:8]}"
        run = init_run(self.root, display, dict(settings, source_sha256=sig))
        try:
            for step, metrics in series:
                if metrics:
                    run.log(metrics, step=int(step))
            swanlab.finish()
        except BaseException:
            swanlab.finish()
            raise
        with self.db:
            self.db.execute(
                "INSERT INTO committed VALUES(?,?,?)",
                (name, sig, str(settings.get("source", ""))),
            )


@contextmanager
def projection_lock(root):
    root.mkdir(parents=True, exist_ok=True)
    with (root / "cell-import.lock").open("w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield


def fits(sink, art):
    prior = art / "full-ce-scaling" / "fits"
    saved = REPORT / "full-ce-scaling/groups"
    paths = {p.stem: p for p in saved.glob("*.json")}
    paths.update({p.stem: p for p in prior.glob("*-t*.json")})
    cont = art / "continuation-exposure"
    paths.update({p.parent.name + "/" + p.stem: p for p in cont.glob("*/*-t*.json")})
    for name, p in sorted(paths.items(), key=lambda x: ("/" not in x[0], x[0])):
        key = "fit " + name.replace("/", " ")
        raw = p.read_bytes()
        sig = sha(raw)
        if sink.has(key, sig):
            continue
        x = json.loads(raw)
        if not all(k in x for k in ("learning_curve", "exposures", "config")):
            continue
        manifest = (
            REPORT
            / "continuation-exposure/checkpoints"
            / (name.replace("/", "-") + ".json")
            if "/" in name
            else saved / (p.stem + ".json")
        )
        points = {
            r["exposures"]: {
                "train/ce": r["cumulative_train_ce"],
                "train/lr": r["lr"],
                "train/steps": r["steps"],
                "train/tokens": r["exposures"],
                "train/seconds": r["seconds"],
                "train/tokens_per_s": r["exposures"] / r["seconds"],
            }
            for r in x["learning_curve"]
            if r["seconds"] > 0
        }
        last = points.setdefault(x["exposures"], {})
        for k, label in {
            "registered": "parameters/total",
            "forward_observed": "parameters/forward",
            "connected": "parameters/backward",
            "states": "train/states",
            "targets": "train/targets",
            "state_pool": "corpus/states",
            "verified_distinct_effects": "train/verified_effects",
            "exposures": "train/tokens",
            "train_ce": "train/ce",
            "seconds": "train/seconds",
            "steps": "train/steps",
            "tokens_per_s": "train/tokens_per_s",
        }.items():
            if k in x:
                last[label] = x[k]
        weights = p.with_suffix(".pt")
        if not weights.exists():
            weights = prior / (p.stem + ".pt")
        group = name.split("/")[0] if "/" in name else "historical"
        start = cont / group / (p.stem.rsplit("-t", 1)[0] + "-start.json")
        meta = config(
            source=str(p),
            configuration=x["config"],
            seed=x.get("seed"),
            ablation=group,
            data_version=x.get("archive_sha"),
            checkpoint=str(weights) if weights.exists() else None,
            checkpoint_record_commit=provenance(manifest),
            training_git_commit=x.get("training_git_commit"),
            continuation_lineage=jsonfile(start) if start.exists() else None,
        )
        sink.publish(key, sig, meta, sorted(points.items()))


def provenance_rows(curve, full):
    d = defaultdict(dict)
    items = (
        "paid",
        "shortfall",
        "ops",
        "covered_total",
        "new_facts",
        "distinct_positive_names",
        "distinct_visible_effects",
        "higher",
        "higher_selected",
        "coverage",
        "ept",
        "eps",
        "wall",
        "continuation_ept",
        "unresolved_effects",
        "lost_facts",
    )
    for r in curve:
        pre = r["mode"] + "/"
        pts = d[r["budget"]]
        pts.update({pre + k: r[k] for k in items if r.get(k) is not None})
        # The native counts aggregate the whole capped run including its first productive request.
        st = r["statuses"]
        for k in ("binding", "guard", "untriggered_rule"):
            pts[pre + "run_rejected_" + k] = st.get("rejected", {}).get(k, 0)
        for k in ("accepted", "duplicates"):
            pts[pre + "run_" + k] = st.get(k, 0)
    if full:
        r = full["r"]
        q = d[len(full["requests"])]
        q.update(
            {
                "schedule/" + k: r[k]
                for k in ("coverage", "ops", "ept", "eps", "wall", "pending")
            }
        )
        q.update(dict(flat_numbers(r["transport"], "transport/")))
        q.update(dict(flat_numbers(r["stats"], "schedule/")))
        if r.get("native_verify_seconds") is not None:
            q["schedule/native_verify_seconds"] = r["native_verify_seconds"]
        counts = Counter()
        for req in full["requests"]:
            role = "parents_" + str(len(req["refs"]))
            counts[role + "/paid"] += 1
            counts[role + "/accepted"] += req["reply"][1] == 0
            counts[role + "/signed_ops"] += req["ops"]
        q.update(counts)
    return sorted(d.items())


def token_ability(full, primitive):
    contribution = Counter()
    for q in full["requests"]:
        contribution[q["owner"]] += q["ops"]
    counts = Counter()
    for q in full["requests"]:
        uid = q["reply"][0]
        if uid != q["owner"]:
            continue
        kind = "Higher" if q["tid"] >= primitive else "Primitive"
        for tag in (kind, "parents_" + str(len(q["refs"]))):
            counts[tag + "/generated"] += 1
            counts[tag + "/entry_accepted"] += q["reply"][1] == 0
            counts[tag + "/complete_with_work"] += int(
                q["complete"] and contribution[uid] > 0
            )
            counts[tag + "/signed_ops"] += contribution[uid]
    stats = full["r"]["stats"]
    if counts["Primitive/generated"] + counts["Higher/generated"] != stats.get(
        "neural_tokens", 0
    ) or counts["Higher/generated"] != stats.get("higher_selected", 0):
        raise ValueError("neural entries disagree with native Higher accounting")
    for kind in ("Higher", "Primitive"):
        for field in (
            "generated",
            "entry_accepted",
            "complete_with_work",
            "signed_ops",
        ):
            counts.setdefault(kind + "/" + field, 0)
    return dict(counts)


def ability(sink, art, by_model):
    for model, runs in by_model.items():
        if len(runs) != 10:
            continue
        keys = sorted(runs)
        name = "complete Cells " + model
        version = signature([(k, runs[k][0]) for k in keys])
        if sink.has(name, version):
            continue
        cases = sorted({k[0] for k in keys})
        points = defaultdict(dict)
        for (case, seed), (_, counts) in runs.items():
            points[cases.index(case)].update(
                {f"seed_{seed}/" + k: v for k, v in counts.items()}
            )
        sink.publish(
            name,
            version,
            dict(
                source=str(art / "continuation-exposure/native.sqlite"),
                workloads=cases,
                seeds=[193, 307],
                mode="full schedule; unique named token per page",
            ),
            sorted(points.items()),
        )


def native_evidence(sink, art):
    src = art / "continuation-exposure/native.sqlite"
    if not src.exists():
        return
    db = sqlite3.connect(src.as_uri() + "?mode=ro", uri=True)
    try:

        def rows(kind):
            for key, b in db.execute(
                "SELECT key,data FROM evidence WHERE kind=?", (kind,)
            ):
                yield key, json.loads(gzip.decompress(b))

        by_model = defaultdict(dict)
        program_counts = {}
        for _, failure in rows("native_panic"):
            condition = failure["condition"]
            cap = failure["cap"]
            name = f"native failure {condition['model']} {condition['case']} g{condition['seed']} " + (
                "schedule" if cap is None else str(cap)
            ) + (" unique" if condition["unique"] else " iid")
            sink.publish(name, signature(failure),
                         dict(condition, source=str(src), paid_cap=cap, diagnostic=failure["stderr"]),
                         [(0, {"signed_replies_before_failure": len(failure["observed_replies"])})])
        for key, curve in rows("curve"):
            if not curve:
                continue
            r = curve[0]
            meta = {
                k: r[k]
                for k in ("case", "model", "seed", "unique", "program", "weights")
                if k in r
            }
            name = f"native {r['model']} {r['case']} g{r['seed']} " + (
                "unique" if r["unique"] else "iid"
            )
            meta["weights"] = r.get("weights")
            native_condition = {k: v for k, v in meta.items() if v is not None}
            full_key = signature([native_condition, None])
            match = db.execute(
                "SELECT data FROM evidence WHERE kind='trial' AND key=?", (full_key,)
            ).fetchone()
            if not match and not db.execute(
                "SELECT 1 FROM evidence WHERE kind='native_panic' AND key=?", (full_key,)
            ).fetchone():
                continue
            sig = signature([key, sha(match[0]) if match else "native_panic", curve])
            full = json.loads(gzip.decompress(match[0])) if match else None
            if r["unique"] and full:
                case = r["case"]
                if case not in program_counts:
                    sources = [
                        art / "continuation-exposure/worlds" / case / "program.json",
                        Path(os.getenv("CELL_DATA", "/tmp/dfm-local/data"))
                        / case
                        / "program.json",
                    ]
                    for f in sources:
                        if f.exists() and sha(f.read_bytes()) == r["program"]:
                            program_counts[case] = len(jsonfile(f)["templates"])
                            break
                if case in program_counts:
                    by_model[r["model"]][case, r["seed"]] = (
                        full_key,
                        token_ability(full, program_counts[case]),
                    )
            if sink.has(name, sig):
                continue
            sink.publish(
                name,
                sig,
                dict(
                    meta,
                    source=str(src),
                    curve_key=key,
                    full_trial_key=full_key,
                    policy_record_commit=provenance(HERE / "exposure_policy.py"),
                ),
                provenance_rows(curve, full),
            )
        ability(sink, art, by_model)
        for name, v in rows("probes"):
            series = {}
            rr = v["binding"]
            series["validation/ce"] = sum(x["ce"] * x["targets"] for x in rr) / sum(
                x["targets"] for x in rr
            )
            for group in sorted({r["group"] for r in rr}):
                chosen = [x for x in rr if x["group"] == group]
                series["probe/" + group + "_known_hit_rate"] = sum(
                    x["known_hits"] for x in chosen
                ) / sum(x["slots"] for x in chosen)
            series["probe/higher_correct_probability"] = sum(
                z["full"] for z in v["higher"]
            ) / len(v["higher"])
            sink.publish(
                "probe " + name,
                signature(v),
                dict(source=str(src), checkpoint=name),
                [(int(name.rsplit("-t", 1)[1]), series)],
            )
    finally:
        db.close()


def chunks(path):
    current = []
    length = 0
    for line in path.read_text().splitlines(keepends=True):
        if current and length + len(line) > 96000:
            yield "".join(current)
            current, length = [], 0
        current.append(line)
        length += len(line)
    if current:
        yield "".join(current)


def archived_text_complete(sink, name, expected):
    board = sink.root / "runs.swanlab"
    if not board.exists():
        return False
    db = sqlite3.connect(board.as_uri() + "?mode=ro", uri=True)
    try:
        rows = db.execute(
            "SELECT run_id FROM experiment WHERE name=? OR name=? ORDER BY id DESC",
            (name, name + " recovered"),
        )
        for (rid,) in rows:
            archived = {
                sha(p.read_bytes())
                for p in (sink.root / rid / "media/text").glob("*.txt")
            }
            if expected <= archived:
                return True
        return False
    finally:
        db.close()


def archive(sink):
    """Keep heterogeneous historical rows with their original labels and native units."""
    for study in sorted(
        p for p in REPORT.iterdir() if p.is_dir() and p.name != "continuation-exposure"
    ):
        files = sorted(
            p
            for p in study.rglob("*")
            if p.is_file()
            and (
                p.suffix in (".csv", ".jsonl")
                or (
                    p.suffix in (".json", ".yaml", ".yml", ".toml")
                    and any(
                        word in p.stem.lower()
                        for word in ("config", "manifest", "hyperparam", "settings")
                    )
                )
            )
        )
        if not files:
            continue
        hashes = {str(p.relative_to(study)): sha(p.read_bytes()) for p in files}
        name = "archive " + study.name
        sig = signature(hashes)
        expected = {sha(text.encode()) for p in files for text in chunks(p)}
        original_name = name
        if sink.has(name, sig):
            if archived_text_complete(sink, name, expected):
                continue
            name += " recovered"

        def pages():
            for idx, p in enumerate(files, 1):
                data = {"archive/file_bytes": p.stat().st_size}
                for j, chunk in enumerate(chunks(p)):
                    data[f"archive/source_part_{j + 1}"] = swanlab.Text(
                        chunk, caption=str(p.relative_to(study))
                    )
                yield idx, data

        sink.publish(
            name,
            sig,
            dict(
                source=str(study),
                files=hashes,
                source_order=list(hashes),
                record_commit=provenance(study),
                step_unit="source-file ordinal",
            ),
            pages(),
        )
        if not archived_text_complete(sink, original_name, expected):
            raise IOError("SwanLab archive failed source content verification: " + name)


def published_curves(sink):
    from statistics import median

    path = REPORT / "full-ce-scaling/native.csv"
    if not path.exists():
        return
    groups = defaultdict(lambda: defaultdict(list))
    fields = ("model", "phase", "case", "temperature", "unique", "slots")
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["budget"].isdigit():
                key = tuple(row[k] for k in fields)
                groups[key][int(row["budget"])].append(row)
    commit = provenance(path)
    for key, budgets in sorted(groups.items()):
        name = "prior native " + " ".join(key)
        sig = signature(budgets)
        if sink.has(name, sig):
            continue

        def series():
            for budget, rs in sorted(budgets.items()):
                vals = {
                    f"total/{k}": median(float(r[k]) for r in rs)
                    for k in (
                        "coverage",
                        "ept",
                        "eps",
                        "paid",
                        "shortfall",
                        "covered",
                        "ops",
                        "seconds",
                        "higher_selected",
                        "higher_completed",
                    )
                    if all(r.get(k, "") != "" for r in rs)
                }
                vals["summary/generation_runs"] = len(rs)
                yield budget, vals

        seeds = sorted({r["generation_seed"] for rs in budgets.values() for r in rs})
        sink.publish(
            name,
            sig,
            dict(zip(fields, key))
            | dict(
                source=str(path),
                record_commit=commit,
                generation_seeds=seeds,
                statistic="median of published rows at each paid budget",
            ),
            series(),
        )

    path = REPORT / "full-ce-scaling/matrix.csv"
    with path.open() as f:
        members = defaultdict(list)
        for r in csv.DictReader(f):
            members[(r["name"], r["seed"])].append(r)
    for (arm, seed), rows in members.items():
        points = []
        for row in sorted(rows, key=lambda v: int(v["exposures"])):
            fields = {
                "exposures": "train/tokens",
                "steps": "train/steps",
                "lr": "train/lr",
                "train_ce": "train/ce",
                "training_states": "train/states",
                "state_named_tokens": "train/targets",
                "tokens_s": "train/tokens_per_s",
                "seconds": "train/seconds",
                "registered": "parameters/total",
                "forward": "parameters/forward",
                "backward": "parameters/backward",
                "frozen_seen_probe_ce": "probe/seen_ce",
            }
            points.append(
                (
                    int(row["exposures"]),
                    {out: float(row[k]) for k, out in fields.items() if row.get(k)},
                )
            )
        sink.publish(
            "prior ablation " + arm + " s" + seed,
            signature(rows),
            dict(source=str(path), seed=seed, configuration=arm, record_commit=commit),
            points,
        )


def journal_worker(path, root, offset=0):
    """A separate SDK process tails one trainer; file I/O and chart rendering stay off the trainer."""
    while not path.exists() or not path.stat().st_size:
        time.sleep(0.2)
    with path.open() as f:
        f.seek(offset)
        header = json.loads(f.readline())
        if header.get("kind") != "config":
            raise ValueError("journal has no configuration record")
        sink = Sink(root)
        name = f"live {path.parent.name} {header['model']}"
        sig = signature([str(path), header])
        if sink.has(name, sig):
            return
        run = init_run(root, name, dict(header, source=str(path)))
        try:
            while True:
                pos = f.tell()
                line = f.readline()
                if line and line.endswith("\n"):
                    x = json.loads(line)
                    if x.get("kind") == "metrics":
                        run.log(x["metrics"], step=x["step"])
                    if x.get("kind") in ("finish", "config"):
                        break
                else:
                    f.seek(pos)
                    try:
                        os.kill(header["pid"], 0)
                    except ProcessLookupError:
                        break
                    time.sleep(1)
        finally:
            swanlab.finish()
        with sink.db:
            sink.db.execute(
                "INSERT OR IGNORE INTO committed VALUES(?,?,?)", (name, sig, str(path))
            )


def scan(root, art, history=False):
    with projection_lock(root):
        sink = Sink(root)
        try:
            fits(sink, art)
            native_evidence(sink, art)
            if history:
                archive(sink)
                published_curves(sink)
        finally:
            sink.db.close()


def main():
    import sys

    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("sync", "watch", "journal", "archive"))
    parser.add_argument(
        "--logdir",
        type=Path,
        default=Path(os.environ.get("CELL_SWANLOG", str(DEFAULT_LOG))),
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=Path(os.environ.get("PARTNER_INDEX_OUT", str(DEFAULT_ART))),
    )
    parser.add_argument("--path", type=Path)
    parser.add_argument("--offset", type=int, default=0)
    a = parser.parse_args()
    if a.command == "journal":
        journal_worker(a.path, a.logdir, a.offset)
        return
    if a.command == "archive":
        with projection_lock(a.logdir):
            sink = Sink(a.logdir)
            archive(sink)
            published_curves(sink)
        return
    cursors = {}
    children = {}
    monitor = None
    if a.command == "watch":
        a.logdir.mkdir(parents=True, exist_ok=True)
        monitor = (a.logdir / "cell-watcher.lock").open("a")
        try:
            fcntl.flock(monitor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
    try:
        while True:
            scan(a.logdir, a.artifacts, history=a.command == "sync")
            if a.command == "sync":
                return
            for file in a.artifacts.glob("continuation-exposure/*/*-live.jsonl"):
                with file.open() as f:
                    f.seek(cursors.get(file, 0))
                    while True:
                        offset = f.tell()
                        line = f.readline()
                        if not line.endswith("\n"):
                            break
                        cursors[file] = f.tell()
                        if json.loads(line).get("kind") == "config":
                            children[file, offset] = subprocess.Popen(
                                [
                                    sys.executable,
                                    __file__,
                                    "journal",
                                    "--path",
                                    str(file),
                                    "--offset",
                                    str(offset),
                                    "--logdir",
                                    str(a.logdir),
                                ]
                            )

            time.sleep(30)
    finally:
        for p in children.values():
            if p.poll() is None:
                p.terminate()


if __name__ == "__main__":
    main()
