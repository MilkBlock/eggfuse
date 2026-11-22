"""Flip one source R scalar and observe both policy addresses and native successor use."""
import argparse
from collections import Counter
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

import torch

from first_reader import fit
from policy import Pointer, TABLES
from study import compare, exact, rollout, semantic


def check(args):
    torch.set_num_threads(1)
    policy = Pointer().eval()
    policy.load_state_dict(torch.load(args.checkpoint, map_location="cpu", weights_only=True))
    policy.first_reader = fit(1703, 0, True, True, "productive", 600, True)
    template = Path(__file__).with_name("family.egg").read_text()
    totals = Counter()
    with TemporaryDirectory() as folder:
        root = Path(folder)
        plans = root / "plans.json"
        plans.write_text("[]")
        for offset in range(8):
            left, other, distractor = [(offset + i) % 8 for i in (0, 1, 3)]
            previous = None
            for target in (left, other):
                facts = f"(L {left}) (L {other}) (R {distractor}) (R {target}) (Tag 0)"
                source = root / f"case-{offset}-{target}.egg"
                source.write_text(template[:template.index("(L 1)")] + facts + "\n" +
                                  template[template.index("(run-schedule"):])
                bundle = source.with_suffix("")
                subprocess.run([args.compiler, "compile", "--source", source, "--output", bundle],
                               check=True, capture_output=True)
                program = bundle / "program.json"
                trace = []
                learned = rollout(args.native, program, policy, "learned", read_trace=trace)
                leaf = rollout(args.native, program, policy, "leaf")
                reference = exact(args.reference, program, plans)
                for result in (learned, leaf):
                    if result["rejected"] or not semantic(compare(result, reference)):
                        raise ValueError((offset, target, "native divergence"))
                if [role for role, _, _ in trace] != ["left", "right"]:
                    raise ValueError(("retry or missing parent", trace))
                for role, address, features in trace:
                    if not features[TABLES.index("L" if role == "left" else "R")] or not features[len(TABLES)+target]:
                        raise ValueError((role, address, target))
                first_address = trace[0][1]
                if previous == first_address:
                    raise ValueError("changing the R value did not change the chosen L address")
                previous = first_address
                if learned["uses"] != [[1, True]] or leaf["uses"] != [[0, False]]:
                    raise ValueError("successor did not follow the actual issuing owner")
                saved = leaf["paid"] - learned["paid"]
                if saved != 1 or learned["internal"] != 1:
                    raise ValueError(("unrealized takeover", saved))
                totals.update(cases=1, saved=saved, learned_packets=learned["paid"],
                              reads=learned["queries"], scores=learned["pointer_scores"],
                              receiver_reads=learned["receiver_reads"], first_encoded=learned["first_encoded"],
                              strict_equal=int(all(compare(learned, reference).values())))
    print(dict(totals))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("compiler", "native", "reference", "checkpoint"):
        parser.add_argument(name, type=Path)
    check(parser.parse_args())
