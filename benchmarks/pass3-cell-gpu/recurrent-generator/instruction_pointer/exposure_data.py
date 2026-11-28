"""Offline same-window proposals and native singleton/blank forks from three behavior policies."""
import gzip
import json
import os
import pickle
import random
from collections import Counter, defaultdict
from contextlib import nullcontext

import numpy as np
import torch

from cell_kv_runtime import native
from exposure_policy import Historical, policy
from exposure_train import output, sha
from scaling_archive import directory
from exposure_worlds import world
from feedback_measure import prob
from int_parameters import digest
from partner_index_worlds import args
from scaling_eval import HeldoutLedger, Sampling
from scaling_fit import atomic


def dump(path, value):
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wb", compresslevel=3) as f:
        pickle.dump(value, f, protocol=5)
    tmp.replace(path)


def load(path):
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def observed(w, align, a, pol, seed, limit):
    trace = HeldoutLedger()
    r = native(a, w, policy=pol, seed=seed, slots=6, submit_pages=2,
               receipt_memory=True, rule_state=True, reference=align, execution_trace=trace,
               paid_limit=limit)
    return r, trace


class Capture:
    def __init__(self, primary, hist, learned, uniform, seed, source):
        self.primary, self.hist, self.learned, self.uniform = primary, hist, learned, uniform
        self.seed, self.source = seed, source
        self.pages = []
        self.samples = []

    def prepare(self, w):
        for p in (self.learned, self.uniform, self.hist):
            p.prepare(w)

    def inference_session(self):
        return self.primary.inference_session() if hasattr(self.primary, "inference_session") else nullcontext()

    def observe_native_memory(self, frame, publication, repairs):
        self.hist.observe_native_memory(frame, publication, repairs)

    def observe_publication(self, frame):
        for p in (self.learned, self.uniform):
            p.observe_publication(frame)

    def generate(self, w, s, rng, slots):
        issued = self.primary.generate(w, s, rng, slots)
        page = len(self.pages)
        self.pages.append(issued)
        if not s["menu"] or not s["request_receipts"]:
            return issued
        # Independent diagnostic RNG. Draws from the three policies never alter the issued page.
        a = np.random.default_rng(self.seed * 193 + page)
        model = self.learned.generate(w, s, a, 6)
        rnd = self.uniform.generate(w, s, a, 6)
        hist = self.hist.propose(12)
        if issued or hist or model or rnd:
            all_tokens = sorted(set(issued + hist + model + rnd))
            self.samples.append((page, s, dict(issued=issued, history=hist, neural=model, random=rnd),
                                 prob(self.learned.net, w, s, all_tokens)))
        return issued


class Fork:
    def __init__(self, pages, page, s, token):
        self.pages, self.page, self.state, self.token = pages, page, s, token
        self.i = 0
        self.hit = False

    def prepare(self, w):
        pass

    def generate(self, w, s, rng, slots):
        i = self.i
        self.i += 1
        if i < self.page:
            return self.pages[i]
        if i == self.page:
            if s != self.state:
                raise ValueError("native replay differs at the policy decision")
            self.hit = True
            return [] if self.token is None else [self.token]
        return []


def branch(a, w, align, pages, page, s, token, seed):
    p = Fork(pages, page, s, token)
    r, trace = observed(w, align, a, p, seed, None)
    if not p.hit:
        raise ValueError("proposal fork did not reach the decision")
    evidence = {}
    if token is not None:
        entry = trace.responses[len(s["request_receipts"])]
        uid = entry[-1][0]
        item = trace.higher.get(uid, trace.entries[uid])
        if (entry[0], entry[2], tuple(entry[3])) != (s["run"], token[0], token[1]):
            raise ValueError("wrong signed request at intervention")
        evidence = dict(status=item["status"], ops=item["effective_ops"],
                        complete=(uid not in trace.higher or item["completed"]))
    return set(r["facts"]), r["graph"], evidence


def collect(a, source, seed, case):
    dst = output(a)
    if case not in ("fact", "sum-divisors"):
        raise ValueError("only development programs may supply forks")
    key = f"fork-{case}-{source}-{seed}"
    path = dst / (key + ".pkl.gz")
    if path.exists():
        return
    model, w, align = policy(a, case, "local-s71-t100000")
    uniform = policy(a, case, "random")[0]
    hist = Historical(a)
    capture = Capture({"history": hist, "neural": model, "random": uniform}[source],
                      hist, model, uniform, seed, source)
    result, trace = observed(w, align, a, capture, seed, 257)
    if sum(r["effective_ops"] for r in trace.entries.values() if r["uid"] not in trace.higher) + sum(
        r["effective_ops"] for r in trace.higher.values()) != result["ops"]:
        raise ValueError("native credit did not partition")
    ordinary, potential = [], []
    for row in capture.samples:
        page, s, choices, probs = row
        k = len(s["request_receipts"])
        # Read the actual native receipt prefix, including possible internal suffix requests.
        signed = trace.responses[k:k+len(choices["issued"])]
        useful = []
        for t, rep in zip(choices["issued"], signed, strict=True):
            uid = rep[-1][0]
            if (rep[2], tuple(rep[3])) != t:
                raise ValueError("issued name differs from native receipt")
            v = trace.higher.get(uid, trace.entries[uid])
            if v["effective_ops"] > 0:
                useful.append(t)
        if useful:
            ordinary.append((row, useful))
        alternatives = set(choices["history"] + choices["random"]) - set(choices["neural"])
        if alternatives and (choices["history"] or useful):
            potential.append((row, sorted(alternatives, key=lambda t: (probs[t], t))))
    rng = random.Random(seed)
    rng.shuffle(ordinary)
    rng.shuffle(potential)
    decisions = {}
    for kind, candidates, count in (("ordinary", ordinary, 18), ("hard", potential, 28)):
        for row, names in candidates[:count]:
            page, s, choices, probs = row
            entry = decisions.setdefault(page, dict(state=s, choices=choices, p=probs,
                                                     ordinary=[], hard=[]))
            entry[kind] = names[:3]
    examples = []
    for page, e in sorted(decisions.items()):
        s = e["state"]
        pre, graph, _ = branch(a, w, align, capture.pages, page, s, None, seed)
        table = []
        for t in sorted(set(e["ordinary"] + e["hard"])):
            after, gh, evidence = branch(a, w, align, capture.pages, page, s, t, seed)
            gain, lost = sorted(after-pre), sorted(pre-after)
            productive = evidence["status"] == "accepted" and evidence["complete"] and evidence["ops"] > 0 and gain and not lost
            table.append(dict(token=t, p=e["p"][t], ordinary=t in e["ordinary"], hard=t in e["hard"],
                              gain=gain, lost=lost, graph=gh, evidence=evidence,
                              effect=digest([gain,lost]) if productive else None,
                              named_repeat=any((v[2], tuple(v[3]))==t for v in s["request_receipts"])))
        examples.append(dict(page=page, state=s, sh=digest(s), alternatives=e["choices"],
                             blank_graph=graph, table=table))
        if len(examples)%10 == 0:
            print(key, len(examples), len(decisions), flush=True)
    dump(path, dict(case=case, source=source, seed=seed, pages=capture.pages, examples=examples,
                    result=result, responses=trace.responses, productive_windows=len(ordinary),
                    disagreement_windows=len(potential)))


def materialize(a):
    dst = output(a)
    manifest = dst / "corpora.json"
    if manifest.exists():
        for name, expected in json.loads(manifest.read_text())["sha256"].items():
            if sha(dst / name) != expected:
                raise ValueError(f"augmented corpus changed: {name}")
        return
    old = load(directory(a) / "difficulty.pkl.gz")
    old_states = {key[1] for key in old}
    buckets = defaultdict(lambda: defaultdict(dict))
    states = {}
    origin = {}
    files = sorted(dst.glob("fork-*.pkl.gz"))
    if len(files) != 42:
        raise ValueError(f"expected all 42 prespecified behavior tapes, found {len(files)}")
    excluded = set()
    for path in files:
        tape = load(path)
        for e in tape["examples"]:
            k = tape["case"], e["sh"]
            if k[1] in old_states:
                excluded.add(k)
                continue
            states[k] = e["state"]
            origin.setdefault(k, (k[0], tape["source"]))
            for q in e["table"]:
                if q["effect"]:
                    for kind in ("ordinary", "hard"):
                        if q[kind] and (kind == "ordinary" or q["p"] <= 0.05):
                            buckets[kind][k][q["token"]] = q
    hard = set(buckets["hard"])
    ordinary = set(buckets["ordinary"]) - hard
    rng = random.Random(3801)
    sets = {"B": [], "C": []}
    strata = {}
    for group in sorted(set(origin.values())):
        populations = [sorted(k for k in keys if origin[k] == group) for keys in (ordinary, hard)]
        count = min(map(len, populations))
        strata["/".join(group)] = dict(ordinary=len(populations[0]), hard=len(populations[1]), per_arm=count)
        for label, kind, keys in zip(("B", "C"), ("ordinary", "hard"), populations, strict=True):
            for k in rng.sample(keys, count):
                group_targets = buckets[kind][k]
                if kind == "hard":
                    token = min(group_targets, key=lambda t: (group_targets[t]["p"], t))
                else:
                    token = rng.choice(sorted(group_targets))
                sets[label].append((k[0], states[k], token, group_targets[token]["effect"]))
    if not sets["B"]:
        raise ValueError("no matched native additions")
    sets["D"] = sets["B"] + sets["C"]
    hashes = {}
    for label, rows in sets.items():
        path = dst / (label + "-data.pkl.gz")
        dump(path, rows)
        hashes[path.name] = sha(path)
    atomic(manifest, dict(disjoint_states_per_arm=len(sets["B"]), strata=strata,
                          source_tapes={p.name: sha(p) for p in files}, sha256=hashes,
                          preexisting_states_excluded=len(excluded),
                          max_hard_probability=0.05, development=["fact","sum-divisors"]))


def extend_pool(a, pool, net, rows):
    worlds={}
    for case,s,t,effect in rows:
        if case not in ("fact","sum-divisors"):
            raise ValueError("test case in training data")
        if case not in worlds:
            worlds[case]=world(a,net.actor,case)[0]
        w=worlds[case]
        if (sha(w.dir / "program.json"), digest(s)) in pool.records:
            raise ValueError("new state was already in the base corpus")
        key=pool.add_base("egg_rollout",w,s,[t],False)
        pool.effects.setdefault(key,{})[t]=effect
    pool.keys=list(pool.records)
    if set(pool.keys)&pool.validation_keys:
        raise ValueError("augmented validation state overlap")


if __name__=="__main__":
    torch.set_num_threads(1)
    with torch.no_grad():
        a=args()
        if os.getenv("EXPOSURE_MATERIALIZE"):
            materialize(a)
        else:
            for case in os.getenv("EXPOSURE_CASES", "sum-divisors").split():
                for src in os.getenv("EXPOSURE_SOURCES","neural random history").split():
                    for seed in map(int,os.getenv("EXPOSURE_SEEDS","419 733").split()):
                        collect(a,src,seed,case)
