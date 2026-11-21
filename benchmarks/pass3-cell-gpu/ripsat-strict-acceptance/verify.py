"""Reconcile archived CLI, semantic and normal-Cargo checks without running inference."""
from pathlib import Path
import hashlib
import json

HERE=Path(__file__).resolve().parent

def load(name):return json.loads((HERE/name).read_bytes())

def main():
    meta=load("manifest.json")
    for name,digest in meta["files"].items():
        assert hashlib.sha256((HERE/name).read_bytes()).hexdigest()==digest,name
    cli=load("adapter-checks.json");parts=load("proof-checks.json");source=load("source-checks.json")
    assert cli["source_manifest_sha"]==load("../ripsat-donor-evidence/trust.json")["manifest_sha256"]
    assert cli["positive_paths"]==[[[143,1,55]]] and cli["original_sample"]=="dot-product-p143-o1-c55-full"
    assert cli["producer_only_trace"]["default_authorized"]==0
    assert cli["foreign"]["cardinalities"]==[15,14] and cli["foreign"]["original_graph_sha"]!=cli["foreign"]["alien_graph_sha"]
    expected={"stopped","unfinished_round_with_saturated_label","producer_scope_only","observation_only",
              "wrong_grounded_report_source","wrong_ordered_port_same_cardinality","local_alias_instead_of_second_input",
              "wrong_ground_literal","missing_original_named_parent","wrong_op","wrong_op_and_fact_id_rebound",
              "activation_same_run","wrong_but_later_source_run","wrong_consumer_fact_version","local_history_application_missing",
              "disconnected_native_applications","wrong_later_consumer_read","produced_port_resolves_to_another_class",
              "local_history_read_dependency_changed","consistent_observation_only_markers","raw_digest_mismatch",
              "foreign_compiled_donor","unrelated_compiled_target","other_real_graph_only","other_real_source_and_export","forged_native_receipt_and_literal"}
    assert set(cli["attempts"])==expected
    for case,a in cli["attempts"].items():
        assert a["exit"] in (0,1) and a["forbidden_paths"]==1 and a["authorized_paths"]==0 and not a["leaked_paths"],case
        assert a["reasons"] or (a["static_consumer_paths"] and case in ("disconnected_native_applications","wrong_later_consumer_read")),case
    assert len(parts["rejections"])==13 and parts["native_positive"]["consumer"]
    proof=parts["native_positive"]["consumer"][0]
    assert proof["producer_record"]==0 and proof["consumer_record"]==8 and proof["write_read_token"]==6
    assert parts["native_positive"]["local_result"]==5
    assert source["local_source_execution"]=={"pairs":2,"unguarded":2,"alias_guarded":1}
    assert set(source["rejected"])=={"constructor_set_has_no_static_return","instance_equality_as_template_theorem","missing_independent_source_premise"}
    assert "7 passed; 0 failed" in (HERE/"cargo-reference.txt").read_text()
    print("Archived default rejection matrix, source/semantic controls and normal Cargo execution verified.")

if __name__=="__main__":main()
