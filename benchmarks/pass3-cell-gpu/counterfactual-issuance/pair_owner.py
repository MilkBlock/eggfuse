"""Train a producer-side compound issuance decision on generated versioned returns."""
from collections import Counter, defaultdict, deque
from itertools import product
import random

import torch


def wiring(recipe):
    # Resolve by the query shape, preserving atom order and the shared result slot.
    targets = []
    for rid, r in enumerate(recipe["rules"]):
        q = r["query"]
        if ([a["call"].get("table") for a in q] == ["PotentialExtractedExpr", "TCPair"]
                and [len(a["args"]) for a in q] == [3, 3]
                and q[0]["args"][1] == q[1]["args"][2]
                and all("slot" in a for atom in q for a in atom["args"])
                and len({a["slot"] for atom in q for a in atom["args"]}) == 5):
            targets.append(rid)
    target, = targets
    pairs = {}
    for rid, r in enumerate(recipe["rules"]):
        definitions = {}
        for i, op in enumerate(r["effects"]):
            if op["op"] == "copy":
                definitions[op["dst"]] = definitions.get(op["arg"].get("slot"))
            if op.get("kind") != "construct":
                continue
            table = op["call"]["table"]
            if table == "PotentialExtractedExpr":
                inner = definitions.get(op["args"][1].get("slot"))
                if inner is not None and inner[0] == "TCPair":
                    pairs.setdefault(rid, []).append((i, inner[1]))
            definitions[op["dst"]] = (table, i)
    return target, pairs


def features(reused, versions, epoch, claimed):
    return [*reused, *(v == epoch for v in versions), claimed]


def generated(seed, n, clean):
    rng = random.Random(seed)
    x, y = [], []
    for _ in range(n):
        # Random frames return two linked rows. Prior steps in this epoch can
        # create either row without this producer having created it.
        epoch = rng.randint(2, 100)
        versions = [epoch-rng.randrange(2) for _ in range(2)]
        reused = [v < epoch or rng.random() < .5 for v in versions]
        claimed = False if clean else rng.random() < .4
        x.append(features(reused, versions, epoch, claimed))
        # One consumer Run after this epoch; only the first ticket displaces a
        # separate proposal. Both old inputs are below its delta watermark.
        y.append(int(max(versions) == epoch and not claimed))
    return torch.tensor(x, dtype=torch.float32), torch.tensor(y, dtype=torch.float32)


def fit(seed, count, clean=False, width=8, steps=240, device="cpu"):
    x,y = (t.to(device) for t in generated(seed, count, clean))
    torch.manual_seed(seed)
    model = torch.nn.Sequential(torch.nn.Linear(5,width),torch.nn.Tanh(),
                                torch.nn.Linear(width,1)).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=.035)
    for _ in range(steps):
        opt.zero_grad()
        torch.nn.functional.binary_cross_entropy_with_logits(model(x).flatten(),y).backward()
        opt.step()
    return model.cpu().eval()


def action_table(model):
    bits = list(product((False,True),repeat=5))
    with torch.no_grad():
        actions = model(torch.tensor(bits,dtype=torch.float32)).flatten() >= 0
    return dict(zip(bits,actions.tolist()))


def replay(data, target, pairs, policies):
    roots = data["root_recipe"]
    returns = defaultdict(dict)
    for ordinal, _, op, cell, field, version, reused in roots["pair_returns"]:
        returns[ordinal][op] = ((cell,field,version),bool(reused))
    internal = {r[0] for r in data["strict_named"]["signed_commits"]}
    rows = roots["commits"]
    def parent(ref):
        fact = ref["row"].get("Fact")
        if fact is None:
            raise ValueError("expected a constructor witness")
        return fact["cell"],fact["op"],ref["version"]
    # Precompute every Boolean input's frozen neural decision. Nothing in the
    # decision table depends on workload labels or physical addresses.
    decisions = {name:action_table(net) for name,net in policies.items()}
    bits = list(product((False,True), repeat=5))
    decisions["issue_all"] = dict.fromkeys(bits,True)
    decisions["first_versioned_pair"] = {b:not b[-1] for b in bits}
    decisions["fresh_unclaimed"] = {b:(b[2] or b[3]) and not b[4] for b in bits}
    results={}
    for name, table in decisions.items():
        claimed=set()
        pending=defaultdict(deque)
        predicted=[]
        counts=Counter()
        for ordinal, _, serial, rule, _, epoch, refs, _ in rows:
            if rule==target and serial not in internal:
                key=tuple(parent(ref) for ref in sorted(refs,key=lambda x:x["atom"]))
                counts["external_target_commits"]+=1
                # Enforce the query snapshot: a same-epoch RHS return cannot
                # explain a match that was already collected before RHS execution.
                if pending[key] and pending[key][0]<epoch:
                    counts["matched_once"]+=1
                    pending[key].popleft()
            if rule not in pairs:
                continue
            frame=returns.get(ordinal,{})
            for outer,inner in pairs[rule]:
                if outer not in frame or inner not in frame:
                    continue
                (a,ra),(b,rb)=frame[outer],frame[inner]
                key=(a,b)
                counts["returned_pairs"]+=1
                if table[tuple(features((ra,rb),(a[2],b[2]),epoch,key in claimed))]:
                    counts["issued"]+=1
                    claimed.add(key)
                    pending[key].append(epoch)
                    if name=="mixed":
                        predicted.append([ordinal,[list(a),list(b)]])
        if name=="mixed" and predicted!=roots["pair_proposals"]:
            raise ValueError("online proposals differ from causal replay")
        counts["unmatched"]=counts["issued"]-counts["matched_once"]
        results[name]=dict(counts)
    return results


def validate_children(data,target,children,other_internal):
    roots = data["root_recipe"]
    by_serial = {r[2]:r for r in roots["commits"]}
    authorized = {(ordinal,tuple(map(tuple,refs))) for ordinal,refs in roots["pair_proposals"]}
    seen=set()
    for serial, owner in children:
        row=by_serial[serial]
        pair=tuple((p["row"]["Fact"]["cell"],p["row"]["Fact"]["op"],p["version"])
                   for p in row[6])
        if (row[0] in seen or row[0] in other_internal or row[0]<=owner or row[3]!=target
                or [p["atom"] for p in row[6]]!=[0,1] or (owner,pair) not in authorized):
            raise ValueError("pair continuation lacks a unique committed owner or ordered witness")
        seen.add(row[0])


def compare_residual(data, shadow_lanes):
    roots=data["root_recipe"]
    by_serial={r[2]:r for r in roots["commits"]}
    private=Counter()
    for serial,_ in roots["pair_children"]:
        row=by_serial[serial]
        fact=row[6][0]["row"]["Fact"]
        private[row[5],fact["cell"],fact["op"]]+=1
    if any(n!=1 for n in private.values()):
        raise ValueError("multiple protected outcomes for one source pivot")
    residual=Counter(map(tuple,roots["pair_external"]))
    if residual.keys() & private.keys() or not private.keys()<=shadow_lanes.keys():
        raise ValueError("protected pivot overlap or missing reference")
    counts=shadow_lanes.copy()
    for k in private:
        del counts[k]
    if residual!=counts:
        raise ValueError("uncovered external lane changed")
    return sum(shadow_lanes[k]-1 for k in private)
