"""Exercise typed source/native checks below the independent file-provenance pins."""
import argparse
import copy
import json
from pathlib import Path
from runpy import run_path
import mutations

HERE=Path(__file__).resolve().parent
PROOF=HERE.parent/"ripsat-strict-programs"


def run(evidence, donor):
    manifest=json.loads(evidence.read_bytes())
    item=next(s for s in manifest["donors"]["dot-product"]["samples"]
              if s["sample_id"]=="dot-product-p143-o1-c55-full")
    def path(file):
        return evidence.parent/item["artifacts"][file]["path"]
    def read(file):
        return json.loads(path(file).read_bytes())
    source=run_path(str(PROOF/"source_proof.py"))
    native=run_path(str(PROOF/"native_proof.py"))
    recipe=source["Recipe"](donor)
    packet=read("origin.json");origin=packet["sample"];profile=packet["profile"]
    proof,_=source["verify_origin"](recipe,origin)
    entry=path("entry.egg").read_text()
    records=[read("native/"+name) for name in (
        "ripen.json","initial-state.json","saturated-rule-composition.json","history.json","acceptance.json")]
    def investigate(data):
        return native["check_native"](recipe,origin,profile,entry,*data,proof)
    positive=investigate(records)
    assert positive["native_consumer_reads"]
    result={"native_positive":{"producer":positive["history_producer_occurrences"],
                              "consumer":positive["native_consumer_reads"],
                              "local_args":positive["local_args"],"local_result":positive["local_result"]},
            "rejections":{}}
    # A consumer-history failure may preserve a separately derived producer
    # return. A default authorizing link must actually disappear in that case.
    cases=(
        ("both_graphs_observation_only", (1,2), mutations.observation_only),
        ("no_source_ordered_return", (2,), mutations.foreign_swapped_row),
        ("unjustified_local_alias", (2,), mutations.unexpected_local_alias),
        ("wrong_source_grounding", (0,), mutations.foreign_grounded_program),
        ("missing_native_trace", (3,), mutations.missing_native_application),
        ("wrong_producer_prerequisite", (3,), mutations.wrong_native_read_dependency),
        ("wrong_produced_class", (3,), mutations.wrong_produced_class),
        ("disconnected_applications", (3,), mutations.disconnected_native_applications),
        ("wrong_consumer_fact", (3,), mutations.wrong_consumer_native_read),
    )
    for name,indices,operator in cases:
        data=copy.deepcopy(records)
        for i in indices:operator(data[i])
        try:
            remaining=investigate(data)
        except ValueError as err:
            result["rejections"][name]=str(err)
        else:
            assert name in ("disconnected_applications","wrong_consumer_fact") and not remaining["native_consumer_reads"],name
            result["rejections"][name]="no certified subsequent consumer read"
    for name,operator in (
        ("no_explicit_root_parent",mutations.missing_named_input),("forged_op",mutations.coherent_wrong_op),
        ("wrong_run_order",mutations.wrong_source_run),("wrong_return_version",mutations.wrong_origin_version)):
        bad=copy.deepcopy(packet);operator(bad)
        try:source["verify_origin"](recipe,bad["sample"])
        except ValueError as err:result["rejections"][name]=str(err)
        else:raise AssertionError(name)
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("evidence","donor","out"):p.add_argument(name,type=Path)
    a=p.parse_args();data=run(a.evidence,a.donor)
    a.out.write_text(json.dumps(data,indent=2)+"\n")
    print(len(data["rejections"]),"independent proof-layer mutations rejected.")
