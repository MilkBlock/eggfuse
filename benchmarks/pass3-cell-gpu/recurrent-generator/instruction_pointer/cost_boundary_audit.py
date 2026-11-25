"""Observation-only source probes for the frozen 0e480c54 candidate access path.

Insert counters before existing statements in disposable in-process copies. A
missing or ambiguous probe fails the audit. No on-disk runtime source is edited.
"""

import argparse
import json
from collections import Counter
from inspect import getsource
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

import numpy as np
import torch

from cost_bake import CostBake, LearnedCostEntries
from event_addresses import Bank, Directory
from event_generator import EventGenerator
from field_retrieval import FieldIndex
from recursive_ripsat_study import setup_policy
from structure_runtime import StructureEntries
from transaction_native import execute

TARGET = (883892, 2, 303)
COUNTS = Counter()
TRACE = {}


def inject(cls, method, insertions):
    original = getattr(cls, method)
    src = dedent(getsource(original))
    lines = src.splitlines()
    for anchor, probe in insertions:
        ix = [i for i, line in enumerate(lines) if line.lstrip().startswith(anchor)]
        if len(ix) != 1:
            raise RuntimeError(f"{cls.__name__}.{method}: {anchor!r} has {len(ix)} matches")
        i = ix[0]
        indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
        lines[i:i] = [indent + line for line in probe.splitlines()]
    space = {**original.__globals__, "C": COUNTS, "capture_choice": capture_choice, "TRACE": TRACE}
    exec(compile("\n".join(lines) + "\n", f"<audit:{cls.__name__}.{method}>", "exec"), space)
    setattr(cls, method, space[original.__name__])


def capture_choice(owner, mem, r, j, wm, source, ix, logits):
    if (owner.txn.run, r, j) != (541, 498, 4):
        return False
    pos = source.positions.get(TARGET[:2])
    at = np.flatnonzero(ix == pos) if pos is not None else []
    if not len(at):
        return False
    i = int(at[0])
    if tuple(source.rows[pos]) != TARGET:
        return False
    TRACE.update(
        run=541,
        rule=r,
        entry_role=j,
        source=list(TARGET),
        watermark=int(wm),
        page_roots=len(ix),
        source_position=int(pos),
        page_offset=i,
        logits=logits[i].tolist(),
        selected=int(logits[i].argmax()),
        device=str(logits.device),
        order=list(mem.order(r, j)),
        role_scans=[],
    )
    return True


def install():
    inject(
        Directory,
        "bank",
        [
            ("v = self.rd.versions[t]", 'C["bank_generation_lookups"] += 1'),
            ("self.cache[t] = v, Bank", 'C["bank_rebuilds"] += 1'),
        ],
    )
    inject(
        Bank,
        "__init__",
        [
            (
                "self.positions =",
                'C["bank_rows_copied"] += len(self.ports)\nC["position_map_writes"] += len(self.ports)',
            ),
            ("self.version_order =", 'C["version_sort_input_rows"] += len(self.ports)'),
            ("self.versions =", 'C["max_array_version_gathers"] += len(self.ports)'),
            (
                "self.codes = np.array",
                'C["bank_key_means"] += len(self.ports)\nC["bank_field_codes_copied"] += sum(map(len,self.codes))',
            ),
        ],
    )
    inject(
        Bank,
        "postings",
        [
            ("if col not in", 'C["field_posting_cache_probes"] += 1'),
            (
                "code = self.codes",
                'C["field_posting_builds"] += 1\nC["posting_sort_and_histogram_rows_each"] += len(self.ports)',
            ),
        ],
    )
    inject(
        Directory,
        "window",
        [
            ("dst = self.bank", 'C["schema_link_lookups"] += 1'),
            (
                "return order, offsets",
                'C["field_code_gathers"] += len(paths)\nC["bucket_offset_reads"] += 3*len(paths)',
            ),
        ],
    )
    inject(
        FieldIndex,
        "advance_rows",
        [
            ("previous = self.rows.get", 'C["published_row_lookups"] += 1'),
            ("if value == old_hashes", 'C["published_scalar_hash_comparisons"] += 1'),
            (
                "raw = torch.from_numpy",
                'C["field_encodings"] += len(changed)\nC["lsh_sign_comparisons"] += 8*len(changed)',
            ),
        ],
    )
    inject(
        EventGenerator,
        "wake",
        [
            ("r, j = k", 'C["waiting_rule_role_lookups"] += 1'),
            (
                "if self.generation.get",
                'C["wake_generation_vector_probes"] += 1\nC["wake_role_generations_read"] += len(versions)',
            ),
            ("for a, v in list", 'C["waiting_items_scanned"] += len(waiting)'),
            (
                "if i is None or",
                'C["wake_position_lookups"] += 1\nC["wake_row_version_comparisons"] += int(i is not None)',
            ),
        ],
    )
    inject(
        EventGenerator,
        "run_snapshot",
        [
            ("legal = (refs", 'C["emit_parent_version_comparisons"] += refs.shape[0]*refs.shape[1]'),
            ("keep = logits >=", 'C["candidate_logit_comparisons"] += logits.numel()'),
            ("child = np.column_stack", 'C["child_path_i64_written"] += len(addr)*(depth+1)'),
            ("addr = pos if post", 'C["posting_address_gathers"] += len(pos) if post is not None else 0'),
        ],
    )
    inject(
        CostBake,
        "choose",
        [
            ("self.active = False", "self.traced=False"),
            ("self.cached.clear", 'C["discarded_fresh_indices"] += len(self.cached)'),
            (
                "chosen = logits.argmax",
                'self.traced=capture_choice(owner,mem,r,j,wm,source,ix,logits)\nC["two_option_decisions"] += len(ix)',
            ),
            (
                "if len(bank.versions)",
                'C["max_version_reads_and_compares"] += int(bool(len(bank.versions)))\nif self.traced:\n    TRACE["role_scans"].append([order[d],mem.roles[r][order[d]],len(bank.rows),int(bank.versions[-1]) if len(bank.versions) else None])',
            ),
        ],
    )
    inject(
        CostBake,
        "roots",
        [
            (
                "self.owner.count",
                'if self.traced:\n    TRACE["cut"]=self.cut\n    TRACE["closed_on_page"]=int(self.selected[ix].sum())',
            )
        ],
    )
    inject(
        CostBake,
        "window",
        [
            ("required = self.selected", 'C["window_root_mask_gathers"] += len(paths)'),
            ("required &=", 'C["prior_role_version_gathers_and_compares"] += len(paths)'),
            ("if key not in self.cached", 'C["fresh_index_cache_probes"] += 1'),
            (
                "fresh = bank.rows",
                'C["fresh_index_builds"] += 1\nC["fresh_build_version_reads_and_compares"] += len(listing)',
            ),
            (
                "self.cached[key] = (",
                'C["fresh_listing_i64_writes"] += len(listing)+int(fresh.sum())\nC["rank_i64_writes"] += 1+len(listing)',
            ),
            ("lo = cumulative", 'C["rank_array_i64_reads"] += 2*len(start)'),
        ],
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("data", type=Path)
    p.add_argument("store", type=Path)
    p.add_argument("arm", choices=["base", "frozen"])
    a = p.parse_args()
    torch.set_num_threads(1)
    install()
    state = torch.load(a.store / "structure-rl.pt", weights_only=True)
    _, _, policy, _ = setup_policy(
        a.data,
        a.store,
        "sum-divisors",
        state,
        True,
        policy_cls=StructureEntries if a.arm == "base" else LearnedCostEntries,
    )
    dest = a.store / "boundary"
    dest.mkdir(exist_ok=True)
    with TemporaryDirectory(dir=dest) as tmp:
        row = execute(a.data, "sum-divisors", study=policy, seconds=1500, series=tmp)
    old = json.loads((a.store / f"sum-divisors-{a.arm}-2.json").read_text())
    for k in ("state_sha", "runs", "paid", "signed_ops", "verdicts", "termination"):
        assert old[k] == row[k], k
    for k in ("visits", "parent_candidate_scores", "generated_templates", "generated_proofs"):
        assert old["work"][k] == row["work"][k], k
    output = {
        k: row[k]
        for k in (
            "state_sha",
            "runs",
            "paid",
            "signed_ops",
            "verdicts",
            "termination",
            "wall",
            "work",
            "native_verify_seconds",
        )
    }
    output.update(counters=COUNTS, event=TRACE)
    (dest / f"observed-{a.arm}.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
