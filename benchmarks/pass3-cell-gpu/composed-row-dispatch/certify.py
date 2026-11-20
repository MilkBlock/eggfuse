"""Bake a constant row action when binary32 score intervals prove strict dominance."""
from fractions import Fraction
from hashlib import sha256
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
UNIT = Fraction(1, 1 << 24)
TINY = Fraction(1, 1 << 149)
BOX = ((0, 6), (0, 2), (0, 2), (1, 1), (-1, 1))


def scalar(v):
    bits = struct.pack("<f", v)
    numeric = struct.unpack("<f", bits)[0]
    if not math.isfinite(numeric):
        raise ValueError("non-finite coefficient")
    return Fraction(numeric)


def affine(weights, bias, features):
    """Real interval and an absolute error bound for the ordered float dot."""
    if len(weights) != len(features):
        raise ValueError("affine layer width mismatch")
    lo = hi = bias
    err = Fraction(0)
    for w, (l, u) in zip(weights, features):
        a, b = sorted((w * l, w * u))
        lo, hi = lo + a, hi + b
        # First product roundoff, then accumulation roundoff (including previous error).
        err += UNIT * max(abs(a), abs(b)) + TINY
        magnitude = max(abs(lo), abs(hi)) + err
        if max(abs(a), abs(b), magnitude) >= 2 ** 120:
            raise ValueError("outside finite binary32 proof range")
        err += UNIT * magnitude + TINY
    return lo, hi, err


def certify(weights):
    w = [[scalar(v) for v in row] for row in weights["hidden"]]
    b = list(map(scalar, weights["bias"]))
    d = [[scalar(v) for v in row] for row in weights["decisions"]]
    o = list(map(scalar, weights["offsets"]))
    if len(w) != len(b) or len(d) != 8 or len(o) != 8:
        raise ValueError("unexpected row policy shape")
    hidden = []
    for col, bias in zip(w, b):
        lo, hi, err = affine(col, bias, BOX)
        # Only tanh's sign and range are used. Magnitudes and training data are unnecessary.
        hidden.append((0 if lo >= err else -1, 0 if hi <= -err else 1))
    errors = [affine(col, bias, hidden)[2] for col, bias in zip(d, o)]
    margins = []
    for i in range(8):
        lower = []
        for j in range(8):
            if j == i:
                continue
            # Both outputs use the same hidden float vector. Keep that dependence.
            gap = o[i] - o[j]
            for a, b, (l, u) in zip(d[i], d[j], hidden):
                gap += min((a - b) * l, (a - b) * u)
            lower.append(gap - errors[i] - errors[j])
        margins.append(min(lower))
    exact = next((i for i, margin in enumerate(margins) if margin > 0), None)
    canonical = json.dumps(weights, sort_keys=True, separators=(",", ":")).encode()
    return dict(weights_sha256=sha256(canonical).hexdigest(), input_bounds=BOX, hidden_bounds=hidden,
                margin_bounds=list(map(float, margins)), action=exact)


def lower_shared_one(rows, single_config):
    """Return the original dispatch configuration when the certified features or proof are absent."""
    model = single_config.get("model") or {}
    if (model.get("certified_inputs") is not True or "action" in rows or "policy" not in rows
            or rows.get("capture") or rows.get("max_rows") not in (1, 2, 4, 8)):
        return rows
    if certify(rows["policy"])["action"] != 4:
        return rows
    out = dict(rows)
    del out["policy"]
    out.update(action=4, max_rows=1, workers=1)
    return out


def evidence():
    archive = json.loads((HERE.parent / "adaptive-row-policy/checkpoints.json").read_bytes())
    result = {}
    for seed in (1703, 1709):
        for method in ("policy-gradient", "supervised"):
            key = f"{seed}-{method}-8-8.json"
            result[key] = certify(archive[key]["weights"])
        trained = archive[f"{seed}-policy-gradient-8-8.json"]["weights"]
        # Force a tie across actions. Strict certification must decline.
        tied = dict(trained, decisions=[trained["decisions"][0]] * 8,
                    offsets=[trained["offsets"][0]] * 8)
        assert certify(tied)["action"] is None
        spec = dict(policy=trained, max_rows=8, workers=8, verify=2, batch=True)
        certified = dict(model=dict(certified_inputs=True))
        assert lower_shared_one(spec, certified) == dict(action=4, max_rows=1, workers=1, verify=2, batch=True)
        assert lower_shared_one(spec, {}) is spec
        capture = dict(spec, capture=True)
        assert lower_shared_one(capture, certified) is capture
        undecidable = dict(spec, policy=tied)
        assert lower_shared_one(undecidable, certified) is undecidable
    return result


if __name__ == "__main__":
    print(json.dumps(evidence(), indent=1))
