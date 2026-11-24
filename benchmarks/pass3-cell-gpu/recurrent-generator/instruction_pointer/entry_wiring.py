"""Read B's template options from the existing RipSat graph network."""
from argparse import ArgumentParser
from pathlib import Path
import torch
from actor import rotate
from receipt_bake import read
from ripsat_policy import CellScorer, GraphBank
from ripsat_layout import signatures
from rule_read import load_actor


@torch.no_grad()
def compile_codes(program, manifest, weights, checkpoint):
    if signatures(program) != manifest["signatures"]:
        raise ValueError("graph compilation requires the catalog's donor Recipe")
    actor = load_actor(weights, True).eval()
    cat = actor.catalog_type(program, integer_parameters=True)
    nodes = actor.template_graph(cat)
    model = CellScorer(actor.width).eval()
    model.load_state_dict(torch.load(checkpoint, weights_only=True)["model"])
    layouts = manifest["layouts"]
    # Each primitive is represented by exactly its root step. Keep the pairs
    # aligned when target-program structural linking drops unrelated layouts.
    bank = GraphBank(layouts + [[u[0]] for u in layouts], cat, nodes)
    baked, primitive = bank.encode(model).chunk(2)
    return dict(baked=baked, primitive=primitive, structural_keys=manifest["structural_keys"])


def terminal_codes(graphs, role):
    # Keep BranchNet's original 30 static coordinates and all 32 graph
    # coordinates, folding the final pair into the first pair without parameters.
    role_ids = torch.full((len(graphs),), role + 1)
    code = rotate(graphs, role_ids)
    folded = code[:, :30].clone()
    folded[:, :2] += code[:, 30:]
    return folded.numpy()


def use_wiring(family, compiled):
    if family.structural_keys != compiled["structural_keys"]:
        raise ValueError("compiled graph readout belongs to a different catalog")
    for (rule, role), previous in family.codes.items():
        ids = family.menu[rule]
        primitive = compiled["primitive"][ids]
        if not torch.allclose(primitive, primitive[:1].expand_as(primitive), atol=1e-5):
            raise ValueError("linked family has distinct primitive roots")
        graph = torch.cat([primitive[:1], compiled["baked"][ids]])
        family.codes[rule, role] = terminal_codes(graph, role)
        if family.codes[rule, role].shape != previous.shape:
            raise ValueError("incompatible B terminal input")


if __name__ == "__main__":
    p = ArgumentParser()
    for k in ("program", "catalog", "actor", "gnn", "out"):
        p.add_argument(k, type=Path)
    a = p.parse_args()
    torch.set_num_threads(1)
    codes = compile_codes(read(a.program), read(a.catalog), a.actor, a.gnn)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    torch.save(codes, a.out)
