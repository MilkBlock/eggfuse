"""Post-publication compatibility on independent native policy trajectories."""

import torch

from cell_kv_runtime import native
from cell_kv_world import World, compile_world
from compatibility_eval import diagnose
from compatibility_study import ARMS, SEEDS, align, checkpoint, policy
from compatibility_world import source
from partner_index_worlds import args
from rule_read import load_actor
from token_embedding_study import save


def program(i, f, zero):
    src = source(2, "LR", 2, True, 101, 697003 + i, f)
    # New entry evidence can only appear if the model succeeds in warm.
    producer = (
        "(rule () ((Seed 71 83)) :ruleset warm)"
        if zero
        else "(rule ((Noise x y)) ((Seed x y)) :ruleset warm)"
    )
    return src.replace(
        "(ruleset root)", f"(ruleset warm)\n{producer}\n(ruleset root)"
    ).replace("(run-schedule (run root)", "(run-schedule (run warm) (run root)")


class RecordRoot:
    def __init__(self, net):
        self.net = net
        self.page = None

    def prepare(self, w):
        self.net.prepare(w)

    def generate(self, w, s, rng, slots):
        out = self.net.generate(w, s, rng, slots)
        if w.root in s["menu"]:
            self.page = s, out
        return out


@torch.no_grad()
def run(a):
    actor = load_actor(a.actor, True)
    raw = []
    probes = []
    for i in range(8):
        zero = i >= 4
        ws = [
            World(compile_world(a, f"publish-{i}-{f}", program(i % 4, f, zero)), actor)
            for f in (0, 1)
        ]
        ex = [
            next(x for x in native(a, w, teacher="higher") if w.root in x[0]["menu"])
            for w in ws
        ]
        ref, tids = align(*ex, ws[0])
        for arm in ARMS:
            for seed in SEEDS if arm != "A" else SEEDS[:1]:
                net = policy(a, arm).eval()
                net.load_state_dict(
                    torch.load(checkpoint(a, arm, seed), weights_only=True)
                )
                for p in diagnose(net, ws, ex, ref, tids):
                    probes.append(dict(pair=i, zero=zero, arm=arm, seed=seed, **p))
                for f, w in enumerate(ws):
                    es, ts = ex[f]
                    signatures = {p[0]: (p[3], p[4][:2]) for p in es["ports"]}
                    targets = {
                        (t, signatures[rs[0]]) for t, rs in ts if t >= w.primitives
                    }
                    for draw in (193, 827):
                        spy = RecordRoot(net)
                        net.static_cache.clear()
                        r = native(a, w, policy=spy, seed=draw)
                        s, choices = spy.page
                        ports = {p[0]: p for p in s["ports"]}
                        opened = {
                            p[0]
                            for p in s["ports"]
                            if p[2] >= 0 and p[3] == w.tabs.index("Seed")
                        }
                        hits = [
                            (t, rs)
                            for t, rs in choices
                            if t >= w.primitives
                            and rs[0] in opened
                            and (t, (ports[rs[0]][3], ports[rs[0]][4][:2])) in targets
                        ]
                        raw.append(
                            dict(
                                pair=i,
                                zero=zero,
                                flip=f,
                                arm=arm,
                                seed=seed,
                                draw=draw,
                                published=len(opened),
                                fresh_verified_hits=len(hits),
                                run=s["run"],
                                response=s["response"],
                                **r,
                            )
                        )
    save(a.out / "publish.json", raw)
    save(a.out / "publish-probes.json", probes)


if __name__ == "__main__":
    torch.set_num_threads(1)
    run(args())
