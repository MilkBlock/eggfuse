"""Replay the actual sampler and isolate each active term of the historical slot loss."""

from collections import Counter, defaultdict
from pathlib import Path
import json
import torch
from torch.nn import functional as F

from discovery_states import cli
from fine_fit import fit, path_factors, update

ARMS = (
    "self",
    "omission",
    "inactive",
    "binding",
    "repeat",
    "edit",
    "no-inactive",
    "witness",
)


def step(
    net,
    opt,
    sampler,
    arm,
    rec,
    batches,
    k,
    pare,
    edit,
    edge,
    budget,
    gate,
    objective,
    limit,
    count,
):
    if arm == "witness":
        return update(
            net,
            opt,
            sampler,
            arm,
            rec,
            batches,
            k,
            pare,
            edit,
            edge,
            budget,
            gate,
            objective,
            limit,
            count,
        )
    opt.zero_grad()
    cache = {}

    def factors(key):
        if key not in cache:
            cache[key] = path_factors(net, batches[key])
        return cache[key]

    def log(key, c):
        return factors(key)[batches[key][1][c]].clamp_min(1e-30).log()

    losses = []
    if batches[k]:
        fs = factors(k)
        groups = defaultdict(list)
        rules = set()
        for c, i in batches[k][1].items():
            if c in rec["positive"]:
                target = "self" if c in rec["self_positive"] else "omission"
                if arm in (target, "no-inactive"):
                    groups[rec["positive"][c]].append(i)
            if c in rec["inactive"] and (c.rule, c.higher) not in rules:
                rules.add((c.rule, c.higher))
                if arm == "inactive":
                    losses.append(fs[i, 0])
            elif c in rec["bad_binding"] and arm in ("binding", "no-inactive"):
                losses.append(fs[i, 0].detach() * fs[i, 1:].prod())
        p = fs.prod(1)
        for ids in groups.values():
            losses.append(
                torch.expm1(
                    int(budget) * torch.log1p(-p[ids].sum().clamp(max=1 - 1e-6))
                )
                / int(budget)
            )
    if pare and arm in ("repeat", "no-inactive"):
        x, y, c = pare
        losses.append(0.05 * F.softplus(log(y, c).sum() - log(x, c).sum()))
    if edit and arm in ("edit", "no-inactive"):
        x, bad, good, j = edit
        losses.append(0.05 * F.softplus(log(x, bad)[1 + j] - log(x, good)[1 + j]))
    # Preserve historical Adam momentum and weight decay even on empty-label steps.
    loss = sum(losses, next(net.parameters()).sum() * 0)
    if batches[k]:
        loss = loss + factors(k).sum() * 0
    loss.backward()
    torch.nn.utils.clip_grad_norm_(net.parameters(), 5, error_if_nonfinite=True)
    opt.step()
    count[arm + "_steps"] += 1
    count[arm + "_nonempty"] += bool(losses)


class Exposure:
    def __init__(self):
        self.count = Counter()
        self.unique = defaultdict(set)
        self.programs = set()
        self.pool = Counter()

    def __call__(self, idx, seed, data, rec, batches, k, pare, edit):
        if idx not in self.programs:
            self.programs.add(idx)
            for b, sh in data.items():
                for j, e in enumerate(sh["events"]):
                    self.pool["available_page_occurrences"] += 1
                    self.pool["neural_tokens_branch_" + str(b)] += len(e["response"])
                    self.pool["omission_witness_occurrences"] += len(e["omitted"])
                    for name in (
                        "positive",
                        "self_positive",
                        "inactive",
                        "bad_binding",
                    ):
                        self.pool["available_page_" + name] += len(rec[b, j][name])

        def add(kind, key, c=None):
            b, j = key
            sh = data[b]
            e = sh["events"][j]
            state = (
                idx,
                e["frame"]["run"],
                e["semantic_state"],
                tuple(
                    map(
                        tuple,
                        next(
                            s[4]
                            for s in sh["scheduler"]
                            if s[0] == e["frame"]["run"] and not s[3]
                        ),
                    )
                ),
            )
            identity = (state, c)
            for scope in (str(seed), "combined"):
                label = scope + "/" + kind
                self.count[label] += 1
                self.unique[label].add(identity)
            return state

        add("chosen", k)
        b, j = k
        direct_pos = 0
        r = rec[k]
        if batches[k]:
            seen = set()
            for c in batches[k][1]:
                active = False
                if c in r["positive"]:
                    add("self" if c in r["self_positive"] else "omission", k, c)
                    add("positive_effect", k, r["positive"][c])
                    direct_pos += 1
                    active = True
                if c in r["inactive"]:
                    if (c.rule, c.higher) not in seen:
                        add("inactive_template", k, (c.rule, c.higher))
                        active = True
                    seen.add((c.rule, c.higher))
                elif c in r["bad_binding"]:
                    add("binding_tuple", k, c)
                    active = True
                if active:
                    add("supervised_state", k)
                else:
                    add("no_direct_page_term", k, c)
        if batches[k] and seen:
            run = data[b]["events"][j]["frame"]["run"]
            all_rules = next(
                s[4] for s in data[b]["scheduler"] if s[0] == run and not s[3]
            )
            add("page_with_inactive_term", k)
            if not direct_pos:
                add("inactive_no_positive_page", k)
            if len(seen) < len(all_rules):
                add("partial_inactive_penalty", k)
            if not any(dirty for _, _, dirty in all_rules):
                add("all_inactive_with_penalty", k)
        if pare:
            x, y, c = pare
            for label, key in (("unfinished", x), ("completed", y)):
                add("repeat_" + label, key, c)
                add("supervised_state", key)
        if edit:
            key, bad, good, slot = edit
            add("minimal_edit", key, (bad, good, slot))
            add("supervised_state", key)

    def write(self, path):
        path.write_text(
            json.dumps(
                dict(
                    pool=self.pool,
                    exposures=self.count,
                    distinct={k: len(v) for k, v in self.unique.items()},
                ),
                indent=2,
            )
            + "\n"
        )


if __name__ == "__main__":
    p = cli()
    p.add_argument("--initial", type=Path, required=True)
    p.add_argument("--programs", type=int, default=64)
    p.add_argument("--steps", type=int, default=512)
    p.add_argument("--inventory-only", action="store_true")
    a = p.parse_args()
    a.arms = () if a.inventory_only else ARMS
    a.tag = "inventory" if a.inventory_only else "isolate"
    a.objective = "slot"
    a.slot_limit = 8192
    torch.set_num_threads(1)
    exposure = Exposure()
    fit(a, step=step, observe=exposure)
    exposure.write(a.out / "exposure.json")
