#!/usr/bin/env python3
"""Replay expression proofs independently of runtime roots and key indexes.

Source equalities are the trusted inputs. Every congruence step must be justified
by earlier inputs/steps; the final 'satisfied' bits are never premises. This is
an audit checker, not an untrusted-program loader or a source-rule verifier.
"""
import argparse
import copy
import json
from pathlib import Path


def verify(data):
    apps, eqs, cells = (data[k] for k in ("applications", "equalities", "cells"))
    parents = {}

    def root(x):
        while x in parents:
            x = parents[x]
        return x

    def equal(a, b):
        return root(a) == root(b)

    def union(a, b):
        a, b = root(a), root(b)
        if a != b:
            parents[max(a, b)] = min(a, b)

    seen, sources, last_epoch = set(), 0, 0
    for proof in data["proofs"]:
        assert proof["epoch"] >= last_epoch, "proof crossed a source barrier backwards"
        last_epoch = proof["epoch"]
        if proof["kind"] == "source":
            union(*eqs[proof["equality"]]["endpoints"])
            sources += 1
            continue
        assert proof["kind"] == "congruence"
        i = proof["cell"]
        assert i not in seen, "cell completed twice"
        c = cells[i]
        left, right = (apps[j] for j in c["applications"])
        assert left["table"] == right["table"]
        a, b = left["fields"], right["fields"]
        assert len(a) == len(b)
        ports = []
        for x, y in zip(a[:-1], b[:-1]):
            if "Eq" in x:
                assert "Eq" in y
                assert equal(x["Eq"], y["Eq"]), "ungrounded congruence premise"
                ports.append(sorted((x["Eq"], y["Eq"])))
            else:
                assert x == y, "unequal primitive fields"
        assert [eqs[j]["endpoints"] for j in c["ports"]] == ports
        output = eqs[c["output"]]["endpoints"]
        assert output == sorted((a[-1]["Eq"], b[-1]["Eq"]))
        assert c["completed"] == proof["epoch"] and c["born"] <= proof["epoch"]
        union(*output)
        seen.add(i)
    for e in eqs:
        assert e["satisfied"] == equal(*e["endpoints"]), "incorrect equality state"
        assert not e["proposed"] or e["satisfied"], "uncommitted proposal at audit barrier"
    for i, c in enumerate(cells):
        missing = {j for j in c["ports"] if not equal(*eqs[j]["endpoints"])}
        assert c["remaining"] == len(missing)
        assert (i in seen) == (c["completed"] is not None) == (not missing)
    return {"applications": len(apps), "equalities": len(eqs), "cells": len(cells),
            "sources": sources, "completed": len(seen), "waiting": len(cells) - len(seen)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("audit", type=Path)
    ap.add_argument("--reject-missing-sources", action="store_true")
    args = ap.parse_args()
    data = json.loads(args.audit.read_text())
    result = verify(data)
    if args.reject_missing_sources:
        damaged = copy.deepcopy(data)
        damaged["proofs"] = [p for p in damaged["proofs"] if p["kind"] != "source"]
        try:
            verify(damaged)
        except AssertionError:
            result["missing_sources_rejected"] = True
        else:
            raise AssertionError("fixture did not require any source equality")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
