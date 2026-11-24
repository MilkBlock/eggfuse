"""Counterfactual training grammars with distinct arities and dependency wiring."""

import re
from recursive_corpus import grammar

# Same parse semantics, with distinct instruction graphs and scaled positions.
TRAIN_LAYOUTS = {
    "left": (2, "(+ (+ s p1) p1)"),
    "twice": (4, "(+ s (* (* p1 2) 2))"),
    "fork": (5, "(+ (+ s (* p1 2)) (* p1 3))"),
    "swap": (5, "(+ (* p1 3) (+ (* p1 2) s))"),
}
BLIND_LAYOUT = {"held": (7, "(+ (* 4 p1) (+ s (* 3 p1)))")}


def sources(src):
    for label, (stride, expr) in (TRAIN_LAYOUTS | BLIND_LAYOUT).items():
        for seed in [11901371] if label in BLIND_LAYOUT else [17118, 17119, 17120]:
            text = re.sub(
                r"\(getString (\d+)\)",
                lambda m: f"(getString {int(m[1]) * stride})",
                grammar(seed),
            )
            source = src.replace("(+ s p1)", expr)
            yield f"grammar-benefit-{label}-{seed}", source + text
            if seed == 17120 and label in ("twice", "fork"):
                words = [
                    line
                    for line in text.splitlines()
                    if line.startswith("(set (getString")
                ]
                distance = (len(words) + 1) * stride
                repeats = [
                    re.sub(
                        r"getString (\d+)",
                        lambda m: f"getString {int(m[1]) + j * distance}",
                        w,
                    )
                    for j in range(1, 9)
                    for w in words
                ]
                yield (
                    f"grammar-benefit-large-{label}-{seed}",
                    source
                    + text.replace("(run 10000)", "\n".join(repeats) + "\n(run 10000)"),
                )

    # Extrapolation beyond the four-instruction training maximum, with a
    # separate seed. Do not include this layout in the fitting registry.
    stride = 7
    expr = "(+ (* 2 (+ p1 (* 2 p1))) (+ s p1))"
    text = re.sub(
        r"\(getString (\d+)\)",
        lambda m: f"(getString {int(m[1]) * stride})",
        grammar(11901379),
    )
    yield "grammar-benefit-held-deep-11901379", src.replace("(+ s p1)", expr) + text
