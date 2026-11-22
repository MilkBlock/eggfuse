"""Rotate fixed and learned SubTuple scale on identical history-addressed inputs."""
from time import perf_counter

from ept import ledger_digest, score
from train import work


def compare(run, request, baseline, recipe, reference, packets):
    results = {}
    arms = ("depth2", "model", "depth8")
    query = request["strict_named"]
    rid = query["depth_reader"]["rule"]
    def source_roots(record):
        commits = {r[2]: r for r in record["root_recipe"]["commits"] if r[3] == rid}
        caps = record["strict_named"]["depth_caps"]
        if len({serial for serial, _, _ in caps}) != len(caps):
            raise ValueError("duplicate scale decision")
        return {commits[serial][0] for serial, _, _ in caps}
    subjects = source_roots(baseline)
    for turn in range(len(arms)):
        for name in arms[turn:] + arms[:turn]:
            model = dict(query["depth_reader"])
            if name != "model":
                model["fixed_depth"] = int(name[5:])
            spec = dict(request, strict_named=dict(query, depth_reader=model))
            start = perf_counter()
            trial = run(spec)
            wall = 1000 * (perf_counter() - start)
            for field in ("rhs", "writes", "resumes", "events", "runs", "schedule", "state_sha"):
                if trial.get(field) != baseline[field]:
                    raise ValueError((name, field))
            root = trial["root_recipe"]
            for field in ("history_online", "history_access", "history_suppressed"):
                if root[field] != baseline["root_recipe"][field]:
                    raise ValueError((name, field))
            if ledger_digest(trial) != reference:
                raise ValueError("scale changed reference ledger")
            caps = trial["strict_named"]["depth_caps"]
            external = source_roots(trial)
            seen = {r[0] for r in root["commits"] if r[3] == rid}
            if not (external | subjects) <= seen:
                raise ValueError("missing committed scale subject")
            if name != "model" and any(action != (1 if name == "depth2" else 2)
                                       for _, _, action in caps):
                raise ValueError("fixed control did not apply to all its roots")
            checked, pending = root["history_online"]
            paid = packets(trial) + sum(not valid for _, _, valid in checked) + len(pending)
            ept = score(trial, recipe, paid, reference)
            if not results.get(name):
                results[name] = dict(native_ms=[], request_ms=[])
            counts = dict(work(trial), paid=paid, ept=ept["ept"], signed=ept["signed"],
                          choices=trial["strict_named"]["depth_choices"][0],
                          extra_external=len(external - subjects),
                          displaced_external=len(subjects - external))
            arm = results[name]
            if "counts" in arm and arm["counts"] != counts:
                raise ValueError("nondeterministic scale metrics")
            arm["counts"] = counts
            arm["native_ms"].append(trial["ms"])
            arm["request_ms"].append(wall)
            del trial
    return results
