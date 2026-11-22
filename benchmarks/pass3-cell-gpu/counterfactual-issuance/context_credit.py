"""Measure what token context adds to first-issuance marginal return prediction."""
import argparse
from collections import Counter
import json
from pathlib import Path
import random

from train import study, verify
import torch


def inputs(seed, distractors, present):
    rng = random.Random(seed)
    ids = iter(rng.sample(range(100000), 2 * distractors + 6))

    def eq():
        return {"sort": "Expr", "eq": f"Value({next(ids)})"}

    source, output, single = eq(), eq(), eq()
    rows = [dict(table="Get", values=[source, {"sort": "i64", "value": rng.randrange(8)}, output],
                 subsumed=False)]
    unrelated = eq()
    rows.append(dict(table="Single", values=[output if present else unrelated, single], subsumed=False))
    for _ in range(distractors):
        rows.append(dict(table="Single", values=[eq(), eq()], subsumed=False))
    if seed % 3:
        rows.append(dict(table="Single", values=[eq(), output], subsumed=False))
    rng.shuffle(rows)
    return rows


def context(rows):
    # This read sees only initial tokens, before either branch executes.
    target = next(r["values"][-1] for r in rows if r["table"] == "Get")
    linked = any(r["table"] == "Single" and r["values"][0] == target for r in rows)
    port_rows = []
    for r in rows:
        matches = [float(v == target) for v in r["values"]]
        port_rows.append([float(r["table"] == "Single"), *matches,
                          *([0.] * (3 - len(matches)))])
    return linked, port_rows


def collect(args, program_name, start, n):
    program, plans, req, spec = study["setup"](args, program_name)
    samples = []
    with study["src"].base.session(args.native, program, plans) as run:
        for i in range(n):
            seed = start + i // 2
            rows = inputs(seed, seed % 4, bool(i % 2))
            def episode(serial):
                actor = dict(mode="pair", weights=[0.] * 3, seed=seed,
                             signed_pair=None if serial is None else [serial, serial])
                cfg = study["matrix"]["cfg"](req, dict(spec, issuance_actor=actor,
                         block_verifier=True, receipt_scan=2, reuse_returns=True), True)
                return run(dict(cfg, generated_get_inputs=rows))
            leaf = episode(None)
            exact = run(dict(baseline=True, audit=True, generated_get_inputs=rows))
            for k in ("rhs", "writes", "resumes", "state_sha", "schedule", "runs", "events"):
                if leaf[k] != exact[k]:
                    raise ValueError((seed, k))
            actor = leaf["strict_named"]["issuance_actor"]
            page = actor["pair_pages"][0]
            if page[1:3] != [1, 143] or sum(p[:3] == page[:3] for p in actor["pair_pages"]) != 1:
                raise ValueError(("expected the unique initial Get", page))
            serial = page[3]
            full = episode(serial)
            verify(leaf, full)
            other = full["strict_named"]["issuance_actor"]
            if other["pair_pages"][0] != page or [s for s, _, yes in other["decisions"] if yes] != [serial]:
                raise ValueError("different action")
            _, features, _ = next(d for d in actor["decisions"] if d[0] == serial)
            paid = [study["packets"](d) for d in (leaf, full)]
            signed = full["strict_named"]["signed_commits"]
            if paid[0] - paid[1] != len({r[0] for r in signed}) or any(r[1] != serial for r in signed):
                raise ValueError("unattributed saving")
            linked, port_rows = context(rows)
            samples.append((features, int(linked), paid, port_rows))
    return samples


def experiment(args):
    train = collect(args, "dot-product", 64100, args.pairs * 2)
    test = collect(args, "sum-bits", 71100, args.pairs * 2)
    report = {}
    for name, width, include_context in (("old", 1, False), ("old_wide", 64, False),
                                 ("context", 1, True), ("context_wide", 64, True)):
        def data(rows):
            x = torch.tensor([f + ([c] if include_context else []) for f, c, _, _ in rows])
            y = torch.tensor([p[0] - p[1] for _, _, p, _ in rows], dtype=torch.float)
            return x, y
        x, y = data(train)
        torch.manual_seed(17)
        model = (torch.nn.Linear(x.shape[1], 1) if width == 1 else
                 torch.nn.Sequential(torch.nn.Linear(x.shape[1], width), torch.nn.Tanh(), torch.nn.Linear(width, 1)))
        opt = torch.optim.Adam(model.parameters(), lr=.03)
        for _ in range(400):
            opt.zero_grad()
            (model(x).flatten() - y).square().mean().backward()
            opt.step()
        xt, yt = data(test)
        with torch.no_grad():
            prediction = model(xt).flatten()
        take = prediction >= .5
        report[name] = dict(parameters=sum(p.numel() for p in model.parameters()),
                            paid=sum(p[int(choice)] for (_, _, p, _), choice in zip(test, take)),
                            signed=int(take.sum()), correct_gain=int((prediction.round() == yt).sum()),
                            mae=float((prediction-yt).abs().mean()))
    # All exposed token rows, including the subject itself. The read head
    # must learn which row type and port position predict productive signing.
    torch.manual_seed(17)
    reader = torch.nn.Sequential(torch.nn.Linear(4, 12), torch.nn.Tanh())
    head = torch.nn.Linear(12, 1)
    opt = torch.optim.Adam([*reader.parameters(), *head.parameters()], lr=.03)

    def encode(rows):
        toks = [torch.tensor(ports) for ports in rows]
        padded = torch.nn.utils.rnn.pad_sequence(toks, batch_first=True)
        valid = torch.arange(padded.shape[1])[None, :] < torch.tensor([len(t) for t in toks])[:, None]
        return padded, valid

    def score(batch):
        values, valid = batch
        state = reader(values).masked_fill(~valid[..., None], -torch.inf).amax(dim=1)
        return head(state).flatten()

    train_batch = encode([r[3] for r in train])
    for _ in range(400):
        opt.zero_grad()
        (score(train_batch) - y).square().mean().backward()
        opt.step()
    with torch.no_grad():
        prediction = score(encode([r[3] for r in test]))
    take = prediction >= .5
    report["learned_token_read"] = dict(
        parameters=sum(p.numel() for m in (reader, head) for p in m.parameters()),
        paid=sum(p[int(choice)] for (_, _, p, _), choice in zip(test, take)),
        signed=int(take.sum()), correct_gain=int((prediction.round() == yt).sum()),
        mae=float((prediction - yt).abs().mean()))
    program, plans, req, spec = study["setup"](args, "sum-bits")
    live_paid = live_signed = 0
    with study["src"].base.session(args.native, program, plans) as run:
        for i in range(len(test)):
            rows = inputs(71100 + i // 2, (71100 + i // 2) % 4, bool(i % 2))
            _, ports = context(rows)
            with torch.no_grad():
                margin = score(encode([ports])).item() - .5
            actor = dict(mode="first_context", seed=0, weights=[margin, 0., 0.])
            cfg = study["matrix"]["cfg"](req, dict(spec, issuance_actor=actor,
                     block_verifier=True, receipt_scan=2, reuse_returns=True), True)
            actual = run(dict(cfg, generated_get_inputs=rows))
            exact = run(dict(baseline=True, audit=True, generated_get_inputs=rows))
            for key in ("rhs", "writes", "resumes", "state_sha", "schedule", "runs", "events"):
                if actual[key] != exact[key]:
                    raise ValueError(("live vs exact", i, key))
            decisions = actual["strict_named"]["issuance_actor"]["decisions"]
            chosen = margin >= 0
            if not decisions or [r[2] for r in decisions] != [chosen]+[False]*(len(decisions)-1):
                raise ValueError(("wrong live action", i))
            if study["packets"](actual) != test[i][2][int(chosen)]:
                raise ValueError(("live vs same-input intervention", i))
            live_signed += chosen
            live_paid += study["packets"](actual)
    report["learned_token_read"].update(live_paid=live_paid, live_signed=live_signed)
    report.update(generated_per_split=len(test), leaf_paid=sum(p[0] for _, _, p, _ in test),
                  full_paid=sum(p[1] for _, _, p, _ in test),
                  test_outcomes=dict(Counter(f"context={c},gain={p[0]-p[1]}" for _, c, p, _ in test)))
    (args.out/"context-credit.json").write_text(json.dumps(report, indent=2)+"\n")
    print(report)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for field in ("exp", "native", "out"):
        p.add_argument(field, type=Path)
    p.add_argument("--pairs", type=int, default=32)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(1)
    experiment(args)
