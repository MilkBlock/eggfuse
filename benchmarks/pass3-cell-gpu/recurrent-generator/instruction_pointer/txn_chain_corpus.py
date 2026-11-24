"""CYK with strided input coordinates. Parse lengths still count tokens."""

import re

from recursive_corpus import grammar

CHAIN_TRAIN = ("grammar-stride2-17118", "grammar-stride3-17119")
CHAIN_VALID = "grammar-stride2-17122"
CHAIN_BLIND = "grammar-stride3-split-7300147"


def chain_sources(src):
    cases = [
        (CHAIN_TRAIN[0], 17118, 2, "(+ s (* p1 2))"),
        (CHAIN_TRAIN[1], 17119, 3, "(+ (* 3 p1) s)"),
        (CHAIN_VALID, 17122, 2, "(+ s (* p1 2))"),
        (CHAIN_BLIND, 7300147, 3, "(+ s (+ (* p1 2) p1))"),
    ]
    sources = {}
    for name, seed, stride, start in cases:
        if src.count("(+ s p1)") != 2:
            raise ValueError("expected two span productions")
        text = re.sub(
            r"\(getString (\d+)\)",
            lambda m: f"(getString {int(m[1]) * stride})",
            grammar(seed),
        )
        sources[name] = src.replace("(+ s p1)", start) + text
    return sources
