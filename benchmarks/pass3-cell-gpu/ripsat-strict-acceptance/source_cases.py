"""Exercise real compiled source operands without relying on an adapter's candidate selection."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
module = importlib.util.spec_from_file_location("strict_source", HERE.parent/"ripsat-strict-programs/source_proof.py")
proof = importlib.util.module_from_spec(module)
module.loader.exec_module(proof)


def denied(recipe, route, expected):
    try:
        recipe.certify(*route)
    except proof.Refusal as exc:
        assert str(exc) == expected, (route, expected, str(exc))
        return str(exc)
    raise AssertionError(f"Authorized unsafe route {route}")


def run(donor, small, state):
    recipe = proof.Recipe(donor)
    assert recipe.certify(143,1,55,0)["table"] == "Single"
    positive = proof.Recipe(small)
    rid = {r["metadata"]["name"]: i for i,r in enumerate(positive.rules)}
    make = rid["independent_pair"]
    op = next(i for i,e in enumerate(positive.rules[make]["effects"]) if e.get("call",{}).get("table")=="Pair")
    assert positive.certify(make,op,rid["unguarded"],0)["table"] == "Pair"
    checks = {
        # Native Pass-3 rule 60 reads both Single and Add-Gets; op 1 supplies only Single.
        "missing_independent_source_premise": denied(recipe, (143,1,60,0), "external_lhs_or_guard_not_implemented"),
        # The same Pair row would satisfy this consumer in a particular run with x≡y only.
        "constructor_set_has_no_static_return": denied(recipe, (55,1,143,0), "not_a_returning_constructor"),
        "instance_equality_as_template_theorem": denied(positive, (make,op,rid["equal_arguments_only"],0),
                                                        "alias_guard_requires_runtime_equality"),
    }
    rows = json.loads(state.read_bytes())["rows"]
    def facts(table):
        return [[a["eq"] for a in r["values"]] for r in rows if r["table"]==table and not r["subsumed"]]
    pairs=facts("Pair");assert len(pairs)==2 and sum(a==b for a,b,_ in pairs)==1
    assert {a[0] for a in facts("Always")}=={p for a,b,p in pairs}
    assert {a[0] for a in facts("EqualOnly")}=={p for a,b,p in pairs if a==b}
    return {"local_source_execution":{"pairs":len(pairs),"unguarded":len(facts("Always")),
                                    "alias_guarded":len(facts("EqualOnly"))},"passed_positive": ["Jacobi-1d 143[1] → 55[0]", "Pair(x,y) → unguarded"],
            "rejected": checks}


if __name__ == "__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("donor",type=Path);p.add_argument("compiled_fixture",type=Path)
    p.add_argument("state",type=Path);p.add_argument("--out",type=Path);a=p.parse_args()
    data=run(a.donor,a.compiled_fixture,a.state)
    if a.out:a.out.write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps(data,ensure_ascii=False))
