"""Exact FP32 key/query collisions on witnessed bindings, before the copy and owner routes."""

from collections import Counter, defaultdict

from address_corpus import files, read_state
from draft_results import csvfile
from parallel_budget import args


def run(a):
    rows = []
    for f in files(a, "eval"):
        s = read_state(f)
        counts = defaultdict(Counter)
        for tab, d in s["domains"].items():
            ks = [v.tobytes() for v in d["keys"]]
            freq = Counter(k for k, live in zip(ks, d["live"], strict=True) if live)
            qs = [v.tobytes() for v in d["queries"]]
            qs_count = Counter(qs)
            for _, _, steps in s["tokens"]:
                for j, (domain, i, y) in enumerate(steps):
                    if domain != tab or y < 0:
                        continue
                    m = counts["template" if j == 0 else "first" if j == 1 else "later"]
                    m["targets"] += 1
                    m["indistinguishable_live_key"] += int(freq[ks[y]] > 1)
                    m["largest_key_tie"] = max(m["largest_key_tie"], freq[ks[y]])
                    m["identical_query_other_prefix"] += int(qs_count[qs[i]] > 1)
        for role, c in counts.items():
            rows.append(dict(case=s["case"], run=s["run"], role=role, **c))
    csvfile(a.out / "alias.csv", rows)


if __name__ == "__main__":
    run(args().parse_args())
