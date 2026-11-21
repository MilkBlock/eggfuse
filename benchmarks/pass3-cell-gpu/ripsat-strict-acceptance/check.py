"""Automatic rejection tests for the RipSat evidence → strict neural library adapter."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ADAPTER = HERE.parent / "ripsat-strict-programs" / "compile.py"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")


def invoke(manifest, donors, target, output):
    assert not output.exists(), "each case must receive an empty output path"
    command = [sys.executable, str(ADAPTER), "--evidence", str(manifest)]
    for name, path in donors.items():
        command.extend(("--donor", f"{name}={path}"))
    command.extend(("--target", str(target), "--out", str(output)))
    proc = subprocess.run(command, capture_output=True, text=True)
    compiled = read(output) if output.is_file() else None
    return proc, compiled


def candidate_paths(library,key="strict_named"):
    if library is None:
        return set()
    setting = library[key]
    return {tuple(tuple(e) for e in path) for path in setting["library"]}


def require_rejection(label, attempt, forbidden):
    proc, report = attempt
    leaked = candidate_paths(report) & forbidden
    weak = candidate_paths(report,"strict_named_static_consumer") & forbidden if report else set()
    weak_allowed=label in ("disconnected_native_applications","wrong_later_consumer_read")
    if not weak_allowed:leaked|=weak

    if proc.returncode not in (0,1):raise AssertionError(f"{label}: unexpected compiler/usage error {proc.returncode}")
    if proc.returncode != 0 and report is not None:
        raise AssertionError(f"{label} wrote a partial library on an error")
    def reasons(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key in ("reason", "rejection", "error") and isinstance(value,str):yield value
                elif isinstance(value,(dict,list)):yield from reasons(value)
        elif isinstance(obj,list):
            for value in obj:yield from reasons(value)
    messages=sorted(set(reasons(report)))
    if proc.returncode and proc.stderr.strip():messages.append(proc.stderr.strip().splitlines()[-1])
    if "rejections" in (report or {}):messages.extend(k for k,v in report["rejections"].items() if v)
    messages=sorted(set(messages))
    return {"exit": proc.returncode, "authorized_paths": len(candidate_paths(report)),
            "forbidden_paths": len(forbidden),"static_consumer_paths":len(weak),"reasons":messages,"leaked_paths":[[list(e) for e in p] for p in sorted(leaked)]}


def copied_sample(evidence, sample_id):
    matches=[sample for donor in evidence["donors"].values()
             for sample in donor["samples"] if sample["sample_id"]==sample_id]
    assert len(matches)==1, sample_id
    return matches[0]


def replace_self_digest(node, old, new):
    """Rebind only an altered sample's own copied artifact references; never the supplied donor or target."""
    if isinstance(node,dict):
        return {k:replace_self_digest(v,old,new) for k,v in node.items()}
    if isinstance(node,list):
        return [replace_self_digest(v,old,new) for v in node]
    return new if node==old else node


def run_suite(args):
    import shutil
    import mutations
    donors=dict(item.split("=",1) for item in args.donor)
    donors={name:Path(path).resolve() for name,path in donors.items()}
    source_dir=args.evidence.resolve().parent
    if args.scratch.resolve().is_relative_to(source_dir):raise ValueError("scratch must be outside the source evidence directory")
    original=read(args.evidence)
    actual=[s for s in original["donors"]["dot-product"]["samples"] if s["sample_id"]=="dot-product-p143-o1-c55-full" and s["native_accepted"]]
    assert actual,"need a native Single return with a later consumed local application"
    selected=actual[0];sid=selected["sample_id"]
    mutation_cases=[
        ("stopped", "native/ripen.json", mutations.stopped),
        ("unfinished_round_with_saturated_label","native/ripen.json",mutations.unfinished_round),
        ("producer_scope_only","origin.json",mutations.producer_scope_only),
        ("observation_only", "native/saturated-rule-composition.json", mutations.observation_only),
        ("wrong_grounded_report_source", "native/ripen.json", mutations.foreign_grounded_program),
        ("wrong_ordered_port_same_cardinality", "native/saturated-rule-composition.json", mutations.foreign_swapped_row),
        ("local_alias_instead_of_second_input", "native/saturated-rule-composition.json", mutations.unexpected_local_alias),
        ("wrong_ground_literal", "native/saturated-rule-composition.json", mutations.foreign_ground_literal),
        ("missing_original_named_parent", "origin.json", mutations.missing_named_input),
        ("wrong_op", "origin.json", mutations.wrong_source_op),
        ("wrong_op_and_fact_id_rebound", "origin.json", mutations.coherent_wrong_op),
        ("wrong_but_later_source_run","origin.json",mutations.wrong_but_later_source_run),
        ("activation_same_run", "origin.json", mutations.wrong_source_run),
        ("wrong_consumer_fact_version", "origin.json", mutations.wrong_origin_version),
        ("local_history_application_missing", "native/history.json", mutations.missing_native_application),
        ("disconnected_native_applications","native/history.json",mutations.disconnected_native_applications),
        ("wrong_later_consumer_read","native/history.json",mutations.wrong_consumer_native_read),
        ("produced_port_resolves_to_another_class","native/history.json",mutations.wrong_produced_class),
        ("local_history_read_dependency_changed", "native/history.json", mutations.wrong_native_read_dependency),
    ]
    experiment={"source_manifest_sha":sha(args.evidence),"original_sample":sid,"attempts":{}}
    with tempfile.TemporaryDirectory(dir=args.scratch) as scratch_text:
        scratch=Path(scratch_text)
        def prepare(name,keep_sid=sid):
            folder=scratch/name
            shutil.copytree(source_dir,folder)
            manifest_path=folder/args.evidence.name
            evidence=read(manifest_path)
            for donor in evidence["donors"].values():
                donor["samples"]=[s for s in donor["samples"] if s["sample_id"]==keep_sid]
            record=copied_sample(evidence,keep_sid)
            for a in record["artifacts"].values():
                assert (folder/a["path"]).resolve().is_relative_to(folder.resolve())
            write(manifest_path,evidence)
            return folder,manifest_path,evidence,record
        def altered(rec,f,change,update=True):
            a=rec["artifacts"][f]
            path=folder/a["path"]
            old=sha(path)
            assert old==a["sha256"]
            change(path)
            if update:
                new=sha(path)
                assert new!=old
                for k in list(rec):
                    if k!="artifacts":rec[k]=replace_self_digest(rec[k],old,new)
                a["sha256"]=new
        folder,manifest,evidence,record=prepare("positive")
        proc,output=invoke(manifest,donors,args.target,folder/"library.json")
        assert proc.returncode==0,proc.stderr
        forbidden=candidate_paths(output)
        assert len(forbidden)==1,("isolation must produce an actual positive",output)
        experiment["positive_paths"]=[[list(e) for e in path] for path in sorted(forbidden)]
        noalias="dot-product-p446-o0-c446-full"
        folder,manifest,evidence,record=prepare("distinct_static_status",noalias)
        proc,secondary=invoke(manifest,donors,args.target,folder/"library.json")
        assert proc.returncode==0 and not candidate_paths(secondary),("producer-only history is static-consumer-only",secondary)
        experiment["producer_only_trace"]={"sample":noalias,"default_authorized":0,"static_consumer_programs":len(candidate_paths(secondary,"strict_named_static_consumer")),"rejections":secondary.get("rejections",{})}
        for label,filename,mutation in mutation_cases:
            folder,manifest,evidence,record=prepare(label)
            altered(record,filename,lambda p:mutations.edit(p,mutation))
            if filename=="origin.json":
                actual=read(folder/record["artifacts"][filename]["path"])["sample"]
                record["scope_mode"]=read(folder/record["artifacts"][filename]["path"])["profile"]["scope_mode"]
                for k in ("producer_op","consumer_atom","original_fact","original_version","relative_runs"):
                    record[k]=actual[k]
            write(manifest,evidence)
            trial=invoke(manifest,donors,args.target,folder/'library.json')
            experiment["attempts"][label]=require_rejection(label,trial,forbidden)
        label="consistent_observation_only_markers"
        folder,manifest,evidence,record=prepare(label)
        for f in ("native/initial-state.json","native/saturated-rule-composition.json"):
            altered(record,f,lambda p:mutations.edit(p,mutations.observation_only))
        write(manifest,evidence)
        experiment["attempts"][label]=require_rejection(label,invoke(manifest,donors,args.target,folder/"library.json"),forbidden)
        # Simulate editing even the native receipt and every editable sample hash.
        # The trust index distributed separately with the compiler remains untouched.
        label="forged_native_receipt_and_literal"
        folder,manifest,evidence,record=prepare(label)
        graph_name="native/saturated-rule-composition.json"
        receipt_name="native/acceptance.json"
        altered(record,graph_name,lambda p:mutations.edit(p,mutations.foreign_ground_literal))
        def forge(receipt):
            receipt["artifact_sha256"]["saturated-rule-composition.json"]=record["artifacts"][graph_name]["sha256"]
        altered(record,receipt_name,lambda p:mutations.edit(p,forge))
        record["native_acceptance"]=read(folder/record["artifacts"][receipt_name]["path"])
        write(manifest,evidence)
        experiment["attempts"][label]=require_rejection(label,invoke(manifest,donors,args.target,folder/"library.json"),forbidden)
        # No data rehash on this first fault: the integrity layer itself should catch it.
        folder,manifest,evidence,record=prepare("raw_digest_mismatch")
        altered(record,"native/saturated-rule-composition.json",lambda p:mutations.edit(p,mutations.foreign_swapped_row),False)
        experiment["attempts"]["raw_digest_mismatch"]=require_rejection("raw_digest_mismatch",invoke(manifest,donors,args.target,folder/"library.json"),forbidden)
        donor_name=next(k for k,v in original["donors"].items() if any(s["sample_id"]==sid for s in v["samples"]))
        replacement=next((p for k,p in donors.items() if k!=donor_name and sha(p)!=sha(donors[donor_name])),None)
        if replacement is not None:
            label="foreign_compiled_donor"
            folder,manifest,evidence,record=prepare(label)
            fake=dict(donors);fake[donor_name]=replacement
            experiment["attempts"][label]=require_rejection(label,invoke(manifest,fake,args.target,folder/"library.json"),forbidden)
        if args.unrelated_target is not None:
            label="unrelated_compiled_target"
            folder,manifest,evidence,record=prepare(label)
            experiment["attempts"][label]=require_rejection(label,invoke(manifest,donors,args.unrelated_target,folder/"library.json"),forbidden)
        if args.foreign is not None:
            native0=source_dir/selected["artifacts"]["native/saturated-rule-composition.json"]["path"]
            alien0=args.foreign/"native/saturated-rule-composition.json"
            def sizes(p):
                g=read(p);return [len(g["values"]),len(g["rows"])]
            assert sizes(native0)==sizes(alien0) and sha(native0)!=sha(alien0)
            assert read(args.foreign/"native/acceptance.json")["accepted"] is True
            experiment["foreign"]={"cardinalities":sizes(native0),"original_graph_sha":sha(native0),"alien_graph_sha":sha(alien0)}
            for label,files in [
                ("other_real_graph_only",["native/saturated-rule-composition.json"]),
                ("other_real_source_and_export",[f for f in selected["artifacts"] if f!="origin.json"])]:
                folder,manifest,evidence,record=prepare(label)
                for f in files:
                    if f not in record["artifacts"]:continue
                    src=args.foreign/f
                    if sha(src)==record["artifacts"][f]["sha256"]:continue
                    altered(record,f,lambda p,src=src:shutil.copyfile(src,p))
                write(manifest,evidence)
                experiment["attempts"][label]=require_rejection(label,invoke(manifest,donors,args.target,folder/"library.json"),forbidden)
    return experiment


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",required=True,type=Path)
    parser.add_argument("--donor",required=True,action="append")
    parser.add_argument("--target",required=True,type=Path)
    parser.add_argument("--foreign",type=Path)
    parser.add_argument("--unrelated-target",type=Path)
    parser.add_argument("--scratch",required=True,type=Path)
    parser.add_argument("--out",required=True,type=Path)
    args=parser.parse_args();report=run_suite(args);write(args.out,report)
    leaked=[k for k,v in report["attempts"].items() if v["leaked_paths"]]
    if leaked:raise SystemExit("Unexpected authorized mutations: "+", ".join(leaked))
    print(f"Positive authorization and {len(report['attempts'])} negative controls passed.")
