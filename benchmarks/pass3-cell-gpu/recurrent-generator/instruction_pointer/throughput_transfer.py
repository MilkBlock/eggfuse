"""Measure cross-task parameter interference at the actual template draw, before parents."""

from collections import Counter
from pathlib import Path
import json
import numpy as np
import torch
from coverage_eval import choices
from discovery_sampling import seed_for
from discovery_states import cli, read, save
from query_environment import conditioned
from recursive_train import folder
from throughput_slots import SlotLog, instrument


@torch.no_grad()
def compare(a, case, source):
    root = a.archive / source / case
    m = conditioned(a, folder(a.data, case), root / "scheduler.jsonl")
    names = [
        "initial",
        "isolate-binding",
        "isolate-edit",
        "isolate-inactive",
        "dual-witness",
        "isolate-no-inactive",
        "conservative",
    ]
    pages = {
        n: instrument(choices(a, m, n, 256, 9633)[2], SlotLog(retain_page=True))
        for n in names
    }

    def publish(frame):
        for p in pages.values():
            p.publication(frame)

    m.on_page_publication = publish
    all_runs = sorted(s["run"] for s in read(root / "states.json"))
    selected = {
        all_runs[i]
        for i in np.linspace(0, len(all_runs) - 1, min(8, len(all_runs)), dtype=int)
    }
    ctxs = (
        read(a.archive / "dirty" / case / "contexts.json")
        if source == "rollout"
        else {}
    )
    rows = []
    for line in (root / "frames.jsonl").open():
        frame = json.loads(line)
        r = frame["run"]
        if r > max(selected):
            break
        m.update(frame)
        if r not in selected:
            continue
        if ctxs:
            last, event, state, ctx = ctxs[str(r)]
            m.last = tuple(last) if last else None
            m.event, m.state = torch.tensor(event), torch.tensor(state)
            torch.testing.assert_close(m.context(), torch.tensor(ctx), rtol=0, atol=0)
        base = None
        for name, p in pages.items():
            p.sample(m, (), 1, np.random.default_rng(seed_for(r, 9)), Counter())
            slots = p.slot_observer.last_page
            if base is None:
                base = slots
            count = Counter()
            for (t, why, refs), (old, old_why, _) in zip(slots, base, strict=True):
                count["template_changed"] += t != old
                count["initial_complete_now_empty_domain"] += (
                    not old_why and why and (why - 1) % 3 == 0
                )
                count["same_template_completeness_changed"] += t == old and bool(
                    old_why
                ) != bool(why)
                count["initial_incomplete_now_complete"] += bool(old_why) and not why
            rows.append(
                dict(
                    case=case, source=source, run=r, arm=name, slots=len(slots), **count
                )
            )
    m.close_observer()
    dest = a.out / "transfer"
    dest.mkdir(exist_ok=True)
    save(dest / (source + "-" + case + ".json"), rows)


if __name__ == "__main__":
    p = cli()
    p.add_argument("--archive", type=Path, required=True)
    a = p.parse_args()
    torch.set_num_threads(1)
    for case in a.cases:
        for source in ("teacher", "rollout"):
            compare(a, case, source)
