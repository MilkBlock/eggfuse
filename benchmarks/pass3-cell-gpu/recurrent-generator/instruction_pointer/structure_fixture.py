"""Native positive control with two completed bodies, two branches and a later fan-in."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from entry_closure import named
from event_addresses import Directory
from higher_replacement import send
from protocol_experiment import dump
from receipt_bake import save
from receipt_takeover import replay_many
from recursive_train import binary, read
from structure_recipe import Evidence, native_unit, validate_program
from structure_runtime import StructureEntries
from transaction_native import execute


class ForcedBodyPair:
    """Explicit input addresses instead of a learned choice in the positive control."""

    def __init__(self, store, evidence, groups, units, plan, refs):
        self.policy = StructureEntries(
            evidence.t.program,
            store,
            store / "wired.pt",
            None,
            read(store / "entry-contracts.json"),
            evidence.t.rules.rules,
        )
        self.policy.programs = {0: plan}
        self.policy.needed = {op for _, _, wires in plan for _, back, op in wires if back >= 0}
        self.entries = [tuple(map(named, evidence.t.q[g[0]]["parents"])) for g in groups]
        self.units = units
        self.ops = [p[1] for p in refs]
        self.signed = []
        self.memory = None

    def run_snapshot(self, frame, pub, rd, model, txn, stats, deadline):
        p = self.policy
        if self.memory is None:
            self.memory = Directory(rd, stats)
        p.start(rd, pub, txn, dict(frame["rules"]), stats)
        p.resume_programs(self.memory)
        if txn.run == 1:
            for i, (body, inputs) in enumerate(zip(self.units, self.entries, strict=True)):
                uid = -10 - i
                p.cat.units[uid] = body
                reply = send(txn, body[0][0], np.array([inputs], np.int64))[0]
                if reply[1] != 0:
                    raise ValueError("fixture root rejected")
                self.signed.append(int(reply[0]))
                p.begin(uid, inputs, int(reply[0]), txn)
        elif txn.run == 3:
            tails = {members[0]: t for t, members in p.members.items()}
            refs = tuple(p.observed[tails[t], op] for t, op in zip(self.signed, self.ops, strict=True))
            p.issue_structure(p.programs[0][0][0], refs, "Compose", self.memory, 0)


def check(data, directory, output):
    e = Evidence(data, "fixture", directory)
    tape = e.t
    root = next(q for q in tape.tape if q["run"] == 3)
    refs = tuple(map(named, root["parents"]))
    groups = []
    units = []
    cases = []
    for ref in refs:
        tail = tape.q[ref[0]]
        upstream, op, _ = named(tail["parents"][0])
        groups.append((upstream, ref[0]))
        cases.append((len(units), [upstream, ref[0]]))
        units.append([(tape.q[upstream]["rule"], 0, ((-1, 0),)), (tail["rule"], 1, ((0, op),))])
    plan, tokens = e.mine(root, refs, groups)
    validate_program(plan)
    if len(tokens) != 3 or [g for _, g, _ in plan] != [0, 0, 1] or {w[0] for w in plan[-1][2]} != {0, 1}:
        raise AssertionError("missing same-stage sibling or later fan-in")
    if e.match(plan, root, refs, groups) != tokens:
        raise AssertionError("compiled layout cannot reproduce its instance")
    cases.append((len(units), tokens))
    units.append(native_unit(plan, tokens, tape))
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "units.json"
        save(path, units)
        checks = replay_many(
            directory, binary(data), path, cases, tape.tape, read(directory / "capture.json")
        )
        # Keep the real data root immutable while reusing its unchanged runtime and weights.
        tmp = Path(tmp)
        (tmp / "recursive-agent").mkdir()
        for name in ("unified-scale", "structured-retrieval", "recursive-agent/multi.pt"):
            (tmp / name).symlink_to((data / name).resolve())
        (tmp / "recursive-agent/fixture").symlink_to(directory.resolve())
        forced = ForcedBodyPair(output.parent, e, groups, units[:2], plan, refs)
        ccp = execute(tmp, "fixture", study=forced)
        if not ccp["exact_endpoint"] or ccp["signed_ops"] != sum(e.ops.values()) or ccp["paid"] != 7:
            raise ValueError("CCP fixture failed to reproduce the verified three-part computation")
        ccp = {k: ccp[k] for k in ("protocol", "runs", "paid", "verdicts", "signed_ops", "exact_endpoint")}
        ccp["structure_replies"] = forced.policy.count["structure_reply_accepted"]
        ccp["independent_partner_bindings_at_issue"] = forced.policy.count["open_new_bindings"]
    dump(
        output,
        {
            "oracle": True,
            "witnessed_plan": plan,
            "completed_bodies": groups,
            "composite_tokens": tokens,
            "effective_ops": sum(e.ops[t] for t in tokens),
            "native": checks,
            "ccp": ccp,
        },
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for name in ("data", "directory", "output"):
        p.add_argument(name, type=Path)
    a = p.parse_args()
    check(a.data, a.directory, a.output)
