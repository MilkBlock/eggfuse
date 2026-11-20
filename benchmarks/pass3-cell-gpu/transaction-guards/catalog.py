"""Validate every compiled read-only guard against the source slots independently."""

import json


def validate(rule_program, parent_plan, shipped, tables):
    query = rule_program["query"]
    ordered = parent_plan["ins"]
    parents = [entry[0] for entry in ordered if entry[1]]
    suffix = {entry[0] for entry in ordered if not entry[1]}
    out = []
    for atom, table, owner, width, compares in shipped:
        terms = query[atom]["args"]
        assert atom in suffix and tables[table]["name"] == query[atom]["call"]["table"]
        assert len(terms) == width + 1
        available = (
            set()
            if owner is None
            else {a["slot"] for a in query[parents[owner]]["args"] if "slot" in a}
        )
        assert all(
            "slot" not in term or term["slot"] in available for term in terms[:-1]
        )
        if compares:
            assert "slot" not in terms[-1] or terms[-1]["slot"] in available
        out.append(
            {
                "atom": atom,
                "table": tables[table]["name"],
                "owner_atom": None if owner is None else parents[owner],
                "key_arity": width,
                "checks_result": compares,
            }
        )
    return out


def check(bundle, shipped):
    recipe = json.loads((bundle / "program.json").read_bytes())["recipe"]
    plans = json.loads((bundle / "plans.json").read_bytes())
    return {
        rid: validate(
            recipe["rules"][int(rid)], plans[int(rid)], v["guards"], recipe["tables"]
        )
        for rid, v in shipped.items()
    }
