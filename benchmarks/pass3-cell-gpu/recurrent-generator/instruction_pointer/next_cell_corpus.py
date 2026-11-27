"""Positive-only Next Cell corpus. Offline native evidence never enters the sampler."""

import gzip
import hashlib
import json
import os
import pickle
from collections import Counter, defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import torch

from credit_scale_fit import load_shard
from credit_scale_programs import topology
from data_scale_corpus import program as base_recipe
from transition_programs import source as dynamic_source
from coverage_examples import pack
from discovery_score import token
from discovery_states import cli
from discrete_cells import from_q
from transition_credit import decode, schema
from query_environment import conditioned
from address_scores import weight

POLICY, OMITTED, TEACHER, REPLACEMENT, DOWNSTREAM = 1, 2, 4, 8, 16


def digest(data):
    return hashlib.sha256(data).hexdigest()


def sidecar(source, name):
    path = source.parent.parent / name / source.name
    if not path.exists():
        return {}
    obj = load_shard(path)
    if obj["source_sha256"] != digest(source.read_bytes()):
        raise ValueError(f"stale evidence: {path}")
    return obj


def add(groups, cell, effect, source):
    key = ("named", cell) if effect is None else ("effect", effect)
    aliases = groups.setdefault(key, {})
    aliases[cell] = aliases.get(cell, 0) | source


def collect(paths, folder):
    """A state key includes the physical publication history, not just the final e-graph."""
    prog = (folder / "program.json").read_bytes()
    program_hash = digest(prog)
    layout = schema(json.loads(prog))
    states = {}
    counts = Counter()
    for path in paths:
        sh = load_shard(path)
        if sh["program"] != program_hash:
            raise ValueError(path)
        pages = sidecar(path, "page-dual").get("events")
        fine = sidecar(path, "credit")
        edits = defaultdict(list)
        for run, _, good, _, gain in fine.get("edits", []):
            if gain > 0:
                edits[run].append(token(good))
        providers = {(r, uid) for r, uid, *_ in fine.get("edges", [])}
        history = hashlib.sha256(prog)
        counts["shards"] += 1
        if len(sh["events"]) != len(sh["scheduler"]) - int(
            bool(sh["scheduler"][-1][3])
        ):
            raise ValueError("unaligned scheduler")
        for i, ((signed, omissions), e) in enumerate(
            zip(decode(sh, layout), sh["events"], strict=True)
        ):
            f = e["frame"]
            r = f["run"]
            history.update(
                json.dumps(
                    [f, sh["scheduler"][i], e["context"], e["semantic_state"]],
                    separators=(",", ":"),
                ).encode()
            )
            k = history.hexdigest()
            anchor, groups = states.setdefault(k, ((str(path), i), {}))
            counts["state_occurrences"] += 1
            counts["pure_signed" if sh["branch"] == 2 else "mixed_signed"] += len(
                signed
            )
            counts["assisted_occurrences"] += len(e["assisted"])
            signatures = {c: sig for c, _, _, sig, _ in signed}
            signatures.update({c: sig for c, _, sig in omissions})
            positive = {}
            for (c, status, gain, sig, _), reply in zip(
                signed, e["response"], strict=True
            ):
                counts["response_" + status] += 1
                if status == "accepted" and (gain > 0 or (r, reply[0]) in providers):
                    positive[c] = POLICY | (
                        DOWNSTREAM if (r, reply[0]) in providers else 0
                    )
            if e["stable"]:
                for c, gain, _ in omissions:
                    if gain > 0:
                        positive[c] = positive.get(c, 0) | OMITTED
            if pages is not None:
                page = pages[i]
                if (page["run"], page["epoch"]) != (r, f["epoch"]):
                    raise ValueError("teacher alignment")
                for q, gain in page["teacher_witnesses"] or []:
                    if gain > 0:
                        c = from_q(q)
                        positive[c] = positive.get(c, 0) | TEACHER
            for c in edits[r]:
                positive[c] = positive.get(c, 0) | REPLACEMENT
            for c, evidence in positive.items():
                add(groups, c, signatures.get(c), evidence)
            history.update(
                json.dumps(
                    [
                        e["generated"],
                        e["response"],
                        e["assisted"],
                        e["assisted_response"],
                    ],
                    separators=(",", ":"),
                ).encode()
            )
    # The same named witness can occur in multiple proof sources. Coalesce only
    # when the concrete cell itself links an unknown signature to a known one.
    for _, groups in states.values():
        identified = {c: k for k, cs in groups.items() if k[0] == "effect" for c in cs}
        for k in list(groups):
            if k[0] == "named" and k[1] in identified:
                c = k[1]
                cs = groups[identified[c]]
                cs[c] = cs.get(c, 0) | groups.pop(k)[c]
    return states, counts


def store_file(path, obj):
    with TemporaryDirectory(dir=path.parent) as scratch:
        temp = Path(scratch) / path.with_suffix(".tmp").name
        with gzip.open(temp, "wb", compresslevel=1) as fp:
            pickle.dump(obj, fp, protocol=5)
        os.replace(temp, path)


def program(a, idx, gate):
    folder = a.previous / "programs" / f"{idx:04}"
    held = idx >= 256
    roots = (
        [a.buffer_root / "held"]
        if held
        else [a.buffer_root, a.buffer_root / "diverse", a.buffer_root / "fine", a.dual]
    )
    paths = [
        p for root in roots for p in sorted((root / "buffer").glob(f"{idx:04}-*.gz"))
    ]
    if not paths:
        raise ValueError(f"no experience for {idx}")
    states, counts = collect(paths, folder)
    selected = defaultdict(dict)
    for key, ((p, i), groups) in states.items():
        if groups:
            selected[p][i] = (key, groups)
    blocks = []
    with TemporaryDirectory() as td, torch.no_grad():
        for p, todo in selected.items():
            sh = load_shard(Path(p))
            observer = Path(td) / "observer"
            observer.write_text("".join(json.dumps(x) + "\n" for x in sh["scheduler"]))
            m = conditioned(a, folder, observer)
            try:
                for i, e in enumerate(sh["events"]):
                    m.update(e["frame"])
                    if i not in todo:
                        continue
                    torch.testing.assert_close(
                        m.context(), torch.tensor(e["context"]), rtol=0, atol=0
                    )
                    key, groups = todo[i]
                    cells = [c for cs in groups.values() for c in cs]
                    packet = pack(m, cells, gate, "offline", e["frame"]["run"])
                    packet["offsets"] = np.r_[
                        0, np.cumsum([len(v) for v in groups.values()])
                    ]
                    packet["cells"] = cells
                    packet["evidence"] = np.array(
                        [v for cs in groups.values() for v in cs.values()],
                        dtype=np.uint8,
                    )
                    packet["state"] = key
                    packet["anchor"] = (p, i)
                    counts["decision_targets"] += len(groups)
                    counts["named_targets"] += len(cells)
                    for name, mask in [
                        ("policy", POLICY),
                        ("omitted", OMITTED),
                        ("teacher", TEACHER),
                        ("replacement", REPLACEMENT),
                        ("downstream", DOWNSTREAM),
                    ]:
                        counts[name] += int(((packet["evidence"] & mask) != 0).sum())
                    blocks.append(packet)
            finally:
                m.close_observer()
    counts.update(states=len(states), supervised_states=len(blocks))
    if (folder / "source.egg").read_text() != dynamic_source(idx)[0]:
        raise ValueError("unexpected dynamic Recipe")
    return dict(
        index=idx,
        signature=topology(base_recipe(71391 + idx)[0]),
        counts=counts,
        blocks=blocks,
    )


if __name__ == "__main__":
    p = cli()
    for name in ("buffer-root", "dual"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--indices", nargs="+", type=int, required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    dest = a.out / "packets"
    dest.mkdir(parents=True, exist_ok=True)
    gate = weight(a).eval().to("mps")
    for idx in a.indices:
        path = dest / f"{idx:04}.pkl.gz"
        obj = program(a, idx, gate)
        store_file(path, obj)
        print(idx, dict(obj["counts"]), flush=True)
