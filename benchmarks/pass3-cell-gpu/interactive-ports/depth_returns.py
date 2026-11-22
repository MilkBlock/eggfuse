"""Fit issuance depth and independent successor decisions on paired native returns."""
import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import subprocess
import torch

from first_reader import fit
from policy import Pointer, WIDTH
from study import compile_case, exact, rollout, semantic, compare


def train_choice(observations, inputs, actions):
    head = torch.nn.Linear(inputs, actions)
    optimizer = torch.optim.Adam(head.parameters(), lr=.06)
    x = torch.tensor([x for x, _ in observations])
    returns = torch.tensor([r for _, r in observations], dtype=torch.float)
    for _ in range(250):
        loss = -(head(x).softmax(1) * returns).sum(1).mean()
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()
    return lambda features: int(head(features).argmax())


def reward(result, reference):
    # Enforce correctness before giving credit for fewer external tokens.
    if not semantic(compare(result, reference)) or result["rejected"]:
        return -32
    return -result["paid"]


def main(args):
    torch.manual_seed(1703)
    torch.set_num_threads(1)
    policy = Pointer().eval()
    policy.load_state_dict(torch.load(args.checkpoint, weights_only=True, map_location="cpu"))
    policy.first_reader = fit(1703, 0, True, True, "productive", 600, True)
    with TemporaryDirectory() as directory:
        root = Path(directory)
        plans = root / "plans.json"
        plans.write_text("[]")
        def case(seed, kind):
            program = compile_case(args.compiler, root, seed, kind)
            return program, exact(args.reference, program, plans)
        def run(program, depth, skip):
            return rollout(args.native, program, policy, "learned", depth=depth, finish_skip=skip)
        train = [case(2300+i, ("fresh", "reuse")[i%2]) for i in range(12)]
        finish = []
        for program, reference in train:
            for depth in (1, 2, 3):
                send, skip = (run(program, depth, action) for action in (False, True))
                features = send["finish_features"]
                if features is None or features != skip["finish_features"]:
                    raise ValueError("finish decision point differs between forks")
                finish.append((features, [reward(send, reference), reward(skip, reference)]))
        stop = train_choice(finish, 2, 2)
        roots = []
        for program, reference in train:
            arms = [run(program, d, stop) for d in (1, 2, 3)]
            if not all(r["root_features"] == arms[0]["root_features"] for r in arms):
                raise ValueError("root forks do not share input")
            roots.append((arms[0]["root_features"], [reward(r, reference) for r in arms]))
        choose = train_choice(roots, WIDTH, 3)
        totals = {}
        for i in range(48):
            program, ref = case(4800+i, ("absent","fresh","reuse")[(i//3+i)%3])
            for name, depth, skip in (("leaf",1,False),("previous",2,False),
                                      ("fixed_three",3,True),("learned",lambda x: 1+choose(x),stop)):
                r = run(program, depth, skip)
                if reward(r,ref) == -32:
                    raise ValueError((i,name,compare(r,ref),r["rejected"]))
                births = r["source"]["final_births"]
                # This family has no deletion/union; source births are an independent numerator.
                expected = {e[4] for events in ref["events"] for e in events if e[0]=="birth"}
                if births != len(expected):
                    raise ValueError(("birth numerator", i, name, births, len(expected)))
                row = totals.setdefault(name, dict(final_births=0, paid=0, internal=0, strict=0))
                row["final_births"] += births
                row["paid"] += r["paid"]
                row["internal"] += r["internal"]
                row["strict"] += int(all(compare(r,ref).values()))
        # A finish rule with an additional guard falls outside the certified
        # unary route. Its standalone packet can still be checked by Rust.
        fixture = Path(__file__).with_name("family.egg").read_text()
        original = "((= c (C p))) ((Use c))"
        if fixture.count(original) != 1:
            raise ValueError("unexpected finish query")
        guarded = root / "guarded.egg"
        guarded.write_text(fixture.replace(original, "((= c (C p)) (< 0 1)) ((Use c))"))
        bundle = root / "guarded"
        subprocess.run([args.compiler, "compile", "--source", guarded, "--output", bundle],
                       check=True, capture_output=True)
        program = bundle / "program.json"
        ref = exact(args.reference, program, plans)
        short, long = run(program, 2, False), run(program, 3, True)
        if reward(short, ref) == -32 or not long["rejected"] or semantic(compare(long, ref)):
            raise ValueError("uncertified third step escaped verification")
    report = dict(guarded_long_rejections=long["rejected"], train_programs=len(train), finish_forks=len(finish), root_forks=len(roots),
                  test_programs=48, totals=totals)
    args.out.write_text(json.dumps(report,indent=2)+"\n")
    print(report)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("compiler","native","reference","checkpoint","out"):
        p.add_argument(name, type=Path)
    main(p.parse_args())
