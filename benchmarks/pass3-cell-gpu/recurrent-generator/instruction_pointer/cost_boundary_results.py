"""Extract the verified root ledger, native fork and isolated hardware samples."""

import argparse
import json
import subprocess
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import numpy as np

from cost_profile import FIELDS, META
from recursive_train import binary, folder


def hardware(boundary, arm):
    timing = json.loads((boundary / f"event-{arm}.json").read_text())
    toc = ET.parse(boundary / f"root-{arm}-toc.xml")
    table = toc.find('.//table[@schema="counters-profile"]')
    events = ["INST_LDST", "LD_UNIT_UOP", "ST_UNIT_UOP"]
    if table is None or table.get("pmc-events").replace('"', "").split() != events:
        raise ValueError("wrong hardware counters")
    origin = round(datetime.fromisoformat(toc.findtext(".//start-date")).timestamp() * 1e9)
    cache = {}
    counts = np.zeros(3, dtype=np.int64)
    rows = 0
    for _, row in ET.iterparse(boundary / f"root-{arm}.xml", events=("end",)):
        if row.tag != "row":
            continue
        time, pmc = row[0], row[-1]
        for node in (time, pmc):
            if node.get("id"):
                cache[node.get("id")] = node.text
        if pmc.tag == "pmc-events":
            stamp = origin + int(time.text or cache[time.get("ref")])
            if timing["begin_unix_ns"] + 1000000 <= stamp <= timing["end_unix_ns"] - 1000000:
                counts += np.array((pmc.text or cache[pmc.get("ref")]).split(), dtype=np.int64)
                rows += 1
        row.clear()
    if not rows or not all(counts):
        raise ValueError("no hardware samples in measured interval")
    return dict(
        **timing,
        samples=rows,
        counts=dict(zip(events, map(int, counts))),
        sampled_per_root=dict(zip(events, counts / timing["rounds"])),
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    args = p.parse_args()
    s = args.store
    z = np.load(s / "sum-divisors-ledger.npz")
    meta = z["meta"]
    (ix,) = np.flatnonzero((meta[:, :7] == [541, 498, 4, 883892, 2, 303, 1]).all(1))
    cmd = [
        binary(args.data),
        "replay",
        folder(args.data, "sum-divisors") / "program.json",
        s / "sum-divisors-issued.json",
        "time",
        "540",
        "--audit-next-proofs",
    ]
    bindings = json.loads(subprocess.check_output(cmd))
    outcome = json.loads(subprocess.check_output([*cmd[:-1], "--audit-exact-next"]))
    if outcome["run"] != 541 or outcome["result"].get("next") != [0, False]:
        raise ValueError(outcome)
    depth = z["depth"][ix]
    if depth[:, 1].sum() != 404643 or bindings or z["verdict"][ix, -1] != 0:
        raise ValueError("event or native fork mismatch")
    result = dict(
        meta=dict(zip(META, map(int, meta[ix]))),
        depth=[dict(zip(FIELDS, map(int, d))) for d in depth if d.any()],
        formed=int(z["verdict"][ix, -2]),
        signed=int(z["verdict"][ix, -1]),
        effective_ops=int(z["ops"][ix]),
        native_exact_next=outcome,
        native_next_proofs=len(bindings),
        hardware={a: hardware(s / "boundary", a) for a in ("base", "frozen")},
    )
    (s / "boundary/root-evidence.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
